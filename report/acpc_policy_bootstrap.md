# ACPC policy bootstrap check

Implemented the PDF-style evaluation path that does not hand-roll full poker transitions:

- estimate empirical policies `pi(player action | common state)`
- restrict pairwise comparisons to common-support states
- evaluate both players on the same population-weighted state distribution
- score actions with historical continuation payoff `Q_pop(S,a)`

State variants tested:

- `s_sim`: structural + hole class + made-hand bucket
- `s_pdf`: `s_fine` + hole class + made-hand bucket + board bucket + players behind

## Results

```text
s_sim nmin=10:
pearson=-0.277 spearman=-0.175

s_pdf nmin=3:
pearson=0.347 spearman=0.224
```

`s_pdf` is the first variant that points in the right direction, but it is weak and not publication-grade.

## Main miss still remaining

The PDF asks for range-relative hand-strength quintiles plus range-aware wetness/dynamicness. Current implementation only uses cheap proxies:

- exact hole class
- made-hand bucket
- board texture bucket

That avoids a fake full-hand simulator, but it is not the full range model yet.
