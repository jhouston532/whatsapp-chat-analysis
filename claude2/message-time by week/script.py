"""
chat_to_csv.py
==============
Read a WhatsApp chat export (chat.txt) and produce a wide-format CSV
message-count timeline: one row per fixed time bucket (default 30 min),
one column per participant, with the number of messages that
participant sent in that bucket.

Header row:
    time,user1,user2,user3,...

Usage:
    python chat_to_csv.py chat.txt
    python chat_to_csv.py chat.txt -o output.csv
    python chat_to_csv.py chat.txt --interval 15   # 15-minute buckets
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timedelta
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


def floor_to_bucket(ts: datetime, interval_minutes: int) -> datetime:
    """Round a timestamp down to the start of its N-minute bucket (from midnight)."""
    minutes_since_midnight = ts.hour * 60 + ts.minute
    bucket_start_minutes = (minutes_since_midnight // interval_minutes) * interval_minutes
    day_start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start + timedelta(minutes=bucket_start_minutes)


def build_bucket_counts(
    rows: list[tuple[Optional[datetime], str, str]], interval_minutes: int
) -> tuple[list[datetime], list[str], dict[tuple[datetime, str], int]]:
    """
    Bucket messages into fixed-size time windows and count messages per
    user per bucket. Returns (all_buckets, users, counts) where
    all_buckets spans every bucket from the first to the last message
    (inclusive), even ones with zero activity, and users preserves
    first-seen order.
    """
    # Preserve first-seen order of participants for stable, readable columns.
    users: list[str] = []
    counts: dict[tuple[datetime, str], int] = {}
    timestamped_rows = [(ts, author) for ts, author, _ in rows if ts is not None]

    for _, author, _ in rows:
        if author not in users:
            users.append(author)

    for ts, author in timestamped_rows:
        bucket = floor_to_bucket(ts, interval_minutes)
        key = (bucket, author)
        counts[key] = counts.get(key, 0) + 1

    if not timestamped_rows:
        return [], users, counts

    first_bucket = floor_to_bucket(min(ts for ts, _ in timestamped_rows), interval_minutes)
    last_bucket = floor_to_bucket(max(ts for ts, _ in timestamped_rows), interval_minutes)

    all_buckets: list[datetime] = []
    current = first_bucket
    step = timedelta(minutes=interval_minutes)
    while current <= last_bucket:
        all_buckets.append(current)
        current += step

    return all_buckets, users, counts


def group_buckets_by_week(all_buckets: list[datetime]) -> list[list[datetime]]:
    """
    Split a contiguous list of time buckets into 7-day windows, starting
    from the date of the very first bucket. Returns a list of bucket
    lists, one per week, in chronological order.
    """
    if not all_buckets:
        return []

    start_date = all_buckets[0].date()
    weeks: dict[int, list[datetime]] = {}

    for bucket in all_buckets:
        week_index = (bucket.date() - start_date).days // 7
        weeks.setdefault(week_index, []).append(bucket)

    return [weeks[idx] for idx in sorted(weeks)]


def write_csv(
    week_buckets: list[datetime],
    users: list[str],
    counts: dict[tuple[datetime, str], int],
    out_path: str,
    multi_day: bool,
) -> None:
    time_fmt = "%Y-%m-%d %H:%M" if multi_day else "%H:%M"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time"] + users)

        for bucket in week_buckets:
            row = [bucket.strftime(time_fmt)]
            row.extend(counts.get((bucket, user), 0) for user in users)
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a WhatsApp chat export into per-user message-count timeline CSVs, one per 7-day window."
    )
    parser.add_argument("chat_file", help="Path to the exported chat.txt file")
    parser.add_argument(
        "-o", "--output", default=None,
        help="Base output CSV path (default: <chat_file>_timeline.csv). "
             "Each 7-day window is written as <base>_<start>_<end><ext>.",
    )
    parser.add_argument(
        "--interval", type=int, default=30, help="Bucket size in minutes (default: 30)"
    )
    args = parser.parse_args()

    base_out = args.output or str(Path(args.chat_file).with_suffix("").as_posix()) + "_timeline.csv"
    base_path = Path(base_out)
    base_stem, base_ext = base_path.stem, base_path.suffix or ".csv"
    base_dir = base_path.parent

    rows = parse_chat(args.chat_file)
    if not rows:
        print("No attributable messages found — check the file's timestamp/author format.")
        sys.exit(1)

    all_buckets, users, counts = build_bucket_counts(rows, args.interval)
    if not all_buckets:
        print("No timestamped messages found — nothing to bucket.")
        sys.exit(1)

    weeks = group_buckets_by_week(all_buckets)

    print(f"Parsed {len(rows)} attributable messages from {len(users)} participants.")
    print(f"Bucketed into {len(all_buckets)} {args.interval}-minute intervals across {len(weeks)} week(s).")

    for week_buckets in weeks:
        start_date = week_buckets[0].date()
        end_date = week_buckets[-1].date()
        out_path = base_dir / f"{base_stem}_{start_date}_{end_date}{base_ext}"

        multi_day = start_date != end_date
        write_csv(week_buckets, users, counts, str(out_path), multi_day)

        print(f"  {start_date} to {end_date}: {out_path}")


if __name__ == "__main__":
    main()
    