#!/usr/bin/env python3
"""
Stage 1 parser: PHH/HandHQ .phhs -> compact per-hand parquet.

Preserves everything needed downstream while re-encoding 15GB of text into a
much smaller binary form. One row per hand.

HandHQ NLHE cash format facts (verified against data):
  * variant 'NT' == No-limit Texas hold'em.
  * actions tokens:
        'd dh pN ????'   deal hole cards to player N (obfuscated)
        'd db <cards>'   deal board (flop=3 cards, turn=1, river=1)
        'pN f'           fold
        'pN cc'          check OR call (disambiguate via outstanding bet)
        'pN cbr X'       bet/raise TO total X (this street total wager)
        'pN sm <cards>'  showdown reveal (or 'sm ????' when mucked/unknown)
  * players[] and seats[] are index aligned; pN maps to players[N-1].
  * blinds_or_straddles[i] is the forced blind/straddle for players[i].
    Convention: index 0 = SB, 1 = BB, 2.. = UTG.. , last = BTN (button).
    (Verified: blinds act last preflop; earliest index acts first postflop.)
  * hole cards stripped except at showdown for players who choose to show.
"""
import os, sys, glob, re, io
import pyarrow as pa
import pyarrow.parquet as pq
from concurrent.futures import ProcessPoolExecutor

TOK = re.compile(r"'([^']*)'|\"([^\"]*)\"")
ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "phh-dataset-src", "data", "handhq")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "hands")

SITE_MAP = {"ABS": "ABS", "FTP": "FTP", "IPN": "IPN", "ONG": "ONG", "PS": "PS", "PTY": "PTY"}

SCHEMA = pa.schema([
    ("site", pa.string()), ("nl_level", pa.int32()), ("hand_id", pa.string()),
    ("table", pa.string()), ("seat_count", pa.int32()), ("n_players", pa.int32()),
    ("players", pa.list_(pa.string())), ("blinds", pa.list_(pa.float64())),
    ("starting_stacks", pa.list_(pa.float64())),
    ("finishing_stacks", pa.list_(pa.float64())),
    ("winnings", pa.list_(pa.float64())), ("actions", pa.list_(pa.string())),
    ("year", pa.int32()), ("month", pa.int32()), ("day", pa.int32()),
    ("time", pa.string()),
])


def parse_list_str(v):
    """Parse a TOML-ish list of quoted strings: ['a','b'] -> [a,b]."""
    l = v.find("[")
    r = v.rfind("]")
    if l < 0 or r < 0:
        return []
    inside = v[l + 1:r]
    return [a or b for a, b in TOK.findall(inside)]


def parse_list_num(v):
    l = v.find("[")
    r = v.rfind("]")
    if l < 0 or r < 0:
        return []
    inside = v[l + 1:r]
    out = []
    for x in inside.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(float(x))
        except ValueError:
            out.append(0.0)
    return out


def iter_blocks(fp):
    block = {}
    with open(fp, errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("["):
                if block:
                    yield block
                block = {}
            elif " = " in line:
                k, v = line.split(" = ", 1)
                block[k] = v
    if block:
        yield block


def level_from_path(fp):
    # e.g. PS-2009-07-01_2009-07-23_25NLH_OBFU
    m = re.search(r"_(\d+)NLH_OBFU", fp)
    return int(m.group(1)) if m else -1


def site_from_path(fp):
    base = os.path.basename(os.path.dirname(os.path.dirname(fp)))  # the *_OBFU dir
    pre = base.split("-")[0]
    return SITE_MAP.get(pre, pre)


def process_file(fp):
    site = site_from_path(fp)
    level = level_from_path(fp)
    rows = {k: [] for k in (
        "site", "nl_level", "hand_id", "table", "seat_count", "n_players",
        "players", "blinds", "starting_stacks", "finishing_stacks", "winnings",
        "actions", "year", "month", "day", "time")}
    for b in iter_blocks(fp):
        if b.get("variant", "").strip().strip("'\"") != "NT":
            continue
        players = parse_list_str(b.get("players", "[]"))
        actions = parse_list_str(b.get("actions", "[]"))
        blinds = parse_list_num(b.get("blinds_or_straddles", "[]"))
        stacks = parse_list_num(b.get("starting_stacks", "[]"))
        finishing = parse_list_num(b.get("finishing_stacks", "[]"))
        winnings = parse_list_num(b.get("winnings", "[]"))
        rows["site"].append(site)
        rows["nl_level"].append(level)
        rows["hand_id"].append(b.get("hand", "").strip().strip("'\""))
        rows["table"].append(b.get("table", "").strip().strip("'\""))
        try:
            rows["seat_count"].append(int(float(b.get("seat_count", "0"))))
        except ValueError:
            rows["seat_count"].append(0)
        rows["n_players"].append(len(players))
        rows["players"].append(players)
        rows["blinds"].append(blinds)
        rows["starting_stacks"].append(stacks)
        rows["finishing_stacks"].append(finishing)
        rows["winnings"].append(winnings)
        rows["actions"].append(actions)
        for f in ("year", "month", "day"):
            try:
                rows[f].append(int(float(b.get(f, "0"))))
            except ValueError:
                rows[f].append(0)
        rows["time"].append(b.get("time", "").strip())
    if not rows["hand_id"]:
        return None, 0
    table = pa.table(rows, schema=SCHEMA)
    return table, len(rows["hand_id"])


def worker(args):
    idx, files, outdir = args
    tables = []
    n = 0
    for fp in files:
        t, c = process_file(fp)
        if t is not None:
            tables.append(t)
            n += c
    if not tables:
        return idx, 0
    combined = pa.concat_tables(tables)
    os.makedirs(outdir, exist_ok=True)
    pq.write_table(combined, os.path.join(outdir, f"part-{idx:04d}.parquet"), compression="zstd")
    return idx, n


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "**", "*.phhs"), recursive=True))
    print(f"found {len(files)} .phhs files", flush=True)
    os.makedirs(OUT, exist_ok=True)
    # chunk files across workers; ~ balanced by count
    nworkers = 10
    chunks = [[] for _ in range(nworkers)]
    # sort by size desc for balance
    files_sz = sorted(files, key=lambda f: os.path.getsize(f), reverse=True)
    for i, f in enumerate(files_sz):
        chunks[i % nworkers].append(f)
    args = [(i, chunks[i], OUT) for i in range(nworkers)]
    total = 0
    with ProcessPoolExecutor(max_workers=nworkers) as ex:
        for idx, n in ex.map(worker, args):
            total += n
            print(f"  worker {idx} done: {n} hands", flush=True)
    print(f"TOTAL NLHE hands parsed: {total}", flush=True)


if __name__ == "__main__":
    main()
