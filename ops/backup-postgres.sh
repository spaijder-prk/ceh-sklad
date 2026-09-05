#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="${CEH_COMPOSE_FILE:-compose.production.yml}"
ENV_FILE="${CEH_ENV_FILE:-.env.production}"
BACKUP_DIR="${CEH_BACKUP_DIR:-./backups}"
RETENTION_DAYS="${CEH_BACKUP_RETENTION_DAYS:-14}"

if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    echo "CEH_BACKUP_RETENTION_DAYS должен быть целым неотрицательным числом" >&2
    exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Команда docker не найдена" >&2
    exit 2
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Не найден compose-файл: $COMPOSE_FILE" >&2
    exit 2
fi
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Не найден env-файл: $ENV_FILE" >&2
    exit 2
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
mkdir -p "$BACKUP_DIR"
umask 077

timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
backup_file="$BACKUP_DIR/ceh_sklad_${timestamp}.dump"
tmp_file="${backup_file}.partial"
checksum_file="${backup_file}.sha256"

cleanup() {
    rm -f "$tmp_file"
}
trap cleanup EXIT

"${COMPOSE[@]}" up -d db >/dev/null

# Дамп создается внутри контейнера PostgreSQL, поэтому на хосте не нужен pg_dump.
"${COMPOSE[@]}" exec -T db sh -eu -c '
    exec pg_dump \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --format=custom \
        --compress=6 \
        --no-owner \
        --no-privileges
' > "$tmp_file"

if [[ ! -s "$tmp_file" ]]; then
    echo "PostgreSQL создал пустой файл резервной копии" >&2
    exit 1
fi

# Если имя архива не указано, pg_restore читает custom-архив из stdin.
"${COMPOSE[@]}" exec -T db pg_restore --list < "$tmp_file" >/dev/null

mv "$tmp_file" "$backup_file"
(
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$backup_file")" > "$(basename "$checksum_file")"
)

if (( RETENTION_DAYS > 0 )); then
    find "$BACKUP_DIR" -type f \
        \( -name 'ceh_sklad_*.dump' -o -name 'ceh_sklad_*.dump.sha256' \) \
        -mtime "+$RETENTION_DAYS" -delete
fi

trap - EXIT
printf 'Резервная копия создана: %s\n' "$backup_file"
printf 'Контрольная сумма: %s\n' "$checksum_file"
