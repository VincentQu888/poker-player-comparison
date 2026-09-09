# Livestream hand candidates

Source: Hustler Casino Live YouTube stream `bG7K_zq0MoQ` — Phil Ivey / Tom Dwan / Garrett Adelstein, $200/$400.

Files:

- `hcl_ivey_dwan_garrett_100_hands.csv` — review queue for manual verification.
- `hcl_ivey_dwan_garrett_100_hands.jsonl` — same queue with empty structured fields for cards/actions/results.

Each row is a candidate timestamp window from auto-caption action keywords. It is **not** a verified hand history yet. Open `review_url`, watch the overlay, and fill `hole_cards`, `board`, `actions`, and `result` in the JSONL or a corrected copy.

The raw video is not redistributed; only URLs, timestamps, and captions are stored.

- `hcl_ivey_dwan_garrett_extracted_hands.jsonl` — evidence packets with contact-sheet paths and action-like caption lines.
- `hcl_auto_hands.jsonl` — automatic HCL crop/OCR/template pipeline output. It marks unknown cards as `low_confidence_cards` and impossible repeated cards as `duplicate_cards`.
- `hcl_methodology_sample.jsonl` / `.csv` — current clean smoke-test dataset: 152 dense-window hands with no unknown or duplicate cards.
- `hcl_ivey_dwan_garrett_fullres_auto_ocr_merged.jsonl` — 162 larger contact-sheet OCR rows for player/action evidence; still noisy.
- `hcl_full_hand_dataset.jsonl` / `.csv` — conservative merged dataset: card-clean hands plus player/action evidence, with low-confidence names left as `unknown`.
- `player_methodology_smoke_test.md` — player-level smoke test over the conservative dataset.
- `hcl_overlay_layout.json` — fixed crop boxes for the HCL 640x360 overlay.
- `frames/` — contact sheets sampled from the video stream.
- `crops/` — sample crop set for checking the layout.

Run more/redo extraction with:

```bash
python src/extract_livestream_hands.py --limit 100
python src/hcl_auto_extract.py --limit 100
python src/filter_livestream_hands.py
python src/build_hcl_hand_dataset.py --ocr report/livestream/hcl_ivey_dwan_garrett_fullres_auto_ocr_merged.jsonl
python src/livestream_player_methodology_smoke.py --trials 300
```

OpenCV seeking against YouTube is slow; reruns skip existing frame sheets. For OCR chunks, use `src/hcl_auto_extract.py --offset N --limit 20` and merge JSONL rows by `hand_id`. Seed HCL card templates are in `card_templates/`; 46/52 cards are currently labeled from clear HCL crops across the original stream plus `hcl_ivey_mikki` / `hcl_million_dollar_late` checks. Missing: `2s`, `6h`, `7c`, `9d`, `Ks`, `Ts`. The dense 200-window original-stream pass produced `152/200` clean card-state records for methodology smoke tests.
