#!/usr/bin/env python3
"""Crop fixed HCL broadcast overlay regions from a frame.

Layout boxes are [x1, y1, x2, y2] at the layout base resolution and scale to the
actual frame size. This is the boring first rung before OCR/card recognition.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
from yt_dlp import YoutubeDL

DEFAULT_LAYOUT = Path("report/livestream/hcl_overlay_layout.json")
DEFAULT_URL = "https://www.youtube.com/watch?v=bG7K_zq0MoQ"


def load_layout(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def crop_regions(frame, layout: dict[str, object]) -> dict[str, object]:
    base_w, base_h = layout["base_size"]
    height, width = frame.shape[:2]
    scale_x = width / base_w
    scale_y = height / base_h
    crops = {}
    for name, box in layout["regions"].items():
        x1, y1, x2, y2 = box
        sx1, sy1, sx2, sy2 = [
            int(round(x1 * scale_x)),
            int(round(y1 * scale_y)),
            int(round(x2 * scale_x)),
            int(round(y2 * scale_y)),
        ]
        crops[name] = frame[sy1:sy2, sx1:sx2]
    return crops


def video_stream_url(url: str, max_height: int) -> str:
    with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    formats = [
        f
        for f in info["formats"]
        if f.get("vcodec") != "none" and f.get("height") and f["height"] <= max_height and f.get("url")
    ]
    if not formats:
        raise RuntimeError("No usable video stream found")
    return max(formats, key=lambda f: f.get("height") or 0)["url"]


def frame_from_youtube(url: str, seconds: int, max_height: int):
    cap = cv2.VideoCapture(video_stream_url(url, max_height))
    if not cap.isOpened():
        raise RuntimeError("Could not open video stream")
    cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Could not read frame at {seconds}s")
    return frame


def write_crops(crops: dict[str, object], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, crop in crops.items():
        cv2.imwrite(str(out_dir / f"{name}.jpg"), crop)


def self_test() -> None:
    import numpy as np

    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    layout = {"base_size": [10, 10], "regions": {"a": [1, 2, 4, 6]}}
    crops = crop_regions(frame, layout)
    assert crops["a"].shape[:2] == (8, 6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--seconds", type=int, default=2330)
    parser.add_argument("--max-height", type=int, default=360)
    parser.add_argument("--out-dir", type=Path, default=Path("report/livestream/crops/hcl_ivey_dwan_garrett_001"))
    parser.add_argument("--write-frame", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("ok")
        return

    frame = cv2.imread(str(args.image)) if args.image else frame_from_youtube(args.url, args.seconds, args.max_height)
    if frame is None:
        sys.exit(f"Could not read image: {args.image}")
    if args.write_frame:
        args.write_frame.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(args.write_frame), frame)
    write_crops(crop_regions(frame, load_layout(args.layout)), args.out_dir)
    print(f"wrote crops to {args.out_dir}")


if __name__ == "__main__":
    main()
