#!/usr/bin/env python3
"""Decisive method comparison, all estimated on TRAIN, validated on TEST winrate.

(A) policy-alignment edge : sum_S w(S) sum_a pi_p(a|S) Qpop(S,a)  -- which actions you pick,
    valued at population outcomes. (Shown to be ~aggression proxy.)
(B) conditional skill     : sum_{S,a} freq_p(S,a) (Qp(S,a) - Qpop(S,a)) -- do you beat peers
    in the SAME public state AND SAME action (like-for-like), removing the aggression confound.
Ceiling = corr(bb100_train, bb100_test).
"""
import duckdb, numpy as np, argparse, json
ap=argparse.ArgumentParser()
ap.add_argument("--state",default="s_core"); ap.add_argument("--split_day",type=int,default=18)
ap.add_argument("--nmin",type=int,default=10); ap.add_argument("--nmin_sa",type=int,default=5)
ap.add_argument("--min_eligible",type=int,default=50)
ap.add_argument("--min_train_hands",type=int,default=2000); ap.add_argument("--min_test_hands",type=int,default=1000)
a=ap.parse_args(); S=a.state
con=duckdb.connect("data/analysis.duckdb",read_only=True); con.execute("PRAGMA threads=6; PRAGMA memory_limit='16GB';")
def pear(x,y):
    xm,ym=x.mean(),y.mean(); d=np.sqrt(((x-xm)**2).sum()*((y-ym)**2).sum()); return float(((x-xm)*(y-ym)).sum()/d) if d else float('nan')
def rk(v):
    _,inv,cnt=np.unique(v,return_inverse=True,return_counts=True);o=v.argsort();r=np.empty(len(v));r[o]=np.arange(len(v));s=np.zeros(len(cnt));np.add.at(s,inv,r);return (s/cnt)[inv]
def spear(x,y): return pear(rk(x),rk(y))

con.execute(f"""CREATE TEMP TABLE realized AS SELECT site,player,
   sum((day<={a.split_day})::int) n_tr, sum((day>{a.split_day})::int) n_te,
   avg(CASE WHEN day<={a.split_day} THEN net_bb END)*100 bb100_tr,
   avg(CASE WHEN day> {a.split_day} THEN net_bb END)*100 bb100_te
 FROM 'data/hand_player/*.parquet' WHERE net_bb IS NOT NULL GROUP BY site,player;""")
con.execute(f"""CREATE TEMP TABLE cohort AS SELECT site,player FROM realized
   WHERE n_tr>={a.min_train_hands} AND n_te>={a.min_test_hands};""")
ncoh=con.execute("SELECT count(*) FROM cohort").fetchone()[0]
con.execute(f"""CREATE TEMP TABLE cd AS SELECT d.site,d.player,d.{S} s,d.a a,d.reward_bb r
   FROM d JOIN cohort USING(site,player) WHERE d.day<={a.split_day};""")
con.execute(f"""CREATE TEMP TABLE elig AS SELECT s,count(DISTINCT (site||player)) eligible,count(*) ndec
   FROM cd GROUP BY s HAVING eligible>={a.min_eligible};""")
con.execute("CREATE TEMP TABLE w AS SELECT s, ndec*1.0/(SELECT sum(ndec) FROM elig) w FROM elig;")
con.execute("""CREATE TEMP TABLE Q AS SELECT cd.s,cd.a,avg(r) qpop,count(r) nq FROM cd JOIN elig USING(s)
   WHERE r IS NOT NULL GROUP BY cd.s,cd.a;""")
con.execute("CREATE TEMP TABLE Qs AS SELECT s,sum(qpop*nq)/sum(nq) qs FROM Q GROUP BY s;")
# ---- (A) edge ----
con.execute("""CREATE TEMP TABLE PIbar AS SELECT cd.s,cd.a,count(*) c FROM cd JOIN elig USING(s) GROUP BY cd.s,cd.a;""")
con.execute("""CREATE TEMP TABLE EVbar AS SELECT p.s,sum(p.c*coalesce(q.qpop,qs.qs))*1.0/sum(p.c) evbar
   FROM PIbar p LEFT JOIN Q q ON p.s=q.s AND p.a=q.a LEFT JOIN Qs qs ON p.s=qs.s GROUP BY p.s;""")
con.execute("""CREATE TEMP TABLE psa AS SELECT site,player,s,a,count(*) c,avg(r) qp,count(r) nqp FROM cd GROUP BY site,player,s,a;""")
con.execute("""CREATE TEMP TABLE psn AS SELECT site,player,s,sum(c) cs FROM psa GROUP BY site,player,s;""")
con.execute(f"""CREATE TEMP TABLE pev AS
   SELECT x.site,x.player,x.s,sum(x.c*coalesce(q.qpop,qs.qs))*1.0/x.cs pevs,x.cs
   FROM (SELECT psa.*,psn.cs FROM psa JOIN psn USING(site,player,s)) x
   LEFT JOIN Q q ON x.s=q.s AND x.a=q.a LEFT JOIN Qs qs ON x.s=qs.s
   GROUP BY x.site,x.player,x.s,x.cs;""")
con.execute(f"""CREATE TEMP TABLE edgeA AS SELECT pev.site,pev.player,sum(w.w*(pev.pevs-e.evbar)) edge
   FROM pev JOIN w USING(s) JOIN EVbar e USING(s) WHERE pev.cs>={a.nmin} GROUP BY pev.site,pev.player;""")
# ---- (B) conditional skill: like-for-like (S,a), weighted by player's own freq ----
con.execute(f"""CREATE TEMP TABLE ptot AS SELECT site,player,sum(c) ntot FROM psa
   JOIN elig USING(s) GROUP BY site,player;""")
con.execute(f"""CREATE TEMP TABLE skillB AS
   SELECT p.site,p.player, sum(p.c*(p.qp-q.qpop))*1.0/t.ntot skill, sum(p.c)*1.0/t.ntot cov
   FROM psa p JOIN elig USING(s) JOIN Q q ON p.s=q.s AND p.a=q.a JOIN ptot t USING(site,player)
   WHERE p.nqp>={a.nmin_sa}
   GROUP BY p.site,p.player,t.ntot;""")

df=con.execute("""SELECT r.site,r.player,r.n_tr,r.n_te,r.bb100_tr,r.bb100_te,
   coalesce(a.edge,0) edge, coalesce(b.skill,0) skill, coalesce(b.cov,0) covB
   FROM cohort c JOIN realized r USING(site,player)
   LEFT JOIN edgeA a USING(site,player) LEFT JOIN skillB b USING(site,player)""").fetchdf()
tr=df.bb100_tr.values; te=df.bb100_te.values; eA=df.edge.values; sB=df.skill.values
print(f"state={S} split_day={a.split_day} cohort={ncoh}  (train>={a.min_train_hands}h,test>={a.min_test_hands}h)")
print(f"mean coverage of measure B = {df.covB.mean():.3f}")
print(f"CEILING   Spearman(bb100_tr, bb100_te)  = {spear(tr,te):.3f}")
print(f"(A) edge  Spearman(edge_tr,  bb100_te)  = {spear(eA,te):.3f}")
print(f"(B) skill Spearman(skill_tr, bb100_te)  = {spear(sB,te):.3f}")
def z(v): return (rk(v)-rk(v).mean())/rk(v).std()
comb=z(eA)+z(sB)
print(f"(A+B)     Spearman(combined,  bb100_te)  = {spear(comb,te):.3f}")
print(f"    in-sample: edge~tr={spear(eA,tr):.3f}  skill~tr={spear(sB,tr):.3f}")
print(f"    edge~skill (train) = {spear(eA,sB):.3f}")
for th in (3000,5000):
    m=df.n_te.values>=th
    if m.sum()>=100:
        print(f"  [test>={th}, n={m.sum()}] ceiling={spear(tr[m],te[m]):.3f}  A={spear(eA[m],te[m]):.3f}  B={spear(sB[m],te[m]):.3f}")
json.dump({"cohort":int(ncoh),"ceiling":spear(tr,te),"A_edge":spear(eA,te),"B_skill":spear(sB,te),
           "params":vars(a)}, open(f"report/holdout2_{S}.json","w"), indent=2)
print("wrote report/holdout2_"+S+".json")
