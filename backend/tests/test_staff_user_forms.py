"""Tests for staff User forms: login = email, display name = first_name."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse

from accounts.forms import StaffUserCreationForm
from leads.models import Lead
from leads.services import render_lead_notification


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=False)
def test_staff_user_creation_sets_username_from_email() -> None:
    """Creating staff copies email into username and keeps display name."""
    form = StaffUserCreationForm(
        data={
            "email": "Ivan.Manager@Hoocon.ru",
            "first_name": "Иван",
            "usable_password": "true",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        },
    )
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.email == "ivan.manager@hoocon.ru"
    assert user.username == "ivan.manager@hoocon.ru"
    assert user.first_name == "Иван"
    assert user.has_usable_password() is True


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=True)
def test_staff_user_creation_otp_mode_skips_password() -> None:
    """With email OTP, create user without permanent password."""
    form = StaffUserCreationForm(
        data={
            "email": "otp.manager@hoocon.ru",
            "first_name": "Ольга",
            "usable_password": "false",
        },
    )
    assert form.is_valid(), form.errors
    user = form.save()
    assert user.email == "otp.manager@hoocon.ru"
    assert user.username == "otp.manager@hoocon.ru"
    assert user.first_name == "Ольга"
    assert user.has_usable_password() is False


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=True)
def test_admin_add_user_otp_hides_password_fields(client) -> None:
    """OTP mode: add form has email + name, no password inputs."""
    admin = User.objects.create_superuser(
        username="creator@hoocon.ru",
        email="creator@hoocon.ru",
        password="password12",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:auth_user_add"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Логин (эл. почта)" in html
    assert "Имя для отображения" in html
    assert "одноразовым кодом" in html
    assert 'name="password1"' not in html
    assert 'name="password2"' not in html
    # Unfold input widgets give visible bordered fields (not bare border:0).
    assert "border-base-" in html
    assert 'id="id_email"' in html
    assert 'id="id_first_name"' in html


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=False)
def test_staff_user_creation_rejects_duplicate_email() -> None:
    """Duplicate email is rejected on create."""
    User.objects.create_user(
        username="dup@hoocon.ru",
        email="dup@hoocon.ru",
        password="ComplexPass123!",
    )
    form = StaffUserCreationForm(
        data={
            "email": "dup@hoocon.ru",
            "first_name": "Дубль",
            "usable_password": "true",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        },
    )
    assert form.is_valid() is False
    assert "email" in form.errors


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=False)
def test_admin_add_user_form_has_email_and_display_name(client) -> None:
    """Add-user Admin page asks for email login and display name."""
    admin = User.objects.create_superuser(
        username="creator2@hoocon.ru",
        email="creator2@hoocon.ru",
        password="password12",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:auth_user_add"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Логин (эл. почта)" in html
    assert "Имя для отображения" in html
    assert 'name="email"' in html
    assert 'name="first_name"' in html


@pytest.mark.django_db
def test_lead_notification_includes_assignee_display_name() -> None:
    """New-lead email names the assigned manager by first_name."""
    mgr = User.objects.create_user(
        username="anna@hoocon.ru",
        email="anna@hoocon.ru",
        password="password12",
        first_name="Анна",
        is_staff=True,
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        message="Нужен привод для вентиляции.",
        assignee=mgr,
    )
    _subject, text_body, html_body = render_lead_notification(lead)
    assert "Ответственный менеджер: Анна" in text_body
    assert "Анна" in html_body
