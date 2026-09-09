#!/usr/bin/env python3
"""Automatic HCL overlay extraction from contact sheets.

Pipeline: contact sheet -> fixed crops -> OCR text fields -> optional template-match
cards -> frame states -> one best-effort hand record per candidate.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from crop_hcl_overlay import crop_regions, load_layout
from extract_livestream_hands import captions_between
from livestream_scrape import parse_vtt

CARD_RE = re.compile(r"^(10|[2-9TJQKA])([cdhs])$", re.IGNORECASE)
AMOUNT_RE = re.compile(r"[S$]?\s*([0-9]+(?:\.[0-9]+)?)\s*([KkMm]?)")
TEXT_FIELDS = {
    "top_name",
    "bottom_name",
    "top_stack",
    "bottom_stack",
    "top_position_action",
    "bottom_position_action",
    "pot_amount",
    "left_player_top",
    "left_player_bottom",
}
CARD_FIELDS = {
    "top_hole_card_1",
    "top_hole_card_2",
    "bottom_hole_card_1",
    "bottom_hole_card_2",
    "board_card_1",
    "board_card_2",
    "board_card_3",
    "board_card_4",
    "board_card_5",
}


@dataclass(frozen=True)
class FrameState:
    offset_index: int
    text: dict[str, str]
    cards: dict[str, str]
    card_confidence: dict[str, float]


@dataclass(frozen=True)
class AutoHand:
    hand_id: str
    review_url: str
    start_seconds: int
    end_seconds: int
    players: list[dict[str, object]]
    board: list[str]
    pot: float | None
    action_caption_snippets: list[str]
    frame_states: list[FrameState]
    extraction_status: str


def split_contact_sheet(sheet) -> list[np.ndarray]:
    h, w = sheet.shape[:2]
    cell_h, cell_w = h // 2, w // 4
    return [sheet[y * cell_h : (y + 1) * cell_h, x * cell_w : (x + 1) * cell_w] for y in range(2) for x in range(4)]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def read_text(reader, image) -> str:
    if reader is None:
        return ""
    big = cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    try:
        parts = reader.readtext(big, detail=0, paragraph=False)
    except Exception:
        return ""
    return clean_text(" ".join(map(str, parts)))


def parse_amount(value: str) -> float | None:
    match = AMOUNT_RE.search(value.replace(",", ""))
    if not match:
        return None
    amount = float(match.group(1))
    suffix = match.group(2).lower()
    return amount * {"k": 1_000, "m": 1_000_000}.get(suffix, 1)


def load_card_templates(path: Path) -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    if not path.exists():
        return templates
    for file in path.glob("*.jpg"):
        match = CARD_RE.match(file.stem)
        image = cv2.imread(str(file), cv2.IMREAD_GRAYSCALE)
        if match and image is not None:
            templates[file.stem.replace("10", "T")] = image
    return templates


def normalize_card_crop(crop) -> np.ndarray:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (40, 48), interpolation=cv2.INTER_CUBIC)


def recognize_card(crop, templates: dict[str, np.ndarray]) -> tuple[str, float]:
    if not templates:
        return "unknown", 0.0
    target = normalize_card_crop(crop)
    scores = []
    for card, template in templates.items():
        template = cv2.resize(template, (40, 48), interpolation=cv2.INTER_CUBIC)
        score = float(cv2.matchTemplate(target, template, cv2.TM_CCOEFF_NORMED)[0][0])
        scores.append((score, card))
    score, card = max(scores)
    return (card, score) if score >= 0.75 else ("unknown", score)


def mode_known(values: list[str]) -> str:
    known = [v for v in values if v and v != "unknown"]
    return Counter(known).most_common(1)[0][0] if known else "unknown"


def extract_frame_state(frame, layout, reader, templates, offset_index: int) -> FrameState:
    crops = crop_regions(frame, layout)
    text = {name: read_text(reader, crops[name]) for name in TEXT_FIELDS if name in crops}
    recognized = {name: recognize_card(crops[name], templates) for name in CARD_FIELDS if name in crops}
    return FrameState(
        offset_index=offset_index,
        text=text,
        cards={name: card for name, (card, _) in recognized.items()},
        card_confidence={name: conf for name, (_, conf) in recognized.items()},
    )


def extraction_status(cards: list[str]) -> str:
    if any(card == "unknown" for card in cards):
        return "low_confidence_cards"
    if len(cards) != len(set(cards)):
        return "duplicate_cards"
    return "complete"


def build_hand(candidate, states: list[FrameState], captions: list[str]) -> AutoHand:
    top_cards = [mode_known([s.cards.get("top_hole_card_1", "unknown") for s in states]), mode_known([s.cards.get("top_hole_card_2", "unknown") for s in states])]
    bottom_cards = [mode_known([s.cards.get("bottom_hole_card_1", "unknown") for s in states]), mode_known([s.cards.get("bottom_hole_card_2", "unknown") for s in states])]
    board = [mode_known([s.cards.get(f"board_card_{i}", "unknown") for s in states]) for i in range(1, 6)]
    board = [c for c in board if c != "unknown"]
    latest_text = states[-1].text if states else {}
    players = [
        {"name": latest_text.get("top_name") or "unknown", "stack": parse_amount(latest_text.get("top_stack", "")), "cards": top_cards},
        {"name": latest_text.get("bottom_name") or "unknown", "stack": parse_amount(latest_text.get("bottom_stack", "")), "cards": bottom_cards},
    ]
    all_cards = [*top_cards, *bottom_cards, *board]
    return AutoHand(
        hand_id=str(candidate["candidate_id"]),
        review_url=str(candidate["review_url"]),
        start_seconds=int(candidate["start_seconds"]),
        end_seconds=int(candidate["end_seconds"]),
        players=players,
        board=board,
        pot=parse_amount(latest_text.get("pot_amount", "")),
        action_caption_snippets=captions,
        frame_states=states,
        extraction_status=extraction_status(all_cards),
    )


def self_test() -> None:
    assert extraction_status(["As", "Kd", "2c"]) == "complete"
    assert extraction_status(["As", "unknown"]) == "low_confidence_cards"
    assert extraction_status(["As", "As"]) == "duplicate_cards"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=Path("report/livestream/hcl_ivey_dwan_garrett_100_hands.jsonl"))
    parser.add_argument("--layout", type=Path, default=Path("report/livestream/hcl_overlay_layout.json"))
    parser.add_argument("--frames-dir", type=Path, default=Path("report/livestream/frames"))
    parser.add_argument("--vtt", type=Path, default=Path("data/livestream/raw/hcl_ivey_dwan_garrett.en-orig.vtt"))
    parser.add_argument("--templates", type=Path, default=Path("report/livestream/card_templates"))
    parser.add_argument("--out", type=Path, default=Path("report/livestream/hcl_auto_hands.jsonl"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("ok")
        return

    reader = None
    if not args.no_ocr:
        try:
            import easyocr

            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except Exception:
            reader = None

    layout = load_layout(args.layout)
    templates = load_card_templates(args.templates)
    cues = parse_vtt(args.vtt)
    all_candidates = [json.loads(line) for line in args.candidates.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidates = all_candidates[args.offset : args.offset + args.limit]
    hands: list[AutoHand] = []
    for candidate in candidates:
        sheet_path = args.frames_dir / f"{candidate['candidate_id']}.jpg"
        sheet = cv2.imread(str(sheet_path))
        if sheet is None:
            continue
        states = [extract_frame_state(frame, layout, reader, templates, i) for i, frame in enumerate(split_contact_sheet(sheet))]
        captions = captions_between(cues, int(candidate["start_seconds"]), int(candidate["end_seconds"]))
        hands.append(build_hand(candidate, states, captions))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for hand in hands:
            f.write(json.dumps(asdict(hand), ensure_ascii=False) + "\n")
    print(f"wrote {len(hands)} auto hands to {args.out} ({len(templates)} card templates loaded)")


if __name__ == "__main__":
    main()
