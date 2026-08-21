# Can we rank poker players by empirical decision quality without a solver?

**Dataset:** UofT CPRG PHH / HandHQ obfuscated online NLHE cash, 6 sites, July 2009.
21,606,087 hands -> 174,164,978 decisions / 116,861,965 hand-player rows. Player
identity = (site, player) (persistent within a site). All code in `research/src`,
all numbers in `research/report/*.json|csv`.

## KEY QUESTION
"On common empirical public poker states, whose observed policy produces the greatest
expected return against the other observed policies?"

## VERDICT: NEEDS CHANGES
The pipeline exactly as specified (estimate pi_p(a|state), evaluate by Monte-Carlo /
empirical continuation against population outcomes) is **biased and not valid** for ranking
players. But the underlying goal — ranking players by empirical decision quality with **no
GTO/superhuman solver** — **is achievable** with a corrected estimator, and the data is
**not** too sparse. The two binding constraints are (1) hole cards are essentially
unobserved, and (2) the 26-day window makes the validation target very noisy.

## Why the specified method fails
1. **Hole cards are unobservable.** Only **3.8%** of hand-players ever reveal cards, only at
   showdown, and those hands are massively selection-biased (mean net +5.85 vs -0.29 bb).
   So the hero's hand is unknown at ~96% of decisions: we cannot bucket by hero
   hand-strength percentile, and must define the state from **public observables** only.
2. **The empirical action-value is hand-selection-confounded.** With state public-only,
   Q(S,a) = population mean forward reward is high for bets/raises simply because, in the
   population, aggression is done with strong (unobserved) ranges. Scoring a player by
   sum_S w(S) sum_a pi_p(a|S) Q(S,a) therefore **rewards aggression per se**:
   Spearman(score, aggression frequency) = **0.87**, while Spearman(realized bb/100,
   aggression) = **-0.01**. The specified estimator collapses to an aggression proxy that
   does not track profitability. It is *precise* (33% of players significantly above / 45%
   below baseline; 77% of pairs separable via hand-clustered SEs) but measures the wrong
   thing. Bradley-Terry/Elo just recovers this (degenerate) total order.

## The change that works
Score players by **conditional like-for-like performance**:
  skill_p = sum_{S,a} freq_p(S,a) ( Q_p(S,a) - Q_pop(S,a) )
i.e. *given the same public state AND the same action, do you end up better than peers?*
This removes the aggression confound (it is uncorrelated with the specified score,
Spearman -0.06) and, on a public state enriched with **wetness** (made-hand density) and
**dynamicness** (equity volatility) terciles — verified distinct, Spearman(W,D) = -0.07 —
predicts **out-of-sample future win-rate** at Spearman **0.33** for well-sampled players.

### Validation (temporal holdout: train days 1-18 -> realized win-rate days 19-26)
Realized win-rate is very noisy here (single 26-day window; per-hand sd 8.3 bb), so the
right bar is the **reliability ceiling** = how well *past* win-rate predicts *future*
win-rate. Spearman, [subset with >=5k test hands]:

| estimator | all | [test>=5k] |
|---|---|---|
| reliability ceiling (past->future win-rate) | 0.319 | 0.474 |
| specified method A (policy vs pop Q) | 0.150 | 0.230 |
| corrected B, public state | 0.125 | 0.266 |
| corrected B + texture (s_core) | 0.180 | 0.309 |
| **corrected B + texture (s_fine)** | **0.192** | **0.326** |

The corrected, texture-featured estimator recovers ~**69%** of the (noisy) ceiling with no
solver and no hole cards. It still does **not beat simply using a player's own past
win-rate** — expected, since past win-rate embeds hole-card-dependent skill the public-state
model cannot see.

## Feasibility summary (not the bottleneck)
- Cohort >=5k hands: **4,249** players (19,359 have >=1k). For this cohort **99%** of
  decisions have >=3 same-state observations (96.5% at >=10); 324 core states shared by
  >=10% of the cohort cover 98% of decisions. Common support is ample.
- Outcomes: money conservation holds (0 hands create money; mean per-hand net -0.30 bb =
  rake); 96% outcome coverage.

## Answer to the KEY QUESTION
A defensible, solver-free ranking of decision quality on shared public states **is possible**,
but **not** via the specified "policy value against population outcomes" estimator (which
ranks aggression). Use conditional like-for-like performance on a public state that includes
board wetness/dynamicness. Because hole cards are unobserved and the sample window is short
and high-variance, such a ranking captures a real but partial (~2/3 of the noisy ceiling)
slice of true skill and should be treated as a *lower-variance complement* to, not a
replacement for, a long-run win-rate.

See `FINDINGS.md` for full detail and `src/` for the pipeline
(parse -> replay -> build_states -> support -> ev/results -> holdout/holdout2 ->
wetness -> texture_holdout).
