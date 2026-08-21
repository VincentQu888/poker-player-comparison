#!/usr/bin/env python3
"""Does adding board texture (wetness/dynamicness terciles) to postflop states
improve out-of-sample validity of the conditional-skill measure B?
Compares s_core vs s_tex (= s_core + W/D terciles on postflop states)."""
import duckdb, numpy as np, argparse
ap=argparse.ArgumentParser(); ap.add_argument("--split_day",type=int,default=18)
ap.add_argument("--nmin_sa",type=int,default=5); ap.add_argument("--min_eligible",type=int,default=50)
ap.add_argument("--min_train_hands",type=int,default=2000); ap.add_argument("--min_test_hands",type=int,default=1000)
a=ap.parse_args()
con=duckdb.connect("data/analysis.duckdb",read_only=True); con.execute("PRAGMA threads=6; PRAGMA memory_limit='16GB';")
con.execute("CREATE TEMP VIEW tex AS SELECT flop,wtile,dtile FROM 'data/flop_texture.parquet';")
def rk(v):
    _,inv,cnt=np.unique(v,return_inverse=True,return_counts=True);o=v.argsort();r=np.empty(len(v));r[o]=np.arange(len(v));s=np.zeros(len(cnt));np.add.at(s,inv,r);return (s/cnt)[inv]
def spear(x,y):
    x=rk(x)-rk(x).mean();y=rk(y)-rk(y).mean();return float((x*y).sum()/np.sqrt((x**2).sum()*(y**2).sum()))

con.execute(f"""CREATE TEMP TABLE realized AS SELECT site,player,
   sum((day<={a.split_day})::int) n_tr, sum((day>{a.split_day})::int) n_te,
   avg(CASE WHEN day> {a.split_day} THEN net_bb END)*100 bb100_te,
   avg(CASE WHEN day<={a.split_day} THEN net_bb END)*100 bb100_tr
 FROM 'data/hand_player/*.parquet' WHERE net_bb IS NOT NULL GROUP BY site,player;""")
con.execute(f"""CREATE TEMP TABLE cohort AS SELECT site,player FROM realized
   WHERE n_tr>={a.min_train_hands} AND n_te>={a.min_test_hands};""")

def run(state_expr, label):
    con.execute("DROP TABLE IF EXISTS cd;")
    con.execute(f"""CREATE TEMP TABLE cd AS
      SELECT d.site,d.player, {state_expr} AS s, d.a a, d.reward_bb r
      FROM d JOIN cohort USING(site,player)
      LEFT JOIN tex ON substr(d.board,1,6)=tex.flop
      WHERE d.day<={a.split_day};""")
    con.execute(f"""CREATE TEMP TABLE elig AS SELECT s,count(DISTINCT (site||player)) eligible,count(*) ndec
       FROM cd GROUP BY s HAVING eligible>={a.min_eligible};""")
    con.execute("""CREATE OR REPLACE TEMP TABLE Q AS SELECT cd.s,cd.a,avg(r) qpop FROM cd JOIN elig USING(s)
       WHERE r IS NOT NULL GROUP BY cd.s,cd.a;""")
    con.execute("""CREATE OR REPLACE TEMP TABLE psa AS SELECT site,player,s,a,count(*) c,avg(r) qp,count(r) nqp
       FROM cd GROUP BY site,player,s,a;""")
    con.execute("""CREATE OR REPLACE TEMP TABLE ptot AS SELECT site,player,sum(c) ntot FROM psa JOIN elig USING(s) GROUP BY site,player;""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE skillB AS
       SELECT p.site,p.player, sum(p.c*(p.qp-q.qpop))*1.0/t.ntot skill
       FROM psa p JOIN elig USING(s) JOIN Q q ON p.s=q.s AND p.a=q.a JOIN ptot t USING(site,player)
       WHERE p.nqp>={a.nmin_sa} GROUP BY p.site,p.player,t.ntot;""")
    df=con.execute("""SELECT r.n_te, r.bb100_te, r.bb100_tr, coalesce(b.skill,0) skill
       FROM cohort c JOIN realized r USING(site,player) LEFT JOIN skillB b USING(site,player)""").fetchdf()
    con.execute("DROP TABLE elig;")
    te=df.bb100_te.values; sB=df.skill.values; nte=df.n_te.values
    o=f"[{label}] B~test={spear(sB,te):.3f}"
    for th in (3000,5000):
        m=nte>=th
        if m.sum()>=100: o+=f"  test>={th}:{spear(sB[m],te[m]):.3f}"
    print(o)

df0=con.execute("SELECT bb100_tr,bb100_te,n_te FROM realized r JOIN cohort USING(site,player)").fetchdf()
print(f"cohort={len(df0)}  CEILING bb_tr~bb_te={spear(df0.bb100_tr.values,df0.bb100_te.values):.3f} "
      f"(test>=5000:{spear(df0[df0.n_te>=5000].bb100_tr.values,df0[df0.n_te>=5000].bb100_te.values):.3f})")
run("d.s_core", "s_core")
run("CASE WHEN length(d.board)>=6 THEN d.s_core||'|W'||tex.wtile||'|D'||tex.dtile ELSE d.s_core END", "s_core+texture")
run("d.s_fine", "s_fine ")
run("CASE WHEN length(d.board)>=6 THEN d.s_fine||'|W'||tex.wtile||'|D'||tex.dtile ELSE d.s_fine END", "s_fine+texture")
