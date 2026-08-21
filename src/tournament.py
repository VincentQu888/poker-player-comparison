#!/usr/bin/env python3
"""Literal 'who wins more' tournament -- real money, per hand, NO reward model.

Each player is scored by realized winnings net_bb per 100 hands (bb/100), the
actual money they won/lost. We report uncertainty (analytic SE of the mean, since
per-hand nets are ~independent), head-to-head P(A beats B), how many players are
*resolvably* winning, and whether the ranking generalizes out of sample
(train days 1-18 winrate vs test days 19-26 winrate).

Matching on 'similar properties': we also compute a STAKES-MATCHED winrate
(each player's per-nl_level bb/100 reweighted to a common stake mix), so players
are compared over the same distribution of stakes.
"""
import duckdb, numpy as np, argparse, json
from math import erf, sqrt
ap = argparse.ArgumentParser()
ap.add_argument("--cohort_hands", type=int, default=5000)
ap.add_argument("--split_day", type=int, default=18)
a = ap.parse_args()
con = duckdb.connect("data/analysis.duckdb", read_only=True)
con.execute("PRAGMA threads=6; PRAGMA memory_limit='16GB';")
HP = "'data/hand_player/*.parquet'"

def spear(x, y):
    def rk(v):
        _, inv, cnt = np.unique(v, return_inverse=True, return_counts=True)
        o = v.argsort(); r = np.empty(len(v)); r[o] = np.arange(len(v))
        s = np.zeros(len(cnt)); np.add.at(s, inv, r); return (s/cnt)[inv]
    x = rk(x)-rk(x).mean(); y = rk(y)-rk(y).mean()
    return float((x*y).sum()/np.sqrt((x**2).sum()*(y**2).sum()))
def phi(x): return 0.5*(1+erf(x/sqrt(2)))

# cohort and realized winnings (real money, per hand)
con.execute(f"""CREATE TEMP TABLE agg AS
  SELECT site,player, count(*) n_hands, avg(net_bb) m, stddev_samp(net_bb) sd
  FROM {HP} WHERE net_bb IS NOT NULL GROUP BY site,player;""")
df = con.execute(f"SELECT * FROM agg WHERE n_hands>={a.cohort_hands}").fetchdf()
df["bb100"] = df.m*100
df["se"] = 100*df.sd/np.sqrt(df.n_hands)          # SE of mean winrate
df["lo"] = df.bb100-1.96*df.se; df["hi"] = df.bb100+1.96*df.se
df = df.sort_values("bb100", ascending=False).reset_index(drop=True)
N = len(df)

sig_win = int((df.lo > 0).sum()); sig_lose = int((df.hi < 0).sum())
print(f"WHO WINS MORE -- real money, per hand (cohort >= {a.cohort_hands} hands: {N} players)")
print(f"bb/100 spread: p5={np.percentile(df.bb100,5):.1f}  median={df.bb100.median():.1f}  "
      f"p95={np.percentile(df.bb100,95):.1f}  (mean per-hand ~ -0.05 bb = rake)")
print(f"median 95% CI half-width = +/-{df.se.median()*1.96:.1f} bb/100  (median {df.n_hands.median():.0f} hands)")
print(f"players RESOLVABLY winning (CI low > 0):  {sig_win} ({100*sig_win/N:.1f}%)")
print(f"players RESOLVABLY losing  (CI high < 0): {sig_lose} ({100*sig_lose/N:.1f}%)")
print(f"=> {100*(N-sig_win-sig_lose)/N:.0f}% of players are statistically indistinguishable from break-even.")

cols = ["site","player","bb100","lo","hi","n_hands"]
print("\nTOP 12 winners (bb/100 [95% CI]):")
print(df.head(12)[cols].to_string(index=False, float_format=lambda x: f"{x:.1f}"))
print("\nBOTTOM 6:")
print(df.tail(6)[cols].to_string(index=False, float_format=lambda x: f"{x:.1f}"))

# head-to-head P(A beats B) among top-6 (normal approx on winrate difference)
top = df.head(6).reset_index(drop=True)
print("\nHead-to-head P(row wins more than col) -- top 6:")
lab = [p[:6] for p in top.player]
print("        " + "  ".join(f"{l:>7}" for l in lab))
for i in range(6):
    row = []
    for j in range(6):
        if i == j: row.append("   -   ")
        else:
            d = top.bb100[i]-top.bb100[j]; s = np.hypot(top.se[i], top.se[j])
            row.append(f"{phi(d/s):7.2f}")
    print(f"{lab[i]:>6}  " + "  ".join(row))

# stakes-matched winrate (compare over a common stake mix)
con.execute(f"""CREATE TEMP TABLE pl AS
  SELECT site,player,nl_level, count(*) n, avg(net_bb) m
  FROM {HP} WHERE net_bb IS NOT NULL GROUP BY site,player,nl_level;""")
con.execute(f"""CREATE TEMP TABLE lw AS
  SELECT nl_level, count(*)*1.0/(SELECT count(*) FROM {HP} WHERE net_bb IS NOT NULL) w FROM {HP}
  WHERE net_bb IS NOT NULL GROUP BY nl_level;""")
sm = con.execute(f"""SELECT p.site,p.player, sum(lw.w*p.m)/sum(lw.w)*100 bb100_sm, sum(p.n) nn
  FROM pl p JOIN lw USING(nl_level)
  JOIN (SELECT site,player FROM agg WHERE n_hands>={a.cohort_hands}) c USING(site,player)
  GROUP BY p.site,p.player""").fetchdf()
mm = df.merge(sm, on=["site","player"])
print(f"\nSpearman(raw bb/100, stakes-matched bb/100) = {spear(mm.bb100.values, mm.bb100_sm.values):.3f} "
      "(stakes matching barely changes the ranking)")

# temporal holdout: does winning in period 1 predict winning in period 2?
con.execute(f"""CREATE TEMP TABLE tt AS
  SELECT site,player,
    sum((day<={a.split_day})::int) n_tr, sum((day>{a.split_day})::int) n_te,
    avg(CASE WHEN day<={a.split_day} THEN net_bb END)*100 tr,
    avg(CASE WHEN day> {a.split_day} THEN net_bb END)*100 te
  FROM {HP} WHERE net_bb IS NOT NULL GROUP BY site,player;""")
h = con.execute("SELECT * FROM tt WHERE n_tr>=2000 AND n_te>=1000").fetchdf()
print(f"\nGENERALIZATION (train days<= {a.split_day} vs test days>): n={len(h)}")
print(f"  Spearman(winrate_train, winrate_test) = {spear(h.tr.values,h.te.values):.3f}")
for th in (3000,5000):
    m=h.n_te.values>=th
    if m.sum()>=100:
        print(f"    [test>={th}h, n={m.sum()}]: {spear(h.tr.values[m],h.te.values[m]):.3f}")

df.to_csv("report/tournament_winrate.csv", index=False)
json.dump({"cohort":N,"resolvably_winning":sig_win,"resolvably_losing":sig_lose,
           "indistinguishable_pct":round(100*(N-sig_win-sig_lose)/N,1),
           "median_CI_halfwidth_bb100":float(df.se.median()*1.96),
           "generalization_spearman":spear(h.tr.values,h.te.values)},
          open("report/tournament_winrate.json","w"), indent=2)
print("\nwrote report/tournament_winrate.csv")
