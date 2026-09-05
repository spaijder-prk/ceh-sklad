FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY entrypoint-production.sh /usr/local/bin/ceh-entrypoint

RUN pip install --upgrade pip \
    && pip install . \
    && chmod +x /usr/local/bin/ceh-entrypoint \
    && useradd --create-home --uid 10001 ceh \
    && chown -R ceh:ceh /app

USER ceh

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/ceh-entrypoint"]
