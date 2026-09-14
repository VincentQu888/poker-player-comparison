#!/usr/bin/env python3
"""Parse ACPC 2010 heads-up fixed-limit PHH logs into the repo hand schema."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from parse_phh import SCHEMA, iter_blocks, parse_list_num, parse_list_str

SOURCE = Path("data/raw/acpc_2010_2p_limit")
OUT_DIR = Path("data/acpc2010_limit_sample/hands")
P_TOKEN = re.compile(r"\bp([12])\b")


def remap_player_token(match: re.Match[str]) -> str:
    return "p1" if match.group(1) == "2" else "p2"


def remap_action(action: str) -> str:
    return P_TOKEN.sub(remap_player_token, action)


def parse_hand(block: dict[str, str], file_stem: str) -> dict | None:
    if block.get("variant", "").strip().strip("'\"") != "FT":
        return None
    players = parse_list_str(block.get("players", "[]"))
    results = parse_list_num(block.get("_results", "[]"))
    if len(players) != 2 or len(results) != 2:
        return None

    original_stacks = parse_list_num(block.get("starting_stacks", "[]")) or [2000.0, 2000.0]
    original_stacks = (original_stacks + [2000.0, 2000.0])[:2]

    # ACPC HU PHH order has p2 acting first preflop, i.e. p2 is SB/button and
    # p1 is BB. The repo replay assumes players[0]=SB and players[1]=BB, so
    # swap player-indexed fields and rewrite p1/p2 action tokens once here.
    players = [players[1], players[0]]
    stacks = [original_stacks[1], original_stacks[0]]
    results = [results[1], results[0]]
    finishing = [stacks[i] + results[i] for i in range(2)]
    actions = [remap_action(action) for action in parse_list_str(block.get("actions", "[]"))]
    big_blind = max(parse_list_num(block.get("blinds_or_straddles", "[]")) or [10.0])
    hand = block.get("hand", "").strip().strip("'\"")

    return {
        "site": "ACPC2010_LIMIT",
        "nl_level": int(big_blind * 100),
        "hand_id": f"{file_stem}/{hand}",
        "table": file_stem,
        "seat_count": 2,
        "n_players": 2,
        "players": players,
        "blinds": [big_blind / 2, big_blind],
        "starting_stacks": stacks,
        "finishing_stacks": finishing,
        "winnings": [],
        "actions": actions,
        "year": 2010,
        "month": 1,
        "day": 1,
        "time": "",
    }


def flush(rows: list[dict], out_dir: Path, part: int) -> None:
    if not rows:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    columns = {name: [row[name] for row in rows] for name in SCHEMA.names}
    pq.write_table(pa.table(columns, schema=SCHEMA), out_dir / f"part-{part:04d}.parquet", compression="zstd")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--limit-files", type=int, default=10)
    parser.add_argument("--sample-files", type=int, default=0, help="evenly sample N files across the source")
    parser.add_argument("--max-hands", type=int, default=0)
    parser.add_argument("--part-size", type=int, default=100_000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sample = next(args.source.glob("*.phhs"))
        row = parse_hand(next(iter_blocks(str(sample))), sample.stem)
        assert row is not None
        assert row["players"] == ["ASVP", "Arnold2"]
        assert row["blinds"] == [5.0, 10.0]
        assert row["finishing_stacks"] == [1940.0, 2060.0]
        assert row["actions"][:3] == ["d dh p2 Kd4c", "d dh p1 Ts6d", "p1 cc"]
        print("ok")
        return

    files = sorted(args.source.rglob("*.phhs"))
    if args.sample_files:
        step = max(1, len(files) // args.sample_files)
        files = files[::step][: args.sample_files]
    elif args.limit_files:
        files = files[: args.limit_files]
    rows: list[dict] = []
    total = 0
    part = 0
    for file_index, path in enumerate(files, 1):
        for block in iter_blocks(str(path)):
            row = parse_hand(block, path.relative_to(args.source).with_suffix("").as_posix())
            if not row:
                continue
            rows.append(row)
            total += 1
            if len(rows) >= args.part_size:
                flush(rows, args.out_dir, part)
                rows = []
                part += 1
            if args.max_hands and total >= args.max_hands:
                break
        if file_index % 500 == 0:
            print(f"parsed {file_index}/{len(files)} files, {total} hands", flush=True)
        if args.max_hands and total >= args.max_hands:
            break
    flush(rows, args.out_dir, part)
    print(f"wrote {total} ACPC 2010 limit hands to {args.out_dir}")


if __name__ == "__main__":
    main()
