"""Staff commands in messenger replies: templates, transfer, assignment."""

from __future__ import annotations

import logging
import re
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.db.models import QuerySet

from supportchat.models import Conversation, Message, ReplyTemplate
from supportchat.presentation import staff_public_name
from supportchat.services import SupportChatError, add_staff_note, add_staff_reply

logger = logging.getLogger(__name__)

_STAFF_ASSIGN_RE = re.compile(
    r"^(?:@([\w.@+-]+)|/assign\s+@?([\w.@+-]+))\s*$",
    re.IGNORECASE,
)
_STAFF_TEMPLATE_RE = re.compile(r"^/t\s+([\w-]+)\s*$", re.IGNORECASE)
_STAFF_TEMPLATE_LIST = {"/t", "/tpls", "/templates"}


def support_staff_queryset() -> QuerySet[Any]:
    """Active managers/admins/superusers who may own a support dialog."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from accounts.roles import GROUP_ADMIN, GROUP_MANAGER

    return (
        get_user_model()
        .objects.filter(is_active=True, is_staff=True)
        .filter(Q(groups__name__in=(GROUP_MANAGER, GROUP_ADMIN)) | Q(is_superuser=True))
        .distinct()
    )


def support_transfer_target(user_pk: int | None) -> AbstractBaseUser | None:
    """Colleague picked by an assign button — only support staff, never any is_staff."""
    if not user_pk:
        return None
    return support_staff_queryset().filter(pk=user_pk).first()


def _staff_user_by_handle(handle: str) -> AbstractBaseUser | None:
    """Active staff user for an ``@handle`` (username, email or first name)."""
    from django.db.models import Q

    h = (handle or "").lstrip("@").strip()
    if not h:
        return None
    return (
        support_staff_queryset()
        .filter(
            Q(username__iexact=h)
            | Q(email__iexact=h)
            | Q(first_name__iexact=h)
            | Q(username__iregex=rf"^{re.escape(h)}@"),
        )
        .first()
    )


def submit_staff_reply(
    staff_user: AbstractBaseUser,
    conversation_id: int,
    body: str,
) -> tuple[bool, str]:
    """Staff reply/note/assign/template from any messenger (shared core).

    Commands inside the text: ``/note …`` internal note, ``@handle`` or
    ``/assign …`` reassign, ``/t slug`` canned reply (``/t`` lists slugs).

    Returns:
        (ok, plain-text status for the staff chat).
    """
    from django.contrib.auth.models import PermissionsMixin

    if not isinstance(staff_user, PermissionsMixin) or not staff_user.has_perm(
        "supportchat.change_conversation",
    ):
        logger.warning(
            "staff_reply_denied user=%s conv=%s — missing supportchat.change_conversation",
            getattr(staff_user, "pk", None),
            conversation_id,
        )
        return False, "Недостаточно прав для ответа в поддержке."

    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return False, f"Диалог #{conversation_id} не найден."

    text = body.strip()
    if text.lower().startswith("/note"):
        try:
            add_staff_note(conversation, text[5:].strip(), author=staff_user)
        except SupportChatError as exc:
            return False, str(exc)
        return True, f"Заметка сохранена · диалог #{conversation_id} (клиенту не видна)"

    if text.lower() in _STAFF_TEMPLATE_LIST:
        templates = active_reply_templates()
        if not templates:
            return False, "Шаблоны не настроены (Admin → Диалоги поддержки → Шаблоны ответов)."
        lines = "\n".join(f"• /t {tpl.slug} — {tpl.title}" for tpl in templates)
        return True, f"Шаблоны ответов:\n{lines}\n\nИспользование: #{conversation_id} /t код"

    template_match = _STAFF_TEMPLATE_RE.match(text)
    if template_match:
        slug = template_match.group(1)
        template = find_reply_template(slug)
        if template is None:
            return False, f"Шаблон «{slug}» не найден. Список: /t"
        text = template.body

    assign_match = _STAFF_ASSIGN_RE.match(text)
    if assign_match:
        handle = assign_match.group(1) or assign_match.group(2) or ""
        target = _staff_user_by_handle(handle)
        if target is None:
            return False, f"Сотрудник «{handle}» не найден (username/email/имя)."
        assign_conversation(conversation, target, actor=staff_user)
        return True, f"Диалог #{conversation_id} передан: {staff_public_name(target)}"

    try:
        message = add_staff_reply(conversation, text, author=staff_user)
    except SupportChatError as exc:
        return False, str(exc)

    from supportchat.tasks import deliver_outbound_message

    try:
        deliver_outbound_message.delay(message.pk)
    except Exception as exc:
        logger.warning(
            "staff_reply_deliver_enqueue_failed error=%s",
            type(exc).__name__,
        )
        deliver_outbound_message(message.pk)

    label = conversation.display_name or conversation.external_user_id
    channel = conversation.get_channel_display()
    return True, f"Ответ отправлен · диалог #{conversation_id} · {channel} · {label}"


def find_reply_template(slug: str) -> ReplyTemplate | None:
    """Active canned reply by slug (``/t dostavka`` in messengers)."""
    key = (slug or "").strip().lower()
    if not key:
        return None
    return ReplyTemplate.objects.filter(slug__iexact=key, is_active=True).first()


def active_reply_templates() -> list[ReplyTemplate]:
    """Canned replies for Admin composer dropdown / messenger ``/t`` list."""
    return list(ReplyTemplate.objects.filter(is_active=True))


def staff_transfer_candidates(*, exclude_pk: int | None = None) -> list[AbstractBaseUser]:
    """Active managers/admins/superusers for the «Передать» picker."""
    qs = support_staff_queryset().order_by("first_name", "username")
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return list(qs)


def notify_conversation_assigned(
    conversation: Conversation,
    target: AbstractBaseUser,
    actor: AbstractBaseUser | None,
) -> None:
    """Ping the new assignee in bound messengers; the notice carries reply buttons."""
    from social.publishers import publish_max, publish_telegram

    actor_label = staff_public_name(actor)
    label = conversation.display_name or conversation.external_user_id
    channel_label = conversation.get_channel_display()
    text = f"🔀 {actor_label} передал вам диалог #{conversation.pk} · {channel_label} · {label}"

    from accounts.telegram_alerts import telegram_chat_id_for

    chat_id = telegram_chat_id_for(target)
    if chat_id:
        from social.telegram_staff_reply import (
            staff_support_alert_reply_markup,
            store_support_alert_message_id,
        )

        result = publish_telegram(
            chat_id=chat_id,
            text=text,
            reply_markup=staff_support_alert_reply_markup(conversation.pk),
        )
        if result.ok and result.external_id:
            store_support_alert_message_id(conversation.pk, chat_id, result.external_id, text)

    profile = getattr(target, "max_profile", None)
    max_user_id = (getattr(profile, "max_user_id", "") or "").strip() if profile else ""
    if max_user_id and getattr(profile, "max_alerts_enabled", False):
        from social.max_staff_reply import (
            staff_support_alert_attachments,
            store_support_alert_mid,
        )

        result = publish_max(
            user_id=max_user_id,
            text=text,
            attachments=staff_support_alert_attachments(conversation.pk),
        )
        if result.ok and result.external_id:
            store_support_alert_mid(conversation.pk, max_user_id, result.external_id, text)


@transaction.atomic
def assign_conversation(
    conversation: Conversation,
    target: AbstractBaseUser | None,
    *,
    actor: AbstractBaseUser | None,
) -> Message:
    """Reassign the dialog to another staff member and log an internal note."""
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    conversation.assignee = target  # type: ignore[assignment]
    conversation.save(update_fields=["assignee", "updated_at"])
    target_label = staff_public_name(target) if target is not None else "—"
    actor_label = staff_public_name(actor)
    return add_staff_note(
        conversation,
        f"{actor_label}: диалог передан → {target_label}",
        author=actor,
    )
