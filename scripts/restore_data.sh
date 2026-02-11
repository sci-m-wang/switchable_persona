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
MANIFEST="$BACKUP_DIR/manifest.json"

if [[ ! -f "$BACKUP_DIR/SHA256SUMS" ]]; then
  echo "Missing SHA256SUMS in $BACKUP_DIR" >&2
  exit 1
fi

# If parts exist, try to rebuild archive from parts (handles truncated archive case).
if ls "$BACKUP_DIR"/data.tar.zst.part-* >/dev/null 2>&1; then
  # Validate part sizes against manifest before rebuilding.
  if [[ -f "$MANIFEST" ]] && command -v python3 >/dev/null 2>&1; then
    echo "[info] Validating part sizes against manifest..."
    if ! python3 -c "
import json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
backup_dir = pathlib.Path(sys.argv[2])
ok = True
for p in manifest.get('parts', []):
    f = backup_dir / p['name']
    if not f.exists():
        print(f\"[error] Missing part: {p['name']}\", file=sys.stderr)
        ok = False
    elif f.stat().st_size != p['size_bytes']:
        print(f\"[error] Size mismatch for {p['name']}: expected {p['size_bytes']} bytes, got {f.stat().st_size} bytes\", file=sys.stderr)
        ok = False
if not ok:
    sys.exit(1)
print('[info] Part sizes match manifest.')
" "$MANIFEST" "$BACKUP_DIR"; then
      echo "[error] Backup data is corrupted or incomplete. Re-download the backup files." >&2
      exit 1
    fi
  fi

  echo "[info] Rebuilding archive from parts..."
  cat "$BACKUP_DIR"/data.tar.zst.part-* > "$ARCHIVE"
elif [[ ! -f "$ARCHIVE" ]]; then
  echo "No archive and no parts found in $BACKUP_DIR" >&2
  exit 1
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
