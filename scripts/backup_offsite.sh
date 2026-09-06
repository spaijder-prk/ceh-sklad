#!/usr/bin/env sh
set -eu

if [ "$#" -ne 0 ]; then
  echo "Использование: ./scripts/backup_offsite.sh" >&2
  exit 2
fi

OUTPUT=$(./scripts/backup.sh --production)
printf '%s\n' "$OUTPUT"
FILE=$(printf '%s\n' "$OUTPUT" | sed -n 's/^BACKUP_FILE=//p' | tail -n 1)

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "Не удалось определить созданный production backup." >&2
  exit 3
fi

FILES="$FILE ${FILE}.sha256 ${FILE}.meta"
for item in $FILES; do
  if [ ! -s "$item" ]; then
    echo "Не найден обязательный файл резервной копии: $item" >&2
    exit 3
  fi
done

if [ -n "${CEH_BACKUP_OFFSITE_DIR:-}" ]; then
  DEST=${CEH_BACKUP_OFFSITE_DIR%/}
  mkdir -p "$DEST"
  for item in $FILES; do
    name=$(basename "$item")
    tmp="$DEST/.${name}.tmp.$$"
    install -m 600 "$item" "$tmp"
    mv -f "$tmp" "$DEST/$name"
  done
  (
    cd "$DEST"
    sha256sum -c "$(basename "$FILE").sha256" >/dev/null
  )
  echo "Off-site копия сохранена и проверена: $DEST/$(basename "$FILE")"
  exit 0
fi

if [ -n "${CEH_BACKUP_RCLONE_REMOTE:-}" ]; then
  command -v rclone >/dev/null 2>&1 || {
    echo "Для CEH_BACKUP_RCLONE_REMOTE требуется установленный rclone." >&2
    exit 4
  }
  REMOTE=${CEH_BACKUP_RCLONE_REMOTE%/}
  for item in $FILES; do
    rclone copyto "$item" "$REMOTE/$(basename "$item")" --retries 3 --low-level-retries 5
  done
  echo "Off-site копия отправлена через rclone: $REMOTE/$(basename "$FILE")"
  exit 0
fi

echo "Не настроено внешнее хранилище: задайте CEH_BACKUP_OFFSITE_DIR или CEH_BACKUP_RCLONE_REMOTE." >&2
exit 4
