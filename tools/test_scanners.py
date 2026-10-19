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

Since v6.6.3 it mirrors the STORAGE as well as the arithmetic, because that is
where the mistakes were hiding. The seasonality buckets are a fixed array, and
the MQL5 side used to return 1-based month and week numbers into it: December
(index 12 of a 12-slot array) and week 53 were dropped by the range test in
Accumulate(), while bucket 0 was an empty phantom row. A mirror that only
re-derives the formula from a Python dict cannot see that - the dict grows. So
SLOTS below reproduces the array bounds, and the out-of-range rule is asserted
rather than assumed. The median reservoir is mirrored too, including the LCG,
so "deterministic across passes" is a tested property and not a comment.

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
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# The fixed arrays of CSeasonalityScanner: a bucket outside 0..slots-1 is
# DROPPED by the range test in Accumulate(). This number, not a Python dict,
# is what makes December either exist or not.
SLOTS = {"MONTH": 12, "WEEK": 53, "DOW": 7, "HOUR": 24}
SAMPLE = 512                      # QSC_SEAS_SAMPLE
MASK32 = 0xFFFFFFFF


def bucket_of(dt, kind):
    """Mirror of CSeasonalityScanner::BucketOf - 0-based, all four kinds."""
    if kind == "MONTH":
        return dt.month - 1                       # 0..11
    if kind == "DOW":
        return (dt.weekday() + 1) % 7             # MQL5: 0=Sunday
    if kind == "HOUR":
        return dt.hour                            # 0..23
    return ((dt.timetuple().tm_yday + 6) // 7) - 1  # 0..52, and W53 is reachable


def seas_name(bucket, kind):
    """Mirror of QSeasBucketName: buckets are 0-based, the label is 1-based."""
    if kind == "MONTH":
        return MONTH_NAMES[bucket] if 0 <= bucket < 12 else "?"
    if kind == "DOW":
        return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][bucket] \
            if 0 <= bucket < 7 else "?"
    if kind == "WEEK":
        return "W%d" % (bucket + 1)
    return "%dh" % bucket


class Seasonality:
    """Bucket bar-to-bar returns by month/week/dow/hour, into fixed slots."""

    def __init__(self, min_n=30, basis="SERVER", kind="MONTH"):
        self.min_n = min_n
        self.basis = basis
        self.kind = kind
        self.slots = SLOTS[kind]
        self.buckets = {}
        self.year_mask = {}
        self.dropped = 0            # observations outside 0..slots-1
        self.capped = 0             # observations the reservoir had to sample

    def accumulate(self, times, closes, kind=None):
        if kind is not None:
            self.kind = kind
            self.slots = SLOTS[kind]
        self.buckets = {b: [] for b in range(self.slots)}
        self.year_mask = {b: set() for b in range(self.slots)}
        self.reservoir = {b: [] for b in range(self.slots)}
        self.rng = 0x811C9DC5       # same seed as the MQL5 Reset()
        self.dropped = 0
        self.capped = 0
        for i in range(1, len(closes)):
            prev, cur = closes[i - 1], closes[i]
            if not (prev > 0.0 and cur > 0.0):
                continue
            ret = (cur - prev) / prev * 100.0
            t = times[i]
            b = bucket_of(t, self.kind)
            if b < 0 or b >= self.slots:
                self.dropped += 1
                continue
            self.buckets[b].append(ret)
            self.year_mask[b].add(t.year)
            r = self.reservoir[b]
            if len(r) < SAMPLE:
                r.append(ret)
            else:
                # Algorithm R with the MQL5 LCG, so both sides see the same
                # sample: j = (rng >> 1) % n_total, replace when j < SAMPLE.
                self.capped += 1
                self.rng = (1664525 * self.rng + 1013904223) & MASK32
                j = (self.rng >> 1) % len(self.buckets[b])
                if j < SAMPLE:
                    r[j] = ret

    def row(self, b):
        out = dict(bucket=b, n=0, years=0, mean=0.0, median=0.0,
                   std=0.0, pos_share=0.0, withheld=True, sampled=False)
        if b < 0 or b >= self.slots:
            return out
        vals = self.buckets[b]
        n = len(vals)
        out["n"] = n
        out["years"] = len(self.year_mask[b])
        if n <= 0:
            return out
        if n < self.min_n:
            out["mean"] = sum(vals) / n
            return out
        mu = sum(vals) / n
        res = self.reservoir[b]
        #--- exact two-pass when the reservoir IS the bucket, streaming form
        #--- (clamped) otherwise - the same branch the MQL5 takes.
        if n == len(res):
            var = sum((v - mu) ** 2 for v in res) / n
        else:
            var = sum(v * v for v in vals) / n - mu * mu
            var = 0.0 if var <= 0.0 else var
        out.update(mean=mu, std=var ** 0.5,
                   pos_share=100.0 * sum(1 for v in vals if v > 0) / n,
                   withheld=False, sampled=(n != len(res)))
        s = sorted(res)
        m = len(s)
        out["median"] = s[m // 2] if m % 2 else (s[m // 2 - 1] + s[m // 2]) / 2.0
        return out


def make_series(n, start, step_hours, closes):
    times = [start + timedelta(hours=step_hours * i) for i in range(n)]
    return times, closes


print("=" * 72)
print(" QSMC v6.6.4 PART C PHASE 7 - SCANNER ARITHMETIC CHECK")
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

jan = s.row(0)                      # buckets are 0-based: slot 0 IS January
feb = s.row(1)
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
jan2 = s2.row(0)
check(not jan2["withheld"], "T2b n above the minimum => shown",
      "n=%d >= min_n=%d" % (jan2["n"], s2.min_n))
check(abs(jan2["median"] - 1.0) < 1e-9, "T2c median reported correctly",
      "%.6f%%" % jan2["median"])
check(abs(jan2["pos_share"] - 100.0) < 1e-9, "T2d positive share reported",
      "%.1f%%" % jan2["pos_share"])

# An absent bucket must report n=0 and be withheld, never 0.0 shown as data.
# The series is monthly bars at 00:00, so under HOUR bucketing bucket 0 holds
# everything and buckets 1..23 are absent by construction.
s3 = Seasonality(min_n=10, kind="HOUR")
s3.accumulate(times, closes)
absent = s3.row(5)
check(absent["n"] == 0 and absent["withheld"],
      "T3 an absent bucket is withheld, never zero-filled",
      "n=%d" % absent["n"])
check(s3.row(0)["n"] > 0, "T3b the bucket that exists is the one that reports",
      "n=%d at hour 0" % s3.row(0)["n"])
check(s3.dropped == 0, "T3c nothing fell outside the array under HOUR bucketing",
      "dropped=%d" % s3.dropped)


# =====================================================================
# ATR percentile: mirrors CVolatilityHeatmap::Percentile
# =====================================================================
def percentile(atr_series, ci, window, value):
    """Count of past ATR values strictly below `value`, as a percentage.

    Divided by the ATRs ACTUALLY COMPARED, not by the window: a warm-up stretch
    where ATR is not defined yet is not evidence of quietness, and counting it in
    the denominator diluted the percentile toward 0 (a true 80th reported as
    64th). Below 10 real samples there is no percentile to report.
    """
    frm = max(1, ci - window + 1)
    n = ci - frm + 1
    if n < 10 or not (value > 0.0):
        return -1.0
    below = 0
    valid = 0
    for i in range(frm, ci + 1):
        a = atr_series[i]
        if not (a > 0.0):
            continue
        valid += 1
        if a < value:
            below += 1
    if valid < 10:
        return -1.0
    return 100.0 * below / valid


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

print("\nT8  bucket coverage: the array bounds the MQL5 side must respect")

# The bug this test exists for: BucketOf() used to return 1-based month and week
# numbers into a 12/53-slot array, so December (index 12) and week 53 were
# discarded by the range test while slot 0 stayed an empty phantom.
dec = s2.row(11)
check(dec["n"] > 0, "T8a December is counted (was dropped at index 12 of 12)",
      "n=%d mean=%+.4f%%" % (dec["n"], dec["mean"]))
check(abs(dec["mean"] - (-1.0)) < 1e-9,
      "T8b December carries the -1% branch, not an empty row",
      "%+.6f%%" % dec["mean"])
check(s2.row(0)["n"] > 0, "T8c slot 0 is January, not a phantom",
      "n=%d" % s2.row(0)["n"])
check(seas_name(0, "MONTH") == "Jan" and seas_name(11, "MONTH") == "Dec",
      "T8d labels stay 1-based where the buckets are 0-based",
      "%s / %s" % (seas_name(0, "MONTH"), seas_name(11, "MONTH")))
# Day-of-year 365 or 366 -> (doy+6)//7 == 53 -> slot 52, the last legal one.
late = datetime(2019, 12, 31, 0, 0)         # tm_yday = 365 (a 53-week year)
check(bucket_of(late, "WEEK") == 52, "T8e week 53 maps to slot 52 and is in range",
      "slot=%d label=%s" % (bucket_of(late, "WEEK"), seas_name(52, "WEEK")))
check(bucket_of(datetime(2021, 1, 1), "WEEK") == 0,
      "T8f the first days of a year land in week 1, not slot -1")
s4 = Seasonality(min_n=10, kind="WEEK")
s4.accumulate(times, closes)
check(s4.dropped == 0, "T8g no observation fell outside the bucket array",
      "dropped=%d" % s4.dropped)


print("\nT9  percentile denominator: valid ATRs only")

# The same 100-bar window, but with a 20-bar warm-up stretch where ATR is not
# defined (<= 0). Dividing by the window diluted the result toward 0; dividing by
# the values actually compared does not.
warm = [1.0 + 0.01 * i for i in range(300)]
for i in range(ci - 99, ci - 79):
    warm[i] = 0.0
clean = percentile(warm, ci, 100, warm[ci])
naive_below = sum(1 for i in range(ci - 99, ci + 1) if warm[i] > 0.0 and warm[i] < warm[ci])
check(abs(clean - 100.0 * naive_below / 80.0) < 1e-9,
      "T9a a warm-up hole is excluded from the denominator, not counted as quiet",
      "pct=%.2f over %d valid" % (clean, 80))
check(abs(percentile(atr, ci, 100, cur) - 99.0) < 1e-9,
      "T9b with no holes the answer is unchanged (99.00)")
mostly_broken = [0.0] * 300
mostly_broken[ci] = 1.0
check(percentile(mostly_broken, ci, 100, 1.0) == -1.0,
      "T9c fewer than 10 valid samples is refused, never reported as 0 or 100")


print("\nT10  median reservoir: an unbiased sample, and the same one every time")

# 512 observations of -2%, then 1000 of +5%, all in one bucket. The exact median
# of that bucket is +5 (the later group is the majority), while the median of
# "the first 512" - what the old code stored - is -2. A uniform 512-sample
# reservoir must land near +5, so this distinguishes the two designs instead of
# merely describing them.
big_t, big_c = [], []
px = 100.0
start2 = datetime(2000, 1, 1, 0, 0)
RET = [-0.02] * 512 + [0.05] * 1000
for i, r in enumerate(RET):
    px *= 1.0 + r
    big_t.append(start2 + timedelta(days=i))       # every bar at 00:00 => bucket 0
    big_c.append(px)
s5 = Seasonality(min_n=10, kind="HOUR")
s5.accumulate(big_t, big_c)
r0 = s5.row(0)
allv = sorted(s5.buckets[0])
n_exact = len(allv)
exact_med = allv[n_exact // 2] if n_exact % 2 else (allv[n_exact // 2 - 1] + allv[n_exact // 2]) / 2.0
first_med = sorted(100.0 * r for r in RET[:512])[256]   # same units as the rest
check(r0["n"] == n_exact and r0["sampled"],
      "T10a n is the FULL bucket even though the median is sampled",
      "n=%d, reservoir=%d" % (r0["n"], SAMPLE))
check(abs(r0["median"] - exact_med) < abs(first_med - exact_med),
      "T10b the sampled median tracks the whole bucket, not the oldest 512 bars",
      "reservoir=%.3f exact=%.3f first-512=%.3f" % (r0["median"], exact_med, first_med))
first_pass = list(s5.reservoir[0])
s5b = Seasonality(min_n=10, kind="HOUR")
s5b.accumulate(big_t, big_c)
check(list(s5b.reservoir[0]) == first_pass,
      "T10c identical bars => identical sample => identical median (no clock, no RNG seed)")
check(abs(s5b.row(0)["std"] - r0["std"]) < 1e-12,
      "T10d dispersion is reproducible too", "std=%.9f" % r0["std"])
# A constant bucket that fits entirely in the reservoir: this is the branch
# where the MQL5 takes the exact two-pass route, so the dispersion must be
# exactly 0.0 - the streaming form E[X^2]-E[X]^2 is the one that can land on a
# tiny negative and then has to be clamped.
flat_t = [start2 + timedelta(days=i) for i in range(401)]
flat_c = [100.0] * 401
s5c = Seasonality(min_n=10, kind="HOUR")
s5c.accumulate(flat_t, flat_c)
fc = s5c.row(0)
check(fc["n"] == 400 and not fc["sampled"] and fc["std"] == 0.0 and not fc["withheld"],
      "T10e a constant bucket inside the reservoir => std exactly 0.0",
      "n=%d std=%.17g" % (fc["n"], fc["std"]))

print("\n" + "-" * 72)
if FAILS:
    print("RESULT: %d FAILED" % len(FAILS))
    for f in FAILS:
        print("   - %s" % f)
else:
    print("RESULT: all scanner arithmetic checks passed")
print("-" * 72)
print("This mirrors QSMC_Scanners.mqh - its arithmetic AND its fixed bucket")
print("arrays, which is how the December/week-53 drop became visible. It also")
print("runs against the real host now: MQL5/Indicators/QSMC_ScannerProbe.mq5.")
print("It does NOT test")
print("symbol discovery, Market Watch or CopyRates - those need a terminal.")
print("It is not a backtest and produces no win rate. Press F7 to compile.")
sys.exit(1 if FAILS else 0)
