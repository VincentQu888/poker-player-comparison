#!/usr/bin/env python3
"""Stage 4a: build an on-disk DuckDB table of decisions enriched with public
state buckets and a sized action label. Public observables only (hero hole cards
are unobserved at ~96% of decisions, per feasibility)."""
import duckdb, os

DEC = "data/decisions/*.parquet"
DB = "data/analysis.duckdb"
if os.path.exists(DB):
    os.remove(DB)
con = duckdb.connect(DB)
con.execute("PRAGMA threads=6; PRAGMA memory_limit='16GB';")

# size bucket macro on a pot-relative fraction
con.execute("""
CREATE MACRO sizeb(x) AS (
  CASE WHEN x IS NULL THEN 'na'
       WHEN x < 0.4 THEN '1'
       WHEN x < 0.75 THEN '2'
       WHEN x < 1.25 THEN '3'
       ELSE '4' END);
""")
con.execute("""
CREATE MACRO sprb(s) AS (
  CASE WHEN s < 0.5 THEN 'a' WHEN s < 1 THEN 'b' WHEN s < 2 THEN 'c'
       WHEN s < 5 THEN 'd' WHEN s < 15 THEN 'e' ELSE 'f' END);
""")
con.execute("""
CREATE MACRO posg(l) AS (
  CASE WHEN l IN ('SB','SB/BTN') THEN 'SB'
       WHEN l = 'BB' THEN 'BB'
       WHEN l = 'BTN' THEN 'BTN'
       WHEN l = 'CO' THEN 'CO'
       WHEN l IN ('UTG','UTG1','UTG2') THEN 'EP'
       ELSE 'MP' END);
""")
con.execute("""
CREATE MACRO nab(n) AS (CASE WHEN n>=6 THEN '6+' ELSE CAST(n AS VARCHAR) END);
""")

print("building enriched table...")
con.execute(f"""
CREATE TABLE d AS
SELECT
  site, player, hand_id, nl_level, seat_count, n_players,
  street, pot_type, posg(pos_label) AS pos, action_faced,
  sizeb(prev_wager_frac) AS faced_sz,
  sprb(spr) AS spr_b,
  nab(n_active_before) AS nactive,
  CASE act
    WHEN 'fold' THEN 'f' WHEN 'check' THEN 'x' WHEN 'call' THEN 'c'
    WHEN 'bet' THEN 'b'||sizeb(act_frac * pot_before_bb / NULLIF(pot_before_bb + to_call_bb, 0))
    WHEN 'raise' THEN 'r'||sizeb(act_frac * pot_before_bb / NULLIF(pot_before_bb + to_call_bb, 0))
  END AS a,
  act AS act_base,
  reward_bb, hand_net_bb, net_source,
  board, year, month, day
FROM '{DEC}';
""")
n = con.execute("SELECT count(*) FROM d").fetchone()[0]
print("rows:", n)
# state keys at two granularities
con.execute("""
ALTER TABLE d ADD COLUMN s_core VARCHAR;
UPDATE d SET s_core = street||'|'||pot_type||'|'||pos||'|'||action_faced||'|'||spr_b;
""")
con.execute("""
ALTER TABLE d ADD COLUMN s_fine VARCHAR;
UPDATE d SET s_fine = s_core||'|'||faced_sz||'|'||nactive;
""")
print("action distribution:")
for r in con.execute("SELECT a, count(*) c FROM d GROUP BY a ORDER BY c DESC").fetchall():
    print(f"  {r[0]:>4} {r[1]:>12,}")
print("distinct s_core:", con.execute("SELECT count(DISTINCT s_core) FROM d").fetchone()[0])
print("distinct s_fine:", con.execute("SELECT count(DISTINCT s_fine) FROM d").fetchone()[0])
con.close()
print("wrote", DB)
