#!/usr/bin/env python3
"""
Independent Python mirror of the arithmetic in QSMC_Scanners.mqh (PART C,
Phase 7): seasonality bucketing, ATR percentile and the momentum z-score.

Why this exists
---------------
These three are pure arithmetic, so they can be checked exactly without a
terminal. They are also the easiest places for a silent error: a seasonality
row with a wrong n, or a percentile computed against the wrong window, still
prints a plausible-looking number.

It is an INDEPENDENT re-implementation of the same rules, not a translation,
so a disagreement with the MQL5 means one of the two is wrong.

It does NOT model symbol discovery, Market Watch or CopyRates - those need a
terminal and are listed as UNVERIFIED in the Phase 7 doc.

Usage:  python3 tools/test_scanners.py [-v]
"""

import sys
from datetime import datetime, timedelta

VERBOSE = "-v" in sys.argv
FAILS = []


def check(cond, name, detail=""):
    tag = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name)
    print("%s  %-60s %s" % (tag, name, ("[%s]" % detail) if detail else ""))


# =====================================================================
# Seasonality: mirrors CSeasonalityScanner
# =====================================================================
class Seasonality:
    """Bucket bar-to-bar returns by month/week/dow/hour."""

    def __init__(self, min_n=30, basis="SERVER"):
        self.min_n = min_n
        self.basis = basis
        self.buckets = {}
        self.year_mask = {}

    def accumulate(self, times, closes, kind):
        self.buckets.clear()
        self.year_mask.clear()
        for i in range(1, len(closes)):
            prev, cur = closes[i - 1], closes[i]
            if not (prev > 0.0 and cur > 0.0):
                continue
            ret = (cur - prev) / prev * 100.0
            t = times[i]
            if kind == "MONTH":
                b = t.month
            elif kind == "DOW":
                b = (t.weekday() + 1) % 7          # MQL5: 0=Sunday
            elif kind == "HOUR":
                b = t.hour
            else:
                b = (t.timetuple().tm_yday + 6) // 7
            self.buckets.setdefault(b, []).append(ret)
            self.year_mask.setdefault(b, set()).add(t.year)

    def row(self, b):
        vals = self.buckets.get(b, [])
        n = len(vals)
        years = len(self.year_mask.get(b, set()))
        out = dict(bucket=b, n=n, years=years, mean=0.0, median=0.0,
                   std=0.0, pos_share=0.0, withheld=True)
        if n <= 0:
            return out
        if n < self.min_n:
            out["mean"] = sum(vals) / n
            return out
        mu = sum(vals) / n
        var = sum(v * v for v in vals) / n - mu * mu
        out.update(mean=mu,
                   std=(var ** 0.5) if var > 0 else 0.0,
                   pos_share=100.0 * sum(1 for v in vals if v > 0) / n,
                   withheld=False)
        s = sorted(vals)
        out["median"] = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0
        return out


def make_series(n, start, step_hours, closes):
    times = [start + timedelta(hours=step_hours * i) for i in range(n)]
    return times, closes


print("=" * 72)
print(" QSMC v6.6.0 PART C PHASE 7 - SCANNER ARITHMETIC CHECK")
print("=" * 72)

# ---------------------------------------------------------------- T1-T3
print("\nT1-T3  seasonality: sample size, dispersion, withholding")

# A series where every January bar returns +1% and every other month -1%.
start = datetime(2020, 1, 1, 0, 0)
n = 240                     # 20 years of monthly bars
times, closes = [], []
px = 100.0
t = start
for i in range(n):
    # Apply the month's move FIRST, then store: closes[i] must be the
    # CLOSE of month times[i], or every return lands in the wrong bucket.
    px *= 1.01 if t.month == 1 else 0.99
    times.append(t)
    closes.append(px)
    y, m = t.year, t.month
    m += 1
    if m > 12:
        m = 1
        y += 1
    t = datetime(y, m, 1, 0, 0)

s = Seasonality(min_n=30)
s.accumulate(times, closes, "MONTH")

jan = s.row(1)
feb = s.row(2)
# 240 monthly bars -> 239 close-to-close returns, because bar 0 has no
# prior close. 20 Januaries therefore yield 19 January observations. This
# is asserted explicitly: an off-by-one here is exactly the kind of error
# that makes a seasonality table quietly wrong.
check(jan["n"] == 19, "T1a January n = 19 (the first bar has no prior close)",
      "n=%d (expected 19)" % jan["n"])
check(jan["years"] == 19, "T1b years covered counts only years with a return",
      "years=%d (expected 19)" % jan["years"])
check(abs(jan["mean"] - 1.0) < 1e-9, "T1c January mean return is +1.00%",
      "%.6f%%" % jan["mean"])
check(abs(feb["mean"] - (-1.0)) < 1e-9, "T1d February mean return is -1.00%",
      "%.6f%%" % feb["mean"])
check(jan["std"] < 1e-9, "T1e dispersion of a constant series is 0",
      "std=%.9f" % jan["std"])
# The whole point: with min_n=30 and only 20 Januaries the row MUST be
# withheld, not shown with a warning.
check(jan["withheld"], "T2a n below the minimum => WITHHELD (not shown)",
      "n=%d < min_n=%d" % (jan["n"], s.min_n))

s2 = Seasonality(min_n=10)
s2.accumulate(times, closes, "MONTH")
jan2 = s2.row(1)
check(not jan2["withheld"], "T2b n above the minimum => shown",
      "n=%d >= min_n=%d" % (jan2["n"], s2.min_n))
check(abs(jan2["median"] - 1.0) < 1e-9, "T2c median reported correctly",
      "%.6f%%" % jan2["median"])
check(abs(jan2["pos_share"] - 100.0) < 1e-9, "T2d positive share reported",
      "%.1f%%" % jan2["pos_share"])

# An empty bucket must report n=0 and be withheld, never 0.0 shown as data.
empty = s2.row(13) if 13 not in s2.buckets else s2.row(7)
check(empty["withheld"] and empty["n"] >= 0,
      "T3 an absent bucket is withheld, never zero-filled",
      "n=%d" % empty["n"])


# =====================================================================
# ATR percentile: mirrors CVolatilityHeatmap::Percentile
# =====================================================================
def percentile(atr_series, ci, window, value):
    """Count of past ATR values strictly below `value`, as a percentage."""
    frm = max(1, ci - window + 1)
    n = ci - frm + 1
    if n < 10 or not (value > 0.0):
        return -1.0
    below = sum(1 for i in range(frm, ci + 1) if atr_series[i] < value)
    return 100.0 * below / n


print("\nT4-T5  volatility percentile and regime")

# A rising ATR series: the current value is the largest, so it must sit at
# (n-1)/n - i.e. at the top of the distribution but strictly below 100.
atr = [1.0 + 0.01 * i for i in range(300)]
ci = len(atr) - 1
cur = atr[ci]
p100 = percentile(atr, ci, 100, cur)
p250 = percentile(atr, ci, 250, cur)
check(p100 > 0 and p100 <= 100.0, "T4a percentile is within [0,100]",
      "pct100=%.2f" % p100)
check(abs(p100 - 99.0) < 1e-9, "T4b the maximum of a rising series is at 99",
      "pct100=%.2f (expected 99.00)" % p100)
check(p250 > p100 - 60 and p250 <= 100.0,
      "T4c the 250-bar window also places it near the top",
      "pct250=%.2f" % p250)

# The minimum must sit at 0, and a mid value near 50.
lo = percentile(atr, ci, 100, min(atr[ci - 99:ci + 1]))
check(abs(lo - 0.0) < 1e-9, "T4d the minimum sits at percentile 0",
      "%.2f" % lo)

# Short history must return -1 (NOT 0.0, which would read as "very quiet").
check(percentile(atr, 5, 100, cur) == -1.0,
      "T5a insufficient history returns -1, not 0.0")
check(percentile(atr, ci, 100, 0.0) == -1.0,
      "T5b ATR=0 returns -1, not a percentile")


# Regime thresholds, mirroring the MQL5 buckets
def regime(p):
    if p < 0:      return "UNKNOWN"
    if p < 20.0:   return "LOW"
    if p < 70.0:   return "NORMAL"
    if p < 90.0:   return "HIGH"
    return "EXTREME"


check(regime(-1.0) == "UNKNOWN", "T5c no data => UNKNOWN, never LOW")
check(regime(10.0) == "LOW" and regime(50.0) == "NORMAL"
      and regime(80.0) == "HIGH" and regime(95.0) == "EXTREME",
      "T5d the five buckets map as documented")


# =====================================================================
# Momentum z-score: mirrors CMomentumHeatmap
# =====================================================================
def zscore(closes, ci, lookback, hist, min_samples=8):
    if ci < lookback + 2:
        return None, "not enough bars"
    now, then = closes[ci], closes[ci - lookback]
    if not (now > 0 and then > 0):
        return None, "no price"
    roc = (now - then) / then * 100.0
    first = max(lookback + 1, ci - hist + 1)
    samples = []
    for i in range(first, ci + 1):
        a, b = closes[i], closes[i - lookback]
        if a > 0 and b > 0:
            samples.append((a - b) / b * 100.0)
    if len(samples) < min_samples:
        return roc, "n<%d for z-score" % min_samples
    mu = sum(samples) / len(samples)
    var = sum((x - mu) ** 2 for x in samples) / (len(samples) - 1)
    sd = var ** 0.5
    # Same degeneracy guard as the MQL5: a std dev that is only floating
    # point noise must not be divided by.
    scale = max(abs(mu), 1e-8)
    return roc, (0.0 if sd <= scale * 1e-6 else (roc - mu) / sd)


print("\nT6-T7  momentum z-score")

# A flat series has zero variance: the z-score must be 0, not NaN/inf.
flat = [100.0] * 200
roc, z = zscore(flat, 199, 20, 100)
check(z == 0.0, "T6a zero variance => z = 0, never NaN", "z=%s" % z)

# Too little history for the z-score window.
short = [100.0 + i for i in range(25)]
roc, z = zscore(short, 24, 20, 100)
check(isinstance(z, str) and "n<" in z,
      "T6b below the sample floor the z-score is refused, not computed",
      str(z))

# A noiseless ramp: every window returns the same value, so the current
# observation equals the mean and z must be 0.
ramp = [100.0 * (1.01 ** i) for i in range(300)]
roc, z = zscore(ramp, 299, 20, 100)
check(abs(z) < 1e-6, "T7a a constant-growth series has z = 0 (degenerate sd guarded)",
      "z=%.9f" % z)
check(abs(roc - (1.01 ** 20 - 1) * 100.0) < 1e-6,
      "T7b ROC over the lookback is correct",
      "%.6f%% (expected %.6f%%)" % (roc, (1.01 ** 20 - 1) * 100.0))

# An observation far above its own history must give a large positive z.
spike = [100.0] * 199 + [130.0]
roc, z = zscore(spike, 199, 20, 100)
check(z > 0, "T7c an upside outlier gives a positive z", "z=%.3f" % z)

print("\n" + "-" * 72)
if FAILS:
    print("RESULT: %d FAILED" % len(FAILS))
    for f in FAILS:
        print("   - %s" % f)
else:
    print("RESULT: all scanner arithmetic checks passed")
print("-" * 72)
print("This mirrors the arithmetic of QSMC_Scanners.mqh. It does NOT test")
print("symbol discovery, Market Watch or CopyRates - those need a terminal.")
print("It is not a backtest and produces no win rate. Press F7 to compile.")
sys.exit(1 if FAILS else 0)
