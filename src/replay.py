#!/usr/bin/env python3
"""
Core hand replay: one Stage-1 hand row -> (decisions, hand_player) records.

A "decision" is a voluntary player action (fold / check / call / bet / raise).
Blind posts and card deals are not decisions.

State captured at each decision (BEFORE the action resolves):
  street            0=preflop 1=flop 2=turn 3=river
  board             visible board cards string
  pot_before        chips committed to pot before this action (incl. this street)
  to_call           chips hero must add to continue
  hero_stack_before hero remaining stack before acting
  spr               hero_stack_before / pot_before
  action_faced      no_wager / bet / raise / reraise
                    (preflop the BB counts as the first wager)
  prev_wager_frac   last wager increment / pot before that wager (bet sizing)
  pot_type          limped / SRP / 3bet / 4bet+ (from preflop raise count)
  pos_idx / pos_label   seat index (0=SB,1=BB,...,last=BTN) and label
  n_active_before   players not yet folded when hero acts
  n_to_act_after    players still to act after hero on this street

Action recorded:
  act              fold / check / call / bet / raise
  act_to           total street wager after action (bet/raise); call amount for call
  act_frac         (chips added by hero) / pot_before   (pot-relative size)

Outcome attached (forward-looking, in BB):
  reward_bb        net chips won from THIS decision onward
                   = hand_net + committed_before   (sunk chips excluded)
  hand_net_bb      whole-hand net for hero (winnings - invested)
  net_source       'winnings' | 'finishing' | 'uncontested' | 'unknown'
"""
import re

try:
    import eval7
    _HAVE_EVAL7 = True
except Exception:
    _HAVE_EVAL7 = False

POS_LABELS_BY_N = {}


def _cards(s):
    return [s[i:i + 2] for i in range(0, len(s), 2)]


def _resolve_winners(alive, hole, board):
    """Identify showdown winner indices from shown cards. Returns
    (winners_list, source) or (None, None) if unresolvable."""
    if not _HAVE_EVAL7:
        return None, None
    bcards = _cards(board)
    if len(bcards) != 5:
        return None, None
    known = [i for i in alive if hole[i] and hole[i] != "????" and len(hole[i]) == 4]
    if len(known) == len(alive) and len(alive) >= 2:
        try:
            bd = [eval7.Card(c) for c in bcards]
            scores = {i: eval7.evaluate(bd + [eval7.Card(c) for c in _cards(hole[i])])
                      for i in alive}
        except Exception:
            return None, None
        best = max(scores.values())
        return [i for i in alive if scores[i] == best], "showdown_eval"
    if len(known) == 1:
        return [known[0]], "sd_heuristic"
    return None, None


def pos_labels(n):
    """Return list of position labels for n seated players, index 0=SB.
    Order preflop-action-wise: 0=SB,1=BB,2=UTG,...,n-1=BTN."""
    if n in POS_LABELS_BY_N:
        return POS_LABELS_BY_N[n]
    if n == 2:
        labels = ["SB/BTN", "BB"]  # heads-up: SB is the button
    else:
        base = ["SB", "BB"]
        late = ["BTN", "CO", "HJ", "LJ"]  # from the button backwards
        mid = ["UTG", "UTG1", "UTG2", "MP", "MP1", "MP2", "MP3"]
        # positions 2..n-1 : UTG.. then ... CO, BTN as last
        n_mid = n - 2
        seq = []
        # fill from UTG upward, but ensure last is BTN, second last CO, etc.
        tail = ["BTN", "CO", "HJ", "LJ", "MP2", "MP1"][:max(0, n_mid)]
        tail = list(reversed(tail))
        head = ["UTG", "UTG1", "UTG2", "MP", "MP1"][:max(0, n_mid - len(tail))]
        seq = head + tail
        # If mismatch in length, pad generically
        while len(seq) < n_mid:
            seq.insert(len(head), "MP")
        labels = base + seq[:n_mid]
    POS_LABELS_BY_N[n] = labels
    return labels


ACT_RE = re.compile(r"^p(\d+) (f|cc|cbr|sm)(?: (.+))?$")
DB_RE = re.compile(r"^d db (.+)$")


def _rake(pot_bb, flop_seen, bb):
    """Rake model for pots resolved WITHOUT a rake-accurate winnings field.
    2009 online micro/low-stakes: ~5% of pot, no-flop-no-drop, capped.
    Cap ~ $3 translated to BB; also capped at 3 BB to avoid over-raking micro.
    winnings/finishing-based nets are already rake-accurate and skip this."""
    if not flop_seen:
        return 0.0
    cap_bb = min(3.0 / bb if bb > 0 else 3.0, 3.0)
    return min(cap_bb, 0.05 * pot_bb)


def replay_hand(row):
    """row: dict-like with keys players, blinds, starting_stacks, finishing_stacks,
    winnings, actions, site, nl_level, hand_id, year, month, day.
    Returns (list_of_decision_dicts, list_of_hand_player_dicts)."""
    players = list(row["players"])
    n = len(players)
    if n < 2:
        return [], []
    blinds = list(row["blinds"]) + [0.0] * (n - len(row["blinds"]))
    stacks = list(row["starting_stacks"]) + [0.0] * (n - len(row["starting_stacks"]))
    winnings = list(row["winnings"])
    finishing = list(row["finishing_stacks"])
    actions = list(row["actions"])
    nl = row["nl_level"]
    bb = nl / 100.0
    if bb <= 0:
        bb = max(blinds) if blinds and max(blinds) > 0 else 1.0

    labels = pos_labels(n)

    # per-player running state
    invested = [0.0] * n          # total chips in pot over hand
    street_contrib = [0.0] * n    # chips in this street
    folded = [False] * n
    stack_rem = list(stacks)      # remaining stack
    hole = ["" for _ in range(n)]
    reached_sd = [False] * n

    # post blinds
    pot = 0.0
    for i in range(n):
        b = blinds[i]
        if b > 0:
            b = min(b, stack_rem[i])
            street_contrib[i] = b
            invested[i] += b
            stack_rem[i] -= b
            pot += b
    current_bet = max(street_contrib) if street_contrib else 0.0
    n_wagers = 1 if current_bet > 0 else 0     # BB counts as wager 1 preflop
    last_wager_inc = current_bet               # size of BB as "prev wager"
    pot_before_last_wager = 0.0
    preflop_raises = 0

    street = 0
    board = ""
    n_active = n
    # order of players who still need to act this street handled implicitly by action list.

    decisions = []
    # We need n_to_act_after: count of active players after hero in this street's
    # action order who have not yet folded. We approximate using the action list
    # look-ahead per street. Simpler: compute from remaining actions on same street.

    # Pre-index actions into streets for look-ahead of "to act after".
    # Build list of (idx, token) with street numbers.
    parsed = []
    st = 0
    for tok in actions:
        m = DB_RE.match(tok)
        if m:
            st += 1
            parsed.append(("board", st, m.group(1)))
            continue
        m = ACT_RE.match(tok)
        if not m:
            parsed.append(("other", st, tok))
            continue
        pidx = int(m.group(1)) - 1
        verb = m.group(2)
        arg = m.group(3)
        parsed.append((verb, st, (pidx, arg)))

    # helper: for a given position in parsed list, count distinct not-yet-acted
    # active players remaining on same street after this index.
    def to_act_after(cur_i, cur_street, acted_set, folded_snapshot):
        seen = set()
        for j in range(cur_i + 1, len(parsed)):
            typ, s, payload = parsed[j]
            if typ == "board":
                break
            if s != cur_street:
                break
            if typ in ("f", "cc", "cbr"):
                pj = payload[0]
                if pj not in seen and not folded_snapshot[pj]:
                    seen.add(pj)
        return len(seen)

    street = 0
    for i, (typ, s, payload) in enumerate(parsed):
        if typ == "board":
            street = s
            board = board + payload
            # reset street state
            street_contrib = [0.0] * n
            current_bet = 0.0
            n_wagers = 0
            last_wager_inc = 0.0
            pot_before_last_wager = pot
            continue
        if typ == "other":
            continue
        pidx, arg = payload
        if typ == "sm":
            if arg and arg != "????":
                hole[pidx] = arg
                reached_sd[pidx] = True
            elif arg == "????":
                reached_sd[pidx] = True
            continue
        # a voluntary decision by pidx
        to_call = current_bet - street_contrib[pidx]
        if to_call < 0:
            to_call = 0.0
        hero_stack_before = stack_rem[pidx]
        pot_before = pot
        # action_faced
        if to_call <= 1e-9:
            faced = "no_wager"
        elif n_wagers <= 1:
            faced = "bet"
        elif n_wagers == 2:
            faced = "raise"
        else:
            faced = "reraise"
        prev_wager_frac = (last_wager_inc / pot_before_last_wager
                           if pot_before_last_wager > 1e-9 else
                           (99.0 if last_wager_inc > 0 else 0.0))
        spr = hero_stack_before / pot_before if pot_before > 1e-9 else 99.0
        n_to_act = to_act_after(i, s, None, folded)
        pot_type = ("limped" if preflop_raises == 0 else
                    "SRP" if preflop_raises == 1 else
                    "3bet" if preflop_raises == 2 else "4bet+")

        rec = {
            "site": row["site"], "nl_level": nl, "hand_id": row["hand_id"],
            "player": players[pidx], "pos_idx": pidx,
            "pos_label": labels[pidx] if pidx < len(labels) else "?",
            "seat_count": row["seat_count"], "n_players": n,
            "street": street, "board": board,
            "pot_before_bb": pot_before / bb, "to_call_bb": to_call / bb,
            "hero_stack_before_bb": hero_stack_before / bb,
            "spr": spr, "action_faced": faced,
            "prev_wager_frac": prev_wager_frac, "pot_type": pot_type,
            "n_active_before": n_active, "n_to_act_after": n_to_act,
            "year": row["year"], "month": row["month"], "day": row["day"],
            "committed_before_bb": invested[pidx] / bb,
        }

        # resolve action
        if typ == "f":
            rec["act"] = "fold"; rec["act_to_bb"] = 0.0; rec["act_frac"] = 0.0
            folded[pidx] = True
            n_active -= 1
        elif typ == "cc":
            if to_call <= 1e-9:
                rec["act"] = "check"; rec["act_to_bb"] = 0.0; rec["act_frac"] = 0.0
            else:
                pay = min(to_call, stack_rem[pidx])
                rec["act"] = "call"; rec["act_to_bb"] = pay / bb
                rec["act_frac"] = pay / pot_before if pot_before > 1e-9 else 0.0
                street_contrib[pidx] += pay
                invested[pidx] += pay
                stack_rem[pidx] -= pay
                pot += pay
        elif typ == "cbr":
            try:
                to_amt = float(arg)
            except (TypeError, ValueError):
                to_amt = current_bet
            inc = to_amt - street_contrib[pidx]
            inc = min(inc, stack_rem[pidx])
            is_raise = current_bet > 1e-9
            rec["act"] = "raise" if is_raise else "bet"
            rec["act_to_bb"] = to_amt / bb
            rec["act_frac"] = inc / pot_before if pot_before > 1e-9 else 99.0
            # update wager tracking
            pot_before_last_wager = pot
            last_wager_inc = inc
            street_contrib[pidx] += inc
            invested[pidx] += inc
            stack_rem[pidx] -= inc
            pot += inc
            current_bet = street_contrib[pidx]
            n_wagers += 1
            if street == 0:
                preflop_raises += 1
        decisions.append(rec)

    # ---- settle uncalled bet on the final street ----
    # Earlier streets are always matched (we only advance to a new board when
    # >=2 players continue with equal contributions). The last aggressor may
    # have an uncalled excess over the second-highest contribution; return it.
    sc_sorted = sorted(range(n), key=lambda i: street_contrib[i], reverse=True)
    if n >= 2:
        top, second = sc_sorted[0], sc_sorted[1]
        excess = street_contrib[top] - street_contrib[second]
        if excess > 1e-9:
            invested[top] -= excess
            stack_rem[top] += excess
            pot -= excess
            street_contrib[top] -= excess

    # ---- outcomes ----
    # Net is computed from the action-log matched pot (which conserves money to
    # within rake). The `winnings` field's dollar amount is NOT trusted for the
    # amount (its handling of uncalled returns differs across sites); it is used
    # only to identify the winner at otherwise-unresolvable showdowns.
    flop_seen = board != ""
    rake_dollars = _rake(pot / bb, flop_seen, bb) * bb  # in dollars
    net = [None] * n
    net_source = "unknown"
    alive = [i for i in range(n) if not folded[i]]
    winners = None
    if len(alive) == 1:
        winners, net_source = [alive[0]], "uncontested"
    else:
        winners, net_source = _resolve_winners(alive, hole, board)
        if winners is None and winnings and len(winnings) == n and any(w > 0 for w in winnings):
            # use winnings only to pick the winner(s), not the amount
            winners = [i for i in range(n) if winnings[i] > 0]
            net_source = "winnings_winner"
    if winners:
        share = (pot - rake_dollars) / len(winners)
        net = [-invested[i] for i in range(n)]
        for w in winners:
            net[w] = share - invested[w]
    else:
        net = [None] * n
        net_source = "unknown"

    hand_players = []
    for i in range(n):
        hand_players.append({
            "site": row["site"], "nl_level": nl, "hand_id": row["hand_id"],
            "player": players[i], "pos_idx": i, "n_players": n,
            "invested_bb": invested[i] / bb,
            "net_bb": (net[i] / bb) if net[i] is not None else None,
            "net_source": net_source,
            "reached_showdown": reached_sd[i],
            "saw_hole": hole[i] != "",
            "hole": hole[i],
            "vpip": invested[i] > (blinds[i] + 1e-9),
            "year": row["year"], "month": row["month"], "day": row["day"],
        })

    # attach forward reward to decisions
    for rec in decisions:
        pidx = rec["pos_idx"]
        if net[pidx] is not None:
            rec["hand_net_bb"] = net[pidx] / bb
            rec["reward_bb"] = net[pidx] / bb + rec["committed_before_bb"]
            rec["net_source"] = net_source
        else:
            rec["hand_net_bb"] = None
            rec["reward_bb"] = None
            rec["net_source"] = net_source

    return decisions, hand_players


if __name__ == "__main__":
    # quick self-test on a sample hand
    row = {
        "players": ["A", "B", "C", "D"], "blinds": [0.10, 0.25, 0, 0],
        "starting_stacks": [25, 54.75, 16.35, 24.65],
        "finishing_stacks": [], "winnings": [],
        "actions": ['d dh p1 ????', 'd dh p2 ????', 'd dh p3 ????', 'd dh p4 ????',
                    'p3 f', 'p4 cbr 0.75', 'p1 f', 'p2 cc', 'd db 4dQs4s',
                    'p2 cc', 'p4 cc', 'd db 9h', 'p2 cc', 'p4 cc', 'd db Ad',
                    'p2 cc', 'p4 cc', 'p2 sm 8sAh', 'p4 sm ????'],
        "site": "PS", "nl_level": 25, "hand_id": "X", "seat_count": 6,
        "year": 2009, "month": 7, "day": 1,
    }
    decs, hps = replay_hand(row)
    from pprint import pprint
    for d in decs:
        print(d["player"], d["street"], d["act"], "faced", d["action_faced"],
              "potB=%.2f" % d["pot_before_bb"], "toc=%.2f" % d["to_call_bb"],
              "reward=%s" % (None if d["reward_bb"] is None else round(d["reward_bb"], 2)))
    print("--- hand_player ---")
    for h in hps:
        print(h["player"], "net_bb=", h["net_bb"], h["net_source"], "sd=", h["reached_showdown"], "hole=", h["hole"])
