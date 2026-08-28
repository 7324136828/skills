#!/usr/bin/env python3
"""
sender_groups.py -- Stage 1.5 of the inbox audit pipeline.

inbox_summary.py groups senders by registrable domain and accepts an aliases
file to merge ESP domains onto a parent brand. That single mechanism breaks in
both directions on a real mailbox:

  OVER-merging. Shared platforms -- Constant Contact (ccsend.com), Wix
  (wixemails.com), free webmail (gmail.com) -- put many unrelated senders behind
  one registrable domain. Left alone, an optician and a gym merge into a single
  "ccsend.com brand", and six unrelated people merge into one "gmail.com brand"
  that then appears to hold a billing relationship.

  UNDER-merging that a domain map cannot express: one sender address on a shared
  platform that belongs to a brand which also mails from its own domain.

So this stage rewrites `from_registrable` before scoring: shared platforms are
split per sending address, then per-address overrides pull the known ones back
onto their real brand. Domain-level merges stay in the aliases file and are
passed through to stage 2 unchanged.

Usage:
    python sender_groups.py messages.jsonl -o messages_grouped.jsonl \
        --config config/aliases.json --emit-domain-aliases _domain_aliases.json
"""

from __future__ import annotations

import argparse
import json
import sys


def load_config(path):
    """
    Accepts either the structured form:

        {"domain_aliases": {...}, "split_per_address": [...], "address_brand": {...}}

    or a flat {domain: brand} map, which is treated as domain_aliases only.
    """
    if not path:
        return {}, set(), {}
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if any(k in cfg for k in ("domain_aliases", "split_per_address", "address_brand")):
        return (cfg.get("domain_aliases", {}),
                set(cfg.get("split_per_address", [])),
                cfg.get("address_brand", {}))
    return ({k: v for k, v in cfg.items() if not k.startswith("_")}, set(), {})


def main(argv=None):
    ap = argparse.ArgumentParser(description="Regroup sending identities before scoring.")
    ap.add_argument("src", help="messages.jsonl from stage 1")
    ap.add_argument("-o", "--out", default="messages_grouped.jsonl")
    ap.add_argument("--config", default=None, help="aliases.json")
    ap.add_argument("--emit-domain-aliases", default=None,
                    help="write the flat {domain: brand} map stage 2 expects")
    args = ap.parse_args(argv)

    domain_aliases, split_per_address, address_brand = load_config(args.config)

    n = split = pinned = 0
    with open(args.src, encoding="utf-8") as fh, open(args.out, "w", encoding="utf-8") as out:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            addr = r.get("from_addr") or ""
            rd = r.get("from_registrable") or ""
            if addr in address_brand:
                r["from_registrable"] = address_brand[addr]
                pinned += 1
            elif rd in split_per_address:
                r["from_registrable"] = addr or rd
                split += 1
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1

    if args.emit_domain_aliases:
        with open(args.emit_domain_aliases, "w", encoding="utf-8") as fh:
            json.dump(domain_aliases, fh, indent=1)

    print(f"stage 1.5: regrouped {n} records "
          f"({split} split off a shared platform, {pinned} pinned to a brand) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
