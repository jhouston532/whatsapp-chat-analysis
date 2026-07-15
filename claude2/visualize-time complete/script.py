"""
visualize_chat.py
==================
Turn a parsed WhatsApp chat export into two diagnostic charts, saved as
PNGs:

1. Activity heatmap  (date x hour-of-day, one panel per top user)
   Shows *when* each person is active. Bots/scripted accounts often show
   up as suspiciously regular bands (same hour, every day); humans tend
   to look noisier and more clustered around normal waking hours.

2. Inter-message interval histogram (log-scaled seconds, per top user)
   Shows the gaps between a person's consecutive messages. A tight,
   spiky distribution (e.g. always ~50-60s apart) is a strong scripted-
   behavior signal; human timing is usually much more spread out.

This reads the ORIGINAL chat.txt export directly (not the bucketed
_timeline_*.csv files chat_to_csv.py produces) because the interval
histogram needs exact per-message timestamps, which get lost once
messages are binned into 30-minute counts.

Usage:
    python visualize_chat.py chat.txt
    python visualize_chat.py chat.txt --top 10 --output-dir charts/
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Reuse the exact same parsing logic as chat_to_csv.py so results stay
# consistent between the CSV pipeline and these charts.
from chat_to_csv import parse_chat


def top_users(rows, top_n: int) -> list[str]:
    totals: dict[str, int] = defaultdict(int)
    for ts, author, _ in rows:
        if ts is not None:
            totals[author] += 1
    ranked = sorted(totals, key=lambda u: totals[u], reverse=True)
    return ranked[:top_n]


def build_heatmap_data(rows, users: list[str]):
    """Return (dates, counts) where counts[user] is a (len(dates) x 24) matrix."""
    dates = sorted({ts.date() for ts, _, _ in rows if ts is not None})
    date_index = {d: i for i, d in enumerate(dates)}

    counts = {u: np.zeros((len(dates), 24), dtype=int) for u in users}
    for ts, author, _ in rows:
        if ts is None or author not in counts:
            continue
        counts[author][date_index[ts.date()], ts.hour] += 1

    return dates, counts


def plot_heatmap(rows, users: list[str], out_path: Path) -> None:
    dates, counts = build_heatmap_data(rows, users)
    if not dates or not users:
        print("Not enough timestamped data to build a heatmap.")
        return

    vmax = max(1, max(m.max() for m in counts.values()))

    n = len(users)
    fig, axes = plt.subplots(n, 1, figsize=(10, 1.1 * n + 1), squeeze=False, sharex=True)
    date_labels = [d.strftime("%m/%d") for d in dates]

    im = None
    for ax, user in zip(axes[:, 0], users):
        im = ax.imshow(counts[user], aspect="auto", cmap="YlOrRd", vmin=0, vmax=vmax)
        ax.set_yticks(range(len(dates)))
        ax.set_yticklabels(date_labels, fontsize=7)
        ax.set_ylabel(user, fontsize=8, rotation=0, ha="right", va="center")

    axes[-1, 0].set_xticks(range(0, 24, 2))
    axes[-1, 0].set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 2)], fontsize=8, rotation=45)
    axes[-1, 0].set_xlabel("Hour of day")

    fig.suptitle("Message activity by date and hour", fontsize=12)
    fig.colorbar(im, ax=axes[:, 0], label="Messages", fraction=0.03, pad=0.02)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote: {out_path}")


def plot_intervals(rows, users: list[str], out_path: Path) -> None:
    per_user_ts: dict[str, list] = defaultdict(list)
    for ts, author, _ in rows:
        if ts is not None and author in users:
            per_user_ts[author].append(ts)

    plotted_users = [u for u in users if len(per_user_ts.get(u, [])) >= 3]
    if not plotted_users:
        print("Not enough messages per user to build an interval histogram (need >= 3 each).")
        return

    n = len(plotted_users)
    cols = min(3, n)
    rows_grid = -(-n // cols)  # ceil division
    fig, axes = plt.subplots(rows_grid, cols, figsize=(4.5 * cols, 3.2 * rows_grid), squeeze=False)

    all_intervals = []
    for user in plotted_users:
        times = sorted(per_user_ts[user])
        diffs = [(t2 - t1).total_seconds() for t1, t2 in zip(times, times[1:])]
        diffs = [d for d in diffs if d > 0]
        all_intervals.append(diffs)

    max_seconds = max((max(d) for d in all_intervals if d), default=60)
    bins = np.logspace(0, np.log10(max(max_seconds, 10)), 30)

    for idx, (user, diffs) in enumerate(zip(plotted_users, all_intervals)):
        ax = axes[idx // cols, idx % cols]
        if diffs:
            ax.hist(diffs, bins=bins, color="steelblue", edgecolor="white")
        ax.set_xscale("log")
        ax.set_title(user, fontsize=9)
        ax.set_xlabel("Seconds between messages")
        ax.set_ylabel("Count")

    # Hide any unused subplot slots
    for idx in range(len(plotted_users), rows_grid * cols):
        axes[idx // cols, idx % cols].axis("off")

    fig.suptitle("Time between consecutive messages per user (log scale)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate activity heatmap and interval-histogram charts from a WhatsApp chat export.")
    parser.add_argument("chat_file", help="Path to the exported chat.txt file")
    parser.add_argument("--top", type=int, default=8, help="Number of most active participants to chart (default: 8)")
    parser.add_argument("--output-dir", default=".", help="Directory to write PNG charts to (default: current directory)")
    args = parser.parse_args()

    rows = parse_chat(args.chat_file)
    if not rows:
        print("No attributable messages found — check the file's timestamp/author format.")
        sys.exit(1)

    users = top_users(rows, args.top)
    if not users:
        print("No timestamped messages found — nothing to chart.")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(args.chat_file).stem

    plot_heatmap(rows, users, out_dir / f"{base}_heatmap.png")
    plot_intervals(rows, users, out_dir / f"{base}_intervals.png")


if __name__ == "__main__":
    main()
    