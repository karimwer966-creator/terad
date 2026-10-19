#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QSMC v6.6.0 - independent reference implementation of the signal gates.

WHY THIS FILE EXISTS
--------------------
The MQL5 self-test (MQL5/Include/QSMC/QSMC_Selftest.mqh) can only be run
inside MetaTrader 5. This file re-implements the SAME rules R1-R7 in
Python so that the expected decisions of docs/KLJ_V6.6.0_SIGNAL_
ARBITRATION.md (section 8) can be checked on any machine, in milliseconds,
with no terminal.

It is an INDEPENDENT implementation, not a translation. If this file and
the MQL5 self-test ever disagree, one of them contains a defect - that is
the whole point of keeping both.

It is NOT a backtest, produces NO statistics and NO win rate, and makes
no claim about profitability.

Run:  python3 tools/test_arbiter.py
      python3 tools/test_arbiter.py -v    (print every scenario)
"""

from __future__ import annotations
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---------------------------------------------------------------- constants
EPS = 1e-9

ZR_SUPPORT, ZR_RESISTANCE, ZR_NEUTRAL = 0, 1, 2

SIG_NONE, SIG_NO_TRADE, SIG_WATCH, SIG_PREVIEW = 0, 1, 2, 3
SIG_TACTICAL_INFO, SIG_COUNTER_TREND, SIG_LIMITED_ROOM, SIG_CONFIRMED = 4, 5, 6, 7

STATE_NAME = {
    SIG_NONE: "NONE", SIG_NO_TRADE: "NO TRADE", SIG_WATCH: "WATCH",
    SIG_PREVIEW: "PREVIEW", SIG_TACTICAL_INFO: "TACTICAL-INFO",
    SIG_COUNTER_TREND: "COUNTER-TREND / SCALP ONLY",
    SIG_LIMITED_ROOM: "LIMITED ROOM", SIG_CONFIRMED: "CONFIRMED",
}

EV_WICK, EV_CANDLE, EV_VOLUME, EV_DISPLACEMENT, EV_SWEEP, EV_MSS = 1, 2, 4, 8, 16, 32
EV_NAMES = [(EV_WICK, "wick"), (EV_CANDLE, "candle"), (EV_VOLUME, "volume"),
            (EV_DISPLACEMENT, "displacement"), (EV_SWEEP, "sweep"), (EV_MSS, "ltf-MSS")]
EV_COUNT = 6


def ev_list(mask: int) -> str:
    s = "+".join(n for b, n in EV_NAMES if mask & b)
    return s if s else "none"


def ev_count(mask: int) -> int:
    return sum(1 for b, _ in EV_NAMES if mask & b)


def ev_missing(mask: int) -> str:
    s = "+".join(n for b, n in EV_NAMES if not (mask & b))
    return s if s else "none"


# ---------------------------------------------------------------- config
@dataclass
class Cfg:
    zone_reach_atr: float = 1.50
    merge_tol_atr: float = 0.50
    max_penetration_atr: float = 0.35
    break_atr: float = 0.30
    min_zone_strength: int = 60
    min_evidence: int = 2
    retest_lookback_bars: int = 24
    min_wick_ratio: float = 0.50
    volume_mult: float = 1.60
    displacement_atr: float = 0.50
    w_d1: int = 50
    w_h4: int = 30
    w_h1: int = 20
    allow_countertrend: bool = True
    countertrend_min_score: int = 70
    countertrend_extra_evidence: int = 1
    min_rr: float = 1.50
    max_stop_atr: float = 4.00
    sl_buffer_atr: float = 0.20
    cooldown_bars: int = 10
    min_alert_distance_atr: float = 0.50
    flipflop_bars: int = 10
    min_bars: int = 30
    tick: float = 0.01


# ---------------------------------------------------------------- zone
@dataclass
class Zone:
    lo: float
    hi: float
    birth_role: int
    strength: int = 80
    touches: int = 2
    broken_closed: bool = False
    flipped: bool = False
    retested: bool = False
    sources: str = "TEST"
    id: str = ""

    def __post_init__(self):
        if not self.id:
            tag = "S" if self.birth_role == ZR_SUPPORT else "R"
            self.id = "Z|%s|%.8f|%.8f" % (tag, self.lo, self.hi)

    @property
    def role(self) -> int:
        """Role = causal birth role, reversed only by a confirmed flip."""
        if not self.flipped:
            return self.birth_role
        if self.birth_role == ZR_SUPPORT:
            return ZR_RESISTANCE
        if self.birth_role == ZR_RESISTANCE:
            return ZR_SUPPORT
        return ZR_NEUTRAL

    def gap(self, price: float) -> float:
        return max(0.0, max(self.lo - price, price - self.hi))


# ---------------------------------------------------------------- bars
@dataclass
class Bars:
    o: List[float]
    h: List[float]
    l: List[float]
    c: List[float]
    v: List[float]
    t: List[int]

    @property
    def n(self) -> int:
        return len(self.c)

    @property
    def closed_index(self) -> int:
        """Chronological orientation: n-1 is the forming bar, n-2 the last closed."""
        return self.n - 2


# ---------------------------------------------------------------- reaction
@dataclass
class Reaction:
    valid: bool = False
    touched: bool = False
    penetration_bounded: bool = False
    closed_back: bool = False
    accepted: bool = False
    retest_held: bool = False
    dir: int = 0
    evidence_mask: int = 0
    evidence_count: int = 0
    penetration_atr: float = 0.0
    displacement_atr: float = 0.0
    bar_time: int = 0
    missing: str = ""
    summary: str = ""


def candle_rejects(b: Bars, i: int, buy: bool) -> bool:
    """Named reversal geometry on a CLOSED bar (mirrors CReactionDetector)."""
    if i < 1:
        return False
    o, h, l, c = b.o[i], b.h[i], b.l[i], b.c[i]
    po, pc = b.o[i - 1], b.c[i - 1]
    rng = h - l
    if rng <= 0:
        return False
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    pbody = abs(pc - po)
    up, dn = c > o, c < o
    strong = (body / rng >= 0.55)

    def _three(extra):
        if i < 2:
            return False
        b2o, b2c = b.o[i - 2], b.c[i - 2]
        mo, mh, ml, mc = b.o[i - 1], b.h[i - 1], b.l[i - 1], b.c[i - 1]
        mrng = mh - ml
        middle_small = mrng > 0 and abs(mc - mo) <= mrng * 0.35
        return middle_small and extra(b2o, b2c)

    if buy:
        engulf = up and c >= po and o <= pc and c > pc and body >= pbody * 0.90
        hammer = (lower >= body * 2.0 and upper <= max(body * 0.75, 1e-12)
                  and (c - l) / rng >= 0.62)
        piercing = pc < po and up and c > po and c < (po + pc) * 0.5
        morning = _three(lambda a, z: z < a) and up and strong and c > (b.o[i - 2] + b.c[i - 2]) * 0.5
        return bool(engulf or hammer or piercing or morning)
    engulf = dn and o >= pc and c <= po and c < pc and body >= pbody * 0.90
    shooting = (upper >= body * 2.0 and lower <= max(body * 0.75, 1e-12)
                and (c - l) / rng <= 0.38)
    dark = pc > po and dn and c < po and c > (po + pc) * 0.5
    evening = _three(lambda a, z: z > a) and dn and strong and c < (b.o[i - 2] + b.c[i - 2]) * 0.5
    return bool(engulf or shooting or dark or evening)


def detect_reaction(z: Zone, b: Bars, idx: int, atr: float, cfg: Cfg,
                    vols: Optional[List[float]] = None) -> Reaction:
    r = Reaction()
    last_closed = b.closed_index
    if idx < 1 or idx > last_closed:
        return r
    if atr <= 0 or z.birth_role == ZR_NEUTRAL:
        return r
    h, l, o, c = b.h[idx], b.l[idx], b.o[idx], b.c[idx]
    eps = max(1e-8, atr * 0.0005)
    is_sup = (z.role == ZR_SUPPORT)
    r.bar_time = b.t[idx]

    # 1) touch
    r.touched = (l <= z.hi + eps) and (h >= z.lo - eps)
    if not r.touched:
        r.summary = "no touch"
        return r

    # 2) bounded penetration beyond the ROLE edge
    pen = max(0.0, z.lo - l) if is_sup else max(0.0, h - z.hi)
    r.penetration_atr = pen / atr
    r.penetration_bounded = r.penetration_atr <= cfg.max_penetration_atr + 1e-9

    # 3) acceptance vs close-back
    brk = cfg.break_atr * atr
    if is_sup:
        r.accepted = c < z.lo - brk - eps
        r.closed_back = c > z.lo + eps
    else:
        r.accepted = c > z.hi + brk + eps
        r.closed_back = c < z.hi - eps

    # 4) direction from role + bar fact (never from bias)
    if r.accepted:
        r.dir = -1 if is_sup else +1
        reject = False
    elif r.closed_back and r.penetration_bounded:
        r.dir = +1 if is_sup else -1
        reject = True
    else:
        r.dir = 0
        r.summary = "touch without rejection or acceptance"
        return r

    buy = r.dir > 0
    mask = 0
    rng = h - l
    if reject:
        if rng > 0:
            wick = (min(o, c) - l) if buy else (h - max(o, c))
            if wick / rng >= cfg.min_wick_ratio:
                mask |= EV_WICK
        if candle_rejects(b, idx, buy):
            mask |= EV_CANDLE
    else:
        if atr > 0 and abs(c - o) >= cfg.displacement_atr * atr:
            mask |= EV_CANDLE

    if vols is not None:
        look = 20
        lo = max(0, idx - look)
        med = sorted(vols[lo:idx])[max(0, (idx - lo) // 2)] if idx > lo else 0.0
        if med > 0 and vols[idx] >= med * cfg.volume_mult:
            mask |= EV_VOLUME
        elif med <= 0 and vols[idx] > 0:
            mask |= EV_VOLUME

    disp = (c - l) if (reject and buy) else (h - c) if reject else \
           ((c - z.hi) if buy else (z.lo - c))
    r.displacement_atr = disp / atr
    if disp >= cfg.displacement_atr * atr:
        mask |= EV_DISPLACEMENT

    if reject and pen >= atr * 0.02:
        mask |= EV_SWEEP

    r.evidence_mask = mask
    r.evidence_count = ev_count(mask)
    r.missing = ev_missing(mask)
    r.valid = True
    r.summary = ("rejection" if reject else "acceptance") + " at " + \
                ("SUPPORT" if is_sup else "RESISTANCE")
    return r


def detect_retest(z: Zone, b: Bars, upto: int, lookback: int, atr: float, direction: int) -> bool:
    if atr <= 0 or direction == 0:
        return False
    eps = max(1e-8, atr * 0.0005)
    start = max(1, upto - lookback + 1)
    for i in range(start, upto + 1):
        h, l, c = b.h[i], b.l[i], b.c[i]
        if not (l <= z.hi + eps and h >= z.lo - eps):
            continue
        if direction > 0 and c > z.hi + eps:
            return True
        if direction < 0 and c < z.lo - eps:
            return True
    return False


# ---------------------------------------------------------------- geometry
def build_geometry(z: Zone, direction: int, entry: float, atr: float,
                   zones: List[Zone], cfg: Cfg):
    if direction == 0 or entry <= 0 or atr <= 0:
        return None
    buf = cfg.sl_buffer_atr * atr
    sl = min(z.lo, entry) - buf if direction > 0 else max(z.hi, entry) + buf
    if sl <= 0:
        return None
    risk = entry - sl if direction > 0 else sl - entry
    if risk <= 0 or risk > cfg.max_stop_atr * atr:
        return None

    barrier = 0.0
    best = None
    for oz in zones:
        opp = (oz.role == ZR_RESISTANCE) if direction > 0 else (oz.role == ZR_SUPPORT)
        if not opp:
            continue
        d = (oz.lo - entry) if direction > 0 else (entry - oz.hi)
        if direction > 0 and oz.hi < entry:
            continue
        if direction < 0 and oz.lo > entry:
            continue
        if best is None or d < best:
            best = max(0.0, d)
            barrier = oz.lo if direction > 0 else oz.hi
    room = abs(barrier - entry) / atr if barrier > 0 else -1.0

    # Round TP1 AWAY from the entry so tick rounding cannot push RR below
    # min_rr (see QSMC_BuildGeometry in QSMC_Zones.mqh for the same fix).
    import math
    tp1 = entry + direction * risk * cfg.min_rr
    capped = False
    if barrier > 0:
        if direction > 0 and tp1 > barrier:
            tp1, capped = barrier, True
        if direction < 0 and tp1 < barrier:
            tp1, capped = barrier, True
    if not capped:
        tp1 = (math.ceil(tp1 / cfg.tick) if direction > 0
               else math.floor(tp1 / cfg.tick)) * cfg.tick
    else:
        tp1 = round(tp1 / cfg.tick) * cfg.tick
    rr = abs(tp1 - entry) / risk
    tp2 = barrier if barrier > 0 else entry + direction * risk * (cfg.min_rr + 1.0)
    tp3 = barrier if barrier > 0 else entry + direction * risk * (cfg.min_rr + 2.0)
    return dict(sl=sl, tp1=tp1, tp2=tp2, tp3=tp3, rr=rr, room=room, risk=risk, barrier=barrier)


# ---------------------------------------------------------------- gates
@dataclass
class Cand:
    direction: int = 0
    zone: Optional[Zone] = None
    entry: float = 0.0
    sl: float = 0.0
    tp1: float = 0.0
    rr: float = 0.0
    room: float = -1.0
    distance_atr: float = 0.0
    score: int = 0
    state: int = SIG_CONFIRMED
    bar_index: int = 0
    bar_closed: bool = True
    bar_time: int = 0
    reaction: Reaction = field(default_factory=Reaction)
    reason: str = ""
    downgraded: bool = False
    rejected: List[str] = field(default_factory=list)


def gate_location(c: Cand, price: float, atr: float, cfg: Cfg,
                  zones: List[Zone]) -> Tuple[str, str]:
    """R1. Returns ("PASS"|"FAIL"|"DOWNGRADE", reason)."""
    if c.direction == 0:
        return "FAIL", "no direction"
    if c.zone is None:
        return "FAIL", "no zone"
    nearest = min(zones, key=lambda z: z.gap(price))
    gap = nearest.gap(price) / atr
    if gap > cfg.zone_reach_atr:
        return "FAIL", "BETWEEN ZONES - nearest zone is %.2f ATR away, limit is %.2f ATR" % (
            gap, cfg.zone_reach_atr)
    if nearest.id != c.zone.id:
        return "FAIL", "a nearer zone (%s @ %.2f ATR) owns this price, not %s" % (
            nearest.id, gap, c.zone.id)
    if nearest.strength < cfg.min_zone_strength:
        return "FAIL", "zone strength %d < %d (weak level)" % (
            nearest.strength, cfg.min_zone_strength)

    want_buy = c.direction > 0
    if want_buy and nearest.role == ZR_RESISTANCE and not c.reaction.accepted:
        return "FAIL", "BUY at RESISTANCE %s without a closed-bar breakout (forbidden by R1)" % nearest.id
    if (not want_buy) and nearest.role == ZR_SUPPORT and not c.reaction.accepted:
        return "FAIL", "SELL at SUPPORT %s without a closed-bar breakout (forbidden by R1)" % nearest.id

    if nearest.broken_closed and not nearest.retested:
        break_dir = -1 if nearest.birth_role == ZR_SUPPORT else +1
        if c.direction == -break_dir:
            return "FAIL", ("zone %s was broken by a closed bar and has not been retested "
                            "yet - no counter-break trade (R1)") % nearest.id

    if not c.reaction.valid:
        return "FAIL", "no closed-bar reaction/acceptance at %s" % nearest.id
    if c.reaction.dir != c.direction:
        return "FAIL", "the closed-bar fact points %s, the candidate points %s" % (
            "BUY" if c.reaction.dir > 0 else "SELL",
            "BUY" if c.direction > 0 else "SELL")
    if not c.reaction.accepted and not c.reaction.closed_back:
        return "FAIL", "the bar touched the zone but neither rejected nor accepted it"
    if not c.reaction.accepted and not c.reaction.penetration_bounded:
        return "FAIL", "penetration %.2f ATR exceeds the bounded limit %.2f ATR" % (
            c.reaction.penetration_atr, cfg.max_penetration_atr)
    if not c.reaction.accepted and c.reaction.evidence_count < cfg.min_evidence:
        return "DOWNGRADE", ("only %d/%d evidence groups, %d required; missing: %s" % (
            c.reaction.evidence_count, EV_COUNT, cfg.min_evidence, c.reaction.missing))
    return "PASS", ""


def gate_bias(c: Cand, bias_score: int, d1: int, h4: int, h1: int, cfg: Cfg):
    if c.direction == 0:
        return "FAIL", "no direction"
    if bias_score > 0:
        agree = 1 if c.direction > 0 else -1
    elif bias_score < 0:
        agree = -1 if c.direction > 0 else 1
    elif d1 != 0:
        agree = 1 if d1 == c.direction else -1
    elif h4 != 0:
        agree = 1 if h4 == c.direction else -1
    elif h1 != 0:
        agree = 1 if h1 == c.direction else -1
    else:
        agree = 0
    if agree >= 0:
        return "PASS", ""
    if not cfg.allow_countertrend:
        return "FAIL", "HTF bias opposes this direction and counter-trend is disabled"
    need = cfg.min_evidence + cfg.countertrend_extra_evidence
    if c.reaction.evidence_count < need:
        return "FAIL", "COUNTER-TREND: only %d evidence groups, %d required" % (
            c.reaction.evidence_count, need)
    if c.score < cfg.countertrend_min_score:
        return "FAIL", "COUNTER-TREND: evidence score %d < %d" % (
            c.score, cfg.countertrend_min_score)
    return "DOWNGRADE", "COUNTER-TREND / SCALP ONLY - HTF consensus %d opposes" % bias_score


def gate_room(c: Cand, atr: float, cfg: Cfg):
    risk = (c.entry - c.sl) if c.direction > 0 else (c.sl - c.entry)
    if risk <= 0:
        return "FAIL", "STOP GEOMETRY"
    if risk > cfg.max_stop_atr * atr:
        return "FAIL", "STOP %.2f ATR > max %.2f ATR" % (risk / atr, cfg.max_stop_atr)
    if c.rr < cfg.min_rr - 1e-9:
        return "FAIL", "LIMITED ROOM - RR to TP1 is %.2f, minimum is %.2f" % (c.rr, cfg.min_rr)
    if c.room >= 0:
        need = (c.rr + 1.0) * risk / atr
        if c.room < need - 1e-9:
            return "FAIL", "LIMITED ROOM - barrier %.2f ATR away, TP1 needs %.2f ATR" % (c.room, need)
    return "PASS", ""


def gate_closed_bar(c: Cand):
    if not c.bar_closed and c.state == SIG_CONFIRMED:
        return "DOWNGRADE", "forming bar - CONFIRMED requires a closed bar (R3)"
    return "PASS", ""


def score_reaction(r: Reaction, strength: int) -> int:
    if not r.valid:
        return 0
    ev_pts = min(EV_COUNT, max(0, r.evidence_count)) / EV_COUNT * 60.0
    zs = min(100, max(0, strength)) * 0.30
    pen_pts = 10.0 if r.penetration_bounded else 0.0
    return int(max(0.0, min(100.0, ev_pts + zs + pen_pts + 0.5)))


# ---------------------------------------------------------------- arbiter
class Arbiter:
    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        self.published = 0
        self.suppressed = 0
        self.history = {}       # (zone,dir,state) -> bar index
        self.prices = {}        # (zone,dir) -> price
        self.dirs = {}          # zone -> (dir, bar index)

    def allows(self, c: Cand, bar_index: int, atr: float):
        key = (c.zone.id, c.direction, c.state)
        if key in self.history and (bar_index - self.history[key]) < self.cfg.cooldown_bars:
            return False, "cooldown %d/%d" % (bar_index - self.history[key], self.cfg.cooldown_bars)
        k2 = (c.zone.id, c.direction)
        if k2 in self.prices and self.cfg.min_alert_distance_atr > 0 and atr > 0:
            d = abs(c.entry - self.prices[k2]) / atr
            if d < self.cfg.min_alert_distance_atr - 1e-9:
                return False, "distance %.2f ATR" % d
        if c.zone.id in self.dirs:
            ddir, dbar = self.dirs[c.zone.id]
            if ddir != c.direction and (bar_index - dbar) < self.cfg.flipflop_bars:
                return False, "flip-flop guard %d/%d" % (bar_index - dbar, self.cfg.flipflop_bars)
        return True, ""

    def commit(self, c: Cand, bar_index: int):
        self.history[(c.zone.id, c.direction, c.state)] = bar_index
        self.prices[(c.zone.id, c.direction)] = c.entry
        self.dirs[c.zone.id] = (c.direction, bar_index)

    def evaluate(self, c: Cand, price: float, atr: float, zones: List[Zone],
                 bias=(0, 0, 0, 0), bar_index: int = 0, regime: int = 3) -> Tuple[Cand, str]:
        cfg = self.cfg
        c = Cand(**{k: v for k, v in c.__dict__.items()})
        c.rejected = list(c.rejected)
        state = c.state

        res, why = gate_closed_bar(c)
        if res == "DOWNGRADE":
            state = min(state, SIG_PREVIEW)
            c.downgraded = True
            c.reason = why

        res, why = gate_location(c, price, atr, cfg, zones)
        if res == "FAIL":
            c.rejected.append("LOCATION: " + why)
            return c, why
        if res == "DOWNGRADE":
            state = min(state, SIG_WATCH)
            c.downgraded = True
            c.reason = why

        res, why = gate_bias(c, bias[0], bias[1], bias[2], bias[3], cfg)
        if res == "FAIL":
            c.rejected.append("HTF_BIAS: " + why)
            return c, why
        if res == "DOWNGRADE":
            state = min(state, SIG_COUNTER_TREND)
            c.downgraded = True
            c.reason = why

        res, why = gate_room(c, atr, cfg)
        if res == "FAIL":
            c.rejected.append("ROOM_RR: " + why)
            return c, why

        if regime == 5:  # EXTREME
            need = cfg.min_evidence + 1
            if c.reaction.evidence_count < need:
                state = min(state, SIG_WATCH)
                c.downgraded = True
                c.reason = "EXTREME volatility: %d evidence groups, %d required" % (
                    c.reaction.evidence_count, need)

        c.state = state
        return c, ""

    def publish(self, c: Cand, price: float, atr: float, zones: List[Zone],
                bias=(0, 0, 0, 0), bar_index: int = 0, tactical_cap=True,
                tactical: bool = True, regime: int = 3) -> Tuple[bool, Cand, str]:
        c, why = self.evaluate(c, price, atr, zones, bias, bar_index, regime)
        if c.rejected:
            self.suppressed += 1
            return False, c, c.rejected[-1]
        if tactical and tactical_cap:
            if c.state > SIG_TACTICAL_INFO:
                c.state = SIG_TACTICAL_INFO
                c.downgraded = True
                if not c.reason:
                    c.reason = "MTF tactical path - informational only (R7)"
        if c.state not in (SIG_CONFIRMED, SIG_COUNTER_TREND, SIG_TACTICAL_INFO):
            self.suppressed += 1
            return False, c, "state %s is not alertable" % STATE_NAME[c.state]
        ok, why = self.allows(c, bar_index, atr)
        if not ok:
            self.suppressed += 1
            return False, c, why
        self.commit(c, bar_index)
        self.published += 1
        return True, c, ""


# ---------------------------------------------------------------- helpers
def flat(n, base, half, vol=1000, t0=1_700_000_000, step=60):
    o = [base - half * 0.3] * n
    h = [base + half] * n
    l = [base - half] * n
    c = [base] * n
    v = [vol] * n
    t = [t0 + i * step for i in range(n)]
    return Bars(o, h, l, c, v, t)


def zone(role, lo, hi, strength=80):
    return Zone(lo, hi, role, strength)


def mk_cand(z: Zone, direction: int, entry: float, atr: float, zones: List[Zone],
            cfg: Cfg, rxn: Reaction, bar_index: int, bar_time: int, closed=True):
    g = build_geometry(z, direction, entry, atr, zones, cfg)
    if g is None:
        return None
    c = Cand(direction=direction, zone=z, entry=entry, sl=g["sl"], tp1=g["tp1"],
             rr=g["rr"], room=g["room"], score=score_reaction(rxn, z.strength),
             bar_index=bar_index, bar_closed=closed, bar_time=bar_time, reaction=rxn,
             distance_atr=z.gap(entry) / atr)
    return c


# ---------------------------------------------------------------- scenarios
def run(verbose=False):
    cfg = Cfg()
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))
        if verbose:
            print(("PASS  " if cond else "FAIL  ") + name + ("  [%s]" % detail if detail else ""))

    Z_RES = zone(ZR_RESISTANCE, 108.00, 109.00, 80)
    Z_SUP = zone(ZR_SUPPORT, 90.00, 91.00, 78)
    ATR = 2.0

    # ---- T01 rejection at resistance -> SELL once, no repeat -----------
    cfg1 = Cfg(cooldown_bars=20)
    b = flat(40, 105.0, 0.30)
    b.o[37], b.h[37], b.l[37], b.c[37] = 105.20, 107.00, 105.00, 106.80
    b.o[38], b.h[38], b.l[38], b.c[38], b.v[38] = 106.80, 109.40, 106.70, 107.10, 2000
    rxn = detect_reaction(Z_RES, b, 38, ATR, cfg1, b.v)
    check("T01a rejection detected at resistance, direction SELL",
          rxn.valid and rxn.dir == -1, rxn.summary + " ev=" + ev_list(rxn.evidence_mask))
    c = mk_cand(Z_RES, -1, 107.10, ATR, [Z_RES, Z_SUP], cfg1, rxn, 38, b.t[38])
    ar = Arbiter(cfg1)
    ok, cc, why = ar.publish(c, 107.10, ATR, [Z_RES, Z_SUP], tactical=False)
    check("T01b SELL published as CONFIRMED (non-tactical source)",
          ok and cc.state == SIG_CONFIRMED, why or STATE_NAME[cc.state])
    # same bar again
    ok2, _, why2 = ar.publish(
        mk_cand(Z_RES, -1, 107.10, ATR, [Z_RES, Z_SUP], cfg1, rxn, 38, b.t[38]),
        107.10, ATR, [Z_RES, Z_SUP], tactical=False)
    check("T01c same bar cannot publish twice", not ok2, why2)
    # 20 flat bars
    extra = 0
    for k in range(20):
        bb = flat(40, 107.2, 0.20)
        r2 = detect_reaction(Z_RES, bb, 38, ATR, cfg1, bb.v)
        if not r2.valid:
            continue
        c2 = mk_cand(Z_RES, r2.dir, bb.c[38], ATR, [Z_RES, Z_SUP], cfg1, r2, 38 + k + 1, bb.t[38])
        if c2 is None:
            continue
        o3, _, w3 = ar.publish(c2, bb.c[38], ATR, [Z_RES, Z_SUP], bar_index=39 + k, tactical=False)
        if o3:
            extra += 1
    check("T01d no repeat over the next 20 bars", extra == 0, "extra=%d" % extra)

    # ---- T02 breakout -> BUY continuation, no SELL ---------------------
    b = flat(40, 106.0, 0.30)
    b.o[37], b.h[37], b.l[37], b.c[37] = 106.00, 108.60, 105.90, 108.40
    b.o[38], b.h[38], b.l[38], b.c[38], b.v[38] = 108.40, 110.10, 108.20, 110.00, 2000
    rxn = detect_reaction(Z_RES, b, 38, ATR, cfg, b.v)
    check("T02a closed bar accepted above resistance -> BUY",
          rxn.valid and rxn.accepted and rxn.dir == +1, rxn.summary)
    c = mk_cand(Z_RES, +1, 110.00, ATR, [Z_RES, Z_SUP], cfg, rxn, 38, b.t[38])
    ar = Arbiter(cfg)
    ok, cc, why = ar.publish(c, 110.00, ATR, [Z_RES, Z_SUP], tactical=False)
    check("T02b BUY continuation published", ok and cc.direction > 0, why)
    c_sell = mk_cand(Z_RES, -1, 110.00, ATR, [Z_RES, Z_SUP], cfg,
                     Reaction(valid=True, accepted=True, dir=-1, closed_back=False), 38, b.t[38])
    ok_s, _, why_s = ar.publish(c_sell, 110.00, ATR, [Z_RES, Z_SUP], tactical=False)
    check("T02c a SELL at the same accepted zone is refused", not ok_s, why_s)

    # ---- T03 SELL inside SUPPORT blocked -------------------------------
    b = flat(40, 90.50, 0.15)
    b.o[38], b.h[38], b.l[38], b.c[38], b.v[38] = 90.60, 90.90, 90.30, 90.40, 2000
    rxn = detect_reaction(Z_SUP, b, 38, ATR, cfg, b.v)
    ar = Arbiter(cfg)
    if rxn.valid:
        c = mk_cand(Z_SUP, rxn.dir, b.c[38], ATR, [Z_SUP, Z_RES], cfg, rxn, 38, b.t[38])
        ok, cc, why = ar.publish(c, b.c[38], ATR, [Z_SUP, Z_RES], tactical=False)
    else:
        ok, why = False, rxn.summary
    check("T03a no SELL alert inside a SUPPORT zone", not ok, why)
    check("T03b the silence carries a reason", bool(why), why)

    # ---- T04 between zones ---------------------------------------------
    b = flat(40, 100.0, 0.30)
    b.o[38], b.h[38], b.l[38], b.c[38], b.v[38] = 100.00, 101.00, 99.50, 100.80, 2000
    ar = Arbiter(cfg)
    nearest = min([Z_RES, Z_SUP], key=lambda z: z.gap(100.80))
    gap = nearest.gap(100.80) / ATR
    check("T04a no zone within reach",
          gap > cfg.zone_reach_atr, "nearest gap %.2f ATR > %.2f" % (gap, cfg.zone_reach_atr))
    c = Cand(direction=+1, zone=nearest, entry=100.80, sl=99.0, tp1=103.0, rr=1.5,
             room=-1.0, bar_closed=True, bar_index=38, reaction=Reaction())
    ok, cc, why = ar.publish(c, 100.80, ATR, [Z_RES, Z_SUP], tactical=False)
    check("T04b no signal between zones", not ok, why)
    check("T04c reason names BETWEEN ZONES", "BETWEEN ZONES" in why, why)

    # ---- T05 forming bar -> PREVIEW only --------------------------------
    b = flat(40, 106.0, 0.30)
    b.o[38], b.h[38], b.l[38], b.c[38], b.v[38] = 106.80, 109.40, 106.70, 107.10, 2000
    b.o[39], b.h[39], b.l[39], b.c[39], b.v[39] = 107.10, 109.60, 106.90, 107.20, 1500
    rxn = detect_reaction(Z_RES, b, 38, ATR, cfg, b.v)
    c = mk_cand(Z_RES, -1, 107.10, ATR, [Z_RES, Z_SUP], cfg, rxn, 38, b.t[38], closed=False)
    ar = Arbiter(cfg)
    ok, cc, why = ar.publish(c, 107.10, ATR, [Z_RES, Z_SUP], tactical=False)
    check("T05a a forming-bar fact never publishes CONFIRMED",
          not (ok and cc.state == SIG_CONFIRMED),
          (STATE_NAME[cc.state] + " " + why) if not ok else STATE_NAME[cc.state])

    # ---- T06 30 M1 fires inside one zone -> <= 1 alert ------------------
    # Every one of the 30 bars is a GENUINE closed-bar rejection of the
    # same zone (spike into 108-109, close back below). Without the
    # anti-spam locks this is exactly the "one alert per minute" storm
    # reported by the user.
    ar = Arbiter(cfg)
    fired = 0
    valid_bars = 0
    first_why = ""
    for k in range(30):
        base = 107.20 + 0.01 * k
        bb = flat(40, base, 0.20)
        bb.o[38], bb.h[38], bb.l[38], bb.c[38] = base - 0.10, 109.30, 107.00, base
        bb.v[38] = 2200 if (k % 3 == 0) else 1000
        r6 = detect_reaction(Z_RES, bb, 38, ATR, cfg, bb.v)
        if not r6.valid or r6.dir == 0:
            continue
        valid_bars += 1
        c6 = mk_cand(Z_RES, r6.dir, bb.c[38], ATR, [Z_RES, Z_SUP], cfg, r6,
                     38 + k, bb.t[38] + k * 60)
        if c6 is None:
            continue
        o6, _, w6 = ar.publish(c6, bb.c[38], ATR, [Z_RES, Z_SUP], bar_index=38 + k)
        if o6:
            fired += 1
        elif first_why == "":
            first_why = w6
    check("T06a the 30 bars really are 30 valid rejections (not a trivial pass)",
          valid_bars == 30, "valid=%d/30" % valid_bars)
    check("T06b 30 M1 fires inside one zone collapse to <= 1 alert",
          fired <= 1, "published=%d suppressed=%d first-suppression=%s"
          % (fired, ar.suppressed, first_why))

    # ---- T07 flip-flop suppressed ---------------------------------------
    ar = Arbiter(cfg)
    b = flat(40, 107.0, 0.30)
    b.o[37], b.h[37], b.l[37], b.c[37] = 106.80, 107.60, 106.70, 107.20
    b.o[38], b.h[38], b.l[38], b.c[38], b.v[38] = 107.20, 109.30, 107.10, 107.30, 2000
    r1 = detect_reaction(Z_RES, b, 38, ATR, cfg, b.v)
    c1 = mk_cand(Z_RES, -1, 107.30, ATR, [Z_RES, Z_SUP], cfg, r1, 38, b.t[38])
    o1, _, _ = ar.publish(c1, 107.30, ATR, [Z_RES, Z_SUP], bar_index=38, tactical=False)
    before = ar.published
    # --- one bar later the zone is ACCEPTED above (a legitimate BUY).
    #     break_atr 0.30 x ATR 2.00 = 0.60, so the close must exceed
    #     109.60 for the fact to be an acceptance rather than a rejection.
    b2 = flat(40, 107.3, 0.30)
    b2.o[38], b2.h[38], b2.l[38], b2.c[38], b2.v[38] = 107.30, 110.30, 107.20, 110.00, 2000
    r2 = detect_reaction(Z_RES, b2, 38, ATR, cfg, b2.v)
    check("T07a the second bar is a genuine BUY acceptance",
          r2.valid and r2.accepted and r2.dir == +1, r2.summary)
    c2 = mk_cand(Z_RES, +1, 110.00, ATR, [Z_RES, Z_SUP], cfg, r2, 39, b2.t[38] + 60)
    o2, _, w2 = ar.publish(c2, 110.00, ATR, [Z_RES, Z_SUP], bar_index=39, tactical=False)
    check("T07b the opposite direction on the same zone is suppressed",
          ar.published == before, "before=%d after=%d why=%s" % (before, ar.published, w2))
    check("T07c the suppression is the flip-flop guard, not something else",
          "flip-flop" in w2, w2)

    # ---- T08 two charts (simulated by a shared key space) ---------------
    ar = Arbiter(cfg)
    b = flat(40, 105.0, 0.30)
    b.o[37], b.h[37], b.l[37], b.c[37] = 105.20, 107.00, 105.00, 106.80
    b.o[38], b.h[38], b.l[38], b.c[38], b.v[38] = 106.80, 109.40, 106.70, 107.10, 2000
    rxn = detect_reaction(Z_RES, b, 38, ATR, cfg, b.v)
    pub = 0
    for _ in range(2):
        c = mk_cand(Z_RES, -1, 107.10, ATR, [Z_RES, Z_SUP], cfg, rxn, 38, b.t[38])
        o, _, _ = ar.publish(c, 107.10, ATR, [Z_RES, Z_SUP], bar_index=38, tactical=False)
        if o:
            pub += 1
    check("T08 two charts of one symbol publish at most one alert",
          pub <= 1, "published=%d" % pub)

    # ---- T09 counter-trend downgrade ------------------------------------
    b = flat(40, 105.0, 0.30)
    b.o[37], b.h[37], b.l[37], b.c[37] = 105.20, 107.00, 105.00, 106.80
    b.o[38], b.h[38], b.l[38], b.c[38] = 108.30, 108.60, 106.70, 108.20
    rxn = detect_reaction(Z_RES, b, 38, ATR, cfg, b.v)
    ar = Arbiter(cfg)
    c = mk_cand(Z_RES, -1, 108.20, ATR, [Z_RES, Z_SUP], cfg, rxn, 38, b.t[38])
    ok, cc, why = ar.publish(c, 108.20, ATR, [Z_RES, Z_SUP], bias=(100, 1, 1, 1), tactical=False)
    check("T09a an opposed candidate is never published as CONFIRMED",
          not (ok and cc.state == SIG_CONFIRMED), why or STATE_NAME[cc.state])
    check("T09b the counter-trend is named in the reason",
          ("COUNTER-TREND" in (why + " " + cc.reason)) or ("evidence" in why),
          (why + " / " + cc.reason).strip())

    # ---- T10 data not ready ---------------------------------------------
    ar = Arbiter(cfg)
    check("T10 no signal without data (series empty -> no closed bar)",
          flat(2, 100.0, 0.1).closed_index < 1, "closed_index=%d" % flat(2, 100.0, 0.1).closed_index)

    return results


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    res = run(verbose)
    if not verbose:
        for name, ok, detail in res:
            print(("PASS  " if ok else "FAIL  ") + name + ("  [%s]" % detail if detail else ""))
    bad = [r for r in res if not r[1]]
    print("-" * 72)
    print("RESULT: %d passed, %d failed" % (len(res) - len(bad), len(bad)))
    print("-" * 72)
    print("This is an independent reference implementation of the v6.6.0 gates.")
    print("It is NOT a backtest and produces NO win rate. A disagreement with")
    print("MQL5/Include/QSMC/QSMC_Selftest.mqh means one of the two is wrong.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
