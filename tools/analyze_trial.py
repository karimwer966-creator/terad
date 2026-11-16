#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ANALYZE THE DEMO TRIAL - read the EA's CSV journal and apply the owner's thresholds.

WHAT IT READS
    MQL5/Files/QSMC_trial_<login>.csv, written by QSMC_AutoTrader.mq5 (R1).
    One row per execution event:
        time_server,symbol,tf,magic,signal_bar_time,dir,class,score,
        entry_signal,sl,tp,spread_points,lots,risk_money,retcode,event,note
    Events: signal_seen, order_sent, order_refused, fill, partial_close,
    sl_move, close, breaker_trip.

WHAT IT PRINTS
    a funnel (seen -> sent -> filled -> closed), the refusals grouped by cause,
    every breaker trip with its numbers, and then the four acceptance
    thresholds from tools/trial_acceptance.json:
        min_trades, max_dd_r, min_expectancy_r, max_avg_slippage_points
    Each line is PASS / FAIL / INCONCLUSIVE. Below `min_sample_for_conclusion`
    closed trades the tool prints

        sample size too small to conclude

    even when everything passes, because that is exactly what a 12-trade sample
    supports. It never prints a profit claim, a win rate, or a forecast.

USAGE
    python3 tools/analyze_trial.py                       # newest CSV it can find
    python3 tools/analyze_trial.py path/to/QSMC_trial_123.csv
    python3 tools/analyze_trial.py --acceptance tools/trial_acceptance.json
    python3 tools/analyze_trial.py --json                # machine-readable

EXIT CODES
    0  every threshold PASS (or INCONCLUSIVE because the sample is small)
    1  a threshold FAILED
    2  the CSV could not be read / has no usable rows
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ACCEPTANCE = os.path.join(ROOT, "tools", "trial_acceptance.json")

# The CSV lives in the TERMINAL's data folder, not in this repository. These are
# the places an operator is most likely to point us at.
SEARCH = (
    os.path.join(ROOT, "MQL5", "Files", "QSMC_trial_*.csv"),
    os.path.expanduser("~/MQL5/Files/QSMC_trial_*.csv"),
    os.path.expanduser("~/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Files/QSMC_trial_*.csv"),
)

EVENTS = ("signal_seen", "order_sent", "order_refused", "fill",
          "partial_close", "sl_move", "close", "breaker_trip")

NUM = re.compile(r"(-?\d+(?:\.\d+)?)")


def find_csv(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    candidates: list[str] = []
    for pattern in SEARCH:
        candidates.extend(glob.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def grab(note: str, key: str) -> float | None:
    """Pull `key=<number>` out of a journal note. None when absent."""
    m = re.search(re.escape(key) + r"=(" + NUM.pattern + ")", note)
    return float(m.group(1)) if m else None


def load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if not r:
            continue
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if r.get("event"):
            out.append(r)
    return out


def stats(rows: list[dict]) -> dict:
    counts = {e: 0 for e in EVENTS}
    refusals: dict[str, int] = {}
    breakers: list[dict] = []
    closes: list[dict] = []
    fills: list[dict] = []
    slip: list[float] = []

    for r in rows:
        e = r["event"]
        counts[e] = counts.get(e, 0) + 1
        note = r.get("note", "")
        if e == "order_refused":
            why = note.split(":")[0].strip()[:60] or "unspecified"
            refusals[why] = refusals.get(why, 0) + 1
        elif e == "breaker_trip":
            breakers.append(r)
        elif e == "fill":
            fills.append(r)
            s = grab(note, "slip_points")
            if s is not None:
                slip.append(abs(s))
        elif e == "close":
            r_val = grab(note, "R")
            profit = grab(note, "profit")
            closes.append({"time": r.get("time_server", ""), "R": r_val,
                           "profit": profit, "note": note})

    # cumulative-R curve, in time order, for the drawdown
    curve, run = [], 0.0
    for c in closes:
        if c["R"] is None:
            continue
        run += c["R"]
        curve.append(run)
    peak, dd = 0.0, 0.0
    for v in curve:
        peak = max(peak, v)
        dd = max(dd, peak - v)

    r_values = [c["R"] for c in closes if c["R"] is not None]
    return {
        "rows": len(rows),
        "counts": counts,
        "refusals": refusals,
        "breakers": breakers,
        "closed_with_R": len(r_values),
        "expectancy_r": (sum(r_values) / len(r_values)) if r_values else None,
        "max_dd_r": dd if curve else None,
        "avg_slippage_points": (sum(slip) / len(slip)) if slip else None,
        "fills_with_slippage": len(slip),
        "fills": len(fills),
    }


def verdict(ok: bool, enough: bool) -> str:
    if not ok:
        return "FAIL"
    return "PASS" if enough else "INCONCLUSIVE"


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply the demo-trial thresholds to the EA's CSV journal.")
    ap.add_argument("csv", nargs="?", help="path to QSMC_trial_<login>.csv")
    ap.add_argument("--acceptance", default=DEFAULT_ACCEPTANCE,
                    help="thresholds file (default tools/trial_acceptance.json)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    try:
        with open(args.acceptance, encoding="utf-8") as fh:
            acc = json.load(fh)
    except (OSError, ValueError) as exc:
        print("cannot read acceptance file %s: %s" % (args.acceptance, exc))
        return 2

    path = find_csv(args.csv)
    if not path:
        print("no QSMC_trial_*.csv found.")
        print("looked in: MQL5/Files/ of this checkout, ~/MQL5/Files/, and the Wine MT5 path.")
        print("Pass the file explicitly: python3 tools/analyze_trial.py /path/to/QSMC_trial_<login>.csv")
        return 2
    rows = load_rows(path)
    if not rows:
        print("%s: no usable rows (header only?)" % path)
        return 2

    s = stats(rows)
    min_trades = int(acc.get("min_trades", 30))
    min_sample = int(acc.get("min_sample_for_conclusion", 100))
    enough = s["closed_with_R"] >= min_sample

    checks = []
    checks.append(("min_trades", s["closed_with_R"], min_trades,
                   s["closed_with_R"] >= min_trades,
                   "closed trades with an R value (need >= %d)" % min_trades))

    if s["max_dd_r"] is None:
        checks.append(("max_dd_r", None, acc.get("max_dd_r"), False,
                       "no close row carried an R value"))
    else:
        checks.append(("max_dd_r", round(s["max_dd_r"], 3), acc.get("max_dd_r"),
                       s["max_dd_r"] <= float(acc.get("max_dd_r", 6)),
                       "worst peak-to-trough of the cumulative R curve"))

    if s["expectancy_r"] is None:
        checks.append(("min_expectancy_r", None, acc.get("min_expectancy_r"), False,
                       "no close row carried an R value"))
    else:
        checks.append(("min_expectancy_r", round(s["expectancy_r"], 4),
                       acc.get("min_expectancy_r"),
                       s["expectancy_r"] >= float(acc.get("min_expectancy_r", 0.0)),
                       "mean R per closed trade"))

    if s["avg_slippage_points"] is None:
        checks.append(("max_avg_slippage_points", None, acc.get("max_avg_slippage_points"),
                       False, "no fill row carried slip_points"))
    else:
        checks.append(("max_avg_slippage_points", round(s["avg_slippage_points"], 2),
                       acc.get("max_avg_slippage_points"),
                       s["avg_slippage_points"] <= float(acc.get("max_avg_slippage_points", 20)),
                       "mean |fill - planned entry| in points"))

    failed = [c for c in checks if not c[3]]
    verdicts = [(name, verdict(ok, enough)) for name, _, _, ok, _ in checks]

    if args.json:
        print(json.dumps({"file": path, "stats": s, "checks": [
            {"name": n, "value": v, "threshold": t, "verdict": vd, "meaning": m}
            for (n, v, t, _ok, m), (_n, vd) in zip(checks, verdicts)],
            "sample_sufficient": enough,
            "failed": [c[0] for c in failed]}, indent=2, default=str))
        return 1 if failed else 0

    line = "-" * 78
    print(line)
    print("QSMC DEMO TRIAL - %s" % path)
    print(line)
    print("rows: %d" % s["rows"])
    for e in EVENTS:
        print("  %-14s %d" % (e, s["counts"].get(e, 0)))
    if s["refusals"]:
        print("refusals by cause:")
        for why, n in sorted(s["refusals"].items(), key=lambda kv: -kv[1]):
            print("  %-60s %d" % (why, n))
    if s["breakers"]:
        print("breaker trips:")
        for b in s["breakers"]:
            print("  %s  %s" % (b.get("time_server", ""), b.get("note", "")))
    print(line)
    print("thresholds from %s" % args.acceptance)
    for (name, value, threshold, ok, meaning), (_n, vd) in zip(checks, verdicts):
        print("  %-5s %-26s value=%-10s threshold=%s" %
              (vd, name, "n/a" if value is None else value, threshold))
        print("        %s" % meaning)
    print(line)
    if not enough:
        print("sample size too small to conclude: %d closed trade(s), %d needed."
              % (s["closed_with_R"], min_sample))
        print("The numbers above are printed because they are measured, not because")
        print("they mean anything yet. Do not read a verdict into them.")
    else:
        print("sample size %d closed trades: the thresholds above are the verdict."
              % s["closed_with_R"])
    print("This is a technical and statistical check of EXECUTION, not a forecast,")
    print("not a win rate, and not a promise of profit. A PASS here says the EA did")
    print("what it was built to do on this sample.")
    print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
