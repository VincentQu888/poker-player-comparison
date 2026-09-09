# Livestream methodology smoke test

Input: `report\livestream\hcl_methodology_sample.jsonl` (152 clean extracted records)
Preflop equity: Monte Carlo, 500 boards per hand

| bucket | hands | avg preflop equity | 5-card-board showdowns | showdown win share |
|---|---:|---:|---:|---:|
| top_seat | 152 | 0.625 | 11 | 0.864 |
| bottom_seat | 152 | 0.375 | 11 | 0.136 |

Verdict: the card-state comparison plumbing works, but this dataset is not yet a real player-ranking input because player names, actions, and hand results are still missing/weak.
