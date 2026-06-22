"""Rename duplicate Lidl PNG filenames on Google Drive.

When many receipt photos are uploaded with the same name (e.g. all
``Файл_000.png``), the Windows Drive client auto-suffixes them locally as
``Файл_000 (1).png``, ``Файл_000 (2).png``, … but the cloud copies can keep
the identical name. ``rclone sync`` then keeps only one file per path.

This script lists PNGs under the Drive ``Lidl/`` folder (via rclone), detects
names shared by more than one object, and renames them in place through the
Drive API (``files.update``). That works for user-owned files shared with the
service account as Editor; ``rclone moveto``/``moveid`` fails because it
copy-then-deletes and the service account cannot delete those originals.

Safe by design:
- dry-run by default; pass ``--apply`` to actually rename;
- idempotent (already-unique names are left alone);
- renames by Drive file ID so same-path sources never collide.

Run from the project root (needs ``rclone`` + ``openssl``, same SA as
``deploy/refresh.sh``):

    python -m tools.rename_lidl_pngs            # preview
    python -m tools.rename_lidl_pngs --apply    # rename on Drive
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

PNG_RE = re.compile(r"^(.+?)(?: \((\d+)\))?\.png$", re.IGNORECASE)


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def png_stem(name: str) -> str:
    m = PNG_RE.match(name)
    return m.group(1) if m else Path(name).stem


def target_name(stem: str, index: int) -> str:
    """index 0 -> stem.png; 1+ -> stem (N).png (Windows Drive style)."""
    if index == 0:
        return f"{stem}.png"
    return f"{stem} ({index}).png"


def join_remote(remote: str, *parts: str) -> str:
    """Join rclone remote with path segments (gdrive: + Lidl/foo -> gdrive:Lidl/foo)."""
    remote = remote.rstrip("/")
    rel = "/".join(p.strip("/") for p in parts if p)
    if remote.endswith(":"):
        return f"{remote}{rel}"
    return f"{remote}/{rel}"


def rclone_config_show(remote_name: str) -> str:
    """Return `rclone config show` for the remote name (e.g. gdrive from gdrive:)."""
    name = remote_name.rstrip(":").split(",")[0]
    out = subprocess.run(
        ["rclone", "config", "show", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


def assert_remote_writable(remote: str) -> None:
    """Fail fast when the rclone remote is configured read-only."""
    try:
        cfg = rclone_config_show(remote)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"cannot read rclone config for {remote!r}: {exc.stderr}") from exc
    if "scope = drive.readonly" in cfg:
        name = remote.rstrip(":").split(",")[0]
        raise SystemExit(
            f"rclone remote {name!r} uses scope=drive.readonly — cannot rename on Drive.\n"
            "Create a write-capable remote (scope=drive) shared to the same folder, then run:\n"
            f"  python -m tools.rename_lidl_pngs --remote {name}-write --apply"
        )


def rclone_lsjson(remote: str, folder: str) -> list[dict]:
    path = join_remote(remote, folder)
    out = subprocess.run(
        ["rclone", "lsjson", path, "--files-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout or "[]")


def service_account_path(remote: str) -> Path:
    cfg = rclone_config_show(remote)
    for line in cfg.splitlines():
        if line.strip().startswith("service_account_file"):
            return Path(line.split("=", 1)[1].strip())
    raise SystemExit("no service_account_file in rclone config for this remote")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def drive_access_token(sa_path: Path) -> str:
    sa = json.loads(sa_path.read_text(encoding="utf-8"))
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claim = _b64url(json.dumps({
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/drive",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{claim}".encode()
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as kf:
        kf.write(sa["private_key"])
        key_path = kf.name
    try:
        sig = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=signing_input,
            check=True,
            capture_output=True,
        ).stdout
    finally:
        os.unlink(key_path)
    jwt = f"{header}.{claim}.{_b64url(sig)}"
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt,
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["access_token"]


def drive_rename_file(file_id: str, new_name: str, token: str) -> None:
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?supportsAllDrives=true"
    body = json.dumps({"name": new_name}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        if exc.code == 403:
            raise SystemExit(
                f"Drive returned 403 renaming file {file_id!r} to {new_name!r}.\n"
                f"{err}\n"
                "Share the DigitalReceipts folder with the service account "
                "(gdrive-sa.json client_email) as Editor."
            ) from exc
        raise SystemExit(f"Drive API error {exc.code}: {err}") from exc


def apply_plan(plan: list[tuple[dict, str]], token: str) -> None:
    for f, final in plan:
        drive_rename_file(f["ID"], final, token)


def build_plan(files: list[dict]) -> list[tuple[dict, str]]:
    """Return [(file_meta, new_name), ...] for files that must be renamed."""
    pngs = [f for f in files if not f.get("IsDir")
            and f.get("Name", "").lower().endswith(".png")]
    by_name: dict[str, list[dict]] = defaultdict(list)
    for f in pngs:
        by_name[f["Name"]].append(f)

    reserved = {name for name, group in by_name.items() if len(group) == 1}
    plan: list[tuple[dict, str]] = []

    for name, group in sorted(by_name.items()):
        if len(group) == 1:
            continue
        stem = png_stem(name)
        ordered = sorted(group, key=lambda f: (f.get("ModTime", ""), f["ID"]))
        idx = 0
        for f in ordered:
            while True:
                candidate = target_name(stem, idx)
                idx += 1
                if candidate not in reserved:
                    reserved.add(candidate)
                    if candidate != f["Name"]:
                        plan.append((f, candidate))
                    break
    return plan


def main(apply: bool, remote: str, folder: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    _load_dotenv()
    remote = remote or os.environ.get("RCLONE_REMOTE", "gdrive:")

    files = rclone_lsjson(remote, folder)
    pngs = [f for f in files
            if not f.get("IsDir") and f.get("Name", "").lower().endswith(".png")]
    by_name: dict[str, int] = defaultdict(int)
    for f in pngs:
        by_name[f["Name"]] += 1
    dup_groups = sum(1 for c in by_name.values() if c > 1)

    plan = build_plan(files)
    png_count = len(pngs)

    print(f"Remote: {remote}{folder}/")
    print(f"{png_count} PNG(s) · {dup_groups} duplicate name group(s) · "
          f"{len(plan)} to rename · {png_count - len(plan)} already unique\n")

    for f, new_name in plan:
        print(f"  {f['Name']:28} -> {new_name}  "
              f"(id={f['ID'][:12]}… mod={f.get('ModTime', '')[:10]})")

    if not plan:
        print("\nNothing to do.")
        return

    if not apply:
        print("\n(dry run — re-run with --apply to rename on Drive)")
        return

    assert_remote_writable(remote)
    token = drive_access_token(service_account_path(remote))
    apply_plan(plan, token)
    print(f"\nDone: renamed {len(plan)} file(s) on Drive.")
    print("Run deploy/refresh.sh (or wait for the hourly timer) to sync and rebuild the DB.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="perform the rename on Google Drive")
    ap.add_argument("--remote", default="",
                    help="rclone remote (default: RCLONE_REMOTE or gdrive:)")
    ap.add_argument("--folder", default="Lidl",
                    help="subfolder under the remote (default: Lidl)")
    args = ap.parse_args()
    main(args.apply, args.remote, args.folder)
