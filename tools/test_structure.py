#!/usr/bin/env python3
"""Independent contract tests for the causal structure-event definitions.

This intentionally models event timing and boundary rules separately from the
MQL5 engine. It is not a market replay or a profitability test.
"""
from dataclasses import dataclass

FAILS = []


def check(ok, label):
    print(("PASS" if ok else "FAIL") + "  " + label)
    if not ok:
        FAILS.append(label)


@dataclass
class Bar:
    t: int
    high: float
    low: float
    open: float = 10.
    close: float = 10.


def strict_swing(values, pivot, left, right, high=True):
    if pivot-left < 0 or pivot+right >= len(values):
        return False
    center = values[pivot]
    neighbors = values[pivot-left:pivot] + values[pivot+1:pivot+right+1]
    return all(center > x for x in neighbors) if high else all(center < x for x in neighbors)


# The pivot is at bar 2, but the event must not exist until bar 4 closes.
highs = [12., 12., 15., 12., 11., 12., 18., 12., 12., 22.]
confirmed_at = None
for closed in range(len(highs)):
    pivot = closed-2
    if pivot >= 2 and strict_swing(highs, pivot, 2, 2):
        confirmed_at = closed
        break
check(confirmed_at == 4, "strict pivot high is emitted on right-side confirmation, not at pivot time")
check(not strict_swing([12., 15., 15., 12.], 1, 1, 1), "equal-high plateau is not arbitrarily selected as a swing")

# Structural breaks use closed price beyond a buffer, not wick-only penetration.
level, buffer = 18., .25
wick_only = Bar(10, high=20., low=17., open=17.5, close=18.1)
close_break = Bar(11, high=20., low=17., open=19., close=18.3)
check(wick_only.high > level and not (wick_only.close > level+buffer), "wick penetration alone is not BOS")
check(close_break.close > level+buffer, "closed close beyond confirmed swing level qualifies for BOS")

# State machine: initial break -> BOS/up; opposite structural close -> invalidation + CHoCH/down.
trend = 0
up_bos = close_break.close > level+buffer
if up_bos:
    trend = 1
low_level = 7.
down_close = 6.5
invalidated = trend == 1 and down_close < low_level-buffer
choch_down = invalidated
if choch_down:
    trend = -1
check(up_bos and choch_down and trend == -1, "BOS establishes trend; opposite close invalidates and emits CHoCH")

# Liquidity only exists after two confirmed highs are equal within tolerance.
first, second, equal_tol = 15., 15.08, .15
pool = (first+second)/2 if abs(first-second) <= equal_tol else None
sweep_high, sweep_close = 15.5, 15.0
break_close = 15.4
check(pool is not None, "two confirmed equal highs form buy-side liquidity")
check(sweep_high > pool+.2 and sweep_close <= pool, "wick through pool plus close-back is a one-shot sweep")
check(break_close > pool+.25, "close beyond configured break buffer is breakout, not sweep")
check(abs(15.-15.3) > equal_tol, "a lone swing is not promoted to equal-high liquidity")

# Event-time fields retain pivot time separately from availability boundary.
pivot_time, confirmation_bar_open, availability = 120, 240, 300
check(pivot_time < confirmation_bar_open < availability,
      "event time and signal-availability time remain distinct and causal")


def direction(htf_dir, htf_score, structure_dir):
    raw = (0.65*htf_score if htf_dir else 0.)
    if htf_dir and abs(raw) < 10:
        raw = 10.*htf_dir
    raw += 35.*structure_dir
    score = max(-100, min(100, round(raw)))
    conflict = bool(htf_dir and structure_dir and htf_dir != structure_dir)
    out = 0 if conflict else (htf_dir or structure_dir)
    return out, score, conflict

aligned = direction(1, 80, 1)
conflict = direction(-1, -80, 1)
htf_only = direction(1, 60, 0)
local_only = direction(0, 0, -1)
check(aligned[0] == 1 and aligned[1] == 87 and not aligned[2],
      "aligned HTF and confirmed local structure strengthen directional context")
check(conflict[0] == 0 and conflict[2],
      "opposing HTF/local trends resolve to MIXED, not forced direction")
check(htf_only[0] == 1 and local_only[0] == -1,
      "direction label identifies the sole available evidence source")

if FAILS:
    raise SystemExit("%d structure contract test(s) failed" % len(FAILS))
print("All structure contract checks passed; this is not a backtest.")
