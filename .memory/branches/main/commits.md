# main

**Purpose:** Main project memory branch

---

## Commit 2026-09-14T07:15:17Z — Poker comparison ACPC policy/range progress

### Branch Purpose
Main project memory branch for the poker-player-comparison research repo.

### Previous Progress Summary
This is the first manual Brain commit after initializing `.memory/` in the repo. The project investigates empirical poker-player decision quality without a GTO/superhuman solver, using observed hand-history policies on common-support states.

### This Commit's Contribution
Captured the current research state after major ACPC/Pluribus work:

- Pluribus replay bug found/fixed: dealt hole-card actions (`d dh`) were initially ignored, making Pluribus policies public-only despite full hole cards being present. Replay now captures `hero_hole` and `hero_hole_class`.
- ACPC parser added: `src/parse_acpc_txt.py` parses `C:\Users\vince\Downloads\acpc_2014_nl_sample.zip` converted PokerStars HU logs into the repo parquet schema.
- ACPC no-rake bug fixed: `replay.py` now treats ACPC as rake-free when exact finishing stacks are absent; ACPC money conservation is exact after rebuild.
- ACPC processed dataset: 576,000 HU hands, 3,076,968 decisions, 1,152,000 hand-player rows, 4 bots, 100% hole-card coverage.
- Actual ACPC profit: Tartanian7 +3.09 bb/100; Hyperborean_iro -0.20; Prelude -1.23; Slumbot -1.67. Pairwise actual: Tartanian7 beats all; Hyperborean beats Prelude/Slumbot; Slumbot beats Prelude.
- Toy full-hand policy simulator (`src/simulate_policy_matchups.py`) was built and repeatedly improved, but should not be trusted: even with random deals, strict seen-state rejection, exact observed sizing, made-hand/board buckets, and opponent-specific policies, it remains anti-correlated with actual ACPC profit. The failure is likely wrong reach/transition dynamics from stitching local empirical policies into fake full hands.
- More defensible method implemented in `src/policy_bootstrap_eval.py`: pairwise common-support empirical continuation scoring using the same eval-state distribution and `Q_pop(S,a)` historical rewards.
- Approximate range features implemented in `src/range_features.py`: empirical public-context ranges, range-relative hand strength percentile bins, wetness bins, dynamicness proxy bins, outputting `d_range.s_range`.
- Full ACPC approximate range feature build produced 674,224 range feature rows and `corr(W,D) ≈ -0.103`, so W/D are not redundant under the proxy.
- Current approximate `s_range` results are still negative on ACPC (population weighting nmin 3/10 both anti-correlated), so do not claim success.
- Latest audit of 100 random ACPC hands against `s_range` policy: 713 decisions; mean actual-action policy probability 50.5%, median 54.1%; top-action accuracy by street: preflop 64.9%, flop 77.4%, turn 60.1%, river 61.0%. Biggest policy misses are low-frequency aggressive deviations: actual rare bets/raises where top policy is often check/call.

### Next Step
Replace proxy range/W/D features with true equity/range estimation, possibly borrowing from `C:\Users\vince\programming\projects\apex-poker`, and run sparsity/common-support diagnostics before further Monte Carlo. Continue to prefer empirical continuation/pairwise comparisons over fake full-hand simulation unless a validated Markov transition model exists.
