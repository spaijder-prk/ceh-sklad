#!/usr/bin/env sh
set -eu

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M%S)
FILE="backups/ceh_sklad_${STAMP}.dump"

docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER:-ceh}" \
  -d "${POSTGRES_DB:-ceh_sklad}" \
  -Fc > "$FILE"

echo "Резервная копия создана: $FILE"
