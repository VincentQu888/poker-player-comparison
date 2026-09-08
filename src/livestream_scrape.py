#!/usr/bin/env python3
"""Create manual-verification hand candidates from public poker livestreams.

This does not redistribute video. It stores source URLs, timestamps, transcript
snippets, and empty fields for a human to verify from the video overlay.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_SOURCE_URL = "https://www.youtube.com/watch?v=bG7K_zq0MoQ"
DEFAULT_SOURCE_NAME = "Hustler Casino Live: Phil Ivey / Tom Dwan / Garrett Adelstein $200/$400"
ACTION_RE = re.compile(
    r"\b(raise[sd]?|bet[st]?|call[sed]?|fold[sed]?|all[ -]?in|straddle|flop|turn|river|button)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class HandCandidate:
    candidate_id: str
    source_name: str
    source_url: str
    video_id: str
    start_seconds: int
    end_seconds: int
    review_url: str
    transcript_snippet: str
    scrape_method: str
    verification_status: str
    table_stakes: str | None = "$200/$400"
    game: str | None = "NLHE cash"
    players_claimed_in_title: tuple[str, ...] = ("Phil Ivey", "Tom Dwan", "Garrett Adelstein")
    hole_cards: dict[str, list[str]] | None = None
    board: list[str] | None = None
    actions: list[dict[str, str]] | None = None
    result: dict[str, str] | None = None
    notes: str = "Fill cards/actions/result by watching the linked timestamp."


def parse_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_vtt(path: Path) -> list[Cue]:
    cues: list[Cue] = []
    current_time: tuple[float, float] | None = None
    text_parts: list[str] = []

    def flush() -> None:
        nonlocal current_time, text_parts, cues
        if not current_time or not text_parts:
            current_time = None
            text_parts = []
            return
        cleaned = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", part)).strip() for part in text_parts]
        cleaned = [part for part in cleaned if part]
        text = cleaned[-1] if cleaned else ""
        if text and text != "[Music]":
            cues.append(Cue(current_time[0], current_time[1], text))
        current_time = None
        text_parts = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:")):
            flush()
            continue
        if "-->" in line:
            flush()
            start, end = line.split(" --> ", 1)
            current_time = (parse_timestamp(start), parse_timestamp(end.split()[0]))
            continue
        if current_time:
            text_parts.append(line)
    flush()
    return cues


def video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname and "youtu.be" in parsed.hostname:
        return parsed.path.strip("/")
    return parse_qs(parsed.query).get("v", ["video"])[0]


def ensure_vtt(url: str, out_dir: Path, basename: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = out_dir / f"{basename}.en-orig.vtt"
    if existing.exists():
        return existing
    subprocess.run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--write-auto-subs",
            "--sub-lang",
            "en-orig",
            "--skip-download",
            "--sub-format",
            "vtt",
            "-o",
            str(out_dir / f"{basename}.%(ext)s"),
            url,
        ],
        check=True,
    )
    if not existing.exists():
        raise FileNotFoundError(f"yt-dlp did not create {existing}")
    return existing


def snippet_near(cues: list[Cue], start: float, seconds: int = 45) -> str:
    parts: list[str] = []
    for cue in cues:
        if start <= cue.start <= start + seconds and cue.text not in parts[-3:]:
            parts.append(cue.text)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:500]


def pick_candidates(cues: list[Cue], count: int, min_gap: int, start_after: int) -> list[int]:
    starts: list[int] = []
    for cue in cues:
        if not ACTION_RE.search(cue.text):
            continue
        start = int(cue.start)
        if start < start_after:
            continue
        if starts and start - starts[-1] < min_gap:
            continue
        starts.append(start)
        if len(starts) == count:
            break
    return starts


def write_outputs(candidates: list[HandCandidate], out_base: Path) -> None:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_base.with_suffix(".jsonl")
    csv_path = out_base.with_suffix(".csv")
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in candidates:
            f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["candidate_id", "review_url", "start_seconds", "end_seconds", "verification_status", "transcript_snippet"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in candidates:
            data = asdict(row)
            writer.writerow({k: data[k] for k in fields})


def build_candidates(args: argparse.Namespace) -> list[HandCandidate]:
    vid = video_id(args.url)
    vtt = ensure_vtt(args.url, args.raw_dir, args.basename)
    cues = parse_vtt(vtt)
    starts = pick_candidates(cues, args.count, args.min_gap_seconds, args.start_after_seconds)
    if len(starts) < args.count:
        raise RuntimeError(f"Only found {len(starts)} candidates; lower --min-gap-seconds")
    return [
        HandCandidate(
            candidate_id=f"{args.basename}_{i:03d}",
            source_name=args.source_name,
            source_url=args.url,
            video_id=vid,
            start_seconds=start,
            end_seconds=start + args.window_seconds,
            review_url=f"{args.url}&t={start}s",
            transcript_snippet=snippet_near(cues, start),
            scrape_method="auto-caption action keyword, min-gap candidate",
            verification_status="needs_manual_verification",
        )
        for i, start in enumerate(starts, 1)
    ]


def self_test() -> None:
    assert parse_timestamp("01:02:03.456") == 3723.456
    tmp = Path("_tmp_test.vtt")
    tmp.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nPhil raises to 1000\n", encoding="utf-8")
    try:
        cues = parse_vtt(tmp)
        assert cues == [Cue(1.0, 2.0, "Phil raises to 1000")]
        assert pick_candidates([Cue(1300, 1301, "Phil raises")], 1, 120, 1200) == [1300]
        assert snippet_near([Cue(1, 2, "Phil raises"), Cue(2, 3, "Phil raises")], 1) == "Phil raises"
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--min-gap-seconds", type=int, default=150)
    parser.add_argument("--window-seconds", type=int, default=210)
    parser.add_argument("--start-after-seconds", type=int, default=2300)
    parser.add_argument("--basename", default="hcl_ivey_dwan_garrett")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/livestream/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/livestream/hcl_ivey_dwan_garrett_100_hands"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("ok")
        return
    candidates = build_candidates(args)
    write_outputs(candidates, args.out)
    print(f"wrote {len(candidates)} candidates to {args.out.with_suffix('.jsonl')} and {args.out.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
