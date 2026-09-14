# Poker Player Comparison Memory

## Current State

This repo investigates empirical poker-player decision quality without a GTO/superhuman solver. Current active dataset is ACPC 2014 NL sample from `C:\Users\vince\Downloads\acpc_2014_nl_sample.zip`; PHH/HandHQ and Pluribus were also explored.

Recent work found that naive full-hand policy Monte Carlo is unreliable: even with seen-state rejection, random deals, exact observed sizing, opponent-specific policies, and richer state buckets, simulated pairwise results remain anti-correlated with actual ACPC profit. The more defensible path is the prompt's empirical common-support continuation/bootstrap comparison.

Implemented current pipeline pieces:
- `src/parse_acpc_txt.py` parses ACPC converted PokerStars HU logs into the repo hand parquet schema.
- `src/replay.py` now parses dealt hole cards (`d dh`) and ACPC no-rake settlement; emits `hero_hole`, `hero_hole_class`, `hero_hand_bucket`, `board_bucket`.
- `src/run_replay.py` schema includes the new decision fields.
- `src/build_states.py` builds `s_hole`, `s_sim`, `s_pdf` and carries sizing/pot columns needed by later analysis.
- `src/simulate_policy_matchups.py` contains the experimental toy simulator, but its results should not be trusted as a ranking method.
- `src/policy_bootstrap_eval.py` implements pairwise common-support empirical continuation scoring with shared eval-state distribution.
- `src/range_features.py` creates approximate range-relative features and `d_range.s_range`.

Current ACPC processed size:
- 576,000 heads-up hands
- 3,076,968 decisions
- 1,152,000 hand-player rows
- 4 bots: Hyperborean_iro, Prelude, Slumbot, Tartanian7
- hole-card coverage 100%
- money conservation exact after ACPC rake fix

Actual ACPC profit by bot:
- Tartanian7 +3.09 bb/100
- Hyperborean_iro -0.20 bb/100
- Prelude -1.23 bb/100
- Slumbot -1.67 bb/100

Actual pairwise: Tartanian7 beats all; Hyperborean beats Prelude/Slumbot and loses to Tartanian7; Slumbot beats Prelude.

## Key Findings

1. Pluribus bug fixed: PHH dealt-hole-card actions were initially ignored, so policies were public-only despite Pluribus having full private cards. After fixing, Pluribus decision hole coverage is 100%, but validation is still weak because there are only ~14 players.

2. ACPC parser and no-rake replay fix: ACPC logs have no rake and no `finishing_stacks`; replay previously applied a rake model. ACPC now uses 0 rake and conserves money.

3. Policy action prediction improves with private cards:
- Pluribus public `s_core`: ~69% action accuracy
- Pluribus hole-aware `s_hole`: ~75% action accuracy
- ACPC hole/range states predict actions better than public-only states, but action predictability does not equal profit ranking.

4. Toy full-hand simulation fails:
- 100k accepted seen-state random-deal rollouts stayed anti-correlated with actual ACPC pairwise profit.
- Fixes tried: no population fallback, random deck deals, exact observed action-size sampling, made-hand bucket, board bucket, opponent-specific policy, stricter state support.
- Conclusion: local empirical policies stitched through a hand-rolled transition model generate wrong reach distributions. Do not rely on `simulate_policy_matchups.py` for scientific ranking.

5. Empirical continuation/common-support evaluation is more aligned with the handoff prompt, but current approximate states still fail or are weak:
- `s_pdf` earlier produced weak positive correlation (~Pearson 0.35 / Spearman 0.22).
- Approximate `s_range` using H/W/D currently produced negative correlations on ACPC, indicating remaining state/value confounding or flawed proxies.

6. Latest random-hand policy-vs-actual audit over 100 ACPC hands with `s_range`:
- 713 decisions
- median actual-action policy probability 54.1%
- mean 50.5%
- top-action accuracy by street: preflop 64.9%, flop 77.4%, turn 60.1%, river 61.0%
- Biggest aggregate gaps: preflop actual calls more and folds less than policy expects; flop actual checks more; misses are mostly rare aggressive deviations (postflop bets/raises where policy top is check/call).

## Important Caveats

`src/range_features.py` is still a practical proxy, not true GTO/range-equity implementation. It uses empirical range distributions in public context and cheap hand/category strength proxies for H/W/D. It does not yet use the Apex Poker implementation for true equity/ranges.

The latest downloaded instructions require:
- range-relative hand-strength quintiles
- range-aware wetness
- dynamicness as expected next-card equity movement
- common support before MC
- same eval-state distribution
- continuation bootstrap/pairwise empirical comparison preferred unless transition model is credibly Markov-like

## Latest Data Acquisition

Found and selectively extracted authoritative ACPC archive data from Zenodo record 17136841 without downloading the full 20.3 GB ZIP. HTTP Range support was confirmed (`206 PARTIAL_CONTENT`). Remote central directory listing identified 2010 heads-up limit logs at `data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PLIMIT/2P_LIMIT/`. Extracted 29,000 `.phhs` files to ignored local data path `data/raw/acpc_2010_2p_limit/` using one 2.485 GB contiguous range covering 32.169 GB uncompressed logs. Summary: `report/acpc_2010_2p_limit_summary.md`; full listing: `report/acpc_2010_remote_zip_listing.txt`; scripts: `src/list_acpc_remote_zip.py`, `src/plan_acpc_2010_limit_ranges.py`, `src/extract_acpc_2010_limit.py`.

Reliability check for 2010 HU limit is complete via `src/acpc_2010_limit_reliability.py` and `report/acpc_2010_2p_limit_reliability.md`. It parsed 87,000,000 hands / 174,000,000 hand-player result entries directly from `_results` lines. Unlike the old 4-bot NL sample, this is a strong validation target: overall player split-half bb/100 Pearson 1.000 / Spearman 0.993, directed pairwise split-half Pearson 1.000 / Spearman 0.986. Top half-stable winners: Hyperborean_tbr, Sartre, GS6_iro; clear losers: PLICAS, ASVP, longhorn.

## Latest Diagnosis

`report/acpc_signal_diagnosis.md` and `src/diagnose_acpc_signal.py` now diagnose why current ACPC policy scores do not robustly correlate with winnings:
- replay integrity looks sound: 576k hands, 3.08M decisions, 100% decision hole-card coverage, exact money conservation;
- actual ACPC winnings are not a reliable validation target in this 4-bot sample: all pairwise 95% CIs include zero and split-half player/pairwise bb/100 is anti-correlated;
- `Q_pop(S,a)` policy bootstrap has a fundamental observational OPE/selection-bias problem, not just an implementation sign error;
- `s_pdf` positive correlation at `nmin=1` disappears/reverses under repeated common-support requirements, so it is sparse-state overfit;
- collapsing sized actions to base actions does not restore signal, so action bucket specificity is not the primary failure;
- an in-sample like-for-like residual score weakly ranks Tartanian7 first, confirming rewards are not simply reversed, but it is outcome-based and not a robust counterfactual policy-comparison fix.

## Next Useful Work

1. Full-run or larger balanced-sample the 2010 `2P_LIMIT` parser/replay/build pipeline now that the 60-file smoke path works.
2. For the full run, expect much larger output than the raw 32.2 GB PHH text because replay expands 87M hands into hundreds of millions of decisions; consider adding balanced-by-matchup sampling before full expansion.
3. Then run simple robust metrics first (like-for-like residual, fold/call/bet frequencies by public state) against stable 2010 rankings before attempting causal/counterfactual policy quality.
4. Stop tuning state/action buckets against the old 4-bot ACPC NL target; a positive result there is likely overfit.
