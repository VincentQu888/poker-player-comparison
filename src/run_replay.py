#!/usr/bin/env python3
"""Stage 2 runner: replay all hands -> decisions + hand_player parquet.

Memory-safe: streams each shard in row-group batches (never materializes a full
2M-hand shard as Python objects) and flushes accumulated output every
FLUSH_HANDS hands. Resumable: writes a `.done` marker per shard and skips shards
already completed; a shard that was only partially written is cleaned and redone.
"""
import os, sys, glob, argparse
import pyarrow as pa
import pyarrow.parquet as pq
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from replay import replay_hand

HANDS = os.path.join(os.path.dirname(__file__), "..", "data", "hands")
DEC = os.path.join(os.path.dirname(__file__), "..", "data", "decisions")
HP = os.path.join(os.path.dirname(__file__), "..", "data", "hand_player")

DEC_SCHEMA = pa.schema([
    ("site", pa.string()), ("nl_level", pa.int32()), ("hand_id", pa.string()),
    ("player", pa.string()), ("pos_idx", pa.int8()), ("pos_label", pa.string()),
    ("seat_count", pa.int8()), ("n_players", pa.int8()),
    ("street", pa.int8()), ("board", pa.string()),
    ("pot_before_bb", pa.float32()), ("to_call_bb", pa.float32()),
    ("hero_stack_before_bb", pa.float32()), ("spr", pa.float32()),
    ("action_faced", pa.string()), ("prev_wager_frac", pa.float32()),
    ("pot_type", pa.string()), ("n_active_before", pa.int8()),
    ("n_to_act_after", pa.int8()), ("year", pa.int16()), ("month", pa.int8()),
    ("day", pa.int8()), ("committed_before_bb", pa.float32()),
    ("act", pa.string()), ("act_to_bb", pa.float32()), ("act_frac", pa.float32()),
    ("hand_net_bb", pa.float32()), ("reward_bb", pa.float32()),
    ("net_source", pa.string()),
])
HP_SCHEMA = pa.schema([
    ("site", pa.string()), ("nl_level", pa.int32()), ("hand_id", pa.string()),
    ("player", pa.string()), ("pos_idx", pa.int8()), ("n_players", pa.int8()),
    ("invested_bb", pa.float32()), ("net_bb", pa.float32()),
    ("net_source", pa.string()), ("reached_showdown", pa.bool_()),
    ("saw_hole", pa.bool_()), ("hole", pa.string()), ("vpip", pa.bool_()),
    ("year", pa.int16()), ("month", pa.int8()), ("day", pa.int8()),
])

FLUSH_HANDS = 50000    # flush accumulated output every N hands (bounds worker RAM)
BATCH = 10000          # parquet read batch size (bounds input RAM)


def _done_path(idx):
    return os.path.join(DEC, f"part-{idx:04d}.done")


def process_shard(args):
    idx, path = args
    os.makedirs(DEC, exist_ok=True)
    os.makedirs(HP, exist_ok=True)
    # resume: skip if already completed
    if os.path.exists(_done_path(idx)):
        return idx, -1, -1
    # clean any partial chunks from a prior aborted run
    for p in glob.glob(os.path.join(DEC, f"part-{idx:04d}-*.parquet")):
        os.remove(p)
    for p in glob.glob(os.path.join(HP, f"part-{idx:04d}-*.parquet")):
        os.remove(p)

    pf = pq.ParquetFile(path)
    dec_cols = {f.name: [] for f in DEC_SCHEMA}
    hp_cols = {f.name: [] for f in HP_SCHEMA}
    tot_d = tot_h = 0
    sub = 0
    pending = 0

    def flush():
        nonlocal dec_cols, hp_cols, sub, tot_d, tot_h, pending
        if not dec_cols["hand_id"] and not hp_cols["hand_id"]:
            return
        pq.write_table(pa.table(dec_cols, schema=DEC_SCHEMA),
                       os.path.join(DEC, f"part-{idx:04d}-{sub:03d}.parquet"),
                       compression="zstd")
        pq.write_table(pa.table(hp_cols, schema=HP_SCHEMA),
                       os.path.join(HP, f"part-{idx:04d}-{sub:03d}.parquet"),
                       compression="zstd")
        tot_d += len(dec_cols["hand_id"]); tot_h += len(hp_cols["hand_id"])
        dec_cols = {f.name: [] for f in DEC_SCHEMA}
        hp_cols = {f.name: [] for f in HP_SCHEMA}
        sub += 1
        pending = 0

    dnames = DEC_SCHEMA.names
    hnames = HP_SCHEMA.names
    for batch in pf.iter_batches(batch_size=BATCH):
        cols = batch.to_pydict()
        keys = list(cols.keys())
        m = len(cols["hand_id"])
        for r in range(m):
            row = {k: cols[k][r] for k in keys}
            decs, hps = replay_hand(row)
            for d in decs:
                for f in dnames:
                    dec_cols[f].append(d.get(f))
            for h in hps:
                for f in hnames:
                    hp_cols[f].append(h.get(f))
            pending += 1
            if pending >= FLUSH_HANDS:
                flush()
    flush()
    # mark shard complete
    with open(_done_path(idx), "w") as fh:
        fh.write(f"{tot_d} {tot_h}\n")
    return idx, tot_d, tot_h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process only N shards (0=all)")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    shards = sorted(glob.glob(os.path.join(HANDS, "*.parquet")))
    if a.limit:
        shards = shards[:a.limit]
    args = [(i, p) for i, p in enumerate(shards)]
    tot_d = tot_h = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for idx, nd, nh in ex.map(process_shard, args):
            if nd < 0:
                print(f"  shard {idx}: already done (skipped)", flush=True)
                continue
            tot_d += nd; tot_h += nh
            print(f"  shard {idx}: {nd} decisions, {nh} hand-players", flush=True)
    print(f"NEW-this-run decisions={tot_d}  hand_players={tot_h}", flush=True)


if __name__ == "__main__":
    main()
