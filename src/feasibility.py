#!/usr/bin/env python3
"""Stage 3: FEASIBILITY. Sample sizes per player, stakes, hole-card visibility,
missing-card bias, and a first look at sparsity. Player identity = (site, player)."""
import duckdb, os, json

HP = "data/hand_player/*.parquet"
DEC = "data/decisions/*.parquet"
OUT = "report"
os.makedirs(OUT, exist_ok=True)

con = duckdb.connect()
con.execute("PRAGMA threads=6; PRAGMA memory_limit='12GB';")

R = {}

# ---- totals ----
R["totals"] = con.execute(f"""
  SELECT (SELECT count(*) FROM '{HP}') AS hand_players,
         (SELECT count(*) FROM '{DEC}') AS decisions
""").fetchdf().to_dict("records")[0]

# hands = distinct (site, hand_id) in hand_player
R["n_hands"] = con.execute(f"SELECT count(DISTINCT (site||'|'||hand_id)) AS n FROM '{HP}'").fetchone()[0]

# ---- stakes / site distribution (hand-players) ----
R["by_site_level"] = con.execute(f"""
  SELECT site, nl_level, count(*) AS hand_players,
         count(DISTINCT player) AS players
  FROM '{HP}' GROUP BY site, nl_level ORDER BY hand_players DESC LIMIT 40
""").fetchdf().to_dict("records")

R["by_site"] = con.execute(f"""
  SELECT site, count(*) AS hand_players, count(DISTINCT player) AS players
  FROM '{HP}' GROUP BY site ORDER BY hand_players DESC
""").fetchdf().to_dict("records")

# ---- hands per player (site,player) ----
con.execute(f"""
  CREATE TEMP TABLE pp AS
  SELECT site, player, count(*) AS hands,
         sum(CASE WHEN vpip THEN 1 ELSE 0 END) AS vpip_hands,
         sum(CASE WHEN reached_showdown THEN 1 ELSE 0 END) AS sd_hands,
         sum(CASE WHEN saw_hole THEN 1 ELSE 0 END) AS shown_hands
  FROM '{HP}' GROUP BY site, player
""")
R["n_players"] = con.execute("SELECT count(*) FROM pp").fetchone()[0]
R["hands_per_player_quantiles"] = con.execute("""
  SELECT
    min(hands) AS min, quantile_cont(hands,0.25) AS p25,
    median(hands) AS p50, quantile_cont(hands,0.75) AS p75,
    quantile_cont(hands,0.9) AS p90, quantile_cont(hands,0.99) AS p99,
    max(hands) AS max, avg(hands) AS mean
  FROM pp
""").fetchdf().to_dict("records")[0]
R["players_ge"] = con.execute("""
  SELECT
    sum((hands>=1000)::int) AS ge_1k,
    sum((hands>=5000)::int) AS ge_5k,
    sum((hands>=10000)::int) AS ge_10k,
    sum((hands>=25000)::int) AS ge_25k,
    sum((hands>=50000)::int) AS ge_50k
  FROM pp
""").fetchdf().to_dict("records")[0]
# how much of the total volume do the well-sampled players account for
R["volume_share"] = con.execute("""
  SELECT
    sum(hands) AS total_hands,
    sum(CASE WHEN hands>=1000 THEN hands ELSE 0 END)*1.0/sum(hands) AS share_ge_1k,
    sum(CASE WHEN hands>=5000 THEN hands ELSE 0 END)*1.0/sum(hands) AS share_ge_5k,
    sum(CASE WHEN hands>=10000 THEN hands ELSE 0 END)*1.0/sum(hands) AS share_ge_10k
  FROM pp
""").fetchdf().to_dict("records")[0]

# ---- decisions per player ----
con.execute(f"""
  CREATE TEMP TABLE dp AS
  SELECT site, player, count(*) AS decisions
  FROM '{DEC}' GROUP BY site, player
""")
R["decisions_per_player_quantiles"] = con.execute("""
  SELECT min(decisions) AS min, median(decisions) AS p50,
         quantile_cont(decisions,0.9) AS p90, quantile_cont(decisions,0.99) AS p99,
         max(decisions) AS max, avg(decisions) AS mean
  FROM dp
""").fetchdf().to_dict("records")[0]
R["players_dec_ge"] = con.execute("""
  SELECT sum((decisions>=1000)::int) AS ge_1k,
         sum((decisions>=5000)::int) AS ge_5k,
         sum((decisions>=25000)::int) AS ge_25k
  FROM dp
""").fetchdf().to_dict("records")[0]

# ---- hole-card visibility & missing-card bias ----
R["visibility_overall"] = con.execute(f"""
  SELECT
    avg(saw_hole::int) AS frac_saw_hole,
    avg(reached_showdown::int) AS frac_reached_sd,
    avg(CASE WHEN reached_showdown THEN saw_hole::int END) AS frac_shown_given_sd,
    avg(CASE WHEN NOT reached_showdown THEN saw_hole::int END) AS frac_shown_given_no_sd
  FROM '{HP}'
""").fetchdf().to_dict("records")[0]

# conditional on the hand-player's last action being a fold vs not, and by street reached.
# saw_hole is essentially 1 only at showdown; quantify how biased shown hands are:
R["missing_card_bias"] = con.execute(f"""
  SELECT
    avg(CASE WHEN vpip THEN saw_hole::int END) AS shown_given_vpip,
    avg(CASE WHEN NOT vpip THEN saw_hole::int END) AS shown_given_novpip,
    avg(CASE WHEN saw_hole THEN net_bb END) AS mean_net_shown,
    avg(CASE WHEN NOT saw_hole THEN net_bb END) AS mean_net_notshown,
    avg(CASE WHEN saw_hole THEN invested_bb END) AS mean_inv_shown,
    avg(CASE WHEN NOT saw_hole THEN invested_bb END) AS mean_inv_notshown
  FROM '{HP}'
""").fetchdf().to_dict("records")[0]

# ---- outcome coverage (net_source) ----
R["net_source_dist"] = con.execute(f"""
  SELECT net_source, count(*) AS n, avg(net_bb) AS mean_net
  FROM '{HP}' GROUP BY net_source ORDER BY n DESC
""").fetchdf().to_dict("records")

# money conservation: sum of net_bb per hand should be ~ -rake (<=0). Check per-hand sum.
R["conservation"] = con.execute(f"""
  WITH h AS (
    SELECT site, hand_id, sum(net_bb) AS s, count(*) n_null_free
    FROM '{HP}' WHERE net_bb IS NOT NULL
    GROUP BY site, hand_id
  )
  SELECT count(*) AS hands_with_net,
         avg(s) AS mean_sum_net_bb,
         quantile_cont(s,0.01) AS p01, quantile_cont(s,0.5) AS p50,
         quantile_cont(s,0.99) AS p99,
         sum((s > 0.01)::int) AS hands_money_created,
         sum((abs(s) < 0.01)::int) AS hands_exact_zero
  FROM h
""").fetchdf().to_dict("records")[0]

print(json.dumps(R, indent=2, default=str))
with open(os.path.join(OUT, "feasibility.json"), "w") as f:
    json.dump(R, f, indent=2, default=str)
print("\nwrote", os.path.join(OUT, "feasibility.json"))
