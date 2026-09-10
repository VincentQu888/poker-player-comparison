#!/usr/bin/env python3
"""Parse the PHH Pluribus dataset into this repo's hand parquet schema."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from parse_phh import SCHEMA, iter_blocks, parse_list_num, parse_list_str


def parse_hand(path: Path) -> dict | None:
    block = next(iter_blocks(str(path)), None)
    if not block or block.get("variant", "").strip().strip("'\"") != "NT":
        return None
    players = parse_list_str(block.get("players", "[]"))
    blinds = parse_list_num(block.get("blinds_or_straddles", "[]"))
    big_blind = max(blinds) if blinds else float(block.get("min_bet", "100"))
    hand = str(block.get("hand", path.stem)).strip().strip("'\"")
    return {
        "site": "PLURIBUS",
        "nl_level": int(big_blind * 100),
        "hand_id": f"{path.parent.name}/{hand}",
        "table": path.parent.name,
        "seat_count": len(players),
        "n_players": len(players),
        "players": players,
        "blinds": blinds,
        "starting_stacks": parse_list_num(block.get("starting_stacks", "[]")),
        "finishing_stacks": parse_list_num(block.get("finishing_stacks", "[]")),
        "winnings": parse_list_num(block.get("winnings", "[]")),
        "actions": parse_list_str(block.get("actions", "[]")),
        "year": 2019,
        "month": 7,
        "day": 11,
        "time": "",
    }


def natural_key(path: Path) -> tuple[str, int]:
    match = re.search(r"\d+", path.stem)
    return path.parent.name, int(match.group(0)) if match else -1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/raw/phh-dataset/data/pluribus"))
    parser.add_argument("--out", type=Path, default=Path("data/hands/part-0000.parquet"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sample = Path("data/raw/phh-dataset/data/pluribus/100/0.phh")
        if sample.exists():
            row = parse_hand(sample)
            assert row and row["players"][-1] == "Pluribus" and row["nl_level"] == 10000
        print("ok")
        return

    files = sorted(args.source.rglob("*.phh"), key=natural_key)
    rows = []
    for index, file in enumerate(files):
        row = parse_hand(file)
        if row:
            row = {**row, "day": 1 if index < len(files) // 2 else 2}
            rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    columns = {name: [row[name] for row in rows] for name in SCHEMA.names}
    pq.write_table(pa.table(columns, schema=SCHEMA), args.out, compression="zstd")
    print(f"wrote {len(rows)} Pluribus hands to {args.out}")


if __name__ == "__main__":
    main()
