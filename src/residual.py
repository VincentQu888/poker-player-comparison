#!/usr/bin/env python3
"""RESULTS check: do variables omitted from the coarse bucket still predict
action/outcome within buckets? Variance-explained (eta^2) of reward and of
P(fold) as we refine the state: s_core -> s_fine (+faced_size,+n_active) ->
+board texture (+W/D). If refining adds eta^2, the coarse buckets are incomplete
(omitted vars carry residual signal)."""
import duckdb
con = duckdb.connect("data/analysis.duckdb", read_only=True)
con.execute("PRAGMA threads=6; PRAGMA memory_limit='16GB';")
con.execute("CREATE TEMP VIEW tex AS SELECT flop,wtile,dtile FROM 'data/flop_texture.parquet';")
# cohort >=5k to match the EV analysis
con.execute("""CREATE TEMP TABLE cohort AS SELECT site,player FROM
  (SELECT site,player,count(DISTINCT hand_id) h FROM d GROUP BY site,player) WHERE h>=5000;""")
con.execute("""CREATE TEMP TABLE cd AS
  SELECT d.site,d.player,d.s_core,d.s_fine,d.a,d.reward_bb r,
     CASE WHEN length(d.board)>=6 THEN d.s_fine||'|W'||tex.wtile||'|D'||tex.dtile ELSE d.s_fine END s_tex
  FROM d JOIN cohort USING(site,player) LEFT JOIN tex ON substr(d.board,1,6)=tex.flop;""")

def eta2(group_col, val_expr, where=""):
    # eta^2 = between-group variance / total variance (weighted by group n)
    q = f"""
    WITH base AS (SELECT {group_col} g, {val_expr} v FROM cd {where}),
    tot AS (SELECT avg(v) gm, var_pop(v) tv, count(*) n FROM base),
    grp AS (SELECT g, avg(v) m, count(*) gn FROM base GROUP BY g),
    between AS (SELECT sum(grp.gn*(grp.m-tot.gm)*(grp.m-tot.gm)) ss, count(*) ng FROM grp, tot)
    SELECT between.ss / (tot.tv * tot.n) AS eta2, tot.tv, between.ng
    FROM between, tot
    """
    return con.execute(q).fetchone()

print("=== eta^2 of REWARD (bb) explained by state granularity (cohort>=5k) ===")
for name, col in [("s_core", "s_core"), ("s_fine (+faced_sz,+n_active)", "s_fine"),
                  ("s_fine + W/D texture", "s_tex")]:
    e, tv, ng = eta2(col, "r", "WHERE r IS NOT NULL")
    print(f"  {name:32s} eta2={e:.4f}  ({ng:,} groups; total reward var={tv:.1f})")

print("\n=== eta^2 of P(fold) explained by state granularity ===")
for name, col in [("s_core", "s_core"), ("s_fine", "s_fine"), ("s_fine + W/D texture", "s_tex")]:
    e, tv, ng = eta2(col, "(a='f')::int")
    print(f"  {name:32s} eta2={e:.4f}  ({ng:,} groups)")

# incremental: within s_core, how much does adding faced_sz+nactive add?
print("\nIncremental eta^2 (reward): s_fine - s_core =",
      round(eta2("s_fine","r","WHERE r IS NOT NULL")[0]-eta2("s_core","r","WHERE r IS NOT NULL")[0],4))
print("Incremental eta^2 (reward): +texture over s_fine =",
      round(eta2("s_tex","r","WHERE r IS NOT NULL")[0]-eta2("s_fine","r","WHERE r IS NOT NULL")[0],4))
print("\nInterpretation: nonzero increments => omitted variables carry residual predictive")
print("signal within coarser buckets, i.e. the coarse buckets are an approximation.")
