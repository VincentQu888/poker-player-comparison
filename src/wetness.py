#!/usr/bin/env python3
"""WETNESS & DYNAMICNESS on flops (documented proxies).

Range proxy: uniform full 2-card range (range-agnostic texture; a realistic
weighted range is future work). Hole cards are unobserved at ~96% of decisions,
so texture is necessarily range-estimated, not hero-specific.

W(flop) = P_R( best-5 category in {trips, straight, flush, full house, quads,
          straight flush} ) using hole+flop. (Two-pair and weaker excluded.)
D(flop) = Monte-Carlo mean absolute equity change flop->turn, averaged over hero
          hands and turn cards: E_c E_h | eq(h|flop+c) - eq(h|flop) | where eq is
          hero equity vs a random opponent over random runouts (draw-aware
          dynamicness). River D=0 by definition.
Computed on the 1,755 suit-isomorphic canonical flops, then mapped to every
observed flop and bucketed into empirical terciles weighted by decision frequency.
"""
import eval7, itertools, duckdb, numpy as np, pyarrow as pa, pyarrow.parquet as pq, time, random

RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = [r+s for r in RANKS for s in SUITS]
CARD = {c: eval7.Card(c) for c in DECK}
STRONG = {"Trips", "Straight", "Flush", "Full House", "Quads", "Straight Flush"}
ALLCOMBOS = list(itertools.combinations(DECK, 2))


def canon(cards):
    """suit-isomorphic canonical key for a set of card strings."""
    by_suit = {}
    for c in cards:
        by_suit.setdefault(c[1], []).append(RANKS.index(c[0]))
    groups = sorted(tuple(sorted(v)) for v in by_suit.values())
    return tuple(groups)


def strong_density(board_cards):
    bc = [CARD[c] for c in board_cards]
    blocked = set(board_cards)
    strong = 0; tot = 0
    for a, b in ALLCOMBOS:
        if a in blocked or b in blocked:
            continue
        tot += 1
        if eval7.handtype(eval7.evaluate(bc + [CARD[a], CARD[b]])) in STRONG:
            strong += 1
    return strong / tot if tot else 0.0


_RNG = random.Random(12345)


def hero_equity(board_cards, hero, n):
    """MC hero equity vs one random opponent over random remaining runout."""
    bc = [CARD[c] for c in board_cards]; hc = [CARD[hero[0]], CARD[hero[1]]]
    used = set(board_cards) | set(hero)
    avail = [c for c in DECK if c not in used]
    need = 5 - len(board_cards)
    wins = 0.0
    for _ in range(n):
        samp = _RNG.sample(avail, 2 + need)
        opp = [CARD[samp[0]], CARD[samp[1]]]; com = [CARD[x] for x in samp[2:]]
        hv = eval7.evaluate(bc + com + hc); ov = eval7.evaluate(bc + com + opp)
        wins += 1.0 if hv > ov else (0.5 if hv == ov else 0.0)
    return wins / n


def dynamicness(flop, K=16, S1=120, T=20, S2=30):
    """E_c E_h | eq(h|flop+turn) - eq(h|flop) | over sampled hero hands & turns."""
    blocked = set(flop)
    combos = [c for c in ALLCOMBOS if c[0] not in blocked and c[1] not in blocked]
    heroes = _RNG.sample(combos, min(K, len(combos)))
    diffs = []
    for h in heroes:
        used = set(flop) | set(h)
        turns = [c for c in DECK if c not in used]
        e_flop = hero_equity(flop, h, S1)
        for tc in _RNG.sample(turns, min(T, len(turns))):
            e_turn = hero_equity(flop + [tc], h, S2)
            diffs.append(abs(e_turn - e_flop))
    return float(np.mean(diffs)) if diffs else 0.0


def main():
    t0 = time.time()
    # 1) canonical flops -> W3, D
    seen = {}
    for flop in itertools.combinations(DECK, 3):
        k = canon(flop)
        if k not in seen:
            seen[k] = list(flop)
    print(f"{len(seen)} canonical flops; computing W/D...", flush=True)
    WD = {}
    for i, (k, flop) in enumerate(seen.items()):
        w3 = strong_density(flop)
        WD[k] = (w3, dynamicness(flop))
        if (i+1) % 300 == 0:
            print(f"  {i+1}/{len(seen)}  ({time.time()-t0:.0f}s)", flush=True)

    # 2) map observed flops
    con = duckdb.connect("data/analysis.duckdb", read_only=True)
    con.execute("PRAGMA threads=6;")
    flops = con.execute("""SELECT DISTINCT substr(board,1,6) f, count(*) n
        FROM d WHERE length(board)>=6 GROUP BY 1""").fetchall()
    rows = {"flop": [], "w3": [], "dscore": [], "n": []}
    bad = 0
    for f, n in flops:
        cs = [f[0:2], f[2:4], f[4:6]]
        try:
            k = canon(cs)
            w3, dd = WD[k]
        except Exception:
            bad += 1; continue
        rows["flop"].append(f); rows["w3"].append(w3); rows["dscore"].append(dd); rows["n"].append(int(n))
    print(f"mapped {len(rows['flop'])} observed flops ({bad} unmapped)")

    w = np.array(rows["w3"]); dsc = np.array(rows["dscore"]); nn = np.array(rows["n"], dtype=float)
    # empirical terciles weighted by decision frequency
    def wtiles(v, wts):
        order = np.argsort(v); vv = v[order]; ww = wts[order]
        cum = np.cumsum(ww)/ww.sum()
        t1 = vv[np.searchsorted(cum, 1/3)]; t2 = vv[np.searchsorted(cum, 2/3)]
        return t1, t2
    w1, w2 = wtiles(w, nn); d1, d2 = wtiles(dsc, nn)
    wtile = np.where(w <= w1, 0, np.where(w <= w2, 1, 2))
    dtile = np.where(dsc <= d1, 0, np.where(dsc <= d2, 1, 2))
    rows["wtile"] = wtile.tolist(); rows["dtile"] = dtile.tolist()

    # distinctness (decision-weighted Spearman of W vs D)
    def rk(v):
        _, inv, cnt = np.unique(v, return_inverse=True, return_counts=True)
        o = v.argsort(); r = np.empty(len(v)); r[o] = np.arange(len(v))
        s = np.zeros(len(cnt)); np.add.at(s, inv, r); return (s/cnt)[inv]
    rw, rd = rk(w), rk(dsc)
    def wcorr(x, y, wt):
        xm=np.average(x,weights=wt); ym=np.average(y,weights=wt)
        return np.average((x-xm)*(y-ym),weights=wt)/np.sqrt(np.average((x-xm)**2,weights=wt)*np.average((y-ym)**2,weights=wt))
    print(f"W range: {w.min():.3f}..{w.max():.3f}  D range: {dsc.min():.4f}..{dsc.max():.4f}")
    print(f"decision-weighted Spearman(W, D) = {wcorr(rw, rd, nn):.3f}  (distinct if |rho|<~0.7)")
    print(f"W terciles cut at {w1:.3f}, {w2:.3f}; D terciles at {d1:.4f}, {d2:.4f}")

    tbl = pa.table({k: rows[k] for k in ["flop","w3","dscore","n","wtile","dtile"]})
    pq.write_table(tbl, "data/flop_texture.parquet")
    print("wrote data/flop_texture.parquet;", f"{time.time()-t0:.0f}s total")


if __name__ == "__main__":
    main()
