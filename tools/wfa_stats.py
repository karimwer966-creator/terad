#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WFA-STATS - the offline half of the over-optimisation defence.

WHY THIS EXISTS
---------------
An optimiser returns the single best row of a search. That row is the *most*
fitted object in the study: of N trials, it is by construction the one that
benefited most from noise. Every decision that follows - do I trade it, at what
size, with what kill criteria - is then made from the one number that carries
the largest selection bias.

This module takes the artefacts an MT5 run actually produces (a grid of
optimisation rows, a stitched out-of-sample equity, a list of closed trades)
and answers the questions that the optimiser cannot:

  * Is the chosen parameter set on a plateau or on a spike?      `plateau`
  * Does the out-of-sample behaviour survive the roll-forward?   `wfa`
  * Is the drawdown a property of the edge or of trade order?    `mc`
  * Did I try enough variants that the best Sharpe is luck?      `dsr`
  * Do random entries with the same exits beat my entries?       `benchmark`
  * Does the edge survive 1.5-2x costs?                          `stress`
  * All of the above, with PASS/WARN/FAIL, in one document.      `report`

WHAT THIS IS NOT
----------------
  * Not a backtester. It never prices a bar and never invents a trade. If the
    input trade list is wrong, the output is wrong with confidence intervals.
  * Not a compiler and not a MetaTrader client. It reads files the terminal
    wrote (see tools/wfa_harness.py for producing them).
  * Not a proof of profitability. A study that passes every gate here has
    survived a specific battery of attacks. It has not seen tomorrow's spread.
  * Not investment advice; forex trading carries substantial risk of loss.

INPUT FORMATS (deliberately dumb, so they are inspectable)
----------------------------------------------------------
Trades CSV - one closed trade per row, NET of commission and swap, in account
currency. A header is optional. Recognised profit columns: profit, net profit,
result, balance. Anything else is ignored except a leading time column.

    time,profit
    2024-01-02 10:15:00,12.40
    2024-01-02 14:05:00,-8.10

Runs CSV - one optimisation row per row, header REQUIRED. Parameter columns are
whatever is numeric and not a recognised metric; metric columns are the aliases
in METRIC_ALIASES below ("Profit", "Profit Factor", "Total Trades", ...).

Exit codes: 0 = every gate PASS/WARN/SKIP, 1 = at least one FAIL, 2 = bad input.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import random
import re
import sys

# ---------------------------------------------------------------------------
# Small numeric helpers. No numpy: this repo's gates run on a bare python3.
# ---------------------------------------------------------------------------

EULER_GAMMA = 0.5772156649015329


def norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation).

    Relative error < 1.15e-9 over (0, 1); it backs the deflated-Sharpe quantile
    where the difference between a good and a mediocre approximation is a few
    thousandths of probability, i.e. exactly the region that decides a pass.
    """
    if not (0.0 < p < 1.0):
        raise ValueError("norm_ppf domain is (0, 1), got %r" % (p,))
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    p_low, p_high = 0.02425, 1.0 - 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > p_high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


THOUSAND_SEPS = re.compile(r"[\s\u00a0\u202f']")


def to_float(value):
    """Parse an MT5-ish number. Returns None when the cell is not numeric.

    MT5 writes thousands separators in its HTML/XML reports depending on locale
    ("1 234.56", "1,234.56", "1.234,56"). A comma is only a decimal separator
    when it is the *last* separator and is followed by 1-2 digits, which is the
    only case where treating it as thousands would corrupt the magnitude.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = THOUSAND_SEPS.sub("", str(value).strip())
    if not s or s in ("-", "--", "n/a", "N/A", "nan", "NaN"):
        return None
    s = s.rstrip("%")
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        # 1.234,56 -> 1234.56 ; 1,234.56 -> 1234.56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        tail = s.rsplit(",", 1)[1]
        s = s.replace(",", ".") if len(tail) <= 2 else s.replace(",", "")
    try:
        out = float(s)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def mean(xs) -> float:
    return sum(xs) / float(len(xs)) if xs else float("nan")


def stdev(xs) -> float:
    """Sample standard deviation (n-1). 0.0 for fewer than 2 points."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def percentile(sorted_xs, p: float) -> float:
    """Linear-interpolated percentile of an already-sorted list; p in [0, 1]."""
    if not sorted_xs:
        return float("nan")
    if p <= 0:
        return sorted_xs[0]
    if p >= 1:
        return sorted_xs[-1]
    pos = p * (len(sorted_xs) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_xs) - 1)
    frac = pos - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def summarise(values) -> dict:
    """mean/median/percentiles of a sample; empty input is an explicit error."""
    if not values:
        return {"n": 0}
    xs = sorted(values)
    return {
        "n": len(xs),
        "mean": mean(xs),
        "median": percentile(xs, 0.5),
        "p05": percentile(xs, 0.05),
        "p25": percentile(xs, 0.25),
        "p75": percentile(xs, 0.75),
        "p95": percentile(xs, 0.95),
        "min": xs[0],
        "max": xs[-1],
    }


# ---------------------------------------------------------------------------
# Trade lists and the statistics built on them
# ---------------------------------------------------------------------------

PROFIT_COLUMNS = ("profit", "net profit", "net profit ", "result", "balance",
                  "pnl", "p/l", "profit/loss")

METRIC_ALIASES = {
    "net_profit": ("profit", "net profit", "total net profit", "result",
                   "balance", "total profit"),
    "gross_profit": ("gross profit",),
    "gross_loss": ("gross loss",),
    "trades": ("trades", "total trades", "# trades", "orders", "total deals"),
    "profit_factor": ("profit factor",),
    "max_dd_pct": ("maximal drawdown %", "equity dd %", "max drawdown %",
                   "drawdown %", "maximal equity drawdown %"),
    "max_dd_abs": ("maximal drawdown", "equity dd", "max drawdown",
                   "maximal equity drawdown"),
    "sharpe": ("sharpe ratio", "sharpe"),
    "expectancy": ("expected payoff", "expectancy"),
    "recovery": ("recovery factor",),
    "win_rate": ("profit trades %", "win rate", "% profitable",
                 "profit trades (% of total)"),
    "trades_per_day": ("trades per day",),
}


def clean_key(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).replace("\ufeff", "").strip().lower())


def canonical_metric(name: str):
    """Map an MT5 column label to a canonical metric name, or None."""
    key = clean_key(name)
    for canon, aliases in METRIC_ALIASES.items():
        if key in aliases:
            return canon
    if "profit factor" in key:
        return "profit_factor"
    if key.startswith("sharpe"):
        return "sharpe"
    if "drawdown" in key and ("%" in key or "percent" in key):
        return "max_dd_pct"
    if "drawdown" in key:
        return "max_dd_abs"
    if key.startswith("recovery"):
        return "recovery"
    if "expected payoff" in key or "expectancy" in key:
        return "expectancy"
    if "trades" in key and ("total" in key or key.endswith("trades")):
        return "trades"
    if key in ("profit", "net profit") or key.endswith(" net profit"):
        return "net_profit"
    return None


def load_trades(path: str) -> list:
    """Read a closed-trade CSV into a list of net P/L floats, in file order."""
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("%s: no rows" % path)

    header = rows[0]
    header_keys = [clean_key(c) for c in header]
    col = None
    for i, key in enumerate(header_keys):
        if key in PROFIT_COLUMNS:
            col = i
            break
    if col is None and canonical_metric(header[0] or "") == "net_profit":
        col = 0
    if col is None:
        # No usable header: take the last numeric cell of every row. The header
        # row itself then contributes nothing (no cell parses), which is exactly
        # the behaviour we want for a headerless export.
        data = rows
    else:
        data = rows[1:]

    profits = []
    for lineno, row in enumerate(data, start=2 if col is not None else 1):
        if not row:
            continue
        if col is not None and col < len(row):
            val = to_float(row[col])
        else:
            val = None
            for cell in reversed(row):
                val = to_float(cell)
                if val is not None:
                    break
        if val is None:
            continue
        profits.append(val)
    if not profits:
        raise ValueError("%s: no numeric profit column found (expected one of %s)"
                         % (path, ", ".join(PROFIT_COLUMNS)))
    return profits


def trade_stats(profits, start_equity: float = 10000.0) -> dict:
    """Headline metrics of a closed-trade list.

    `max_dd_pct` is peak-to-trough on the cumulative P/L path, expressed as a
    fraction of the peak equity reached - the same convention the MT5 report
    uses for "Equity DD %", so a stitched OOS number can be compared with the
    terminal's own.

    `sharpe` is per-trade (mean/stdev of trade P/L), NOT annualised. Annualising
    a per-trade Sharpe requires an assumption about trades per year, which is
    exactly the sort of assumption that makes a bad system look smooth.
    """
    n = len(profits)
    out = {"trades": n, "net_profit": 0.0, "profit_factor": float("nan"),
           "expectancy": float("nan"), "sharpe": float("nan"),
           "max_dd_abs": 0.0, "max_dd_pct": 0.0, "win_rate": float("nan"),
           "longest_dd_trades": 0}
    if n == 0:
        return out

    eq = start_equity
    peak = eq
    peak_idx = 0
    max_dd = 0.0
    max_dd_pct = 0.0
    longest_dd = 0
    wins = 0
    gross_win = gross_loss = 0.0
    for i, p in enumerate(profits):
        eq += p
        if p > 0:
            wins += 1
            gross_win += p
        elif p < 0:
            gross_loss += -p
        if eq >= peak:
            peak = eq
            peak_idx = i
            longest_dd = max(longest_dd, i - peak_idx)
        else:
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
            if peak > 0 and dd / peak > max_dd_pct:
                max_dd_pct = dd / peak
        longest_dd = max(longest_dd, i - peak_idx)

    out.update({
        "trades": n,
        "net_profit": sum(profits),
        "expectancy": mean(profits),
        "sharpe": (mean(profits) / stdev(profits)) if stdev(profits) > 0 else float("nan"),
        "max_dd_abs": max_dd,
        "max_dd_pct": max_dd_pct,
        "win_rate": wins / float(n),
        "gross_profit": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "longest_dd_trades": longest_dd,
    })
    return out


def equity_path(profits, start_equity: float = 10000.0,
                compounding: bool = False) -> dict:
    """Final equity and peak-to-trough drawdown of one ordered trade path.

    `compounding=True` scales every trade's P/L by current_equity/start_equity,
    which is the first-order behaviour of fixed-fractional sizing. It is an
    approximation: it ignores the stop distance being recomputed, lot-step
    rounding and margin. Say so when you quote the number.
    """
    eq = start_equity
    peak = eq
    max_dd = 0.0
    max_dd_pct = 0.0
    ruined = False
    for p in profits:
        scale = (eq / start_equity) if compounding else 1.0
        eq += p * scale
        if eq <= 0:
            ruined = True
            eq = 0.0
        if eq > peak:
            peak = eq
        else:
            dd = peak - eq
            max_dd = max(max_dd, dd)
            if peak > 0:
                max_dd_pct = max(max_dd_pct, dd / peak)
    return {"final_equity": eq, "net_profit": eq - start_equity,
            "max_dd_abs": max_dd, "max_dd_pct": max_dd_pct, "ruined": ruined}


# ---------------------------------------------------------------------------
# Monte Carlo: order, resample, skip
# ---------------------------------------------------------------------------

def mc_shuffle(profits, iterations: int = 5000, seed: int = 7,
               start_equity: float = 10000.0, compounding: bool = False) -> dict:
    """Permutation test on trade ORDER. The set of trades is unchanged.

    If the equity curve only looks acceptable in one particular sequence, the
    edge depends on luck of ordering, not on the trades. In that case the 95th
    percentile drawdown here is materially worse than the backtest's.
    """
    if not profits:
        raise ValueError("mc_shuffle needs at least one trade")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    rng = random.Random(seed)
    pool = list(profits)
    dds, fins, durs = [], [], []
    for _ in range(iterations):
        order = pool[:]
        rng.shuffle(order)
        r = equity_path(order, start_equity, compounding)
        dds.append(r["max_dd_pct"])
        fins.append(r["net_profit"])
    return {"kind": "order_shuffle", "iterations": iterations, "seed": seed,
            "compounding": compounding, "start_equity": start_equity,
            "dd_pct": summarise(dds), "net_profit": summarise(fins),
            "trades": len(pool)}


def mc_bootstrap(profits, iterations: int = 5000, seed: int = 7,
                 start_equity: float = 10000.0, compounding: bool = False) -> dict:
    """Resample WITH replacement: a different historical sample of the same size.

    This is the honest question ("how much does this statistic move when the
    sample is drawn again?"), and it widens the tails because it also resamples
    the loss-clustering that shuffling destroys.
    """
    if not profits:
        raise ValueError("mc_bootstrap needs at least one trade")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    rng = random.Random(seed)
    pool = list(profits)
    n = len(pool)
    dds, fins = [], []
    for _ in range(iterations):
        order = [pool[rng.randrange(n)] for _ in range(n)]
        r = equity_path(order, start_equity, compounding)
        dds.append(r["max_dd_pct"])
        fins.append(r["net_profit"])
    return {"kind": "bootstrap_resample", "iterations": iterations, "seed": seed,
            "compounding": compounding, "start_equity": start_equity,
            "dd_pct": summarise(dds), "net_profit": summarise(fins),
            "trades": n}


def mc_skip(profits, iterations: int = 5000, seed: int = 7, drop_frac: float = 0.05,
            start_equity: float = 10000.0, compounding: bool = False,
            randomised: bool = True) -> dict:
    """Drop `drop_frac` of trades and re-measure.

    `randomised=True` drops a random subset every iteration - the distribution
    version of "does this system need its ten best trades?".

    `randomised=False` drops the BEST trades deterministically: the single
    worst-case answer to that same question. If a system only survives because
    of the top 5% of its winners, this is the number that says so.
    """
    if not profits:
        raise ValueError("mc_skip needs at least one trade")
    if not (0.0 <= drop_frac < 1.0):
        raise ValueError("drop_frac must be in [0, 1)")
    rng = random.Random(seed)
    pool = list(profits)
    n = len(pool)
    k = int(round(n * drop_frac))
    fins, dds = [], []
    for _ in range(iterations):
        if randomised:
            idx = sorted(rng.sample(range(n), k)) if k else []
            keep = [p for i, p in enumerate(pool) if i not in set(idx)]
        else:
            keep = sorted(pool)[:max(0, n - k)] if k else list(pool)
        r = equity_path(keep, start_equity, compounding)
        fins.append(r["net_profit"])
        dds.append(r["max_dd_pct"])
    spread = summarise(fins)
    return {"kind": ("skip_trades_random" if randomised else "skip_worst_trades"),
            "iterations": iterations, "seed": seed, "drop_frac": drop_frac,
            "compounding": compounding, "start_equity": start_equity,
            "net_profit": spread, "dd_pct": summarise(dds),
            "prob_negative": sum(1 for x in fins if x <= 0) / float(len(fins)),
            "trades": n}


# ---------------------------------------------------------------------------
# Multiple testing: PSR / Deflated Sharpe Ratio
# ---------------------------------------------------------------------------

def moments(xs) -> dict:
    """n, mean, sample sd, skew and raw (non-excess) kurtosis."""
    n = len(xs)
    if n < 2:
        return {"n": n, "mean": mean(xs) if xs else float("nan"),
                "sd": 0.0, "skew": 0.0, "kurtosis": 3.0}
    m = mean(xs)
    sd = stdev(xs)
    if sd == 0:
        return {"n": n, "mean": m, "sd": 0.0, "skew": 0.0, "kurtosis": 3.0,
                "sharpe": float("nan")}
    skew = sum(((x - m) / sd) ** 3 for x in xs) / float(n)
    kurt = sum(((x - m) / sd) ** 4 for x in xs) / float(n)
    return {"n": n, "mean": m, "sd": sd, "skew": skew, "kurtosis": kurt,
            "sharpe": m / sd}


def psr(sr: float, n: int, skew: float, kurtosis: float,
        sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio (Bailey & Lopez de Prado).

    P(true SR > benchmark) given the observed per-observation SR, its sample
    length, and the higher moments that fatten the sampling distribution.

    The formula is only defined while the denominator stays positive; extreme
    skew with a large SR can push it negative, and returning a probability there
    would be inventing one. Callers get NaN and must treat it as "unknown".
    """
    if n < 2 or not math.isfinite(sr):
        return float("nan")
    denom = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if denom <= 0:
        return float("nan")
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom)
    return norm_cdf(z)


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """E[max SR] of N independent zero-skill trials, with SR variance V.

    Bailey & Lopez de Prado's approximation using the Gumbel limit:
    sqrt(V) * ((1-g)*Z^-1(1 - 1/N) + g*Z^-1(1 - 1/(N*e))), g = Euler-Mascheroni.
    This is the hurdle a reported Sharpe has to clear before it means anything.
    """
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    if n_trials == 1:
        return 0.0
    if not (sr_variance >= 0.0):
        raise ValueError("sr_variance must be >= 0")
    v = math.sqrt(sr_variance)
    z1 = norm_ppf(1.0 - 1.0 / n_trials)
    z2 = norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    return v * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)


def deflated_sharpe(profits, n_trials: int, trial_sharpes=None,
                    trial_sharpe_sd=None) -> dict:
    """DSR = PSR evaluated against the expected best-of-N zero-skill Sharpe.

    n_trials is every variant that was tried while developing the system: every
    parameter set in every grid, every filter you added and removed, every
    "let me just check one more thing". Undercounting it is the single easiest
    way to fake a pass.

    The hurdle needs the DISPERSION of the trial Sharpes, not just their count:
    with V=0 the expected best-of-N is 0 and the "correction" corrects nothing.
    `var_source` records where V came from, and `build_gates` refuses to pass a
    multi-trial study whose V was never supplied - otherwise `--trials 50000`
    with no dispersion would look like the strictest possible test while
    actually applying no penalty at all.
    """
    m = moments(profits)
    if m["n"] < 2 or not math.isfinite(m.get("sharpe", float("nan"))):
        return {"n_trials": n_trials, "psr": float("nan"), "dsr": float("nan"),
                "sr0": float("nan"), "sharpe": m.get("sharpe", float("nan")),
                "n": m["n"], "var_sr": float("nan"), "var_source": "none"}
    srs = [s for s in (trial_sharpes or []) if s is not None and math.isfinite(s)]
    if trial_sharpe_sd is not None and float(trial_sharpe_sd) > 0:
        var_sr, source = float(trial_sharpe_sd) ** 2, "assumed_sd"
    elif len(srs) >= 2:
        var_sr, source = stdev(srs) ** 2, "trial_sharpes"
    else:
        var_sr, source = 0.0, "none"
    sr0 = expected_max_sharpe(n_trials, var_sr)
    return {"n_trials": n_trials,
            "sharpe": m["sharpe"], "skew": m["skew"], "kurtosis": m["kurtosis"],
            "n": m["n"], "var_sr": var_sr, "var_source": source, "sr0": sr0,
            "psr": psr(m["sharpe"], m["n"], m["skew"], m["kurtosis"], 0.0),
            "dsr": psr(m["sharpe"], m["n"], m["skew"], m["kurtosis"], sr0)}


# ---------------------------------------------------------------------------
# Random-entry benchmark
# ---------------------------------------------------------------------------

METRIC_FUNCS = {
    "net_profit": lambda p: sum(p),
    "expectancy": lambda p: mean(p),
    "sharpe": lambda p: (mean(p) / stdev(p)) if stdev(p) > 0 else float("nan"),
    "profit_factor": lambda p: (
        (sum(x for x in p if x > 0) / -sum(x for x in p if x < 0))
        if any(x < 0 for x in p) else float("inf")),
    "total": lambda p: sum(p),
}


def benchmark(real_profits, bench_profit_lists, metric: str = "net_profit") -> dict:
    """One-sided p-value: how often does a random-entry run beat the real one?

    p = (1 + #{bench >= real}) / (1 + N) - the "+1" keeps p honest when no
    benchmark run beats the real one (you cannot claim p=0 from 200 samples).

    The benchmark must be generated with the SAME exits, position sizing and
    trade count, and only the entries randomised. If it uses different exits,
    you are comparing two systems, not testing your entries.
    """
    if metric not in METRIC_FUNCS:
        raise ValueError("metric must be one of %s" % ", ".join(sorted(METRIC_FUNCS)))
    fn = METRIC_FUNCS[metric]
    real = fn(list(real_profits))
    benches = []
    for i, b in enumerate(bench_profit_lists):
        if not b:
            continue
        v = fn(list(b))
        if math.isfinite(v):
            benches.append(v)
    if not benches:
        raise ValueError("benchmark needs at least one non-empty random-entry run")
    better = sum(1 for v in benches if v >= real)
    return {"metric": metric, "real": real, "n_benchmarks": len(benches),
            "beat_or_equal": better, "p_value": (1.0 + better) / (1.0 + len(benches)),
            "bench": summarise(benches)}


# ---------------------------------------------------------------------------
# Optimisation surface: plateau, not peak
# ---------------------------------------------------------------------------

def load_runs(path: str):
    """Read an optimisation grid CSV. Returns (param_names, rows).

    Every row is a dict of {param: float, metric: float, ...}; a column is a
    parameter when it parses numerically and is not a known metric label.
    """
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("%s: needs a header row" % path)
        rows = []
        params, metrics = [], []
        for field in reader.fieldnames:
            if canonical_metric(field):
                metrics.append(field)
            else:
                params.append(field)
        for raw in reader:
            row = {}
            numeric_params = 0
            for field in params:
                val = to_float(raw.get(field))
                if val is not None:
                    numeric_params += 1
                row[field] = val
            if numeric_params == 0:
                continue
            for field in metrics:
                row[canonical_metric(field)] = to_float(raw.get(field))
            if "net_profit" not in row:
                row["net_profit"] = to_float(raw.get("Profit"))
            rows.append(row)
    if not rows:
        raise ValueError("%s: no numeric rows" % path)
    param_names = [p for p in params
                   if all(r.get(p) is not None for r in rows)]
    if not param_names:
        raise ValueError("%s: no fully numeric parameter columns" % path)
    return param_names, rows


def _normalise(runs, param_names):
    """Scale each parameter axis to [0, 1] so distances mix axes sanely."""
    axes = {}
    for name in param_names:
        vals = [r[name] for r in runs]
        lo, hi = min(vals), max(vals)
        axes[name] = (lo, hi, (hi - lo) or 1.0)
    vecs = []
    for r in runs:
        vecs.append(tuple((r[n] - axes[n][0]) / axes[n][2] for n in param_names))
    return vecs


BAND = 0.02  # "equally good" = within 2% of the best neighbourhood median


def plateau(runs, param_names, score: str = "net_profit", k: int = 4,
            min_trades: float = 0.0) -> dict:
    """Rank candidates by the mean score of their k nearest neighbours.

    Why neighbours and not the row itself: an isolated peak is a local artefact
    of the search, while a broad plateau means small errors in the parameter
    estimate cost little. Selecting the centre of a plateau is the only defence
    that survives the fact that tomorrow's optimum is not today's.

    Returns the recommended row, its neighbour statistics, the peak row for
    comparison, and a peakiness score. Neighbour distance is Euclidean in the
    per-axis normalised space, so `k` neighbours can be diagonal, not only
    axis-adjacent - which is what a real 3-6 parameter grid looks like.
    """
    if not runs:
        raise ValueError("plateau needs at least one run")
    if score not in runs[0] and not all(score in r for r in runs):
        raise ValueError("score column %r is missing from the runs" % score)
    if k < 1:
        raise ValueError("k must be >= 1")

    usable = [r for r in runs
              if r.get(score) is not None
              and math.isfinite(r[score])
              and (min_trades <= 0 or (r.get("trades") or 0) >= min_trades)]
    if len(usable) < 2:
        raise ValueError("plateau needs >= 2 usable runs after filters "
                         "(min_trades=%s removed %d of %d)"
                         % (min_trades, len(runs) - len(usable), len(runs)))

    vecs = _normalise(usable, param_names)
    kk = min(k, len(usable) - 1)
    scored = []
    for i, run in enumerate(usable):
        dists = []
        for j in range(len(usable)):
            if i == j:
                continue
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(vecs[i], vecs[j])))
            dists.append((d, j))
        dists.sort(key=lambda t: (t[0], t[1]))
        neigh = sorted(usable[j][score] for _, j in dists[:kk])
        # MEDIAN, not mean. A single outlier neighbour (one lucky cell three
        # steps away) can lift a neighbour MEAN above the real plateau and drag
        # the recommendation onto the artefact's doorstep. The median ignores
        # that one neighbour by construction.
        scored.append({
            "run": run,
            "params": {n: run[n] for n in param_names},
            "score": run[score],
            "neighbour_median": percentile(neigh, 0.5),
            "neighbour_mean": mean(neigh),
            "neighbour_min": min(neigh),
            "neighbour_max": max(neigh),
            "nn_distance": dists[0][0],
            "edge_margin": min(min(v, 1.0 - v) for v in vecs[i]) if vecs[i] else 0.0,
        })

    by_score = sorted(scored, key=lambda s: (-s["score"], s["nn_distance"]))
    # Candidates within BAND of the best neighbourhood score, then the one
    # furthest from the grid boundary wins. Choosing the centre of a plateau is
    # the point: when two regions are equally good, the one you can move inside
    # without falling off is strictly better.
    best_med = max(s["neighbour_median"] for s in scored)
    band = abs(best_med) * BAND + 1e-12
    pool = [s for s in scored if s["neighbour_median"] >= best_med - band]
    by_robust = sorted(pool, key=lambda s: (-s["edge_margin"], -s["neighbour_median"],
                                            s["nn_distance"]))
    peak = by_score[0]
    chosen = by_robust[0]
    all_scores = sorted(r[score] for r in usable)
    chosen_row = chosen["run"]

    drop = chosen["neighbour_mean"] - chosen["neighbour_min"]
    # How far the chosen point's *own* result sits above the average of the
    # search: a big number means most of the grid is not this good, i.e. a
    # narrow feature rather than a broad edge.
    spread = stdev(all_scores) or 1.0
    return {
        "params": param_names,
        "score": score,
        "k": kk,
        "runs_total": len(runs),
        "runs_used": len(usable),
        "chosen": chosen,
        "peak": peak,
        "band": BAND,
        "min_trades": min_trades,
        "chosen_is_peak": chosen is peak,
        "neighbour_drop": drop,
        "neighbour_drop_frac": (drop / abs(chosen["neighbour_mean"]))
                               if chosen["neighbour_mean"] else float("nan"),
        "peak_z": (peak["score"] - mean(all_scores)) / spread,
        "score_median": percentile(all_scores, 0.5),
        "score_p90": percentile(all_scores, 0.9),
        "top": [
            {"params": s["params"], "score": s["score"],
             "neighbour_median": s["neighbour_median"],
             "neighbour_mean": s["neighbour_mean"],
             "neighbour_min": s["neighbour_min"],
             "edge_margin": s["edge_margin"]}
            for s in sorted(scored, key=lambda s: (-s["neighbour_median"],
                                                   -s["edge_margin"]))[:10]
        ],
        "chosen_metrics": {k2: v for k2, v in chosen_row.items()
                           if k2 in METRIC_ALIASES or k2 == "net_profit"},
    }


def perturbation_report(runs, param_names, chosen_params, base_score=None) -> dict:
    """One-at-a-time +/- step sensitivity around the chosen parameters.

    For every parameter, find the grid rows that differ in that parameter only
    (or as close as the grid allows) and report the score range. A robust
    system degrades gently; a spike collapses to zero one step away.

    Implemented as nearest-neighbour in the normalised space with the tested
    axis excluded, so a randomised or non-Cartesian grid still yields an answer.
    """
    if not runs:
        raise ValueError("perturbation_report needs runs")
    axes = {}
    for name in param_names:
        vals = [r[name] for r in runs if r.get(name) is not None]
        if not vals:
            raise ValueError("parameter %r missing from every run" % name)
        lo, hi = min(vals), max(vals)
        axes[name] = (lo, hi, (hi - lo) or 1.0)

    def vec(run, skip=None):
        return tuple((run[n] - axes[n][0]) / axes[n][2]
                     for n in param_names if n != skip)

    base = []
    for r in runs:
        if all(abs(r[n] - chosen_params[n]) <= 1e-12 for n in param_names):
            base.append(r)
    if not base:
        raise ValueError("chosen_params do not match any run: %r" % (chosen_params,))
    base_row = base[0]
    base_val = base_score if base_score is not None else base_row.get("net_profit")

    out = {}
    for name in param_names:
        bv = vec(base_row, skip=name)
        scored = []
        for r in runs:
            if r is base_row or r.get("net_profit") is None:
                continue
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(bv, vec(r, skip=name))))
            scored.append((d, r[name], r["net_profit"]))
        if not scored:
            continue
        chosen_val = chosen_params[name]
        # "One grid step" = the nearest DISTINCT value on each side of the
        # chosen one; among the rows at that value, take the one whose other
        # axes are closest to the chosen row. Distance must be measured on the
        # other axes only, so every row in a column ties at 0 - which is why
        # the axis value is selected first and the distance second.
        below_vals = sorted({s[1] for s in scored if s[1] < chosen_val})
        above_vals = sorted({s[1] for s in scored if s[1] > chosen_val})
        near = []
        for target in (below_vals[-1] if below_vals else None,
                       above_vals[0] if above_vals else None):
            if target is None:
                continue
            same = [s for s in scored if s[1] == target]
            near.append(min(same, key=lambda t: (t[0], -t[2])))
        if not near:
            continue
        vals = [s[2] for s in near]
        axis_vals = [s[1] for s in near]
        out[name] = {
            "chosen": chosen_val,
            "tested_min": min(axis_vals),
            "tested_max": max(axis_vals),
            "score_min": min(vals),
            "score_max": max(vals),
            "worst_ratio": (min(vals) / base_val) if base_val else float("nan"),
        }
    return {"base": base_val, "params": out,
            "chosen": dict(chosen_params)}


def heatmap_rows(runs, param_x, param_y, score="net_profit", agg="mean") -> dict:
    """Collapse a >2D grid onto two axes and return a printable matrix.

    Aggregating over the remaining parameters is what makes a 4-parameter grid
    readable at all: you look at the *worst* or *mean* cell, never the best one.
    """
    xs = sorted({r[param_x] for r in runs if r.get(param_x) is not None})
    ys = sorted({r[param_y] for r in runs if r.get(param_y) is not None})
    if not xs or not ys:
        raise ValueError("heatmap axes must exist in the runs")
    cells = {}
    for r in runs:
        v = r.get(score)
        if v is None or not math.isfinite(v):
            continue
        cells.setdefault((r[param_x], r[param_y]), []).append(v)
    fn = min if agg == "min" else mean
    grid = [[fn(cells[(x, y)]) if (x, y) in cells else float("nan")
             for x in xs] for y in ys]
    return {"x": xs, "y": ys, "grid": grid, "agg": agg, "score": score,
            "x_name": param_x, "y_name": param_y}


def render_heatmap(hm, width=7) -> str:
    """ASCII/plain-text matrix: rows = param_y (ascending), columns = param_x."""
    out = []
    param_x_label = hm.get("x_name", "x")
    param_y_label = hm.get("y_name", "y")
    head = " " * 12 + " ".join("%*g" % (width, x) for x in hm["x"])
    out.append(head)
    for y, row in zip(hm["y"], hm["grid"]):
        cells = []
        for v in row:
            cells.append("%*s" % (width, "-" if not math.isfinite(v)
                                  else "%g" % (round(v, 2) if abs(v) < 1000 else round(v))))
        out.append("%-12g" % y + " ".join(cells))
    out.append("")
    out.append("columns = %s (ascending), rows = %s (ascending), cell = %s of %s "
               "over the remaining parameters"
               % (param_x_label, param_y_label, hm["agg"], hm["score"]))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------

def walk_forward(windows) -> dict:
    """Evaluate a roll-forward plan on the OOS segments only.

    Input: a list of dicts, each with at least
        {"name": "w1", "is_start": ..., "is_end": ..., "oos_start": ...,
         "oos_end": ..., "is_net_profit": 12.0, "oos_net_profit": 5.0,
         "params": {name: value, ...}}
    Optionally "oos_trades": [ ... ] to close each window with its own limit
    (a stop-out inside an OOS window is not cancelled by a good window later).

    Four numbers decide the verdict:
      * aggregate WFE = sum(OOS) / sum(IS): the classic >~50-60% bar.
      * median per-window WFE: one giant OOS window must not carry the average.
      * fraction of OOS windows profitable: consistency, not total.
      * parameter drift per window: a moving optimum is fitting by definition.
    """
    if not windows:
        raise ValueError("walk_forward needs at least one window")
    rows = []
    for w in windows:
        is_val = w.get("is_net_profit")
        oos_val = w.get("oos_net_profit")
        wfe = None
        if is_val not in (None, 0) and oos_val is not None:
            wfe = oos_val / is_val if is_val > 0 else None
        rows.append({"name": w.get("name", "?"),
                     "is_start": w.get("is_start"), "is_end": w.get("is_end"),
                     "oos_start": w.get("oos_start"), "oos_end": w.get("oos_end"),
                     "is": is_val, "oos": oos_val, "wfe": wfe,
                     "params": dict(w.get("params") or {})})

    is_sum = sum(r["is"] for r in rows if r["is"] is not None)
    oos_sum = sum(r["oos"] for r in rows if r["oos"] is not None)
    wfes = [r["wfe"] for r in rows if r["wfe"] is not None]
    profitable = sum(1 for r in rows if r["oos"] is not None and r["oos"] > 0)
    counted = sum(1 for r in rows if r["oos"] is not None)

    curve = []
    eq = 0.0
    for r in rows:
        if r["oos"] is None:
            continue
        eq += r["oos"]
        curve.append({"name": r["name"], "oos": r["oos"], "cumulative": eq})

    names = sorted({n for r in rows for n in r["params"]})
    stability = {}
    for n in names:
        vals = [r["params"].get(n) for r in rows if r["params"].get(n) is not None]
        if len(vals) < 2:
            continue
        lo, hi = min(vals), max(vals)
        rel = (hi - lo) / (abs(mean(vals)) or 1.0)
        changes = sum(1 for a, b in zip(vals, vals[1:]) if a != b)
        stability[n] = {"values": vals, "min": lo, "max": hi,
                        "relative_spread": rel,
                        "change_rate": changes / float(len(vals) - 1)}

    max_dd = 0.0
    peak = 0.0
    for point in curve:
        peak = max(peak, point["cumulative"])
        max_dd = max(max_dd, peak - point["cumulative"])

    return {
        "windows": rows,
        "n_windows": len(rows),
        "is_sum": is_sum,
        "oos_sum": oos_sum,
        "wfe_aggregate": (oos_sum / is_sum) if is_sum > 0 else None,
        "wfe_median": percentile(sorted(wfes), 0.5) if wfes else None,
        "wfe_min": min(wfes) if wfes else None,
        "wfe_max": max(wfes) if wfes else None,
        "profitable_windows": profitable,
        "oos_windows": counted,
        "profitable_frac": (profitable / float(counted)) if counted else 0.0,
        "stability": stability,
        "oos_curve": curve,
        "oos_curve_max_dd": max_dd,
        "windows_without_is": sum(1 for r in rows if r["is"] is None),
        "loss_making_is_windows": sum(1 for r in rows if (r["is"] or 0) <= 0),
    }


# ---------------------------------------------------------------------------
# Gates and verdicts
# ---------------------------------------------------------------------------

DEFAULT_GATES = {
    "min_trades": 100,
    "min_trades_per_param": 30,
    "max_params": 6,
    "profit_factor_lo": 1.3,
    "profit_factor_hi": 3.0,
    "wfe_min": 0.5,
    "profitable_oos_min": 0.6,
    "mc_dd_p95_max": 0.30,
    "skip_p05_min": 0.0,
    "benchmark_p_max": 0.05,
    "dsr_min": 0.95,
    "cost_stress_min": 0.0,
    "holdout_min": 0.0,
}


def _verdict(name, ok, value, threshold, warn=False, detail=""):
    status = "WARN" if warn else ("PASS" if ok else "FAIL")
    return {"gate": name, "value": value, "threshold": threshold,
            "status": status, "detail": detail}


def build_gates(report: dict, gates=None) -> list:
    """Turn raw study numbers into PASS/WARN/FAIL. No opinion beyond the gates.

    Every threshold is a configurable default, not a law of nature. What is NOT
    configurable is that a missing measurement is a SKIP, never a PASS.
    """
    g = dict(DEFAULT_GATES)
    g.update(gates or {})
    out = []
    stats = report.get("trades_stats") or {}
    n = stats.get("trades") or 0
    n_params = len(report.get("selection") or {})

    if n:
        out.append(_verdict("sample size", n >= g["min_trades"],
                            "%d trades" % n, ">= %d" % g["min_trades"]))
        if n_params:
            need = n_params * g["min_trades_per_param"]
            out.append(_verdict("trades per free parameter", n >= need,
                                "%d trades / %d params = %.0f"
                                % (n, n_params, n / float(n_params)),
                                ">= %d" % need))
    else:
        out.append(_verdict("sample size", False, "no trades", ">= %d" % g["min_trades"],
                            detail="SKIP is not available: the trade list is empty"))

    if n_params:
        out.append(_verdict("free parameters", n_params <= g["max_params"],
                            n_params, "<= %d" % g["max_params"]))
    else:
        out.append(_verdict("free parameters", False, "selection not supplied",
                            "<= %d" % g["max_params"]))

    pf = stats.get("profit_factor")
    if pf is not None and math.isfinite(pf):
        out.append(_verdict("profit factor in range",
                            g["profit_factor_lo"] <= pf <= g["profit_factor_hi"],
                            round(pf, 2),
                            "%.2f - %.2f" % (g["profit_factor_lo"], g["profit_factor_hi"]),
                            warn=(pf > g["profit_factor_hi"]),
                            detail=("above %.1f on a large sample is usually a "
                                    "survivor of the search, not an edge"
                                    % g["profit_factor_hi"]) if pf > g["profit_factor_hi"] else ""))

    wfa = report.get("wfa") or {}
    if wfa.get("wfe_aggregate") is not None:
        out.append(_verdict("walk-forward efficiency",
                            wfa["wfe_aggregate"] >= g["wfe_min"],
                            round(wfa["wfe_aggregate"], 2),
                            ">= %.2f" % g["wfe_min"],
                            detail="aggregate OOS / IS"))
        out.append(_verdict("profitable OOS windows",
                            wfa["profitable_frac"] >= g["profitable_oos_min"],
                            "%d/%d (%.0f%%)" % (wfa["profitable_windows"],
                                                wfa["oos_windows"],
                                                100 * wfa["profitable_frac"]),
                            ">= %.0f%%" % (100 * g["profitable_oos_min"])))
    else:
        out.append(_verdict("walk-forward efficiency", False, "not run",
                            ">= %.2f" % g["wfe_min"],
                            detail="no OOS segments supplied"))

    drift = [v["relative_spread"] for v in (wfa.get("stability") or {}).values()]
    if drift:
        worst = max(drift)
        out.append(_verdict("parameter stability (worst axis)",
                            worst <= 0.5, "%.2f relative spread" % worst, "<= 0.50",
                            warn=(worst <= 0.5 and worst > 0.3),
                            detail="an optimum that moves every window is a fit"))

    mc = report.get("mc") or {}
    if mc.get("dd_pct", {}).get("p95") is not None:
        p95 = mc["dd_pct"]["p95"]
        out.append(_verdict("Monte Carlo drawdown p95",
                            p95 <= g["mc_dd_p95_max"], "%.1f%%" % (100 * p95),
                            "<= %.0f%%" % (100 * g["mc_dd_p95_max"])))
    skip = report.get("skip") or {}
    if skip.get("net_profit", {}).get("p05") is not None:
        p05 = skip["net_profit"]["p05"]
        out.append(_verdict("drop 5-10% of trades",
                            p05 > g["skip_p05_min"], "p05 = %.2f" % p05,
                            "> %.2f" % g["skip_p05_min"]))

    dsr = report.get("dsr") or {}
    if (dsr.get("dsr") is not None and math.isfinite(dsr.get("dsr", float("nan")))
            and dsr.get("var_source", "none") == "none" and dsr.get("n_trials", 0) > 1):
        out.append(_verdict("deflated Sharpe ratio (%.0f trials)"
                            % dsr["n_trials"], False,
                            round(dsr["dsr"], 3), ">= %.2f" % g["dsr_min"],
                            detail="no trial-Sharpe dispersion supplied, so the "
                                   "hurdle is 0 and nothing was deflated; pass "
                                   "trial_sharpes or trial_sharpe_sd"))
    elif dsr.get("dsr") is not None and math.isfinite(dsr.get("dsr", float("nan"))):
        out.append(_verdict("deflated Sharpe ratio (%.0f trials)"
                            % dsr.get("n_trials", 0),
                            dsr["dsr"] >= g["dsr_min"],
                            round(dsr["dsr"], 3), ">= %.2f" % g["dsr_min"],
                            detail="SR* = %.3f hurdle (%s)"
                                   % (dsr.get("sr0", 0.0), dsr.get("var_source", "?"))))
    else:
        out.append(_verdict("deflated Sharpe ratio", False, "not computable",
                            ">= %.2f" % g["dsr_min"],
                            detail="supply trial_count and/or trial_sharpes"))

    bm = report.get("benchmark") or {}
    if bm.get("p_value") is not None:
        out.append(_verdict("random-entry benchmark",
                            bm["p_value"] <= g["benchmark_p_max"],
                            "p = %.3f (%d runs)" % (bm["p_value"], bm["n_benchmarks"]),
                            "<= %.3f" % g["benchmark_p_max"]))

    stress = report.get("stress") or {}
    if stress.get("net_profit") is not None:
        out.append(_verdict("cost stress (extra %.2f/trade)"
                            % stress.get("extra_cost_per_trade", 0.0),
                            stress["net_profit"] > g["cost_stress_min"],
                            round(stress["net_profit"], 2),
                            "> %.2f" % g["cost_stress_min"]))

    hold = report.get("holdout")
    if hold is not None:
        out.append(_verdict("single look at the holdout",
                            hold.get("net_profit", 0) > g["holdout_min"],
                            round(hold.get("net_profit", 0.0), 2),
                            "> %.2f" % g["holdout_min"],
                            detail="if you now tune on it, it is no longer a holdout"))
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(v, nd=2):
    if v is None:
        return "-"
    if isinstance(v, float):
        if not math.isfinite(v):
            return "inf" if v > 0 else "-"
        return ("%%.%df" % nd) % v
    return str(v)


def render_report(report: dict, gates) -> str:
    L = []
    a = L.append
    a("# Walk-forward robustness report — %s" % report.get("label", "unnamed study"))
    a("")
    if report.get("generated"):
        a("Generated %s · engine `tools/wfa_stats.py`" % report["generated"])
        a("")
    a("> This report quantifies how the study was attacked, not how much money the")
    a("> system will make. A PASS means the system survived these tests; it does not")
    a("> mean the edge is real. Nothing here is financial advice.")
    a("")

    fails = [g for g in gates if g["status"] == "FAIL"]
    warns = [g for g in gates if g["status"] == "WARN"]
    overall = "NO-GO" if fails else ("GO (with warnings)" if warns else "GO")
    a("## Verdict: **%s**" % overall)
    a("")
    a("| gate | measured | threshold | verdict |")
    a("|---|---|---|---|")
    for g in gates:
        detail = (" — " + g["detail"]) if g.get("detail") else ""
        a("| %s | %s | %s | **%s**%s |" % (g["gate"], g["value"], g["threshold"],
                                          g["status"], detail))
    a("")

    sel = report.get("selection") or {}
    if sel:
        a("## 1. Selected parameters")
        a("")
        a("| parameter | value |")
        a("|---|---|")
        for k in sorted(sel):
            a("| `%s` | %s |" % (k, sel[k]))
        a("")
        a("%d free parameters. A parameter that is not in this table was not optimised,"
          % len(sel))
        a("and that is deliberate.")
        a("")

    st = report.get("trades_stats")
    if st:
        a("## 2. Out-of-sample trades (stitched, unoptimised)")
        a("")
        a("| metric | value |")
        a("|---|---|")
        for key, label in (("trades", "trades"), ("net_profit", "net profit"),
                           ("expectancy", "expectancy / trade"),
                           ("profit_factor", "profit factor"),
                           ("sharpe", "per-trade Sharpe"),
                           ("max_dd_abs", "max drawdown (currency)"),
                           ("max_dd_pct", "max drawdown (% of peak)"),
                           ("win_rate", "win rate"),
                           ("longest_dd_trades", "longest drawdown (trades)")):
            if key in st:
                val = st[key]
                if key == "win_rate":
                    val = _fmt((val or 0) * 100, 1) + "%"
                elif key == "max_dd_pct":
                    val = _fmt((val or 0) * 100, 1) + "%"
                a("| %s | %s |" % (label, _fmt(val)))
        a("")

    pl = report.get("plateau")
    if pl:
        a("## 3. Optimisation surface")
        a("")
        c = pl["chosen"]
        a("| | peak row | chosen (plateau centre) |")
        a("|---|---|---|")
        a("| score (%s) | %s | %s |" % (pl["score"], _fmt(pl["peak"]["score"]),
                                        _fmt(c["score"])))
        a("| neighbour median | %s | %s |" % (_fmt(pl["peak"]["neighbour_median"]),
                                              _fmt(c["neighbour_median"])))
        a("| neighbour mean | %s | %s |" % (_fmt(pl["peak"]["neighbour_mean"]),
                                            _fmt(c["neighbour_mean"])))
        a("| neighbour min | %s | %s |" % (_fmt(pl["peak"]["neighbour_min"]),
                                           _fmt(c["neighbour_min"])))
        a("")
        a("- runs used: %d of %d (rows with a score%s)"
          % (pl["runs_used"], pl["runs_total"],
             ", trades >= the minimum" if pl.get("min_trades") else ""))
        a("- chosen == peak row: **%s**%s" % (
            pl["chosen_is_peak"],
            " (the search peak is also the broadest region — rare, verify it)" if pl["chosen_is_peak"] else ""))
        a("- worst neighbour drop: %s (%s of the chosen score)"
          % (_fmt(pl["neighbour_drop"]), _fmt(pl["neighbour_drop_frac"], 2)))
        a("- peak distance from the grid mean: %.2f standard deviations"
          % pl["peak_z"])
        a("")
        if pl.get("heatmap_text"):
            a("```")
            a(pl["heatmap_text"])
            a("```")
            a("")
        a("Chosen parameters: " + ", ".join("`%s=%s`" % (k, v) for k, v in
                                            sorted(c["params"].items())))
        a("")

    pert = report.get("perturbation")
    if pert:
        a("### Perturbation (± one grid step, one parameter at a time)")
        a("")
        a("| parameter | chosen | tested range | score range | worst / base |")
        a("|---|---|---|---|---|")
        for name, p in sorted(pert["params"].items()):
            a("| `%s` | %s | %s … %s | %s … %s | %s |" % (
                name, _fmt(p["chosen"]), _fmt(p["tested_min"]), _fmt(p["tested_max"]),
                _fmt(p["score_min"]), _fmt(p["score_max"]), _fmt(p["worst_ratio"], 2)))
        a("")

    wfa = report.get("wfa")
    if wfa:
        a("## 4. Walk-forward")
        a("")
        a("| window | IS | OOS | OOS/IS | parameters |")
        a("|---|---|---|---|---|")
        for w in wfa["windows"]:
            p = ", ".join("%s=%s" % (k, v) for k, v in sorted((w["params"] or {}).items()))
            a("| %s | %s | %s | %s | %s |" % (w["name"], _fmt(w["is"]), _fmt(w["oos"]),
                                              _fmt(w["wfe"]), p or "-"))
        a("")
        a("- aggregate WFE: **%s**" % _fmt(wfa["wfe_aggregate"]))
        a("- median per-window WFE: %s (min %s, max %s)"
          % (_fmt(wfa["wfe_median"]), _fmt(wfa["wfe_min"]), _fmt(wfa["wfe_max"])))
        a("- profitable OOS windows: %d of %d" % (wfa["profitable_windows"],
                                                  wfa["oos_windows"]))
        a("- stitched OOS sum: %s, peak-to-trough on the stitched curve: %s"
          % (_fmt(wfa["oos_sum"]), _fmt(wfa["oos_curve_max_dd"])))
        if wfa["loss_making_is_windows"]:
            a("- **%d IS window(s) were not profitable**: those windows have no WFE,"
              % wfa["loss_making_is_windows"])
            a("  and the aggregate is computed without them — read it as conditional.")
        if wfa["stability"]:
            a("")
            a("| parameter | values across windows | relative spread | changed at |")
            a("|---|---|---|---|")
            for name, s in sorted(wfa["stability"].items()):
                a("| `%s` | %s | %s | %s |" % (
                    name, ", ".join(_fmt(v) for v in s["values"]),
                    _fmt(s["relative_spread"], 2), "%.0f%%" % (100 * s["change_rate"])))
        a("")

    for key, title in (("mc", "5. Monte Carlo — trade order"),
                       ("bootstrap", "5b. Monte Carlo — resampled trades")):
        m = report.get(key)
        if not m:
            continue
        a("## %s" % title)
        a("")
        a("%d iterations, seed %d, %s." % (m["iterations"], m["seed"],
                                           "compounded" if m["compounding"] else "fixed size"))
        a("")
        a("| | p05 | median | p95 | worst |")
        a("|---|---|---|---|---|")
        d = m["dd_pct"]
        a("| drawdown %% of peak | %s | %s | %s | %s |" % (
            _fmt(100 * d.get("p05", 0), 1), _fmt(100 * d.get("median", 0), 1),
            _fmt(100 * d.get("p95", 0), 1), _fmt(100 * d.get("max", 0), 1)))
        p = m["net_profit"]
        a("| net profit | %s | %s | %s | %s |" % (
            _fmt(p.get("p05")), _fmt(p.get("median")), _fmt(p.get("p95")),
            _fmt(p.get("min"))))
        a("")

    skip = report.get("skip")
    if skip:
        a("## 6. Skip-trades Monte Carlo")
        a("")
        a("Dropping %.0f%% of trades (%s): net profit p05 = %s, p50 = %s; "
          "P(result <= 0) = %.1f%%."
          % (100 * skip["drop_frac"], skip["kind"].replace("_", " "),
             _fmt(skip["net_profit"].get("p05")), _fmt(skip["net_profit"].get("median")),
             100 * skip["prob_negative"]))
        a("")

    dsr = report.get("dsr")
    if dsr:
        a("## 7. Multiple testing")
        a("")
        a("- trials counted: **%d**" % dsr["n_trials"])
        a("- observed per-trade Sharpe: %s (n=%d, skew %s, kurtosis %s)"
          % (_fmt(dsr["sharpe"], 3), dsr["n"], _fmt(dsr.get("skew"), 2),
             _fmt(dsr.get("kurtosis"), 2)))
        a("- expected best-of-%d zero-skill Sharpe (SR*): %s (dispersion from: %s)"
          % (dsr["n_trials"], _fmt(dsr["sr0"], 3),
             dsr.get("var_source", "unknown").replace("_", " ")))
        a("- PSR against SR=0: %s" % _fmt(dsr["psr"], 3))
        a("- **DSR**: %s (probability the true Sharpe exceeds SR*)" % _fmt(dsr["dsr"], 3))
        a("")

    bm = report.get("benchmark")
    if bm:
        a("## 8. Random-entry benchmark")
        a("")
        a("Metric `%s`: real = %s; %d randomised-entry runs beat or matched it; "
          "**p = %.3f**." % (bm["metric"], _fmt(bm["real"]), bm["beat_or_equal"],
                             bm["p_value"]))
        b = bm["bench"]
        a("")
        a("Benchmark distribution: p05 %s, median %s, p95 %s."
          % (_fmt(b.get("p05")), _fmt(b.get("median")), _fmt(b.get("p95"))))
        a("")

    st2 = report.get("stress")
    if st2:
        a("## 9. Cost stress")
        a("")
        a("Charging an extra %s per trade: net profit %s → **%s**, profit factor %s → %s."
          % (_fmt(st2["extra_cost_per_trade"]), _fmt(st2["base_net_profit"]),
             _fmt(st2["net_profit"]), _fmt(st2["base_profit_factor"]),
             _fmt(st2["profit_factor"])))
        a("")

    a("## 10. What this report does not prove")
    a("")
    a("- It does not re-simulate a single bar: every number is derived from the")
    a("  trade list and the optimisation grid you supplied.")
    a("- It cannot see spread widening, requotes, partial fills or broker-side")
    a("  stop hunting except through the trades you recorded.")
    a("- A PASS on a 100-trade sample is weak evidence; the gates exist to make")
    a("  that weakness visible, not to remove it.")
    a("- Every gate threshold is a default in `DEFAULT_GATES`, not a law. Change")
    a("  them in the manifest consciously, and never after seeing the verdict.")
    a("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Study orchestration
# ---------------------------------------------------------------------------

def run_study(manifest: dict, base_dir: str = ".", generated=None) -> dict:
    """Execute every measurement a manifest asks for, then build the verdict."""
    def path_of(p):
        return p if os.path.isabs(p) else os.path.join(base_dir, p)

    report = {"label": manifest.get("label", "unnamed study"),
              "generated": generated or ""}
    gates = manifest.get("gates") or {}

    selection = manifest.get("selection") or {}
    report["selection"] = selection

    trades = None
    if manifest.get("trades"):
        trades = load_trades(path_of(manifest["trades"]))
        report["trades_stats"] = trade_stats(trades, manifest.get("start_equity", 10000.0))

    plateau_spec = manifest.get("plateau")
    pl = None
    if plateau_spec:
        params, runs = load_runs(path_of(plateau_spec["runs"]))
        use = plateau_spec.get("params") or params
        missing = [p for p in use if p not in params]
        if missing:
            raise ValueError("plateau params not found in %s: %s"
                             % (plateau_spec["runs"], ", ".join(missing)))
        pl = plateau(runs, use, score=plateau_spec.get("score", "net_profit"),
                     k=plateau_spec.get("k", 4),
                     min_trades=plateau_spec.get("min_trades", 0))
        if plateau_spec.get("heatmap"):
            hm = heatmap_rows(runs, plateau_spec["heatmap"][0],
                              plateau_spec["heatmap"][1],
                              score=plateau_spec.get("score", "net_profit"),
                              agg=plateau_spec.get("agg", "mean"))
            pl["heatmap_text"] = render_heatmap(hm)
        report["plateau"] = pl
        if not selection:
            selection = pl["chosen"]["params"]
            report["selection"] = selection
        if plateau_spec.get("perturbation", True) and selection:
            try:
                report["perturbation"] = perturbation_report(runs, use, selection)
            except ValueError:
                pass

    if manifest.get("windows"):
        report["wfa"] = walk_forward(manifest["windows"])
        if not selection:
            first = next((w.get("params") for w in manifest["windows"]
                          if w.get("params")), None)
            if first:
                report["selection"] = first

    if trades:
        start_eq = manifest.get("start_equity", 10000.0)
        compounding = bool(manifest.get("compounding", False))
        mc_spec = manifest.get("mc") or {}
        report["mc"] = mc_shuffle(trades, mc_spec.get("iterations", 5000),
                                  mc_spec.get("seed", 7), start_eq, compounding)
        report["skip"] = mc_skip(trades, mc_spec.get("iterations", 5000),
                                 mc_spec.get("seed", 7),
                                 mc_spec.get("drop_frac", 0.05), start_eq, compounding)
        if mc_spec.get("bootstrap"):
            report["bootstrap"] = mc_bootstrap(trades, mc_spec.get("iterations", 5000),
                                               mc_spec.get("seed", 7), start_eq,
                                               compounding)
        trial_sharpes = manifest.get("trial_sharpes")
        if trial_sharpes is None and plateau_spec:
            try:
                _, runs2 = load_runs(path_of(plateau_spec["runs"]))
                trial_sharpes = [r.get("sharpe") for r in runs2 if r.get("sharpe") is not None]
            except ValueError:
                trial_sharpes = None
        n_trials = manifest.get("trials")
        if n_trials is None and pl:
            n_trials = pl["runs_used"]
        if n_trials:
            report["dsr"] = deflated_sharpe(trades, int(n_trials), trial_sharpes,
                                            manifest.get("trial_sharpe_sd"))

        bench_paths = manifest.get("benchmarks") or []
        if bench_paths:
            lists = [load_trades(path_of(p)) for p in bench_paths]
            report["benchmark"] = benchmark(trades, lists,
                                            manifest.get("benchmark_metric", "net_profit"))

        cost = manifest.get("cost_stress")
        if cost is not None:
            extra = float(cost.get("extra_cost_per_trade", 0.0)
                          if isinstance(cost, dict) else cost)
            stressed = [p - extra for p in trades]
            base_stats = report["trades_stats"]
            st = trade_stats(stressed, manifest.get("start_equity", 10000.0))
            report["stress"] = {
                "extra_cost_per_trade": extra,
                "base_net_profit": base_stats["net_profit"],
                "net_profit": st["net_profit"],
                "base_profit_factor": base_stats["profit_factor"],
                "profit_factor": st["profit_factor"],
            }

    if manifest.get("holdout_trades"):
        report["holdout"] = trade_stats(load_trades(path_of(manifest["holdout_trades"])),
                                        manifest.get("start_equity", 10000.0))

    report["gates"] = build_gates(report, gates)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _emit(obj, args):
    text = json.dumps(obj, indent=2, sort_keys=True, default=str)
    if getattr(args, "json", None):
        with io.open(args.json, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)


def cmd_plateau(args):
    params, runs = load_runs(args.runs)
    use = args.params.split(",") if args.params else params
    missing = [p for p in use if p not in params]
    if missing:
        print("unknown parameter(s): %s (available: %s)"
              % (", ".join(missing), ", ".join(params)), file=sys.stderr)
        return 2
    pl = plateau(runs, use, score=args.score, k=args.k, min_trades=args.min_trades)
    out = {k: v for k, v in pl.items() if k != "heatmap_text"}
    if args.heatmap:
        a, b = args.heatmap.split(",")
        if a not in params or b not in params:
            print("heatmap parameters must both exist in the grid", file=sys.stderr)
            return 2
        hm = heatmap_rows(runs, a, b, score=args.score, agg=args.agg)
        print(render_heatmap(hm))
        out["heatmap"] = hm
    if args.perturbation:
        out["perturbation"] = perturbation_report(runs, use, out["chosen"]["params"])
    _emit(out, args)
    return 0


def cmd_wfa(args):
    with io.open(args.windows, encoding="utf-8") as fh:
        data = json.load(fh)
    windows = data["windows"] if isinstance(data, dict) else data
    res = walk_forward(windows)
    _emit(res, args)
    return 0 if (res["wfe_aggregate"] or 0) >= args.wfe_min else 1


def cmd_mc(args):
    trades = load_trades(args.trades)
    if args.mode == "bootstrap":
        res = mc_bootstrap(trades, args.iterations, args.seed, args.start_equity,
                           args.compounding)
    elif args.mode == "skip":
        res = mc_skip(trades, args.iterations, args.seed, args.drop_frac,
                      args.start_equity, args.compounding, randomised=not args.worst)
    else:
        res = mc_shuffle(trades, args.iterations, args.seed, args.start_equity,
                         args.compounding)
    _emit(res, args)
    return 0


def cmd_dsr(args):
    trades = load_trades(args.trades)
    srs = None
    if args.trial_sharpes:
        with io.open(args.trial_sharpes, encoding="utf-8") as fh:
            rows = [line.strip() for line in fh if line.strip()]
        if rows and "sharpe" in rows[0].lower():
            rows = rows[1:]
        # An empty (or all-text) file means "no trial Sharpes supplied": the
        # hurdle then assumes zero variance between trials, which is the
        # conservative reading of a grid whose Sharpe column was not exported.
        srs = [to_float(r.split(",")[-1]) for r in rows]
        srs = [s for s in srs if s is not None] or None
    res = deflated_sharpe(trades, args.trials, srs, args.trial_sharpe_sd)
    _emit(res, args)
    return 0 if (res.get("dsr") or 0) >= args.dsr_min else 1


def cmd_benchmark(args):
    real = load_trades(args.trades)
    lists = []
    if os.path.isdir(args.bench_dir):
        for name in sorted(os.listdir(args.bench_dir)):
            if name.lower().endswith(".csv"):
                try:
                    lists.append(load_trades(os.path.join(args.bench_dir, name)))
                except ValueError:
                    continue
    else:
        lists.append(load_trades(args.bench_dir))
    if not lists:
        print("no benchmark trade files found", file=sys.stderr)
        return 2
    res = benchmark(real, lists, args.metric)
    _emit(res, args)
    return 0 if res["p_value"] <= args.p_max else 1


def cmd_stress(args):
    trades = load_trades(args.trades)
    base = trade_stats(trades, args.start_equity)
    stressed = [p - args.extra_cost for p in trades]
    st = trade_stats(stressed, args.start_equity)
    res = {"extra_cost_per_trade": args.extra_cost,
           "base_net_profit": base["net_profit"], "net_profit": st["net_profit"],
           "base_profit_factor": base["profit_factor"],
           "profit_factor": st["profit_factor"],
           "base_expectancy": base["expectancy"],
           "expectancy": st["expectancy"]}
    _emit(res, args)
    return 0 if res["net_profit"] > 0 else 1


def cmd_report(args):
    with io.open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    base = os.path.dirname(os.path.abspath(args.manifest))
    report = run_study(manifest, base, generated=args.date)
    text = render_report(report, report["gates"])
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        verdict = [line for line in text.splitlines() if line.startswith("## Verdict")]
        print("report: %s" % args.out)
        if verdict:
            print(verdict[0].lstrip("# "))
    elif not args.json:
        print(text)
    if args.json:
        _emit(report, args)
    fails = [g for g in report["gates"] if g["status"] == "FAIL"]
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Offline walk-forward / over-optimisation statistics for MT5 exports.")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("plateau", help="choose params from a plateau, not the peak")
    p.add_argument("--runs", required=True, help="optimisation grid CSV")
    p.add_argument("--params", help="comma list of parameter columns (default: all numeric)")
    p.add_argument("--score", default="net_profit")
    p.add_argument("--k", type=int, default=4, help="neighbours averaged (default 4)")
    p.add_argument("--min-trades", type=float, default=0.0)
    p.add_argument("--heatmap", help="a,b to print a collapsed matrix")
    p.add_argument("--agg", choices=("mean", "min"), default="mean")
    p.add_argument("--perturbation", action="store_true")
    p.add_argument("--json", default=None,
                   help="also write the raw result as JSON to this path")
    p.set_defaults(func=cmd_plateau)

    p = sub.add_parser("wfa", help="score a roll-forward plan")
    p.add_argument("--windows", required=True, help="windows JSON (list or {windows: [...]})")
    p.add_argument("--wfe-min", type=float, default=DEFAULT_GATES["wfe_min"])
    p.add_argument("--json", default=None,
                   help="also write the raw result as JSON to this path")
    p.set_defaults(func=cmd_wfa)

    p = sub.add_parser("mc", help="Monte Carlo on a closed-trade list")
    p.add_argument("--trades", required=True)
    p.add_argument("--mode", choices=("shuffle", "bootstrap", "skip"), default="shuffle")
    p.add_argument("--iterations", type=int, default=5000)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--start-equity", type=float, default=10000.0)
    p.add_argument("--compounding", action="store_true")
    p.add_argument("--drop-frac", type=float, default=0.05)
    p.add_argument("--worst", action="store_true",
                   help="skip mode: drop the worst trades instead of random ones")
    p.add_argument("--json", default=None,
                   help="also write the raw result as JSON to this path")
    p.set_defaults(func=cmd_mc)

    p = sub.add_parser("dsr", help="deflated Sharpe ratio")
    p.add_argument("--trades", required=True)
    p.add_argument("--trials", type=int, required=True)
    p.add_argument("--trial-sharpes", help="CSV/text of Sharpe values from the grid")
    p.add_argument("--trial-sharpe-sd", type=float, default=None,
                   help="assumed dispersion of trial Sharpes when the grid did "
                        "not export them (needed for the hurdle to be non-zero)")
    p.add_argument("--dsr-min", type=float, default=DEFAULT_GATES["dsr_min"])
    p.add_argument("--json", default=None,
                   help="also write the raw result as JSON to this path")
    p.set_defaults(func=cmd_dsr)

    p = sub.add_parser("benchmark", help="random-entry benchmark p-value")
    p.add_argument("--trades", required=True)
    p.add_argument("--bench-dir", required=True, help="dir of random-entry trade CSVs")
    p.add_argument("--metric", default="net_profit", choices=sorted(METRIC_FUNCS))
    p.add_argument("--p-max", type=float, default=DEFAULT_GATES["benchmark_p_max"])
    p.add_argument("--json", default=None,
                   help="also write the raw result as JSON to this path")
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("stress", help="re-price the trade list with worse costs")
    p.add_argument("--trades", required=True)
    p.add_argument("--extra-cost", type=float, required=True,
                   help="extra cost per round turn, account currency")
    p.add_argument("--start-equity", type=float, default=10000.0)
    p.add_argument("--json", default=None,
                   help="also write the raw result as JSON to this path")
    p.set_defaults(func=cmd_stress)

    p = sub.add_parser("report", help="run a study manifest and emit PASS/WARN/FAIL")
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", help="write markdown here")
    p.add_argument("--date", help="override the generated-date line (for reproducibility)")
    p.add_argument("--json", default=None,
                   help="also write the raw result as JSON to this path")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args)
    except (ValueError, KeyError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
