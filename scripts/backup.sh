#!/usr/bin/env sh
set -eu

MODE="development"
if [ "${1:-}" = "--production" ]; then
  MODE="production"
  shift
fi
if [ "$#" -ne 0 ]; then
  echo "Использование: ./scripts/backup.sh [--production]" >&2
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

umask 077
mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M%S)
FILE="backups/ceh_sklad_${STAMP}.dump"

compose exec -T db pg_dump \
  -U "${POSTGRES_USER:-ceh}" \
  -d "${POSTGRES_DB:-ceh_sklad}" \
  -Fc > "$FILE"

if [ ! -s "$FILE" ]; then
  rm -f "$FILE"
  echo "Резервная копия не создана или пуста." >&2
  exit 3
fi

echo "Резервная копия создана: $FILE"
