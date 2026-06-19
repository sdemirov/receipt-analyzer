# Deploying on a server (Hetzner) with rclone-sourced receipts

The app runs as the existing Docker Compose stack. Receipts come from Google Drive,
**read-only**, via rclone synced to local disk; a scheduled job pulls new files and
rebuilds the DB. The API reads the DB per request, so no restart is needed after a
rebuild.

## Why sync (not `rclone mount`)
OCR reads every Lidl PNG in full each run. Over a FUSE `rclone mount` that's slow and
can stall; `rclone sync` to local disk is fast and reliable. The OCR-text cache
(`data/ocr_cache/`, keyed by file content hash) means only **new or changed** PNGs are
OCR'd, so scheduled rebuilds are cheap.

## One-time setup

```bash
# 0. Prereqs on the host: docker + compose plugin, rclone, git.
sudo apt-get update && sudo apt-get install -y rclone docker.io docker-compose-plugin

# 1. Checkout
sudo git clone https://github.com/sdemirov/receipt-analyzer.git /opt/receipts-analyzer
cd /opt/receipts-analyzer

# 2. rclone remote that points at DigitalReceipts (read-only).
#    `rclone ls gdrive:` should list Kaufland/ and Lidl/.  (rclone config is per-user
#    in ~/.config/rclone/rclone.conf — keep it OFF git.)
rclone ls gdrive: | head

# 3. Environment: tell Compose + the script where to put the synced receipts.
cp deploy/.env.example .env
#   edit .env -> RECEIPTS_HOST_DIR=/srv/digitalreceipts , RCLONE_REMOTE=gdrive:
sudo mkdir -p /srv/digitalreceipts

# 4. First sync + build (also warms the OCR cache).
chmod +x deploy/refresh.sh
./deploy/refresh.sh

# 5. Start the app (restart: unless-stopped is already set).
docker compose up -d
#   API + UI on :8090  ->  http://SERVER_IP:8090
```

## Scheduling automatic processing of new uploads

**systemd timer (recommended):**
```bash
sudo cp deploy/receipts-refresh.service deploy/receipts-refresh.timer /etc/systemd/system/
#   edit the .service: set User= and WorkingDirectory= to match your checkout
sudo systemctl daemon-reload
sudo systemctl enable --now receipts-refresh.timer
systemctl list-timers receipts-refresh.timer      # confirm next run
journalctl -u receipts-refresh.service -f          # watch a run
```

**cron fallback:**
```cron
0 * * * * /opt/receipts-analyzer/deploy/refresh.sh >> /var/log/receipts-refresh.log 2>&1
```

Each run: `rclone sync` pulls new/changed files → `build_db` rebuilds the DB (cached OCR
→ fast) into the mounted `data/`. Refresh the browser to see new data.

## Notes
- **Read-only source:** `rclone sync` only pulls; it never writes back to Drive. The app
  writes only to the local `data/` (DB, CSVs, `ocr_cache/`).
- **Editable inputs persist:** `data/product_mapping.csv` and `data/product_meta.csv`
  survive rebuilds (renames/brand/category edits are kept). Back up `data/` to keep them.
- **Secrets:** never commit `.env` or `rclone.conf` (both are gitignored / per-user).
- **Public HTTPS:** to serve on a domain, front `:8090` (container `:8000`) with Caddy or
  nginx + TLS. (Not included here — ask if you want it scaffolded.)
- **Resources:** OCR + the React build need RAM/CPU for `docker compose build`; a small
  Hetzner CX/CPX instance is fine. Rebuilds after the first are light (cached OCR).
