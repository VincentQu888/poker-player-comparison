#!/usr/bin/env python3
"""Keep only complete, physically possible livestream hand records."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def cards_for(hand: dict) -> list[str]:
    return [card for player in hand["players"] for card in player["cards"]] + hand["board"]


def is_clean(hand: dict) -> bool:
    cards = cards_for(hand)
    return hand.get("extraction_status") == "complete" and "unknown" not in cards and len(cards) == len(set(cards))


def flatten(hand: dict) -> dict[str, object]:
    return {
        "hand_id": hand["hand_id"],
        "review_url": hand["review_url"],
        "start_seconds": hand["start_seconds"],
        "end_seconds": hand["end_seconds"],
        "top_cards": " ".join(hand["players"][0]["cards"]),
        "bottom_cards": " ".join(hand["players"][1]["cards"]),
        "board": " ".join(hand["board"]),
        "pot": hand.get("pot"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("report/livestream/hcl_auto_hands.jsonl"))
    parser.add_argument("--out-jsonl", type=Path, default=Path("report/livestream/hcl_clean_hands.jsonl"))
    parser.add_argument("--out-csv", type=Path, default=Path("report/livestream/hcl_clean_hands.csv"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        assert is_clean({"extraction_status": "complete", "players": [{"cards": ["As", "Kd"]}, {"cards": ["2c", "3h"]}], "board": ["4s"]})
        assert not is_clean({"extraction_status": "complete", "players": [{"cards": ["As", "As"]}, {"cards": ["2c", "3h"]}], "board": []})
        assert not is_clean({"extraction_status": "low_confidence_cards", "players": [{"cards": ["As", "Kd"]}, {"cards": ["2c", "3h"]}], "board": []})
        print("ok")
        return

    hands = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    clean = [hand for hand in hands if is_clean(hand)]
    args.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.out_jsonl.open("w", encoding="utf-8") as f:
        for hand in clean:
            f.write(json.dumps(hand, ensure_ascii=False) + "\n")
    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        rows = [flatten(hand) for hand in clean]
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["hand_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"kept {len(clean)}/{len(hands)} clean hands")


if __name__ == "__main__":
    main()
