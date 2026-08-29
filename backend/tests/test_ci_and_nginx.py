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


def test_ci_workflow_has_check_job_with_postgres() -> None:
    """CI has a merged check job (pytest + lint) with a Postgres service."""
    import yaml

    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    check_job = data["jobs"].get("check")
    assert check_job is not None
    services = check_job.get("services", {})
    assert "postgres" in services
    steps = check_job.get("steps", [])
    step_runs = [s.get("run", "") for s in steps if isinstance(s, dict)]
    joined = "\n".join(step_runs)
    assert "pytest" in joined
    assert "ruff check" in joined
    assert "mypy" in joined
    assert "pip-audit" in joined


def test_ci_workflow_build_skipped_on_pull_request() -> None:
    """Build (image + frontend) runs only on push / workflow_dispatch."""
    import yaml

    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    build_job = data["jobs"].get("build")
    assert build_job is not None
    assert build_job.get("needs") == "check"
    assert "pull_request" not in build_job.get("if", "")


def test_ci_workflow_deploy_only_on_main() -> None:
    """Deploy SSH runs on push to main (or manual workflow_dispatch)."""
    import yaml

    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    deploy_job = data["jobs"].get("deploy")
    assert deploy_job is not None
    deploy_if = deploy_job.get("if", "")
    assert "refs/heads/main" in deploy_if
    assert "refs/heads/develop" not in deploy_if


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


def test_nginx_catalog_has_tighter_limit_and_bad_bot_ua() -> None:
    """Phase 1: catalog zone + scraper UA block; SEO allowlist in map."""
    conf = NGINX_CONF.read_text(encoding="utf-8")
    site = NGINX_SITE_INC.read_text(encoding="utf-8")
    assert "zone=catalog_api" in conf
    assert "rate=8r/s" in conf
    assert "limit_conn_zone" in conf
    assert "zone=api_conn" in conf
    assert "$hoocon_bad_bot" in conf
    assert "headlesschrome" in conf.lower()
    assert "research-scan" in conf.lower()
    assert "googlebot" in conf.lower()
    assert "yandex" in conf.lower()

    block = site.split("location /api/catalog/", 1)[1].split("\nlocation ", 1)[0]
    assert "zone=catalog_api" in block
    assert "limit_conn api_conn" in block
    assert "hoocon_bad_bot" in block
    assert "return 429" in block
    # Must not ban HeadlessChrome on HTML (PageSpeed / Lighthouse).
    spa = site.split("location @spa", 1)[1]
    assert "hoocon_bad_bot" not in spa


def test_deploy_remote_exports_redirects_map_after_health() -> None:
    """Post-deploy: regenerate redirects.map from DB so nginx matches Admin."""
    deploy = (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    assert "export_nginx_redirects" in deploy
    assert "DEPLOY_EXPORT_REDIRECTS" in deploy
    assert deploy.index("/api/health/") < deploy.index("export_nginx_redirects")
    assert deploy.index("export_nginx_redirects") < deploy.index("Prune")


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


def test_nginx_spa_location_gzips_without_proxy_cache() -> None:
    """@spa gzips HTML but must not proxy_cache (cache+gzip broke SPA GETs)."""
    content = _nginx_site_text()
    block = content.split("location @spa", 1)[1].split("\nlocation ", 1)[0]
    assert "gzip on" in block
    assert "gzip_types text/html" in block
    assert "gzip_proxied any" in block
    assert "proxy_cache" not in block
    assert 'proxy_set_header Accept-Encoding ""' in block
    assert "proxy_http_version 1.1" in block


def test_nginx_upstream_uses_keepalive() -> None:
    """Upstream keepalive cuts per-request gunicorn connect latency."""
    content = NGINX_CONF.read_text(encoding="utf-8")
    assert "upstream hoocon_app" in content
    assert "keepalive" in content
    # Zone may remain for future use / old hosts; @spa must not reference it.
    assert "proxy_cache_path" in content


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


def test_deploy_remote_prepares_spa_cache_dir_before_nginx_reload() -> None:
    """proxy_cache_path needs the on-disk dir before ``nginx -t`` on VPS."""
    deploy = (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    assert "mkdir -p /var/cache/nginx/hoocon_spa" in deploy
    assert "purged hoocon_spa proxy_cache" in deploy
    assert deploy.index("mkdir -p /var/cache/nginx/hoocon_spa") < deploy.index("nginx -t")


def test_vps_free_disk_script_exists() -> None:
    """Emergency pre-deploy cleanup when VPS disk is full."""
    script = ROOT / "scripts" / "vps-free-disk.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "vps-disk-cleanup.sh" in text
    assert "vps-free-disk.sh" in (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")


def test_redirects_map_has_documentation() -> None:
    """redirects.map has usage documentation (not just empty)."""
    content = REDIRECTS_MAP.read_text(encoding="utf-8")
    assert len(content) > 100  # has explanatory comments
    assert "tproduct" in content  # references the Tilda URL pattern
