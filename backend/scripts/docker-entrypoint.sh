#!/bin/bash
set -euo pipefail

fix_media_permissions() {
    if [ "$(id -u)" -ne 0 ]; then
        return 0
    fi
    mkdir -p /app/media /app/private_media /app/staticfiles
    chown -R appuser:appuser /app/media /app/private_media /app/staticfiles
}

run_as_appuser() {
    if [ "$(id -u)" -eq 0 ]; then
        gosu appuser "$@"
    else
        "$@"
    fi
}

fix_media_permissions

# Only the web service bootstraps the DB; workers would race it.
if [ "${RUN_BOOTSTRAP:-1}" = "1" ]; then
    run_as_appuser python manage.py migrate --noinput
    run_as_appuser python manage.py seed_wiki
    run_as_appuser python manage.py collectstatic --noinput
fi

if [ "$(id -u)" -eq 0 ]; then
    exec gosu appuser "$@"
else
    exec "$@"
fi
