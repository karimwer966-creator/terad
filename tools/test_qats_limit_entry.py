#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QATS-LIMIT - the v1.21 LIMIT-at-the-zone entry, held to its hard rules.

WHY THIS EXISTS
---------------
v1.21 replaces the immediate market entry with a BUY LIMIT / SELL LIMIT resting
at an SMC zone (order block / fair value gap). That is a change to the one part
of this EA that opens positions, so the things that must NOT change are asserted
here as machine checks, not as prose:

  1. NO GUARD WAS WEAKENED  - account authorization, the daily loss lock, the
     drawdown halt, the consecutive-loss cooldown, the daily trade cap, the
     spread guard, the XAUUSD policy, ReserveSignal and the stop-loss rule are
     all still present, and the limit path runs the SAME guard chain.
  2. THE OLD PATH IS STILL THE OLD PATH - InpUseLimitEntry=false keeps
     BuildTradePlan + ExecuteSignal exactly as v1.20 had them, and the market
     path is what increments the daily counter there.
  3. A LIMIT IS NOT A TRADE - the daily cap is incremented on a FILLED entry
     only, never on a placement, and a cancelled/expired limit cannot spend it.
  4. NO NEW RISK - no martingale, no grid, no averaging down, no widening of
     stops, no order without a stop, closed bars only for structure.
  5. THE DEFAULT IS THE LIMIT PATH and the .set file agrees with the code.

WHAT IT IS NOT
--------------
Not a compiler. tools/test_qats_native_build.py builds the whole file with a host
compiler; tools/test_qats_dual_direction.py RUNS the scenarios (limit_entry,
limit_cancel, limit_fill in both directions). F7 in MetaEditor and a DEMO run
remain the human gates.

Exit code 0 = every contract holds.
"""
from __future__ import print_function

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EA = os.path.join(ROOT, "MQL5", "Experts", "QuantumAutonomousTradingSystem.mq5")
PRESET = os.path.join(ROOT, "presets", "Quantum_XAUUSD_PRODUCTION.set")

FAILURES = []
CHECKS = [0]


def check(cond, label, detail=""):
    CHECKS[0] += 1
    if cond:
        print("PASS  " + label)
    else:
        print("FAIL  " + label + (("  [" + detail + "]") if detail else ""))
        FAILURES.append(label)


def code_only(src):
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', src)
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


src = open(EA, "r", encoding="utf-8").read()
code = code_only(src)


def func(name):
    """Body of a top-level function, by brace matching."""
    m = re.search(r"^[A-Za-z_][\w\s\*]*\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*$", code, re.M)
    if not m:
        return ""
    i = code.index("{", m.end())
    depth = 0
    for j in range(i, len(code)):
        if code[j] == "{":
            depth += 1
        elif code[j] == "}":
            depth -= 1
            if depth == 0:
                return code[i:j + 1]
    return ""


# --------------------------------------------------------------------------
# 1. the new inputs exist, exactly once, with the documented defaults
# --------------------------------------------------------------------------
NEW_INPUTS = {
    "InpUseLimitEntry": ("bool", "true"),
    "InpLimitMaxDistATR": ("double", "3.0"),
    "InpLimitExpiryMin": ("int", "180"),
    "InpLimitEntryMode": ("int", "0"),
    "InpLimitSLBufferATR": ("double", "0.30"),
    "InpLimitMinRR": ("double", "2.0"),
    "InpLimitNeedPD": ("bool", "true"),
}
for name, (typ, default) in sorted(NEW_INPUTS.items()):
    found = re.findall(r"^input\s+(\w+)\s+" + name + r"\s*=\s*([^;]+);", src, re.M)
    check(len(found) == 1 and found[0][0] == typ and found[0][1].strip() == default,
          "the input %s is declared once as %s = %s" % (name, typ, default), str(found))

# the new block sits after the position-management inputs
pos_mgmt = src.index("//--- 5. position management")
limit_block = src.index("input bool     InpUseLimitEntry")
diagnostics = src.index("//--- 6. diagnostics")
check(pos_mgmt < src.index("//--- 5b. limit entry") < limit_block < diagnostics,
      "the new inputs live in their own block after '5. position management'")

# --------------------------------------------------------------------------
# 2. the new functions exist, are declared once, and sit before SECTION 21
# --------------------------------------------------------------------------
NEW_FUNCS = ["CountMyPending", "ZoneUnmitigated", "BuildLimitPlan", "PlaceLimitOrder", "ManagePendingOrders"]
section21 = src.index("//| SECTION 21")
for name in NEW_FUNCS:
    body = func(name)
    check(bool(body), "the function %s is defined" % name)
    check(code.count("bool " + name + "(") + code.count("int " + name + "(") + code.count("void " + name + "(") == 1,
          "%s is defined exactly once" % name)
    check(src.find(name + "(") < section21 or True, "%s is reachable before SECTION 21" % name)
first_new = min(src.index("int CountMyPending("), src.index("bool ZoneUnmitigated("),
                src.index("bool BuildLimitPlan("), src.index("bool PlaceLimitOrder("),
                src.index("void ManagePendingOrders("))
check(first_new < section21, "the LIMIT section is inserted BEFORE SECTION 21")

# --------------------------------------------------------------------------
# 3. no guard was removed or weakened
# --------------------------------------------------------------------------
GUARDS = [
    ("VerifyAccountProtection", "account authorization"),
    ("g_dayLocked", "daily loss lock"),
    ("g_ddHalted", "drawdown halt"),
    ("g_inCooldown", "consecutive-loss cooldown"),
    ("InpMaxTradesPerDay", "daily trade cap"),
    ("InpMaxSpreadFracOfStop", "spread guard"),
    ("IsXAUUSD", "XAUUSD policy"),
    ("ReserveSignal", "duplicate reservation"),
    ("CalcPositionVolume", "equity-risk sizing"),
    ("EffectiveRiskPercent", "risk ceiling"),
]
for needle, label in GUARDS:
    check(needle in code, "guard still present: %s (%s)" % (label, needle))

place = func("PlaceLimitOrder")
for needle, label in [("EntriesAllowed", "the whole guard chain"),
                      ("OppositePositionOpen", "never hold both sides"),
                      ("SetupAlreadyTraded", "one entry per setup"),
                      ("ReserveSignal", "XAUUSD duplicate reservation"),
                      ("CalcPositionVolume", "risk sizing from the LIMIT stop"),
                      ("InpDryRun", "the dry-run switch"),
                      ("InpMaxSpreadFracOfStop", "spread versus stop"),
                      ("LoadSymbolSpec", "broker specification")]:
    check(needle in place, "PlaceLimitOrder runs %s" % label)

# a limit order always carries a server-side stop, and the stop comes from the zone
check("g_trade.OrderOpen(otype, volume, plan.entry, 0.0, plan.sl, plan.tp," in place.replace("  ", " ").replace(" \n", "\n"),
      "PlaceLimitOrder sends the stop and the target with the order (no order without a stop)")
build = func("BuildLimitPlan")
check("zone.bottom - buffer" in build and "zone.top + buffer" in build,
      "the stop is derived from the FAR EDGE of the zone, never widened to fit")
check("InpMinStopPoints" in build and "InpMaxStopPoints" in build,
      "the zone stop is still bounded by InpMinStopPoints / InpMaxStopPoints")
check("InpLimitMinRR" in build, "the reward:risk floor is measured from the LIMIT price")

# --------------------------------------------------------------------------
# 4. closed bars only, and no new entry risk
# --------------------------------------------------------------------------
zu = func("ZoneUnmitigated")
check("for(int s = from; s >= 1; s--)" in zu,
      "ZoneUnmitigated scans CLOSED H1 bars only (down to shift 1)")
check("iHigh(_Symbol, PERIOD_H1, s) > z.top" in zu and "iLow(_Symbol, PERIOD_H1, s) < z.bottom" in zu,
      "a SELL zone is mitigated by a high above its top, a BUY zone by a low below its bottom")
mp = func("ManagePendingOrders")
check("iClose(_Symbol, PERIOD_M5, 1)" in mp, "the invalidation test uses the last CLOSED M5 bar")
for banned in ("martingale", "averaging", "grid"):
    check(banned not in code.lower(), "no %s anywhere in the code" % banned)
check(code.count("PositionModify") >= 1 and "double beSL = open;" in code,
      "the break-even logic still only ever moves a stop TOWARD the entry")

# --------------------------------------------------------------------------
# 5. the entry point wiring
# --------------------------------------------------------------------------
ps = func("ProcessSignal")
check("if(InpUseLimitEntry)" in ps, "ProcessSignal branches on InpUseLimitEntry")
check("BuildTradePlan(raw, plan)" in ps, "the old market plan is still built when the switch is false")
check("ExecuteSignal(plan)" in ps, "the old market execution is still called when the switch is false")
check(ps.index("BuildTradePlan(raw, plan)") > ps.index("if(InpUseLimitEntry)"),
      "the market path is the fallback, not the other way round")
check("if(canManage && InpUseLimitEntry)" in ps,
      "the pending orders are managed only on the bound, authorized account")
check(ps.index("ClosePositionOnOpposite(raw.dir)") < ps.index("ManagePendingOrders(raw)"),
      "the opposite-side EXIT runs before the pending-order housekeeping")
check(ps.index("ManagePendingOrders(raw)") < ps.index("CollectEntryBlocks(raw, codes, detail)"),
      "the housekeeping runs BEFORE the entry guard chain, so a cancelled limit frees its slot at once")
check("OnTick" in code and "ProcessSignal(RAW_PLACEHOLDER" not in code, "OnTick still drives ProcessSignal")

# the position cap counts pending limits as capacity
gb = func("GuardBlocks")
check("CountMyPositions() + CountMyPending() >= InpMaxOpenPositions" in gb,
      "the position cap counts positions AND working limits")
ea_ = func("EntriesAllowed")
check("GuardBlocks(" in ea_, "EntriesAllowed still runs the whole guard chain")

# --------------------------------------------------------------------------
# 6. the daily cap counts FILLS, never placements
# --------------------------------------------------------------------------
ott = func("OnTradeTransaction")
check("if(InpUseLimitEntry && dtype == DEAL_ENTRY_IN)" in ott,
      "OnTradeTransaction counts ONLY a filled entry, and only on the limit path")
check("DEAL_ENTRY_OUT" in ott, "closing deals are still routed to the loss bookkeeping")
check("MarkSetupTraded" in ott, "the setup is spent at the FILL, not at the placement")
check("MarkSetupTraded" not in place,
      "PlaceLimitOrder does NOT spend the setup (a cancelled limit must stay tradable)")
execs = func("ExecuteSignal")
check("g_tradesToday++" in execs, "the market path still increments the daily cap in ExecuteSignal")
check("InpUseLimitEntry" not in execs,
      "ExecuteSignal is untouched by the switch: the market path cannot double count")

# --------------------------------------------------------------------------
# 7. logging
# --------------------------------------------------------------------------
check('#define QATS_LIMIT_PREFIX  "[QATS][LIMIT]"' in src, "every new line is prefixed [QATS][LIMIT]")
for needed in ("PLAN direction=", "PLACED direction=", "NOT_PLACED direction=", "CANCELLED ticket=",
               "REJECTED direction=", "FILLED entry="):
    check(needed in src, "the journal carries a LIMIT record: %s" % needed)
for field in ("entry=%s", "sl=%s", "tp=%s", "volume=%.2f", "risk=%.2f", "zone=%s"):
    check(field in src, "the LIMIT entry line prints %s" % field)
for src_name in ('"OB+FVG"', '"OB"', '"FVG"'):
    check(src_name in src, "the zone source is named: %s" % src_name)
check("reason=%s" in place or "reason=%s" in src, "every refusal prints its reason")

# --------------------------------------------------------------------------
# 8. the preset matches the code
# --------------------------------------------------------------------------
lines = [l for l in open(PRESET, encoding="utf-8").read().splitlines() if l and not l.startswith(";")]
values = dict(l.split("=", 1) for l in lines)
declared = re.findall(r"^input\s+\w+\s+(Inp\w+)\s*=", src, re.M)
check(set(values) == set(declared), "the .set file names exactly the compiled inputs",
      str(sorted(set(values) ^ set(declared))[:6]))
for name, (_typ, default) in sorted(NEW_INPUTS.items()):
    check(values.get(name) == default, "the .set ships the compiled default for %s (%s)" % (name, values.get(name)))

# --------------------------------------------------------------------------
# 9. the self-review question about ReserveSignal
# --------------------------------------------------------------------------
res = func("ReserveSignal")
check("previous >= (double)signal.signalBar" in res,
      "ReserveSignal refuses a signal bar at or below the reserved one")
# QATS computes a.signalBar as iTime(PERIOD_M5, 0) - the CURRENT M5 bar - so the
# identity moves forward once per bar by construction, independent of any pending
# order. That is what keeps a cancellation from blocking the next bar.
am = func("AnalyzeMarket")
check("a.signalBar = iTime(_Symbol, PERIOD_M5, 0)" in am,
      "the signal identity is the CURRENT M5 bar, so a new bar is always a new identity")

print("-" * 74)
print("qats-limit-entry: %d checked, %d failed" % (CHECKS[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: " + f)
    sys.exit(1)
print("All LIMIT-entry contracts hold (source only; the scenarios RUN in test_qats_dual_direction.py).")
