"""VK callback handlers: staff replies, client menu, attachments, rating."""

from __future__ import annotations

import logging
from typing import Any

from django.core.files.base import ContentFile

from social.max_bot import resolve_menu_action
from social.max_staff_reply import (
    compose_staff_note_prompt,
    compose_staff_reply_prompt,
    parse_staff_alert_callback,
    parse_staff_reply_text,
)
from social.publishers import PublishResult, publish_vk_dm
from social.vk_client_menu import main_menu_keyboard_vk
from social.vk_staff_reply import (
    answer_vk_message_event,
    clear_pending_staff_reply,
    compose_staff_account_notice,
    compose_staff_reply_help,
    get_pending_staff_reply,
    set_pending_staff_reply,
    staff_transfer_keyboard,
    staff_user_for_vk_user_id,
    submit_staff_reply_from_vk,
)

logger = logging.getLogger("hoocon.social")


def send_to_vk_user(user_id: str, text: str, *, keyboard: str | None = None) -> PublishResult:
    return publish_vk_dm(user_id=user_id, text=text, keyboard=keyboard)


def try_staff_vk_reply(user_key: str, text: str) -> PublishResult | None:
    staff_user = staff_user_for_vk_user_id(user_key)
    if staff_user is None:
        return None

    parsed = parse_staff_reply_text(text)
    if parsed is not None:
        clear_pending_staff_reply(user_key)
    elif resolve_menu_action(text) is None:
        pending = get_pending_staff_reply(user_key)
        body = (text or "").strip()
        raw = body.casefold()
        if pending is not None and body and not raw.startswith("/reply"):
            conv_id, mode = pending
            parsed = (conv_id, f"/note {body}" if mode == "note" else body)
            clear_pending_staff_reply(user_key)

    if parsed is not None:
        conv_id, reply_body = parsed
        ok, status = submit_staff_reply_from_vk(staff_user, conv_id, reply_body)
        return send_to_vk_user(user_key, status if ok else f"Не отправлено: {status}")

    raw = (text or "").strip().casefold()
    if raw.startswith("/reply"):
        return send_to_vk_user(user_key, compose_staff_reply_help())

    if resolve_menu_action(text) is not None:
        clear_pending_staff_reply(user_key)
        return None

    pending = get_pending_staff_reply(user_key)
    if pending is not None:
        pending_conv, pending_mode = pending
        if pending_mode == "note":
            return send_to_vk_user(user_key, compose_staff_note_prompt(pending_conv))
        return send_to_vk_user(user_key, compose_staff_reply_prompt(pending_conv))

    return send_to_vk_user(user_key, compose_staff_account_notice())


def vk_message_attachment(message: dict[str, Any]) -> tuple[ContentFile, str, str] | None:
    from social.vk_http import vk_download_attachment

    attachments = message.get("attachments")
    if not isinstance(attachments, list):
        return None
    for att in attachments:
        if not isinstance(att, dict):
            continue
        kind = att.get("type")
        if kind == "photo":
            raw_photo = att.get("photo")
            photo: dict[str, Any] = raw_photo if isinstance(raw_photo, dict) else {}
            raw_sizes = photo.get("sizes")
            sizes: list[Any] = raw_sizes if isinstance(raw_sizes, list) else []
            best_url = ""
            best_area = 0
            for size in sizes:
                if not isinstance(size, dict):
                    continue
                url = str(size.get("url") or "").strip()
                w = int(size.get("width") or 0)
                h = int(size.get("height") or 0)
                area = w * h
                if url and area >= best_area:
                    best_area = area
                    best_url = url
            if not best_url:
                continue
            downloaded = vk_download_attachment(best_url)
            if downloaded is None:
                continue
            data, _ = downloaded
            return ContentFile(data, name="photo.jpg"), "photo.jpg", "image/jpeg"
        if kind == "doc":
            raw_doc = att.get("doc")
            doc: dict[str, Any] = raw_doc if isinstance(raw_doc, dict) else {}
            url = str(doc.get("url") or "").strip()
            title = str(doc.get("title") or "file")[:200]
            if not url:
                continue
            downloaded = vk_download_attachment(url)
            if downloaded is None:
                continue
            data, _ = downloaded
            return ContentFile(data, name=title), title, str(doc.get("ext") or "")
    return None


def handle_message_event(event: dict[str, Any]) -> PublishResult | None:
    obj = event.get("object")
    if not isinstance(obj, dict):
        return None
    user_id = obj.get("user_id")
    peer_id = obj.get("peer_id")
    event_id = obj.get("event_id")
    payload = str(obj.get("payload") or "").strip()
    if user_id is None or peer_id is None or event_id is None:
        return None
    user_key = str(user_id)

    from supportchat.rating import parse_support_rating_callback

    rating = parse_support_rating_callback(payload)
    if rating is not None:
        _handle_rating_callback(user_key, int(event_id), int(peer_id), int(user_id), *rating)
        return None

    parsed = parse_staff_alert_callback(payload)
    if parsed is None:
        return None
    action, conv_id, target_uid = parsed

    staff_user = staff_user_for_vk_user_id(user_key)
    if staff_user is None:
        answer_vk_message_event(
            event_id=int(event_id),
            user_id=int(user_id),
            peer_id=int(peer_id),
            text="Недоступно",
        )
        return None

    from supportchat.models import Conversation
    from supportchat.presentation import staff_public_name
    from supportchat.staff_actions import (
        STAFF_SUPPORT_DENIED,
        assign_conversation,
        notify_conversation_assigned,
        staff_may_handle_support,
        support_transfer_target,
    )

    if not staff_may_handle_support(staff_user):
        answer_vk_message_event(
            event_id=int(event_id),
            user_id=int(user_id),
            peer_id=int(peer_id),
            text=STAFF_SUPPORT_DENIED,
        )
        return None

    conv = Conversation.objects.filter(pk=conv_id).select_related("assignee").first()
    if conv is None:
        answer_vk_message_event(
            event_id=int(event_id),
            user_id=int(user_id),
            peer_id=int(peer_id),
            text=f"Диалог #{conv_id} не найден",
        )
        return None
    if conv.assignee_id is not None and conv.assignee_id != staff_user.pk:
        answer_vk_message_event(
            event_id=int(event_id),
            user_id=int(user_id),
            peer_id=int(peer_id),
            text=f"Диалог уже взял {staff_public_name(conv.assignee)}",
        )
        return None

    if action == "assign_to":
        target = support_transfer_target(target_uid)
        if target is None:
            answer_vk_message_event(
                event_id=int(event_id),
                user_id=int(user_id),
                peer_id=int(peer_id),
                text="Сотрудник не найден",
            )
            return None
        assign_conversation(conv, target, actor=staff_user)
        notify_conversation_assigned(conv, target, staff_user)
        answer_vk_message_event(
            event_id=int(event_id),
            user_id=int(user_id),
            peer_id=int(peer_id),
            text=f"Передан: {staff_public_name(target)}",
        )
        return send_to_vk_user(
            user_key,
            f"Диалог #{conv_id} передан: {staff_public_name(target)}",
        )

    if action == "assign":
        answer_vk_message_event(
            event_id=int(event_id),
            user_id=int(user_id),
            peer_id=int(peer_id),
            text=f"Диалог #{conv_id}",
        )
        return send_to_vk_user(
            user_key,
            f"Кому передать диалог #{conv_id}?",
            keyboard=staff_transfer_keyboard(conv_id, exclude_pk=staff_user.pk),
        )

    if action == "note":
        set_pending_staff_reply(user_key, conv_id, mode="note")
        answer_vk_message_event(
            event_id=int(event_id),
            user_id=int(user_id),
            peer_id=int(peer_id),
            text=f"Диалог #{conv_id}",
        )
        return send_to_vk_user(user_key, compose_staff_note_prompt(conv_id))

    set_pending_staff_reply(user_key, conv_id)
    answer_vk_message_event(
        event_id=int(event_id),
        user_id=int(user_id),
        peer_id=int(peer_id),
        text=f"Диалог #{conv_id}",
    )
    return send_to_vk_user(user_key, compose_staff_reply_prompt(conv_id))


def _handle_rating_callback(
    user_key: str,
    event_id: int,
    peer_id: int,
    user_id: int,
    conv_id: int,
    score: int,
) -> None:
    from supportchat.models import Channel, Conversation
    from supportchat.rating import rate_conversation
    from supportchat.services import SupportChatError

    conv = Conversation.objects.filter(pk=conv_id, channel=Channel.VK).first()
    ok = conv is not None and conv.external_user_id == user_key
    failure = "Не удалось сохранить оценку"
    if ok and conv is not None:
        try:
            rate_conversation(conv, score)
        except SupportChatError as exc:
            ok = False
            failure = str(exc)
    answer_vk_message_event(
        event_id=event_id,
        user_id=user_id,
        peer_id=peer_id,
        text="Спасибо за оценку!" if ok else failure,
    )


def reply_keyboard_for_action(action: str) -> str | None:
    # /chatid — plain reply; VK rejects keyboard without «Chat bot» community mode.
    if action == "chatid":
        return None
    if action in {"start", "help", "contacts", "contact", "catalog", "consultation", "where", "channel"}:
        return main_menu_keyboard_vk()
    return main_menu_keyboard_vk()
