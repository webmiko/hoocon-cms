"""Tests for CI workflow + nginx stub (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1 — CI skeleton (.github/workflows/ci.yml) + deploy/nginx/
stub (hoocon.conf + redirects.map). docs/security-baseline.md §5 (CI gates).

These are config files (YAML/nginx), not Python — tests validate structure
and required directives rather than runtime behavior.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
NGINX_CONF = ROOT / "deploy" / "nginx" / "hoocon.conf"
NGINX_SITE_INC = ROOT / "deploy" / "nginx" / "hoocon-site.inc"
REDIRECTS_MAP = ROOT / "deploy" / "nginx" / "redirects.map"


def _nginx_site_text() -> str:
    """hoocon.conf + shared site body (locations live in the .inc)."""
    return NGINX_CONF.read_text(encoding="utf-8") + "\n" + NGINX_SITE_INC.read_text(encoding="utf-8")


def test_ci_workflow_file_exists() -> None:
    """The CI workflow file exists at the expected path."""
    assert CI_YML.exists(), f"Missing CI workflow: {CI_YML}"


def test_ci_workflow_is_valid_yaml() -> None:
    """The CI workflow is parseable YAML."""
    import yaml

    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "jobs" in data


def test_ci_workflow_has_test_job_with_postgres() -> None:
    """CI has a test job with a Postgres service container."""
    import yaml

    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    test_job = data["jobs"].get("test")
    assert test_job is not None
    services = test_job.get("services", {})
    assert "postgres" in services


def test_ci_workflow_has_lint_job() -> None:
    """CI has a lint job (ruff + mypy + pip-audit)."""
    import yaml

    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    lint_job = data["jobs"].get("lint")
    assert lint_job is not None
    # Lint job depends on test (gated pipeline).
    assert "needs" in lint_job
    assert "test" in lint_job["needs"]


def test_ci_workflow_triggers_on_develop_and_main() -> None:
    """CI runs on push/PR to develop and main (git-flow)."""
    import yaml

    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    on_config = data.get(True) or data.get("on")
    push_branches = on_config["push"]["branches"]
    assert "develop" in push_branches
    assert "main" in push_branches


def test_nginx_conf_file_exists() -> None:
    """The nginx site config exists at the expected path."""
    assert NGINX_CONF.exists(), f"Missing nginx config: {NGINX_CONF}"
    assert NGINX_SITE_INC.exists(), f"Missing nginx site include: {NGINX_SITE_INC}"


def test_nginx_conf_has_api_proxy() -> None:
    """nginx config proxies /api/ to the Django upstream."""
    content = _nginx_site_text()
    assert "location /api/" in content
    assert "proxy_pass" in content
    assert "upstream hoocon_app" in content


def test_nginx_conf_has_security_headers() -> None:
    """nginx config sets baseline security headers (nosniff, frame-deny)."""
    content = _nginx_site_text()
    assert "X-Content-Type-Options" in content
    assert "nosniff" in content
    assert "X-Frame-Options" in content


def test_nginx_conf_has_lead_rate_limit() -> None:
    """nginx config rate-limits /api/leads/ (anti-spam backstop)."""
    content = _nginx_site_text()
    assert "lead_limit" in content
    assert "location /api/leads/" in content


def test_nginx_conf_has_spa_fallback() -> None:
    """nginx config proxies HTML SPA routes to Django (@spa)."""
    content = _nginx_site_text()
    assert "try_files" in content
    assert "@spa" in content
    assert "proxy_pass" in content


def test_nginx_sw_js_is_not_cached() -> None:
    """``/sw.js`` must revalidate so deploys activate without a hard refresh."""
    content = _nginx_site_text()
    assert "location = /sw.js" in content
    block = content.split("location = /sw.js", 1)[1].split("location ", 1)[0]
    assert "no-cache" in block
    assert "no-store" in block


def test_nginx_conf_strips_trailing_slash() -> None:
    """nginx 301-rewrites trailing slash (БЗ canonical without /)."""
    content = _nginx_site_text()
    assert "rewrite ^/(.*)/$ /$1 permanent" in content
    assert "location = /index.html" in content


def test_nginx_conf_has_redirects_map_placeholder() -> None:
    """nginx config references the redirects.map (Iter 5 SEO migration)."""
    content = NGINX_CONF.read_text(encoding="utf-8")
    assert "redirects.map" in content


def test_nginx_conf_has_admin_block() -> None:
    """nginx config has an /admin/ block (IP allowlist stub for Iter 5)."""
    content = _nginx_site_text()
    assert "location /admin/" in content


def test_nginx_conf_enables_https_apex() -> None:
    """TLS cutover: LE paths, :443 for apex, HTTP→HTTPS and www→apex."""
    content = NGINX_CONF.read_text(encoding="utf-8")
    assert "listen 443 ssl" in content
    assert "http2 on" in content
    assert "/etc/letsencrypt/live/hoocon.ru/fullchain.pem" in content
    assert "return 301 https://hoocon.ru$request_uri" in content
    assert "include /etc/nginx/hoocon-site.inc" in content
    assert "hoocon-site.inc" in (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")


def test_redirects_map_file_exists() -> None:
    """The redirects.map stub file exists."""
    assert REDIRECTS_MAP.exists(), f"Missing redirects map: {REDIRECTS_MAP}"


def test_redirects_map_has_documentation() -> None:
    """redirects.map has usage documentation (not just empty)."""
    content = REDIRECTS_MAP.read_text(encoding="utf-8")
    assert len(content) > 100  # has explanatory comments
    assert "tproduct" in content  # references the Tilda URL pattern
