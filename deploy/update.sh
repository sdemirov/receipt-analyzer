#!/usr/bin/env bash
# Redeploy the Digital Receipts Analyzer after repo changes.
#
#   ./deploy/update.sh              pull + rebuild image + recreate container
#   ./deploy/update.sh --data-only  skip the app; just re-sync Drive + rebuild the DB
#   ./deploy/update.sh --no-pull    rebuild/restart from the current checkout (no git pull)
#
# Local-only files (.env, docker-compose.override.yml, gdrive-sa.json) are git-excluded,
# so `git pull` never clobbers them. The API reads the DB per request, so a data refresh
# needs no restart.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

DATA_ONLY=0
DO_PULL=1
for arg in "$@"; do
  case "$arg" in
    --data-only) DATA_ONLY=1 ;;
    --no-pull)   DO_PULL=0 ;;
    -h|--help)   sed -n '2,9p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if [ "$DATA_ONLY" -eq 1 ]; then
  echo "[update] data-only: sync Drive + rebuild DB"
  exec "$REPO_DIR/deploy/refresh.sh"
fi

if [ "$DO_PULL" -eq 1 ]; then
  echo "[update] git pull"
  git pull --ff-only
fi

echo "[update] build image"
docker compose build

echo "[update] recreate container"
docker compose up -d

echo "[update] waiting for health"
for _ in $(seq 1 20); do
  s="$(docker inspect -f '{{.State.Health.Status}}' dra 2>/dev/null || echo none)"
  echo "  $s"
  [ "$s" = healthy ] && break
  sleep 3
done

echo "[update] done — https://receipts.threepixels.dev"
