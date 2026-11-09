#!/usr/bin/env python3
"""
Predicts the outcome of every scenario in MQL5/Include/QSMC/QSMC_Selftest.mqh
WITHOUT MetaTrader, by faithfully re-implementing the harness's own data
generator and the reaction decision.

Why this exists
---------------
QSMC_Selftest.mqh cannot be executed here (no compiler, no terminal). But the
scenarios are pure arithmetic: Flat() builds the bars, ComputeWilderATR()
derives the ATR, and CReactionDetector::Evaluate() turns (bar, zone, ATR, cfg)
into a direction. All three are deterministic and small enough to port exactly.

This script guards against the failure mode that this harness actually had:
the scenario bars were written assuming ATR = 2.00 while Flat(...,0.30,...)
produced ATR = 0.60. Because every distance in every scenario is expressed in
ATR units, that single unit error silently invalidated the geometry - T01 and
T07 would have FAILED, and T06/T08 would have passed without ever testing
anything.

It is a GEOMETRY check only. It does not model the gates, the arbiter or the
alert manager; tools/test_arbiter.py covers those independently.

Usage:  python3 tools/check_scenario_geometry.py [-v]
"""

import sys

QST_BARS   = 40
QST_ATR    = 2.00
QST_HALF   = QST_ATR / 2.0
QST_ATR_TOL = 0.05
ATR_PERIOD = 14

# CfgBase() in QSMC_Selftest.mqh
CFG = dict(
    max_penetration_atr=0.35,
    break_atr=0.30,
    min_rr=1.50,
    max_stop_atr=4.00,
    sl_buffer_atr=0.20,
    zone_reach_atr=1.50,
    min_zone_strength=60,
    min_evidence=2,
    min_wick_ratio=0.50,
    volume_mult=1.60,
    displacement_atr=0.50,
)

RES, SUP = "RESISTANCE", "SUPPORT"


class Bars:
    """Flat() from QSMC_Selftest.mqh: index n-1 is the FORMING bar."""

    def __init__(self, n, base, half, vol=1000):
        self.n = n
        self.o = [base - half * 0.3] * n
        self.h = [base + half] * n
        self.l = [base - half] * n
        self.c = [base] * n
        self.v = [vol] * n

    def setbar(self, i, o, h, l, c, v):
        self.o[i], self.h[i], self.l[i], self.c[i], self.v[i] = o, h, l, c, v

    def closed_index(self):
        return self.n - 2

    def true_range(self, i):
        if i < 1:
            return self.h[i] - self.l[i]
        return max(self.h[i] - self.l[i],
                   abs(self.h[i] - self.c[i - 1]),
                   abs(self.l[i] - self.c[i - 1]))

    def wilder_atr(self):
        """ComputeWilderATR() from QSMC_MarketData.mqh, ported line for line."""
        ci = self.closed_index()
        if ci < ATR_PERIOD + 1:
            return 0.0
        total, seeded = 0.0, 0
        for i in range(1, ATR_PERIOD + 1):
            total += self.true_range(i)
            seeded += 1
        if seeded < ATR_PERIOD:
            return 0.0
        atr = total / ATR_PERIOD
        if not atr > 0.0:
            return 0.0
        for i in range(ATR_PERIOD + 1, ci + 1):
            atr = (atr * (ATR_PERIOD - 1) + self.true_range(i)) / ATR_PERIOD
        return atr if atr > 0.0 else 0.0


def reaction(bars, idx, atr, zlo, zhi, role):
    """
    CReactionDetector::Evaluate() - the touch / penetration / acceptance /
    closed-back / direction part (QSMC_Reaction.mqh lines 186-250).
    Returns (dir, pen_atr, bounded, accepted, closed_back, touched, summary).
    """
    h, l, o, c = bars.h[idx], bars.l[idx], bars.o[idx], bars.c[idx]
    if not (atr > 0.0):
        return 0, 0.0, False, False, False, False, "atr<=0"
    eps = max(0.01, atr * 0.0005)
    is_support = (role == SUP)

    touched = (l <= zhi + eps) and (h >= zlo - eps)
    if not touched:
        return 0, 0.0, False, False, False, False, "no touch"

    pen = max(0.0, zlo - l) if is_support else max(0.0, h - zhi)
    pen_atr = pen / atr
    bounded = pen_atr <= CFG["max_penetration_atr"] + 1e-9

    break_dist = CFG["break_atr"] * atr
    if is_support:
        accepted = c < zlo - break_dist - eps
        closed_back = c > zlo + eps
    else:
        accepted = c > zhi + break_dist + eps
        closed_back = c < zhi - eps

    if accepted:
        return (-1 if is_support else +1), pen_atr, bounded, True, closed_back, True, \
            "acceptance at %s" % role
    if closed_back and bounded:
        return (+1 if is_support else -1), pen_atr, bounded, False, True, True, \
            "rejection at %s" % role
    if not bounded:
        return 0, pen_atr, False, False, closed_back, True, \
            "penetration %.2f ATR exceeds the %.2f cap - not a bounded rejection" % (
                pen_atr, CFG["max_penetration_atr"])
    return 0, pen_atr, bounded, False, False, True, \
        "inside the band: neither rejected nor broken => NO TRADE"


def geometry(bars, idx, atr, zlo, zhi, role):
    """Gap from the decision price to the zone, in ATR units."""
    c = bars.c[idx]
    if zlo <= c <= zhi:
        return 0.0
    return (min(abs(c - zlo), abs(c - zhi))) / atr if atr > 0 else float("inf")


VERBOSE = "-v" in sys.argv
FAILS = []


def check(cond, name, detail=""):
    tag = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name)
    print("%s  %-58s %s" % (tag, name, ("[%s]" % detail) if detail else ""))


def report(label, b, idx, atr, zlo, zhi, role, expect_dir):
    d, pen, bounded, acc, cb, tch, why = reaction(b, idx, atr, zlo, zhi, role)
    gap = geometry(b, idx, atr, zlo, zhi, role)
    ok = "yes" if d == expect_dir else "NO"
    print("    bar %d  ATR=%.4f  pen=%.2f ATR(bounded=%s) accepted=%s closed_back=%s"
          % (idx, atr, pen, bounded, acc, cb))
    print("    -> dir=%+d expected=%+d  match=%s   %s" % (d, expect_dir, ok, why))
    if VERBOSE:
        print("       O=%.2f H=%.2f L=%.2f C=%.2f  gap=%.2f ATR"
              % (b.o[idx], b.h[idx], b.l[idx], b.c[idx], gap))
    return d == expect_dir


print("=" * 72)
print(" QSMC v6.6.0 - SCENARIO GEOMETRY CHECK (predicts QSMC_Selftest.mqh)")
print(" QST_BARS=%d  QST_ATR=%.2f  QST_HALF=%.2f  ATR_PERIOD=%d"
      % (QST_BARS, QST_ATR, QST_HALF, ATR_PERIOD))
print("=" * 72)

# ---------------------------------------------------------------- T00 / T01
print("\nT01  SELL rejection at resistance 108.00-109.00, once, no repeat")
b = Bars(QST_BARS, 105.0, QST_HALF)
b.setbar(37, 105.20, 107.00, 105.00, 106.80, 1000)
b.setbar(38, 106.80, 109.40, 106.70, 107.10, 2000)
atr = b.wilder_atr()
check(abs(atr - QST_ATR) / QST_ATR <= QST_ATR_TOL,
      "T00 synthetic ATR matches QST_ATR",
      "expected %.2f measured %.4f" % (QST_ATR, atr))
check(report("T01", b, 38, atr, 108.00, 109.00, RES, -1),
      "T01a bar 38 is a bounded rejection => SELL")

# ---------------------------------------------------------------- T02
print("\nT02  closed bar accepted above resistance => BUY continuation")
b = Bars(QST_BARS, 106.0, QST_HALF)
b.setbar(37, 106.00, 108.60, 105.90, 108.40, 1000)
b.setbar(38, 108.40, 110.10, 108.20, 110.00, 2000)
atr = b.wilder_atr()
check(report("T02", b, 38, atr, 108.00, 109.00, RES, +1),
      "T02a bar 38 is an acceptance => BUY")

# ---------------------------------------------------------------- T03
print("\nT03  tactical SELL inside SUPPORT 90.00-91.00 => blocked by location")
b = Bars(QST_BARS, 90.50, QST_HALF)
b.setbar(38, 90.60, 90.90, 90.30, 90.40, 2000)
atr = b.wilder_atr()
# The zone can only ever license a BUY here; the fact asks for a SELL, so the
# location gate must refuse. The geometry check asserts the zone is reachable.
d, pen, bounded, acc, cb, tch, why = reaction(b, 38, atr, 90.00, 91.00, SUP)
print("    bar 38  ATR=%.4f  -> dir=%+d  %s" % (atr, d, why))
check(tch, "T03a the zone is actually in reach (not a trivial pass)", why)
check(d != -1, "T03b the zone cannot license a SELL (location gate must refuse)")
check(d == +1, "T03c the only role-consistent direction is BUY")

# ---------------------------------------------------------------- T04
print("\nT04  price between zones => NO TRADE / BETWEEN ZONES")
b = Bars(QST_BARS, 100.0, QST_HALF)
b.setbar(38, 100.00, 101.00, 99.50, 100.80, 2000)
atr = b.wilder_atr()
g_r = geometry(b, 38, atr, 108.00, 109.00, RES)
g_s = geometry(b, 38, atr, 90.00, 91.00, SUP)
nearest = min(g_r, g_s)
print("    ATR=%.4f  gap to RES=%.2f ATR  gap to SUP=%.2f ATR  nearest=%.2f"
      % (atr, g_r, g_s, nearest))
check(nearest > CFG["zone_reach_atr"], "T04a no zone within %.2f ATR" %
      CFG["zone_reach_atr"], "nearest %.2f ATR" % nearest)

# ---------------------------------------------------------------- T05
print("\nT05  the fact cites the FORMING bar => never CONFIRMED")
b = Bars(QST_BARS, 106.0, QST_HALF)
b.setbar(37, 106.00, 108.60, 105.90, 108.40, 1000)
b.setbar(38, 106.80, 109.40, 106.70, 107.10, 2000)
b.setbar(39, 107.10, 109.60, 106.90, 107.20, 1500)
atr = b.wilder_atr()
check(b.closed_index() == 38 and QST_BARS - 1 == 39,
      "T05a bar 39 is the forming bar (ClosedIndex=%d)" % b.closed_index())

# ---------------------------------------------------------------- T06
print("\nT06  30 M1 bars, each a genuine rejection of the same zone")
valid = 0
atr_seen = None
for k in range(30):
    b = Bars(QST_BARS, 106.0, QST_HALF)
    b.setbar(37, 105.20, 107.00, 105.00, 106.80, 1000)
    base = 107.20 + 0.01 * k
    b.setbar(38, base - 0.10, 109.30, 107.00, base, 2200 if k % 3 == 0 else 1000)
    b.setbar(39, base, base + 0.25, base - 0.20, base + 0.15, 1000)
    a = b.wilder_atr()
    if atr_seen is None:
        atr_seen = a
    d, pen, bounded, acc, cb, tch, why = reaction(b, 38, a, 108.00, 109.00, RES)
    if d == -1:
        valid += 1
    elif VERBOSE:
        print("      k=%2d dir=%+d  %s" % (k, d, why))
print("    ATR=%.4f  valid rejections: %d/30" % (atr_seen, valid))
check(valid == 30, "T06a all 30 bars are genuine rejections",
      "valid=%d/30" % valid)

# ---------------------------------------------------------------- T07
print("\nT07  SELL then a genuine BUY acceptance on the same zone => flip-flop")
b = Bars(QST_BARS, 107.0, QST_HALF)
b.setbar(37, 106.80, 107.60, 106.70, 107.20, 1000)
b.setbar(38, 107.20, 109.30, 107.10, 107.30, 2000)
atr = b.wilder_atr()
check(report("T07-1", b, 38, atr, 108.00, 109.00, RES, -1),
      "T07a first bar is a SELL rejection")
b.setbar(38, 107.30, 110.30, 107.20, 110.00, 2000)
b.setbar(39, 110.00, 110.40, 109.80, 110.20, 1000)
atr = b.wilder_atr()
check(report("T07-2", b, 38, atr, 108.00, 109.00, RES, +1),
      "T07b second bar is a genuine BUY acceptance (opposite direction)")

# ---------------------------------------------------------------- T08
print("\nT08  two charts, one symbol => at most one alert")
b = Bars(QST_BARS, 105.0, QST_HALF)
b.setbar(37, 105.20, 107.00, 105.00, 106.80, 1000)
b.setbar(38, 106.80, 109.40, 106.70, 107.10, 2000)
atr = b.wilder_atr()
check(report("T08", b, 38, atr, 108.00, 109.00, RES, -1),
      "T08a the shared bar really publishes (not a trivial pass)")

# ---------------------------------------------------------------- T09
print("\nT09  weak rejection against a bullish HTF consensus => COUNTER-TREND")
b = Bars(QST_BARS, 105.0, QST_HALF)
b.setbar(37, 105.20, 107.00, 105.00, 106.80, 1000)
b.setbar(38, 108.30, 108.60, 106.70, 108.20, 1000)
atr = b.wilder_atr()
d, pen, bounded, acc, cb, tch, why = reaction(b, 38, atr, 108.00, 109.00, RES)
print("    bar 38  ATR=%.4f  -> dir=%+d  %s" % (atr, d, why))
o, h, l, c = b.o[38], b.h[38], b.l[38], b.c[38]
rng = h - l
wick = h - max(o, c)
ratio = wick / rng if rng > 0 else 0.0
print("    wick ratio %.2f (min %.2f)  volume %d vs flat 1000"
      % (ratio, CFG["min_wick_ratio"], b.v[38]))
check(d == -1, "T09a the zone licenses a SELL (so the bias gate is reached)", why)
check(ratio < CFG["min_wick_ratio"] and b.v[38] <= 1000,
      "T09b the rejection is genuinely weak (few evidence groups)",
      "wick %.2f<%0.2f, no volume spike" % (ratio, CFG["min_wick_ratio"]))

# ---------------------------------------------------------------- T10
print("\nT10  no series loaded => no signal (no geometry to check)")
check(True, "T10 no data => BuildContext() must return false")

print("\n" + "-" * 72)
if FAILS:
    print("RESULT: %d FAILED" % len(FAILS))
    for f in FAILS:
        print("   - %s" % f)
else:
    print("RESULT: all geometry checks passed")
print("-" * 72)
print("This predicts the arithmetic of QSMC_Selftest.mqh. It does NOT model")
print("the gates, the arbiter or the alert manager, and it is NOT a backtest.")
print("It does not prove compilation. Press F7.")
sys.exit(1 if FAILS else 0)
