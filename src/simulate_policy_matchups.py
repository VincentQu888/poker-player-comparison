#!/usr/bin/env python3
"""Monte Carlo ACPC heads-up matchups from empirical action policies."""

from __future__ import annotations

import argparse
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import eval7
import numpy as np
RANKS = "23456789TJQKA"
ACTIONS = ["b1", "b2", "b3", "b4", "c", "f", "r1", "r2", "r3", "r4", "x"]
DH_RE = re.compile(r"d dh p(\d+) (....)")
DB_RE = re.compile(r"d db (.+)")


def hole_class(hole: str) -> str:
    r1, s1, r2, s2 = hole[0], hole[1], hole[2], hole[3]
    hi, lo = sorted([r1, r2], key=RANKS.index, reverse=True)
    return hi + lo if hi == lo else hi + lo + ("s" if s1 == s2 else "o")


def sprb(spr: float) -> str:
    return "a" if spr < 0.5 else "b" if spr < 1 else "c" if spr < 2 else "d" if spr < 5 else "e" if spr < 15 else "f"


def pot_type(raises: int) -> str:
    return "limped" if raises == 0 else "SRP" if raises == 1 else "3bet" if raises == 2 else "4bet+"


def has_straight(ranks: list[str]) -> bool:
    vals = {RANKS.index(r) + 2 for r in ranks}
    if 14 in vals:
        vals.add(1)
    return any(all(v + k in vals for k in range(5)) for v in range(1, 11))


def board_bucket(board: list[str]) -> str:
    if not board:
        return "preflop"
    ranks = [c[0] for c in board]
    suits = [c[1] for c in board]
    paired = "paired" if max(Counter(ranks).values()) > 1 else "unpaired"
    suit_count = max(Counter(suits).values())
    suited = "mono" if suit_count >= 3 else "two" if suit_count == 2 else "rainbow"
    vals = sorted({RANKS.index(r) for r in ranks})
    connected = "conn" if len(vals) >= 3 and vals[-1] - vals[0] <= 4 else "gap"
    return f"{len(board)}{paired[0]}{suited[0]}{connected[0]}"


def hand_bucket(hole: str, board: list[str]) -> str:
    if not board:
        return "preflop"
    cards = [hole[:2], hole[2:], *board]
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]
    rank_counts = sorted(Counter(ranks).values(), reverse=True)
    flush = max(Counter(suits).values()) >= 5
    straight = has_straight(ranks)
    if flush and straight:
        return "straight_flush"
    if rank_counts[0] == 4:
        return "quads"
    if rank_counts[:2] == [3, 2]:
        return "full_house"
    if flush:
        return "flush"
    if straight:
        return "straight"
    if rank_counts[0] == 3:
        return "trips"
    if rank_counts[:2] == [2, 2]:
        return "two_pair"
    if rank_counts[0] == 2:
        board_ranks = [c[0] for c in board]
        pair_rank = next(r for r, n in Counter(ranks).items() if n == 2)
        return "overpair_pair" if pair_rank in hole and pair_rank not in board_ranks else "pair"
    if max(Counter(suits).values()) == 4:
        return "flush_draw"
    return "high_card"


def sizeb(x: float | None) -> str:
    if x is None:
        return "na"
    return "1" if x < 0.4 else "2" if x < 0.75 else "3" if x < 1.25 else "4"


def state(mode: str, street: int, raises: int, pos: str, faced: str, stack: float, pot: float, hole: str, board: list[str], last_inc: float, last_pot: float, nactive: int, behind: int) -> str:
    core = f"{street}|{pot_type(raises)}|{pos}|{faced}|{sprb(stack / pot if pot else 99)}"
    simple = f"{core}|H={hole_class(hole)}|M={hand_bucket(hole, board)}"
    if mode == "s_sim":
        return simple
    faced_sz = sizeb(last_inc / last_pot) if last_pot > 0 and faced != "no_wager" else "4" if faced != "no_wager" and last_inc > 0 else "na"
    fine = f"{core}|{faced_sz}|{nactive if nactive < 6 else '6+'}"
    return f"{fine}|H={hole_class(hole)}|M={hand_bucket(hole, board)}|B={board_bucket(board)}|behind={behind}"


def random_deal(rng: random.Random) -> tuple[str, str, list[str]]:
    deck = [str(card) for card in eval7.Deck()]
    rng.shuffle(deck)
    return deck[0] + deck[1], deck[2] + deck[3], deck[4:9]


def load_policies(db: Path, state_col: str):
    con = duckdb.connect(str(db), read_only=True)
    rows = con.execute(f"""
        WITH opp AS (
          SELECT a.hand_id, a.player, b.player opponent
          FROM 'data/hand_player/*.parquet' a
          JOIN 'data/hand_player/*.parquet' b ON a.hand_id=b.hand_id AND a.player<>b.player)
        SELECT d.player, opp.opponent, d."{state_col}", d.a, count(*) n
        FROM d JOIN opp USING(hand_id, player) GROUP BY 1,2,3,4
    """).fetchall()
    size_rows = con.execute(f"""
        WITH opp AS (
          SELECT a.hand_id, a.player, b.player opponent
          FROM 'data/hand_player/*.parquet' a
          JOIN 'data/hand_player/*.parquet' b ON a.hand_id=b.hand_id AND a.player<>b.player)
        SELECT d.player, opp.opponent, d."{state_col}", d.a, list(d.act_frac) sizes
        FROM d JOIN opp USING(hand_id, player)
        WHERE d.a LIKE 'b%' OR d.a LIKE 'r%' GROUP BY 1,2,3,4
    """).fetchall()
    player = defaultdict(Counter)
    pop = defaultdict(Counter)
    sizes = {}
    for p, opponent, s, a, n in rows:
        player[(p, opponent, s)][a] += n
        pop[s][a] += n
    for p, opponent, s, a, vals in size_rows:
        sizes[(p, opponent, s, a)] = [float(v) for v in vals if v is not None]
    actual = {(p, o): bb100 for p, o, bb100 in con.execute("""
        WITH hp AS (SELECT * FROM 'data/hand_player/*.parquet'), opp AS (
          SELECT a.player, b.player opponent, a.net_bb
          FROM hp a JOIN hp b ON a.hand_id=b.hand_id AND a.player<>b.player)
        SELECT player, opponent, avg(net_bb)*100 bb100 FROM opp GROUP BY 1,2
    """).fetchall()}
    return player, pop, sizes, actual


class UnseenState(Exception):
    pass


def choose(rng: random.Random, counts: Counter, legal: list[str]) -> str:
    weighted = [(a, counts[a]) for a in legal if counts[a] > 0]
    if not weighted:
        raise UnseenState
    total = sum(w for _, w in weighted)
    pick = rng.uniform(0, total)
    upto = 0
    for action, weight in weighted:
        upto += weight
        if upto >= pick:
            return action
    return weighted[-1][0]


def fill_board(rng: random.Random, h0: str, h1: str, board: list[str]) -> list[str]:
    used = {h0[:2], h0[2:], h1[:2], h1[2:], *board}
    deck = [str(c) for c in eval7.Deck() if str(c) not in used]
    rng.shuffle(deck)
    return [*board, *deck[: 5 - len(board)]]


def settle(h0: str, h1: str, board: list[str], invested: list[float], pot: float) -> float:
    b = [eval7.Card(c) for c in board]
    s0 = eval7.evaluate(b + [eval7.Card(h0[:2]), eval7.Card(h0[2:])])
    s1 = eval7.evaluate(b + [eval7.Card(h1[:2]), eval7.Card(h1[2:])])
    if s0 == s1:
        return pot / 2 - invested[0]
    return pot - invested[0] if s0 > s1 else -invested[0]


def run_hand(rng, policies, pop, sizes, mode, p0, p1, deal) -> float:
    holes = [deal[0], deal[1]]
    stacks = [199.5, 199.0]
    invested = [0.5, 1.0]
    street_bet = [0.5, 1.0]
    pot = 1.5
    preflop_raises = 0
    board = []
    active = [True, True]
    full_board = fill_board(rng, holes[0], holes[1], deal[2])
    players = [p0, p1]

    for street in range(4):
        if street:
            board = full_board[: 3 if street == 1 else 4 if street == 2 else 5]
            street_bet = [0.0, 0.0]
        current = max(street_bet)
        street_wagers = 1 if street == 0 else 0
        last_inc = current
        last_pot = 0.0 if street == 0 else pot
        acted = [False, False]
        turn = 0 if street == 0 else 1
        steps = 0
        while steps < 24:
            steps += 1
            other = 1 - turn
            to_call = max(0.0, current - street_bet[turn])
            faced = "no_wager" if to_call == 0 else "bet" if street_wagers <= 1 else "raise" if street_wagers == 2 else "reraise"
            pos = "SB" if turn == 0 else "BB"
            s = state(mode, street, preflop_raises, pos, faced, stacks[turn], pot, holes[turn], board, last_inc, last_pot, sum(active), 1 if active[other] else 0)
            legal = ["x", "b1", "b2", "b3", "b4"] if to_call == 0 else ["f", "c", "r1", "r2", "r3", "r4"]
            counts = policies.get((players[turn], players[other], s), Counter())
            action = choose(rng, counts, legal)
            if action == "f":
                active[turn] = False
                return -invested[0] if turn == 0 else pot - invested[0]
            if action in ("c", "x"):
                pay = min(to_call, stacks[turn])
                stacks[turn] -= pay; invested[turn] += pay; street_bet[turn] += pay; pot += pay
                acted[turn] = True
            else:
                observed_sizes = sizes.get((players[turn], players[other], s, action))
                if not observed_sizes:
                    raise UnseenState
                pay = min(stacks[turn], max(to_call, pot * rng.choice(observed_sizes)))
                last_pot = pot
                last_inc = pay
                stacks[turn] -= pay; invested[turn] += pay; street_bet[turn] += pay; pot += pay
                current = street_bet[turn]; acted = [False, False]; acted[turn] = True
                street_wagers += 1
                if street == 0:
                    preflop_raises += 1
            if all(acted) and abs(street_bet[0] - street_bet[1]) < 1e-9:
                break
            turn = other
    return settle(holes[0], holes[1], full_board, invested, pot)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-attempts", type=int, default=200000)
    ap.add_argument("--state", choices=["s_sim", "s_pdf"], default="s_sim")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    policies, pop, sizes, actual = load_policies(Path("data/analysis.duckdb"), args.state)
    players = sorted({p for p, _, _ in policies})
    simulated = {}
    attempts_by_pair = {}
    print("simulated bb/100 for row player vs column player")
    for p0 in players:
        vals = []
        for p1 in players:
            if p0 == p1:
                vals.append("   --  ")
                continue
            total = 0.0
            kept = attempts = 0
            while kept < args.hands and attempts < args.max_attempts:
                attempts += 1
                try:
                    if kept % 2:
                        total += run_hand(rng, policies, pop, sizes, args.state, p0, p1, random_deal(rng))
                    else:
                        total -= run_hand(rng, policies, pop, sizes, args.state, p1, p0, random_deal(rng))
                except UnseenState:
                    continue
                kept += 1
            attempts_by_pair[(p0, p1)] = attempts
            if kept:
                simulated[(p0, p1)] = total / kept * 100
                vals.append(f"{simulated[(p0, p1)]:7.2f}/{kept:04d}")
            else:
                vals.append(" unseen")
        print(f"{p0:16s} " + " ".join(vals))
    pairs = sorted(set(simulated) & set(actual))
    sim = np.array([simulated[p] for p in pairs])
    real = np.array([actual[p] for p in pairs])
    pearson = float(np.corrcoef(sim, real)[0, 1])
    spearman = float(np.corrcoef(np.argsort(np.argsort(sim)), np.argsort(np.argsort(real)))[0, 1])
    print(f"pearson_sim_vs_actual={pearson:.3f} spearman_sim_vs_actual={spearman:.3f}")
    kept_total = sum(args.hands for pair in simulated)
    attempts_total = sum(attempts_by_pair[pair] for pair in simulated)
    accept_rate = kept_total / attempts_total if attempts_total else 0.0
    print(f"accepted_rollouts={kept_total} failed_rollouts={attempts_total - kept_total} attempts={attempts_total} accept_rate={accept_rate:.3f}")
    for pair in sorted(simulated):
        attempts = attempts_by_pair[pair]
        print(f"{pair[0]} vs {pair[1]}: accepted={args.hands} failed={attempts - args.hands} attempts={attempts}")


if __name__ == "__main__":
    main()
