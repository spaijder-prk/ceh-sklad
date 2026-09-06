#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
umask 077

if [ ! -f .env.production ]; then
  echo "Не найден .env.production" >&2
  exit 2
fi

BACKUP_DIR="${CEH_BACKUP_DIR:-backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
ARCHIVE="$BACKUP_DIR/ceh_sklad_caddy_pki_${STAMP}.tar.gz"
CHECKSUM="$ARCHIVE.sha256"

cleanup() {
  if [ -f "$ARCHIVE" ] && [ ! -s "$ARCHIVE" ]; then
    rm -f "$ARCHIVE" "$CHECKSUM"
  fi
}
trap cleanup EXIT INT TERM

docker compose --env-file .env.production -f docker-compose.production.yml \
  exec -T caddy tar -C /data -czf - caddy/pki > "$ARCHIVE"

if [ ! -s "$ARCHIVE" ]; then
  echo "Caddy PKI backup пуст" >&2
  exit 3
fi

if ! tar -tzf "$ARCHIVE" | grep -q 'caddy/pki/authorities/local/root.crt'; then
  echo "В backup Caddy PKI не найден root.crt" >&2
  exit 3
fi
if ! tar -tzf "$ARCHIVE" | grep -q 'caddy/pki/authorities/local/root.key'; then
  echo "В backup Caddy PKI не найден root.key" >&2
  exit 3
fi

sha256sum "$ARCHIVE" > "$CHECKSUM"
chmod 600 "$ARCHIVE" "$CHECKSUM"

echo "Создан закрытый Caddy PKI backup: $ARCHIVE"
echo "Checksum: $CHECKSUM"
echo "ВНИМАНИЕ: архив содержит private key внутреннего CA. Храните его как секрет и копируйте в защищённое off-site хранилище."
