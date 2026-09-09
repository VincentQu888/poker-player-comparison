# HCL player methodology smoke test

Input: `report\livestream\hcl_full_hand_dataset.jsonl` (152 card-clean hands)
Names/actions are conservative OCR+caption signals; unknown stays unknown.

| player | named hands | avg preflop equity | known caption/overlay actions | showdowns | win share |
|---|---:|---:|---:|---:|---:|
| LUCKY | 32 | 0.497 | 137 | 0 | 0.000 |
| GARRETT | 24 | 0.450 | 105 | 1 | 0.000 |
| MATT | 16 | 0.488 | 41 | 0 | 0.000 |
| DYLAN | 12 | 0.487 | 55 | 1 | 1.000 |
| KRISH | 12 | 0.598 | 31 | 1 | 1.000 |
| DR ELI | 5 | 0.572 | 17 | 1 | 0.500 |

Verdict: player grouping now works for a small audited subset, but OCR coverage is still too sparse for ranking claims.
