#!/usr/bin/env bash
# Pull new/changed receipts from Google Drive and rebuild the DB.
# The API reads the DB per request, so no app restart is needed afterwards.
#
# Before sync, duplicate Lidl PNG names on Drive are renamed in place (phone
# uploads often all share ``Файл_000.png``; rclone sync keeps only one per path).
#
# Configure via environment (or deploy/.env, see .env.example):
#   REPO_DIR        path to this checkout            (default: script's repo root)
#   RCLONE_REMOTE   rclone remote pointing at DigitalReceipts (default: gdrive:)
#   RECEIPTS_HOST_DIR  local sync target, also the Compose mount (default: /srv/digitalreceipts)
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive:}"
RECEIPTS_HOST_DIR="${RECEIPTS_HOST_DIR:-/srv/digitalreceipts}"

cd "$REPO_DIR"
# Load .env if present (provides RECEIPTS_HOST_DIR for both rclone and Compose).
[ -f .env ] && set -a && . ./.env && set +a

echo "[$(date -Is)] dedupe Lidl PNG names on Drive (if any)"
python3 -m tools.rename_lidl_pngs --apply

echo "[$(date -Is)] sync ${RCLONE_REMOTE} -> ${RECEIPTS_HOST_DIR}"
mkdir -p "$RECEIPTS_HOST_DIR"
# --fast-list: fewer Drive API calls; sync skips unchanged files (size+modtime).
rclone sync "$RCLONE_REMOTE" "$RECEIPTS_HOST_DIR" --fast-list

echo "[$(date -Is)] rebuild DB (OCR is cached; only new/changed PNGs are OCR'd)"
RECEIPTS_HOST_DIR="$RECEIPTS_HOST_DIR" docker compose run --rm app python -m extract.build_db

echo "[$(date -Is)] done"
