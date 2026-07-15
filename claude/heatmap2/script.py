#!/usr/bin/env python3
"""
chat_heatmap.py

Parses a WhatsApp group chat export (.txt) and renders a publication-quality
sender x time-bin activity heatmap image (PNG/PDF/SVG).

Color scale: black (0 messages) -> blue (low) -> light blue (high)
Layout: sender names on the right, day labels in large font across the top,
        hour labels in small font beneath the day labels, medium-grey
        background outside the heatmap itself.
Active hours: 09:00-21:00 by default (21:00-09:00 is skipped, since chat
        activity is typically flat/empty overnight).

Usage:
    python chat_heatmap.py chat.txt
    python chat_heatmap.py chat.txt -o heatmap.pdf --bin-minutes 60
    python chat_heatmap.py chat.txt --sort total --dpi 300
"""

import argparse
import re
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# ---------------------------------------------------------------------------
# Chat parsing (shared approach with the other chat-analysis scripts)
# ---------------------------------------------------------------------------

BIDI_CHARS = re.compile(
    "[\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c\u202f]"
)

MESSAGE_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2}\s?[APap][Mm])\]\s*"
    r"(?P<sender>[^:]+):\s?(?P<message>.*)$"
)

SYSTEM_MSG_MARKERS = (
    "Messages and calls are end-to-end encrypted",
    "created this group",
    "added you",
    "added ~",
    "changed the settings",
    "changed this group",
    "reset this group's invite link",
    "changed the group description",
    "<Media omitted>",
    "This message was deleted",
)


def clean_line(line: str) -> str:
    return BIDI_CHARS.sub(" ", line).strip()


def is_system_message(message: str) -> bool:
    return any(marker in message for marker in SYSTEM_MSG_MARKERS)


def parse_datetime(date_str: str, time_str: str):
    time_str = time_str.replace(" ", "")
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


def parse_chat(path: str):
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
                dt = parse_datetime(date_str, time_str)
                if dt is None:
                    if current is not None:
                        current["message"] += "\n" + line
                    continue
                current = {"dt": dt, "sender": sender.strip(), "message": message}
                entries.append(current)
            else:
                if current is not None:
                    current["message"] += "\n" + line
    return entries


# ---------------------------------------------------------------------------
# Binning
# ---------------------------------------------------------------------------

def floor_to_bin(dt: datetime, bin_minutes: int) -> datetime:
    minutes_since_midnight = dt.hour * 60 + dt.minute
    floored = (minutes_since_midnight // bin_minutes) * bin_minutes
    return dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=floored)


def is_active_hour(hour: int, start_hour: int, end_hour: int) -> bool:
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def build_activity_matrix(entries, bin_minutes, exclude_system,
                           start_hour, end_hour, sort_mode):
    if exclude_system:
        entries = [e for e in entries if not is_system_message(e["message"])]

    hour_filter_on = start_hour is not None and end_hour is not None
    if hour_filter_on:
        entries = [e for e in entries if is_active_hour(e["dt"].hour, start_hour, end_hour)]

    if not entries:
        return None, [], [], {}

    entries.sort(key=lambda e: e["dt"])
    first_bin = floor_to_bin(entries[0]["dt"], bin_minutes)
    last_bin = floor_to_bin(entries[-1]["dt"], bin_minutes)

    bins = []
    cursor = first_bin
    step = timedelta(minutes=bin_minutes)
    while cursor <= last_bin:
        if not hour_filter_on or is_active_hour(cursor.hour, start_hour, end_hour):
            bins.append(cursor)
        cursor += step

    counts = defaultdict(lambda: defaultdict(int))
    first_seen = {}
    for e in entries:
        sender = e["sender"]
        b = floor_to_bin(e["dt"], bin_minutes)
        if b in bins or not hour_filter_on:
            counts[sender][b] += 1
        if sender not in first_seen:
            first_seen[sender] = e["dt"]

    senders = list(counts.keys())
    if sort_mode == "alpha":
        senders.sort(key=str.lower)
    elif sort_mode == "total":
        senders.sort(key=lambda s: sum(counts[s].values()), reverse=True)
    else:  # first-seen
        senders.sort(key=lambda s: first_seen[s])

    matrix = np.zeros((len(senders), len(bins)), dtype=int)
    for r, sender in enumerate(senders):
        for c, b in enumerate(bins):
            matrix[r, c] = counts[sender].get(b, 0)

    return matrix, senders, bins, first_seen


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def render_heatmap(matrix, senders, bins, out_path, dpi=300, vmax=None,
                    title=None):
    n_senders, n_bins = matrix.shape

    cmap = LinearSegmentedColormap.from_list(
        "black_blue_lightblue", ["black", "#0000CD", "#ADD8E6"], N=256
    )

    grey = "#808080"

    fig_width = max(8, n_bins * 0.35)
    fig_height = max(4, n_senders * 0.35 + 1.5)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor(grey)
    ax.set_facecolor(grey)

    vmax_val = vmax if vmax is not None else max(matrix.max(), 1)
    im = ax.imshow(
        matrix, aspect="auto", cmap=cmap, vmin=0, vmax=vmax_val,
        interpolation="nearest", origin="upper",
    )

    # --- Sender names on the right ---
    ax.set_yticks(range(n_senders))
    ax.set_yticklabels(senders, fontsize=9)
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.tick_params(axis="y", length=0)

    # --- Hour labels (small font) at the top ---
    ax.set_xticks(range(n_bins))
    ax.set_xticklabels(
        [b.strftime("%H:%M") for b in bins], fontsize=6, rotation=90
    )
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    ax.tick_params(axis="x", length=2, pad=2)

    # --- Day labels (large font), grouped above the hour labels ---
    day_spans = []  # (day_label, start_idx, end_idx)
    current_day = None
    start_idx = 0
    for i, b in enumerate(bins):
        day_str = b.strftime("%Y-%m-%d")
        if day_str != current_day:
            if current_day is not None:
                day_spans.append((current_day, start_idx, i - 1))
            current_day = day_str
            start_idx = i
    day_spans.append((current_day, start_idx, len(bins) - 1))

    trans = ax.get_xaxis_transform()  # x in data coords, y in axes fraction
    for day_str, s_idx, e_idx in day_spans:
        center = (s_idx + e_idx) / 2
        ax.text(
            center, 1.16, day_str, transform=trans,
            fontsize=15, fontweight="bold", ha="center", va="bottom",
            color="black",
        )
        # separator line between days
        if s_idx > 0:
            ax.axvline(s_idx - 0.5, color=grey, linewidth=1.5)

    # subtle gridlines between cells for readability
    ax.set_xticks(np.arange(-0.5, n_bins, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_senders, 1), minor=True)
    ax.grid(which="minor", color=grey, linewidth=0.5)
    ax.tick_params(which="minor", length=0)

    for spine in ax.spines.values():
        spine.set_visible(False)

    # --- Colorbar on the left (keeps sender names on the right clear) ---
    cbar = fig.colorbar(im, ax=ax, location="left", fraction=0.035, pad=0.08)
    cbar.set_label("Messages per bin", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    cbar.outline.set_visible(False)

    if title:
        fig.suptitle(title, fontsize=13, y=0.99, color="black")

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description="Render a publication-quality sender x time-bin heatmap from a WhatsApp export."
    )
    parser.add_argument("chat_file", help="Path to the exported WhatsApp .txt file")
    parser.add_argument(
        "-o", "--output", default="chat_heatmap.png",
        help="Output image path — extension controls format (.png, .pdf, .svg). "
        "Default: chat_heatmap.png",
    )
    parser.add_argument(
        "--bin-minutes", type=int, default=60,
        help="Size of each time bucket in minutes (default: 60)",
    )
    parser.add_argument(
        "--sort", choices=["first-seen", "total", "alpha"], default="first-seen",
        help="Order of sender rows (default: first-seen)",
    )
    parser.add_argument(
        "--include-system", action="store_true",
        help="Include WhatsApp system messages",
    )
    parser.add_argument(
        "--start-hour", type=int, default=9,
        help="First active hour to include (default: 9)",
    )
    parser.add_argument(
        "--end-hour", type=int, default=21,
        help="Hour active window ends at, exclusive (default: 21)",
    )
    parser.add_argument(
        "--no-hour-filter", action="store_true",
        help="Disable the active-hours filter and include all 24 hours",
    )
    parser.add_argument(
        "--dpi", type=int, default=300,
        help="Output resolution for raster formats (default: 300)",
    )
    parser.add_argument(
        "--vmax", type=int, default=None,
        help="Cap the color scale at this count instead of the data max "
        "(useful if one outlier bin washes out the rest of the scale)",
    )
    parser.add_argument(
        "--title", default=None,
        help="Optional figure title",
    )
    args = parser.parse_args()

    entries = parse_chat(args.chat_file)
    if not entries:
        print("No messages could be parsed from this file.")
        return

    start_hour = None if args.no_hour_filter else args.start_hour
    end_hour = None if args.no_hour_filter else args.end_hour

    matrix, senders, bins, first_seen = build_activity_matrix(
        entries, args.bin_minutes, exclude_system=not args.include_system,
        start_hour=start_hour, end_hour=end_hour, sort_mode=args.sort,
    )
    if matrix is None or matrix.size == 0:
        print("No messages left after filtering.")
        return

    render_heatmap(
        matrix, senders, bins, args.output,
        dpi=args.dpi, vmax=args.vmax, title=args.title,
    )

    print(f"Parsed {len(entries)} messages.")
    if start_hour is not None:
        print(f"Active hours filter: {start_hour:02d}:00 - {end_hour:02d}:00")
    print(f"{len(senders)} senders x {len(bins)} time bins written to {args.output}")


if __name__ == "__main__":
    main()