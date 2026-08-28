#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  run_audit.sh -- inbox audit, end to end.
#
#    ./run_audit.sh [MAIL_FOLDER] [OUTPUT_FOLDER]
#
#    MAIL_FOLDER    folder of .eml files (walked recursively). Default: ./output
#    OUTPUT_FOLDER  where everything lands.  Default: ./audit_out
#
#  config/aliases.json and config/annotations.json are used when present and
#  skipped when absent -- neither is required.
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAILDIR="${1:-$HERE/output}"
OUTDIR="${2:-$HERE/audit_out}"
PY="${PYTHON:-python3}"

command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: no Python 3 on PATH." >&2; exit 1; }

[ -d "$MAILDIR" ] || { echo "ERROR: mail folder not found: $MAILDIR" >&2; exit 1; }
mkdir -p "$OUTDIR"

ALIASES=(); [ -f "$HERE/config/aliases.json" ] && ALIASES=(--config "$HERE/config/aliases.json")
NOTES=();   [ -f "$HERE/config/annotations.json" ] && NOTES=(--annotations "$HERE/config/annotations.json")

echo
echo "  source : $MAILDIR"
echo "  output : $OUTDIR"
echo "  python : $PY"
echo

# stage 1: .eml -> messages.jsonl
"$PY" "$HERE/eml_extract.py" "$MAILDIR" -o "$OUTDIR/messages.jsonl"

# stage 1.5: regroup sending identities
"$PY" "$HERE/sender_groups.py" "$OUTDIR/messages.jsonl" \
    -o "$OUTDIR/messages_grouped.jsonl" \
    "${ALIASES[@]}" \
    --emit-domain-aliases "$OUTDIR/_domain_aliases.json"

# stage 2: score registration + build the cleanup plan
"$PY" "$HERE/inbox_summary.py" "$OUTDIR/messages_grouped.jsonl" \
    --outdir "$OUTDIR/report" \
    --aliases "$OUTDIR/_domain_aliases.json"

# stage 3: ordered work list
"$PY" "$HERE/worklist.py" "$OUTDIR/report/summary.json" \
    -o "$OUTDIR/inbox_cleanup_worklist.csv" \
    --json "$OUTDIR/worklist.json" \
    "${NOTES[@]}"

# stage 4: the report
"$PY" "$HERE/gen_report.py" "$OUTDIR/report/summary.json" "$OUTDIR/worklist.json" \
    -o "$OUTDIR/inbox_audit.html" \
    "${NOTES[@]}" \
    --source "$MAILDIR"

echo
echo "  DONE  $OUTDIR/inbox_audit.html"
echo "        $OUTDIR/inbox_cleanup_worklist.csv"
