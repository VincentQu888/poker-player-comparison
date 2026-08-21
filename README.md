## incredibly vibecoded experiment i wanted to try

# Poker player comparison

Can we rank online-poker players by **empirical decision quality** from hand
histories **without** building a GTO/superhuman solver? This repo is a full
autoresearch investigation on the UofT CPRG PHH / HandHQ dataset
(~21.6M obfuscated No-Limit Hold'em cash hands, 6 sites, July 2009) that answers
that question — and, importantly, documents why the obvious approaches fail.

**TL;DR verdict: NEEDS CHANGES.** A solver-free ranking is *possible* but severely
constrained, because **hole cards are essentially unobservable** (revealed only at
showdown) and the sample window is short and high-variance. The naive "value each
player's action mix by population outcomes" estimator is confounded and collapses
into an **aggression meter**; a corrected like-for-like estimator recovers only a
partial, noisy slice of true skill.

> Note: the raw data and a couple of side artifacts are intentionally **not** in
> this repo (see [Data](#data)). Everything here is code + aggregated findings.

## The question

Estimate each player's policy `P(action | state)` and compare players on shared
states to see whose decisions produce the most value — cash only, per-site
anonymous IDs treated as players.

## Key findings

1. **Hole cards are the wall.** Only **3.8%** of hand-player rows ever reveal cards,
   and only at showdown. Propagated to decisions, just **10%** have a known hero
   hand — but **0% of folds** (52% of all decisions) and most no-showdown wins never
   reveal. It's missing-not-at-random (endogenous selection), so *more of the same
   data cannot fix it*. => the decision state must be built from **public
   observables only**.

2. **The naive empirical-continuation estimator is confounded.** Scoring a player by
   `Σ_S w(S) Σ_a π_p(a|S) · Q_pop(S,a)` (population mean forward reward) rewards
   aggression, because population bets/raises are +EV on average (made with strong
   *hidden* ranges). Result: `corr(score, aggression) = 0.87` while
   `corr(realized bb/100, aggression) = -0.01`. This is unobserved-confounder bias
   in off-policy evaluation. **This approach was removed from the repo as invalid.**

3. **Board texture helps a corrected estimator.** A like-for-like measure
   (`Σ freq_p(S,a)·(Q_p(S,a) − Q_pop(S,a))`, i.e. "do you beat peers in the *same*
   public spot *and* same action") on a state enriched with **wetness** (made-hand
   density) and **dynamicness** (equity volatility) terciles — verified distinct
   (Spearman −0.07) — predicts out-of-sample future win-rate at Spearman **0.33**
   for well-sampled players, ~69% of the (noisy) reliability ceiling of 0.47.

4. **"Who wins more" with real money is mostly noise.** Ranking the ≥5k-hand cohort
   (4,188 players) by realized bb/100: median 95% CI half-width is **±12 bb/100**,
   only **8.9%** are resolvably winning and **14.9%** resolvably losing — **76% are
   statistically indistinguishable from break-even**. Head-to-head P(A beats B) is
   near 0.5 even for top players. Past win-rate predicts future win-rate at only
   Spearman 0.32 (0.47 for ≥5k test hands). Public state explains just ~8% of
   outcome variance — hidden cards and runout luck dominate.

See [`report/REPORT.md`](report/REPORT.md) for the verdict write-up and
[`report/FINDINGS.md`](report/FINDINGS.md) for the full detail.

## Pipeline (`src/`)

| stage | script | what it does |
|---|---|---|
| 1 parse | `parse_phh.py` | HandHQ `.phhs` text -> compact per-hand parquet |
| 2 replay | `replay.py`, `run_replay.py` | replay hands -> decisions + hand-player rows (money-conserving; memory-safe streaming) |
| 3 feasibility | `feasibility.py` | sample sizes, stakes, hole-card visibility, missing-card bias |
| 4 state/support | `build_states.py`, `support.py` | public-state buckets + sized actions; common-support analysis |
| 5 texture | `wetness.py` | wetness `W` and dynamicness `D` on canonical flops (eval7) |
| 6 validation | `holdout2.py`, `texture_holdout.py`, `residual.py` | temporal holdout, texture ablation, within-bucket residual predictiveness |
| 7 tournament | `tournament.py` | literal "who wins more" (real per-hand money, CIs, head-to-head, generalization) |

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# obtain + place the dataset (see Data), then:
python src/parse_phh.py            # -> research/data/hands/
python src/run_replay.py --workers 6
python src/build_states.py         # -> research/data/analysis.duckdb
python src/feasibility.py
python src/support.py
python src/wetness.py
python src/holdout2.py --state s_core
python src/texture_holdout.py
python src/tournament.py
```
(Scripts assume they're run from the `research/` directory; paths are relative to it.)

## Data

Not included (multi-GB, and upstream-owned). Source: the University of Toronto
Computer Poker Research Group PHH release of the HandHQ obfuscated online NLHE cash
hands. Place the `.phhs` files where `parse_phh.py` expects them
(`phh-dataset-src/data/handhq/...`) and regenerate `research/data/` locally.

Player IDs are the dataset's own per-site obfuscated tokens; all published numbers
here are aggregate stats keyed by those anonymized IDs.
