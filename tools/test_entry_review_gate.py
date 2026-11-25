#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUDIT-2026-11-25 / P1: the 12-condition entry review is a SAFETY GATE.

WHY THIS EXISTS
---------------
QSMC_AutoTrader.mq5 calls RunEntryReview() immediately before g_trade.Buy/Sell
and treats a non-empty return value as a refusal ("ENTRY REVIEW BLOCKED"). The
review re-reads account authorization, tick age, spread, session, daily cap,
open positions, geometry, RR-at-fill, broker stops level, size and opposite
exposure on the FINAL numbers. tools/test_signal_execution_profiles.py pins
that contract: "a failed review blocks the order and names the condition".

RunEntryReview() began with:

    if(!InpPrintEntryReview) return "";

so setting the PRINT switch to false disabled all twelve safety checks. A
logging input is not an execution authorization. This suite compiles the
shipped review bodies (ReviewName / ReviewLine / RunEntryReview) together with
the shipped QSMC_ExecutionRules.mqh and executes them with deterministic
terminal stubs. It proves that the verdict is identical with the print switch
on and off, for every one of the twelve failing conditions.

A pass here is NOT a MetaEditor compile and NOT a backtest. rc=77 means the
host has no C++ toolchain and the native half was NOT verified; the source
contracts still run and are reported separately.
"""
from __future__ import print_function

from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_toolchain as NT

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "MQL5/Experts/QSMC_AutoTrader.mq5"
RULES = ROOT / "MQL5/Include/QSMC/QSMC_ExecutionRules.mqh"

FAILURES = []
CHECKS = [0]


def check(cond, what):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(what)


ea = EA.read_text(encoding="utf-8", errors="replace")
rules = RULES.read_text(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Source contracts. These also hold when no compiler is available.
# ---------------------------------------------------------------------------
review = ea[ea.index("string RunEntryReview"):ea.index("void HandleSignal")]
review_line = ea[ea.index("void ReviewLine"):ea.index("string RunEntryReview")]

check("if(!InpPrintEntryReview) return \"\";" not in review,
      "the print switch must not early-return out of the review gate")
check("return first_fail;" in review,
      "the review returns the first failing condition")
for i, fn in enumerate(("QER_ClassOk", "QER_AccountOk", "QER_TickAgeOk",
                        "QER_SpreadOk", "QER_SessionOk", "QER_TradesTodayOk",
                        "QER_OpenPositionsOk", "QER_GeometryOk", "QER_RROk",
                        "QER_StopsOk", "QER_SizeOk", "QER_OppositeOk"), start=1):
    check(fn + "(" in review, "R%d calls %s" % (i, fn))
check(review.count("if(InpPrintEntryReview)") >= 2,
      "the BEGIN/END log lines are guarded by the print switch")
check("if(!InpPrintEntryReview) return;" in review_line,
      "ReviewLine is silenced by the print switch, not the verdict")
# The gate at the call site is unchanged: a failed review still blocks.
check('review_fail!=""' in ea and "ENTRY REVIEW BLOCKED: " in ea,
      "a failed review still blocks the order at the call site")

# ---------------------------------------------------------------------------
# Native behavioural half: execute the shipped bodies with stubbed terminal I/O.
# ---------------------------------------------------------------------------
PRELUDE = r'''
#include <string>
#include <vector>
#include <cmath>
#include <cassert>
#include <iostream>
#include <limits>
using std::string;
using datetime = long long;

struct SQsigSignal {
  datetime bar_time=1000; int dir=1; int cls=1; double score=80;
  double entry=100.0, sl=99.0, tp=103.0;
};
const int SYMBOL_TIME=1, SYMBOL_ASK=2, SYMBOL_BID=3, SYMBOL_POINT=4;
const int QSMC_AT_REVIEW_CHECKS=12;

// ---- shipped globals, driven by the harness -------------------------------
bool   InpPrintEntryReview=true;
int    InpMaxDataAgeSeconds=10;
int    InpMaxSpreadPoints=20;
double InpMaxSpreadFracOfStop=0.0;
double InpMinRRAtFill=0.0;
bool   InpCloseOnOpposite=false;
int    _Digits=3;
int    g_fail=-1;                 // which condition to break, -1 = all pass
double g_ask=100.100, g_bid=100.000, g_point=0.01;   // spread = 10.0 pts
long   g_now=100000, g_tick_time=100000;
int    g_trades_today=0, g_max_day=0, g_open_count=0, g_max_pos=3;
bool   g_session_open=true, g_stops_ok=true, g_class_allowed=true;

// ---- terminal / EA stubs (read-only, deterministic) -----------------------
template<class... A> void Print(A&&...) {}
template<class... A> string StringFormat(const char* f, A&&...) { return string(f); }
string IntegerToString(long v) { return std::to_string(v); }
string DoubleToString(double v, int) { return std::to_string(v); }
string SignalKey(datetime t, int d) { return std::to_string(t) + "|" + std::to_string(d); }
string DirText(int d) { return d > 0 ? "BUY" : "SELL"; }
string ClassName(int) { return "STRONG"; }
double RiskMultiplierForClass(int) { return 1.0; }
double ScaledRiskPercent(int) { return 0.50; }
double EffectiveRiskPercent() { return 0.50; }
bool MathIsValidNumber(double x) { return std::isfinite(x); }
bool ClassAllowed(int, string &why) {
  if(g_fail==0) { why="class refused"; return false; }
  return g_class_allowed;
}
string TradeEnvBlock(bool) { return g_fail==1 ? "REAL account without authorization" : ""; }
bool RealProfileActive() { return false; }
long TimeCurrent() { return g_now; }
long SymbolInfoInteger(string, int prop) {
  if(prop==SYMBOL_TIME) return (g_fail==2 ? g_now-999 : g_tick_time);
  return 0;
}
double SymbolInfoDouble(string, int prop) {
  if(prop==SYMBOL_ASK)  return (g_fail==3 ? 100.209 : g_ask);  // 20.9 pts
  if(prop==SYMBOL_BID)  return g_bid;
  if(prop==SYMBOL_POINT) return g_point;
  return 0.0;
}
bool SessionOpenNow(string &why) {
  if(g_fail==4) { why="outside session"; return false; }
  return g_session_open;
}
int MaxTradesPerDayNow() { return (g_fail==5 ? 3 : g_max_day); }
int TradesToday() { return (g_fail==5 ? 3 : g_trades_today); }
int MaxOpenPositionsNow() { return (g_fail==6 ? 1 : g_max_pos); }
int OpenCount(string) { return (g_fail==6 ? 1 : g_open_count); }
bool StopsDistanceOK(string, double, double, double) {
  return (g_fail==9 ? false : g_stops_ok);
}
double MathAbs(double x) { return std::fabs(x); }
double MathMax(double a, double b) { return std::fmax(a, b); }
'''

TESTS = r'''
static int fails=0;
#define CHECK(cond, what) do { if(!(cond)) { std::cout << "FAIL " << what << "\n"; ++fails; } } while(0)

static string Run(const bool print_on, const int fail,
                  const double lots, const ulong opposite,
                  const double sl, const double tp, const double min_rr)
  {
   InpPrintEntryReview=print_on;
   g_fail=fail;
   InpMinRRAtFill=min_rr;
   SQsigSignal s;
   s.sl=sl; s.tp=tp;
   return RunEntryReview(s,"XAUUSD",100.0,lots,opposite,true);
  }

int main()
  {
   const string expect[12] = {
     "R1  CLASS", "R2  ACCOUNT", "R3  TICK_AGE", "R4  SPREAD",
     "R5  SESSION", "R6  TRADES_TODAY", "R7  OPEN_POSITIONS", "R8  GEOMETRY",
     "R9  RR_AT_FILL", "R10 STOPS_LEVEL", "R11 RISK_SIZE", "R12 NO_OPPOSITE"
   };
   // A healthy review is READY with the log on AND with the log off.
   CHECK(Run(true,  -1, 0.10, 0, 99.0, 103.0, 0.0)=="",
         "all conditions pass with printing ON");
   CHECK(Run(false, -1, 0.10, 0, 99.0, 103.0, 0.0)=="",
         "all conditions pass with printing OFF");

   // Force each condition to fail in turn. The verdict must be non-empty and
   // IDENTICAL with the print switch on and off. Before the fix the "OFF"
   // verdict was always "" (the whole gate was skipped).
   for(int i=0;i<12;i++)
     {
      double lots=0.10, sl=99.0, tp=103.0, min_rr=0.0;
      ulong opposite=0;
      if(i==7)  sl=101.0;               // R8 buy stop above price
      if(i==8)  min_rr=99.0;            // R9 impossible RR floor
      if(i==10) lots=0.0;               // R11 no size
      if(i==11) opposite=12345;         // R12 opposite not allowed
      string on =Run(true,  i, lots, opposite, sl, tp, min_rr);
      string off=Run(false, i, lots, opposite, sl, tp, min_rr);
      CHECK(on==expect[i], "condition " + std::to_string(i) + " fails by name with printing ON");
      CHECK(off==on,       "condition " + std::to_string(i) + " verdict is unchanged with printing OFF");
      CHECK(off!="",       "condition " + std::to_string(i) + " is NOT bypassed with printing OFF");
     }

   // R4 must also refuse a fractional spread above the cap and a NaN quote,
   // with the print switch off (the int-cast defect reproduced in the audit).
   InpMaxSpreadFracOfStop=0.0;
   CHECK(Run(false, 3, 0.10, 0, 99.0, 103.0, 0.0)=="R4  SPREAD",
         "20.9 pts against a 20-pt cap is refused with printing OFF");
   // A disabled absolute cap must not veto; the review agrees with SpreadOK().
   InpMaxSpreadPoints=0;
   CHECK(Run(false, -1, 0.10, 0, 99.0, 103.0, 0.0)=="",
         "a disabled absolute spread cap does not veto");
   InpMaxSpreadPoints=20;
   g_ask=std::numeric_limits<double>::quiet_NaN();
   CHECK(Run(false, -1, 0.10, 0, 99.0, 103.0, 0.0)=="R4  SPREAD",
         "a NaN quote fails closed with printing OFF");

   if(fails!=0) { std::cout << fails << " FAILED\n"; return 1; }
   std::cout << "PASS entry review gate: 12 conditions evaluated with the print switch ON and OFF\n";
   return 0;
  }
'''


def main():
    # Source contracts first (compiler-independent).
    for f in FAILURES:
        print("  FAILED (source contract): " + f)
    native_failed = False
    cxx = NT.compiler(sanitizers=True)
    if cxx is None:
        NT.skip("native subset: entry-review gate (12 conditions)", sanitizers=True)
    else:
        rules_native = rules.replace("string &keys[]", "std::vector<string> &keys")
        region = ea[ea.index("string ReviewName"):ea.index("void HandleSignal")]
        with tempfile.TemporaryDirectory(prefix="qsmc-review-gate-") as d:
            cpp = Path(d) / "review_gate.cpp"
            exe = Path(d) / "review_gate"
            cpp.write_text(PRELUDE + rules_native + "\n" + region + "\n" + TESTS)
            build = subprocess.run(
                [cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                 str(cpp), "-o", str(exe)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if build.returncode:
                print(build.stdout.strip()[:4000])
                FAILURES.append("native harness failed to build the shipped review bodies")
            else:
                run = subprocess.run([str(exe)], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)
                print(run.stdout.strip()[:4000])
                if run.returncode:
                    native_failed = True
                    FAILURES.append("native entry-review gate returned rc=%d" % run.returncode)

    print("-" * 74)
    print("entry-review-gate checks: %d, failures: %d" % (CHECKS[0], len(FAILURES)))
    if native_failed or FAILURES:
        return 1
    print("Entry review is a gate, not a print option. NOT a MetaEditor compile or backtest.")
    return NT.exit_code(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
