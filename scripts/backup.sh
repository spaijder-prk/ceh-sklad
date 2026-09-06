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

compose() {
  if [ -n "$ENV_FILE" ]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

umask 077
mkdir -p backups
STAMP=$(date -u +%Y%m%d_%H%M%S)
FILE="backups/ceh_sklad_${STAMP}.dump"
CHECKSUM_FILE="${FILE}.sha256"
META_FILE="${FILE}.meta"

cleanup_failed_backup() {
  rm -f "$FILE" "$CHECKSUM_FILE" "$META_FILE"
}

if ! compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$FILE"; then
  cleanup_failed_backup
  echo "pg_dump завершился ошибкой." >&2
  exit 3
fi

if [ ! -s "$FILE" ]; then
  cleanup_failed_backup
  echo "Резервная копия не создана или пуста." >&2
  exit 3
fi

# Проверяем, что создан именно читаемый PostgreSQL custom archive, а не текст ошибки/обрезанный файл.
if ! compose exec -T db pg_restore --list < "$FILE" >/dev/null; then
  cleanup_failed_backup
  echo "Резервная копия не проходит pg_restore --list." >&2
  exit 3
fi

BACKUP_DIR=$(dirname "$FILE")
BACKUP_NAME=$(basename "$FILE")
(
  cd "$BACKUP_DIR"
  sha256sum "$BACKUP_NAME" > "${BACKUP_NAME}.sha256"
)

SCHEMA_REVISION=$(compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT version_num FROM alembic_version"' | tr -d '\r\n')
SOURCE_COMMIT=$(git rev-parse HEAD 2>/dev/null || printf 'unknown')
SIZE_BYTES=$(wc -c < "$FILE" | tr -d ' ')
CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > "$META_FILE" <<EOF
created_at=$CREATED_AT
mode=$MODE
schema_revision=$SCHEMA_REVISION
source_commit=$SOURCE_COMMIT
size_bytes=$SIZE_BYTES
archive=$BACKUP_NAME
checksum=$(cut -d ' ' -f 1 "$CHECKSUM_FILE")
EOF

chmod 600 "$FILE" "$CHECKSUM_FILE" "$META_FILE"

echo "Резервная копия создана и проверена: $FILE"
echo "BACKUP_FILE=$FILE"
