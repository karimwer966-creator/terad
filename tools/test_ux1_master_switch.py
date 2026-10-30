#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-UX1 - the master switch and the redraw gate, as a contract.

Two small additions, both answering an operator complaint after the seven phases
merged: "I want ONE file on the chart with ALL the features", and "the chart
refreshes too much".

  * InpEnableAllModules - one switch that turns on all seven strategy modules
    AND their tooltip output, instead of fourteen separate flags.
  * InpRedrawTradeBoxOnNewBarOnly - stops DrawTradeBox()/DrawTradeLevels() from
    rewriting their objects on EVERY tick. DrawZoneBox/DrawFibLine update in
    place (ObjectFind, then ObjectMove + ~7 ObjectSetInteger), so a single tick
    issued ~35 object-property writes and a chart repaint for values that are
    closed-bar state and cannot change intrabar.

WHAT THIS SUITE PINS
--------------------
  A  both inputs exist and default to false, like every other behavioural
     switch in this file. Nothing changes for anyone who does not opt in.
  B  all seven module gates carry the OR: `if(!(InpEnableX||InpEnableAllModules))
     return;` - exactly once each, and NO bare `if(!InpEnableX) return;` survives
     anywhere. A gate that lost its OR would silently ignore the master switch.
  C  all seven tooltip guards carry the OR on BOTH halves, so the master switch
     also makes the module's output visible - otherwise enabling a module with
     one click would still leave its readout hidden behind a second flag.
  D  the Confluence Engine's candle leg carries the OR, so with the master switch
     on, the candle pillar is fed (its weight is 15 of 100; without Price Action
     the reachable maximum is 85).
  E  the master switch does NOT enable the chart-object opt-ins
     (InpSBShowEntryZone, InpWyckoffShowRange, InpOBShowLifecycleLabel). Boxes on
     the chart are the clutter the complaint was about; the master switch adds
     tooltip TEXT, not objects.
  F  both per-tick draw calls are gated by
     (!InpRedrawTradeBoxOnNewBarOnly || is_new_bar || detection_updated ||
      prev_calculated==0), i.e. they redraw when the data they show could have
     changed and not otherwise.
  G  the in-place update helpers are untouched: DrawZoneBox and DrawFibLine still
     ObjectFind first and create only when the object is missing. Rewriting them
     to delete+create would turn every redraw into visible flicker.
  H  the additions are display/perf only: no new buffer, plot, enum member or
     trade API, and the version triple is unchanged.

Not a compiler, not a backtest. F7 remains the authority.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "nadir2.mq5")

FAILURES = []
COUNT = [0]


def check(cond, label, detail=""):
    COUNT[0] += 1
    if cond:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s%s" % (label, ("  [%s]" % detail) if detail else ""))
        FAILURES.append(label)


with io.open(SRC, encoding="utf-8", newline="") as fh:
    RAW = fh.read()
TEXT = RAW.replace("\r\n", "\n")
LINES = TEXT.split("\n")

MODULES = [("PowerOf3", "P3ShowOnDashboard"), ("SilverBullet", "SBShowOnDashboard"),
           ("Wyckoff", "WyckoffShowOnDashboard"), ("PriceAction", "PAShowOnDashboard"),
           ("MeanReversion", "MRShowOnDashboard"), ("Confluence", "CFShowOnDashboard"),
           ("RiskModel", "RMShowOnDashboard")]

# ============================================================ A. the two inputs
for name in ("InpEnableAllModules", "InpRedrawTradeBoxOnNewBarOnly"):
    decl = [l for l in LINES if l.startswith("input ") and re.search(r"\b%s\s*=" % name, l)]
    check(len(decl) == 1, "A %s is declared exactly once" % name, "%d decls" % len(decl))
    check(bool(decl) and re.search(r"=\s*false\s*;", decl[0]) is not None,
          "A %s defaults to false" % name,
          decl[0].strip()[:70] if decl else "missing")
check('input group "====== All Seven Modules At Once (AUDIT-UX1) ======"' in RAW,
      "A the two inputs sit in their own AUDIT-UX1 group, not smuggled into a "
      "module's group")

# ============================================== B. every module gate carries OR
for mod, _ in MODULES:
    want = "if(!(InpEnable%s||InpEnableAllModules)) return;" % mod
    check(TEXT.count(want) == 1,
          "B the %s gate carries the master-switch OR, exactly once" % mod,
          "count=%d" % TEXT.count(want))
    bare = "if(!InpEnable%s) return;" % mod
    check(TEXT.count(bare) == 0,
          "B no bare %s gate survives anywhere" % mod,
          "count=%d" % TEXT.count(bare))

# ============================================ C. tooltip guards OR both halves
for mod, show in MODULES:
    want = "if((InpEnable%s||InpEnableAllModules) && (Inp%s||InpEnableAllModules))" % (mod, show)
    check(TEXT.count(want) == 1,
          "C the %s tooltip guard ORs the module switch AND the show switch" % mod,
          "count=%d" % TEXT.count(want))
    bare = "if(InpEnable%s && Inp%s)" % (mod, show)
    check(TEXT.count(bare) == 0, "C no un-ORed %s tooltip guard survives" % mod,
          "count=%d" % TEXT.count(bare))

# ================================================= D. the confluence candle leg
check(TEXT.count("g_cf_has_candle=((InpEnablePriceAction||InpEnableAllModules) &&") == 1,
      "D the Confluence candle leg carries the OR, so the master switch feeds the "
      "15-weight candle pillar",
      "count=%d" % TEXT.count("g_cf_has_candle=((InpEnablePriceAction||InpEnableAllModules) &&"))

# ============================ E. chart-object opt-ins stay out of the master
for opt in ("InpSBShowEntryZone", "InpWyckoffShowRange", "InpOBShowLifecycleLabel"):
    check(TEXT.count("%s||InpEnableAllModules" % opt) == 0
          and TEXT.count("InpEnableAllModules||%s" % opt) == 0,
          "E the master switch does NOT enable %s - boxes on the chart are the "
          "clutter, not the feature" % opt)

# ==================================================== F. the redraw gate
GATE = "(!InpRedrawTradeBoxOnNewBarOnly || (is_new_bar || detection_updated || prev_calculated==0))"
def call_sites(call):
    """The call spans two lines - the `if(` opens on the line above the call - so
    walk back to the statement start instead of matching a single line."""
    out = []
    for i, l in enumerate(LINES):
        if call in l and not l.strip().startswith("//"):
            j = i
            while j > 0 and not LINES[j].lstrip().startswith(("if(", "void ")):
                j -= 1
            if LINES[j].lstrip().startswith("if("):
                out.append((j, i))
    return out


for call in ("DrawTradeBox();", "DrawTradeLevels(rates_total,g_buf_t);"):
    idx = call_sites(call)
    check(len(idx) == 1, "F %s is called from exactly one site" % call[:-1], str(idx))
    if idx:
        j, i = idx[0]
        window = "\n".join(LINES[j:i + 1])
        check(GATE in window,
              "F the %s call site carries the redraw gate" % call[:-1],
              window.strip()[:120])
check(TEXT.count("InpRedrawTradeBoxOnNewBarOnly") >= 3,
      "F the redraw switch is read at both call sites and declared once",
      "%d mentions" % TEXT.count("InpRedrawTradeBoxOnNewBarOnly"))

# ============================== G. the in-place updaters are still in place
for name in ("DrawZoneBox", "DrawFibLine"):
    i = None
    for k, l in enumerate(LINES):
        if re.match(r"^void %s\(" % name, l):
            tail = "".join(LINES[k:k + 8])
            after = tail[tail.index("("):]
            bi, si = after.find("{"), after.find(";")
            if bi >= 0 and (si < 0 or bi < si):
                i = k
                break
    check(i is not None, "G %s is still defined" % name)
    if i is not None:
        d = 0
        body = []
        for j in range(i, len(LINES)):
            body.append(LINES[j])
            d += LINES[j].count("{") - LINES[j].count("}")
            if d == 0 and j > i:
                break
        blk = "\n".join(body)
        check("if(ObjectFind(0,name)<0)" in blk,
              "G %s still creates only when the object is missing (update in "
              "place, no delete+create flicker)" % name)
        check("ObjectMove(0,name,0," in blk,
              "G %s still repositions in place" % name)

# ================================================ H. display/perf only
code = re.sub(r"//[^\n]*", "", RAW)
for api in ("OrderSend", "OrderSendAsync", "PositionOpen", "CTrade"):
    check(len(re.findall(r"\b%s\b" % api, code)) == 0,
          "H still zero %s in the indicator's code" % api)
check(re.search(r"#property indicator_buffers\s+19", RAW) is not None,
      "H indicator_buffers is still 19 - the master switch adds no buffer")
check(re.search(r"#property indicator_plots\s+7", RAW) is not None,
      "H indicator_plots is still 7")
check(re.search(r'QSMC_VERSION_TEXT\s+"v6\.6\.13"', RAW) is not None,
      "H the version triple is unchanged by a UX switch")
check(RAW.count("\n") - RAW.count("\r\n") == 0, "H the file is still pure CRLF")

print("")
print("=" * 74)
print("AUDIT-UX1 checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("One switch for all seven modules, and no per-tick object churn. Both opt-in,")
print("both default false. Not a compiler, not a backtest. Press F7.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
