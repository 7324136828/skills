#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  run_digest.sh -- download recent mail, summarize it, narrate it.
#
#    ./run_digest.sh [DAYS]        (DAYS defaults to 7)
#
#  Steps: imap_download.py -> summarize_emails.py -> tts_kokoro.py
#  PYTHON=... selects an interpreter (e.g. a virtualenv).
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

DAYS="${1:-7}"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

echo "=== Step 1/3: Downloading mail from the past $DAYS day(s) ==="
"$PY" imap_download.py --credentials config/credentials.json --output output --days "$DAYS"

echo
echo "=== Step 2/3: Summarizing with Ollama ==="
"$PY" summarize_emails.py --source output --days "$DAYS" --output summary.txt

echo
echo "=== Step 3/3: Generating speech audio ==="
"$PY" tts_kokoro.py --input summary.txt --output summary.mp3

echo
echo "All done. Text: summary.txt  Audio: summary.mp3"
