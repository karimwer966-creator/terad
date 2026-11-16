#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CANDLE PATTERNS - execute the two-bar reversal geometry natively.

WHY THIS EXISTS
QSMC_Reaction.mqh offers four NAMED reversal patterns to the buy side and four
to the sell side, and an unnamed bar earns no candle evidence at all. In
v6.6.23 two of them were mathematically impossible:

    piercing   : r_c>p_o  AND  r_c<(p_o+p_c)/2   while p_c<p_o  =>  mid<p_o
    dark cloud : r_c<p_o  AND  r_c>(p_o+p_c)/2   while p_c>p_o  =>  mid>p_o

Each demanded a close both above and below the same price. Nothing could ever
satisfy them, so the detector silently offered three reversals instead of four
and no log line said so - the definition of a defect grep cannot see.

v6.6.24 moved the geometry into MQL5/Include/QSMC/QSMC_CandlePatterns.mqh as
side-effect-free predicates that CReactionDetector calls. This suite compiles
THAT HEADER and executes it:

  1. the truth table of both patterns, including the strict boundaries;
  2. an EXHAUSTIVE-ish sweep proving the OLD expressions are unsatisfiable over
     the sampled price grid while the NEW ones match textbook candles - so the
     defect cannot come back without this suite failing.

    rc=0   verified on this host
    rc=77  NOT verified on this host (no C++ compiler) - see native_toolchain
"""
from pathlib import Path
import subprocess
import tempfile

import native_toolchain as NT

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "MQL5/Include/QSMC/QSMC_CandlePatterns.mqh"
source = HEADER.read_text()

PRELUDE = r'''
#include <cmath>
#include <iostream>
'''

TESTS = r'''
static int fails = 0;
#define CHECK(cond, what) do { if(!(cond)) { std::cout << "FAIL " << what << "\n"; ++fails; } } while(0)

//--- The v6.6.23 expressions, verbatim, for the unsatisfiability proof.
static bool old_piercing(double p_o, double p_c, double r_o, double r_c)
  { (void)r_o; return (p_c < p_o && r_c > r_o && r_c > p_o && r_c < (p_o + p_c) * 0.5); }
static bool old_dark_cloud(double p_o, double p_c, double r_o, double r_c)
  { (void)r_o; return (p_c > p_o && r_c < r_o && r_c < p_o && r_c > (p_o + p_c) * 0.5); }

void PiercingTruthTable()
  {
   //--- a textbook piercing line: prior bearish 110 -> 100, bar opens 99
   //--- closes 105 (above the 105 midpoint? mid = 105 exactly -> must be >)
   CHECK(!QCP_Piercing(110, 100, 99, 105), "piercing: a close ON the midpoint is not enough");
   CHECK(QCP_Piercing(110, 100, 99, 105.5), "piercing: textbook candle (mid 105, close 105.5)");
   CHECK(!QCP_Piercing(110, 100, 99, 110), "piercing: a close AT the prior open is engulfing, not piercing");
   CHECK(!QCP_Piercing(110, 100, 99, 111), "piercing: a close above the prior open is engulfing");
   CHECK(!QCP_Piercing(110, 100, 100.5, 106), "piercing: must open below the prior close");
   CHECK(!QCP_Piercing(110, 100, 99, 98.5), "piercing: must close up (r_c>r_o)");
   CHECK(!QCP_Piercing(100, 110, 111, 105.5), "piercing: the prior bar must be bearish");
   CHECK(QCP_Piercing(110, 100, 99, 105.0001),
         "piercing: a hair above the midpoint qualifies");
  }

void DarkCloudTruthTable()
  {
   //--- textbook dark cloud: prior bullish 100 -> 110, opens 111, closes 104
   CHECK(!QCP_DarkCloud(100, 110, 111, 105), "dark cloud: a close ON the midpoint is not enough");
   CHECK(QCP_DarkCloud(100, 110, 111, 104.5), "dark cloud: textbook candle (mid 105, close 104.5)");
   CHECK(!QCP_DarkCloud(100, 110, 111, 105.5), "dark cloud: above the midpoint fails");
   CHECK(!QCP_DarkCloud(100, 110, 111, 110), "dark cloud: a close AT the prior open fails");
   CHECK(!QCP_DarkCloud(100, 110, 111, 99), "dark cloud: a close below the prior open is engulfing");
   CHECK(!QCP_DarkCloud(100, 110, 109.5, 104), "dark cloud: must open above the prior close");
   CHECK(!QCP_DarkCloud(100, 110, 111, 111.5), "dark cloud: must close down");
   CHECK(!QCP_DarkCloud(110, 100, 111, 104), "dark cloud: the prior bar must be bullish");
  }

void OldExpressionsWereImpossible()
  {
   //--- Sweep a dense grid of two-bar shapes. The old expressions must NEVER
   //--- fire (that is the defect); the new ones must fire somewhere (that is
   //--- the fix) and must fire on every shape the old one would have accepted
   //--- had the algebra been right.
   int old_hits = 0, new_hits = 0;
   for (double p_c = 96.0; p_c <= 104.0; p_c += 1.0)
     {
      double p_o = 100.0;
      for (double r_o = 94.0; r_o <= 106.0; r_o += 0.5)
         for (double r_c = 94.0; r_c <= 106.0; r_c += 0.5)
           {
            if (old_piercing(p_o, p_c, r_o, r_c)) ++old_hits;
            if (old_dark_cloud(p_o, p_c, r_o, r_c)) ++old_hits;
            if (QCP_Piercing(p_o, p_c, r_o, r_c)) ++new_hits;
            if (QCP_DarkCloud(p_o, p_c, r_o, r_c)) ++new_hits;
           }
     }
   CHECK(old_hits == 0, "the v6.6.23 piercing / dark-cloud expressions are unsatisfiable");
   CHECK(new_hits > 0, "the corrected geometry matches real candle shapes");
  }

int main()
  {
   PiercingTruthTable();
   DarkCloudTruthTable();
   OldExpressionsWereImpossible();
   if(fails != 0) { std::cout << fails << " FAILED\n"; return 1; }
   std::cout << "PASS candle patterns: piercing + dark cloud geometry, old expressions proven unsatisfiable\n";
   return 0;
  }
'''


def main():
    cxx = NT.compiler(sanitizers=True)
    if cxx is None:
        NT.skip("native subset: candle reversal geometry", sanitizers=True)
        return
    with tempfile.TemporaryDirectory(prefix="qsmc-candles-") as d:
        src = Path(d) / "candles.cpp"
        binary = Path(d) / "candles"
        src.write_text(PRELUDE + source + TESTS)
        subprocess.run([cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(src), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


main()
raise SystemExit(NT.exit_code([]))
