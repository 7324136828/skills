---
name: html-split
description: Split one oversized HTML document — a single-page manual, an API reference, an exported wiki or book — into per-section plain-text files small enough to read, grep, or embed one at a time. Use when a document is too large to load into context in one piece, when preparing source material for retrieval or per-section analysis, or when someone asks to chunk, section, or convert a big HTML file to text.
---

# HTML document splitter

`html_split.py` walks a document's own heading structure and writes one readable
`.txt` file per section, so a 500 KB single-page manual becomes a couple of dozen
files that can be opened individually. Standard library only.

## Run it

```bash
python html_split.py <input.html> -o <output_dir>
```

Options:

- `--threshold N` (default 40000) — a section whose text exceeds N characters is
  exploded into its own subfolder and split again by its `<h2>` headings. A
  sub-section still over the threshold with no headings left is chunked at block
  boundaries (`</p>`, `</ul>`, `</pre>`), so list entries and code blocks are
  never cut in half. Lower it to around 15000 when the files are destined for a
  context window.
- `--any-h1` — treat every `<h1>` as a section boundary. By default only `<h1>`
  tags carrying an `id` attribute count, which skips decorative headings. If the
  run reports "No `<h1>` section headings found", this is the flag to try.

## What you get

```
output/
  00_intro.txt                  document title + table of contents
  01_<slugified-heading>.txt
  ...
  14_<big-section>/             a section that exceeded the threshold
    00_intro.txt
    01_<sub-heading>.txt
    07_<sub-heading>_part01.txt
```

Conversion keeps what matters for reading: block tags become line breaks, list
items get a `- ` prefix, `<pre>` blocks keep their internal formatting and
indentation, entities are decoded. Everything else is dropped.

## Working with the result

- Start with `00_intro.txt` — it holds the table of contents, which is the map
  of what every other file contains.
- Then grep across the folder to locate a topic and read only the files that
  hit. Reading every file defeats the point of splitting.
- The numeric prefixes preserve document order; keep them if reading order
  matters downstream.

## Rules

- Writes only into `-o`; the input document is never modified.
- The split is lossy on purpose — tables, images, and attributes do not survive.
  Go back to the source HTML for anything where exact markup matters.
