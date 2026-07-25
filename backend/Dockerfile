# Hoocon CMS — multi-stage image (Poetry + gunicorn).
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1000 -d /app appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ARG GIT_SHA=unknown
ENV BUILD_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}

COPY --chown=appuser:appuser . .
RUN chmod +x scripts/docker-entrypoint.sh \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R appuser:appuser /app

EXPOSE 8000
ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --timeout 60 --access-logfile -"]
