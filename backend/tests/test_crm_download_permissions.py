"""M15: CRM file downloads require the model's view permission, not only scope.

Regression: email attachments, client documents and call recordings were
served to any staff user who could see the client, even with the view
permission revoked for that model.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.base import ContentFile
from django.test import Client as DjangoClient
from django.urls import reverse

from crm.models import Call, CallDirection, Client, ClientDocument, DocumentKind, EmailAttachment, EmailMessage


def _staff(*perms: str) -> User:
    user = User.objects.create_user(f"staff-{len(perms)}-{User.objects.count()}", password="x", is_staff=True)
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _browser(user: User) -> DjangoClient:
    page = DjangoClient()
    page.force_login(user)
    return page


@pytest.fixture
def owned_files(db: None) -> dict[str, int]:
    manager = _staff()
    client = Client.objects.create(name="Клиент", email="dl@acme.test", assignee=manager)
    doc = ClientDocument.objects.create(
        client=client, kind=DocumentKind.OTHER, title="dog.pdf", file=ContentFile(b"%PDF", name="dog.pdf")
    )
    email = EmailMessage.objects.create(client=client, subject="s", to_email=client.email, created_by=manager)
    att = EmailAttachment.objects.create(email=email, filename="a.txt", file=ContentFile(b"a", name="a.txt"))
    call = Call.objects.create(
        client=client,
        manager=manager,
        direction=CallDirection.INBOUND,
        entry_id="entry-dl-1",
        recording=ContentFile(b"ID3", name="rec.mp3"),
    )
    return {"manager": manager.pk, "doc": doc.pk, "att": att.pk, "call": call.pk}


def _urls(ids: dict[str, int]) -> list[str]:
    return [
        reverse("admin:crm_clientdocument_download", args=[ids["doc"]]),
        reverse("admin:crm_emailattachment_download", args=[ids["att"]]),
        reverse("admin:crm_call_recording_download", args=[ids["call"]]),
    ]


@pytest.mark.django_db
def test_downloads_forbidden_without_view_permission(owned_files: dict[str, int]) -> None:
    """Менеджер карточки без права «просмотр» не скачивает файлы."""
    page = _browser(User.objects.get(pk=owned_files["manager"]))
    for url in _urls(owned_files):
        assert page.get(url).status_code == 403, url


@pytest.mark.django_db
def test_downloads_allowed_with_view_permission(owned_files: dict[str, int]) -> None:
    manager = User.objects.get(pk=owned_files["manager"])
    for codename in ("view_clientdocument", "view_emailattachment", "view_call"):
        manager.user_permissions.add(Permission.objects.get(codename=codename))
    page = _browser(User.objects.get(pk=manager.pk))
    for url in _urls(owned_files):
        assert page.get(url).status_code == 200, url


@pytest.mark.django_db
def test_recording_without_client_limited_to_own_calls() -> None:
    """Звонок без карточки: запись слушает только его менеджер или РОП."""
    owner = _staff("view_call")
    other = _staff("view_call")
    call = Call.objects.create(
        manager=owner,
        direction=CallDirection.INBOUND,
        entry_id="entry-dl-2",
        recording=ContentFile(b"ID3", name="rec2.mp3"),
    )
    url = reverse("admin:crm_call_recording_download", args=[call.pk])
    assert _browser(owner).get(url).status_code == 200
    assert _browser(other).get(url).status_code == 403
