#!/usr/bin/env python3
"""Check whether ACPC 2010 2P LIMIT winnings are stable enough as labels."""
from __future__ import annotations

import argparse
import ast
import hashlib
import math
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path("data/raw/acpc_2010_2p_limit")
OUT = Path("report/acpc_2010_2p_limit_reliability.md")
BB_CHIPS = 10.0


def split_for(file_name: str, hand: str) -> int:
    digest = hashlib.blake2b(f"{file_name}:{hand}".encode(), digest_size=1).digest()[0]
    return digest % 2


def add(stats: dict[tuple[str, ...], list[float]], key: tuple[str, ...], value: float) -> None:
    row = stats[key]
    row[0] += 1
    row[1] += value
    row[2] += value * value


def parse_file(path: Path) -> dict[tuple[str, ...], list[float]]:
    stats: dict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    players: list[str] | None = None
    results: list[float] | None = None
    hand = ""

    def flush() -> None:
        if not players or not results or len(players) != 2 or len(results) != 2:
            return
        split = str(split_for(path.name, hand))
        values = [result / BB_CHIPS for result in results]
        for i, player in enumerate(players):
            opponent = players[1 - i]
            value = values[i]
            add(stats, ("player", player, split), value)
            add(stats, ("pair", player, opponent, split), value)

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("["):
                flush()
                players = None
                results = None
                hand = ""
                continue
            if line.startswith("hand = "):
                hand = line.split("=", 1)[1].strip()
            elif line.startswith("players = "):
                players = ast.literal_eval(line.split("=", 1)[1].strip())
            elif line.startswith("_results = "):
                results = ast.literal_eval(line.split("=", 1)[1].strip())
    flush()
    return dict(stats)


def merge(all_stats: list[dict[tuple[str, ...], list[float]]]) -> dict[tuple[str, ...], list[float]]:
    total: dict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for stats in all_stats:
        for key, row in stats.items():
            acc = total[key]
            acc[0] += row[0]
            acc[1] += row[1]
            acc[2] += row[2]
    return total


def to_rows(stats: dict[tuple[str, ...], list[float]], kind: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, (n, sum_x, sum_x2) in stats.items():
        if key[0] != kind:
            continue
        mean = sum_x / n
        var = max(0.0, (sum_x2 - (sum_x * sum_x / n)) / (n - 1)) if n > 1 else 0.0
        se_bb100 = math.sqrt(var) * 100 / math.sqrt(n) if n > 0 else float("nan")
        if kind == "player":
            _, player, split = key
            rows.append({"player": player, "split": int(split), "hands": int(n), "bb100": mean * 100, "se_bb100": se_bb100})
        else:
            _, player, opponent, split = key
            rows.append({"player": player, "opponent": opponent, "split": int(split), "hands": int(n), "bb100": mean * 100, "se_bb100": se_bb100})
    return rows


def spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank().corr(b.rank()))


def split_summary(df: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, float, float]:
    wide = df.pivot(index=keys, columns="split", values="bb100").reset_index()
    wide = wide.rename(columns={0: "half0", 1: "half1"})
    return wide, float(wide.half0.corr(wide.half1)), spearman(wide.half0, wide.half1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    files = sorted(args.root.rglob("*.phhs"))
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        stats = merge(ex.map(parse_file, files, chunksize=50))

    player = pd.DataFrame(to_rows(stats, "player"))
    pair = pd.DataFrame(to_rows(stats, "pair"))
    player_wide, player_p, player_s = split_summary(player, ["player"])
    pair_wide, pair_p, pair_s = split_summary(pair, ["player", "opponent"])
    overall = pair.groupby(["player", "opponent"], as_index=False).agg(hands=("hands", "sum"), bb100=("bb100", "mean"))

    lines = ["# ACPC 2010 2P LIMIT reliability", ""]
    lines.append(f"Source files: `{args.root}`")
    lines.append(f"Files parsed: {len(files):,}")
    hand_player_entries = int(player.hands.sum())
    lines.append(f"Hands parsed: {hand_player_entries // 2:,}")
    lines.append(f"Hand-player entries: {hand_player_entries:,}")
    lines.append("")
    lines.append("## Split-half stability")
    lines.append(f"Overall player bb/100 split-half: Pearson {player_p:.3f}, Spearman {player_s:.3f}.")
    lines.append(f"Directed pairwise bb/100 split-half: Pearson {pair_p:.3f}, Spearman {pair_s:.3f}.")
    lines.append("")
    lines.append("## Overall player halves")
    lines.append(player_wide.sort_values("half0", ascending=False).to_markdown(index=False, floatfmt=".2f"))
    lines.append("")
    lines.append("## Pairwise summary sample")
    lines.append(overall.sort_values("hands", ascending=False).head(40).to_markdown(index=False, floatfmt=".2f"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")
    print(lines[5])
    print(lines[6])


if __name__ == "__main__":
    main()
