#!/usr/bin/env bash
set -euo pipefail

# Backup large local datasets without committing them into git.
# Usage:
#   bash scripts/backup_data.sh weibo processed_data
# Env:
#   BACKUP_PART_SIZE=1900m (default)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <path1> [path2 ...]"
  echo "Example: $0 weibo processed_data"
  exit 2
fi

TS="$(date -u +%Y%m%d-%H%M%S)"
OUT_DIR="$ROOT_DIR/backups/$TS"
PART_SIZE="${BACKUP_PART_SIZE:-1900m}"

mkdir -p "$OUT_DIR"

INCLUDES=()
for p in "$@"; do
  if [[ -e "$p" ]]; then
    INCLUDES+=("$p")
  else
    echo "[warn] Skip missing path: $p" >&2
  fi
done

if [[ ${#INCLUDES[@]} -eq 0 ]]; then
  echo "No existing paths to backup. Nothing to do." >&2
  exit 1
fi

ARCHIVE="$OUT_DIR/data.tar.zst"
MANIFEST="$OUT_DIR/manifest.json"

# Create compressed tarball (streaming) for speed and low temp usage.
# We intentionally avoid GNU tar --zstd portability issues by piping.

echo "[info] Creating archive: $ARCHIVE"
# shellcheck disable=SC2016
{
  tar -cf - "${INCLUDES[@]}" \
  | zstd -T0 -19 -o "$ARCHIVE"
}

echo "[info] Splitting into parts (size=$PART_SIZE)"
split -b "$PART_SIZE" -d -a 3 "$ARCHIVE" "$ARCHIVE.part-"

echo "[info] Writing checksums"
(
  cd "$OUT_DIR"
  sha256sum "$(basename "$ARCHIVE")" "$(basename "$ARCHIVE").part-"* > SHA256SUMS
)

GIT_COMMIT=""
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"
fi

python3 - <<PY
import json, os, pathlib, time
out_dir = pathlib.Path(${OUT_DIR@Q})
archive = out_dir / 'data.tar.zst'
parts = sorted(out_dir.glob('data.tar.zst.part-*'))
manifest = {
  'created_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
  'git_commit': ${GIT_COMMIT@Q},
  'included_paths': ${INCLUDES[@]@Q},
  'archive': {'name': archive.name, 'size_bytes': archive.stat().st_size if archive.exists() else None},
  'parts': [{'name': p.name, 'size_bytes': p.stat().st_size} for p in parts],
  'notes': 'Upload parts + SHA256SUMS + manifest.json to external storage (e.g., GitHub Release assets).'
}
(out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print('[info] Wrote', out_dir / 'manifest.json')
PY

echo
echo "[done] Backup created in: $OUT_DIR"
echo "Next: upload the files in that folder to external storage (GitHub Releases / cloud drive)."
