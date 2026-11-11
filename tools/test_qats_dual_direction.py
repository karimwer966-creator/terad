#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QATS-DUAL - BUY and SELL are detected, scored and executed by the same rules.

WHAT THIS RUNS
--------------
The REAL QuantumAutonomousTradingSystem.mq5 source, built by the host compiler
against the typed MQL5 shim (tools/qats_native.py), driven by the broker
simulator in tools/qats_sim/. Nothing here re-implements the EA in Python.

  1. UNIT        pure functions and the H1 engines on hand-built series:
                 weights, core gate, direction policy, structure (BOS / CHoCH),
                 liquidity (sweep, two-bar reclaim, breakout acceptance, failed
                 sweep, EQH / EQL, PDH / PDL, targets), displacement, OB, FVG -
                 each bullish case next to its bearish mirror image.
  2. INTEGRATION 45 scenarios, each in its own process, replayed tick by tick
                 through OnInit / OnTick / OnTradeTransaction: strong BUY and
                 strong SELL from detection to a closed position, the core gate
                 per profile, D1/H4 against H1, every rejection with its exact
                 reason, duplicate prevention, SL/TP validation, the cooldown
                 state machine, loss counting from deal history, restart, retry.
  3. MIRROR      every bullish scenario is replayed on the price-mirrored market
                 (price -> K - price, bid and ask swapped). The bearish twin must
                 be the exact mirror: same scores on the other side, same volume,
                 mirrored entry / SL / TP, same P/L.
  4. SYMMETRY    a 10-week random-walk market is replayed twice, straight and
                 mirrored, on an integer price grid. EVERY bar's BUY score must
                 equal the mirrored bar's SELL score and every trade must have
                 its mirrored twin. One mismatch fails the suite.
  5. MEMORY      the same scenarios under AddressSanitizer + UBSan with every
                 automatic variable poisoned (-ftrivial-auto-var-init=pattern)
                 must print the same results: no decision reads an
                 uninitialised field. Division by zero - integer or floating
                 point - is trapped too: MQL5 stops an EA on "zero divide".

WHAT IT DOES NOT PROVE
----------------------
NOT a MetaEditor compile, NOT the MT5 Strategy Tester, NOT broker execution, and
nothing about profitability. F7 and a DEMO run remain the human gates.

Exit code: 0 verified, 77 no host C++ compiler here, 1 verified and failed.
"""
from __future__ import print_function

import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qats_native as Q  # noqa: E402
import qats_backtest as BT  # noqa: E402

FAILURES = []
COUNT = [0]
MIRROR_K = 4000.00          # scenarios mirror at 400000 points on the 2-digit grid

MIRROR_PAIRS = [
    ("strong_buy", "strong_sell"),
    ("strong_buy_conservative", "strong_sell_conservative"),
    ("strong_buy_active", "strong_sell_active"),
    ("sweep_only_buy_conservative", "sweep_only_sell_conservative"),
    ("sweep_only_buy_balanced", "sweep_only_sell_balanced"),
    ("sweep_only_buy_active", "sweep_only_sell_active"),
    ("bos_only_buy_conservative", "bos_only_sell_conservative"),
    ("bos_only_buy_balanced", "bos_only_sell_balanced"),
    ("bos_only_buy_active", "bos_only_sell_active"),
    ("counter_trend_sell_gold", "counter_trend_buy_gold"),
    ("counter_trend_sell_other", "counter_trend_buy_other"),
]


def check(ok, label, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + label)
    else:
        print("FAIL  " + label + (("  [" + detail + "]") if detail else ""))
        FAILURES.append(label)


def run(exe, *args, **kw):
    proc = subprocess.run([exe] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, timeout=kw.get("timeout", 600))
    return proc.returncode, proc.stdout


def parse_result(out):
    for line in out.splitlines():
        if line.startswith("RESULT "):
            return dict(tok.split("=", 1) for tok in line.split()[1:] if "=" in tok)
    return None


def summary_counts(out):
    m = re.search(r"(\d+) checks, (\d+) failed", out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 1)


def main():
    if not Q.find_compiler():
        print("SKIP  qats-dual-direction: this host has no usable C++17 compiler (g++, c++, clang++)")
        print("      NOT verified here. The Linux CI run on every push has one.")
        return Q.SKIP_EXIT

    exe, rc, diag = Q.build(Q.EA_SOURCE, "dual")
    check(rc == 0 and exe is not None, "0  the EA builds against the MQL5 shim with the strict flag set", diag.strip()[:300])
    if not exe:
        return 1

    # ------------------------------------------------------------- 1. unit
    rc, out = run(exe, "selftest", "unit")
    checks, failed = summary_counts(out)
    for line in out.splitlines():
        if "FAIL" in line:
            print("      " + line.strip())
    check(rc == 0 and failed == 0 and checks >= 200,
          "1  unit: %d checks on weights, core gate, direction policy, structure, liquidity, zones (bullish + bearish)" % checks)

    # ------------------------------------------------------ 2. integration
    rc, listing = run(exe, "selftest", "--list")
    scenarios = [s for s in listing.split() if s]
    check(len(scenarios) >= 44, "2  %d integration scenarios are registered" % len(scenarios))
    results = {}
    total_checks = 0
    for name in scenarios:
        rc, out = run(exe, "selftest", name)
        checks, failed = summary_counts(out)
        total_checks += checks
        results[name] = parse_result(out)
        if rc != 0 or failed:
            for line in out.splitlines():
                if "FAIL" in line:
                    print("      " + line.strip())
        check(rc == 0 and failed == 0 and checks > 0, "2  scenario %-32s %3d checks" % (name, checks))
    print("      (%d scenario checks in total, each scenario in its own process)" % total_checks)

    # ----------------------------------------------------------- 3. mirror
    for a, b in MIRROR_PAIRS:
        ra, rb = results.get(a), results.get(b)
        if not ra or not rb:
            check(False, "3  mirror pair %s / %s produced results" % (a, b))
            continue
        fa = {k: float(ra[k]) for k in ("price", "sl", "tp", "volume", "net")}
        fb = {k: float(rb[k]) for k in ("price", "sl", "tp", "volume", "net")}
        traded = ra["dir"] != "NONE"
        ok = (ra["entries"] == rb["entries"] and ra["trades"] == rb["trades"] and
              ra["buyScore"] == rb["sellScore"] and ra["sellScore"] == rb["buyScore"] and
              abs(fa["volume"] - fb["volume"]) < 1e-9 and abs(fa["net"] - fb["net"]) < 0.005)
        if traded:
            ok = ok and ra["dir"] != rb["dir"] and rb["dir"] != "NONE"
            for k in ("price", "sl", "tp"):
                ok = ok and abs(fa[k] + fb[k] - MIRROR_K) < 0.0051
        else:
            ok = ok and rb["dir"] == "NONE"
        detail = "%s vs %s" % (ra, rb)
        what = ("%s %s @ %.2f SL %.2f TP %.2f  <->  %s @ %.2f SL %.2f TP %.2f"
                % (ra["dir"], ra["volume"], fa["price"], fa["sl"], fa["tp"], rb["dir"], fb["price"], fb["sl"], fb["tp"])
                if traded else "no trade on either side")
        check(ok, "3  %s is the exact mirror of %s (%s)" % (b, a, what), detail)

    # --------------------------------------------------------- 4. symmetry
    work = os.path.join(Q.OUT_DIR, "symmetry")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    synth = BT.synthetic_m1(os.path.join(work, "synthetic_m1.csv"))
    sym = BT.mirror_check(exe, "2024-06-03", "2024-08-12", work, files=[synth], sets=dict(BT.SIGNAL_STUDY), tag="synthetic")
    check(sym["bars_compared"] >= 10000, "4  symmetry replay scored %d bars" % sym["bars_compared"])
    # A resting LIMIT fills far less often than a market order, so the bar for
    # "not vacuous" is lower than the market entry's. It is still asserted, per
    # side, because a replay that trades nothing proves nothing.
    check(sym["buy_trades"] >= 2 and sym["sell_trades"] >= 2,
          "4  the replay is not vacuous: %d BUY and %d SELL trades" % (sym["buy_trades"], sym["sell_trades"]))
    check(sym["bar_mismatches"] == 0 and sym["bars_only_in_mirror"] == 0,
          "4  on EVERY bar the BUY score equals the mirrored SELL score, with mirrored evidence and outcome",
          "%d mismatching bars, e.g. %s" % (sym["bar_mismatches"], sym.get("examples", [])[:1]))
    check(sym["trade_mismatches"] == 0 and sym["trades"] == sym["trades_mirror"],
          "4  every trade has its mirrored twin: same times, volume and P/L, mirrored entry / SL / TP (%d trades)" % sym["trades"])
    check(sym["buy_trades"] == sym["mirror_sell_trades"] and sym["sell_trades"] == sym["mirror_buy_trades"],
          "4  BUY/SELL trade counts swap exactly: %d/%d -> %d/%d"
          % (sym["buy_trades"], sym["sell_trades"], sym["mirror_buy_trades"], sym["mirror_sell_trades"]))
    check(abs(sym["balance_end"] - sym["balance_end_mirror"]) < 0.005,
          "4  both replays end on the same balance (%.2f)" % sym["balance_end"])
    check(sym["score_sum_violations"] == 0, "4  on every bar the listed points add up to the printed score (no hidden component)")
    check(sym["format_errors"] == 0 and sym["api_errors"] == 0 and not sym["critical"],
          "4  no format-string mismatch, no API misuse, no critical error in either replay")

    # --------------------------------------------------------- 4b. file seam
    # The public dataset ships one file per year and the files OVERLAP at their
    # seams. Fed row by row the overlap sends the simulated clock backwards and
    # replays up to a day of quotes. The loader must skip a row that does not move
    # time forward: a market cut into two overlapping files replays exactly like
    # the same market in one file.
    parts = BT.split_with_overlap(synth, work, 24 * 7020 + 3000, repeated=300)
    seam = {}
    for tag, files in (("one", [synth]), ("two", parts)):
        path = os.path.join(work, "seam_%s.json" % tag)
        cmd = BT.run_replay(exe, None, "2024-06-03", "2024-07-08", path, dict(BT.SIGNAL_STUDY), "fixed:25", 1000000,
                            "seam " + tag, files=files)
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        seam[tag] = BT.load_json(path) if proc.returncode == 0 else {}
    one, two = seam["one"], seam["two"]
    check(bool(one) and bool(two) and one.get("m1_rows_skipped_repeated_at_a_file_seam") == 0
          and two.get("m1_rows_skipped_repeated_at_a_file_seam") == 300,
          "4b a market cut into two files that overlap by 300 rows: exactly those 300 repeated rows are skipped",
          "skipped %s / %s" % (one.get("m1_rows_skipped_repeated_at_a_file_seam"), two.get("m1_rows_skipped_repeated_at_a_file_seam")))
    same = [k for k in one if k not in ("m1_rows_skipped_repeated_at_a_file_seam", "label") and one[k] != two.get(k)]
    check(bool(one) and not same and one.get("all", {}).get("trades", 0) >= 1,
          "4b ... and the replay is identical to the one-file replay in every other field (%d M1 bars, %d ticks, %d trades, "
          "balance %.2f): the clock never runs backwards at a seam"
          % (one.get("m1_bars", 0), one.get("ticks", 0), one.get("all", {}).get("trades", 0), one.get("balance_end", 0.0)),
          "fields that differ: %s" % same[:6])
    shutil.rmtree(work, ignore_errors=True)

    # ----------------------------------------------------------- 5. memory
    san_flags = ["-fsanitize=address,undefined,float-divide-by-zero", "-ftrivial-auto-var-init=pattern"]
    if Q.supports_flags(san_flags):
        sexe, src_rc, sdiag = Q.build(Q.EA_SOURCE, "dual_san", optimize="-O1", sanitize=True,
                                      extra_flags=["-ftrivial-auto-var-init=pattern"])
        check(src_rc == 0 and sexe is not None, "5  sanitizer build (ASan + UBSan + zero-divide trap, automatic variables poisoned)", sdiag.strip()[:300])
        if sexe:
            rc, out = run(sexe, "selftest", "unit", timeout=900)
            checks, failed = summary_counts(out)
            check(rc == 0 and failed == 0, "5  unit suite is clean under the sanitizers (%d checks)" % checks,
                  "\n".join(l for l in out.splitlines() if "ERROR" in l or "runtime error" in l)[:400])
            diverged, dirty = [], []
            for name in scenarios:
                rc, out = run(sexe, "selftest", name, timeout=900)
                if rc != 0 or "runtime error" in out or "AddressSanitizer" in out:
                    dirty.append(name)
                if parse_result(out) != results.get(name):
                    diverged.append(name)
            check(not dirty, "5  all %d scenarios are clean under ASan + UBSan (no zero divide, no overflow, no bad read)" % len(scenarios), ", ".join(dirty[:6]))
            check(not diverged, "5  poisoned automatic variables change no result (no uninitialised read decides anything)",
                  ", ".join(diverged[:6]))
    else:
        print("NOTE  5  this compiler cannot link %s: the memory pass was NOT run here" % " ".join(san_flags))
        print("         (the Linux CI runner can; the functional passes above did run).")

    print("")
    print("-" * 74)
    print("qats-dual-direction: %d checked, %d failed" % (COUNT[0], len(FAILURES)))
    if FAILURES:
        for f in FAILURES:
            print("  FAILED: " + f)
        return 1
    print("BUY and SELL go through one code path and mirror each other exactly.")
    print("This is a host-compiled simulation of the real source: NOT MetaEditor, NOT the")
    print("Strategy Tester, NOT a broker, and it says nothing about profitability.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
