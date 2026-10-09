"""Tests for staff Wiki admin (browse + read HTML)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from content.models import WikiDocument

User = get_user_model()


@pytest.mark.django_db
def test_wiki_browse_page_for_superuser(client) -> None:
    """Staff with view_wikidocument sees Wiki index grouped by category."""
    admin_user = User.objects.create_superuser(
        username="wiki-admin",
        email="wiki-admin@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Тестовый отчёт",
        slug="test-report",
        category="Аналитика склада",
        summary="Пояснение к цифрам.",
        body="<p>42</p>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_browse")
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "Вики" in html
    assert "Тестовый отчёт" in html
    assert "Аналитика склада" in html
    assert "Пояснение к цифрам" in html


@pytest.mark.django_db
def test_wiki_read_full_html_document(client) -> None:
    """Full HTML documents are returned as-is for staff read view."""
    admin_user = User.objects.create_superuser(
        username="wiki-read",
        email="wiki-read@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Dashboard",
        slug="dash-full",
        body="<!DOCTYPE html><html><body><h1>Stock</h1></body></html>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_read", args=["dash-full"])
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert "<h1>Stock</h1>" in response.content.decode()


@pytest.mark.django_db
def test_wiki_read_fragment_uses_admin_wrapper(client) -> None:
    """HTML fragments render inside admin read template with |safe body."""
    admin_user = User.objects.create_superuser(
        username="wiki-frag",
        email="wiki-frag@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Фрагмент",
        slug="frag",
        body="<p>Фрагмент Wiki</p>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_read", args=["frag"])
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-wiki-read__body" in html
    assert "Фрагмент Wiki" in html


@pytest.mark.django_db
def test_csp_wiki_read_allows_inline_scripts_for_dashboards(client) -> None:
    """Wiki read CSP allows inline Chart.js bootstrap (staff HTML dashboards)."""
    admin_user = User.objects.create_superuser(
        username="wiki-csp",
        email="wiki-csp@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Dashboard",
        slug="dash-csp",
        body="<!DOCTYPE html><html><body><script>window.ok=1</script></body></html>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_read", args=["dash-csp"])
    response = client.get(url)
    csp = (
        response.headers.get("Content-Security-Policy")
        or response.headers.get("Content-Security-Policy-Report-Only")
        or ""
    )
    assert response.status_code == 200
    assert "'unsafe-inline'" in csp
    assert "nonce-" not in csp.split("script-src", 1)[1].split(";", 1)[0]


@pytest.mark.django_db
def test_wiki_stock_fixture_uses_self_hosted_chart_js() -> None:
    """Stock dashboard fixture loads Chart.js from static (CSP script-src 'self')."""
    from pathlib import Path

    wiki_dir = Path(__file__).resolve().parents[1] / "content" / "fixtures" / "wiki"
    for name in (
        "stock-dashboard-14-09-2026.html",
        "stock-dashboard-year-2025-09-2026-08.html",
    ):
        html = (wiki_dir / name).read_text(encoding="utf-8")
        assert "/static/admin/js/vendor/chart-4.4.4.umd.min.js" in html
        assert "cdn.jsdelivr.net" not in html

    chart_js = Path(__file__).resolve().parents[1] / "static" / "admin" / "js" / "vendor" / "chart-4.4.4.umd.min.js"
    assert chart_js.is_file()
    assert "Chart" in chart_js.read_text(encoding="utf-8", errors="ignore")[:500]


@pytest.mark.django_db
def test_seed_wiki_admin_3_0_covers_crm_ops() -> None:
    """Инструкция 3.0 описывает канбан КП, заказ из КП и отчёт РОП."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    doc = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    assert "Отчёт начальника отдела продаж" in doc.body
    assert "crm.send_weekly_sales_report" in doc.body
    assert "Создать заказ" in doc.body
    assert "следующий контакт" in doc.body
    assert 'id="rop"' in doc.body
    assert "Копия черновиком" in doc.body
    assert "07.10.2026" in doc.body
    assert 'id="chat"' in doc.body
    assert 'id="changelog"' in doc.body
    assert "Диалоги поддержки" in doc.body
    assert "отчёт роп" in doc.summary.casefold()
    assert "диалоги" in doc.summary.casefold()


@pytest.mark.django_db
def test_seed_wiki_novosystem_guide() -> None:
    """Вики Новосистем: виджет, ЛК UIS, ID сотрудника; ссылка в руководстве 3.0."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    doc = WikiDocument.objects.get(slug="novosystem-telephony-guide")
    assert doc.category == "Инструкции"
    for anchor in ("widget", "uis", "employee", "call", "journal", "trouble"):
        assert f'id="{anchor}"' in doc.body
    assert "ID сотрудника UIS" in doc.body
    assert "call_session_id" in doc.body
    assert "employee_id" in doc.body
    assert "именно на этот номер" not in doc.body
    assert "?token=" in doc.body
    assert "Укажите ID сотрудника UIS в профиле пользователя" in doc.body
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    assert "09.10.2026" in guide.body
    assert "Телефония Новосистем (UIS)" in guide.body
    mango = WikiDocument.objects.get(slug="mango-telephony-guide")
    assert "настройках сервера" not in mango.body


@pytest.mark.django_db
def test_seed_wiki_guide_explains_manual_catalog_edits() -> None:
    """Руководство 3.0: ручные правки карточки и галочки блокировки — в каталоге и журнале."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    assert 'id="catalog-manual"' in guide.body
    for label in ("тексты правлены вручную", "правлено вручную", "скрыто вручную"):
        assert label in guide.body
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert "Пересборка карточек из мануалов" in changelog


@pytest.mark.django_db
def test_seed_wiki_guide_explains_company_member_confirmation() -> None:
    """Руководство 3.0: реквизиты компании в кабинете — только после «подтверждён менеджером»."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert 'id="changelog-company-confirm"' in changelog
    assert "подтверждён менеджером" in changelog


@pytest.mark.django_db
def test_seed_wiki_guide_explains_quote_transitions_and_mail_matching() -> None:
    """Руководство 3.0: порядок статусов КП и привязка писем только от клиента заявки."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert 'id="changelog-quote-transitions"' in changelog
    assert "Черновик сразу в «Согласовано» не перетащить" in changelog
    assert "только письма её клиента" in changelog


@pytest.mark.django_db
def test_seed_wiki_guide_explains_staged_chat_handoff() -> None:
    """Руководство 3.0: бот не забирает передачу менеджеру через минуту."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert 'id="changelog-chat-handoff"' in changelog
    assert "менеджеры заняты" in changelog
    assert "через 30 минут" in changelog


@pytest.mark.django_db
def test_seed_wiki_guide_explains_pdn_consent_and_kept_manual_edits() -> None:
    """Руководство 3.0: согласие 152-ФЗ в карточках; редиректы и статьи не затираются импортом."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert 'id="changelog-pdn-consent"' in changelog
    assert "Согласие на обработку ПДн" in changelog
    assert 'id="changelog-manual-edits-kept"' in changelog
    assert "правлено вручную" in changelog
    assert changelog.index("changelog-pdn-consent") < changelog.index("changelog-chat-handoff")


@pytest.mark.django_db
def test_seed_wiki_guide_explains_chat_and_telephony_guards() -> None:
    """Руководство 3.0: одна оценка, «Передать» только менеджерам, скрытый токен вебхука, https для Mango."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert 'id="changelog-chat-telephony-guards"' in changelog
    assert "Оценка уже сохранена" in changelog
    assert "https://" in changelog
    assert changelog.index("changelog-chat-telephony-guards") < changelog.index("changelog-pdn-consent")
    row = changelog.split('id="changelog-chat-telephony-guards"', 1)[1].split("</tr>", 1)[0]
    assert row.count("<td>") + row.count("<td ") == 3


@pytest.mark.django_db
def test_seed_wiki_includes_year_stock_dashboard() -> None:
    """Yearly stock dashboard seed is wired in seed_wiki."""
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("seed_wiki", stdout=out)
    doc = WikiDocument.objects.get(slug="ostatki-prodazhi-god-2025-09-2026-08")
    assert "сен 2025" in doc.title
    assert "const DATA = " in doc.body
    assert '"total_sold": 29432' in doc.body
    assert 'id="procurement"' in doc.body
    assert '"procurement":' in doc.body
    assert 'href="#forecast"' in doc.body
    assert '"forecast_rows":' in doc.body
    assert '"planning":' in doc.body
    assert "chartSeason" in doc.body
    assert "chartForecast" in doc.body


@pytest.mark.django_db
def test_seed_wiki_keeps_admin_edits_and_deactivation() -> None:
    """seed_wiki на каждом старте затирал правки вики из админки и включал выключенные страницы."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    doc = WikiDocument.objects.get(slug="mango-telephony-guide")
    assert doc.seed_hash
    doc.body = "<p>Правка менеджера</p>"
    doc.is_active = False
    doc.save()

    out = StringIO()
    call_command("seed_wiki", stdout=out)
    doc.refresh_from_db()
    assert doc.body == "<p>Правка менеджера</p>"
    assert doc.is_active is False
    assert "Skipped Wiki: mango-telephony-guide" in out.getvalue()

    call_command("seed_wiki", "--force", stdout=StringIO())
    doc.refresh_from_db()
    assert doc.body != "<p>Правка менеджера</p>"
    assert doc.is_active is False


@pytest.mark.django_db
def test_seed_wiki_refreshes_unedited_page_from_repo() -> None:
    """Неправленная страница обновляется из репозитория (руководство доходит до прода)."""
    from io import StringIO

    from django.core.management import call_command

    from content.management.commands.seed_wiki import body_hash

    call_command("seed_wiki", stdout=StringIO())
    doc = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    old = "<p>Старая версия из репозитория</p>"
    WikiDocument.objects.filter(pk=doc.pk).update(body=old, seed_hash=body_hash(old))

    call_command("seed_wiki", stdout=StringIO())
    doc.refresh_from_db()
    assert 'id="changelog"' in doc.body


@pytest.mark.django_db
def test_wiki_browse_requires_permission(client) -> None:
    """User without content.view_wikidocument cannot open Wiki browse."""
    user = User.objects.create_user(
        username="no-wiki",
        email="no-wiki@example.com",
        password="password12",
        is_staff=True,
    )
    client.force_login(user)
    url = reverse("admin:content_wikidocument_browse")
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_seed_wiki_guide_explains_lead_contact_verification() -> None:
    """Руководство 3.0: заявка с сайта видна в кабинете после «в работу», КП или галочки."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide")
    changelog = guide.body.split('id="changelog"', 1)[1]
    assert 'id="changelog-contact-verified"' in changelog
    assert "контакт подтверждён" in changelog


@pytest.mark.django_db
def test_seed_wiki_mango_guide_has_webhook_address_and_rejected_call() -> None:
    """Гайд Mango: адрес внешней системы для событий и ошибка «Mango отклонил звонок»."""
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="mango-telephony-guide")
    assert 'id="trouble-journal-empty"' in guide.body
    assert "/api/telephony/mango" in guide.body
    assert 'id="trouble-rejected"' in guide.body
