FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-cache-dir . \
    && addgroup --system ceh \
    && adduser --system --ingroup ceh --home /nonexistent --no-create-home ceh \
    && chown -R ceh:ceh /app

USER ceh

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
