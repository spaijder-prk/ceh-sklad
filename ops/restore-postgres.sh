#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="${CEH_COMPOSE_FILE:-compose.production.yml}"
ENV_FILE="${CEH_ENV_FILE:-.env.production}"
BACKUP_FILE="${1:-}"

if [[ -z "$BACKUP_FILE" ]]; then
    echo "Использование: CEH_CONFIRM_RESTORE=YES ops/restore-postgres.sh <backup.dump>" >&2
    exit 2
fi
if [[ "${CEH_CONFIRM_RESTORE:-}" != "YES" ]]; then
    echo "Восстановление отменено: задайте CEH_CONFIRM_RESTORE=YES" >&2
    exit 2
fi
if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "Файл резервной копии не найден: $BACKUP_FILE" >&2
    exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "Команда docker не найдена" >&2
    exit 2
fi
if [[ ! -f "$COMPOSE_FILE" || ! -f "$ENV_FILE" ]]; then
    echo "Не найдены compose/env файлы production" >&2
    exit 2
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
checksum_file="${BACKUP_FILE}.sha256"

if [[ -f "$checksum_file" ]]; then
    (
        cd "$(dirname "$BACKUP_FILE")"
        sha256sum -c "$(basename "$checksum_file")"
    )
else
    echo "Предупреждение: рядом нет SHA-256 файла, проверяется только структура архива" >&2
fi

# Для проверки и восстановления достаточно PostgreSQL; Redis запускаем заранее,
# чтобы после успешного restore backend мог подняться без дополнительной задержки.
"${COMPOSE[@]}" up -d db redis >/dev/null
"${COMPOSE[@]}" exec -T db pg_restore --list < "$BACKUP_FILE" >/dev/null

"${COMPOSE[@]}" stop backend web >/dev/null 2>&1 || true
restore_complete=0
on_exit() {
    if (( restore_complete == 0 )); then
        echo "Восстановление не завершено. Backend и web оставлены остановленными для проверки БД." >&2
    fi
}
trap on_exit EXIT

"${COMPOSE[@]}" exec -T db sh -eu -c '
    case "$POSTGRES_DB" in
        ""|postgres|template0|template1|*[!A-Za-z0-9_]*)
            echo "Недопустимое имя целевой базы: $POSTGRES_DB" >&2
            exit 2
            ;;
    esac

    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$POSTGRES_DB'\'' AND pid <> pg_backend_pid();" >/dev/null
    dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"
    createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
'

# Если имя архива не указано, pg_restore читает custom-архив из stdin.
"${COMPOSE[@]}" exec -T db sh -eu -c '
    exec pg_restore \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --no-owner \
        --no-privileges \
        --exit-on-error
' < "$BACKUP_FILE"

restore_complete=1
trap - EXIT

# Entrypoint backend применит более новые Alembic-миграции, если архив был создан
# предыдущей версией приложения.
"${COMPOSE[@]}" up -d backend web >/dev/null
printf 'База восстановлена из: %s\n' "$BACKUP_FILE"
printf 'Backend и web запущены; проверьте /health и контрольные остатки.\n'
