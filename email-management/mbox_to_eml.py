#!/usr/bin/env python3
"""Export messages from Thunderbird/Outlook-style mbox files to individual .eml files.

Each top-level file in the input folder that is not an index (.msf) or data
(.dat) file is treated as an mbox file (e.g. INBOX, Sent, Archive, Drafts).
Every message inside is written out as a separate .eml file, grouped into a
subfolder named after the source mbox file.
"""

import argparse
import mailbox
import os
import re

SKIP_EXTENSIONS = {".msf", ".dat"}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_NAME_LEN = 80


def sanitize(name: str) -> str:
    name = INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return name[:MAX_NAME_LEN] if name else "untitled"


def export_mbox(mbox_path: str, output_dir: str) -> int:
    folder_name = os.path.basename(mbox_path)
    dest_dir = os.path.join(output_dir, sanitize(folder_name))
    os.makedirs(dest_dir, exist_ok=True)

    box = mailbox.mbox(mbox_path, factory=None, create=False)
    count = 0
    try:
        for index, message in enumerate(box, start=1):
            subject = sanitize(message.get("Subject", "no_subject"))
            filename = f"{index:05d}_{subject}.eml"
            dest_path = os.path.join(dest_dir, filename)
            try:
                with open(dest_path, "wb") as f:
                    f.write(message.as_bytes())
                count += 1
            except Exception as exc:
                print(f"  [warn] failed to write message {index} from {folder_name}: {exc}")
    finally:
        box.close()

    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_dir",
        nargs="?",
        default=os.path.dirname(os.path.abspath(__file__)),
        help="Folder containing the mbox files (default: script's folder)",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"),
        help="Folder to write .eml files to (default: <script folder>/output)",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    total = 0
    for entry in sorted(os.listdir(args.input_dir)):
        full_path = os.path.join(args.input_dir, entry)
        if not os.path.isfile(full_path):
            continue
        if os.path.splitext(entry)[1].lower() in SKIP_EXTENSIONS:
            continue
        if entry == os.path.basename(__file__):
            continue

        print(f"Processing {entry} ...")
        try:
            n = export_mbox(full_path, args.output_dir)
        except Exception as exc:
            print(f"  [error] could not process {entry}: {exc}")
            continue

        print(f"  exported {n} message(s)")
        total += n

    print(f"Done. Exported {total} message(s) to {args.output_dir}")


if __name__ == "__main__":
    main()
