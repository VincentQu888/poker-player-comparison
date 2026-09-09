#!/usr/bin/env python3
"""Build a conservative hand dataset from HCL auto-extraction output.

Cards come from template matching. Names/actions are best-effort OCR/caption
signals with confidence fields; weak signals stay unknown instead of guessed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import eval7

KNOWN_PLAYERS = {
    "PHIL": ["PHIL", "IVEY"],
    "GARRETT": ["GARRETT", "GARR", "GAR", "GARF", "GARREI"],
    "MATT": ["MATT", "BERKEY"],
    "LUCKY": ["LUCKY"],
    "KRISH": ["KRISH", "KRI"],
    "DYLAN": ["DYLAN", "DYLAM", "DYL"],
    "DR ELI": ["DR ELI", "DRELI", "ELI"],
}
ACTION_RE = re.compile(r"\b(raises?|bets?|calls?|checks?|folds?|jams?|all[- ]?in|shoves?)\b", re.I)
AMOUNT_RE = re.compile(r"\$?\s*(\d+(?:\.\d+)?)\s*([kKmM]?)")
CARD_RE = re.compile(r"^[2-9TJQKA][cdhs]$")
NAME_CONFIDENCE_MIN = 0.75


def load_jsonl(path: Path) -> dict[str, dict]:
    return {row["hand_id"]: row for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def clean_token(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper())


def canonical_name(value: str) -> str | None:
    token = clean_token(value)
    if len(token) < 2:
        return None
    for name, aliases in KNOWN_PLAYERS.items():
        if any(clean_token(alias) in token or token in clean_token(alias) for alias in aliases):
            return name
    return None


def seat_name(states: list[dict], seat: str) -> tuple[str, float, dict[str, int]]:
    fields = [f"{seat}_name", "left_player_top" if seat == "top" else "left_player_bottom"]
    votes = Counter(
        name
        for state in states
        for field in fields
        for name in [canonical_name(state.get("text", {}).get(field, ""))]
        if name
    )
    if not votes:
        return "unknown", 0.0, {}
    name, count = votes.most_common(1)[0]
    total = sum(votes.values())
    confidence = count / total if total else 0.0
    return (name, confidence, dict(votes)) if confidence >= NAME_CONFIDENCE_MIN else ("unknown", confidence, dict(votes))


def parse_amount(text: str) -> float | None:
    match = AMOUNT_RE.search(text.replace(",", ""))
    if not match:
        return None
    amount = float(match.group(1))
    return amount * {"k": 1_000, "m": 1_000_000}.get(match.group(2).lower(), 1)


def caption_actions(snippets: list[str]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    seen = set()
    for snippet in snippets:
        actor = next((name for name, aliases in KNOWN_PLAYERS.items() if any(re.search(rf"\b{re.escape(alias)}\b", snippet, re.I) for alias in aliases)), None)
        match = ACTION_RE.search(snippet)
        if not actor or not match:
            continue
        key = (actor, match.group(1).lower(), snippet[:80])
        if key in seen:
            continue
        seen.add(key)
        actions.append({"actor": actor, "action": match.group(1).lower(), "amount": parse_amount(snippet), "source": "caption", "text": snippet})
    return actions


def overlay_actions(states: list[dict], top: str, bottom: str) -> list[dict[str, object]]:
    rows = []
    for state in states:
        text = state.get("text", {})
        for seat, player, field in [("top", top, "left_player_top"), ("bottom", bottom, "left_player_bottom")]:
            raw = " ".join([text.get(field, ""), text.get(f"{seat}_position_action", "")]).strip()
            match = ACTION_RE.search(raw)
            if match:
                rows.append({"actor": player, "seat": seat, "action": match.group(1).lower(), "amount": parse_amount(raw), "source": "overlay", "text": raw})
    return rows


def winner(players: list[dict], board: list[str]) -> str | None:
    if len(board) != 5:
        return None
    top = [eval7.Card(card) for card in [*players[0]["cards"], *board]]
    bottom = [eval7.Card(card) for card in [*players[1]["cards"], *board]]
    top_value = eval7.evaluate(top)
    bottom_value = eval7.evaluate(bottom)
    if top_value == bottom_value:
        return "split"
    return players[0]["name"] if top_value > bottom_value else players[1]["name"]


def is_clean_cards(hand: dict) -> bool:
    cards = [card for player in hand["players"] for card in player["cards"]] + hand["board"]
    return hand.get("extraction_status") == "complete" and all(CARD_RE.match(card) for card in cards) and len(cards) == len(set(cards))


def matching_states(states: list[dict], cards_hand: dict) -> list[dict]:
    top_cards = cards_hand["players"][0]["cards"]
    bottom_cards = cards_hand["players"][1]["cards"]
    matches = [
        state
        for state in states
        if [state.get("cards", {}).get("top_hole_card_1"), state.get("cards", {}).get("top_hole_card_2")] == top_cards
        and [state.get("cards", {}).get("bottom_hole_card_1"), state.get("cards", {}).get("bottom_hole_card_2")] == bottom_cards
    ]
    return matches or states


def build(cards_hand: dict, ocr_hand: dict | None) -> dict | None:
    if not is_clean_cards(cards_hand):
        return None
    source = ocr_hand or cards_hand
    states = matching_states(source.get("frame_states", []), cards_hand)
    top_name, top_conf, top_votes = seat_name(states, "top")
    bottom_name, bottom_conf, bottom_votes = seat_name(states, "bottom")
    players = [
        {"seat": "top", "name": top_name, "name_confidence": round(top_conf, 3), "name_votes": top_votes, "cards": cards_hand["players"][0]["cards"]},
        {"seat": "bottom", "name": bottom_name, "name_confidence": round(bottom_conf, 3), "name_votes": bottom_votes, "cards": cards_hand["players"][1]["cards"]},
    ]
    actions = [*overlay_actions(states, top_name, bottom_name), *caption_actions(source.get("action_caption_snippets", []))]
    return {
        "hand_id": cards_hand["hand_id"],
        "review_url": cards_hand["review_url"],
        "start_seconds": cards_hand["start_seconds"],
        "end_seconds": cards_hand["end_seconds"],
        "players": players,
        "board": cards_hand["board"],
        "pot": source.get("pot"),
        "actions": actions,
        "winner": winner(players, cards_hand["board"]),
        "dataset_status": "cards_verified_names_actions_best_effort",
    }


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["hand_id", "top_player", "bottom_player", "top_cards", "bottom_cards", "board", "winner", "actions"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "hand_id": row["hand_id"],
                "top_player": row["players"][0]["name"],
                "bottom_player": row["players"][1]["name"],
                "top_cards": " ".join(row["players"][0]["cards"]),
                "bottom_cards": " ".join(row["players"][1]["cards"]),
                "board": " ".join(row["board"]),
                "winner": row["winner"] or "",
                "actions": " | ".join(f"{a['actor']} {a['action']}" for a in row["actions"]),
            })


def self_test() -> None:
    assert canonical_name("Garri") == "GARRETT"
    assert canonical_name("DYLAM") == "DYLAN"
    assert parse_amount("$12.8K") == 12_800
    assert caption_actions(["Phil raises to $3K and Garrett calls"])[0]["actor"] == "PHIL"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=Path, default=Path("report/livestream/hcl_ivey_dwan_garrett_dense_auto_hands.jsonl"))
    parser.add_argument("--ocr", type=Path, default=Path("report/livestream/hcl_ivey_dwan_garrett_fullres_auto_ocr.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("report/livestream/hcl_full_hand_dataset.jsonl"))
    parser.add_argument("--csv", type=Path, default=Path("report/livestream/hcl_full_hand_dataset.csv"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("ok")
        return

    card_rows = load_jsonl(args.cards)
    ocr_rows = load_jsonl(args.ocr) if args.ocr.exists() else {}
    rows = [row for hand_id, hand in card_rows.items() for row in [build(hand, ocr_rows.get(hand_id))] if row]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    write_csv(rows, args.csv)
    print(f"wrote {len(rows)} hands to {args.out} and {args.csv}")


if __name__ == "__main__":
    main()
