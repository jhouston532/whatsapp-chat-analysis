#!/usr/bin/env python3
"""
whatsapp_chat_analyzer.py

Analyzes an exported WhatsApp group chat (.txt) for research purposes:
  1. Per-message timing data (for comparing when each user posts)
  2. Message "chain"/burst detection (for spotting bot-like regular intervals)
  3. Per-user keyword frequency counts

Usage:
    python whatsapp_chat_analyzer.py path/to/chat.txt [options]

Optional flags:
    --outdir DIR           Output folder (default: whatsapp_analysis_output)
    --chain-gap SECONDS     Max gap between messages to count as same burst (default: 60)
    --top-keywords N        Max keywords kept per user (default: 200)
    --include-system        Include WhatsApp system/notification messages in keyword counts

All output files are CSVs, written to an output folder, so they can be
dropped straight into Excel / Google Sheets / any charting tool.
"""

import argparse
import csv
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration / constants
# ---------------------------------------------------------------------------

# Matches the start of a new WhatsApp message line, e.g.:
# [5/5/26, 10:34:46 AM] ~ GateMix: Hello everyone...
MESSAGE_LINE_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2}\s?[APMapm]{2})\]\s*"
    r"([^:]+):\s(.*)$"
)

# WhatsApp system/notification messages look like normal messages (sent
# "from" a phone number/name) but are really group-management events, not
# actual chat content. We flag them so they can be excluded from the
# keyword analysis (and, if you want, the timing analysis too).
SYSTEM_MESSAGE_PATTERNS = [
    r"changed this group's",
    r"changed the group description",
    r"changed the group icon",
    r"changed their phone number",
    r"added ",
    r"removed ",
    r"left$",
    r"created group",
    r"joined using this group's invite link",
    r"Messages and calls are end-to-end encrypted",
    r"changed the subject",
    r"security code changed",
]
SYSTEM_MESSAGE_RE = re.compile("|".join(SYSTEM_MESSAGE_PATTERNS), re.IGNORECASE)

# Minimal, generic English stopword list (kept short so we don't
# accidentally hide meaningful slang/keywords used in the chat).
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "being", "i", "you", "he",
    "she", "it", "we", "they", "this", "that", "these", "those", "my",
    "your", "his", "her", "its", "our", "their", "with", "at", "by", "from",
    "as", "so", "not", "no", "yes", "do", "does", "did", "have", "has",
    "had", "will", "would", "can", "could", "should", "just", "about",
    "up", "out", "get", "got", "like", "im", "dont", "me", "them", "us",
    "am", "than", "then", "there", "here", "what", "who", "when", "where",
    "why", "how", "all", "any", "some", "more", "most", "other", "into",
    "over", "again", "also", "very", "really", "much", "many", "one",
    "two", "new", "now", "because",
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def read_lines(filepath):
    """Read the raw chat export file, tolerating odd encodings/BOMs."""
    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.readlines()


def parse_datetime(date_str, time_str):
    """
    Convert the WhatsApp date/time strings into a datetime object.
    Handles 2-digit or 4-digit years and 12-hour AM/PM time formats.
    Timezone is not attached here -- all timestamps in the export are
    already Mountain Daylight Time (MDT), per the source file.
    """
    time_str = time_str.replace("\u202f", " ").strip()  # narrow no-break space fix
    for fmt in ("%m/%d/%y, %I:%M:%S %p", "%m/%d/%Y, %I:%M:%S %p"):
        try:
            return datetime.strptime(f"{date_str}, {time_str}", fmt)
        except ValueError:
            continue
    raise ValueError(f"Could not parse datetime: {date_str} {time_str}")


def parse_messages(lines):
    """
    Turn raw export lines into a list of message dicts:
        {"datetime": datetime, "sender": str, "message": str, "is_system": bool}

    WhatsApp exports wrap long messages across multiple physical lines.
    Any line that doesn't start with a new "[date, time]" stamp is treated
    as a continuation of the previous message and appended to it.
    """
    messages = []
    for raw_line in lines:
        line = raw_line.rstrip("\n").replace("\u200e", "")  # strip left-to-right marks
        match = MESSAGE_LINE_RE.match(line)
        if match:
            date_str, time_str, sender, text = match.groups()
            try:
                dt = parse_datetime(date_str, time_str)
            except ValueError:
                # Couldn't parse the timestamp -- treat as a continuation instead
                if messages:
                    messages[-1]["message"] += "\n" + line
                continue
            messages.append({
                "datetime": dt,
                "sender": sender.strip(),
                "message": text.strip(),
                "is_system": bool(SYSTEM_MESSAGE_RE.search(text)),
            })
        else:
            # Continuation of the previous message (multi-line message)
            if messages and line.strip():
                messages[-1]["message"] += "\n" + line.strip()
    return messages


# ---------------------------------------------------------------------------
# Analysis 1: Per-message timing (who posts when)
# ---------------------------------------------------------------------------

def export_message_timeline(messages, outdir):
    """
    Write one row per message with time-of-day fields, so each user's
    posting times can be compared directly in a spreadsheet (e.g. scatter
    plot of hour_decimal vs. date, colored/grouped by sender).
    """
    path = os.path.join(outdir, "messages_timeline.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "message_id", "datetime_mdt", "date", "time", "hour_24",
            "minute", "hour_decimal", "day_of_week", "sender",
            "is_system", "message_length", "message"
        ])
        for i, m in enumerate(messages):
            dt = m["datetime"]
            hour_decimal = round(dt.hour + dt.minute / 60 + dt.second / 3600, 3)
            writer.writerow([
                i, dt.isoformat(sep=" "), dt.date().isoformat(),
                dt.time().isoformat(), dt.hour, dt.minute, hour_decimal,
                dt.strftime("%A"), m["sender"], m["is_system"],
                len(m["message"]), m["message"].replace("\n", " ")
            ])
    return path


def export_hourly_distribution(messages, outdir):
    """
    Build a pivot-style table: rows = hour of day (0-23), columns = each
    sender, values = message count in that hour. Feed this straight into
    a line or bar chart to visually compare posting patterns across users.
    """
    senders = sorted({m["sender"] for m in messages})
    counts = {hour: Counter() for hour in range(24)}
    for m in messages:
        counts[m["datetime"].hour][m["sender"]] += 1

    path = os.path.join(outdir, "hourly_distribution_by_user.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["hour_24"] + senders)
        for hour in range(24):
            writer.writerow([hour] + [counts[hour].get(s, 0) for s in senders])
    return path


# ---------------------------------------------------------------------------
# Analysis 2: Message chains / burst detection (bot-timing suspicion)
# ---------------------------------------------------------------------------

def compute_gaps_per_sender(messages):
    """
    For each sender, compute the time gap (in seconds) between each of
    their own consecutive messages. A sender whose gaps cluster tightly
    around a fixed value (low stdev relative to the mean) is behaving in
    a mechanically regular way -- a useful bot-suspicion signal.
    """
    by_sender = defaultdict(list)
    for i, m in enumerate(messages):
        by_sender[m["sender"]].append((i, m["datetime"]))

    gap_rows = []
    for sender, items in by_sender.items():
        items.sort(key=lambda x: x[1])
        for j in range(1, len(items)):
            prev_idx, prev_time = items[j - 1]
            cur_idx, cur_time = items[j]
            gap = (cur_time - prev_time).total_seconds()
            gap_rows.append({
                "sender": sender,
                "message_index": cur_idx,
                "prev_time": prev_time,
                "current_time": cur_time,
                "gap_seconds": gap,
            })
    return gap_rows


def export_sender_gaps(gap_rows, outdir):
    """Write the raw per-message gap data (one row per consecutive pair, per sender)."""
    path = os.path.join(outdir, "sender_message_gaps.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sender", "message_index", "prev_time", "current_time", "gap_seconds"])
        for row in gap_rows:
            writer.writerow([
                row["sender"], row["message_index"],
                row["prev_time"].isoformat(sep=" "),
                row["current_time"].isoformat(sep=" "),
                round(row["gap_seconds"], 2),
            ])
    return path


def export_sender_gap_stats(gap_rows, outdir):
    """
    Summarize gap regularity per sender: mean/median/stdev/min/max, plus a
    "regularity_ratio" (stdev / mean). The lower this ratio, the more
    mechanically consistent that sender's posting interval is -- flag low
    ratios as candidates for scripted/bot accounts.
    """
    by_sender = defaultdict(list)
    for row in gap_rows:
        by_sender[row["sender"]].append(row["gap_seconds"])

    path = os.path.join(outdir, "sender_gap_stats.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "sender", "num_gaps", "mean_gap_sec", "median_gap_sec",
            "stdev_gap_sec", "min_gap_sec", "max_gap_sec", "regularity_ratio"
        ])
        for sender, gaps in by_sender.items():
            mean_g = statistics.mean(gaps)
            median_g = statistics.median(gaps)
            stdev_g = statistics.stdev(gaps) if len(gaps) > 1 else 0.0
            ratio = round(stdev_g / mean_g, 4) if mean_g > 0 else 0.0
            writer.writerow([
                sender, len(gaps), round(mean_g, 2), round(median_g, 2),
                round(stdev_g, 2), round(min(gaps), 2), round(max(gaps), 2),
                ratio
            ])
    return path


def detect_chains(messages, gap_threshold_seconds=60):
    """
    Group consecutive messages (across all senders, in chronological order)
    into "chains"/bursts: a message continues the current chain if it
    arrives within `gap_threshold_seconds` of the previous one; otherwise a
    new chain starts. Useful for spotting synchronized bursts of activity
    (e.g. several bot accounts firing off scripted lines back-to-back)
    followed by quiet periods.
    """
    if not messages:
        return []
    ordered = sorted(messages, key=lambda m: m["datetime"])
    chains = []
    current_chain = [ordered[0]]

    for prev, cur in zip(ordered, ordered[1:]):
        gap = (cur["datetime"] - prev["datetime"]).total_seconds()
        if gap <= gap_threshold_seconds:
            current_chain.append(cur)
        else:
            chains.append(current_chain)
            current_chain = [cur]
    chains.append(current_chain)
    return chains


def export_chains(chains, outdir):
    """Write one summary row per detected chain/burst of messages."""
    path = os.path.join(outdir, "message_chains.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "chain_id", "start_time", "end_time", "duration_seconds",
            "num_messages", "num_unique_senders", "senders", "avg_gap_seconds"
        ])
        for i, chain in enumerate(chains):
            start = chain[0]["datetime"]
            end = chain[-1]["datetime"]
            duration = (end - start).total_seconds()
            senders = sorted({m["sender"] for m in chain})
            if len(chain) > 1:
                gaps = [
                    (b["datetime"] - a["datetime"]).total_seconds()
                    for a, b in zip(chain, chain[1:])
                ]
                avg_gap = round(sum(gaps) / len(gaps), 2)
            else:
                avg_gap = 0.0
            writer.writerow([
                i, start.isoformat(sep=" "), end.isoformat(sep=" "),
                round(duration, 2), len(chain), len(senders),
                "; ".join(senders), avg_gap
            ])
    return path


# ---------------------------------------------------------------------------
# Analysis 3: Per-user keyword frequency
# ---------------------------------------------------------------------------

def tokenize(text):
    """Lowercase and split text into word tokens, dropping punctuation."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return [w.strip("'") for w in words if w.strip("'")]


def safe_filename(name):
    """Turn a sender name/phone number into a filesystem-safe filename."""
    cleaned = re.sub(r"[^\w\-]+", "_", name).strip("_")
    return cleaned or "unknown_sender"


def export_keywords_per_user(messages, outdir, top_n=200, exclude_system=True):
    """
    For each sender, count word frequency across all their messages
    (minus stopwords) and write it to its own CSV file, so keyword
    popularity can be compared or charted per person.
    """
    keyword_dir = os.path.join(outdir, "keywords_by_user")
    os.makedirs(keyword_dir, exist_ok=True)

    by_sender = defaultdict(Counter)
    for m in messages:
        if exclude_system and m["is_system"]:
            continue
        words = [w for w in tokenize(m["message"]) if w not in STOPWORDS and len(w) > 1]
        by_sender[m["sender"]].update(words)

    written_files = []
    for sender, counter in by_sender.items():
        filename = f"{safe_filename(sender)}_keywords.csv"
        path = os.path.join(keyword_dir, filename)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["keyword", "count"])
            for word, count in counter.most_common(top_n):
                writer.writerow([word, count])
        written_files.append(path)
    return written_files


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze an exported WhatsApp group chat .txt file."
    )
    parser.add_argument("filepath", help="Path to the WhatsApp chat export .txt file")
    parser.add_argument(
        "--outdir", default="whatsapp_analysis_output",
        help="Folder to write result files to (default: whatsapp_analysis_output)"
    )
    parser.add_argument(
        "--chain-gap", type=int, default=60,
        help="Max seconds between messages to still count as the same chain/burst (default: 60)"
    )
    parser.add_argument(
        "--top-keywords", type=int, default=200,
        help="Max number of keywords to keep per user (default: 200)"
    )
    parser.add_argument(
        "--include-system", action="store_true",
        help="Include WhatsApp system/notification messages in the keyword analysis"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.filepath):
        sys.exit(f"File not found: {args.filepath}")

    os.makedirs(args.outdir, exist_ok=True)

    print(f"Reading {args.filepath} ...")
    lines = read_lines(args.filepath)

    print("Parsing messages ...")
    messages = parse_messages(lines)
    print(f"  Parsed {len(messages)} messages from {len({m['sender'] for m in messages})} senders")

    if not messages:
        sys.exit("No messages could be parsed -- check that the file matches the expected format.")

    # 1. Timing analysis
    print("Exporting per-message timeline ...")
    export_message_timeline(messages, args.outdir)
    print("Exporting hourly distribution by user ...")
    export_hourly_distribution(messages, args.outdir)

    # 2. Chain / burst detection
    print("Computing per-sender message gaps ...")
    gap_rows = compute_gaps_per_sender(messages)
    export_sender_gaps(gap_rows, args.outdir)
    export_sender_gap_stats(gap_rows, args.outdir)

    print(f"Detecting message chains (gap threshold: {args.chain_gap}s) ...")
    chains = detect_chains(messages, gap_threshold_seconds=args.chain_gap)
    export_chains(chains, args.outdir)
    print(f"  Found {len(chains)} chains/bursts")

    # 3. Keyword popularity per user
    print("Exporting keyword frequency per user ...")
    keyword_files = export_keywords_per_user(
        messages, args.outdir, top_n=args.top_keywords,
        exclude_system=not args.include_system
    )
    print(f"  Wrote {len(keyword_files)} per-user keyword files")

    print(f"\nDone. All results saved under: {os.path.abspath(args.outdir)}")


if __name__ == "__main__":
    main()
    