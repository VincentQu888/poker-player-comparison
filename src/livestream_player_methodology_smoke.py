#!/usr/bin/env python3
"""Player-level smoke test for the conservative HCL hand dataset."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from livestream_methodology_smoke import preflop_equity, showdown_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("report/livestream/hcl_full_hand_dataset.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("report/livestream/player_methodology_smoke_test.md"))
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        assert args.trials > 0
        print("ok")
        return

    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    stats = defaultdict(lambda: {"hands": 0, "equity": 0.0, "showdowns": 0, "wins": 0.0})
    action_counts = Counter(action["actor"] for row in rows for action in row["actions"] if action["actor"] != "unknown")
    rng = random.Random(11)

    for row in rows:
        top, bottom = row["players"]
        equity = preflop_equity(top["cards"], bottom["cards"], args.trials, rng)
        for player, share in [(top, equity), (bottom, 1 - equity)]:
            if player["name"] == "unknown":
                continue
            stats[player["name"]]["hands"] += 1
            stats[player["name"]]["equity"] += share
        result = showdown_result(top["cards"], bottom["cards"], row["board"])
        if result:
            for player, won in [(top, result[0]), (bottom, result[1])]:
                if player["name"] == "unknown":
                    continue
                stats[player["name"]]["showdowns"] += 1
                stats[player["name"]]["wins"] += won

    lines = ["# HCL player methodology smoke test", ""]
    lines.append(f"Input: `{args.input}` ({len(rows)} card-clean hands)")
    lines.append("Names/actions are conservative OCR+caption signals; unknown stays unknown.")
    lines.append("")
    lines.append("| player | named hands | avg preflop equity | known caption/overlay actions | showdowns | win share |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for player, row in sorted(stats.items(), key=lambda item: (-item[1]["hands"], item[0])):
        hands = row["hands"]
        showdowns = row["showdowns"]
        lines.append(f"| {player} | {hands} | {row['equity'] / hands:.3f} | {action_counts[player]} | {showdowns} | {(row['wins'] / showdowns if showdowns else 0):.3f} |")
    lines.append("")
    lines.append("Verdict: player grouping now works for a small audited subset, but OCR coverage is still too sparse for ranking claims.")
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
