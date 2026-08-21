#!/usr/bin/env python3
"""Stage 4b: sparsity & common-support analysis over public states.
How much of each cohort's decisions live in states shared by many players at
usable per-player sample sizes? This gates the EV comparison."""
import duckdb, json, os

con = duckdb.connect("data/analysis.duckdb", read_only=True)
con.execute("PRAGMA threads=6; PRAGMA memory_limit='16GB';")
R = {}

# player summary: hands & decisions per (site,player)
con.execute("""
CREATE TEMP TABLE ps AS
SELECT site, player, count(*) AS n_dec, count(DISTINCT hand_id) AS n_hands
FROM d GROUP BY site, player;
""")

for H in (1000, 5000):
    key = f"cohort_ge_{H}"
    con.execute(f"CREATE OR REPLACE TEMP TABLE cohort AS SELECT site,player FROM ps WHERE n_hands>={H}")
    ncoh = con.execute("SELECT count(*) FROM cohort").fetchone()[0]
    ndec = con.execute("""SELECT count(*) FROM d JOIN cohort USING(site,player)""").fetchone()[0]
    R[key] = {"players": ncoh, "decisions": int(ndec)}

    for sname in ("s_core", "s_fine"):
        # per (player,state) obs among cohort
        con.execute(f"""
        CREATE OR REPLACE TEMP TABLE psst AS
        SELECT d.site, d.player, d.{sname} AS s, count(*) AS c
        FROM d JOIN cohort USING(site,player)
        GROUP BY d.site, d.player, s;
        """)
        # per state: eligible players (>=1 obs) and supported at n
        con.execute("""
        CREATE OR REPLACE TEMP TABLE st AS
        SELECT s,
          count(*) AS eligible,
          sum((c>=3)::int) AS s3,
          sum((c>=5)::int) AS s5,
          sum((c>=10)::int) AS s10,
          sum(c) AS dec_in_state
        FROM psst GROUP BY s;
        """)
        nstates = con.execute("SELECT count(*) FROM st").fetchone()[0]
        # supported-decision fraction: fraction of cohort decisions whose (player,state) c>=n
        supp = con.execute("""
        SELECT
          sum(CASE WHEN c>=3 THEN c ELSE 0 END)*1.0/sum(c) AS f3,
          sum(CASE WHEN c>=5 THEN c ELSE 0 END)*1.0/sum(c) AS f5,
          sum(CASE WHEN c>=10 THEN c ELSE 0 END)*1.0/sum(c) AS f10
        FROM psst;
        """).fetchdf().to_dict("records")[0]
        # common-state coverage: fraction of cohort decisions in states where
        # >=X% of the FULL cohort have >=n obs (require eligible>=20 to be meaningful)
        cov = {}
        tot_dec = con.execute("SELECT sum(dec_in_state) FROM st").fetchone()[0]
        for n_th, col in ((3, "s3"), (5, "s5"), (10, "s10")):
            for X in (0.10, 0.20, 0.30, 0.50):
                thr = X * ncoh
                d_in = con.execute(f"""
                  SELECT coalesce(sum(dec_in_state),0) FROM st
                  WHERE {col} >= {thr} AND eligible>=20
                """).fetchone()[0]
                nst = con.execute(f"""
                  SELECT count(*) FROM st WHERE {col} >= {thr} AND eligible>=20
                """).fetchone()[0]
                cov[f"n{n_th}_X{int(X*100)}"] = {
                    "states": int(nst),
                    "dec_coverage": round(d_in / tot_dec, 4) if tot_dec else 0.0,
                }
        R[key][sname] = {
            "distinct_states": int(nstates),
            "supported_decision_frac": {k: round(v, 4) for k, v in supp.items()},
            "common_state_coverage": cov,
        }
        print(f"[{key}/{sname}] states={nstates} supp={ {k:round(v,3) for k,v in supp.items()} }")
        for k, v in cov.items():
            print(f"    {k}: states={v['states']:>5} dec_cov={v['dec_coverage']}")

os.makedirs("report", exist_ok=True)
with open("report/support.json", "w") as f:
    json.dump(R, f, indent=2)
print("\nwrote report/support.json")
