#!/usr/bin/env python3
"""Tiny card-aware smoke test on extracted livestream hands.

This is not the full player model: names/actions/results are not reliable yet.
It checks whether extracted hole cards + boards can drive a comparison surface.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import eval7


FULL_DECK = [str(card) for card in eval7.Deck()]


def cards(values: list[str]) -> list[eval7.Card]:
    return [eval7.Card(value) for value in values]


def preflop_equity(hero: list[str], villain: list[str], trials: int, rng: random.Random) -> float:
    dead = set(hero + villain)
    deck = [card for card in FULL_DECK if card not in dead]
    score = 0.0
    for _ in range(trials):
        board = rng.sample(deck, 5)
        hero_value = eval7.evaluate(cards(hero + board))
        villain_value = eval7.evaluate(cards(villain + board))
        score += 1.0 if hero_value > villain_value else 0.5 if hero_value == villain_value else 0.0
    return score / trials


def showdown_result(top: list[str], bottom: list[str], board: list[str]) -> tuple[float, float] | None:
    if len(board) != 5:
        return None
    top_value = eval7.evaluate(cards(top + board))
    bottom_value = eval7.evaluate(cards(bottom + board))
    if top_value == bottom_value:
        return 0.5, 0.5
    return (1.0, 0.0) if top_value > bottom_value else (0.0, 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("report/livestream/hcl_methodology_sample.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("report/livestream/methodology_smoke_test.md"))
    parser.add_argument("--trials", type=int, default=500)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        assert preflop_equity(["As", "Ac"], ["7d", "2c"], 50, random.Random(1)) > 0.75
        assert showdown_result(["As", "Ac"], ["7d", "2c"], ["Ah", "Ad", "3s", "4s", "5s"]) == (1.0, 0.0)
        print("ok")
        return

    hands = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    stats = defaultdict(lambda: {"hands": 0, "equity": 0.0, "showdowns": 0, "wins": 0.0})
    rng = random.Random(7)

    for hand in hands:
        top = hand["players"][0]["cards"]
        bottom = hand["players"][1]["cards"]
        top_equity = preflop_equity(top, bottom, args.trials, rng)
        for seat, equity in [("top_seat", top_equity), ("bottom_seat", 1 - top_equity)]:
            stats[seat]["hands"] += 1
            stats[seat]["equity"] += equity
        result = showdown_result(top, bottom, hand["board"])
        if result:
            for seat, won in [("top_seat", result[0]), ("bottom_seat", result[1])]:
                stats[seat]["showdowns"] += 1
                stats[seat]["wins"] += won

    lines = ["# Livestream methodology smoke test", ""]
    lines.append(f"Input: `{args.input}` ({len(hands)} clean extracted records)")
    lines.append(f"Preflop equity: Monte Carlo, {args.trials} boards per hand")
    lines.append("")
    lines.append("| bucket | hands | avg preflop equity | 5-card-board showdowns | showdown win share |")
    lines.append("|---|---:|---:|---:|---:|")
    for seat in ["top_seat", "bottom_seat"]:
        row = stats[seat]
        avg_equity = row["equity"] / row["hands"] if row["hands"] else 0
        win_share = row["wins"] / row["showdowns"] if row["showdowns"] else 0
        lines.append(f"| {seat} | {row['hands']} | {avg_equity:.3f} | {row['showdowns']} | {win_share:.3f} |")
    lines.append("")
    lines.append("Verdict: the card-state comparison plumbing works, but this dataset is not yet a real player-ranking input because player names, actions, and hand results are still missing/weak.")
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
