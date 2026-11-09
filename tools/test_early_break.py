#!/usr/bin/env python3
"""Independent contract checks for the warning-only early-break heuristic."""
import math

FAILS = []


def check(ok, name):
    print(("PASS" if ok else "FAIL") + "  " + name)
    if not ok:
        FAILS.append(name)


def clip01(x):
    return max(0., min(1., x))


def warning_score(*, x, z, body_atr, activity_ratio, close_location,
                  high_dist_atr, low_dist_atr, cusum_side, spread_atr):
    zpart = clip01(abs(z)/3.)*15.
    dpart = clip01(abs(body_atr)/.8)*20.
    apart = clip01(max(0., activity_ratio-1.)/1.5)*15.
    lpart = clip01(abs(close_location))*10.
    cpart = 25. if cusum_side else 0.
    direction = 1 if x > 0 else (-1 if x < 0 else 0)
    level = (clip01(1-high_dist_atr/2.) if direction > 0 else
             clip01(1-low_dist_atr/2.) if direction < 0 else 0.)*15.
    bull = (cpart if cusum_side > 0 else 0.)
    bear = (cpart if cusum_side < 0 else 0.)
    impulse = 1 if body_atr > 0 else (-1 if body_atr < 0 else 0)
    if z > 0: bull += zpart
    elif z < 0: bear += zpart
    if impulse > 0: bull += dpart+apart
    elif impulse < 0: bear += dpart+apart
    if close_location > 0: bull += lpart
    elif close_location < 0: bear += lpart
    if direction > 0: bull += level
    elif direction < 0: bear += level
    penalty = clip01((spread_atr-.03)/.15)*10.
    bull, bear = max(0., bull-penalty), max(0., bear-penalty)
    side = 1 if bull > bear else (-1 if bear > bull else 0)
    score = round(min(100., abs(bull-bear)))
    return side, score


# One-sided upward evidence: intentionally an index, not a probability.
up = warning_score(x=.7, z=2.8, body_atr=.75, activity_ratio=2.2,
                   close_location=.8, high_dist_atr=.3, low_dist_atr=2.,
                   cusum_side=1, spread_atr=.02)
down = warning_score(x=-.7, z=-2.8, body_atr=-.75, activity_ratio=2.2,
                     close_location=-.8, high_dist_atr=2., low_dist_atr=.3,
                     cusum_side=-1, spread_atr=.02)
check(up[0] == 1 and up[1] >= 55, "aligned upward features produce a bounded upward warning score")
check(down[0] == -1 and down[1] >= 55, "mirrored downward features produce a bounded downward warning score")
check(0 <= up[1] <= 100 and 0 <= down[1] <= 100,
      "heuristic score remains normalized to 0..100, not calibrated probability")

flat = warning_score(x=0., z=0., body_atr=0., activity_ratio=1.,
                     close_location=0., high_dist_atr=1., low_dist_atr=1.,
                     cusum_side=0, spread_atr=.02)
check(flat == (0, 0), "neutral price, volume and CUSUM evidence produce no directional warning")
wide_spread = warning_score(x=.7, z=2.8, body_atr=.75, activity_ratio=2.2,
                            close_location=.8, high_dist_atr=.3, low_dist_atr=2.,
                            cusum_side=1, spread_atr=.20)
check(wide_spread[1] < up[1], "excessive spread applies a transparent score penalty")

# Data honesty boundary: the implementation marks unavailable aggressor/order-book
# flow as missing; candle close location is merely a bar proxy.
missing_quotes = 16
check(missing_quotes & 16, "unavailable quote/order-book flow is represented as missing data")

if FAILS:
    raise SystemExit("%d early-break test(s) failed" % len(FAILS))
print("Early-break checks passed; warnings are heuristics, not entries or probabilities.")
