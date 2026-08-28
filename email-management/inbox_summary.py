#!/usr/bin/env python3
"""
inbox_summary.py -- Stage 2 of the inbox audit pipeline.

Reads the JSON Lines file produced by eml_extract.py and derives a *generic*
summary of the mailbox that answers two questions without any hand-written
knowledge of which services happen to be in this particular inbox:

  (1) Which services does the mailbox owner appear to be REGISTERED with?
      -> inferred from account-lifecycle evidence (signup / welcome / verify /
         password / security / order / billing mail), not from marketing volume.

  (2) If they want to clean the mailbox, what is the plan and how do they
      unsubscribe?
      -> inferred from RFC 2369 List-Unsubscribe / RFC 8058 one-click headers,
         mailto opt-outs and in-body opt-out links, plus per-sender volume and
         recency, which together give a delete-vs-keep rule and an ordered
         work list.

Outputs (all machine-readable or paste-ready):
    summary.json        full structured result
    summary.md          human-readable report
    senders.csv         one row per sending identity
    unsubscribe.csv     concrete opt-out target per sender group

Usage:
    python3 inbox_summary.py messages.jsonl --outdir report
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Classification vocabulary
#
# Each bucket is a list of (label, regex). Regexes run against the subject line
# (and, for a few buckets, the sender local-part), so adding a new signal is a
# one-line change rather than a code change.
# ---------------------------------------------------------------------------

ACCOUNT_EVIDENCE = [
    ("signup",       r"\bthank you for (signing up|registering|joining)\b|\bwelcome to\b|\bwelcome,|\byour new .* account\b|\bgetting started\b"),
    ("verification", r"\bverif(y|ication)\b|\bconfirm your\b|\bactivation\b|\bactivate your\b|\bis your .*code\b|\bone[- ]time (code|passcode)\b|\bOTP\b"),
    ("approval",     r"\bapplication (approved|received|submitted)\b|\baccount (approved|created|application)\b|\bcase#\b"),
    ("security",     r"\bpassword\b|\bsecurity info\b|\bsign-?in\b|\bnew device\b|\bsuspicious\b|\btwo[- ]factor\b|\b2fa\b|\brecovery\b"),
    ("credentials",  r"\bapi (key|token)\b|\bapp keys\b|\baccess token\b|\bclient secret\b"),
    ("billing",      r"\border\b|\breceipt\b|\binvoice\b|\bpayment\b|\bsubscription (renew|expir|cancel)|\btrial (ends|expires|is over)\b|\brefund\b|\bcashback\b"),
    ("service_ops",  r"\bcluster\b|\bhas been paused\b|\bwill be (deleted|paused)\b|\bstorage (is )?full\b|\bquota\b|\bservice (notice|update)\b|\bsecurity notice\b"),
    ("terms",        r"\bterms of (use|service)\b|\bprivacy (policy|statement)\b|\bterms and conditions\b"),
]

BULK_HINT = re.compile(
    r"\bsale\b|\bdeals?\b|\bsave\b|% off|\boff\b|\bshop\b|\bblack friday\b|\bcyber\b|"
    r"\bwebinar\b|\bnewsletter\b|\bregister now\b|\bdon'?t miss\b|\blast chance\b|"
    r"\bnew(est)? (features|games|arrivals)\b|\bgift\b|\bpre-?order\b|\bdiscount\b|"
    r"\bwe miss you\b|\bpenny for your thoughts\b|\bhappy (holidays|new year|thanksgiving)\b",
    re.I,
)

# Buckets that constitute real proof of an account, as opposed to a mailing list
# a brand may have added the address to without any registration.
STRONG_ACCOUNT = {"signup", "verification", "approval", "security", "credentials", "billing", "service_ops"}


def classify(rec) -> tuple[list[str], str]:
    """Return (evidence_labels, message_kind)."""
    subject = rec.get("subject", "") or ""
    labels = [name for name, pat in ACCOUNT_EVIDENCE if re.search(pat, subject, re.I)]

    has_list_headers = bool(
        rec.get("list_unsubscribe_raw") or rec.get("list_id") or rec.get("body_unsub_links")
    )
    strong = [l for l in labels if l in STRONG_ACCOUNT]

    if strong and not has_list_headers:
        kind = "transactional"
    elif strong and has_list_headers:
        # e.g. an order confirmation sent through the marketing platform
        kind = "transactional_bulk"
    elif has_list_headers or BULK_HINT.search(subject):
        kind = "bulk"
    else:
        kind = "other"
    return labels, kind


# ---------------------------------------------------------------------------
# Unsubscribe capability
# ---------------------------------------------------------------------------

def unsub_capability(records) -> dict:
    """Best available opt-out route across all messages from one sender group."""
    one_click = [r for r in records if r.get("list_unsubscribe_post")]
    http = [u for r in records for u in r.get("list_unsubscribe_http", [])]
    mailto = [u for r in records for u in r.get("list_unsubscribe_mailto", [])]
    body = [u for r in records for u in r.get("body_unsub_links", [])]

    if one_click:
        # A One-Click sender should publish an https target; if the header only
        # carried a mailto, fall back rather than reporting an empty target.
        oc_http = [u for r in one_click for u in r.get("list_unsubscribe_http", [])]
        method = "one_click_header"
        target = (oc_http or http or body or mailto or [""])[0]
    elif http:
        method, target = "http_header", http[0]
    elif body:
        method, target = "body_link", body[0]
    elif mailto:
        method, target = "mailto_header", mailto[0]
    else:
        method, target = "none_found", ""

    return {
        "method": method,
        "target": target,
        "counts": {
            "messages": len(records),
            "with_list_unsubscribe": sum(1 for r in records if r.get("list_unsubscribe_raw")),
            "one_click": len(one_click),
            "http_targets": len(set(http)),
            "mailto_targets": len(set(mailto)),
            "body_links": len(set(body)),
        },
        "all_http": sorted(set(http))[:3],
        "all_mailto": sorted(set(mailto))[:3],
        "all_body": sorted(set(body))[:3],
    }


UNSUB_ADVICE = {
    "one_click_header": "One-click opt-out (RFC 8058): the mail client's built-in "
                        "Unsubscribe button works and needs no login.",
    "http_header":      "Opt-out URL published in the List-Unsubscribe header: open it "
                        "in a browser; it usually lands on a preference page.",
    "body_link":        "No usable header target; use the unsubscribe link in the "
                        "message footer.",
    "mailto_header":    "Opt-out is by email: send a blank message to the mailto: "
                        "address (keep the subject line intact -- it carries the list ID).",
    "none_found":       "No opt-out mechanism in the mail. Turn the messages off in the "
                        "service's own account/notification settings, or block the sender.",
}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def build(records, stale_days=365, aliases=None):
    """
    aliases: optional {registrable_domain: canonical_brand} mapping. Big vendors
    send from throwaway ESP domains (foo-email.com, e.foo.com) that the naive
    registrable-domain rule cannot tie back to the parent brand; supplying a
    mapping merges them so the account evidence lands on one row instead of
    being split into a real account plus a phantom "list-only" sender.
    """
    now = datetime.now(timezone.utc)
    aliases = aliases or {}

    by_sender = collections.defaultdict(list)   # from_addr -> records
    by_brand = collections.defaultdict(list)    # brand -> records

    for rec in records:
        rec["_labels"], rec["_kind"] = classify(rec)
        rd = rec.get("from_registrable") or "(unknown)"
        rec["_brand"] = aliases.get(rd, rd)
        by_sender[rec.get("from_addr") or "(unknown)"].append(rec)
        by_brand[rec["_brand"]].append(rec)

    def date_span(recs):
        dates = sorted(r["date"][:10] for r in recs if r.get("date"))
        return (dates[0], dates[-1]) if dates else ("", "")

    def days_since(iso):
        if not iso:
            return None
        try:
            return (now - datetime.fromisoformat(iso + "T00:00:00+00:00")).days
        except Exception:
            return None

    def summarise(key, recs, level):
        first, last = date_span(recs)
        labels = collections.Counter(l for r in recs for l in r["_labels"])
        kinds = collections.Counter(r["_kind"] for r in recs)
        names = collections.Counter(r.get("from_name") for r in recs if r.get("from_name"))
        strong_hits = {l: n for l, n in labels.items() if l in STRONG_ACCOUNT}

        # Registration confidence: strong evidence in >=2 distinct categories is
        # near-certain; one category is probable; none means "mailing list only".
        if len(strong_hits) >= 2:
            confidence = "confirmed"
        elif len(strong_hits) == 1:
            confidence = "probable"
        else:
            confidence = "list_only"

        idle = days_since(last)
        return {
            "key": key,
            "level": level,
            "display_name": names.most_common(1)[0][0] if names else key,
            "programs": [n for n, _ in names.most_common(6)],
            "sending_addresses": sorted({r.get("from_addr", "") for r in recs}),
            "sending_domains": sorted({r.get("from_domain", "") for r in recs}),
            "message_count": len(recs),
            "first_seen": first,
            "last_seen": last,
            "days_since_last": idle,
            "stale": (idle is not None and idle > stale_days),
            "kinds": dict(kinds),
            "bulk_share": round(
                (kinds.get("bulk", 0) + kinds.get("transactional_bulk", 0)) / len(recs), 3
            ),
            "account_evidence": dict(labels),
            "registration_confidence": confidence,
            "example_evidence_subjects": [
                r["subject"] for r in sorted(recs, key=lambda x: x.get("date", ""))
                if any(l in STRONG_ACCOUNT for l in r["_labels"])
            ][:4],
            "unsubscribe": unsub_capability(recs),
        }

    brands = [summarise(k, v, "brand") for k, v in by_brand.items()]
    senders = [summarise(k, v, "sender") for k, v in by_sender.items()]
    brands.sort(key=lambda d: -d["message_count"])
    senders.sort(key=lambda d: -d["message_count"])

    # ---- cleanup plan -----------------------------------------------------
    # Each sender group is routed to exactly one action, cheapest wins first.
    plan = {"unsubscribe_then_bulk_delete": [], "unsubscribe_keep_account": [],
            "settings_or_block": [], "keep_archive": []}

    for s in senders:
        u = s["unsubscribe"]["method"]
        if s["registration_confidence"] == "list_only" and s["bulk_share"] >= 0.5:
            bucket = "unsubscribe_then_bulk_delete"
        elif s["bulk_share"] >= 0.5:
            bucket = "unsubscribe_keep_account"
        elif u == "none_found" and s["bulk_share"] > 0:
            bucket = "settings_or_block"
        else:
            bucket = "keep_archive"
        if u == "none_found" and bucket.startswith("unsubscribe"):
            bucket = "settings_or_block"
        plan[bucket].append(s["key"])

    registered = [b for b in brands if b["registration_confidence"] in ("confirmed", "probable")]
    list_only = [b for b in brands if b["registration_confidence"] == "list_only"]

    totals = collections.Counter(r["_kind"] for r in records)
    all_dates = sorted(r["date"][:10] for r in records if r.get("date"))

    return {
        "generated_at": now.isoformat(),
        "totals": {
            "messages": len(records),
            "distinct_sending_addresses": len(by_sender),
            "distinct_brands": len(by_brand),
            "date_range": [all_dates[0], all_dates[-1]] if all_dates else ["", ""],
            "kinds": dict(totals),
            "with_list_unsubscribe": sum(1 for r in records if r.get("list_unsubscribe_raw")),
            "one_click_capable": sum(1 for r in records if r.get("list_unsubscribe_post")),
        },
        "registered_services": registered,
        "list_only_senders": list_only,
        "brands": brands,
        "senders": senders,
        "cleanup_plan": plan,
        "unsubscribe_advice": UNSUB_ADVICE,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(s) -> str:
    t = s["totals"]
    out = []
    w = out.append
    w("# Mailbox audit\n")
    w(f"- Messages analysed: **{t['messages']}** "
      f"({t['date_range'][0]} to {t['date_range'][1]})")
    w(f"- Distinct sending identities: **{t['distinct_sending_addresses']}** "
      f"across **{t['distinct_brands']}** brands")
    w(f"- Carry a List-Unsubscribe header: **{t['with_list_unsubscribe']}** "
      f"({t['one_click_capable']} of them one-click)")
    w(f"- Message mix: {', '.join(f'{k}={v}' for k, v in sorted(t['kinds'].items()))}\n")

    w("## 1. Services this mailbox is registered with\n")
    w("Ranked by strength of account evidence. *Confirmed* = account-lifecycle mail in "
      "two or more independent categories (signup, verification, security, billing, ...); "
      "*probable* = one category.\n")
    w("| Service | Confidence | Evidence | Messages | Active | Programs seen |")
    w("|---|---|---|---|---|---|")
    for b in s["registered_services"]:
        ev = ", ".join(f"{k}×{v}" for k, v in sorted(b["account_evidence"].items())
                       if k in STRONG_ACCOUNT)
        w(f"| {b['display_name']} (`{b['key']}`) | {b['registration_confidence']} | {ev} | "
          f"{b['message_count']} | {b['first_seen']} → {b['last_seen']} | "
          f"{', '.join(b['programs'][:5])} |")

    if s["list_only_senders"]:
        w("\n**Marketing-list-only senders** (no account evidence found — probably reached "
          "the address through another account or a list purchase):\n")
        for b in s["list_only_senders"]:
            w(f"- {b['display_name']} (`{b['key']}`) — {b['message_count']} messages, "
              f"last {b['last_seen'] or 'unknown'}")

    w("\n## 2. Cleanup plan\n")
    plan = s["cleanup_plan"]
    order = [
        ("unsubscribe_then_bulk_delete",
         "Unsubscribe, then delete everything from the sender — no account to protect."),
        ("unsubscribe_keep_account",
         "Unsubscribe from marketing but keep the account and its transactional mail."),
        ("settings_or_block",
         "No opt-out header — change the setting inside the service, or block the sender."),
        ("keep_archive",
         "Keep / archive: mostly transactional or security mail worth retaining."),
    ]
    for key, desc in order:
        items = plan.get(key, [])
        if not items:
            continue
        w(f"\n### {desc}\n")
        for addr in items:
            snd = next(x for x in s["senders"] if x["key"] == addr)
            u = snd["unsubscribe"]
            w(f"- `{addr}` — {snd['message_count']} msgs, last {snd['last_seen'] or '?'} — "
              f"**{u['method']}**"
              + (f"\n  - {u['target'][:160]}" if u["target"] else ""))

    w("\n### How each opt-out method works\n")
    for k, v in s["unsubscribe_advice"].items():
        w(f"- **{k}** — {v}")
    return "\n".join(out) + "\n"


def write_csvs(s, outdir):
    with open(os.path.join(outdir, "senders.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["sender", "display_name", "brand_guess", "messages", "first_seen",
                     "last_seen", "days_idle", "bulk_share", "registration_confidence",
                     "unsub_method"])
        for x in s["senders"]:
            wr.writerow([x["key"], x["display_name"],
                         (x["sending_domains"] or [""])[0], x["message_count"],
                         x["first_seen"], x["last_seen"], x["days_since_last"],
                         x["bulk_share"], x["registration_confidence"],
                         x["unsubscribe"]["method"]])

    with open(os.path.join(outdir, "unsubscribe.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["sender", "messages", "method", "target", "mailto_fallback"])
        for x in s["senders"]:
            u = x["unsubscribe"]
            if u["method"] == "none_found" and not u["all_mailto"]:
                continue
            wr.writerow([x["key"], x["message_count"], u["method"], u["target"],
                         (u["all_mailto"] or [""])[0]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Summarise an extracted mailbox.")
    ap.add_argument("jsonl", help="messages.jsonl from eml_extract.py")
    ap.add_argument("--outdir", default="report")
    ap.add_argument("--stale-days", type=int, default=365,
                    help="A sender with nothing newer than this is flagged stale.")
    ap.add_argument("--aliases", default=None,
                    help='JSON file mapping ESP domains to a parent brand, e.g. '
                         '{"microsoftstoreemail.com": "microsoft.com"}')
    args = ap.parse_args(argv)

    aliases = {}
    if args.aliases:
        with open(args.aliases, encoding="utf-8") as fh:
            aliases = json.load(fh)

    os.makedirs(args.outdir, exist_ok=True)
    records = [json.loads(line) for line in open(args.jsonl, encoding="utf-8")]
    summary = build(records, stale_days=args.stale_days, aliases=aliases)

    with open(os.path.join(args.outdir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(args.outdir, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(render_markdown(summary))
    write_csvs(summary, args.outdir)

    t = summary["totals"]
    print(f"{t['messages']} messages | {t['distinct_brands']} brands | "
          f"{len(summary['registered_services'])} look registered | "
          f"wrote {args.outdir}/summary.{{json,md}}, senders.csv, unsubscribe.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
