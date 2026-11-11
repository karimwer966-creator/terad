#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUDIT-CH1 / AUDIT-CH2 - chart hygiene of nadir2.mq5 (v6.6.22).

THE DEFECT (CH1)
  AlertDispatcherFinalize() runs once per closed bar and, whenever a primary
  scenario exists, calls AlertDispatcherDrawPrimary(). The mark it drew was named
  after the bar it was PUBLISHED on (QSMC_PRIMARY_<bar time>), and the alert
  cool-down only ever gated the popup. A scenario that stayed primary for N
  closed bars therefore left N arrows and N labels on the chart
  ("[BUY] STRONG REACTION S 4058.44-4060.12 | 72 | needs ..." bar after bar),
  bounded only by a 16-slot ring = 32 objects.

THE FIX
  The mark is named after the SETUP: QSR_Episode() (QSMC_SignalRegistry.mqh)
  gives every zone + direction + source episode one identity and one originating
  bar; re-publication updates the same two objects in place.

CH2
  Every object family nadir2.mq5 can create is classified into a visual layer
  (QSMC_ChartLayers.mqh) and QSMC_DisplayAllowsObject(), the choke point the draw
  primitives already use, consults it while InpChartProfile is CLEAN.

WHAT THIS SUITE DOES
  A  source contracts on nadir2.mq5 (pure text, always run)
  B  EXECUTES the real AlertDispatcherDrawPrimary() text - cut out of nadir2.mq5
     at test time, not re-typed - against a chart-object simulator, next to the
     same function with the eleven pre-fix lines put back, and counts the objects
  C  executes the registry and the layer classifier, and proves that every family
     literal in the indicator has a layer

B and C need a host C++17 compiler; without one the suite exits 77 after A.
NOT MetaEditor: a host build is evidence, never proof, of a clean F7.
"""
from __future__ import print_function

import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import smcvp_native as SN  # noqa: E402

SRC = os.path.join(ROOT, "nadir2.mq5")
MIRROR = os.path.join(ROOT, "MQL5", "Indicators", "nadir2.mq5")
DRIVER = os.path.join(HERE, "smcvp_sim", "hygiene_driver.inc")
OUT = os.path.join(ROOT, "out", "smcvp_native")

PASSED = 0
FAILED = []


def check(cond, label, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("PASS  " + label)
    else:
        FAILED.append(label)
        print("FAIL  " + label + (("  [" + detail + "]") if detail else ""))


RAW = io.open(SRC, encoding="utf-8", newline="").read()
TEXT = RAW.replace("\r\n", "\n")
CODE = SN.QN.strip_comments_and_strings(TEXT)

# The eleven lines AlertDispatcherDrawPrimary() carried before v6.6.22. Kept here
# so the pre-fix behaviour can be EXECUTED without needing the git history.
BEFORE_LINES = [
    '      string base=PFX+"PRIMARY_"+IntegerToString((long)a.bar_time);',
    '      string old=g_primary_mark_names[g_primary_mark_pos];',
    '      if(old!="")',
    '      {',
    '         ObjectDelete(0,old+"_ARROW");',
    '         ObjectDelete(0,old+"_TEXT");',
    '      }',
    '      g_primary_mark_names[g_primary_mark_pos]=base;',
    '      g_primary_mark_pos=(g_primary_mark_pos+1)%QSMC_PRIMARY_MARK_LIMIT;',
    '      datetime tm=a.bar_time;',
    '      int idx=a.closed_index;',
]


def block_from(text, header):
    """The definition that starts with `header`, up to its matching closing brace."""
    start = text.index(header)
    brace = text.index("{", start)
    depth, i = 1, brace + 1
    while depth:
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return text[start:i]


# ---------------------------------------------------------------- A  source contracts
print("=== A  source contracts (nadir2.mq5)")
FUNC = block_from(TEXT, "void AlertDispatcherDrawPrimary(const SAlertCandidate &a)")
check('PFX+"PRIMARY_"+IntegerToString((long)a.bar_time)' not in TEXT,
      "A1 no chart mark is named after the publication bar any more")
check("QSR_Episode(_Symbol,(int)_Period,a.direction,QSR_SourceTag(a.source),a.zone_id,a.bar_time," in FUNC
      and 'string base=PFX+"PRIMARY_"+IntegerToString((long)sig_origin);' in FUNC,
      "A2 the mark name is the setup's originating bar, from the signal registry")
check("if(sig_new) { g_primary_mark_names[evict]=\"\"; g_primary_mark_names[g_primary_mark_pos]=base;" in FUNC,
      "A3 the ring advances only for a NEW signal (a re-publication takes no slot)")
check('if(old!="" && old!=base)' in FUNC, "A4 the ring can never delete the mark it is about to redraw")
check("int idx=QSR_OriginIndex(g_buf_t,a.closed_index,sig_origin,512,tm);" in FUNC,
      "A5 the mark stays anchored on its originating bar")
finalize = block_from(TEXT, "void AlertDispatcherFinalize(const int rates_total)")
check("g_alert_finalized_bar_time==bar_time) return;" in finalize and "AlertDispatcherDrawPrimary(g_alert_primary);" in finalize,
      "A6 the dispatcher still runs once per closed bar and still draws the primary (the cause of the repetition)")
allow = block_from(TEXT, "bool QSMC_DisplayAllowsObject(const string name)")
check(allow.index("QCL_ProfileActive() && !QCL_AllowsName(name,PFX)") < allow.index("InpDisplayMode!=QSMC_MODE_MINIMAL"),
      "A7 the display choke point asks the layer policy first, then the legacy display mode")
check("if(QSMC_IsReaderSilent()) return false;" in allow, "A8 the silent EA reader still paints nothing")
for name, header in (("MVP_Rect", "void MVP_Rect(const string name, const datetime t1, const double p1,"),
                     ("DrawScaleLevel", "void DrawScaleLevel(const string suffix,const double price,const color col,const string text)")):
    body = block_from(TEXT, header)
    check("QSMC_DisplayAllowsObject(name)" in body and body.index("QSMC_DisplayAllowsObject(name)") < body.index("ObjectCreate("),
          "A9 %s asks the display policy before it creates an object" % name)
includes = re.findall(r"^#include <QSMC/QSMC_(\w+)\.mqh>", TEXT, re.M)
check(includes == ["Root", "LiquidityValue", "UnifiedDecision", "IncidentSafety", "SignalRegistry", "ChartLayers",
                   "InstanceIdentity", "InputFingerprint"],
      "A10 the two hygiene modules are tail includes, before the identity / fingerprint pair", str(includes))
check(CODE.count("ObjectCreate(") == 16, "A11 still exactly 16 ObjectCreate call sites (no new object family)",
      "got %d" % CODE.count("ObjectCreate("))
check(RAW.count("\n") == RAW.count("\r\n") and RAW.count("\n") == 45002,
      "A12 the file is pure CRLF and 45002 lines (two include lines appended, nothing shifted)",
      "LF %d CRLF %d" % (RAW.count("\n"), RAW.count("\r\n")))
check(io.open(MIRROR, encoding="utf-8", newline="").read() == RAW, "A13 MQL5/Indicators/nadir2.mq5 is byte-identical to the root copy")
check('#define QSMC_VERSION_TEXT "v6.6.22"' in TEXT and '#property version   "6.622"' in TEXT, "A14 the build is v6.6.22")
# 534 = the inputs nadir2.mq5 declared before v6.6.22 (the release gate's G3 parses the same number).
NEW_INPUTS = ["InpChartProfile", "InpLayerPrimary", "InpLayerSecondary", "InpLayerVolumeProfile", "InpLayerVolumeDetail",
              "InpLayerOptional", "InpPrimaryMarkHistory", "InpSignalEpisodeGapBars"]
own_inputs = re.findall(r"^input\s+(?!group)[^;=]*?\b(Inp\w+)\s*=", TEXT, re.M)
layer_inputs = re.findall(r"^input\s+(?!group)[^;=]*?\b(Inp\w+)\s*=", SN.read_source(os.path.join(SN.INCLUDE_ROOT, "QSMC", "QSMC_ChartLayers.mqh")), re.M)
check(len(own_inputs) == 534 and not [n for n in NEW_INPUTS if n in own_inputs] and layer_inputs == NEW_INPUTS,
      "A15 nadir2.mq5 still declares exactly the 534 inputs it had; the eight new ones are declared in QSMC_ChartLayers.mqh "
      "(a tail include, so they come last in the dialog)", "own %d, layer file %s" % (len(own_inputs), layer_inputs))
check('string base="PD_";' in TEXT and len(re.findall(r"PFX\+base\+", TEXT)) == 8,
      "A16 the only names built as PFX+<variable> are the premium/discount family (base = \"PD_\")",
      "got %d" % len(re.findall(r"PFX\+base\+", TEXT)))

FAMILIES = sorted(set(re.findall(r'PFX\s*\+\s*"([A-Za-z0-9_]+)', CODE and TEXT)))
# literals are blanked in CODE, so take them from TEXT but only on code lines
FAMILIES = sorted(set(m.group(1) for line in TEXT.split("\n")
                      for m in re.finditer(r'PFX\s*\+\s*"([A-Za-z0-9_]+)', line.split("//")[0])))
check(len(FAMILIES) >= 100, "A17 at least 100 distinct object-name literals follow PFX in the indicator", "got %d" % len(FAMILIES))

if not SN.QN.find_compiler():
    print("=== B/C need a host C++17 compiler")
    print("SKIP  qsmc-chart-hygiene: no usable C++17 compiler (g++, c++, clang++) on this host - "
          "the source contracts above ran, the executed sections did NOT")
    print("%d passed, %d failed (text contracts only)" % (PASSED, len(FAILED)))
    sys.exit(1 if FAILED else SN.SKIP_EXIT)

# ---------------------------------------------------------------- the generated hosts
STRUCT = block_from(TEXT, "struct SAlertCandidate") + ";"
HOST_HEAD = '''// GENERATED by tools/test_qsmc_chart_hygiene.py - stubs for the globals the real
// AlertDispatcherDrawPrimary() of nadir2.mq5 reads. The function text below the
// stubs is cut out of nadir2.mq5 verbatim.
#define PFX "QSMC_"
#define QSMC_PRIMARY_MARK_LIMIT   16
enum ENUM_QSMC_DISPLAY_MODE
{
   QSMC_MODE_MINIMAL  = 0,
   QSMC_MODE_STANDARD = 1,
   QSMC_MODE_FULL     = 2
};
input ENUM_QSMC_DISPLAY_MODE InpDisplayMode = QSMC_MODE_MINIMAL;
input bool InpShowEntries = true;
input bool InpShowZREEntryMarks = true;
datetime g_buf_t[];
double   g_buf_l[];
double   g_buf_h[];
double   g_atr_buf[];
double   g_atr=4.0;
string   g_primary_mark_names[QSMC_PRIMARY_MARK_LIMIT];
int      g_primary_mark_pos=0;
string   g_alert_context_text="";
%s
bool QSMC_InVisualDistance(const double price) { return (price>0.0); }
string RXN_LevelName(const int level) { if(level>=5) return "EXECUTION READY"; if(level==4) return "CONFIRMED"; if(level==3) return "STRONG REACTION"; if(level==2) return "REACTION"; return "WATCH"; }
string AlertInvalidationText(const SAlertCandidate &a) { return "inv "+DoubleToString(a.invalidation,2); }
string AlertCompactLine(const SAlertCandidate &a) { return a.zone_id; }
void ResolveChartLabelCollisions() { }
void DrawTextLabel(const string name,const datetime tm,const double price,const string text,const color col,const bool above,const int font_size=8)
{
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_TEXT,0,tm,price);
   ObjectMove(0,name,0,tm,price);
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_COLOR,col);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,font_size);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,(above?ANCHOR_LOWER:ANCHOR_UPPER));
}

%s

#include <QSMC/QSMC_SignalRegistry.mqh>
#include <QSMC/QSMC_ChartLayers.mqh>
'''

new_lines = FUNC.split("\n")
first = next(i for i, l in enumerate(new_lines) if l.strip().startswith("// AUDIT-CH1: the mark belongs to the SETUP"))
check(len(new_lines[first:first + 11]) == 11 and new_lines[first + 10].startswith("      datetime tm=sig_origin;"),
      "B0 the eleven fixed lines sit where the eleven pre-fix lines sat")
before_func = "\n".join(new_lines[:first] + BEFORE_LINES + new_lines[first + 11:])

os.makedirs(OUT, exist_ok=True)
hosts = {}
for tag, func in (("hyg_after", FUNC), ("hyg_before", before_func)):
    path = os.path.join(OUT, tag + "_host.mq5")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(HOST_HEAD % (STRUCT, func))
    hosts[tag] = path

print("=== B  the real function, executed (before / after)")
exes = {}
for tag, path in sorted(hosts.items()):
    exe, rc, diag = SN.build(path, DRIVER, tag, strict=True)
    check(rc == 0 and exe is not None, "B1 %s: strict host build, 0 errors, 0 warnings" % tag, diag.strip()[-600:])
    exes[tag] = exe
if not all(exes.values()):
    print("%d passed, %d failed" % (PASSED, len(FAILED)))
    sys.exit(1)


def run(tag, *args):
    proc = subprocess.run([exes[tag]] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, timeout=120)
    return proc.returncode, proc.stdout


def result(tag, schedule, *sets):
    rc, out = run(tag, "replay", *(list(sets) + [schedule]))
    m = re.search(r"^RESULT (.*)$", out, re.M)
    fields = dict(kv.split("=") for kv in m.group(1).split()) if m else {}
    fields = dict((k, int(v)) for k, v in fields.items())
    fields["rc"] = rc
    t = re.search(r"^FIRSTTEXT (.*)$", out, re.M)
    fields["text"] = t.group(1) if t else ""
    fields["marks"] = re.findall(r"^MARK (\S+) at=(\d+)$", out, re.M)
    fields["clean"] = "fmt_errors=0 api_errors=0" in out
    return fields


S1 = "A" * 12
b = result("hyg_before", S1)
a = result("hyg_after", S1)
check(b["arrows"] == 12 and b["texts"] == 12,
      "B2 BEFORE: one scenario primary for 12 closed bars leaves 12 arrows + 12 labels (the reported defect)",
      "arrows %d texts %d" % (b.get("arrows", -1), b.get("texts", -1)))
check(a["arrows"] == 1 and a["texts"] == 1 and a["peak"] == 2,
      "B3 AFTER: the same 12 publications leave ONE arrow + ONE label, at every bar of the replay",
      "arrows %d texts %d peak %d" % (a.get("arrows", -1), a.get("texts", -1), a.get("peak", -1)))
check(a["registry_created"] == 1 and a["registry_updated"] == 11,
      "B4 AFTER: 1 signal record created, 11 re-publications folded into it")
check(a["text"].startswith("[BUY] STRONG REACTION S 4058.44-4060.12 | 72 |"),
      "B5 the label is the one the operator reported (\"[BUY] STRONG REACTION ...\")", a["text"])
check(len(a["marks"]) == 1 and b["marks"][0][1] == a["marks"][0][1] and len(set(t for _, t in b["marks"])) == 12,
      "B6 AFTER: the single mark sits on the ORIGINATING bar; BEFORE: twelve different bars")
check(a["created"] == 2 and a["deleted"] == 0 and b["created"] == 24,
      "B7 AFTER: 2 objects created and none deleted in 12 bars; BEFORE: 24 created")

S2 = "AAAAAAAAAAAA--AAAAAA----AAAAAABBBBBBBBBB"
b = result("hyg_before", S2)
a = result("hyg_after", S2)
check(b["publications"] == 34 and b["arrows"] == 16 and b["texts"] == 16 and b["peak"] == 32,
      "B8 BEFORE: 34 publications fill the 16-slot ring: 32 objects on the chart")
check(a["arrows"] == 3 and a["texts"] == 3 and a["registry_created"] == 3 and a["registry_expired"] == 1,
      "B9 AFTER: the same 34 publications are 3 setups (a 2-bar pause continues one, a 4-bar pause ends it) = 3 marks",
      str(dict((k, v) for k, v in a.items() if k not in ("marks", "text"))))

a = result("hyg_after", "AAAaaa")
check(a["arrows"] == 1 and a["text"].startswith("[BUY] CONFIRMED "),
      "B10 an upgrade (STRONG REACTION -> CONFIRMED) rewrites the SAME label, it does not add one", a["text"])
a = result("hyg_after", "aaaAAA")
check(a["arrows"] == 1 and a["registry_created"] == 1, "B11 a later, weaker reading does not create a second signal either")
a = result("hyg_after", "AAAASSSS")
check(a["arrows"] == 2 and a["registry_created"] == 2, "B12 the opposite direction on the same zone IS a new signal")
a = result("hyg_after", "AAAACCCC")
check(a["arrows"] == 2, "B13 a different source / zone IS a new signal")

S5 = "-------".join("AB" * 4) + "-------" + "A"
a = result("hyg_after", S5)
check(a["publications"] == 9 and a["registry_created"] == 9 and a["arrows"] == 3 and a["texts"] == 3,
      "B14 nine separate setups keep the current mark + InpPrimaryMarkHistory(2) = 3 marks",
      "arrows %d created %d" % (a.get("arrows", -1), a.get("registry_created", -1)))
a = result("hyg_after", S5, "--set", "InpPrimaryMarkHistory=0")
check(a["arrows"] == 1, "B15 InpPrimaryMarkHistory=0 keeps only the current signal's mark")
a = result("hyg_after", S5, "--set", "InpChartProfile=0")
check(a["arrows"] == 9, "B16 InpChartProfile=LEGACY keeps the historical 16-mark window (nine setups, nine marks)")
a = result("hyg_after", "A" * 40, "--set", "InpChartProfile=0")
check(a["arrows"] == 1 and a["texts"] == 1, "B17 ... and still never repeats one setup, whatever the profile")
a = result("hyg_after", "A-A-A-A-A-A-A", "--set", "InpSignalEpisodeGapBars=1")
check(a["arrows"] == 3 and a["registry_created"] == 7,
      "B18 InpSignalEpisodeGapBars=1: a one-bar pause ends the episode (7 signals, newest 3 marks kept)")
for tag in ("hyg_after", "hyg_before"):
    r = result(tag, S2)
    check(r["user_trend"] == 1 and r["user_note"] == 1 and r["clean"] and r["rc"] == 0,
          "B19 %s: the operator's own objects survive, 0 format / API errors" % tag)

# ---------------------------------------------------------------- C  registry + layers
print("=== C  signal registry and layer policy, executed")
rc, out = run("hyg_after", "selftest")
check(rc == 0 and "PASS QSR_SelfTest" in out, "C1 QSR_SelfTest: 16 lifecycle / identity / capacity checks pass", out.strip())
check("PASS QCL_SelfTest" in out, "C2 QCL_SelfTest: 15 classification / policy checks pass", out.strip())
rc, out = run("hyg_after", "layers", *FAMILIES)
layers = dict(l.split("=") for l in out.strip().split("\n") if "=" in l)
unknown = sorted(k for k, v in layers.items() if v == "UNKNOWN")
check(rc == 0 and len(layers) == len(FAMILIES) and not unknown,
      "C3 every one of the %d object-name literals in nadir2.mq5 has a layer" % len(FAMILIES), "unclassified: %s" % unknown)
census = {}
for v in layers.values():
    census[v] = census.get(v, 0) + 1
print("NOTE  layer census of the name literals: " + ", ".join("%s %d" % kv for kv in sorted(census.items())))
want = {"PRIMARY_": "PRIMARY", "CORE_DASH_": "PRIMARY", "SETUPZONE": "PRIMARY", "TL_SL": "PRIMARY",
        "STRUCT_": "SECONDARY", "OB_": "SECONDARY", "FVG_": "SECONDARY", "LIQ_": "SECONDARY", "PDH": "SECONDARY",
        "SR_LINE_": "SECONDARY", "MVP_L": "VOLUME", "MVP_ND": "VOLUME", "MVP_H": "VOLUME_DETAIL",
        "MVP_LEG": "VOLUME_DETAIL", "MVP_VA": "VOLUME_DETAIL", "RXN_": "OPTIONAL", "ZRE_": "OPTIONAL",
        "PIV_P": "OPTIONAL", "CAM_H3": "OPTIONAL", "KZ_": "OPTIONAL", "BATTLE_": "OPTIONAL", "SCN_": "OPTIONAL",
        "SNIPER_": "OPTIONAL", "ENTRY_PREVIEW": "OPTIONAL", "PD_": "OPTIONAL", "DH_BANNER": "SYSTEM"}
wrong = sorted("%s=%s" % (k, layers.get(k)) for k, v in want.items() if layers.get(k) != v)
check(not wrong, "C4 the hierarchy is the one the audit documents (26 spot checks)", str(wrong))

names = ["QSMC_PRIMARY_1_ARROW", "QSMC_CORE_DASH_BG", "QSMC_OB_7", "QSMC_MVP_L0P", "QSMC_DH_BANNER",
         "QSMC_MVP_H0T12", "QSMC_PIV_P", "QSMC_RXN_BEST_LVL", "QSMC_BATTLE_3", "QSMC_NEW_FAMILY_X"]


def allows(*sets):
    rc_, out_ = run("hyg_after", "allows", *(list(sets) + names))
    return [int(l.split("=")[1]) for l in out_.strip().split("\n") if "=" in l]


check(allows() == [1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
      "C5 CLEAN defaults: primary, secondary, volume lines and the data-health banner show; histogram, pivots, RXN, "
      "battle notes and an unclassified family do not")
check(allows("--set", "InpChartProfile=0") == [1] * 10, "C6 LEGACY profile: the layer policy is out of the way entirely")
check(allows("--set", "InpLayerOptional=true", "--set", "InpLayerVolumeDetail=true") == [1] * 10,
      "C7 every layer has its own switch (optional + volume detail on -> everything shows)")
check(allows("--set", "InpLayerPrimary=false", "--set", "InpLayerSecondary=false",
             "--set", "InpLayerVolumeProfile=false") == [0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
      "C8 with every layer off only the data-health banner (SYSTEM) is left")
check(allows("--set", "InpLayerVolumeProfile=false", "--set", "InpLayerVolumeDetail=true")[5] == 0,
      "C9 volume detail cannot show while the volume layer is off")
rc, out = run("hyg_after", "keep")
check("keep=3 idle=2700" in out, "C10 defaults: 3 marks kept, a 3-bar pause (2700 s on M15) ends an episode", out.strip())

mods = [os.path.join(ROOT, "MQL5", "Include", "QSMC", n) for n in ("QSMC_SignalRegistry.mqh", "QSMC_ChartLayers.mqh")]
problems = SN.lint(mods)
check(not problems, "C11 MQL5 lint: no C++-only construct, no struct by value, no reserved word in the two modules",
      "; ".join(problems[:4]))
for path in mods:
    src = SN.read_source(path)
    banned = [w for w in ("ObjectCreate", "ObjectDelete", "OrderSend", "CTrade", "iCustom", "CopyBuffer", "SetIndexBuffer",
                          "Alert(", "SendNotification", "GlobalVariableSet", "FileOpen")
              if w in SN.QN.strip_comments_and_strings(src)]
    check(not banned, "C12 %s touches no chart object, order, buffer, alert, file or terminal global"
          % os.path.basename(path), str(banned))
count, rc, diag = SN.bool_audit(hosts["hyg_after"], "hyg_bool")
check(rc == 0 and count > 60, "C13 %d boolean operands in the function + modules are all real `bool`" % count,
      diag.strip()[-500:])

print("%d passed, %d failed" % (PASSED, len(FAILED)))
print("This suite executes host-compiled MQL5 text. It is NOT a MetaEditor compile and NOT a chart test.")
sys.exit(1 if FAILED else 0)
