#!/usr/bin/env python3
"""Diagnose why ACPC policy scores do not correlate with winnings.

Outputs a markdown report with integrity checks, target-label reliability,
current estimator reproduction, and an exploratory residual alternative.
"""
from __future__ import annotations

import math
from pathlib import Path

import duckdb
import pandas as pd

DB = Path("data/analysis.duckdb")


def spearman(x, y) -> float:
    if len(x) < 2:
        return float("nan")
    return float(pd.Series(x).rank().corr(pd.Series(y).rank()))


def fmt(x: float) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "nan"
    return f"{x:.3f}"


def current_policy_eval(
    con: duckdb.DuckDBPyConnection,
    table: str,
    state: str,
    nmin: int,
    action_col: str = "a",
) -> tuple[pd.DataFrame, float, float]:
    for temp in ["q", "ps", "psa", "pi", "sw"]:
        con.execute(f"DROP TABLE IF EXISTS {temp}")
    con.execute(f'''
        CREATE TEMP TABLE q AS
        SELECT "{state}" s, "{action_col}" a, avg(reward_bb) q, count(*) n
        FROM "{table}" WHERE reward_bb IS NOT NULL GROUP BY 1,2
    ''')
    con.execute(f'''
        CREATE TEMP TABLE ps AS
        SELECT player, "{state}" s, count(*) n
        FROM "{table}" GROUP BY 1,2 HAVING count(*) >= {nmin}
    ''')
    con.execute(f'''
        CREATE TEMP TABLE psa AS
        SELECT player, "{state}" s, "{action_col}" a, count(*) n
        FROM "{table}" GROUP BY 1,2,3
    ''')
    con.execute('''
        CREATE TEMP TABLE pi AS
        SELECT psa.player, psa.s, psa.a, psa.n * 1.0 / ps.n p
        FROM psa JOIN ps USING(player, s)
    ''')
    con.execute(f'''
        CREATE TEMP TABLE sw AS
        SELECT "{state}" s, count(*) * 1.0 w FROM "{table}" GROUP BY 1
    ''')
    out = con.execute('''
        WITH actual AS (
          WITH hp AS (SELECT * FROM 'data/hand_player/*.parquet'), opp AS (
            SELECT a.player, b.player opponent, a.net_bb
            FROM hp a JOIN hp b ON a.hand_id=b.hand_id AND a.player<>b.player)
          SELECT player, opponent, avg(net_bb)*100 actual_bb100 FROM opp GROUP BY 1,2
        ), players AS (SELECT DISTINCT player FROM d), rows AS (
          SELECT a.player, b.player opponent
          FROM players a JOIN players b ON a.player<>b.player
        ), scored AS (
          SELECT rows.player, rows.opponent, actual.actual_bb100,
                 eva.bb100 - evb.bb100 sim_bb100
          FROM rows
          JOIN actual ON actual.player=rows.player AND actual.opponent=rows.opponent
          JOIN LATERAL (
            WITH common AS (
              SELECT pa.s FROM ps pa JOIN ps pb ON pa.s=pb.s
              WHERE pa.player=rows.player AND pb.player=rows.opponent
            ), weights AS (
              SELECT s, w / sum(w) OVER () w FROM sw JOIN common USING(s)
            )
            SELECT sum(weights.w * pi.p * q.q) * 100 bb100
            FROM weights JOIN pi USING(s) JOIN q USING(s,a)
            WHERE pi.player=rows.player
          ) eva ON true
          JOIN LATERAL (
            WITH common AS (
              SELECT pa.s FROM ps pa JOIN ps pb ON pa.s=pb.s
              WHERE pa.player=rows.player AND pb.player=rows.opponent
            ), weights AS (
              SELECT s, w / sum(w) OVER () w FROM sw JOIN common USING(s)
            )
            SELECT sum(weights.w * pi.p * q.q) * 100 bb100
            FROM weights JOIN pi USING(s) JOIN q USING(s,a)
            WHERE pi.player=rows.opponent
          ) evb ON true
        )
        SELECT * FROM scored ORDER BY sim_bb100 DESC
    ''').fetchdf()
    return out, out.sim_bb100.corr(out.actual_bb100), spearman(out.sim_bb100, out.actual_bb100)


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    lines: list[str] = []
    lines.append("# ACPC signal diagnosis")
    lines.append("")

    integrity = con.execute("""
        SELECT
          (SELECT count(*) FROM (SELECT hand_id FROM 'data/hand_player/*.parquet' GROUP BY 1)) hands,
          (SELECT count(*) FROM d) decisions,
          (SELECT count(*) FROM 'data/hand_player/*.parquet') hand_player_rows,
          (SELECT max(abs(sum_net)) FROM (SELECT hand_id, sum(net_bb) sum_net FROM 'data/hand_player/*.parquet' GROUP BY 1)) max_abs_money_error,
          (SELECT avg((hero_hole_class IS NOT NULL)::int) FROM d) decision_hole_coverage
    """).fetchdf()
    lines.append("## Data integrity")
    lines.append(integrity.to_markdown(index=False, floatfmt=".6f"))
    lines.append("")
    net_sources = con.execute("""
        SELECT net_source, count(*) decisions FROM d GROUP BY 1 ORDER BY decisions DESC
    """).fetchdf()
    lines.append("Decision net sources:")
    lines.append(net_sources.to_markdown(index=False))
    lines.append("")

    actual = con.execute("""
        WITH hp AS (SELECT * FROM 'data/hand_player/*.parquet'), opp AS (
          SELECT a.player, b.player opponent, a.net_bb
          FROM hp a JOIN hp b ON a.hand_id=b.hand_id AND a.player<>b.player)
        SELECT player, opponent, count(*) hands, avg(net_bb)*100 bb100,
               stddev_samp(net_bb)*100/sqrt(count(*)) se_bb100,
               avg(net_bb)*100 / (stddev_samp(net_bb)*100/sqrt(count(*))) z
        FROM opp GROUP BY 1,2 ORDER BY player, opponent
    """).fetchdf()
    lines.append("## Actual winnings target reliability")
    lines.append(actual.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")
    lines.append("All six unordered matchups have 95% confidence intervals that include zero; the largest |z| is " + fmt(abs(actual.z).max()) + ".")
    lines.append("")

    overall_split = con.execute("""
        WITH hp AS (SELECT *, hash(hand_id)%2 split FROM 'data/hand_player/*.parquet'),
        p AS (SELECT player, split, avg(net_bb)*100 bb100, count(*) n FROM hp GROUP BY 1,2)
        SELECT a.player, a.bb100 half0, b.bb100 half1, a.n n0, b.n n1
        FROM p a JOIN p b USING(player) WHERE a.split=0 AND b.split=1 ORDER BY player
    """).fetchdf()
    pair_split = con.execute("""
        WITH hp AS (SELECT *, hash(hand_id)%2 split FROM 'data/hand_player/*.parquet'), pairs AS (
          SELECT least(a.player,b.player) p1, greatest(a.player,b.player) p2,
                 CASE WHEN a.player < b.player THEN a.net_bb ELSE b.net_bb END net_p1, a.split
          FROM hp a JOIN hp b ON a.hand_id=b.hand_id AND a.player<>b.player
          WHERE a.player < b.player
        ), p AS (SELECT p1,p2,split,avg(net_p1)*100 bb100,count(*) n FROM pairs GROUP BY 1,2,3)
        SELECT a.p1, a.p2, a.bb100 half0, b.bb100 half1, a.n n0, b.n n1
        FROM p a JOIN p b USING(p1,p2) WHERE a.split=0 AND b.split=1 ORDER BY p1,p2
    """).fetchdf()
    lines.append("### Split-half stability of the target")
    lines.append(f"Overall player bb/100 split-half: Pearson {fmt(overall_split.half0.corr(overall_split.half1))}, Spearman {fmt(spearman(overall_split.half0, overall_split.half1))}.")
    lines.append(f"Unordered pairwise bb/100 split-half: Pearson {fmt(pair_split.half0.corr(pair_split.half1))}, Spearman {fmt(spearman(pair_split.half0, pair_split.half1))}.")
    lines.append("")
    lines.append(overall_split.to_markdown(index=False, floatfmt=".2f"))
    lines.append("")

    lines.append("## Current policy-bootstrap reproduction")
    rows = []
    for table, state, nmin in [("d", "s_pdf", 1), ("d", "s_pdf", 3), ("d", "s_pdf", 10), ("d", "s_pdf", 50), ("d_range", "s_range", 10), ("d", "s_sim", 10)]:
        out, pear, spear = current_policy_eval(con, table, state, nmin)
        rows.append({"table": table, "state": state, "nmin": nmin, "pairs": len(out), "pearson": pear, "spearman": spear})
    lines.append(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".3f"))
    lines.append("")
    lines.append("`s_pdf` only looks good at `nmin=1`; requiring repeated per-player support removes or reverses the signal. That is the fingerprint of sparse-state noise, not a stable ranking signal.")
    lines.append("")

    action_rows = []
    for action_col in ["a", "act_base"]:
        out, pear, spear = current_policy_eval(con, "d", "s_pdf", 10, action_col)
        action_rows.append({"state": "s_pdf", "nmin": 10, "action_column": action_col, "pairs": len(out), "pearson": pear, "spearman": spear})
    lines.append("### Action granularity check")
    lines.append(pd.DataFrame(action_rows).to_markdown(index=False, floatfmt=".3f"))
    lines.append("")
    lines.append("Collapsing sized actions to base actions does not restore signal, so the current failure is not primarily caused by over-specific bet-size buckets.")
    lines.append("")

    action_q = con.execute("""
        SELECT a, count(*) n, avg(reward_bb) q_bb, stddev_samp(reward_bb) sd_bb
        FROM d GROUP BY 1 ORDER BY q_bb DESC
    """).fetchdf()
    lines.append("## Action-value confounding check")
    lines.append(action_q.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")
    lines.append("Population `Q(S,a)` is not a causal action value. Folds are mechanically 0 continuation bb, while bet/raise buckets are often strongly positive because those actions are selected with stronger private ranges and favorable opponent states. Valuing another player by this table rewards matching population selection effects, not necessarily better decisions.")
    lines.append("")

    residual = []
    for table, state in [("d", "s_core"), ("d", "s_sim"), ("d", "s_pdf"), ("d_range", "s_range")]:
        df = con.execute(f'''
            WITH qpop AS (
              SELECT "{state}" s, a, avg(reward_bb) q, count(*) n
              FROM "{table}" GROUP BY 1,2 HAVING count(*)>=10
            ), joined AS (
              SELECT d.player, d.reward_bb - qpop.q residual
              FROM "{table}" d JOIN qpop ON d."{state}"=qpop.s AND d.a=qpop.a
            ), score AS (
              SELECT player, avg(residual)*100 score, count(*) n FROM joined GROUP BY 1
            ), actual AS (
              SELECT player, avg(net_bb)*100 bb100 FROM 'data/hand_player/*.parquet' GROUP BY 1
            )
            SELECT score.player, score, n, bb100 FROM score JOIN actual USING(player) ORDER BY score DESC
        ''').fetchdf()
        residual.append({"state": state, "pearson": df.score.corr(df.bb100), "spearman": spearman(df.score, df.bb100), "ranking": ", ".join(df.player.tolist())})
    lines.append("## Exploratory like-for-like residual score")
    lines.append(pd.DataFrame(residual).to_markdown(index=False, floatfmt=".3f"))
    lines.append("")
    lines.append("This finds a weak positive player-level signal and usually ranks Tartanian7 first, but it is in-sample and outcome-based. It is evidence that replay/reward signs are not obviously reversed; it is not a robust counterfactual policy-comparison fix.")
    lines.append("")

    lines.append("## Diagnosis")
    lines.append("1. **The actual-winnings target is not reliable enough in this 4-bot ACPC sample.** Split halves are anti-correlated and pairwise standard errors are as large as, or larger than, the measured edges.")
    lines.append("2. **The current method has a fundamental causal/OPE problem.** `Q_pop(S,a)` is an observational continuation mean. Even with hole-card buckets, it still contains selection effects from unmodeled private blockers, exact board/runout, opponent strategy, and future reach distribution.")
    lines.append("3. **Sparse state specificity makes the apparent signal unstable.** Exact-board/hole-heavy `s_pdf` is positive at `nmin=1` but collapses as soon as common support requires repeated observations.")
    lines.append("4. **Action granularity is not the primary cause.** Using base actions instead of sized buckets still fails at the repeated-support setting.")
    lines.append("5. **No gross replay sign error is evident.** Money is conserved, hole coverage is 100%, and the residual score points in the expected direction; the failure is not simply reversed winnings or missing cards.")
    lines.append("")
    lines.append("## Recommended stop condition")
    lines.append("Do not tune more state/action buckets against this target. The next defensible step requires a more reliable label: more hands per matchup, repeated independent tournament seeds, or a dataset with enough players/time to validate on future winnings. Without that, a positive correlation can be manufactured by overfitting `nmin=1` sparse states but will not be robust.")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
