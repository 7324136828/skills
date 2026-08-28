#!/usr/bin/env python3
"""
Email Summarizer

Reads a tree of .eml files (as produced by imap_download.py or mbox_to_eml.py)
and uses a small language model served locally by Ollama to summarize each
message separately. The per-email summaries are written to the intermediate
file, then a larger Ollama model combines them into one briefing that
tts_kokoro.py / tts_sapi.py can narrate.

Usage:
    python summarize_emails.py --source output --output summary.txt
    python summarize_emails.py --days 30 --model llama3.2:1b --overall-model llama3.1:8b
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_SOURCE_DIR = Path("output")        # produced by imap_download.py
EMAIL_GLOB = "**/*.eml"

DAYS_BACK = 7                              # only summarize emails from the past week

DEFAULT_MODEL = "llama3.2:1b"
DEFAULT_OVERALL_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
MAX_SUMMARY_TOKENS = 120
MAX_OVERALL_SUMMARY_TOKENS = -1           # Ollama: -1 means unlimited generation

INTERMEDIATE_SUMMARY_TEXT_FILE = Path("_summary.txt")
SUMMARY_TEXT_FILE = Path("summary.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email loading
# ---------------------------------------------------------------------------


def html_to_text(html: str) -> str:
    """Very small HTML-to-text fallback for emails with no plain-text part."""
    import re
    from html import unescape

    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def extract_body(msg) -> str:
    body_part = msg.get_body(preferencelist=("plain", "html"))
    if body_part is None:
        return ""
    content = body_part.get_content()
    if body_part.get_content_type() == "text/html":
        content = html_to_text(content)
    return content.strip()


def load_recent_emails(root: Path, days_back: int) -> list[dict]:
    cutoff = datetime.now().astimezone() - timedelta(days=days_back)
    emails: list[dict] = []

    for eml_path in root.glob(EMAIL_GLOB):
        try:
            with eml_path.open("rb") as fh:
                msg = BytesParser(policy=policy.default).parse(fh)
        except Exception as exc:
            log.warning("Skipping unreadable file %s: %s", eml_path, exc)
            continue

        date_header = msg.get("Date")
        try:
            sent_at = parsedate_to_datetime(date_header) if date_header else None
        except (TypeError, ValueError):
            sent_at = None
        if sent_at is not None and sent_at.tzinfo is None:
            sent_at = sent_at.astimezone()
        if sent_at is not None and sent_at < cutoff:
            continue

        emails.append({
            "path": eml_path,
            "date": sent_at,
            "from": str(msg.get("From", "unknown sender")),
            "subject": str(msg.get("Subject", "(no subject)")),
            "body": extract_body(msg),
        })

    emails.sort(
        key=lambda email: email["date"].timestamp() if email["date"] else float("-inf"),
        reverse=True,
    )
    return emails


# ---------------------------------------------------------------------------
# Per-email summarization via Ollama
# ---------------------------------------------------------------------------


def build_email_prompt(email: dict) -> str:
    return (
        "Summarize this email in two or three concise sentences. Include important "
        "dates, deadlines, requests, and actions the recipient needs to take. Do "
        "not add facts that are not in the email.\n\n"
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email['date'] or 'unknown'}\n"
        f"Email body:\n{email['body']}"
    )


def summarize_email(email: dict, client, model: str, max_new_tokens: int) -> str:
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": build_email_prompt(email)}],
        options={
            "temperature": 0,
            "num_predict": max_new_tokens,
        },
    )
    return response["message"]["content"].strip()


def format_email_summary(email: dict, summary: str) -> str:
    sent_at = email["date"]
    date_text = sent_at.strftime("%B %d, %Y %p") if sent_at else "an unknown date"
    sender_name, sender_address = parseaddr(email["from"])
    sender = sender_name or sender_address or email["from"]
    return (
        f"From: {sender}\n"
        f"Received: {date_text}\n"
        f"Summary: {summary}"
    )


def summarize_overall(
    per_email_summaries: str,
    client,
    model: str,
    max_new_tokens: int,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Create a complete, engaging newsletter with a clear structure. "
                "Organize content into logical sections with brief descriptive headers, "
                "prioritize timely announcements and key updates, consolidate related items, "
                "and remove duplication. Use natural, conversational language in plain paragraphs. "
                "Include a compelling opening that sets the tone, a closing section for calls to action, "
                "and maintain consistent voice throughout. Avoid excessive formatting—use headers sparingly "
                "and keep the focus on readability and value for the reader. Base the newsletter only on "
                "the provided content summaries. Return the finished newsletter directly without analysis."
            ),
        },
        {
            "role": "user",
            "content": (
                "Write one overall newsletter from these per-email summaries:\n\n"
                f"{per_email_summaries}"
            ),
        },
    ]

    # Ollama exposes reasoning separately from the final content. Disabling it
    # prevents a thinking model from using the entire token budget before it
    # writes the briefing.
    response = client.chat(
        model=model,
        messages=messages,
        options={"temperature": 0, "num_predict": max_new_tokens},
    )
    content = response["message"]["content"].strip()
    if content:
        return content

    # Retry once if the model returns no final content. Preserve unlimited
    # generation when num_predict is -1.
    retry_tokens = (
        -1 if max_new_tokens == -1 else max(1024, max_new_tokens * 2)
    )
    token_description = "unlimited" if retry_tokens == -1 else str(retry_tokens)
    log.warning(
        "Model '%s' returned no final text; retrying with %s output tokens.",
        model,
        token_description,
    )
    response = client.chat(
        model=model,
        messages=messages,
        think=False,
        options={"temperature": 0, "num_predict": retry_tokens},
    )
    content = response["message"]["content"].strip()
    if not content:
        raise RuntimeError(
            "Ollama returned an empty final response twice. Try another "
            "--overall-model."
        )
    return content


def unload_model(client, model: str) -> None:
    """Immediately unload an Ollama model from CPU/GPU memory."""
    client.generate(model=model, prompt="", keep_alive="0s")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory tree of .eml files to summarize.",
    )
    parser.add_argument("--days", type=int, default=DAYS_BACK, help="How many days back to summarize.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ollama model used to summarize each individual email.",
    )
    parser.add_argument(
        "--overall-model",
        default=DEFAULT_OVERALL_MODEL,
        help="Larger Ollama model used to create the overall email briefing.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_OLLAMA_HOST,
        help="Ollama server URL.",
    )
    parser.add_argument(
        "--max-summary-tokens",
        type=int,
        default=MAX_SUMMARY_TOKENS,
        help="Maximum number of generated tokens in each email summary.",
    )
    parser.add_argument(
        "--max-overall-summary-tokens",
        type=int,
        default=MAX_OVERALL_SUMMARY_TOKENS,
        help="Maximum tokens in the overall briefing; -1 means unlimited.",
    )
    parser.add_argument(
        "--intermediate-output",
        type=Path,
        default=INTERMEDIATE_SUMMARY_TEXT_FILE,
        help="Path for the temporary per-email summaries.",
    )
    parser.add_argument("--output", type=Path, default=SUMMARY_TEXT_FILE, help="Path to the output summary text file.")
    args = parser.parse_args()

    if args.max_summary_tokens < 1:
        parser.error("--max-summary-tokens must be at least 1")
    if args.max_overall_summary_tokens == 0 or args.max_overall_summary_tokens < -1:
        parser.error(
            "--max-overall-summary-tokens must be -1 (unlimited) or a positive integer"
        )

    if not args.source.exists():
        log.error("Source directory '%s' not found. Run imap_download.py first.", args.source)
        sys.exit(1)

    log.info("Loading emails from the past %d day(s)...", args.days)
    emails = load_recent_emails(args.source, args.days)
    if not emails:
        log.warning("No emails found in the past %d day(s). Nothing to summarize.", args.days)
        sys.exit(0)
    log.info("Found %d email(s).", len(emails))

    try:
        import ollama
    except ImportError:
        log.error(
            "The 'ollama' Python package is not installed. Install it with: "
            "python -m pip install ollama"
        )
        sys.exit(1)

    client = ollama.Client(host=args.host)
    log.info("Connecting to Ollama at %s...", args.host)
    for model in dict.fromkeys((args.model, args.overall_model)):
        try:
            client.show(model)
        except Exception as exc:
            log.error(
                "Could not use Ollama model '%s'. Make sure Ollama is running and "
                "install the model with 'ollama pull %s'. Error: %s",
                model,
                model,
                exc,
            )
            sys.exit(1)

    formatted_summaries = []
    total = len(emails)
    for index, email in enumerate(emails, start=1):
        log.info(
            "Summarizing email %d/%d: %s",
            index,
            total,
            email["subject"],
        )
        try:
            summary = summarize_email(
                email,
                client,
                args.model,
                args.max_summary_tokens,
            )
        except Exception as exc:
            log.warning("Could not summarize %s: %s", email["path"], exc)
            summary = "This email could not be summarized."
        formatted_summaries.append(format_email_summary(email, summary))

    intermediate_text = "\n\n".join(formatted_summaries) + "\n"
    args.intermediate_output.parent.mkdir(parents=True, exist_ok=True)
    args.intermediate_output.write_text(intermediate_text, encoding="utf-8")
    log.info(
        "Saved %d individual email summaries to %s.",
        total,
        args.intermediate_output,
    )

    if args.model != args.overall_model:
        log.info("Unloading per-email model '%s' from memory...", args.model)
        try:
            unload_model(client, args.model)
        except Exception as exc:
            log.error(
                "Could not unload Ollama model '%s'; the overall model will not "
                "be started to avoid exhausting GPU memory. Error: %s",
                args.model,
                exc,
            )
            sys.exit(1)
    else:
        log.info("Both stages use model '%s'; keeping it loaded.", args.model)

    log.info("Creating overall summary with Ollama model '%s'...", args.overall_model)
    try:
        overall_summary = summarize_overall(
            intermediate_text,
            client,
            args.overall_model,
            args.max_overall_summary_tokens,
        )
    except Exception as exc:
        log.error(
            "Could not create the overall summary with model '%s': %s",
            args.overall_model,
            exc,
        )
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(overall_summary + "\n", encoding="utf-8")
    log.info("Overall summary saved to %s", args.output)


if __name__ == "__main__":
    main()
