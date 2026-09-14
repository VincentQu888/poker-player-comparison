# ACPC 2010 LIMIT sample pipeline

Built a fixed-limit parser/replay smoke path before attempting the full 87M-hand dataset.

## Commands run

```bash
python src/parse_acpc_2010_limit.py --self-test
rm -rf data/acpc2010_limit_sample
python src/parse_acpc_2010_limit.py --limit-files 0 --sample-files 60 --out-dir data/acpc2010_limit_sample/hands
python src/run_replay.py --hands-dir data/acpc2010_limit_sample/hands --dec-dir data/acpc2010_limit_sample/decisions --hand-player-dir data/acpc2010_limit_sample/hand_player --workers 4
python src/build_states.py --decisions 'data/acpc2010_limit_sample/decisions/*.parquet' --db data/acpc2010_limit_sample/analysis.duckdb
```

## Parser/replay validation

- Parsed 60 evenly sampled `.phhs` files.
- Output hands: 180,000
- Replay output: 1,227,169 decisions / 360,000 hand-player rows
- Money conservation: max absolute per-hand net sum = 0
- `net_source`: `finishing`, via `_results` converted to finishing stacks
- Players covered: 15

## Sample policy-eval signal

Report: `report/acpc_2010_limit_sample_policy_eval.txt`

At `nmin=10`:

| state | Pearson | Spearman |
|---|---:|---:|
| s_core | 0.687 | 0.160 |
| s_fine | 0.694 | 0.160 |
| s_hole | 0.915 | 0.578 |
| s_sim | 0.974 | 0.731 |
| s_pdf | 0.892 | 0.264 |

This confirms the old problem was largely the weak 4-bot NL validation target. The 2010 LIMIT data is strong enough to show a signal even on a 180k-hand smoke sample. Do not over-interpret exact correlations yet: sample file selection is sparse across matchups and fixed-limit semantics still deserve a fuller validation pass.

## Next step

Run the same parser/replay/build path on the full extracted 2010 `2P_LIMIT` set, or a larger balanced sample by matchup if runtime/storage matters.
