#!/usr/bin/env python3
"""
imap_download.py -- Download recent messages from one or more IMAP mailboxes.

Reads account definitions from a credentials JSON file and saves every message
newer than --days from each account's mailbox as
    <output>/<email_address>/<uid>.eml

The .eml tree it produces is the input for eml_extract.py (inbox audit) and
summarize_emails.py (spoken digest).

Passwords are NEVER stored in the credentials file: each account names an
environment variable via "password_env", and the value is read from the
environment at run time. See config/credentials.example.json.

Usage:
    python imap_download.py --credentials config/credentials.json --output output
    python imap_download.py --days 30 --folder "[Gmail]/All Mail"

The run is resumable: a .checkpoint.json per account records what has already
been fetched, and messages already on disk are skipped.
"""

from __future__ import annotations

import argparse
import imaplib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = Path("config/credentials.json")
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_DAYS_BACK = 7
DEFAULT_FOLDER = "INBOX"
DEFAULT_FETCH_DELAY_SEC = 0.05      # polite pause between message fetches
CHECKPOINT_FILENAME = ".checkpoint.json"

# Public IMAP endpoints, keyed by the address domain. Anything not listed falls
# back to imap.<domain>:993, and any account may override the guess with
# "imap_server" / "imap_port" in the credentials file.
IMAP_SERVERS: dict[str, tuple[str, int]] = {
    "gmail.com":      ("imap.gmail.com",        993),
    "googlemail.com": ("imap.gmail.com",        993),
    "aol.com":        ("imap.aol.com",          993),
    "yahoo.com":      ("imap.mail.yahoo.com",   993),
    "outlook.com":    ("outlook.office365.com", 993),
    "hotmail.com":    ("outlook.office365.com", 993),
    "live.com":       ("outlook.office365.com", 993),
    "msn.com":        ("outlook.office365.com", 993),
    "icloud.com":     ("imap.mail.me.com",      993),
    "me.com":         ("imap.mail.me.com",      993),
    "fastmail.com":   ("imap.fastmail.com",     993),
    "zoho.com":       ("imap.zoho.com",         993),
    "gmx.com":        ("imap.gmx.com",          993),
    "qq.com":         ("imap.qq.com",           993),
    "foxmail.com":    ("imap.qq.com",           993),
    # Proton requires the locally running Proton Mail Bridge.
    "protonmail.com": ("127.0.0.1",            1143),
    "proton.me":      ("127.0.0.1",            1143),
    "pm.me":          ("127.0.0.1",            1143),
}

# Domains hosted by a provider under a different name (universities and
# companies on Google Workspace or Microsoft 365) are common; add them to your
# own credentials file with an explicit "imap_server" rather than here.

log = logging.getLogger("imap_download")


def setup_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_credentials(path: Path) -> list[dict]:
    if not path.exists():
        log.error(
            "Credentials file not found: %s. Copy config/credentials.example.json "
            "to %s and fill it in.", path, path,
        )
        sys.exit(1)
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    accounts = data.get("accounts", [])
    if not accounts:
        log.error("No accounts defined in %s.", path)
        sys.exit(1)
    for account in accounts:
        env_var = account.get("password_env")
        if env_var:
            account["password"] = os.environ.get(env_var, "")
    return accounts


def resolve_imap(email_address: str) -> tuple[str, int]:
    domain = email_address.split("@")[-1].lower()
    return IMAP_SERVERS.get(domain, (f"imap.{domain}", 993))


def safe_name(text: str) -> str:
    """Strip characters that are illegal in Windows/macOS/Linux file names."""
    return re.sub(r'[\\/:*?"<>|]', "_", text)


def decode_subject(raw: str | None) -> str:
    if not raw:
        return "no_subject"
    parts = []
    for part, charset in decode_header(raw):
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return "".join(parts)


def parse_uid(fetch_response: bytes | None) -> str | None:
    """Extract the UID integer from an IMAP FETCH (UID) response."""
    if not fetch_response:
        return None
    match = re.search(rb"UID (\d+)", fetch_response)
    return match.group(1).decode() if match else None


def since_date_str(days_back: int) -> str:
    """Format the IMAP SEARCH SINCE date, e.g. '18-Aug-2026'."""
    return (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def load_checkpoint(folder_dir: Path) -> dict:
    cp_path = folder_dir / CHECKPOINT_FILENAME
    if cp_path.exists():
        try:
            with cp_path.open(encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return {"downloaded": [], "failed": []}


def save_checkpoint(folder_dir: Path, data: dict) -> None:
    data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with (folder_dir / CHECKPOINT_FILENAME).open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ---------------------------------------------------------------------------
# Core download logic
# ---------------------------------------------------------------------------


def download_account(
    account: dict,
    output_dir: Path,
    days_back: int,
    mail_folder: str,
    delay: float,
) -> None:
    addr: str = account["email"].strip()
    password: str = account["password"]

    default_server, default_port = resolve_imap(addr)
    server: str = account.get("imap_server") or default_server
    port: int = int(account.get("imap_port") or default_port)

    log.info("=== %s  ->  %s:%d ===", addr, server, port)

    try:
        conn = imaplib.IMAP4_SSL(server, port)
        conn.login(addr, password)
    except imaplib.IMAP4.error as exc:
        log.error("Login failed for %s: %s", addr, exc)
        return
    except OSError as exc:
        log.error("Connection error for %s (%s:%d): %s", addr, server, port, exc)
        return

    folder_dir = output_dir / safe_name(addr)
    folder_dir.mkdir(parents=True, exist_ok=True)

    try:
        status, _ = conn.select(mail_folder, readonly=True)
    except imaplib.IMAP4.error as exc:
        log.warning("Could not select '%s' for %s: %s", mail_folder, addr, exc)
        conn.logout()
        return

    if status != "OK":
        log.warning("Skipping %s (SELECT %s failed)", addr, mail_folder)
        conn.logout()
        return

    since = since_date_str(days_back)
    status, search_data = conn.search(None, "SINCE", since)
    if status != "OK" or not search_data or not search_data[0]:
        log.info("  %-40s  0 messages since %s", mail_folder, since)
        conn.logout()
        return

    seq_ids = search_data[0].split()
    total = len(seq_ids)
    log.info("  %-40s  %d messages since %s", mail_folder, total, since)

    checkpoint = load_checkpoint(folder_dir)
    downloaded_set: set[str] = set(checkpoint.get("downloaded", []))
    failed_set: set[str] = set(checkpoint.get("failed", []))

    downloaded = skipped = failed = 0

    for idx, seq_id in enumerate(seq_ids, 1):
        # Resolve the stable UID so the filename survives re-runs.
        uid = None
        uid_status, uid_data = conn.fetch(seq_id, "(UID)")
        if uid_status == "OK" and uid_data and uid_data[0]:
            uid = parse_uid(uid_data[0] if isinstance(uid_data[0], bytes) else uid_data[0][0])
        uid_str = uid or seq_id.decode()
        out_path = folder_dir / f"{uid_str}.eml"

        if out_path.exists():
            skipped += 1
            downloaded_set.add(uid_str)
            failed_set.discard(uid_str)
            log.debug("  [%d/%d] UID %s already on disk", idx, total, uid_str)
            continue

        log.info("  [%d/%d] Fetching UID %s", idx, total, uid_str)
        try:
            msg_status, msg_data = conn.fetch(seq_id, "(RFC822)")
            if msg_status != "OK" or not msg_data or msg_data[0] is None:
                failed += 1
                failed_set.add(uid_str)
                downloaded_set.discard(uid_str)
                log.warning("  [%d/%d] UID %s -- server returned no data", idx, total, uid_str)
                save_checkpoint(folder_dir, {"total": total,
                                             "downloaded": sorted(downloaded_set),
                                             "failed": sorted(failed_set)})
                continue
            raw_bytes: bytes = msg_data[0][1]  # type: ignore[index]
            out_path.write_bytes(raw_bytes)
            downloaded += 1
            downloaded_set.add(uid_str)
            failed_set.discard(uid_str)
            log.info("  [%d/%d] Saved  UID %s (%d bytes)", idx, total, uid_str, len(raw_bytes))
        except Exception as exc:
            log.warning("  [%d/%d] Failed to fetch seq %s: %s", idx, total, seq_id.decode(), exc)
            failed += 1
            failed_set.add(uid_str)
            downloaded_set.discard(uid_str)

        save_checkpoint(folder_dir, {"total": total,
                                     "downloaded": sorted(downloaded_set),
                                     "failed": sorted(failed_set)})
        time.sleep(delay)

    log.info("    downloaded=%d  skipped=%d  failed=%d  total=%d",
             downloaded, skipped, failed, total)
    if failed_set:
        log.warning("    Failed UIDs: %s", ", ".join(sorted(failed_set)))

    conn.logout()
    log.info("Done with %s", addr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS,
                    help="JSON file describing the accounts (default: %(default)s).")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                    help="Directory that receives <address>/<uid>.eml (default: %(default)s).")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK,
                    help="Only download messages newer than this many days (default: %(default)s).")
    ap.add_argument("--folder", default=DEFAULT_FOLDER,
                    help="IMAP mailbox to read (default: %(default)s).")
    ap.add_argument("--delay", type=float, default=DEFAULT_FETCH_DELAY_SEC,
                    help="Seconds to pause between fetches (default: %(default)s).")
    ap.add_argument("--log-file", type=Path, default=None,
                    help="Also append the run log to this file.")
    args = ap.parse_args(argv)

    setup_logging(args.log_file)

    if args.days < 1:
        ap.error("--days must be at least 1")

    accounts = load_credentials(args.credentials)
    args.output.mkdir(parents=True, exist_ok=True)

    for account in accounts:
        email_addr = (account.get("email") or "").strip()
        password = account.get("password") or ""

        if not email_addr:
            log.warning("Skipping account entry with no email address.")
            continue
        if not password:
            log.warning("Skipping %s -- environment variable %s is not set.",
                        email_addr, account.get("password_env", "password_env"))
            continue

        download_account(account, args.output, args.days, args.folder, args.delay)

    log.info("All accounts processed. Messages saved under: %s/", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
