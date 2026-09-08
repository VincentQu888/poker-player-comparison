#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, default=Path('report/livestream/template_candidates.jsonl'))
    p.add_argument('--out', type=Path, default=Path('report/livestream/template_label_sheet.jpg'))
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--count', type=int, default=80)
    args = p.parse_args()
    rows = [json.loads(l) for l in args.manifest.read_text(encoding='utf8').splitlines() if l.strip()]
    rows = rows[args.start:args.start + args.count]
    cells = []
    for i, row in enumerate(rows, args.start):
        img = cv2.imread(row['path'])
        if img is None:
            continue
        img = cv2.resize(img, (160, 180), interpolation=cv2.INTER_CUBIC)
        cv2.putText(img, str(i), (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cells.append(img)
    while cells and len(cells) % 8:
        cells.append(np.zeros_like(cells[0]))
    sheet = cv2.vconcat([cv2.hconcat(cells[i:i+8]) for i in range(0, len(cells), 8)])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), sheet)
    for i, row in enumerate(rows, args.start):
        print(i, row['path'])

if __name__ == '__main__':
    main()
