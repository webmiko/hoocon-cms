#!/bin/bash
set -euo pipefail

fix_media_permissions() {
    if [ "$(id -u)" -ne 0 ]; then
        return 0
    fi
    mkdir -p /app/media /app/staticfiles
    chown -R appuser:appuser /app/media /app/staticfiles
}

run_as_appuser() {
    if [ "$(id -u)" -eq 0 ]; then
        gosu appuser "$@"
    else
        "$@"
    fi
}

fix_media_permissions

run_as_appuser python manage.py migrate --noinput
run_as_appuser python manage.py collectstatic --noinput

if [ "$(id -u)" -eq 0 ]; then
    exec gosu appuser "$@"
else
    exec "$@"
fi
