2#!/usr/bin/env python3
"""
mean_time_between_messages.py

Parses a WhatsApp group chat export (.txt) and computes the mean
(and other summary stats) of the time gap between consecutive messages.

Usage:
    python mean_time_between_messages.py chat.txt
    python mean_time_between_messages.py chat.txt --per-sender
    python mean_time_between_messages.py chat.txt --unit minutes
"""

import argparse
import re
import statistics
from datetime import datetime

# Characters WhatsApp exports often sprinkle in for bidi rendering
# (LRM, RLM, LRE/RLE/PDF, LRI/RLI/FSI/PDI, ALM, and narrow no-break space)
BIDI_CHARS = re.compile(
    "[\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c\u202f]"
)

# Matches the start of a new message line, e.g.:
# [5/5/26, 11:00:38 AM] ~ GateMix: Hello everyone...
MESSAGE_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2}\s?[APap][Mm])\]\s*"
    r"(?P<sender>[^:]+):\s?(?P<message>.*)$"
)


def clean_line(line: str) -> str:
    """Strip invisible bidi/formatting characters and replace narrow
    no-break spaces with regular spaces so parsing/regex behave."""
    return BIDI_CHARS.sub(" ", line).strip()


def parse_chat(path: str):
    """Yield (datetime, sender, message) tuples for every message in the file.

    Multi-line messages (a message body that contains literal newlines)
    are stitched back onto the most recent timestamped message.
    """
    entries = []
    current = None

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = clean_line(raw_line)
            if not line:
                continue

            match = MESSAGE_RE.match(line)
            if match:
                date_str, time_str, sender, message = match.groups()
                sender = sender.strip()
                dt = parse_datetime(date_str, time_str)
                if dt is None:
                    # Couldn't parse the timestamp; treat as a continuation
                    # of the previous message rather than dropping it.
                    if current is not None:
                        current["message"] += "\n" + line
                    continue
                current = {"dt": dt, "sender": sender, "message": message}
                entries.append(current)
            else:
                # Continuation of a previous multi-line message
                if current is not None:
                    current["message"] += "\n" + line

    return entries


def parse_datetime(date_str: str, time_str: str):
    """Try a handful of common WhatsApp export date/time formats."""
    time_str = time_str.replace(" ", "")  # "11:00:38AM" -> normalize
    candidates = [
        "%m/%d/%y,%I:%M:%S%p",
        "%m/%d/%Y,%I:%M:%S%p",
        "%d/%m/%y,%I:%M:%S%p",
        "%d/%m/%Y,%I:%M:%S%p",
    ]
    combined = f"{date_str},{time_str}"
    for fmt in candidates:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    return None


SYSTEM_MSG_MARKERS = (
    "Messages and calls are end-to-end encrypted",
    "created this group",
    "added you",
    "added ~",
    "changed the settings",
    "changed this group",
    "reset this group's invite link",
    "changed the group description",
)


def is_system_message(message: str) -> bool:
    return any(marker in message for marker in SYSTEM_MSG_MARKERS)


def compute_gaps(entries, exclude_system=True):
    """Return list of gaps (seconds) between consecutive message timestamps."""
    if exclude_system:
        entries = [e for e in entries if not is_system_message(e["message"])]

    entries = sorted(entries, key=lambda e: e["dt"])
    gaps = []
    for prev, curr in zip(entries, entries[1:]):
        delta = (curr["dt"] - prev["dt"]).total_seconds()
        if delta >= 0:
            gaps.append(delta)
    return gaps


def format_seconds(seconds: float, unit: str) -> str:
    if unit == "seconds":
        return f"{seconds:.2f} sec"
    if unit == "minutes":
        return f"{seconds / 60:.2f} min"
    if unit == "hours":
        return f"{seconds / 3600:.2f} hr"
    return f"{seconds:.2f} sec"


def summarize(gaps, unit):
    if not gaps:
        print("Not enough messages to compute a gap.")
        return
    mean_gap = statistics.mean(gaps)
    median_gap = statistics.median(gaps)
    stdev_gap = statistics.stdev(gaps) if len(gaps) > 1 else 0.0
    print(f"  Messages considered : {len(gaps) + 1}")
    print(f"  Gaps computed       : {len(gaps)}")
    print(f"  Mean time between   : {format_seconds(mean_gap, unit)}")
    print(f"  Median time between : {format_seconds(median_gap, unit)}")
    print(f"  Std dev             : {format_seconds(stdev_gap, unit)}")
    print(f"  Min gap             : {format_seconds(min(gaps), unit)}")
    print(f"  Max gap             : {format_seconds(max(gaps), unit)}")


def main():
    parser = argparse.ArgumentParser(
        description="Compute mean time between messages in a WhatsApp export."
    )
    parser.add_argument("chat_file", help="Path to the exported WhatsApp .txt file")
    parser.add_argument(
        "--unit",
        choices=["seconds", "minutes", "hours"],
        default="minutes",
        help="Unit to display gap statistics in (default: minutes)",
    )
    parser.add_argument(
        "--include-system",
        action="store_true",
        help="Include WhatsApp system messages (joins, settings changes, etc.) "
        "in the calculation. Excluded by default.",
    )
    parser.add_argument(
        "--per-sender",
        action="store_true",
        help="Also break down mean time between messages for each sender "
        "(time since that same sender's previous message).",
    )
    args = parser.parse_args()

    entries = parse_chat(args.chat_file)
    if not entries:
        print("No messages could be parsed from this file.")
        return

    print(f"Parsed {len(entries)} total messages from {args.chat_file}\n")

    print("=== Overall (all senders, chronological) ===")
    gaps = compute_gaps(entries, exclude_system=not args.include_system)
    summarize(gaps, args.unit)

    if args.per_sender:
        print("\n=== Per-sender (gap since that sender's own previous message) ===")
        by_sender = {}
        filtered = entries if args.include_system else [
            e for e in entries if not is_system_message(e["message"])
        ]
        for e in filtered:
            by_sender.setdefault(e["sender"], []).append(e)

        for sender, msgs in sorted(by_sender.items(), key=lambda kv: kv[0].lower()):
            msgs = sorted(msgs, key=lambda e: e["dt"])
            sender_gaps = [
                (b["dt"] - a["dt"]).total_seconds()
                for a, b in zip(msgs, msgs[1:])
                if (b["dt"] - a["dt"]).total_seconds() >= 0
            ]
            if sender_gaps:
                mean_gap = statistics.mean(sender_gaps)
                print(
                    f"  {sender:30s} n={len(msgs):4d}  "
                    f"mean={format_seconds(mean_gap, args.unit)}"
                )
            else:
                print(f"  {sender:30s} n={len(msgs):4d}  (only 1 message, no gap)")


if __name__ == "__main__":
    main()


    