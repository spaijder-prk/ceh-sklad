#!/bin/sh
set -eu

read_secret() {
    tr -d '\r\n' < "$1"
}

DB_PASSWORD="$(read_secret /run/secrets/db_password)"
JWT_SECRET="$(read_secret /run/secrets/jwt_secret)"
INTEGRATION_KEY="$(read_secret /run/secrets/integration_api_key)"
REDIS_PASSWORD="$(read_secret /run/secrets/redis_password)"

if [ -z "$DB_PASSWORD" ]; then
    echo "Файл секрета db_password пуст" >&2
    exit 1
fi
if [ "${#JWT_SECRET}" -lt 32 ]; then
    echo "JWT-секрет должен содержать не менее 32 символов" >&2
    exit 1
fi
if [ -z "$REDIS_PASSWORD" ]; then
    echo "Файл секрета redis_password пуст" >&2
    exit 1
fi

export CEH_ENVIRONMENT=production
export CEH_AUTO_CREATE_SCHEMA=false
export CEH_JWT_SECRET="$JWT_SECRET"
if [ -n "$INTEGRATION_KEY" ]; then
    export CEH_INTEGRATION_API_KEY="$INTEGRATION_KEY"
else
    unset CEH_INTEGRATION_API_KEY || true
fi

export CEH_DATABASE_URL="$(
    python - "$POSTGRES_USER" "$DB_PASSWORD" "$POSTGRES_HOST" "$POSTGRES_PORT" "$POSTGRES_DB" <<'PY'
import sys
from urllib.parse import quote_plus

user, password, host, port, database = sys.argv[1:]
print(
    f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}@"
    f"{host}:{port}/{quote_plus(database)}"
)
PY
)"

export CEH_REDIS_URL="$(
    python - "$REDIS_PASSWORD" "$REDIS_HOST" "$REDIS_PORT" <<'PY'
import sys
from urllib.parse import quote_plus

password, host, port = sys.argv[1:]
print(f"redis://:{quote_plus(password)}@{host}:{port}/0")
PY
)"

alembic upgrade head
exec uvicorn app.observed_app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips="*" \
    --no-access-log
