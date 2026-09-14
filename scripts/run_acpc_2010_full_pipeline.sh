#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs report
LOG="logs/acpc_2010_full_pipeline.log"

{
  echo "[START] $(date -Is) ACPC 2010 full pipeline"
  echo "[PARSE] $(date -Is)"
  python -u src/parse_acpc_2010_limit.py --limit-files 0 --out-dir data/acpc2010_limit_full/hands --part-size 100000

  echo "[REPLAY] $(date -Is)"
  python -u src/run_replay.py \
    --hands-dir data/acpc2010_limit_full/hands \
    --dec-dir data/acpc2010_limit_full/decisions \
    --hand-player-dir data/acpc2010_limit_full/hand_player \
    --workers 6

  echo "[BUILD_STATES] $(date -Is)"
  python -u src/build_states.py \
    --decisions "data/acpc2010_limit_full/decisions/*.parquet" \
    --db data/acpc2010_limit_full/analysis.duckdb

  echo "[POLICY_EVAL] $(date -Is)"
  for st in s_core s_fine s_hole s_sim s_pdf; do
    echo "=== $st ==="
    python -u src/policy_bootstrap_eval.py \
      --db data/acpc2010_limit_full/analysis.duckdb \
      --table d \
      --state "$st" \
      --nmin 10 \
      --hand-player-glob "data/acpc2010_limit_full/hand_player/*.parquet"
  done > report/acpc_2010_limit_full_policy_eval.txt

  echo "[DONE] $(date -Is)"
} >> "$LOG" 2>&1
