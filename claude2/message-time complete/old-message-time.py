"""
chat_to_csv.py
==============
Read a WhatsApp chat export (chat.txt) and produce a wide-format CSV
timeline: one row per message, one column per participant, with the
message text placed in that participant's column.

Header row:
    time,user1,user2,user3,...

Usage:
    python chat_to_csv.py chat.txt
    python chat_to_csv.py chat.txt -o output.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- 
# Cleanup helpers
# ---------------------------------------------------------------------------

# WhatsApp exports are full of invisible bidi/formatting marks:
#   U+200E LRM, U+200F RLM, U+202A-U+202E embedding/override marks,
#   U+2066-U+2069 isolate marks, U+FEFF BOM.
_INVISIBLE_CHARS = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")

# WhatsApp also renders phone-number separators using non-breaking/typographic
# hyphen variants (e.g. U+2011 non-breaking hyphen) instead of a plain '-'.
_DASH_VARIANTS = re.compile(r"[\u2010-\u2015\u2212]")


def clean_text(text: str) -> str:
    text = _INVISIBLE_CHARS.sub("", text)
    text = _DASH_VARIANTS.sub("-", text)
    return text.strip()


# --------------------------------------------------------------------------- 
# Header parsing: "[M/D/YY, H:MM:SS AM] Author: message"
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(
    r"^\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s*"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?\s?[APap][Mm])\]\s(?P<rest>.*)$"
)

_AUTHOR_SPLIT_RE = re.compile(r"^(?P<author>[^:]{1,80}?):\s(?P<message>.*)$", re.DOTALL)

_DATE_FORMATS = (
    "%m/%d/%y %I:%M:%S %p", "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%y %I:%M %p", "%m/%d/%Y %I:%M %p",
)


def is_record_start(line: str) -> bool:
    return bool(_HEADER_RE.match(clean_text(line)))


def split_into_records(lines: list[str]) -> list[str]:
    """Fold continuation lines (multi-line messages) into the record they belong to."""
    records: list[str] = []
    current: list[str] = []

    for line in lines:
        if is_record_start(line):
            if current:
                records.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
        # else: stray content before the first real record, ignored

    if current:
        records.append("\n".join(current))

    return records


def parse_timestamp(date_str: str, time_str: str) -> Optional[datetime]:
    combined = f"{date_str} {time_str}"
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    return None


def parse_record(record: str) -> Optional[tuple[Optional[datetime], str, str]]:
    """Return (timestamp, author, message) or None if the record can't be parsed
    or has no identifiable author (pure system/group-level notices with no sender)."""
    cleaned = clean_text(record)
    match = _HEADER_RE.match(cleaned)
    if not match:
        return None

    ts = parse_timestamp(match.group("date"), match.group("time"))
    rest = match.group("rest")

    author_match = _AUTHOR_SPLIT_RE.match(rest)
    if not author_match:
        return None  # no "Author:" prefix at all -> can't attribute to a user

    author = author_match.group("author").strip()
    message = author_match.group("message").strip()

    if not author or not message:
        return None

    return ts, author, message


# --------------------------------------------------------------------------- 
# Main pipeline
# ---------------------------------------------------------------------------

def parse_chat(filepath: str) -> list[tuple[Optional[datetime], str, str]]:
    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().splitlines()

    records = split_into_records(lines)

    parsed: list[tuple[Optional[datetime], str, str]] = []
    for record in records:
        result = parse_record(record)
        if result is not None:
            parsed.append(result)

    return parsed


def write_csv(rows: list[tuple[Optional[datetime], str, str]], out_path: str) -> list[str]:
    # Preserve first-seen order of participants for stable, readable columns.
    users: list[str] = []
    for _, author, _ in rows:
        if author not in users:
            users.append(author)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time"] + users)

        for ts, author, message in rows:
            time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else ""
            row = [time_str] + ["" for _ in users]
            row[1 + users.index(author)] = message
            writer.writerow(row)

    return users


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a WhatsApp chat export into a per-user timeline CSV.")
    parser.add_argument("chat_file", help="Path to the exported chat.txt file")
    parser.add_argument("-o", "--output", default=None, help="Output CSV path (default: <chat_file>_timeline.csv)")
    args = parser.parse_args()

    out_path = args.output or str(Path(args.chat_file).with_suffix("").as_posix()) + "_timeline.csv"

    rows = parse_chat(args.chat_file)
    if not rows:
        print("No attributable messages found — check the file's timestamp/author format.")
        sys.exit(1)

    users = write_csv(rows, out_path)

    print(f"Parsed {len(rows)} attributable messages from {len(users)} participants.")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()