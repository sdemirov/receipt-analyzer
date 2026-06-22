# Server deployment (Google Drive → rclone → Docker)

Production runs the same Docker Compose stack as local dev. Receipts live on
Google Drive; the server **syncs** them to disk and rebuilds the DB on a schedule.
See [`deploy/`](../deploy/) for the install scripts and systemd units.

## Why `rclone sync` (not mount)

OCR reads every Lidl PNG in full each run. Over a FUSE `rclone mount` that is slow
and can stall; `rclone sync` to local disk is fast and reliable. The OCR-text cache
(`data/ocr_cache/`, keyed by file content hash) means only **new or changed** PNGs
are OCR'd, so scheduled rebuilds are cheap after the first full build.

## Refresh pipeline

[`deploy/refresh.sh`](../deploy/refresh.sh) runs three steps in order:

1. **Lidl name dedupe** — `python3 -m tools.rename_lidl_pngs --apply`  
   Phone uploads often land on Drive as multiple files all named `Файл_000.png`.
   Google Drive allows duplicate names; `rclone sync` does not — it keeps one file
   per path and logs `Duplicate object found in source - ignoring` for the rest.
   The rename script gives each PNG a unique Windows-style name (`Файл_000.png`,
   `Файл_000 (1).png`, …) via the Drive API **in place** (`files.update`). It is
   idempotent: when all names are already unique, it exits in ~1–2 seconds with
   “Nothing to do.”

2. **`rclone sync`** — pulls `gdrive:` → `RECEIPTS_HOST_DIR` (default
   `/srv/digitalreceipts`). Sync is pull-only for receipt files; the rename step
   above is the only write back to Drive.

3. **`build_db`** — `docker compose run --rm app python -m extract.build_db`  
   Rebuilds `data/receipts.db` (OCR cache makes repeat runs fast).

The API reads the DB per request — no container restart after a refresh.

## Scheduling

**systemd timer (recommended):** copy `deploy/receipts-refresh.service` and
`deploy/receipts-refresh.timer` to `/etc/systemd/system/`, set `User` and
`WorkingDirectory` in the service unit, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now receipts-refresh.timer
systemctl list-timers receipts-refresh.timer
journalctl -u receipts-refresh.service -f
```

Default schedule: **hourly** (`OnCalendar=hourly`), plus ~2 minutes after boot.

**cron fallback:**

```cron
0 * * * * /opt/receipts/deploy/refresh.sh >> /var/log/receipts-refresh.log 2>&1
```

Manual run: `./deploy/refresh.sh` or `./deploy/update.sh --data-only`.

## One-time server setup

```bash
# Prereqs: docker + compose plugin, rclone, git, openssl (for rename JWT)
sudo apt-get update && sudo apt-get install -y rclone docker.io docker-compose-plugin

git clone … /opt/receipts && cd /opt/receipts
cp deploy/.env.example .env
# RECEIPTS_HOST_DIR=/srv/digitalreceipts , RCLONE_REMOTE=gdrive:
sudo mkdir -p /srv/digitalreceipts

# rclone remote → DigitalReceipts root (lists Kaufland/ and Lidl/)
rclone ls gdrive: | head

chmod +x deploy/refresh.sh
./deploy/refresh.sh
docker compose up -d
```

Redeploy after code changes: `./deploy/update.sh` (pull, rebuild image, recreate
container). Data-only refresh: `./deploy/update.sh --data-only`.

## Google Drive / rclone configuration

| Requirement | Why |
|-------------|-----|
| **Service account** shared on the DigitalReceipts folder as **Editor** | Rename uses Drive `files.update`; Viewer is not enough. |
| **rclone `scope = drive`** (not `drive.readonly`) | Needed if you use rclone write operations; the rename script uses the SA JSON directly but the remote should match your intent. |
| **`service_account_file`** in rclone config pointing at `gdrive-sa.json` | Same credentials as `rclone ls` / `sync`. |
| **`root_folder_id`** = the DigitalReceipts folder ID | Remote root is that folder, not all of Drive. |

`rclone sync` itself only reads from Drive. The scheduled rename is the one
maintenance write.

## Adding receipts from your phone

1. Upload Kaufland PDFs to `Kaufland/` and Lidl photos to `Lidl/` on Drive.
2. Wait for the hourly refresh (or run `./deploy/refresh.sh`).
3. Refresh the browser.

**Lidl naming:** If the Windows Drive client uploads photos, it usually suffixes
duplicates automatically (`Файл_000 (1).png`, …). If you upload from a phone and
every file is `Файл_000.png`, the refresh script renames them before sync — no
manual step.

**Kaufland:** Use dated PDF names (`YYYY-MM-DD.pdf`) — see
[`tools/rename_pdfs.py`](../tools/rename_pdfs.py) on the machine where PDFs land.

## Public HTTPS

The Compose service binds to loopback (`127.0.0.1:8090` via
`docker-compose.override.yml`). Front it with nginx or Caddy + TLS (e.g.
`receipts.threepixels.dev`).

## What persists on the server

| Path | Role |
|------|------|
| `data/receipts.db` | Rebuilt each refresh; mounted into the app container |
| `data/product_mapping.csv`, `data/product_meta.csv` | Survive rebuilds — back these up |
| `data/ocr_cache/` | Speeds up Lidl OCR across rebuilds |
| `/srv/digitalreceipts/` | Synced copy of Drive receipts |
| `.env`, `rclone.conf`, `gdrive-sa.json` | Secrets — never commit |
