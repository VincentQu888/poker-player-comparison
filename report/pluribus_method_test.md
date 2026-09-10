# Pluribus 10k method test

Source: `https://github.com/uoftcprg/phh-dataset`, `data/pluribus` sparse checkout.

## Pipeline run

```bash
python src/parse_pluribus_phh.py
python src/run_replay.py --workers 2
python src/build_states.py
python src/feasibility.py
python src/holdout2.py --state s_core --split_day 1 --min_eligible 3 --min_train_hands 100 --min_test_hands 100 --nmin 3 --nmin_sa 2
python src/holdout2.py --state s_fine --split_day 1 --min_eligible 3 --min_train_hands 100 --min_test_hands 100 --nmin 3 --nmin_sa 2
python src/tournament.py
```

## Data loaded

- Hands parsed: 10,000
- Hand-player rows: 60,000
- Decisions: 91,356
- Players: 14
- Net source: `finishing` for all rows after fixing replay to trust exact `finishing_stacks` when present.
- Money conservation: exact zero-sum across all 10,000 hands.

## Holdout result

Synthetic split: first 5,000 PHH files as train day 1, last 5,000 as test day 2.

| state | cohort | B coverage | ceiling Spearman train winrate→test winrate | A edge→test | B skill→test | A+B→test |
|---|---:|---:|---:|---:|---:|---:|
| `s_core` | 12 | 0.933 | -0.245 | -0.021 | -0.189 | -0.204 |
| `s_fine` | 12 | 0.912 | -0.245 | 0.028 | -0.084 | -0.060 |

## Verdict

The pipeline runs on the full Pluribus 10k PHH set, but this method does **not** validate as a ranking method on this dataset. The out-of-sample correlations are near zero or negative, and even raw train winrate has negative holdout correlation.

## Errors / limitations found

1. `replay.py` previously ignored exact `finishing_stacks` and reconstructed net with a rake model. That was wrong for Pluribus/no-rake data; fixed by using exact finishing stacks when they conserve total chips.
2. `support.py` assumes large cohorts with `eligible >= 20`, so its common-state coverage report is not meaningful for Pluribus' 14-player pool.
3. `tournament.py` has a hardcoded day-18 temporal split, so its generalization section is not meaningful for the synthetic day 1/2 Pluribus split.
4. The sample is too small in player count for stable rank validation: only 12 players pass the relaxed train/test hand thresholds.

## Next smallest useful fix

Add a Pluribus-specific evaluation script with repeated random hand-level splits instead of the HandHQ temporal split. One split is too noisy for a 14-player pool.
