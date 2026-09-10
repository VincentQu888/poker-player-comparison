#!/usr/bin/env python3
"""Parse ACPC converted PokerStars heads-up logs into this repo's hand schema."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from parse_phh import SCHEMA

HAND_RE = re.compile(r"PokerStars Hand #(\d+): .+\(\$(\d+(?:\.\d+)?)/\$(\d+(?:\.\d+)?) USD\)")
BUTTON_RE = re.compile(r"Seat #(\d+) is the button")
SEAT_RE = re.compile(r"Seat (\d+): (.+) \(\$(\d+(?:\.\d+)?) in chips\)")
SHOW_RE = re.compile(r"(.+): shows \[([2-9TJQKA][cdhs]) ([2-9TJQKA][cdhs])\]")
FLOP_RE = re.compile(r"\*\*\* FLOP \*\*\* \[([^\]]+)\]")
TURN_RIVER_RE = re.compile(r"\*\*\* (?:TURN|RIVER) \*\*\* \[[^\]]+\] \[([^\]]+)\]")


def cards(text: str) -> str:
    return "".join(text.split())


def parse_action(line: str, player_to_idx: dict[str, int]) -> str | None:
    for name, idx in player_to_idx.items():
        prefix = f"{name}: "
        if not line.startswith(prefix):
            continue
        action = line[len(prefix):]
        if action == "folds":
            return f"p{idx} f"
        if action == "checks":
            return f"p{idx} cc"
        if action.startswith("calls "):
            return f"p{idx} cc"
        match = re.search(r"raises \$\d+(?:\.\d+)? to \$(\d+(?:\.\d+)?)", action)
        if match:
            return f"p{idx} cbr {match.group(1)}"
        match = re.search(r"bets \$(\d+(?:\.\d+)?)", action)
        if match:
            return f"p{idx} cbr {match.group(1)}"
    return None


def parse_block(block: str, file_day: int) -> dict | None:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return None
    hand_match = HAND_RE.match(lines[0])
    if not hand_match:
        return None
    hand_id, sb, bb = hand_match.groups()
    button_seat = None
    seats: dict[int, tuple[str, float]] = {}
    shown: dict[str, str] = {}
    raw_actions: list[str] = []
    in_actions = False
    for line in lines[1:]:
        if "Seat #" in line and "button" in line:
            button_seat = int(BUTTON_RE.search(line).group(1))
            continue
        seat_match = SEAT_RE.match(line)
        if seat_match:
            seat, name, stack = seat_match.groups()
            seats[int(seat)] = (name, float(stack))
            continue
        show_match = SHOW_RE.match(line)
        if show_match:
            shown[show_match.group(1)] = cards(" ".join(show_match.groups()[1:]))
            continue
        if line == "*** HOLE CARDS ***":
            in_actions = True
            continue
        if line.startswith("*** SUMMARY ***"):
            in_actions = False
            continue
        if not in_actions:
            continue
        flop_match = FLOP_RE.match(line)
        if flop_match:
            raw_actions.append(f"d db {cards(flop_match.group(1))}")
            continue
        street_match = TURN_RIVER_RE.match(line)
        if street_match:
            raw_actions.append(f"d db {street_match.group(1)}")
            continue
        raw_actions.append(line)
    if button_seat is None or len(seats) != 2:
        return None
    sb_name, sb_stack = seats[button_seat]
    bb_seat = next(seat for seat in seats if seat != button_seat)
    bb_name, bb_stack = seats[bb_seat]
    players = [sb_name, bb_name]
    player_to_idx = {sb_name: 1, bb_name: 2}
    actions = [f"d dh p{i + 1} {shown.get(name, '????')}" for i, name in enumerate(players)]
    for line in raw_actions:
        if line.startswith("d db "):
            actions.append(line)
            continue
        parsed = parse_action(line, player_to_idx)
        if parsed:
            actions.append(parsed)
    return {
        "site": "ACPC2014",
        "nl_level": int(float(bb) * 100),
        "hand_id": hand_id,
        "table": "ACPC2014",
        "seat_count": 2,
        "n_players": 2,
        "players": players,
        "blinds": [float(sb), float(bb)],
        "starting_stacks": [sb_stack, bb_stack],
        "finishing_stacks": [],
        "winnings": [],
        "actions": actions,
        "year": 2014,
        "month": 8,
        "day": file_day,
        "time": "",
    }


def iter_blocks_from_zip(path: Path):
    with zipfile.ZipFile(path) as zf:
        names = sorted(name for name in zf.namelist() if name.endswith(".txt"))
        for day, name in enumerate(names, 1):
            text = zf.read(name).decode("utf-8", "replace")
            for block in re.split(r"\n\s*\n(?=PokerStars Hand #)", text):
                yield block, day


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"C:\Users\vince\Downloads\acpc_2014_nl_sample.zip"))
    parser.add_argument("--out", type=Path, default=Path("data/hands/part-0000.parquet"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    rows = []
    for block, day in iter_blocks_from_zip(args.source):
        row = parse_block(block, day)
        if row:
            rows.append(row)
            if args.limit and len(rows) >= args.limit:
                break
    if args.self_test:
        assert rows and rows[0]["players"] == ["Hyperborean_iro", "Prelude"]
        assert len(rows[0]["actions"]) >= 4 and rows[0]["actions"][0].startswith("d dh p1 ")
        assert rows[0]["actions"][2:] == ["p1 cbr 3", "p2 f"]
        print("ok")
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({name: [row[name] for row in rows] for name in SCHEMA.names}, schema=SCHEMA), args.out, compression="zstd")
    print(f"wrote {len(rows)} ACPC hands to {args.out}")


if __name__ == "__main__":
    main()
