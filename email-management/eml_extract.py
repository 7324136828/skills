#!/usr/bin/env python3
"""
eml_extract.py -- Stage 1 of the inbox audit pipeline.

Walks a folder of .eml files (as produced by an IMAP/Graph export), parses each
message with the stdlib `email` package, and writes ONE normalised JSON record
per message to a JSON Lines file.

Everything downstream (service inventory, unsubscribe plan) reads that .jsonl,
so this script is the only place that has to understand MIME.

Usage:
    python eml_extract.py <eml_root_dir> -o messages.jsonl

Design notes
------------
* Nothing is inferred here beyond what the headers/body literally say. Judgement
  calls (is this a "service"? is it bulk mail?) happen in stage 2, so that this
  extraction stays reusable for any other question you want to ask the mailbox.
* Header decoding is defensive: real-world exports contain RFC 2047 encoded
  words, broken charsets and mixed encodings. Failures degrade to raw text
  rather than crashing the run.

Two fixes over the original version, both found by reading raw messages that the
first run had mis-reported:

* `List-Unsubscribe` is RFC 2047-decoded BEFORE being split on <...>. Some
  senders ship the header as encoded words, which hides the angle brackets and
  makes the header parse to nothing -- the sender then shows as "one-click
  capable" with no target to click.
* Opt-out links are also detected by ANCHOR TEXT, not only by keywords in the
  URL. Senders that route every link through a click-tracker
  (`links.example.com/u/click?...`) have no opt-out word anywhere in the URL, so
  a URL-only scan reports "no opt-out" for mail that plainly has an unsubscribe
  link in its footer.
"""

from __future__ import annotations

import argparse
import email
import email.policy
import hashlib
import json
import os
import re
import sys
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime

# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

def decode_hdr(raw) -> str:
    """RFC 2047-decode a header value, tolerating malformed input."""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def addr_parts(raw: str):
    """Return (display_name, email_address, domain) for the first address."""
    if not raw:
        return "", "", ""
    try:
        pairs = getaddresses([raw])
    except Exception:
        pairs = []
    if not pairs:
        return "", "", ""
    name, addr = pairs[0]
    name = decode_hdr(name)
    addr = (addr or "").strip().lower()
    domain = addr.rsplit("@", 1)[-1] if "@" in addr else ""
    return name, addr, domain


def registrable_domain(domain: str) -> str:
    """
    Collapse a hostname to something close to its registrable domain.

    Not a full Public Suffix List implementation -- it just keeps the last two
    labels, or three when the second-to-last is a well-known second-level
    suffix (co.uk, com.au, ...). Good enough to group bulk senders; sender_groups.py
    handles the cases where that rule over- or under-merges.
    """
    if not domain:
        return ""
    parts = domain.lower().strip(".").split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    two_level = {"co", "com", "org", "net", "gov", "edu", "ac"}
    if len(parts) >= 3 and parts[-2] in two_level and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ---------------------------------------------------------------------------
# Body helpers
# ---------------------------------------------------------------------------

def get_bodies(msg):
    """Return (text_body, html_body) as decoded strings (may be empty)."""
    text, html = [], []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        if "attachment" in disp:
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            continue
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            body = payload.decode(charset, errors="replace")
        except (LookupError, TypeError):
            body = payload.decode("utf-8", errors="replace")
        (text if ctype == "text/plain" else html).append(body)
    return "\n".join(text), "\n".join(html)


URL_RE = re.compile(r'https?://[^\s"\'<>()\[\]]+', re.I)

# Words that mark a link as an opt-out control rather than content.
UNSUB_HINT = re.compile(
    r"unsubscrib|optout|opt-out|opt_out|email[-_]?preferen|manage[-_]?preferen|"
    r"subscription[-_]?(centre|center|preferences)|notification[-_]?settings|"
    r"notification[-_]?preferences|communication[-_]?preferen|remove[-_]?me|"
    r"stop[-_]?email|revoke-consent|manage-consent",
    re.I,
)

# The same idea applied to the VISIBLE TEXT of a link, which survives click
# trackers. Kept multilingual because export mailboxes rarely are not.
UNSUB_TEXT = re.compile(
    r"unsubscrib|opt[\s-]?out|email preferences|manage preferences|"
    r"notification settings|subscription preferences|manage subscriptions|"
    r"stop (receiving|these) emails|"
    r"退订|取消订阅|邮件设置|退訂|"
    r"d[ée]sabonn|abbestellen|abmelden|cancelar suscripci|darse de baja|"
    r"annulla iscrizione|afmelden",
    re.I,
)

ANCHOR_RE = re.compile(r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.{0,300}?)</a>',
                       re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _clean(url: str) -> str:
    return url.rstrip('.,;)"\'&').replace("&amp;", "&")


def find_unsub_links(text: str, html: str, limit: int = 8):
    """
    URLs in the body that look like opt-out controls.

    Two passes, cheapest signal first:
      1. the URL itself contains an opt-out word;
      2. the link's visible text says "Unsubscribe" (or its equivalent in one of
         a few other languages) even though the URL is a tracker redirect.
    Pass 1 results come first, so a direct preference-centre URL outranks a
    one-shot tracker link when stage 2 picks a single target.
    """
    found, seen = [], set()

    def add(url):
        url = _clean(url)
        if url.lower().startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            found.append(url)

    for blob in (text, html):
        if not blob:
            continue
        for url in URL_RE.findall(blob):
            if UNSUB_HINT.search(url):
                add(url)
                if len(found) >= limit:
                    return found

    if html:
        for href, label in ANCHOR_RE.findall(html):
            label = TAG_RE.sub(" ", label)
            if UNSUB_TEXT.search(label):
                add(href)
                if len(found) >= limit:
                    return found
    return found


def parse_list_unsubscribe(raw: str):
    """Split a List-Unsubscribe header into http(s) and mailto targets."""
    http, mailto = [], []
    if not raw:
        return http, mailto
    # Decode first: some senders emit the whole header as RFC 2047 encoded
    # words, which hides the <> delimiters from the split below.
    if "=?" in raw:
        raw = decode_hdr(raw.replace("\r", "").replace("\n", ""))
    for token in re.findall(r"<([^>]+)>", raw) or [raw]:
        token = token.strip()
        if token.lower().startswith("mailto:"):
            mailto.append(token)
        elif token.lower().startswith(("http://", "https://")):
            http.append(token)
    return http, mailto


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_one(path: str, root: str) -> dict:
    with open(path, "rb") as fh:
        raw = fh.read()
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)

    frm_name, frm_addr, frm_domain = addr_parts(msg.get("From", ""))
    rp_name, rp_addr, rp_domain = addr_parts(msg.get("Return-Path", ""))
    rt_name, rt_addr, rt_domain = addr_parts(msg.get("Reply-To", ""))

    text, html = get_bodies(msg)

    lu_raw = (msg.get("List-Unsubscribe") or "").strip()
    lu_http, lu_mailto = parse_list_unsubscribe(lu_raw)

    date_raw = msg.get("Date", "")
    date_iso = ""
    try:
        dt = parsedate_to_datetime(date_raw)
        if dt is not None:
            date_iso = dt.isoformat()
    except Exception:
        pass

    to_addrs = [a.lower() for _, a in getaddresses([msg.get("To", "") or ""]) if a]

    return {
        "file": os.path.relpath(path, root),
        "folder": os.path.basename(os.path.dirname(path)),
        "message_id": (msg.get("Message-ID") or "").strip(),
        "digest": hashlib.sha1(raw).hexdigest()[:12],
        "date_raw": date_raw,
        "date": date_iso,
        "subject": decode_hdr(msg.get("Subject", "")),
        "from_name": frm_name,
        "from_addr": frm_addr,
        "from_domain": frm_domain,
        "from_registrable": registrable_domain(frm_domain),
        "return_path_domain": rp_domain,
        "reply_to_addr": rt_addr,
        "to": to_addrs,
        "list_id": decode_hdr(msg.get("List-ID", "")),
        "list_unsubscribe_raw": lu_raw,
        "list_unsubscribe_http": lu_http,
        "list_unsubscribe_mailto": lu_mailto,
        "list_unsubscribe_post": (msg.get("List-Unsubscribe-Post") or "").strip(),
        "precedence": (msg.get("Precedence") or "").strip(),
        "auto_submitted": (msg.get("Auto-Submitted") or "").strip(),
        "campaign_headers": {
            k: decode_hdr(v)
            for k, v in msg.items()
            if k.lower().startswith(("x-campaign", "x-mailer", "x-sfmc", "x-mandrill",
                                     "x-ses", "x-sg", "feedback-id", "x-msft"))
        },
        "body_unsub_links": find_unsub_links(text, html),
        "text_excerpt": re.sub(r"\s+", " ", text)[:2000],
        "has_html": bool(html),
        "size_bytes": len(raw),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Extract .eml files to JSON Lines.")
    ap.add_argument("root", help="Directory to walk for .eml files")
    ap.add_argument("-o", "--out", default="messages.jsonl", help="Output .jsonl path")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"eml_extract: not a directory: {root}", file=sys.stderr)
        return 2

    paths = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.lower().endswith(".eml"):
                paths.append(os.path.join(dirpath, fn))
    paths.sort()

    if not paths:
        print(f"eml_extract: no .eml files under {root}", file=sys.stderr)
        return 2

    ok = failed = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for i, path in enumerate(paths, 1):
            try:
                rec = extract_one(path, root)
            except Exception as exc:  # keep going; one bad file shouldn't stop the run
                failed += 1
                print(f"  ! failed {path}: {exc}", file=sys.stderr)
                continue
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ok += 1
            if i % 1000 == 0:
                print(f"  ... {i}/{len(paths)}", flush=True)

    print(f"stage 1: parsed {ok} messages ({failed} failed) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
