#!/usr/bin/env python3
"""Fast empirical range-relative features.

Range approximation: observed hole/hand distribution in the same public context.
This is the smallest runnable version of the full method: H percentile, W strong
made-hand density, and D as range hand-strength dispersion/drawiness proxy.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/analysis.duckdb"))
    args = ap.parse_args()
    con = duckdb.connect(str(args.db))
    con.execute("""
    CREATE OR REPLACE MACRO handv(h) AS (
      CASE h
        WHEN 'straight_flush' THEN 8.0 WHEN 'quads' THEN 7.0 WHEN 'full_house' THEN 6.0
        WHEN 'flush' THEN 5.0 WHEN 'straight' THEN 4.0 WHEN 'trips' THEN 3.0
        WHEN 'two_pair' THEN 2.0 WHEN 'overpair_pair' THEN 1.2 WHEN 'pair' THEN 1.0
        WHEN 'flush_draw' THEN 0.4 WHEN 'high_card' THEN 0.0 ELSE 0.5 END);
    """)
    con.execute("""
    CREATE OR REPLACE MACRO isstrong(h) AS (
      h IN ('trips','straight','flush','full_house','quads','straight_flush'));
    """)
    con.execute("""
    CREATE OR REPLACE MACRO board_dyn(board_bucket, street) AS (
      CASE
        WHEN street = 3 THEN 0.0
        WHEN street = 0 THEN 0.0
        WHEN contains(board_bucket, 'm') THEN 0.35
        WHEN contains(board_bucket, 'c') THEN 0.25
        WHEN contains(board_bucket, 't') THEN 0.18
        ELSE 0.08 END);
    """)
    con.execute("""
    CREATE OR REPLACE TABLE rf_source AS
    SELECT *, street||'|'||pot_type||'|'||pos||'|'||action_faced||'|'||faced_sz||'|'||spr_b||'|'||nactive public_ctx,
           handv(hero_hand_bucket) hv
    FROM d WHERE hero_hole_class IS NOT NULL;
    """)
    con.execute("""
    CREATE OR REPLACE TABLE range_features AS
    WITH dist AS (
      SELECT public_ctx, board, hero_hole_class,
             avg(hv) hv, avg(isstrong(hero_hand_bucket)::int) strong_rate, count(*) n
      FROM rf_source GROUP BY 1,2,3
    ), ctx AS (
      SELECT public_ctx, board, sum(n) total_n, sum(strong_rate*n)/sum(n) wetness,
             stddev_pop(hv) / 8.0 dispersion
      FROM dist GROUP BY 1,2
    ), board_meta AS (
      SELECT public_ctx, board, any_value(board_bucket) board_bucket, any_value(street) street
      FROM rf_source GROUP BY 1,2
    ), pct AS (
      SELECT d.public_ctx, d.board, d.hero_hole_class, d.hv, c.wetness,
             coalesce(c.dispersion, 0) + board_dyn(m.board_bucket, m.street) dynamicness,
             sum(CASE WHEN o.hv <= d.hv THEN o.n ELSE 0 END) * 1.0 / max(c.total_n) h_pct
      FROM dist d JOIN dist o USING(public_ctx, board) JOIN ctx c USING(public_ctx, board)
      JOIN board_meta m USING(public_ctx, board)
      GROUP BY 1,2,3,4,5,6
    ), bins AS (
      SELECT quantile_cont(h_pct, 0.333) h1, quantile_cont(h_pct, 0.667) h2,
             quantile_cont(wetness, 0.333) w1, quantile_cont(wetness, 0.667) w2,
             quantile_cont(dynamicness, 0.333) d1, quantile_cont(dynamicness, 0.667) d2
      FROM pct
    )
    SELECT public_ctx, board, hero_hole_class, h_pct, wetness, dynamicness,
      CASE WHEN h_pct <= h1 THEN 'low' WHEN h_pct <= h2 THEN 'mid' ELSE 'high' END h_bin,
      CASE WHEN wetness <= w1 THEN 'low' WHEN wetness <= w2 THEN 'mid' ELSE 'high' END w_bin,
      CASE WHEN dynamicness <= d1 THEN 'low' WHEN dynamicness <= d2 THEN 'mid' ELSE 'high' END d_bin
    FROM pct CROSS JOIN bins;
    """)
    con.execute("""
    CREATE OR REPLACE TABLE d_range AS
    SELECT d.*, f.h_pct, f.wetness, f.dynamicness, f.h_bin, f.w_bin, f.d_bin,
      d.s_fine||'|Hq='||coalesce(f.h_bin,'mid')||'|W='||coalesce(f.w_bin,'mid')||'|D='||coalesce(f.d_bin,'mid') AS s_range
    FROM d LEFT JOIN range_features f
    ON d.street||'|'||d.pot_type||'|'||d.pos||'|'||d.action_faced||'|'||d.faced_sz||'|'||d.spr_b||'|'||d.nactive = f.public_ctx
    AND d.board = f.board AND d.hero_hole_class = f.hero_hole_class;
    """)
    n, corr = con.execute("SELECT count(*), corr(wetness,dynamicness) FROM range_features").fetchone()
    print(f"wrote range_features={n} d_range; corr(W,D)={corr:.3f}")


if __name__ == "__main__":
    main()
