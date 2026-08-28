#!/usr/bin/env python3
"""
html_split.py -- Split one large HTML document into per-section .txt files.

Long single-page documentation (a manual, a reference, an exported wiki) is
awkward to feed to a language model in one piece. This splits it on its own
heading structure into files small enough to read or embed individually.

Sections are delimited by top-level <h1> headings (by default only those that
carry an id attribute, which skips decorative headings). Everything before the
first such heading -- the document title and table of contents -- is written as
an intro file. Each section's HTML becomes readable plain text: block-level tags
become line breaks, list items get a "- " prefix, <pre> code blocks keep their
internal formatting, and HTML entities are decoded.

Any section whose text exceeds --threshold is exploded into its own subfolder,
split further by <h2> sub-headings; a sub-section that is still oversized and
has no headings left is chunked at block boundaries.

Usage:
    python html_split.py manual.html -o output
    python html_split.py manual.html -o output --threshold 20000 --any-h1
"""

import argparse
import html
import os
import re
import sys

DEFAULT_OUTPUT_DIR = "output"

# <h1> sections whose plain-text length exceeds this get split by <h2>.
DEFAULT_SUBSPLIT_THRESHOLD = 40000


def slugify(text, maxlen=50):
    """Turn a heading into a safe, readable filename fragment."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)      # drop punctuation
    text = re.sub(r"[\s_-]+", "_", text)      # spaces -> underscores
    text = text.strip("_")
    return (text[:maxlen].rstrip("_")) or "section"


def html_to_text(fragment):
    """Convert an HTML fragment to readable plain text."""
    # Preserve <pre> blocks: strip inner tags but keep newlines/indentation.
    def clean_pre(match):
        inner = match.group(1)
        inner = re.sub(r"<[^>]+>", "", inner)   # remove span colouring etc.
        inner = html.unescape(inner)
        return "\n" + inner.strip("\n") + "\n"

    fragment = re.sub(r"<pre[^>]*>(.*?)</pre>", clean_pre, fragment, flags=re.S)

    # Block-level boundaries -> newlines.
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"</(p|h1|h2|h3|div|tr|ul|ol)>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<li[^>]*>", "\n- ", fragment, flags=re.I)
    fragment = re.sub(r"</li>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<h[123][^>]*>", "\n\n", fragment, flags=re.I)

    # Remove all remaining tags, then decode entities.
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)

    # Tidy whitespace: trim trailing spaces, collapse 3+ blank lines.
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def split_by_heading(fragment, heading_re):
    """Split an HTML fragment on heading *start* positions.

    Returns (preamble_html, [(title, html_part), ...]). Splitting on the start
    position (not requiring a matching close tag) tolerates the malformed
    headings in this document whose close tags are all emitted at the very end.
    """
    matches = list(heading_re.finditer(fragment))
    if not matches:
        return fragment, []

    preamble = fragment[: matches[0].start()]
    parts = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(fragment)
        after = fragment[m.end():end]
        title = html.unescape(re.split(r"<", after, maxsplit=1)[0]).strip()
        parts.append((title, fragment[start:end]))
    return preamble, parts


def chunk_html(fragment, max_chars):
    """Greedily group a heading-less fragment into <= max_chars text chunks.

    Splits only at top-level block boundaries (</p>, </ul>, </pre>) so list
    entries and code blocks are never cut in half. Returns a list of HTML
    chunks (always at least one).
    """
    marked = re.sub(r"(</(?:ul|pre|p)>)", "\\1\x00", fragment, flags=re.I)
    blocks = [b for b in marked.split("\x00") if b.strip()]
    if not blocks:
        return [fragment]

    chunks, current, current_len = [], "", 0
    for block in blocks:
        block_len = len(html_to_text(block))
        if current and current_len + block_len > max_chars:
            chunks.append(current)
            current, current_len = "", 0
        current += block
        current_len += block_len
    if current:
        chunks.append(current)
    return chunks


def write_file(path, text):
    with open(path, "w", encoding="utf-8") as out:
        out.write(text)
    return (path, len(text))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("input", help="HTML file to split")
    ap.add_argument("-o", "--out", default=DEFAULT_OUTPUT_DIR,
                    help="Directory to write the .txt files to (default: %(default)s)")
    ap.add_argument("--threshold", type=int, default=DEFAULT_SUBSPLIT_THRESHOLD,
                    help="Split a section further once its text exceeds this many "
                         "characters (default: %(default)s)")
    ap.add_argument("--any-h1", action="store_true",
                    help="Treat every <h1> as a section boundary, not only those "
                         "carrying an id attribute")
    args = ap.parse_args(argv)

    if not os.path.exists(args.input):
        sys.exit(f"Input file not found: {args.input}")

    with open(args.input, encoding="utf-8", errors="replace") as f:
        content = f.read()

    h1_re = re.compile(r"<h1[^>]*>" if args.any_h1 else r'<h1\s+id="[^"]*"[^>]*>', re.I)
    h2_re = re.compile(r"<h2[^>]*>", re.I)
    threshold = args.threshold

    intro_html, h1_parts = split_by_heading(content, h1_re)
    if not h1_parts:
        sys.exit("No <h1> section headings found. Try --any-h1.")

    os.makedirs(args.out, exist_ok=True)
    written = []

    # Intro: document title + table of contents (before the first <h1>).
    intro_text = html_to_text(intro_html)
    if intro_text.strip():
        written.append(write_file(os.path.join(args.out, "00_intro.txt"), intro_text))

    for i, (title, part_html) in enumerate(h1_parts, start=1):
        name = f"{i:02d}_{slugify(title)}"
        text = html_to_text(part_html)

        if len(text) <= threshold:
            written.append(write_file(os.path.join(args.out, f"{name}.txt"), text))
            continue

        # Oversized section -> explode into a subfolder split by <h2>.
        subdir = os.path.join(args.out, name)
        os.makedirs(subdir, exist_ok=True)
        sub_preamble, sub_parts = split_by_heading(part_html, h2_re)

        pre_text = html_to_text(sub_preamble)
        if pre_text.strip():
            written.append(write_file(os.path.join(subdir, "00_intro.txt"), pre_text))

        for j, (sub_title, sub_html) in enumerate(sub_parts, start=1):
            sub_name = f"{j:02d}_{slugify(sub_title)}"
            sub_text = html_to_text(sub_html)

            if len(sub_text) <= threshold:
                written.append(write_file(os.path.join(subdir, f"{sub_name}.txt"), sub_text))
                continue

            # Heading-less but still huge -> chunk at block boundaries.
            for k, chunk in enumerate(chunk_html(sub_html, threshold), start=1):
                path = os.path.join(subdir, f"{sub_name}_part{k:02d}.txt")
                written.append(write_file(path, html_to_text(chunk)))

        # A section with no <h2> at all still needs chunking.
        if not sub_parts:
            for k, chunk in enumerate(chunk_html(part_html, threshold), start=1):
                path = os.path.join(subdir, f"part{k:02d}.txt")
                written.append(write_file(path, html_to_text(chunk)))

    print(f"Wrote {len(written)} files under {args.out}/:")
    for path, size in written:
        print(f"  {path}  ({size} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
