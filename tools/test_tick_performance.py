#!/usr/bin/env python3
"""v6.6.20 tick/UI contract.

This is a source + native-subset check, NOT a MetaEditor compile and NOT a
latency measurement. It pins three things that are easy to regress:

* the private EA reader calculates but never owns/paints chart objects;
* live preview state and exported buffers still run every tick, while object
  writes are coalesced and unchanged properties are not rewritten;
* history copies are full on attach/rebuild and tail-only afterwards.
"""
from __future__ import print_function
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "nadir2.mq5")
RAW = open(SRC, encoding="utf-8", newline="").read()
TEXT = RAW.replace("\r\n", "\n")
FAILS = []


def check(ok, label):
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        FAILS.append(label)


def body(signature):
    m = re.search(r"(?m)^[^\n]*\b" + re.escape(signature) + r"\s*\([^\n]*\n\{", TEXT)
    if not m:
        raise AssertionError("missing function " + signature)
    i = TEXT.index("{", m.start())
    depth = 0
    for j in range(i, len(TEXT)):
        if TEXT[j] == "{":
            depth += 1
        elif TEXT[j] == "}":
            depth -= 1
            if depth == 0:
                return TEXT[i:j + 1]
    raise AssertionError("unterminated " + signature)


check("\r\n" in RAW and "\n" not in RAW.replace("\r\n", ""), "host remains pure CRLF")
check('#property version   "6.620"' in TEXT and
      '#define QSMC_VERSION_TEXT "v6.6.20"' in TEXT, "release identity is v6.6.20")

init = TEXT[TEXT.index("int OnInit()"):TEXT.index("void OnDeinit(")]
role = init.index("g_qsmc_silent_reader=1")
root = init.index("QSMC_RootCreate(")
wipe = init.index("ObjectsDeleteAll(0,PFX)")
check(role < root and role < wipe, "OnInit detects EA-reader role before root creation or object cleanup")
check("if(!QSMC_IsReaderSilent())" in init[wipe - 120:wipe], "initial shared-prefix cleanup is visual-only")
root_inc = open(os.path.join(ROOT, "MQL5/Include/QSMC/QSMC_Root.mqh"), encoding="utf-8").read()
check("InpArbMinSample,!QSMC_SilentReader());" in root_inc, "arbitration renderer is disabled for the private reader")

paint = body("QSMC_PaintAllowed")
check("g_qsmc_silent_reader==0 && g_qsmc_paint_slice" in paint, "paint authority requires visual role AND paint slice")
oncalc = TEXT[TEXT.index("int OnCalculate("):TEXT.index("// RUNTIME DISPLAY-ONLY LOOKAHEAD AUDIT")]
check("const bool paint_bar=(is_new_bar || detection_updated || prev_calculated==0);" in oncalc,
      "new bar/rebuild opens an immediate paint slice")
check("paint_now-g_ui_last_live_ms>=QSMC_LIVE_UI_COALESCE_MS" in oncalc,
      "same-bar live object work is coalesced by elapsed milliseconds")
check("UpdateEarlyBreakPreview(rates_total,g_buf_t,g_buf_h,g_buf_l,g_buf_c);" in oncalc and "UpdateMTFExecutionEntry();" in oncalc,
      "live preview state updaters remain in the tick path")
check("SigLog_Update(rates_total,prev_calculated);" in oncalc,
      "hidden signal buffers remain updated independently of the dashboard cadence")
check("if(ui_dash_due) QA_DrawCoreStatus();" in oncalc, "Core badge is dashboard-cadence only")
check("g_qsmc_paint_slice=true;   // leave events/self-tests" in oncalc, "paint slice is reset before return")
oncalc_code = "\n".join(line.split("//")[0] for line in oncalc.splitlines())
check("ChartRedraw(" not in oncalc_code, "no unconditional terminal redraw was added to OnCalculate")

for fn in ("DrawHLine", "DrawTextLabel", "DrawFibLine", "DrawZoneBox", "DrawQuantumDashboard",
           "ResolveChartLabelCollisions", "QSMC_MergeNearbyChartLabels", "QA_DrawCoreStatus"):
    src = TEXT if fn != "QA_DrawCoreStatus" else open(os.path.join(ROOT, "MQL5/Include/QSMC/QSMC_IncidentSafety.mqh"), encoding="utf-8").read().replace("\r\n", "\n")
    m = re.search(r"(?m)^void\s+" + fn + r"\([^;]*?\n\{\n([^\n]*)", src)
    check(m is not None and "QSMC_PaintAllowed()" in m.group(1), fn + " obeys the paint slice")

copy = TEXT[TEXT.index("int tail_need="):TEXT.index("bool atr_ok=")]
check("int tail_need=(int)MathMax(3,rates_total-g_last_rates_total+2);" in copy and
      "int  need=(indicator_full_copy ? rates_total : tail_need);" in copy,
      "ATR/ADX/RSI copy full history once, then only the changed tail")
check("QSMC_IND_FULL_WINDOW" not in TEXT, "the repeated 2000-bar copy cap is gone")
check("bool indicator_full_copy=(prev_calculated==0 || g_last_rates_total==0 ||" in TEXT and
      "needResize || rates_total>g_last_rates_total+1);" in TEXT and
      "g_needs_full_rebuild" not in TEXT[TEXT.index("bool indicator_full_copy="):TEXT.index("bool full_indicators=")],
      "periodic causal replay does not force a full indicator-history copy")
check("FillEMAAndVWAP(rates_total,g_buf_o,g_buf_h,g_buf_l,g_buf_c,g_buf_t,g_buf_tv,indicator_full_copy);" in TEXT,
      "EMA/VWAP use their rollover-safe incremental path after attach")
check("InpShowPerfMeter" in TEXT and "QSMC_PerfObserve(perf_elapsed,paint_bar);" in TEXT,
      "the existing performance input is wired to an optional timing report")
gate = open(os.path.join(ROOT, "tools/check_release_gate.py"), encoding="utf-8").read()
check('"InpShowPerfMeter": "INERT' not in gate, "release gate no longer classifies the performance input as inert")

# Native subset: compile the actual compare-before-set helpers with terminal stubs.
helpers = "\n".join(body(n) and ("void " + n + "(" + re.search(r"(?m)^void\s+" + n + r"\(([^)]*)\)", TEXT).group(1) + ")\n" + body(n))
                    for n in ("QSMC_SetObjInt", "QSMC_SetObjDbl", "QSMC_SetObjStr", "QSMC_MoveObj"))
paint_fn = "bool QSMC_PaintAllowed()\n" + body("QSMC_PaintAllowed")
harness = r'''
#include <string>
#include <map>
#include <tuple>
#include <cassert>
#include <cstdint>
using string=std::string;
typedef long long datetime;
typedef int color;
enum ENUM_OBJECT_PROPERTY_INTEGER{OBJPROP_TIME=1,OBJPROP_COLOR=2};
enum ENUM_OBJECT_PROPERTY_DOUBLE{OBJPROP_PRICE=3};
enum ENUM_OBJECT_PROPERTY_STRING{OBJPROP_TEXT=4};
static int writes=0,moves=0;
static std::map<std::tuple<string,int,int>,long long> ints;
static std::map<std::tuple<string,int,int>,double> dbls;
static std::map<std::tuple<string,int,int>,string> strs;
long ObjectGetInteger(int,const string&n,int p,int m=0){return ints[{n,p,m}];}
void ObjectSetInteger(int,const string&n,int p,int m,long long v){++writes;ints[{n,p,m}]=v;}
double ObjectGetDouble(int,const string&n,int p,int m=0){return dbls[{n,p,m}];}
void ObjectSetDouble(int,const string&n,int p,int m,double v){++writes;dbls[{n,p,m}]=v;}
string ObjectGetString(int,const string&n,int p,int m=0){return strs[{n,p,m}];}
void ObjectSetString(int,const string&n,int p,int m,const string&v){++writes;strs[{n,p,m}]=v;}
void ObjectMove(int,const string&n,int point,datetime t,double p){++moves;ints[{n,OBJPROP_TIME,point}]=(long long)t;dbls[{n,OBJPROP_PRICE,point}]=p;}
int g_qsmc_silent_reader=0; bool g_qsmc_paint_slice=true;
''' + helpers + "\n" + paint_fn + r'''
int main(){
  QSMC_SetObjInt("x",OBJPROP_COLOR,7); assert(writes==1);
  QSMC_SetObjInt("x",OBJPROP_COLOR,7); assert(writes==1);
  QSMC_SetObjInt("x",OBJPROP_COLOR,8); assert(writes==2);
  QSMC_SetObjDbl("x",OBJPROP_PRICE,1.5); assert(writes==3);
  QSMC_SetObjDbl("x",OBJPROP_PRICE,1.5); assert(writes==3);
  QSMC_SetObjStr("x",OBJPROP_TEXT,"a"); assert(writes==4);
  QSMC_SetObjStr("x",OBJPROP_TEXT,"a"); assert(writes==4);
  QSMC_MoveObj("x",0,10,1.5); assert(moves==1);
  QSMC_MoveObj("x",0,10,1.5); assert(moves==1);
  QSMC_MoveObj("x",0,11,1.5); assert(moves==2);
  assert(QSMC_PaintAllowed());
  g_qsmc_paint_slice=false; assert(!QSMC_PaintAllowed());
  g_qsmc_paint_slice=true; g_qsmc_silent_reader=1; assert(!QSMC_PaintAllowed());
  // MQL uint is 32-bit; subtraction must remain correct across the 49.7-day wrap.
  uint32_t last=0xFFFFFF9Cu, now=32u; assert(now-last>=100u);
  now=0xFFFFFFC0u; assert(now-last<100u);
  return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
    cpp = os.path.join(td, "subset.cpp")
    exe = os.path.join(td, "subset")
    open(cpp, "w", encoding="utf-8").write(harness)
    try:
        subprocess.check_call(["g++", "-std=c++17", "-O0", "-Wall", "-Wextra", cpp, "-o", exe],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        subprocess.check_call([exe], stdout=subprocess.DEVNULL)
        check(True, "native subset: unchanged properties/moves write nothing; reader/slice gate and uint wrap")
    except Exception as exc:
        check(False, "native subset failed: %s" % exc)

print("=" * 74)
print("tick-performance checks: failures=%d" % len(FAILS))
print("This is NOT a MetaEditor compile, backtest, CPU benchmark, or broker-latency proof.")
sys.exit(1 if FAILS else 0)
