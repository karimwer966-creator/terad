#!/usr/bin/env python3
"""Independent arithmetic tests for the quantitative helpers in QSMC_Stats.mqh.

This tests formulas and boundary contracts without claiming that broker tick
volume is centralized traded volume or that a Wilson interval measures edge.
It is not a MetaTrader compiler; the Script self-test exercises the MQL code.
"""
from __future__ import annotations
import math

FAILS: list[str] = []


def check(ok: bool, name: str) -> None:
    print(("PASS" if ok else "FAIL") + "  " + name)
    if not ok:
        FAILS.append(name)


class EW:
    def __init__(self):
        self.reset()

    def reset(self):
        self.n, self.mean, self.var = 0, 0.0, 0.0

    def update(self, x: float, alpha: float) -> bool:
        if not (math.isfinite(x) and math.isfinite(alpha) and 0 < alpha <= 1):
            return False
        if not self.n:
            self.n, self.mean = 1, x
            return True
        delta = x - self.mean
        mean = self.mean + alpha * delta
        var = (1 - alpha) * (self.var + alpha * delta * delta)
        if not (math.isfinite(mean) and math.isfinite(var) and var >= 0):
            return False
        self.n, self.mean, self.var = self.n + 1, mean, var
        return True


class CUSUM:
    def __init__(self):
        self.reset()

    def reset(self):
        self.pos = self.neg = 0.0
        self.alarm = False
        self.side = self.n = 0

    def update(self, x, ref, sigma, k, h):
        if not all(map(math.isfinite, (x, ref, sigma, k, h))) or sigma <= 0 or k < 0 or h <= 0:
            return False
        z = (x-ref)/sigma
        if not math.isfinite(z):
            return False
        pos, neg = max(0., self.pos+z-k), max(0., self.neg-z-k)
        if not (math.isfinite(pos) and math.isfinite(neg)):
            return False
        self.pos, self.neg = pos, neg
        self.n += 1
        if self.pos >= h:
            self.alarm, self.side = True, 1
        elif self.neg >= h:
            self.alarm, self.side = True, -1
        return True


def wilson(successes: int, trials: int, z: float):
    if trials <= 0 or successes < 0 or successes > trials or not math.isfinite(z) or z <= 0:
        return None
    n, p, z2 = float(trials), successes/trials, z*z
    if not math.isfinite(z2):
        return None
    d = 1 + z2/n
    center = (p+z2/(2*n))/d
    half = z*math.sqrt((p*(1-p)+z2/(4*n))/n)/d
    if not (math.isfinite(center) and math.isfinite(half)):
        return None
    lo, hi = max(0., center-half), min(1., center+half)
    return (lo, hi) if math.isfinite(lo) and math.isfinite(hi) and lo <= hi else None


def profile(bars, bin_size, fraction, max_bins=2048):
    """Input tuples are (time, low, high, tick_volume); range is uniform."""
    if not bars or bin_size <= 0 or not 0 < fraction <= 1:
        return None
    usable = [b for b in bars if b[2] >= b[1] and b[3] > 0]
    if not usable:
        return None
    lo = min(b[1] for b in usable)
    hi = max(b[2] for b in usable)
    origin = math.floor(lo/bin_size)*bin_size
    count = math.floor((hi-origin)/bin_size)+1
    if count <= 0 or count > max_bins:
        return None
    bins = [0.0]*count
    accepted, total = [], 0
    for t, low, high, vol in bars:
        if high < low or vol <= 0:
            continue
        first = max(0, math.floor((low-origin)/bin_size))
        last = min(count-1, math.floor((high-origin)/bin_size))
        for idx in range(first, last+1):
            bins[idx] += vol/(last-first+1)
        total += vol
        accepted.append(t)
    if total <= 0:
        return None
    # Python max chooses the first index in a tie; MQL scans upward too.
    poc = max(range(count), key=lambda i: bins[i])
    left = right = poc
    accumulated = bins[poc]
    while accumulated/total < fraction and (left > 0 or right < count-1):
        lv = bins[left-1] if left else -1
        rv = bins[right+1] if right < count-1 else -1
        if lv >= rv:
            if left:
                left -= 1
                accumulated += bins[left]
            else:
                right += 1
                accumulated += bins[right]
        else:
            right += 1
            accumulated += bins[right]
    return dict(poc=origin+(poc+.5)*bin_size, val=origin+left*bin_size,
                vah=origin+(right+1)*bin_size, coverage=len(accepted)/len(bars),
                total=total, fraction=accumulated/total, bins=bins)


# EW: hand-computable case, offset stability, alpha endpoints, reset and invalid inputs.
new = EW()
check(new.update(10., .5) and new.update(12., .5) and new.mean == 11 and new.var == 1,
      "EW recurrence yields mean 11 and weighted population variance 1")
for x in (1e12+0.1, 1e12-0.1, 1e12+0.2, 1e12-0.2):
    new.update(x, .2)
check(new.var >= 0 and math.isfinite(new.var), "EW remains finite/nonnegative around a large offset")
check(not new.update(1., 0.) and not new.update(float('nan'), .5), "EW rejects invalid observations and alpha")
new.reset()
check((new.n, new.mean, new.var) == (0, 0., 0.), "EW reset restores pristine state")

# CUSUM alarms and resets are explicit; alarm is latched until reset.
c = CUSUM()
for _ in range(4):
    c.update(1., 0., 1., .5, 2.)
check(c.alarm and c.side == 1, "CUSUM detects positive mean shift")
c.reset()
for _ in range(4):
    c.update(-1., 0., 1., .5, 2.)
check(c.alarm and c.side == -1, "CUSUM detects negative mean shift")
c.reset()
check(not c.alarm and c.side == 0 and c.n == 0, "CUSUM reset clears accumulated evidence and latch")
check(not c.update(1., 0., 0., .5, 2.), "CUSUM rejects zero scale")

# Wilson endpoints and an interior reference value (95% Wilson: 5/10 ~= [0.2375,0.7625]).
w0, w1, wm = wilson(0, 10, 1.96), wilson(10, 10, 1.96), wilson(5, 10, 1.96)
check(w0 is not None and w0[0] == 0 and 0 < w0[1] < 1, "Wilson all-failure boundary is bounded")
check(w1 is not None and w1[1] == 1 and 0 < w1[0] < 1, "Wilson all-success boundary is bounded")
check(wm is not None and abs(wm[0]-0.2366) < .001 and abs(wm[1]-0.7634) < .001,
      "Wilson interior result matches reference")
check(wilson(1, 0, 1.96) is None and wilson(11, 10, 1.96) is None and
      wilson(5, 10, 1e308) is None,
      "Wilson rejects empty sample, impossible counts and overflow parameters")

bars = [(100, 100., 102., 20), (200, 101., 103., 50), (300, 103., 103., 30)]
p = profile(bars, 1., .70)
check(p is not None and p['poc'] == 103.5 and p['val'] == 102. and p['vah'] == 104.,
      "Volume profile has deterministic POC and value-area expansion")
check(p is not None and p['total'] == 100 and p['coverage'] == 1 and p['fraction'] >= .70,
      "Volume profile reports tick-volume sum, coverage and attained value fraction")
p_with_empty = profile(bars + [(400, -1e6, 1e6, 0)], 1., .70)
check(p_with_empty is not None and p_with_empty['coverage'] == .75 and len(p_with_empty['bins']) == 4,
      "Zero-volume bars do not distort profile range and reduce coverage")
check(profile(bars, 0., .70) is None and profile(bars, .0001, .70) is None,
      "Volume profile rejects invalid binning and oversized ranges")

if FAILS:
    print("%d quantitative test(s) failed" % len(FAILS))
    raise SystemExit(1)
print("All quantitative-statistics checks passed; Wilson is rate uncertainty, not profitability.")
