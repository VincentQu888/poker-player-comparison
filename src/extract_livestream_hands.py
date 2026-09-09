#!/usr/bin/env python3
"""Extract reviewable hand packets from livestream candidate timestamps.

The output is intentionally evidence-first: one JSONL row per candidate with a
local contact sheet and action-like caption lines. Card/action fields stay null
until a human verifies the overlay.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
from yt_dlp import YoutubeDL

from livestream_scrape import ACTION_RE, Cue, parse_vtt


@dataclass(frozen=True)
class ExtractedHand:
    hand_id: str
    source_url: str
    review_url: str
    start_seconds: int
    end_seconds: int
    contact_sheet: str
    action_caption_snippets: list[str]
    players: list[dict[str, object]] | None = None
    board: list[str] | None = None
    actions: list[dict[str, object]] | None = None
    result: list[dict[str, object]] | None = None
    extraction_status: str = "needs_manual_card_action_entry"


def video_stream_url(source_url: str, max_height: int) -> str:
    with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(source_url, download=False)
    formats = [
        f
        for f in info["formats"]
        if f.get("vcodec") != "none" and f.get("height") and f["height"] <= max_height and f.get("url")
    ]
    if not formats:
        raise RuntimeError("No usable video stream found")
    return max(formats, key=lambda f: f.get("height") or 0)["url"]


def captions_between(cues: list[Cue], start: int, end: int) -> list[str]:
    snippets: list[str] = []
    for cue in cues:
        if start <= cue.start <= end and ACTION_RE.search(cue.text):
            text = re.sub(r"\s+", " ", cue.text).strip()
            if text and text not in snippets[-3:]:
                snippets.append(text)
    return snippets[:20]


def frame_at(cap: cv2.VideoCapture, second: int):
    cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
    ok, frame = cap.read()
    if not ok:
        return None
    return frame


def make_contact_sheet(cap: cv2.VideoCapture, start: int, end: int, out_path: Path, cell_size: tuple[int, int] = (320, 180)) -> None:
    if out_path.exists():
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    times = list(range(start, end + 1, 30))[:8]
    frames = []
    for second in times:
        frame = frame_at(cap, second)
        if frame is None:
            continue
        frame = cv2.resize(frame, cell_size)
        cv2.putText(frame, f"t={second}s", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        frames.append(frame)
    if not frames:
        raise RuntimeError(f"No frames captured for {start}-{end}")
    while len(frames) < 8:
        frames.append(frames[-1].copy())
    rows = [cv2.hconcat(frames[i : i + 4]) for i in range(0, 8, 4)]
    cv2.imwrite(str(out_path), cv2.vconcat(rows))


def load_candidates(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract(args: argparse.Namespace) -> list[ExtractedHand]:
    candidates = load_candidates(args.candidates)[: args.limit]
    cues = parse_vtt(args.vtt)
    cap: cv2.VideoCapture | None = None

    rows: list[ExtractedHand] = []
    for candidate in candidates:
        hand_id = str(candidate["candidate_id"])
        start = int(candidate["start_seconds"])
        end = int(candidate["end_seconds"])
        sheet = args.frames_dir / f"{hand_id}.jpg"
        if not sheet.exists():
            if cap is None:
                stream_url = video_stream_url(str(candidates[0]["source_url"]), args.max_height)
                cap = cv2.VideoCapture(stream_url)
                if not cap.isOpened():
                    raise RuntimeError("Could not open video stream")
            make_contact_sheet(cap, start, end, sheet, (args.cell_width, args.cell_height))
        rows.append(
            ExtractedHand(
                hand_id=hand_id,
                source_url=str(candidate["source_url"]),
                review_url=str(candidate["review_url"]),
                start_seconds=start,
                end_seconds=end,
                contact_sheet=str(sheet).replace("\\", "/"),
                action_caption_snippets=captions_between(cues, start, end),
            )
        )
    if cap is not None:
        cap.release()
    return rows


def write_jsonl(rows: list[ExtractedHand], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def self_test() -> None:
    cues = [Cue(10, 11, "Phil raises"), Cue(12, 13, "Phil raises"), Cue(14, 15, "Garrett calls")]
    assert captions_between(cues, 9, 15) == ["Phil raises", "Garrett calls"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=Path("report/livestream/hcl_ivey_dwan_garrett_100_hands.jsonl"))
    parser.add_argument("--vtt", type=Path, default=Path("data/livestream/raw/hcl_ivey_dwan_garrett.en-orig.vtt"))
    parser.add_argument("--out", type=Path, default=Path("report/livestream/hcl_ivey_dwan_garrett_extracted_hands.jsonl"))
    parser.add_argument("--frames-dir", type=Path, default=Path("report/livestream/frames"))
    parser.add_argument("--max-height", type=int, default=360)
    parser.add_argument("--cell-width", type=int, default=320)
    parser.add_argument("--cell-height", type=int, default=180)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("ok")
        return
    rows = extract(args)
    write_jsonl(rows, args.out)
    print(f"wrote {len(rows)} hand packets to {args.out}")


if __name__ == "__main__":
    main()
