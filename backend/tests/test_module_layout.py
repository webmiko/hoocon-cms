"""Large modules split by responsibility stay split (crm.admin, supportchat.services)."""

from __future__ import annotations

from pathlib import Path

from django.contrib import admin

from crm.models import (
    Activity,
    Call,
    Client,
    ClientDocument,
    Company,
    EmailAttachment,
    EmailMessage,
    EmailTemplate,
    InboundMailboxState,
    Quote,
)


def test_every_crm_model_registered_after_package_split() -> None:
    """Разбиение crm/admin.py на пакет не должно терять регистрацию в Admin."""
    import crm.admin  # noqa: F401

    for model in (
        Activity,
        Call,
        Client,
        ClientDocument,
        Company,
        EmailAttachment,
        EmailMessage,
        EmailTemplate,
        InboundMailboxState,
        Quote,
    ):
        assert model in admin.site._registry, model.__name__


def test_crm_admin_modules_stay_small() -> None:
    """Один crm/admin.py на ~1800 строк менялся по любому поводу — держим модули по сущностям."""
    package = Path(__file__).resolve().parents[1] / "crm" / "admin"
    assert not (package.parent / "admin.py").exists()
    for module in package.glob("*.py"):
        assert len(module.read_text(encoding="utf-8").splitlines()) < 700, module.name


def test_supportchat_services_split_by_responsibility() -> None:
    """supportchat/services.py (~1100 строк) смешивал поток сообщений, оценку, команды и подписи."""
    import inspect

    from supportchat import presentation, rating, services, staff_actions

    root = Path(__file__).resolve().parents[1] / "supportchat"
    assert len((root / "services.py").read_text(encoding="utf-8").splitlines()) < 800
    for name in ("rate_conversation", "assign_conversation", "submit_staff_reply", "staff_public_name"):
        fn = getattr(services, name, None)
        assert fn is None or fn.__module__ != "supportchat.services", name
    assert rating.rate_conversation and staff_actions.assign_conversation
    # Labels are a leaf module: the message flow imports them, never the other way round.
    assert "supportchat.services" not in inspect.getsource(presentation)
