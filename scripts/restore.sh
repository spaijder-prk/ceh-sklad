#!/usr/bin/env sh
set -eu

MODE="development"
if [ "${1:-}" = "--production" ]; then
  MODE="production"
  shift
fi

if [ "$#" -ne 1 ]; then
  echo "Использование: ./scripts/restore.sh [--production] backups/имя_файла.dump" >&2
  exit 2
fi

FILE="$1"
if [ ! -f "$FILE" ]; then
  echo "Файл резервной копии не найден: $FILE" >&2
  exit 2
fi
if [ ! -s "$FILE" ]; then
  echo "Файл резервной копии пуст: $FILE" >&2
  exit 2
fi

if [ "$MODE" = "production" ]; then
  ENV_FILE=".env.production"
  COMPOSE_FILE="docker-compose.production.yml"
  if [ ! -f "$ENV_FILE" ]; then
    echo "Не найден production env: $ENV_FILE" >&2
    exit 2
  fi
else
  ENV_FILE=""
  COMPOSE_FILE="docker-compose.yml"
  if [ -f .env ]; then
    ENV_FILE=".env"
  fi
fi

if [ -n "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "./$ENV_FILE"
  set +a
fi

compose() {
  if [ -n "$ENV_FILE" ]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

echo "Останавливаю backend на время восстановления..."
compose stop backend

cleanup() {
  echo "Запускаю backend..."
  compose start backend >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cat "$FILE" | compose exec -T db pg_restore \
  -U "${POSTGRES_USER:-ceh}" \
  -d "${POSTGRES_DB:-ceh_sklad}" \
  --clean --if-exists --no-owner

compose start backend
trap - EXIT INT TERM

echo "Ожидаю health backend; миграции будут проверены при старте..."
ATTEMPT=0
while [ "$ATTEMPT" -lt 30 ]; do
  if compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).read()" >/dev/null 2>&1; then
    echo "Восстановление завершено, backend готов."
    exit 0
  fi
  ATTEMPT=$((ATTEMPT + 1))
  sleep 2
done

echo "Данные восстановлены, но backend не стал ready за отведенное время." >&2
exit 3
