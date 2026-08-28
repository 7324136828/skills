#!/usr/bin/env python3
"""
worklist.py -- Stage 3 of the inbox audit pipeline.

Flattens the cleanup plan in summary.json into one ordered list of things to do,
cheapest opt-out route first, and applies any hand-checked route overrides from
the annotations file.

Overrides exist because two failure modes survive the automated scan:

  * A sender ships NO List-Unsubscribe header and wraps its footer opt-out in a
    click tracker. Stage 2 then scores it bulk_share=0 and files it under
    "keep / archive" -- wrong for a pure alert feed.
  * The only usable opt-out is a settings page inside the account, which no
    header will ever advertise.

Both are corrections of fact, established by reading the raw message, so they
live in annotations.json next to the human-written service notes rather than
being hard-coded here.

Usage:
    python worklist.py report/summary.json -o worklist.csv --json worklist.json \
        --annotations config/annotations.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import json

# Cheapest opt-out route first. account_settings ranks last of the actionable
# routes because it is the only one that requires signing in.
EFFORT = {"one_click_header": 1, "http_header": 2, "body_link": 3,
          "mailto_header": 4, "account_settings": 5, "none_found": 6}

ACTION_RANK = {"unsubscribe_then_bulk_delete": 0, "unsubscribe_keep_account": 1,
               "settings_or_block": 2, "keep_archive": 3}

COLUMNS = ["step", "action", "method", "sender", "name", "messages", "last_seen",
           "days_idle", "target", "note"]


def build(summary, overrides):
    where = {s: a for a, senders in summary["cleanup_plan"].items() for s in senders}
    rows = []
    for s in summary["senders"]:
        key = s["key"]
        row = {
            "sender": key,
            "name": s["display_name"],
            "messages": s["message_count"],
            "last_seen": s["last_seen"],
            "days_idle": s["days_since_last"],
            "action": where.get(key, "keep_archive"),
            "method": s["unsubscribe"]["method"],
            "target": s["unsubscribe"].get("target") or "",
            "note": "",
        }
        row.update(overrides.get(key, {}))
        if row["action"] not in ACTION_RANK:
            raise SystemExit(f"annotations: unknown action {row['action']!r} for {key}")
        if row["method"] not in EFFORT:
            raise SystemExit(f"annotations: unknown method {row['method']!r} for {key}")
        rows.append(row)

    rows.sort(key=lambda r: (ACTION_RANK[r["action"]], EFFORT[r["method"]], -r["messages"]))
    for i, r in enumerate(rows, 1):
        r["step"] = i
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the ordered cleanup work list.")
    ap.add_argument("summary", help="report/summary.json from stage 2")
    ap.add_argument("-o", "--out", default="inbox_cleanup_worklist.csv")
    ap.add_argument("--json", dest="json_out", default="worklist.json")
    ap.add_argument("--annotations", default=None)
    args = ap.parse_args(argv)

    summary = json.load(open(args.summary, encoding="utf-8"))
    overrides = {}
    if args.annotations:
        with open(args.annotations, encoding="utf-8") as fh:
            overrides = json.load(fh).get("route_overrides", {})

    rows = build(summary, overrides)

    # utf-8-sig so Excel on Windows opens the file without mangling accents.
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})

    with open(args.json_out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)

    agg = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        agg[r["action"]][0] += 1
        agg[r["action"]][1] += r["messages"]
    print(f"stage 3: {len(rows)} senders -> {args.out}")
    for action in ACTION_RANK:
        senders, msgs = agg[action]
        print(f"           {action:30s} {senders:4d} senders {msgs:6d} messages")
    if overrides:
        print(f"           {len(overrides)} route override(s) applied from annotations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
