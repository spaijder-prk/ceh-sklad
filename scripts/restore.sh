#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Использование: ./scripts/restore.sh backups/имя_файла.dump" >&2
  exit 2
fi

FILE="$1"
if [ ! -f "$FILE" ]; then
  echo "Файл резервной копии не найден: $FILE" >&2
  exit 2
fi

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

echo "Останавливаю backend на время восстановления..."
docker compose stop backend

cat "$FILE" | docker compose exec -T db pg_restore \
  -U "${POSTGRES_USER:-ceh}" \
  -d "${POSTGRES_DB:-ceh_sklad}" \
  --clean --if-exists --no-owner

echo "Запускаю backend; миграции будут проверены при старте..."
docker compose start backend

echo "Восстановление завершено."
