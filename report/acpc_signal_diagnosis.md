# ACPC signal diagnosis

## Data integrity
|         hands |      decisions |   hand_player_rows |   max_abs_money_error |   decision_hole_coverage |
|--------------:|---------------:|-------------------:|----------------------:|-------------------------:|
| 576000.000000 | 3076968.000000 |     1152000.000000 |              0.000000 |                 1.000000 |

Decision net sources:
| net_source    |   decisions |
|:--------------|------------:|
| uncontested   |     2092831 |
| showdown_eval |      984137 |

## Actual winnings target reliability
| player          | opponent        |   hands |   bb100 |   se_bb100 |      z |
|:----------------|:----------------|--------:|--------:|-----------:|-------:|
| Hyperborean_iro | Prelude         |   96000 |   0.715 |      5.323 |  0.134 |
| Hyperborean_iro | Slumbot         |   96000 |   1.653 |      4.610 |  0.358 |
| Hyperborean_iro | Tartanian7      |   96000 |  -2.955 |      4.642 | -0.637 |
| Prelude         | Hyperborean_iro |   96000 |  -0.715 |      5.323 | -0.134 |
| Prelude         | Slumbot         |   96000 |  -1.088 |      4.566 | -0.238 |
| Prelude         | Tartanian7      |   96000 |  -1.881 |      4.576 | -0.411 |
| Slumbot         | Hyperborean_iro |   96000 |  -1.653 |      4.610 | -0.358 |
| Slumbot         | Prelude         |   96000 |   1.088 |      4.566 |  0.238 |
| Slumbot         | Tartanian7      |   96000 |  -4.449 |      4.043 | -1.100 |
| Tartanian7      | Hyperborean_iro |   96000 |   2.955 |      4.642 |  0.637 |
| Tartanian7      | Prelude         |   96000 |   1.881 |      4.576 |  0.411 |
| Tartanian7      | Slumbot         |   96000 |   4.449 |      4.043 |  1.100 |

All six unordered matchups have 95% confidence intervals that include zero; the largest |z| is 1.100.

### Split-half stability of the target
Overall player bb/100 split-half: Pearson -0.802, Spearman -1.000.
Unordered pairwise bb/100 split-half: Pearson -0.723, Spearman -0.486.

| player          |   half0 |   half1 |     n0 |     n1 |
|:----------------|--------:|--------:|-------:|-------:|
| Hyperborean_iro |    0.92 |   -1.32 | 144068 | 143932 |
| Prelude         |   -6.05 |    3.58 | 143758 | 144242 |
| Slumbot         |   -2.82 |   -0.52 | 144126 | 143874 |
| Tartanian7      |    7.94 |   -1.75 | 143974 | 144026 |

## Current policy-bootstrap reproduction
| table   | state   |   nmin |   pairs |   pearson |   spearman |
|:--------|:--------|-------:|--------:|----------:|-----------:|
| d       | s_pdf   |      1 |      12 |     0.793 |      0.832 |
| d       | s_pdf   |      3 |      12 |     0.347 |      0.224 |
| d       | s_pdf   |     10 |      12 |    -0.559 |     -0.727 |
| d       | s_pdf   |     50 |      12 |    -0.277 |     -0.441 |
| d_range | s_range |     10 |      12 |    -0.503 |     -0.448 |
| d       | s_sim   |     10 |      12 |    -0.277 |     -0.175 |

`s_pdf` only looks good at `nmin=1`; requiring repeated per-player support removes or reverses the signal. That is the fingerprint of sparse-state noise, not a stable ranking signal.

### Action granularity check
| state   |   nmin | action_column   |   pairs |   pearson |   spearman |
|:--------|-------:|:----------------|--------:|----------:|-----------:|
| s_pdf   |     10 | a               |      12 |    -0.559 |     -0.727 |
| s_pdf   |     10 | act_base        |      12 |    -0.645 |     -0.629 |

Collapsing sized actions to base actions does not restore signal, so the current failure is not primarily caused by over-specific bet-size buckets.

## Action-value confounding check
| a   |      n |   q_bb |   sd_bb |
|:----|-------:|-------:|--------:|
| r1  |   1102 | 23.722 |  80.088 |
| r2  |  12238 | 10.986 |  50.861 |
| b4  |  38473 |  9.263 |  33.251 |
| b3  | 105700 |  7.083 |  25.747 |
| b1  | 143234 |  6.267 |  24.450 |
| b2  | 166016 |  5.771 |  23.533 |
| x   | 989157 |  3.219 |  15.303 |
| r4  | 239049 |  2.138 |  26.820 |
| c   | 594368 |  1.853 |  25.076 |
| r3  | 322166 |  1.599 |  20.771 |
| f   | 465465 |  0.000 |   0.000 |

Population `Q(S,a)` is not a causal action value. Folds are mechanically 0 continuation bb, while bet/raise buckets are often strongly positive because those actions are selected with stronger private ranges and favorable opponent states. Valuing another player by this table rewards matching population selection effects, not necessarily better decisions.

## Exploratory like-for-like residual score
| state   |   pearson |   spearman | ranking                                       |
|:--------|----------:|-----------:|:----------------------------------------------|
| s_core  |     0.521 |      0.200 | Tartanian7, Slumbot, Prelude, Hyperborean_iro |
| s_sim   |     0.614 |      0.400 | Tartanian7, Prelude, Slumbot, Hyperborean_iro |
| s_pdf   |     0.719 |      0.400 | Tartanian7, Prelude, Slumbot, Hyperborean_iro |
| s_range |     0.480 |      0.400 | Tartanian7, Prelude, Slumbot, Hyperborean_iro |

This finds a weak positive player-level signal and usually ranks Tartanian7 first, but it is in-sample and outcome-based. It is evidence that replay/reward signs are not obviously reversed; it is not a robust counterfactual policy-comparison fix.

## Diagnosis
1. **The actual-winnings target is not reliable enough in this 4-bot ACPC sample.** Split halves are anti-correlated and pairwise standard errors are as large as, or larger than, the measured edges.
2. **The current method has a fundamental causal/OPE problem.** `Q_pop(S,a)` is an observational continuation mean. Even with hole-card buckets, it still contains selection effects from unmodeled private blockers, exact board/runout, opponent strategy, and future reach distribution.
3. **Sparse state specificity makes the apparent signal unstable.** Exact-board/hole-heavy `s_pdf` is positive at `nmin=1` but collapses as soon as common support requires repeated observations.
4. **Action granularity is not the primary cause.** Using base actions instead of sized buckets still fails at the repeated-support setting.
5. **No gross replay sign error is evident.** Money is conserved, hole coverage is 100%, and the residual score points in the expected direction; the failure is not simply reversed winnings or missing cards.

## Recommended stop condition
Do not tune more state/action buckets against this target. The next defensible step requires a more reliable label: more hands per matchup, repeated independent tournament seeds, or a dataset with enough players/time to validate on future winnings. Without that, a positive correlation can be manufactured by overfitting `nmin=1` sparse states but will not be robust.
