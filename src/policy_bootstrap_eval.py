#!/usr/bin/env python3
"""Pairwise common-support policy evaluation from historical continuations.

This implements the PDF's Design A/C, not the toy full-hand simulator:
for each pair, evaluate both policies on the same common state distribution
using Q_pop(S,a)=historical continuation reward for that state/action.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


def rank_corr(x, y) -> float:
    if len(x) < 2:
        return float("nan")
    return float(pd.Series(x).rank().corr(pd.Series(y).rank()))


def state_expr(state: str) -> str:
    core = "street||'|'||pot_type||'|'||pos||'|'||action_faced||'|'||spr_b"
    states = {
        "s_core": core,
        "s_fine": f"{core}||'|'||faced_sz||'|'||nactive",
        "s_hole": f"{core}||'|H='||coalesce(hero_hole_class, '??')",
        "s_sim": f"{core}||'|H='||coalesce(hero_hole_class, '??')||'|M='||coalesce(hero_hand_bucket, 'unknown')",
        "s_pdf": f"{core}||'|'||faced_sz||'|'||nactive||'|H='||coalesce(hero_hole_class, '??')||'|M='||coalesce(hero_hand_bucket, 'unknown')||'|B='||coalesce(board_bucket, 'unknown')||'|behind='||n_to_act_after",
    }
    if state in states:
        return states[state]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", state):
        raise ValueError(f"unsafe state column: {state}")
    return f'"{state}"'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/analysis.duckdb"))
    ap.add_argument("--table", default="d")
    ap.add_argument("--state", default="s_sim")
    ap.add_argument("--nmin", type=int, default=10)
    ap.add_argument("--weight", choices=["population", "uniform"], default="population")
    ap.add_argument("--hand-player-glob", default="data/hand_player/*.parquet")
    args = ap.parse_args()

    con = duckdb.connect(str(args.db), read_only=True)
    state = state_expr(args.state)
    players = [r[0] for r in con.execute("SELECT DISTINCT player FROM d ORDER BY player").fetchall()]
    actual = {(p, o): bb100 for p, o, bb100 in con.execute("""
        WITH hp AS (SELECT * FROM read_parquet(?)), opp AS (
          SELECT a.player, b.player opponent, a.net_bb
          FROM hp a JOIN hp b ON a.hand_id=b.hand_id AND a.player<>b.player)
        SELECT player, opponent, avg(net_bb)*100 bb100 FROM opp GROUP BY 1,2
    """, [args.hand_player_glob]).fetchall()}

    con.execute(f"""
        CREATE TEMP TABLE q AS
        SELECT {state} s, a, avg(reward_bb) q, count(*) n
        FROM "{args.table}" WHERE reward_bb IS NOT NULL GROUP BY 1,2
    """)
    con.execute(f"""
        CREATE TEMP TABLE ps AS
        SELECT player, {state} s, count(*) n
        FROM "{args.table}" GROUP BY 1,2 HAVING count(*) >= {args.nmin}
    """)
    con.execute(f"""
        CREATE TEMP TABLE psa AS
        SELECT player, {state} s, a, count(*) n
        FROM "{args.table}" GROUP BY 1,2,3
    """)
    con.execute("""
        CREATE TEMP TABLE pi AS
        SELECT psa.player, psa.s, psa.a, psa.n * 1.0 / ps.n p
        FROM psa JOIN ps USING(player, s)
    """)
    weight_expr = "count(*) * 1.0" if args.weight == "population" else "1.0"
    con.execute(f"""
        CREATE TEMP TABLE sw AS
        SELECT {state} s, {weight_expr} w FROM "{args.table}" GROUP BY 1
    """)

    rows = []
    for a in players:
        for b in players:
            if a == b or (a, b) not in actual:
                continue
            df = con.execute("""
                WITH common AS (
                  SELECT pa.s FROM ps pa JOIN ps pb ON pa.s=pb.s
                  WHERE pa.player=? AND pb.player=?
                ), weights AS (
                  SELECT s, w / sum(w) OVER () w FROM sw JOIN common USING(s)
                ), ev AS (
                  SELECT pi.player, sum(weights.w * pi.p * q.q) * 100 bb100
                  FROM weights JOIN pi USING(s) JOIN q USING(s,a)
                  WHERE pi.player IN (?, ?) GROUP BY 1
                )
                SELECT player, bb100 FROM ev
            """, [a, b, a, b]).fetchdf()
            if len(df) != 2:
                continue
            ev = dict(zip(df.player, df.bb100))
            rows.append({"player": a, "opponent": b, "sim_bb100": ev[a] - ev[b], "actual_bb100": actual[(a, b)]})

    out = pd.DataFrame(rows)
    print(f"table={args.table} state={args.state} nmin={args.nmin} weight={args.weight} pairs={len(out)}")
    print(out.sort_values("sim_bb100", ascending=False).to_string(index=False, formatters={"sim_bb100":"{:.3f}".format, "actual_bb100":"{:.3f}".format}))
    print(f"pearson={out.sim_bb100.corr(out.actual_bb100):.3f} spearman={rank_corr(out.sim_bb100, out.actual_bb100):.3f}")


if __name__ == "__main__":
    main()
