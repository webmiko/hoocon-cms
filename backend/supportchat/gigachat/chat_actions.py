"""Branch buttons in support chat (call manager / continue with bot)."""

from __future__ import annotations

from supportchat.gigachat.triage import wants_manager

CALL_MANAGER_ACTION = "call_manager"
CONTINUE_BOT_ACTION = "continue_bot"

CALL_MANAGER_LABEL = "Позвать менеджера"
CONTINUE_BOT_LABEL = "Продолжить с ботом"


def manager_branch_actions() -> list[dict[str, str]]:
    """Offer handoff or keep chatting with the bot."""
    return [
        {"id": CALL_MANAGER_ACTION, "label": CALL_MANAGER_LABEL},
        {"id": CONTINUE_BOT_ACTION, "label": CONTINUE_BOT_LABEL},
    ]


def call_manager_only_actions() -> list[dict[str, str]]:
    """Single CTA when the bot already explained the next step."""
    return [{"id": CALL_MANAGER_ACTION, "label": CALL_MANAGER_LABEL}]


def actions_payload(actions: list[dict[str, str]]) -> dict[str, object]:
    return {"chat_actions": actions}


def normalize_chat_actions(raw: object) -> list[dict[str, str]]:
    """Public API shape for branch buttons on a message."""
    if not isinstance(raw, list):
        return []
    actions: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if action_id and label:
            actions.append({"id": action_id, "label": label})
    return actions


def inbound_chat_action(raw_payload: dict[str, object] | None) -> str:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    return str(payload.get("chat_action", "")).strip()


def inbound_requests_manager_handoff(
    text: str,
    raw_payload: dict[str, object] | None = None,
) -> bool:
    """Explicit user command: typed phrase or branch button."""
    if inbound_chat_action(raw_payload) == CALL_MANAGER_ACTION:
        return True
    return wants_manager(text)


def inbound_continue_with_bot(raw_payload: dict[str, object] | None) -> bool:
    return inbound_chat_action(raw_payload) == CONTINUE_BOT_ACTION
