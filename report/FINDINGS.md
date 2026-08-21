# Empirical Poker Decision-Quality Ranking — Findings

Dataset: UofT CPRG PHH / HandHQ obfuscated online NLHE cash, 6 sites, 2009.
Player identity = (site, player); obfuscated IDs are persistent within a site.

## Stage 1 — Parse (DONE)
- 21,606,087 NLHE cash hands parsed to `data/hands/` (10 shards, ~1.2 GB).

## Stage 2 — Replay (DONE)
- 174,164,978 decisions -> `data/decisions/`
- 116,861,965 hand-player rows -> `data/hand_player/`
- Money conservation verified: **0 hands create money**; per-hand net sum mean = -0.30 BB
  (pure rake), p50 ~ 0, p01 = -3.0 (rake cap). 96% of hand-players have a resolved outcome.
- Fix vs the crashed run: streaming row-group batches + periodic flush + fewer workers.
  Peak RAM ~6.6 GB across 6 workers (was OOM from `to_pydict()` on whole 2M-hand shards).

## Stage 3 — Feasibility

### Volume by site (hand-players / distinct players)
PS 48.4M / 145k · IPN 30.4M / 30.6k · PTY 16.8M / 36.6k · ONG 7.6M / 9.2k ·
FTP 6.9M / 36.8k · ABS 6.8M / 21.8k. Total 280,389 (site,player) IDs.

### Sample sizes per player (hands)
median 60, p75 194, p90 640, p99 7,426, max 106,809, mean 417.
Players with >= 1k hands: **19,359** (72% of all hand volume); >=5k: **4,371** (45%);
>=10k: **1,876** (30%); >=25k: 318; >=50k: 39.
Decisions per player: median 113, p90 1,080, p99 10,031; >=1k dec: 30,121; >=5k: 6,306.
=> A well-sampled core of a few thousand players exists. Policy estimation is feasible
   for these players **provided the state space does not fragment their data away**.

### Hole-card visibility — PIVOTAL CONSTRAINT
- Hole cards known for only **3.8%** of hand-players, and **only at showdown**
  (frac shown | no showdown = 0.0; frac reached showdown = 5.9%; shown | showdown = 64%).
- Shown hands are severely selection-biased: mean net +5.85 BB (shown) vs -0.29 BB (not),
  mean invested 20.2 BB vs 1.58 BB. i.e. we mostly see the cards of players who went deep
  and won.

**Design consequence (documented deviation):** the hero's actual hand is unobserved at
~96% of decisions, so we CANNOT bucket decisions by the hero's realized hand-strength
percentile, and we cannot condition the policy on hero holdings. We therefore define the
decision state **S from public observables only** (street, position, pot type, action
faced, previous sizing, SPR, active/among-to-act counts, board texture). The estimated
policy pi_p(a | public S) marginalizes over the player's unobserved range — which is
exactly the object we want for comparing players on *shared observable* states.
Board-texture features (wetness, dynamicness) remain computable because they depend on the
public board + *estimated* ranges, not the hero's actual hand.

This also means runout-luck removal via "known cards" (objective EVALUATION) is only
possible at showdowns; the primary EV estimator is the empirical continuation bootstrap,
which averages over unobserved cards by construction.

### Outcome source distribution (per-hand, applied to all seats)
uncontested 96.5M · showdown_eval 8.4M · sd_heuristic 7.0M · unknown 4.8M (NULL net,
~4%) · winnings_winner 0.11M.

## Stage 4b — Common support (NOT the bottleneck)
Cohort >=5k hands (4,249 players): 99% of decisions have >=3 same-state obs per
player (96.5% at >=10). 324 core states shared by >=10% of the cohort cover 98%
of decisions. Public-state policy comparison is well-supported.

## Stages 5-7 — Policy EV & validation (core result)
Reward convention makes Q(S,a)=mean forward reward_bb a proper empirical
action-value (fold => forward EV ~ 0). EV_p = sum_S w(S) sum_a pi_p(a|S) Q(S,a);
edge_p = EV_p - EV_pop, differentiating players only where they have >=NMIN obs
(else backoff to population policy). Cohort >=5k, s_core, nmin=10, freq weights:
1,326 common states, EV_pop baseline, edge sd ~0.057 bb/decision.

**Data window is a single 26 days (2009-07-01..07-26); per-hand net sd = 8.3 bb**,
so realized bb/100 over a few thousand hands is dominated by variance.

Temporal holdout (train day<=18, test day>18; train>=2000h, test>=1000h; n=2031):
- Reliability ceiling  Spearman(bb100_train, bb100_test) = 0.319 (0.45-0.47 for
  players with >=3-5k test hands) -- past winrate barely predicts future winrate.
- Policy edge          Spearman(edge_train,  bb100_test) = 0.150 (0.19-0.23 for
  higher test-sample subsets).
=> The public-state policy-EV edge is a genuine, out-of-sample predictor of future
   winrate, but only ~half as informative as a player's own past winrate. It
   misses everything hole-card / hand-reading dependent (unobservable here), and
   Q(S,a) conflates action merit with the hand-selection of players who took a.

## Aggression confound (why Method A fails)
Spearman(edge_A, aggression_freq) = **0.873**; Spearman(realized bb100, aggression)
= -0.009. Because hero cards are unobserved, population Q(S,a) is high for bets/raises
(they're made with strong ranges), so Method A rewards *any* player who is more
aggressive, regardless of their actual holdings. The specified estimator collapses
to an aggression proxy with ~0 relation to profitability. => Method A is biased.

## Corrected estimator (Method B) + board texture
Method B = conditional like-for-like performance: sum_{S,a} freq_p(S,a)(Qp(S,a)-Qpop(S,a))
-- do you beat peers in the SAME public state AND SAME action. B is uncorrelated with A
(Spearman -0.06), i.e. a different construct.

WETNESS W(flop)=strong-made-hand density (exact, uniform-range proxy) and DYNAMICNESS
D(flop)=MC mean |equity change| flop->turn vs random range. Verified DISTINCT:
decision-weighted Spearman(W,D) = -0.068. Empirical terciles.

Out-of-sample (train day<=18 -> test winrate day>18), Spearman, higher-sample subset in []:
  ceiling (bb_tr->bb_te)     0.319   [test>=5k: 0.474]
  A edge                     0.150   [0.230]
  B s_core                   0.125   [0.266]
  B s_core + texture         0.180   [0.309]
  B s_fine  + texture        0.192   [0.326]   (~69% of ceiling)
=> Board texture (W/D) adds genuine, out-of-sample discriminative power. A corrected
   estimator on a well-featured public state recovers most of the noisy reliability
   ceiling with NO solver and NO hole cards.

## Precision vs validity (Method A results)
Cohort >=5k (4,249 players): 33% significantly above / 45% below baseline (hand-clustered
SE); 77% of random pairs have a significant EV difference. So Method A is a *precise*
measurement -- but of aggression, not profitability. Bradley-Terry/Elo is degenerate here
(SEs tiny vs edge spread => near-deterministic pairwise dominance => it just recovers the
edge total order); it adds nothing over the edge ranking.

## Documented deviations / future work
- Hero hand-strength-percentile bucket: infeasible (hole cards unobserved) -> public-state
  marginalization used instead.
- Preflop pot-relative sizing collapses (tiny blind pot); switched size buckets to
  increment/(pot+call). Preflop size resolution still coarse.
- Ranges: uniform proxy for W/D; hero/opponent/asymmetric range variants and RMS-movement
  D not tested. Turn/river texture not computed (flop only).
- Evaluation used analytic hand-clustered SEs rather than literal resampling bootstrap
  (equivalent first-order); Markov P(S_next|S,a) transition simulation (option B) not run
  (compression not verified Markov). Validation target (realized winrate) is very noisy
  (single 26-day window, per-hand sd 8.3bb), capping all measurable correlations.

## Within-bucket residual predictiveness (are the buckets adequate?)
eta^2 (variance explained) as state granularity refines, cohort >=5k:
- REWARD:  s_core 0.071 -> s_fine 0.075 -> +W/D texture 0.085. Public state explains
  only ~7-9% of outcome variance; refining adds a little (texture +0.009). Outcome is
  dominated by unobserved hole cards + runout luck.
- P(fold): s_core 0.420 -> s_fine 0.437 -> +texture 0.438. Public state explains ~42%
  of the fold decision; refinement gives diminishing returns.
=> Omitted variables (faced size, active count, board texture) do carry residual signal,
   confirming the buckets are an approximation -- but the dominant omitted variable is the
   hero's hole cards, which are unobservable in this data. This bounds any public-state
   method and is the root reason it cannot match a card-aware or long-run-winrate ranking.

## REVISION — reward model deleted; literal "who wins more" tournament (real money)
The population-continuation reward model Q(S,a) (Method A) was removed as confounded
(scripts ev.py/results.py/holdout.py deleted). Per-decision reward_bb is also the wrong
unit for "who wins more": its mean is ~1.35 bb/decision because winners take many more
decisions per hand (each a positive forward-profit row) while folders contribute a single
0 — decision-count selection inflates it (and favored low-variance sites like IPN).

Real money is per-HAND net_bb (mean ~ -0.05 bb = rake). Hand-level tournament
(src/tournament.py), cohort >=5k hands = 4,188 players, winrate = bb/100 hands:
- Spread p5=-18.6, median=-1.0, p95=+16.3 bb/100.
- Median 95% CI half-width = +/-12.0 bb/100 at median 8,809 hands -- huge vs the spread.
- Resolvably winning (CI low>0): 371 (8.9%); resolvably losing: 625 (14.9%);
  => **76% of players are statistically indistinguishable from break-even.**
- Head-to-head P(A beats B): even #1 vs #6 ~ 0.67; adjacent players ~0.50 (coin flips).
- Stakes-matched winrate ~ raw (Spearman 0.76): matching doesn't change the story.
- Generalization (train days<=18 -> test days>18): Spearman 0.319 (0.47 for >=5k test hands).
=> "Who wins more" is answerable in principle but dominated by variance at these sample
   sizes; a single 26-day window can't resolve most players from break-even, and matching
   on public spots/stakes can't fix it (public state explains only ~8% of outcome variance).
