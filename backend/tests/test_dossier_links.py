"""Dossier context links: lead card ⇄ client card обращения.

Регресс на «не гадать, какое обращение выбрать»: письмо на карточке
клиента показывает свою заявку; карточка заявки показывает другие
обращения и письма этого клиента (скоуп-aware, как LeadInline).
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client as DjClient
from django.urls import reverse

from crm.models import Client as CrmClient
from crm.models import EmailDirection, EmailMessage, EmailStatus
from leads.models import Lead

User = get_user_model()


def _staff_with_perms(*, username: str, codenames: tuple[str, ...]) -> Any:
    """Create staff user with given model permissions."""
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password12",
        is_staff=True,
        is_superuser=False,
    )
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _superuser() -> Any:
    """Admin user without scope limits."""
    return User.objects.create_superuser(
        username="root",
        email="root@example.com",
        password="password12",
    )


def _make_lead(client_obj: CrmClient, **overrides: Any) -> Lead:
    """Lead linked to the given CRM client card."""
    defaults: dict[str, Any] = {
        "lead_type": Lead.LeadType.CONSULTATION,
        "name": "Контакт",
        "email": client_obj.email,
        "company": client_obj.company,
        "message": "x" * 20,
        "client": client_obj,
    }
    defaults.update(overrides)
    return Lead.objects.create(**defaults)


@pytest.mark.django_db
def test_client_card_email_shows_its_lead_link() -> None:
    """Письмо в инлайне клиента → ссылка на заявку, к которой оно привязано."""
    admin = _superuser()
    crm = CrmClient.objects.create(email="buyer@x.test", name="B")
    lead = _make_lead(crm)
    EmailMessage.objects.create(
        client=crm,
        lead=lead,
        direction=EmailDirection.INBOUND,
        status=EmailStatus.RECEIVED,
        from_email="buyer@x.test",
        subject="Уточнение по КП",
    )
    page = DjClient()
    page.force_login(admin)

    response = page.get(reverse("admin:crm_client_change", args=[crm.pk]))

    assert response.status_code == 200
    assert reverse("admin:leads_lead_change", args=[lead.pk]) in response.content.decode()


@pytest.mark.django_db
def test_lead_card_shows_client_dossier_links() -> None:
    """Карточка заявки → досье-блок: другие заявки и письма этого клиента."""
    admin = _superuser()
    crm = CrmClient.objects.create(email="buyer@x.test", name="B")
    current = _make_lead(crm)
    other = _make_lead(crm, name="Второй контакт")
    mail = EmailMessage.objects.create(
        client=crm,
        lead=other,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.SENT,
        to_email="buyer@x.test",
        subject="КП по приводу",
    )
    page = DjClient()
    page.force_login(admin)

    response = page.get(reverse("admin:leads_lead_change", args=[current.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    # карточка клиента
    assert reverse("admin:crm_client_change", args=[crm.pk]) in body
    # другая заявка этого клиента
    assert reverse("admin:leads_lead_change", args=[other.pk]) in body
    # письмо досье + его связь с заявкой
    assert mail.subject in body
    assert reverse("admin:crm_emailmessage_change", args=[mail.pk]) in body


@pytest.mark.django_db
def test_lead_dossier_hides_out_of_scope_leads() -> None:
    """Менеджер не видит в досье заявки коллеги (скоуп как у LeadInline)."""
    mgr_a = _staff_with_perms(
        username="dossier-a",
        codenames=("view_lead", "change_lead"),
    )
    mgr_b = _staff_with_perms(
        username="dossier-b",
        codenames=("view_lead", "change_lead"),
    )
    crm = CrmClient.objects.create(email="buyer@x.test", name="B")
    current = _make_lead(crm, assignee=mgr_a)
    foreign = _make_lead(
        crm,
        name="Чужой контакт",
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=mgr_b,
    )
    page = DjClient()
    page.force_login(mgr_a)

    response = page.get(reverse("admin:leads_lead_change", args=[current.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert reverse("admin:leads_lead_change", args=[foreign.pk]) not in body
