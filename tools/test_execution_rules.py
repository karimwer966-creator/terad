#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXECUTION-RULES - run the EA's breaker / review arithmetic natively.

WHY THIS EXISTS
---------------
QSMC_AutoTrader.mq5 decides things about money: where the daily floor is, when
a drawdown breaker trips, whether a cooldown is still running, and the twelve
conditions of RunEntryReview. Before v6.6.24 every one of those was an inline
expression inside a 4 700-line EA, which meant the only way to check it was to
attach the EA to a live account and watch. A boundary that is off by one
("eq<floor" instead of "eq<=floor") is invisible in that kind of testing and
expensive in production.

v6.6.24 moved the arithmetic into MQL5/Include/QSMC/QSMC_ExecutionRules.mqh as
side-effect-free functions, and the EA calls them. This suite compiles THAT
HEADER - the shipped text - with a host C++ compiler and executes it, so the
assertions below test the same code the terminal runs, not a copy of it.

The dialect adapter is deliberately tiny (MQL5 `string`/`datetime`/`ulong` and
an array parameter become std:: types). No decision logic is rewritten here.

A pass here is NOT an MQL5 compile and NOT a backtest. It is the arithmetic.

    rc=0   verified on this host
    rc=77  NOT verified on this host (no C++ compiler) - see native_toolchain
"""
from pathlib import Path
import subprocess
import tempfile

import native_toolchain as NT

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "MQL5/Include/QSMC/QSMC_ExecutionRules.mqh"

source = HEADER.read_text()
# MQL5 array parameters are references; the native harness spells that as a
# std::vector reference. Nothing else in the header needs translating.
source = source.replace("string &keys[]", "std::vector<string> &keys")

PRELUDE = r'''
#include <string>
#include <vector>
#include <cmath>
#include <cassert>
#include <iostream>
using std::string;
using datetime = long long;
// ulong already exists as unsigned long on glibc; MQL5's ulong is the same width.
'''

# Every assertion names the rule it pins and the boundary it walks over.
TESTS = r'''
static int fails = 0;
#define CHECK(cond, what) do { if(!(cond)) { std::cout << "FAIL " << what << "\n"; ++fails; } } while(0)

void DayBreakers()
  {
   //--- Day index: the server-day boundary is 00:00, not "24h since attach".
   CHECK(QER_DayIndex(0)==0, "day index of epoch");
   CHECK(QER_DayIndex(86399)==0, "day index just before midnight");
   CHECK(QER_DayIndex(86400)==1, "day index at midnight");
   CHECK(QER_DayIndex(-5)==0, "a negative stamp is clamped, never a negative day");
   CHECK(QER_DayIndex(86400*3)!=QER_DayIndex(86400*3-1), "rollover changes the index");

   //--- Money stop.
   CHECK(QER_DayStopMoney(0.0, 5000.0, 2.0)==0.0, "money stop off when the input is 0");
   CHECK(QER_DayStopMoney(-10.0, 5000.0, 2.0)==0.0, "a negative money input is off, not a credit");
   CHECK(QER_DayStopMoney(50.0, 5000.0, 2.0)==50.0, "money stop under the hard ceiling is used as typed");
   CHECK(QER_DayStopMoney(1000.0, 5000.0, 2.0)==100.0, "money stop is capped by the HARD percentage");
   CHECK(QER_DayStopMoney(1000.0, 0.0, 2.0)==1000.0, "no baseline: the input stands (nothing to cap against)");

   //--- Daily floor: money wins, disabled stays disabled.
   CHECK(QER_DayFloorEquity(0.0, 25.0, 0.5)==0.0, "no baseline means no floor");
   CHECK(QER_DayFloorEquity(5000.0, 25.0, 0.5)==4975.0, "money floor");
   CHECK(QER_DayFloorEquity(5000.0, 0.0, 0.5)==4975.0, "percent floor");
   CHECK(QER_DayFloorEquity(5000.0, 0.0, 0.0)==0.0,
         "a disabled percent stop is a 0.0 floor, NOT the hard ceiling");
   CHECK(QER_DayFloorEquity(5000.0, 25.0, 0.0)==4975.0, "money floor survives a disabled percent input");

   //--- Daily trigger boundary.
   CHECK(!QER_DailyTripped(4975.0, 4975.01), "one cent above the floor does not trip");
   CHECK(QER_DailyTripped(4975.0, 4975.0), "exactly on the floor trips");
   CHECK(QER_DailyTripped(4975.0, 4000.0), "below the floor trips");
   CHECK(!QER_DailyTripped(0.0, 1.0), "a 0.0 floor cannot trip");

   //--- Account drawdown breaker, measured from the high-water mark.
   CHECK(QER_DrawdownFloor(0.0, 3.0)==0.0, "no reference, no floor");
   CHECK(QER_DrawdownFloor(10000.0, 0.0)==0.0, "drawdown disabled means no floor");
   CHECK(QER_DrawdownFloor(10000.0, 3.0)==9700.0, "3% of 10000");
   CHECK(!QER_DrawdownTripped(10000.0, 3.0, 9700.01), "above the dd floor does not trip");
   CHECK(QER_DrawdownTripped(10000.0, 3.0, 9700.0), "exactly on the dd floor trips");
   CHECK(QER_DrawdownTripped(10000.0, 3.0, 9000.0), "below the dd floor trips");
   CHECK(!QER_DrawdownTripped(10000.0, 0.0, 1000.0), "disabled dd never trips");
   //--- the HWM must move the floor with it: a profit run raises the reference.
   CHECK(QER_DrawdownFloor(12000.0, 3.0) > QER_DrawdownFloor(10000.0, 3.0),
         "a higher HWM means a higher floor");

   //--- Consecutive losses.
   CHECK(!QER_LossStreakTripped(5, 0), "limit 0 disables the streak breaker");
   CHECK(!QER_LossStreakTripped(4, 5), "under the limit does not trip");
   CHECK(QER_LossStreakTripped(5, 5), "on the limit trips");
   CHECK(QER_LossStreakTripped(6, 5), "over the limit trips");

   //--- Post-loss cooldown, measured as the age of the most recent close.
   CHECK(!QER_CooldownTripped(false, 0, 30), "cooldown off");
   CHECK(!QER_CooldownTripped(true, 0, 0), "minutes 0 disables the cooldown");
   CHECK(QER_CooldownTripped(true, 0, 30), "a close this second is inside the window");
   CHECK(QER_CooldownTripped(true, 1799, 30), "one second before the window ends is still inside");
   CHECK(QER_CooldownTripped(true, 1800, 30),
         "exactly at the window end still blocks (inclusive, matching HistorySelect)");
   CHECK(!QER_CooldownTripped(true, 1801, 30), "past the window releases");
   CHECK(QER_CooldownTripped(true, -60, 30),
         "a close stamped in the future keeps the cooldown ON (fails safe)");
  }

void SessionWindow()
  {
   //--- start==end is "no window": the filter is off, not a zero-length day.
   CHECK(QER_SessionInside(3, 8, 8), "start==end means the filter is off");
   //--- plain window 8..16, half-open [start,end)
   CHECK(!QER_SessionInside(7, 8, 16), "before the window");
   CHECK(QER_SessionInside(8, 8, 16), "the start hour is inside");
   CHECK(QER_SessionInside(15, 8, 16), "the last hour is inside");
   CHECK(!QER_SessionInside(16, 8, 16), "the end hour is outside (half-open)");
   //--- wrap-around window 22..6
   CHECK(QER_SessionInside(22, 22, 6), "the wrap window opens at 22");
   CHECK(QER_SessionInside(23, 22, 6), "inside after midnight, before 6");
   CHECK(QER_SessionInside(0, 22, 6), "midnight is inside the wrap window");
   CHECK(QER_SessionInside(5, 22, 6), "05:00 is inside the wrap window");
   CHECK(!QER_SessionInside(6, 22, 6), "06:00 closes the wrap window");
   CHECK(!QER_SessionInside(12, 22, 6), "midday is outside an Asia-only window");
  }

void ReviewConditions()
  {
   //--- R1 class
   CHECK(QER_ClassOk(true), "R1 allowed class passes");
   CHECK(!QER_ClassOk(false), "R1 a class the EA does not allow is refused");

   //--- R2 account
   CHECK(QER_AccountOk(""), "R2 an empty block text means armed");
   CHECK(!QER_AccountOk("REAL account without authorization"), "R2 any block text refuses");

   //--- R3 tick age
   CHECK(QER_TickAgeOk(999999, 0), "R3 cap 0 disables the check");
   CHECK(QER_TickAgeOk(5, 10), "R3 a fresh tick passes");
   CHECK(QER_TickAgeOk(10, 10), "R3 exactly at the cap passes");
   CHECK(!QER_TickAgeOk(11, 10), "R3 one second past the cap fails");
   CHECK(QER_TickAgeOk(-2, 10), "R3 a tick ahead of the clock is not stale");

   //--- R4 spread: absolute cap AND share of stop
   double share=0.0;
   CHECK(QER_SpreadOk(10.0, 20, 100.0, 0.0, share), "R4 absolute cap only");
   CHECK(share==0.0, "R4 share stays 0 when the share cap is off");
   CHECK(QER_SpreadOk(10.0, 20, 100.0, 0.25, share), "R4 inside both caps");
   CHECK(std::fabs(share-0.10)<1e-12, "R4 share is measured even when it passes");
   CHECK(QER_SpreadOk(25.0, 20, 100.0, 0.0, share)==false, "R4 above the absolute cap fails");
   CHECK(!QER_SpreadOk(10.0, 20, 30.0, 0.25, share), "R4 33% of the stop fails a 25% share cap");
   CHECK(QER_SpreadOk(20.0, 20, 100.0, 0.20, share), "R4 exactly on both caps passes");
   CHECK(QER_SpreadOk(10.0, 20, 0.0, 0.25, share), "R4 a zero-width stop cannot divide by zero");

   //--- R5 session (the resolver's own arithmetic is covered above)
   CHECK(QER_SessionOk(true), "R5 inside");
   CHECK(!QER_SessionOk(false), "R5 outside refuses");

   //--- R6 trades today
   CHECK(QER_TradesTodayOk(99, 0), "R6 max 0 means unlimited");
   CHECK(QER_TradesTodayOk(2, 3), "R6 under the cap");
   CHECK(!QER_TradesTodayOk(3, 3), "R6 on the cap refuses the next entry");
   CHECK(!QER_TradesTodayOk(4, 3), "R6 over the cap refuses");

   //--- R7 open positions
   CHECK(QER_OpenPositionsOk(0, 1), "R7 room for the first position");
   CHECK(!QER_OpenPositionsOk(1, 1), "R7 the cap is a hard stop");
   CHECK(!QER_OpenPositionsOk(0, 0), "R7 an unknown cap is a refusal, never a pass");

   //--- R8 geometry at the current price
   CHECK(QER_GeometryOk(99.0, 103.0, 100.0, true), "R8 buy geometry");
   CHECK(QER_GeometryOk(103.0, 97.0, 100.0, false), "R8 sell geometry");
   CHECK(!QER_GeometryOk(101.0, 103.0, 100.0, true), "R8 buy stop above the price fails");
   CHECK(!QER_GeometryOk(99.0, 99.5, 100.0, true), "R8 buy target below the price fails");
   CHECK(!QER_GeometryOk(0.0, 103.0, 100.0, true), "R8 a missing stop fails");
   CHECK(!QER_GeometryOk(99.0, 0.0, 100.0, true), "R8 a missing target fails");
   CHECK(!QER_GeometryOk(100.0, 103.0, 100.0, true), "R8 a stop AT the price fails");

   //--- R9 RR at fill
   CHECK(QER_RROk(0.5, 0.0), "R9 floor 0 disables the check");
   CHECK(QER_RROk(2.0, 1.5), "R9 above the floor");
   CHECK(QER_RROk(1.5, 1.5), "R9 exactly on the floor passes");
   CHECK(!QER_RROk(1.4, 1.5), "R9 below the floor fails");
   CHECK(QER_RROk(1.5-1e-12, 1.5), "R9 the 1e-9 tolerance absorbs double rounding");

   //--- R10 stops level (broker resolver verdict is passed through unchanged)
   CHECK(QER_StopsOk(true), "R10 accepted");
   CHECK(!QER_StopsOk(false), "R10 refused");

   //--- R11 size
   CHECK(QER_SizeOk(0.01), "R11 a normalised volume passes");
   CHECK(!QER_SizeOk(0.0), "R11 zero volume fails");
   CHECK(!QER_SizeOk(-1.0), "R11 a negative volume fails");

   //--- R12 opposite exposure
   CHECK(QER_OppositeOk(0, false), "R12 no opposite position");
   CHECK(QER_OppositeOk(12345, true), "R12 opposite allowed when it is closed first");
   CHECK(!QER_OppositeOk(12345, false), "R12 opposite refused when it is not closed");
  }

void RetryBudget()
  {
   std::vector<string> keys(4);
   //--- identity lookup
   CHECK(QER_RetryFind(keys, 4, "a")==-1, "an unknown identity has no budget used");
   keys[0]="123|BUY"; keys[1]="456|SELL";
   CHECK(QER_RetryFind(keys, 4, "123|BUY")==0, "the first identity is found");
   CHECK(QER_RetryFind(keys, 4, "456|SELL")==1, "the second identity is found independently");
   CHECK(QER_RetryFind(keys, 4, "789|BUY")==-1, "a new bar time is a new identity");

   //--- budget arithmetic: InpOrderRetryMax is a ceiling, 0 is never "unlimited"
   CHECK(QER_RetryAllows(0, 1), "the first attempt is always allowed");
   CHECK(!QER_RetryAllows(1, 1), "max 1 refuses the second attempt");
   CHECK(QER_RetryAllows(2, 3), "under the budget");
   CHECK(!QER_RetryAllows(3, 3), "on the budget refuses");
   CHECK(QER_RetryAllows(0, 0), "max 0 behaves as 1");
   CHECK(!QER_RetryAllows(1, 0), "max 0 refuses the second attempt");
   CHECK(!QER_RetryAllows(1, -5), "a negative max is treated as 1, never as unlimited");

   //--- slot rotation: a new identity evicts the oldest instead of growing.
   CHECK(QER_RetryNextSlot(8, 0)==0, "slot 0");
   CHECK(QER_RetryNextSlot(8, 7)==7, "slot 7");
   CHECK(QER_RetryNextSlot(8, 8)==0, "the cursor wraps");
   CHECK(QER_RetryNextSlot(8, -1)==0, "a negative cursor is clamped");
   CHECK(QER_RetryNextSlot(0, 3)==0, "a zero-size table cannot divide by zero");
  }

int main()
  {
   DayBreakers();
   SessionWindow();
   ReviewConditions();
   RetryBudget();
   if(fails!=0) { std::cout << fails << " FAILED\n"; return 1; }
   std::cout << "PASS execution rules: day/drawdown/streak/cooldown floors, session "
                "windows, all 12 review conditions, retry budget\n";
   return 0;
  }
'''


def main():
    cxx = NT.compiler(sanitizers=True)
    if cxx is None:
        NT.skip("native subset: execution rules (breakers + 12 review conditions)", sanitizers=True)
        return
    with tempfile.TemporaryDirectory(prefix="qsmc-execrules-") as d:
        src = Path(d) / "execrules.cpp"
        binary = Path(d) / "execrules"
        src.write_text(PRELUDE + source + TESTS)
        subprocess.run([cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(src), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


main()
raise SystemExit(NT.exit_code([]))
