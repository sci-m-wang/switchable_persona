#!/usr/bin/env bash
set -euo pipefail

# Restore backup created by scripts/backup_data.sh
# Usage:
#   bash scripts/restore_data.sh backups/<timestamp>

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup_dir>" >&2
  exit 2
fi

BACKUP_DIR="$1"
if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "Backup dir not found: $BACKUP_DIR" >&2
  exit 1
fi

ARCHIVE="$BACKUP_DIR/data.tar.zst"

if [[ ! -f "$BACKUP_DIR/SHA256SUMS" ]]; then
  echo "Missing SHA256SUMS in $BACKUP_DIR" >&2
  exit 1
fi

if [[ ! -f "$ARCHIVE" ]]; then
  echo "[info] Rebuilding archive from parts..."
  if ls "$BACKUP_DIR"/data.tar.zst.part-* >/dev/null 2>&1; then
    cat "$BACKUP_DIR"/data.tar.zst.part-* > "$ARCHIVE"
  else
    echo "No archive and no parts found in $BACKUP_DIR" >&2
    exit 1
  fi
fi

echo "[info] Verifying checksums..."
(
  cd "$BACKUP_DIR"
  sha256sum -c SHA256SUMS
)

echo "[info] Extracting archive into repo root..."
# Extract via streaming to avoid large temp files.
zstd -d -c "$ARCHIVE" | tar -xf -

echo "[done] Restore complete."
