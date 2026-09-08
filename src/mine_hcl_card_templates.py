#!/usr/bin/env python3
"""Mine HCL card-template candidates from contact sheets.

This is resumable and safe: it never guesses labels into card_templates. It writes
unique-looking unknown card crops to a review folder so labels can be added once
and reused forever.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from crop_hcl_overlay import crop_regions, load_layout
from hcl_auto_extract import CARD_FIELDS, load_card_templates, recognize_card

def split_contact_sheet(sheet) -> list[np.ndarray]:
    h, w = sheet.shape[:2]
    cell_h, cell_w = h // 2, w // 4
    return [sheet[y * cell_h : (y + 1) * cell_h, x * cell_w : (x + 1) * cell_w] for y in range(2) for x in range(4)]


def image_hash(crop) -> str:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
    return hashlib.sha1(small.tobytes()).hexdigest()[:12]


def is_blank_or_hidden(crop) -> bool:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(gray.std()) < 8 or float(gray.mean()) < 25


def mine(args: argparse.Namespace) -> list[dict[str, object]]:
    layout = load_layout(args.layout)
    templates = load_card_templates(args.templates)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    seen = {p.stem.split("__")[-1] for p in args.out_dir.glob("*.jpg")}
    rows: list[dict[str, object]] = []

    for sheet_path in sorted(args.frames_dir.glob("*.jpg")):
        if not sheet_path.name.startswith(args.prefix):
            continue
        sheet = cv2.imread(str(sheet_path))
        if sheet is None:
            continue
        for offset, frame in enumerate(split_contact_sheet(sheet)):
            for field, crop in crop_regions(frame, layout).items():
                if field not in CARD_FIELDS or is_blank_or_hidden(crop):
                    continue
                card, confidence = recognize_card(crop, templates)
                if card != "unknown" and confidence >= args.known_threshold:
                    continue
                digest = image_hash(crop)
                if digest in seen:
                    continue
                seen.add(digest)
                out = args.out_dir / f"{sheet_path.stem}__f{offset}__{field}__{digest}.jpg"
                cv2.imwrite(str(out), crop)
                rows.append({"path": str(out).replace("\\", "/"), "source_sheet": sheet_path.name, "offset_index": offset, "field": field, "best_known": card, "confidence": confidence})
    return rows


def write_review_sheet(candidates: list[dict[str, object]], out: Path) -> None:
    images = []
    for row in candidates[:200]:
        img = cv2.imread(row["path"])
        if img is None:
            continue
        img = cv2.resize(img, (120, 144), interpolation=cv2.INTER_CUBIC)
        cv2.putText(img, Path(row["path"]).stem[-12:], (4, 138), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        images.append(img)
    if not images:
        return
    while len(images) % 8:
        images.append(np.zeros_like(images[0]))
    rows = [cv2.hconcat(images[i : i + 8]) for i in range(0, len(images), 8)]
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.vconcat(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", type=Path, default=Path("report/livestream/frames"))
    parser.add_argument("--layout", type=Path, default=Path("report/livestream/hcl_overlay_layout.json"))
    parser.add_argument("--templates", type=Path, default=Path("report/livestream/card_templates"))
    parser.add_argument("--out-dir", type=Path, default=Path("report/livestream/template_candidates"))
    parser.add_argument("--manifest", type=Path, default=Path("report/livestream/template_candidates.jsonl"))
    parser.add_argument("--review-sheet", type=Path, default=Path("report/livestream/template_candidates_sheet.jpg"))
    parser.add_argument("--known-threshold", type=float, default=0.88)
    parser.add_argument("--prefix", default="hcl_ivey_dwan_garrett_")
    args = parser.parse_args()

    rows = mine(args)
    with args.manifest.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_review_sheet(rows, args.review_sheet)
    print(f"wrote {len(rows)} candidates to {args.out_dir}")


if __name__ == "__main__":
    main()
