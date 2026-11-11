#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QATS-BACKTEST - replay M1 bid/ask history through the natively built EA.

WHAT THIS IS
------------
The EA source is compiled by the host C++ compiler against the typed MQL5 shim
(tools/qats_native.py) and driven tick by tick by a broker simulator
(tools/qats_sim/). Every decision in a run is made by the bytes MetaEditor
compiles; every number in a report comes from the simulator's deal history
(trades) or from the EA's own journal (signals, blocks, rejections).

WHAT THIS IS NOT
----------------
NOT the MT5 Strategy Tester and NOT broker execution. The fill model is the
"1 minute OHLC" one: each M1 bar becomes four quotes (open, the extreme the bar
most plausibly visited first, the other extreme, close); server-side stops fill
at their level inside a minute and at the quote on a gap; an adverse slippage is
charged on every stop-loss fill. Spread comes from the data's own bid/ask,
optionally scaled or fixed. Swaps are not modelled. Results are a simulation.

Sub-commands
------------
  fetch   download and verify the public XAUUSD M1 bid/ask history (not committed)
  run     one replay; prints the JSON summary
  study   the fixed in-sample / out-of-sample matrix + REPORT.md
  mirror  replay a period and its price-mirrored twin; BUY and SELL must swap exactly
  report  re-render REPORT.md from the JSON files of a previous study

Exit code: 0 ok, 77 no host C++ compiler, anything else = failure.
"""
from __future__ import print_function

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qats_native as Q  # noqa: E402

ROOT = Q.ROOT
EA_REL = "MQL5/Experts/QuantumAutonomousTradingSystem.mq5"

# The public dataset this study was run on. It is NOT committed (10 files, 470 MB).
DATASET = {
    "repo": "Dypoi/XAUUSD_Dataset",
    "commit": "4f9fe4b7a9fdd864c732b6047c899b17acddc7bc",
    "layout": "timestamp(UTC),open_bid,high_bid,low_bid,close_bid,open_ask,high_ask,low_ask,close_ask,volume_bid,volume_ask",
    "files": {
        "XAUUSD_M1_20160901_20170901.csv": "92d23f3cc96054ccaaa3992e2035937f6a37b2ef19697c43249b00ebc9fb6845",
        "XAUUSD_M1_20170901_20180901.csv": "dbc06cc5899515d297bb73db359a2d46fa90df916cfc70dd1223ca700267ac61",
        "XAUUSD_M1_20180901_20190901.csv": "e55306dc3092f8a707e3566e06d40ac4c5d4341e84121215bf4d3f7e1d2401b2",
        "XAUUSD_M1_20190901_20200901.csv": "afa2a696e144ccf9cc5b3f0e1df4770dc630682066d7c2fa0053f604d4b35870",
        "XAUUSD_M1_20200901_20210901.csv": "ff26f5f5e3220297169cf4f957d81d5e36c9de8b3cc8be5bf4c7be7142871a8b",
        "XAUUSD_M1_20210901_20220901.csv": "0d6635f653a1b8edd62431f87f1594f3f789661fc1e1a15c3d92ef1423041ec0",
        "XAUUSD_M1_20220901_20230901.csv": "054c096a4009cb0e6954c020ca5c16e3b57acded77cb1ef7aea1fcb667e48607",
        "XAUUSD_M1_20230901_20240901.csv": "b6fcc2d1757b0ffa8570fe11052199a1f9f0e8ba175976d3170b080b04622645",
        "XAUUSD_M1_20240901_20250901.csv": "f4eb787dd81b2d3ea95ddd3a8397f352e4c77293144e5355b1c31f46d0662a4f",
        "XAUUSD_M1_20250901_20260901.csv": "a36ad5e88179c2b87181d6f064c690fc8abd99ecc1c3ea6b0acabb845a1cb296",
    },
}

# v1.11, the build this audit started from (the parent of the audit branch).
BASELINE_COMMIT = "34156cc993c8272eb8f6865ba248847f38765b26"

# Fixed study design. The out-of-sample window was not looked at while the engine
# was being designed; it is replayed with the shipped defaults only.
PERIODS = [
    ("IS", "in-sample", "2017-02-01", "2023-09-01"),
    ("OOS", "out-of-sample", "2023-09-01", "2026-09-01"),
]

# "signal study" = the two account-level circuit breakers that END a run (equity
# drawdown halt, daily loss lock) are switched off and the balance is large enough
# that the minimum lot never decides, so the SIGNAL can be measured over the whole
# window. Every other guard stays on. The production run keeps everything on.
SIGNAL_STUDY = {"InpMaxAccountDrawdownPct": "0", "InpMaxDailyLossPercent": "0"}

PRESET_REL = "presets/Quantum_XAUUSD_PRODUCTION.set"


def load_preset(path=None):
    """{input: value} from the shipped .set file (comment lines and empty values dropped)."""
    path = path or os.path.join(ROOT, PRESET_REL)
    out = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(";") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if v.strip() != "":
                out[k.strip()] = v.strip()
    return out


STUDY = [
    # key, title, source, input overrides, balance, spread, signal-study?
    ("bal", "v1.20 BALANCED (shipped default)", "ea", {}, 1000000, "scaled:0.5", True),
    ("con", "v1.20 CONSERVATIVE", "ea", {"InpStrategyProfile": "0"}, 1000000, "scaled:0.5", True),
    ("act", "v1.20 ACTIVE", "ea", {"InpStrategyProfile": "2"}, 1000000, "scaled:0.5", True),
    ("v111", "v1.11 baseline", "baseline", {}, 1000000, "scaled:0.5", True),
    ("bal_real", "v1.20 BALANCED, raw feed spread", "ea", {}, 1000000, "real", True),
    ("bal_fixed30", "v1.20 BALANCED, fixed 30-point spread", "ea", {}, 1000000, "fixed:30", True),
    ("bal_zone", "v1.20 BALANCED + InpRequireZoneTouch", "ea", {"InpRequireZoneTouch": "true"}, 1000000, "scaled:0.5", True),
    ("bal_session", "v1.20 BALANCED, session 09-22 server", "ea",
     {"InpSessionStartHour": "9", "InpSessionEndHour": "22"}, 1000000, "scaled:0.5", True),
    ("bal_prod", "v1.20 compiled defaults, ALL guards on, 10k account", "ea", {}, 10000, "scaled:0.5", False),
    ("bal_preset", "v1.20 shipped preset (.set), ALL guards on, 10k account", "ea", "PRESET", 10000, "scaled:0.5", False),
    ("v111_prod", "v1.11 compiled defaults, ALL guards on, 10k account", "baseline", {}, 10000, "scaled:0.5", False),
]
ACCOUNT_RUNS = ("bal_prod", "bal_preset", "v111_prod")


# ------------------------------------------------------------------ binaries
def build_binary(source="ea", out_dir=None):
    """Build the simulator for the working-tree EA ('ea') or for v1.11 ('baseline')."""
    out_dir = out_dir or Q.OUT_DIR
    if source == "ea":
        exe, rc, diag = Q.build(Q.EA_SOURCE, "ea", out_dir=out_dir)
    else:
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.join(out_dir, "baseline_v111", "QuantumAutonomousTradingSystem.mq5")
        os.makedirs(os.path.dirname(base), exist_ok=True)
        proc = subprocess.run(["git", "show", "%s:%s" % (BASELINE_COMMIT, EA_REL)], cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise SystemExit("cannot read the v1.11 baseline from git (%s): %s"
                             % (BASELINE_COMMIT[:8], proc.stderr.decode("utf-8", "replace").strip()))
        with open(base, "wb") as fh:
            fh.write(proc.stdout)
        exe, rc, diag = Q.build(base, "baseline", out_dir=out_dir)
    if rc == Q.SKIP_EXIT:
        print("SKIP  qats-backtest: " + diag)
        sys.exit(Q.SKIP_EXIT)
    if rc != 0:
        print(diag)
        raise SystemExit("host build of the %s EA failed" % source)
    return exe


def run_replay(exe, data_dir, start, end, json_path, sets=None, spread="scaled:0.5", balance=10000,
               label="", trades=None, log=None, extra=None, files=None):
    cmd = [exe, "backtest", "--from", start, "--to", end, "--spread", spread, "--balance", str(balance),
           "--json", json_path, "--quiet", "--label", label]
    if files:
        for f in files:
            cmd += ["--file", f]
    else:
        cmd += ["--data", data_dir]
    for k, v in (sets or {}).items():
        cmd += ["--set", "%s=%s" % (k, v)]
    if trades:
        cmd += ["--trades", trades]
    if log:
        cmd += ["--log", log]
    cmd += list(extra or [])
    return cmd


# -------------------------------------------------------------------- fetch
def cmd_fetch(args):
    try:
        from urllib.request import urlopen
    except ImportError:                                   # pragma: no cover
        raise SystemExit("python3 is required")
    os.makedirs(args.dest, exist_ok=True)
    have = all(os.path.isfile(os.path.join(args.dest, n)) for n in DATASET["files"])
    if not have:
        url = "https://codeload.github.com/%s/tar.gz/%s" % (DATASET["repo"], DATASET["commit"])
        tar_path = os.path.join(args.dest, "dataset.tar.gz")
        print("downloading %s" % url)
        with urlopen(url, timeout=600) as resp, open(tar_path, "wb") as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        with tarfile.open(tar_path) as tar:
            for member in tar.getmembers():
                name = os.path.basename(member.name)
                if name in DATASET["files"]:
                    member.name = name
                    tar.extract(member, args.dest)
        os.remove(tar_path)
    bad = 0
    for name, want in sorted(DATASET["files"].items()):
        h = hashlib.sha256()
        with open(os.path.join(args.dest, name), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        ok = h.hexdigest() == want
        bad += 0 if ok else 1
        print("%s  %s" % ("OK  " if ok else "BAD ", name))
    if bad:
        raise SystemExit("%d file(s) do not match the pinned SHA-256" % bad)
    print("dataset verified: %s @ %s" % (DATASET["repo"], DATASET["commit"][:12]))
    return 0


# ---------------------------------------------------------------- reporting
def pct(x):
    return "%.1f%%" % (100.0 * x)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def journal(j, key):
    return j.get("journal", {}).get(key, 0)


def direction_rows(j):
    """Signals / executions / rejections for BUY and SELL from one result."""
    jr = j.get("journal", {})
    rows = {}
    for side in ("BUY", "SELL"):
        d = j[side.lower()]
        blocked = sum(v for k, v in jr.items() if k.startswith("outcome.%s.BLOCKED" % side))
        rejected = sum(v for k, v in jr.items() if k.startswith("outcome.%s.REJECTED" % side) or
                       k.startswith("outcome.%s.NOT_EXECUTED" % side))
        rows[side] = {
            "detected": jr.get("tag.[QATS][%s][DETECTED]" % side, None),
            "candidate_bars": jr.get("cand.%s" % side, 0),
            "eligible_bars": jr.get("eligible.%s" % side, 0),
            "core_pass_bars": jr.get("core.%s.pass" % side, None),
            "score_ge_min_bars": jr.get("scored.%s.ge_min" % side, None),
            "executed": d["trades"],
            "blocked_bars": blocked,
            "rejected_bars": rejected,
            "win_rate": d["win_rate"],
            "profit_factor": d["profit_factor"],
            "net": d["net"],
            "expectancy_R": d["expectancy_R"],
            "avg_planned_rr": d["avg_planned_rr"],
            "avg_win_R": d["avg_win_R"],
            "avg_loss_R": d["avg_loss_R"],
            "exit_sl": d["exit_sl"], "exit_tp": d["exit_tp"], "exit_other": d["exit_other"],
            "wins": d["wins"], "losses": d["losses"],
        }
    return rows


def reason_table(j, side):
    jr = j.get("journal", {})
    out = {}
    for k, v in jr.items():
        if k.startswith("block.%s." % side):
            out["BLOCK " + k.split(".", 2)[2]] = v
        elif k.startswith("reject.%s." % side):
            out["REJECT stage " + k.split(".", 2)[2]] = v
    if not out:                                          # v1.11 journal: free-text reasons per bar
        for k, v in jr.items():
            if k.startswith("why.%s." % side):
                out[k.split(".", 2)[2]] = v
    return sorted(out.items(), key=lambda kv: -kv[1])


def trade_span(csv_path):
    """(first entry time, last entry time) of a trades CSV, or ('-', '-')."""
    if not os.path.isfile(csv_path):
        return "-", "-"
    first = last = None
    with open(csv_path, "r", encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
        if "open_time" not in header:
            return "-", "-"
        col = header.index("open_time")
        for line in fh:
            parts = line.split(",")
            if len(parts) <= col:
                continue
            if first is None:
                first = parts[col]
            last = parts[col]
    return (first or "-"), (last or "-")


def why_count(j, side, needle):
    """Bars of a v1.11 journal whose free-text rejection reason contains `needle`."""
    return sum(v for k, v in j.get("journal", {}).items()
               if k.startswith("why.%s." % side) and needle in k)


def render_report(out_dir, results):
    lines = []
    w = lines.append
    w("# QATS backtest study - generated by tools/qats_backtest.py")
    w("")
    w("**Simulation, not the MT5 Strategy Tester and not broker execution.** The EA source is built by")
    w("the host compiler against the typed MQL5 shim and replayed against `tools/qats_sim/`. Fill model:")
    w("four quotes per M1 bar, server-side stops fill at their level (at the quote on a gap), 5 points of")
    w("adverse slippage on every stop-loss fill, no commission, no swap. Server clock = New-York-close")
    w("(UTC+2 / UTC+3), the operator's broker convention. Symbol: 2 digits, 100 oz contract, min lot 0.01.")
    w("")
    w("Dataset: `%s` @ `%s` (M1 bid+ask, UTC, 2016-09-01 .. 2026-09-01; first 5 months are warm-up)."
      % (DATASET["repo"], DATASET["commit"][:12]))
    w("")
    w("| window | from | to | role |")
    w("|---|---|---|---|")
    for key, name, a, b in PERIODS:
        w("| %s | %s | %s | %s |" % (key, a, b, name))
    w("")
    w("\"Signal study\" rows switch off ONLY the two breakers that end a run (equity drawdown halt, daily")
    w("loss lock) and use a 1,000,000 balance so the minimum lot never decides; every other guard is on.")
    w("They measure the SIGNAL over the whole window. \"ALL guards on\" rows are what an account would")
    w("have lived through: the compiled default inputs, or `%s`, on a 10,000 account." % PRESET_REL)
    w("The equity drawdown halt is a latch - once it trips, the EA sends nothing until an operator resets")
    w("it - so those rows END at the halt; the table \"Account-level runs\" gives the date.")
    w("")
    w("The out-of-sample window was not used while the engine was designed. Nothing in this report is a")
    w("forecast: a simulation on one-minute bars cannot reproduce a broker's ticks, slippage or costs.")
    w("")
    for pkey, pname, a, b in PERIODS:
        w("## %s (%s .. %s)" % (pname.capitalize(), a, b))
        w("")
        w("| configuration | dir | setups detected | eligible bars | executed | win rate | profit factor | expectancy (R) | avg planned R:R | net | max DD |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for key, title, source, sets, balance, spread, study in STUDY:
            j = results.get((key, pkey))
            if not j:
                continue
            rows = direction_rows(j)
            for side in ("BUY", "SELL"):
                r = rows[side]
                det = "n/a" if r["detected"] is None else str(r["detected"])
                w("| %s | %s | %s | %d | %d | %s | %.2f | %+.3f | %.2f | %+.0f | %s |"
                  % (title if side == "BUY" else "", side, det, r["eligible_bars"], r["executed"],
                     pct(r["win_rate"]), r["profit_factor"], r["expectancy_R"], r["avg_planned_rr"], r["net"],
                     ("%.1f%%" % j["max_drawdown_pct"]) if side == "BUY" else ""))
            a_ = j["all"]
            w("| | **both** | | | **%d** | **%s** | **%.2f** | **%+.3f** | %.2f | %+.0f | |"
              % (a_["trades"], pct(a_["win_rate"]), a_["profit_factor"], a_["expectancy_R"], a_["avg_planned_rr"], a_["net"]))
        w("")
        w("Execution: entry orders sent / accepted / failed, and simulator diagnostics.")
        w("")
        w("| configuration | bars analysed | entries sent | accepted | execution failures | format errors | API misuse |")
        w("|---|---|---|---|---|---|---|")
        for key, title, source, sets, balance, spread, study in STUDY:
            j = results.get((key, pkey))
            if not j:
                continue
            w("| %s | %d | %d | %d | %d | %d | %d |"
              % (title, journal(j, "bars"), j["entry_orders_sent"], j["entry_orders_accepted"], j["execution_failures"],
                 j["format_errors"], j["api_errors"]))
        w("")
        w("### Account-level runs (all guards on) - %s" % pkey)
        w("")
        w("| configuration | closed trades | first entry | last entry | end balance | max DD | setups blocked by DRAWDOWN_HALT (BUY / SELL) | by DAILY_LOSS_LOCK (BUY / SELL) |")
        w("|---|---|---|---|---|---|---|---|")
        for key in ACCOUNT_RUNS:
            j = results.get((key, pkey))
            if not j:
                continue
            title = [t for k, t, *_ in STUDY if k == key][0]
            first, last = trade_span(os.path.join(out_dir, "%s_%s_trades.csv" % (key, pkey)))
            if j["ea_version"] == "1.11":                # v1.11 journal: free text, one line per bar
                halt = "%d / %d bars" % (why_count(j, "BUY", "DRAWDOWN"), why_count(j, "SELL", "DRAWDOWN"))
                lock = "%d / %d bars" % (why_count(j, "BUY", "DAILY LOSS"), why_count(j, "SELL", "DAILY LOSS"))
            else:
                halt = "%d / %d" % (journal(j, "block.BUY.DRAWDOWN_HALT"), journal(j, "block.SELL.DRAWDOWN_HALT"))
                lock = "%d / %d" % (journal(j, "block.BUY.DAILY_LOSS_LOCK"), journal(j, "block.SELL.DAILY_LOSS_LOCK"))
            w("| %s | %d | %s | %s | %.2f | %.1f%% | %s | %s |"
              % (title, j["all"]["trades"], first, last, j["balance_end"], j["max_drawdown_pct"], halt, lock))
        w("")
        for key in ("bal", "v111", "bal_prod", "bal_preset"):
            j = results.get((key, pkey))
            if not j:
                continue
            title = [t for k, t, *_ in STUDY if k == key][0]
            w("### Why eligible signals were not executed - %s, %s" % (title, pkey))
            w("")
            w("| direction | reason | count |")
            w("|---|---|---|")
            for side in ("BUY", "SELL"):
                for reason, n in reason_table(j, side)[:8]:
                    w("| %s | %s | %d |" % (side, reason.replace("|", "/"), n))
            w("")
            w("Counts are `[QATS][BLOCK][REASON]` / `[QATS][EXECUTION][REJECTED]` records for v1.20 (one per")
            w("setup and reason set) and rejected bars for v1.11 (one per M5 bar).")
            w("")
        j = results.get(("bal", pkey))
        if j:
            w("### Net result by calendar year - v1.20 BALANCED signal study, %s" % pkey)
            w("")
            w("| year | closed trades | net |")
            w("|---|---|---|")
            for y, v in sorted(j["by_year"].items()):
                w("| %s | %d | %+.0f |" % (y, v["trades"], v["net"]))
            w("")
    mirror_path = os.path.join(out_dir, "mirror.json")
    if os.path.isfile(mirror_path):
        mj = load_json(mirror_path)
        w("## Direction symmetry on real data")
        w("")
        w("The same year of real prices is replayed twice: as recorded, and mirrored (price -> K - price, bid")
        w("and ask swapped, on an integer price grid so that both runs round identically). An engine that")
        w("treats the two directions alike must turn every BUY of the first run into a SELL of the second,")
        w("with the same volume and the same profit, and finish on the same balance.")
        w("")
        w("| build | exact mirror | BUY / SELL trades | BUY / SELL trades, mirrored feed | end balance | end balance, mirrored feed | bars compared | bars that differ | trades that differ |")
        w("|---|---|---|---|---|---|---|---|---|")
        for source in ("ea", "baseline"):
            r = mj.get(source)
            if not r:
                continue
            w("| v%s | **%s** | %d / %d | %d / %d | %.2f | %.2f | %s | %s | %s |"
              % (r["ea_version"], "YES" if r["exact_mirror"] else "NO", r["buy_trades"], r["sell_trades"],
                 r["mirror_buy_trades"], r["mirror_sell_trades"], r["balance_end"], r["balance_end_mirror"],
                 r.get("bars_compared", "n/a"), r.get("bar_mismatches", "n/a"), r.get("trade_mismatches", "n/a")))
        w("")
        w("\"Bars compared\" = every analysed M5 bar: the BUY score of the first run must equal the SELL score of")
        w("the second, with mirrored evidence and the same outcome. v1.11 prints one score per bar, so only its")
        w("totals can be compared - and they do not mirror.")
        w("")
    w("## How to reproduce")
    w("")
    w("```")
    w("python3 tools/qats_backtest.py fetch --dest /path/to/xau_m1")
    w("python3 tools/qats_backtest.py study --data /path/to/xau_m1 --out out/qats_backtest")
    w("python3 tools/qats_backtest.py mirror --data /path/to/xau_m1 --from 2019-01-01 --to 2020-01-01 --baseline --out out/qats_backtest")
    w("python3 tools/qats_backtest.py report --dir out/qats_backtest")
    w("```")
    w("")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "REPORT.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def collect_results(out_dir):
    results = {}
    for key, *_ in STUDY:
        for pkey, *_p in PERIODS:
            path = os.path.join(out_dir, "%s_%s.json" % (key, pkey))
            if os.path.isfile(path):
                results[(key, pkey)] = load_json(path)
    return results


def cmd_study(args):
    os.makedirs(args.out, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None
    exes = {}
    jobs = []
    for key, title, source, sets, balance, spread, study in STUDY:
        if only and key not in only:
            continue
        if source not in exes:
            exes[source] = build_binary(source)
        for pkey, pname, a, b in PERIODS:
            json_path = os.path.join(args.out, "%s_%s.json" % (key, pkey))
            if os.path.isfile(json_path) and not args.force:
                continue
            allsets = dict(SIGNAL_STUDY) if study else {}
            allsets.update(load_preset() if sets == "PRESET" else sets)
            label = "%s | %s %s..%s | spread %s | balance %d%s" % (title, pkey, a, b, spread, balance,
                                                                  " | signal study" if study else " | all guards on")
            cmd = run_replay(exes[source], args.data, a, b, json_path, allsets, spread, balance, label,
                             trades=os.path.join(args.out, "%s_%s_trades.csv" % (key, pkey)))
            jobs.append((key + "_" + pkey, cmd))
    running = []
    failed = 0
    while jobs or running:
        while jobs and len(running) < max(1, args.jobs):
            name, cmd = jobs.pop(0)
            print("start %s" % name)
            sys.stdout.flush()
            running.append((name, subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)))
        still = []
        for name, proc in running:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                still.append((name, proc))
                continue
            err = proc.stderr.read().decode("utf-8", "replace").strip()
            if proc.returncode != 0:
                failed += 1
                print("FAILED %s rc=%d %s" % (name, proc.returncode, err[:300]))
            else:
                print("done  %s" % name)
            sys.stdout.flush()
        running = still
    results = collect_results(args.out)
    render_report(args.out, results)
    print("report: %s" % os.path.join(args.out, "REPORT.md"))
    return 1 if failed else 0


def cmd_report(args):
    results = collect_results(args.dir)
    if not results:
        raise SystemExit("no study results in %s" % args.dir)
    sys.stdout.write(render_report(args.dir, results))
    return 0


def cmd_run(args):
    exe = build_binary("baseline" if args.baseline else "ea")
    sets = dict(SIGNAL_STUDY) if args.signal_study else {}
    for kv in args.set or []:
        k, v = kv.split("=", 1)
        sets[k] = v
    json_path = args.json or os.path.join(Q.OUT_DIR, "run.json")
    extra = []
    if args.int_grid:
        extra.append("--int-grid")
    if args.mirror:
        extra.append("--mirror")
    cmd = run_replay(exe, args.data, getattr(args, "from"), args.to, json_path, sets, args.spread, args.balance,
                     args.label or "single run", trades=args.trades, log=args.log, extra=extra)
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        return proc.returncode
    sys.stdout.write(open(json_path).read())
    return 0


# ------------------------------------------------------------ mirror proof
SCORED_RE = re.compile(r"\[QATS\]\[SIGNAL\]\[SCORED\]")


def parse_scored(path):
    """bar -> the fields of its scored record (dual-direction journal)."""
    out = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            i = line.find("[QATS][SIGNAL][SCORED]")
            if i < 0:
                continue
            s = line[i:]
            bar = re.search(r"bar=(\S+ \S+)", s).group(1)

            def g(key):
                return re.search(key + r"=(\S+)", s).group(1)
            parts = s.split(" | ")
            out[bar] = {
                "buy": int(g("BUY").split("/")[0]), "sell": int(g("SELL").split("/")[0]),
                "cand": g("candidate"), "outcome": g("outcome"), "reason": g("reason"), "eligible": g("eligible"),
                "buy_points": re.sub(r"\([^)]*\)", "", re.search(r"\[(.*?)\]", parts[2]).group(1)),
                "sell_points": re.sub(r"\([^)]*\)", "", re.search(r"\[(.*?)\]", parts[3]).group(1)),
            }
    return out


def compare_mirror(log_a, log_b, trades_a, trades_b, mirror_k):
    """Bar-by-bar and trade-by-trade comparison of a replay and its mirrored twin."""
    swap = {"BUY": "SELL", "SELL": "BUY", "NONE": "NONE"}
    a, b = parse_scored(log_a), parse_scored(log_b)
    bar_mismatch, sum_violation = 0, 0
    examples = []
    for bar, x in a.items():
        y = b.get(bar)
        ok = (y is not None and x["buy"] == y["sell"] and x["sell"] == y["buy"] and swap[x["cand"]] == y["cand"] and
              x["outcome"] == y["outcome"] and x["reason"] == y["reason"] and x["eligible"] == y["eligible"] and
              x["buy_points"] == y["sell_points"] and x["sell_points"] == y["buy_points"])
        if not ok:
            bar_mismatch += 1
            if len(examples) < 3:
                examples.append((bar, x, y))
        for side in ("buy", "sell"):
            pts = sum(int(tok.split(":")[1]) for tok in x[side + "_points"].split())
            if pts != x[side]:
                sum_violation += 1
    ta = list(csv.DictReader(open(trades_a)))
    tb = list(csv.DictReader(open(trades_b)))
    trade_mismatch = abs(len(ta) - len(tb))
    for x, y in zip(ta, tb):
        ok = (x["open_time"] == y["open_time"] and x["close_time"] == y["close_time"] and
              x["direction"] != y["direction"] and x["volume"] == y["volume"] and x["net"] == y["net"] and
              x["exit"] == y["exit"] and
              abs(float(x["open_price"]) + float(y["open_price"]) - mirror_k) < 1e-6 and
              abs(float(x["sl"]) + float(y["sl"]) - mirror_k) < 1e-6 and
              abs(float(x["tp"]) + float(y["tp"]) - mirror_k) < 1e-6)
        if not ok:
            trade_mismatch += 1
    return {
        "bars_compared": len(a), "bars_only_in_mirror": len(set(b) - set(a)), "bar_mismatches": bar_mismatch,
        "score_sum_violations": sum_violation, "trades": len(ta), "trades_mirror": len(tb),
        "trade_mismatches": trade_mismatch,
        "buy_trades": sum(1 for t in ta if t["direction"] == "BUY"),
        "sell_trades": sum(1 for t in ta if t["direction"] == "SELL"),
        "mirror_buy_trades": sum(1 for t in tb if t["direction"] == "BUY"),
        "mirror_sell_trades": sum(1 for t in tb if t["direction"] == "SELL"),
        "examples": examples,
    }


def mirror_check(exe, start, end, out_dir, data_dir=None, files=None, sets=None, tag="mirror", spread="fixed:25"):
    """Run a replay and its mirror on the integer price grid; return the comparison."""
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    procs = []
    for side, flag in (("orig", []), ("mirr", ["--mirror"])):
        base = os.path.join(out_dir, "%s_%s" % (tag, side))
        paths[side] = base
        cmd = run_replay(exe, data_dir, start, end, base + ".json", sets, spread, 1000000,
                         "%s %s" % (tag, side), trades=base + "_trades.csv", log=base + ".log",
                         extra=["--int-grid"] + flag, files=files)
        procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
    for p in procs:
        p.wait()
        if p.returncode != 0:
            raise SystemExit("mirror replay failed: " + p.stderr.read().decode("utf-8", "replace")[:300])
    ja, jb = load_json(paths["orig"] + ".json"), load_json(paths["mirr"] + ".json")
    has_scored = "scored.BUY.sum" in ja.get("journal", {})
    result = {"ea_version": ja["ea_version"], "balance_end": ja["balance_end"], "balance_end_mirror": jb["balance_end"],
              "buy": ja["buy"], "sell": ja["sell"], "mirror_buy": jb["buy"], "mirror_sell": jb["sell"],
              "format_errors": ja["format_errors"] + jb["format_errors"], "api_errors": ja["api_errors"] + jb["api_errors"],
              "critical": (ja["critical"] + jb["critical"]).strip()}
    if has_scored:
        result.update(compare_mirror(paths["orig"] + ".log", paths["mirr"] + ".log",
                                     paths["orig"] + "_trades.csv", paths["mirr"] + "_trades.csv", 1000000))
    else:                                               # v1.11: compare the aggregates only
        result.update({"trades": ja["all"]["trades"], "trades_mirror": jb["all"]["trades"],
                       "buy_trades": ja["buy"]["trades"], "sell_trades": ja["sell"]["trades"],
                       "mirror_buy_trades": jb["buy"]["trades"], "mirror_sell_trades": jb["sell"]["trades"]})
    result["exact_mirror"] = (
        ja["buy"]["trades"] == jb["sell"]["trades"] and ja["sell"]["trades"] == jb["buy"]["trades"] and
        abs(ja["buy"]["net"] - jb["sell"]["net"]) < 0.005 and abs(ja["sell"]["net"] - jb["buy"]["net"]) < 0.005 and
        abs(ja["balance_end"] - jb["balance_end"]) < 0.005 and
        result.get("bar_mismatches", 0) == 0 and result.get("trade_mismatches", 0) == 0)
    if not args_keep_logs():
        for side in ("orig", "mirr"):
            try:
                os.remove(paths[side] + ".log")
            except OSError:
                pass
    return result


_KEEP_LOGS = [False]


def args_keep_logs():
    return _KEEP_LOGS[0]


def cmd_mirror(args):
    _KEEP_LOGS[0] = args.keep_logs
    out_dir = args.out or os.path.join(Q.OUT_DIR, "mirror")
    report = {}
    for source in (["ea", "baseline"] if args.baseline else ["ea"]):
        exe = build_binary(source)
        r = mirror_check(exe, getattr(args, "from"), args.to, out_dir, data_dir=args.data,
                         sets=dict(SIGNAL_STUDY), tag="mirror_" + source)
        r.pop("examples", None)
        report[source] = r
        print("%s (v%s): exact mirror = %s | trades BUY/SELL %d/%d -> mirrored BUY/SELL %d/%d | "
              "balance %.2f vs %.2f | bar mismatches %s | trade mismatches %s"
              % (source, r["ea_version"], r["exact_mirror"], r["buy_trades"], r["sell_trades"],
                 r["mirror_buy_trades"], r["mirror_sell_trades"], r["balance_end"], r["balance_end_mirror"],
                 r.get("bar_mismatches", "n/a"), r.get("trade_mismatches", "n/a")))
    with open(os.path.join(out_dir, "mirror.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    return 0 if report["ea"]["exact_mirror"] else 1


# ---------------------------------------------------- synthetic test market
def synthetic_m1(path, weeks=32, seed=20261111, start_price=2000.0):
    """A deterministic random-walk market in the dataset's CSV layout (for CI).

    Volatility clusters and follows an intraday profile, so the series has
    swings, impulses, sweeps and breaks of structure in BOTH directions. It is a
    test fixture, not a model of gold; no performance number is read from it.
    """
    rng = random.Random(seed)
    cents = int(round(start_price * 100))
    vol = 1.0
    t0 = 1704067200                                     # Monday 2024-01-01 00:00 UTC
    with open(path, "w") as fh:
        fh.write("timestamp,open_bid,high_bid,low_bid,close_bid,open_ask,high_ask,low_ask,close_ask,volume_bid,volume_ask\n")
        for week in range(weeks):
            drift = rng.choice((-1, 1)) * rng.uniform(0.0, 0.035)
            for minute in range(5 * 1440 - 180):
                ts = t0 + week * 7 * 86400 + minute * 60
                hour = (minute // 60) % 24
                session = 1.6 if 12 <= hour < 17 else (1.2 if 7 <= hour < 12 else 0.7)
                vol = 0.97 * vol + 0.03 * (1.0 + abs(rng.gauss(0.0, 1.6)))
                if rng.random() < 0.0015:
                    vol *= 3.0
                sigma = 9.0 * session * min(vol, 6.0)
                o = cents
                p = o
                hi = lo = o
                for _ in range(4):
                    p += int(round(rng.gauss(drift, sigma / 2.0)))
                    hi = max(hi, p)
                    lo = min(lo, p)
                c = max(p, 50000)
                cents = c
                spread = 25
                v = max(0.001, abs(rng.gauss(0.05, 0.03)) * session)
                d = ts
                days = d // 86400
                # civil date from days (UTC)
                z = days + 719468
                era = z // 146097
                doe = z - era * 146097
                yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
                y = yoe + era * 400
                doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
                mp = (5 * doy + 2) // 153
                dd = doy - (153 * mp + 2) // 5 + 1
                mm = mp + 3 if mp < 10 else mp - 9
                y += 1 if mm <= 2 else 0
                rem = d % 86400
                fh.write("%04d-%02d-%02d %02d:%02d:00,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.5f,%.5f\n"
                         % (y, mm, dd, rem // 3600, rem % 3600 // 60,
                            o / 100.0, hi / 100.0, lo / 100.0, c / 100.0,
                            (o + spread) / 100.0, (hi + spread) / 100.0, (lo + spread) / 100.0, (c + spread) / 100.0,
                            v, v))
    return path


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("fetch", help="download + verify the public XAUUSD M1 bid/ask history")
    p.add_argument("--dest", required=True)
    p = sub.add_parser("run", help="one replay")
    p.add_argument("--data", required=True)
    p.add_argument("--from", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--set", action="append")
    p.add_argument("--spread", default="scaled:0.5")
    p.add_argument("--balance", type=float, default=10000)
    p.add_argument("--signal-study", action="store_true")
    p.add_argument("--baseline", action="store_true", help="replay v1.11 instead of the working tree")
    p.add_argument("--int-grid", action="store_true")
    p.add_argument("--mirror", action="store_true")
    p.add_argument("--json")
    p.add_argument("--trades")
    p.add_argument("--log")
    p.add_argument("--label")
    p = sub.add_parser("study", help="the fixed IS/OOS matrix + REPORT.md")
    p.add_argument("--data", required=True)
    p.add_argument("--out", default=os.path.join(Q.OUT_DIR, "..", "qats_backtest"))
    p.add_argument("--only")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("mirror", help="direction-symmetry proof on real data")
    p.add_argument("--data", required=True)
    p.add_argument("--from", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--out")
    p.add_argument("--baseline", action="store_true", help="also show that v1.11 is NOT symmetric")
    p.add_argument("--keep-logs", action="store_true")
    p = sub.add_parser("report", help="re-render REPORT.md")
    p.add_argument("--dir", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "study":
        return cmd_study(args)
    if args.cmd == "mirror":
        return cmd_mirror(args)
    if args.cmd == "report":
        return cmd_report(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
