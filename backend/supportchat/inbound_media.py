"""Client media from messengers: one message per file, visible loss notices.

MAX, VK and Telegram deliver photos, video and documents as URLs/ids that the
bot has to fetch. Anything that cannot be fetched must never vanish silently:
the manager sees a «⚠» line in the thread and the client is told where to send
the file instead.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from config.seller import SELLER_EMAIL
from supportchat.models import Conversation, Message, MessageDirection

logger = logging.getLogger("hoocon.supportchat")

KIND_LABELS = {
    "photo": "фото",
    "video": "видео",
    "audio": "аудио",
    "file": "файл",
}
REASON_LABELS = {
    "too_big": "файл слишком большой",
    "download_failed": "не удалось скачать, возможно файл слишком большой",
    "no_url": "мессенджер не передал ссылку на файл",
    "host_not_allowed": "ссылка ведёт на неподдерживаемый адрес",
    "unsupported": "этот тип вложения мессенджер не отдаёт боту",
    "limit": "превышен лимит вложений",
}


@dataclass(frozen=True)
class InboundFile:
    """A downloaded client file ready for ``add_inbound_message``."""

    file: Any
    name: str
    mime: str
    kind: str = "file"


@dataclass(frozen=True)
class MediaProblem:
    """A client attachment that could not be stored."""

    kind: str
    reason: str
    detail: str = ""


def messenger_media_max_bytes() -> int:
    """Per-file size cap for media fetched from messengers."""
    return max(1, int(getattr(settings, "SUPPORT_MESSENGER_MEDIA_MAX_BYTES", 50 * 1024 * 1024)))


def messenger_media_max_per_message() -> int:
    """Max files taken from a single messenger message."""
    return max(1, int(getattr(settings, "SUPPORT_MESSENGER_MEDIA_MAX_PER_MESSAGE", 10)))


def messenger_media_max_total_bytes() -> int:
    """Total bytes downloaded for one messenger message (bounds worker RAM)."""
    return max(1, int(getattr(settings, "SUPPORT_MESSENGER_MEDIA_MAX_TOTAL_BYTES", 100 * 1024 * 1024)))


class MediaBudget:
    """What one messenger message may still download.

    Computed before any download from the conversation's remaining file
    quota, the per-message file cap and the per-message byte cap, so a client
    whose thread is full cannot make a worker fetch files that will be dropped.
    """

    def __init__(self, slots: int, file_limit: int, total_bytes: int) -> None:
        self.slots = max(0, slots)
        self.file_limit = file_limit
        self.bytes_left = total_bytes

    def has_room(self) -> bool:
        return self.slots > 0 and self.bytes_left > 0

    @property
    def per_file_limit(self) -> int:
        """Largest single download still allowed."""
        return min(self.file_limit, self.bytes_left)

    def consume(self, size: int) -> None:
        self.slots -= 1
        self.bytes_left -= size


def _problem_summary(problems: list[MediaProblem]) -> str:
    counts = Counter((p.kind, p.reason) for p in problems)
    parts = []
    for (kind, reason), count in counts.items():
        label = KIND_LABELS.get(kind, "файл")
        prefix = f"{count} × " if count > 1 else ""
        parts.append(f"{prefix}{label} ({REASON_LABELS.get(reason, reason)})")
    return ", ".join(parts)


def manager_notice(problems: list[MediaProblem]) -> str:
    """Line stored in the thread so managers see what was lost and why."""
    lines = [
        f"⚠ Клиент приложил вложения, но не все удалось получить: {_problem_summary(problems)}. "
        f"Попросите прислать файлы на {SELLER_EMAIL} или ссылкой на облако.",
    ]
    lines.extend(p.detail for p in problems if p.detail)
    return "\n".join(lines)


def client_reply(problems: list[MediaProblem]) -> str:
    """Message to the client when some attachments were not accepted."""
    return (
        f"Не получилось принять: {_problem_summary(problems)}. "
        f"Пришлите, пожалуйста, файлы на {SELLER_EMAIL} или ссылкой на облако — "
        "менеджер подключится к диалогу."
    )


_BODY_LIMIT = 4000  # services._MAX_BODY_LEN


def _compose_body(text: str, problems: list[MediaProblem]) -> str:
    """Client text plus the loss notice, trimmed so the notice always fits."""
    body = (text or "").strip()
    if not problems:
        return body
    notice = manager_notice(problems)
    room = _BODY_LIMIT - len(notice) - 2
    if len(body) > room:
        body = body[: max(0, room - 1)].rstrip() + "…"
    return f"{body}\n\n{notice}".strip()


def ingest_inbound_media(
    conversation: Conversation,
    text: str,
    load: Callable[[MediaBudget], tuple[list[InboundFile], list[MediaProblem]]],
    *,
    external_message_id: str,
    raw_payload: dict[str, Any] | None,
    display_name: str,
) -> tuple[Any, list[MediaProblem]]:
    """Store the text with the first file, every further file as its own message.

    ``load`` downloads the attachments within the budget it is given; it is
    only called for a message that is not stored yet and after the remaining
    quota is known. Returns ``(auto_reply_or_None, problems)``: the outside-
    hours auto reply like ``add_inbound_message``, and every attachment that
    could not be stored (for the client reply). A message that only carried
    unreadable media is still stored, with the notice as its body.
    """
    from supportchat.services import SupportChatError, add_inbound_message

    ext = (external_message_id or "").strip()
    if (
        ext
        and Message.objects.filter(
            conversation=conversation,
            external_message_id=ext,
        ).exists()
    ):
        return None, []  # redelivered webhook: nothing to download, nothing to say twice

    used = (
        Message.objects.filter(conversation=conversation, direction=MessageDirection.INBOUND)
        .exclude(attachment="")
        .count()
    )
    quota = int(getattr(settings, "SUPPORT_ATTACHMENT_MAX_FILES", 20))
    budget = MediaBudget(
        min(messenger_media_max_per_message(), max(0, quota - used)),
        messenger_media_max_bytes(),
        messenger_media_max_total_bytes(),
    )
    files, problems = load(budget)

    def _store(body_text: str, item: InboundFile | None, message_id: str) -> Any:
        return add_inbound_message(
            conversation,
            body_text,
            external_message_id=message_id,
            raw_payload=raw_payload,
            display_name=display_name,
            attachment=item.file if item else None,
            attachment_name=item.name if item else "",
            attachment_mime=item.mime if item else "",
        )

    first = files[0] if files else None
    extra = files[1:]
    try:
        _inbound, auto = _store(_compose_body(text, problems), first, ext)
    except SupportChatError as exc:
        if first is None:
            raise
        # The file was rejected (quota race, validation): keep the text, tell the manager.
        logger.warning("support_media_first_rejected reason=%s", str(exc)[:160])
        problems.extend(MediaProblem(item.kind, "limit") for item in files)
        _inbound, auto = _store(_compose_body(text, problems), None, ext)
        extra = []

    for index, item in enumerate(extra, start=1):
        try:
            _more, more_auto = _store("", item, f"{ext}#{index}" if ext else "")
        except SupportChatError as exc:
            logger.warning("support_media_extra_rejected index=%s reason=%s", index, str(exc)[:160])
            lost = [MediaProblem(rest.kind, "limit") for rest in extra[index - 1 :]]
            problems.extend(lost)
            # The first message is already stored: leave a separate notice for managers.
            try:
                _store(manager_notice(lost), None, f"{ext}#lost" if ext else "")
            except SupportChatError:
                logger.warning("support_media_notice_failed")
            break
        auto = auto or more_auto
    return auto, problems
