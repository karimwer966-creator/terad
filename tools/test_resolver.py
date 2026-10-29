#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-RS1 contract: the final-signal resolver.

Phase 1 read the pipeline and found the direction conflict is structural, not
cosmetic: the dashboard STATUS word comes from `g_alert_primary` (written by
`AlertDispatcherFinalize`) while the tactical label, arrow and hline colour come
from `UpdateMTFExecutionEntry`'s own `bull`, and nothing in `nadir2.mq5` ever
compares the two. The tactical state word could even print `CONFIRMED` although
the rule printed three lines above it says only the arbiter may.

AUDIT-RS1 adds one authority, `ResolveFinalSignal()`, behind
`InpUseFinalResolver = false`. This suite pins the contract:

  A  the flag and the four weights, and that the weights still sum to 100
  B  the resolver's own state: enum appended at the end, globals declared once,
     no `g_final_score` substring collision with the pre-existing `final_score`
  C  the resolver body: four votes, CONFLICT -> 2, nothing voted -> 0,
     below InpResMinScore -> 0, otherwise the side, and a why-text that calls
     the score a confluence count and not a probability
  D  it is causal: only `closed` bars, no series re-read, no full-history loop
  E  the wiring: OnInit refuses a bad weight sum, OnCalculate calls it after
     `AlertDispatcherFinalize` and only on a closed-bar/detection event
  F  the three surfaces read the same verdict, and the tactical word is demoted
     to INFO so `CONFIRMED` can only come from the resolver
  G  nothing pre-existing was weakened: gates, thresholds and counts unchanged
     apart from the ones this phase is allowed to move, and still no order API
  H  the doc and CI own the same facts

Every number below was measured against the file, not carried forward.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "nadir2.mq5")
DOC = os.path.join(ROOT, "docs", "QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md")
WF = os.path.join(ROOT, ".github", "workflows", "qsmc-verify.yml")

RAW = io.open(SRC, encoding="utf-8", newline="").read()
LINES = RAW.replace("\r\n", "\n").split("\n")
TEXT = "\n".join(LINES)
DOCX = io.open(DOC, encoding="utf-8").read()
WFX = io.open(WF, encoding="utf-8").read()

RESULTS = []


def check(cond, label, detail=""):
    RESULTS.append((bool(cond), label, detail))
    if cond:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s  [%s]" % (label, detail))


def line_at(n):
    return LINES[n - 1] if 1 <= n <= len(LINES) else ""


def find_line(pattern, start=0):
    rx = re.compile(pattern)
    for i in range(start, len(LINES)):
        if rx.search(LINES[i]):
            return i + 1
    return 0


def body(first, last):
    return "\n".join(LINES[first - 1:last])


def fn_end(first):
    """Line of the closing brace of the function that starts at `first`, by
    counting braces - the first `}` on its own line is an inner block, not the
    end, and slicing there silently truncates every body check."""
    depth = 0
    for i in range(first - 1, len(LINES)):
        depth += LINES[i].count("{") - LINES[i].count("}")
        if depth <= 0 and i > first - 1:
            return i + 1
    return 0


# ---------------------------------------------------------------- A. inputs
GRP = 852
FLAG = 853
WB, WZ, WR, WT, WMIN = 856, 857, 858, 859, 860

check('input group "====== Final Signal Resolver (AUDIT-RS1, one verdict '
      'everywhere) ======"' in line_at(GRP),
      "A the resolver has its own input group at L%d" % GRP,
      "L%d is %r" % (GRP, line_at(GRP).strip()[:70]))
check(re.search(r"^input bool\s+InpUseFinalResolver\s*=\s*false;", line_at(FLAG)),
      "A InpUseFinalResolver is declared at L%d and defaults to false" % FLAG,
      "L%d is %r" % (FLAG, line_at(FLAG).strip()[:70]))

WANT = (("InpResWeightBias", 25, WB), ("InpResWeightZone", 25, WZ),
        ("InpResWeightReaction", 30, WR), ("InpResWeightTactical", 20, WT))
for name, val, ln in WANT:
    check(re.search(r"^input int\s+%s\s*=\s*%d;" % (name, val), line_at(ln)),
          "A %s = %d at L%d" % (name, val, ln),
          "L%d is %r" % (ln, line_at(ln).strip()[:70]))

summed = 0
for name, val, ln in WANT:
    m = re.search(r"^input int\s+%s\s*=\s*(\d+);" % name, TEXT, re.M)
    check(m is not None and m.group(1) == str(val),
          "A %s keeps its shipped default %d (never silently retuned)" % (name, val),
          "found %r" % (m.group(1) if m else None))
    summed += int(m.group(1)) if m else 0
check(summed == 100,
      "A the four shipped weights sum to exactly 100 (%d)" % summed,
      "OnInit refuses any other sum, so a wrong default would brick the flag")

check(re.search(r"^input int\s+InpResMinScore\s*=\s*60;", line_at(WMIN)),
      "A InpResMinScore = 60 at L%d" % WMIN,
      "L%d is %r" % (WMIN, line_at(WMIN).strip()[:70]))
check(TEXT.count("InpUseFinalResolver     = false") == 1,
      "A the resolver flag is declared exactly once (no shadow copy)")

# ------------------------------------------- B. enum, globals, no collision
ENUM_LN = 4724
check(line_at(ENUM_LN).strip() == "enum ENUM_FINAL_SIGNAL",
      "B enum ENUM_FINAL_SIGNAL is declared at L%d" % ENUM_LN,
      "L%d is %r" % (ENUM_LN, line_at(ENUM_LN).strip()[:70]))
enums = len(re.findall(r"(?m)^enum\s+ENUM_", TEXT))
check(enums == 44,
      "B the enum was appended, not inserted: 44 ENUM_ declarations",
      "got %d" % enums)
ebody_start = ENUM_LN
ebody_end = find_line(r"^\s*\};", ENUM_LN)
ebody = body(ebody_start, ebody_end)
for state, val in (("FS_WAIT", "0"), ("FS_BUY", "1"), ("FS_SELL", "-1"),
                   ("FS_CONFLICT_WAIT", "2")):
    check(re.search(r"\b%s=%s\b" % (state, re.escape(val)), ebody),
          "B the enum names %s = %s" % (state, val),
          "enum body L%d-L%d: %r" % (ebody_start, ebody_end, ebody.strip()[:90]))
check("FS_CONFLICT_WAIT" in ebody and "FS_WAIT" in ebody,
      "B CONFLICT is its own state, not folded into WAIT: the dashboard can show "
      "the difference")

GL = {"g_final_signal": 4733, "g_res_score": 4734, "g_final_why": 4735,
      "g_tac_dir": 4738, "g_tac_closed": 4739}
for name, ln in sorted(GL.items(), key=lambda kv: kv[1]):
    check(re.search(r"^(int|string|bool)\s+%s\s*=" % name, line_at(ln)),
          "B %s is declared once, at L%d" % (name, ln),
          "L%d is %r" % (ln, line_at(ln).strip()[:70]))
    decls = len(re.findall(r"(?m)^(int|string|bool|double)\s+%s\s*=" % name, TEXT))
    check(decls == 1, "B %s has exactly one global declaration" % name,
          "got %d" % decls)
check("1 BUY, -1 SELL, 0 WAIT, 2 CONFLICT-WAIT" in line_at(4733),
      "B the verdict encoding is documented where it is declared (L4733)",
      "L4733 is %r" % line_at(4733).strip()[:90])
check("g_final_score" not in TEXT,
      "B no g_final_score exists: the resolver score cannot collide as a "
      "substring with the pre-existing final_score the phase suites count",
      "%d occurrence(s)" % TEXT.count("g_final_score"))

# -------------------------------------------------------- C. resolver body
DEF = 6089
check(re.search(r"^int ResolveFinalSignal\(const int closed,string &why\)",
                line_at(DEF)),
      "C ResolveFinalSignal is defined at L%d" % DEF,
      "L%d is %r" % (DEF, line_at(DEF).strip()[:70]))
defs = len(re.findall(r"(?m)^int ResolveFinalSignal\(", TEXT))
check(defs == 1, "C ResolveFinalSignal is defined exactly once", "got %d" % defs)
FWD = 6418
check(re.search(r"^int\s+ResolveFinalSignal\(const int closed,string &why\);",
                line_at(FWD)),
      "C its forward declaration sits at L%d" % FWD,
      "L%d is %r" % (FWD, line_at(FWD).strip()[:70]))
END = fn_end(DEF)
check(0 < END - DEF <= 60,
      "C the resolver is one small function (L%d-L%d, %d lines)" % (DEF, END, END - DEF),
      "a resolver that grows into a second engine is how the conflict came back")
RB = body(DEF, END)

for k, leg in ((0, "bias"), (1, "zone"), (2, "reaction"), (3, "tactical")):
    check(re.search(r'vote\[%d\]=' % k, RB) and re.search(r'w\[%d\]=' % k, RB)
          and ('nm[%d]="%s"' % (k, leg)) in RB,
          "C leg %d votes and is named %r" % (k, leg), "resolver body")
check("vote[0]=(InpUseHTFBias && g_htf_bias!=0)" in RB,
      "C the bias leg respects InpUseHTFBias (a disabled layer cannot vote)")
check(re.search(r"vote\[1\]=PA_ZoneAt\(g_buf_c\[closed\],closed,atr,zn,zt,zb,zd\)", RB),
      "C the zone leg REUSES PA_ZoneAt instead of scanning zones a second time")
check(RB.count("PA_ZoneAt(") == 1,
      "C exactly one PA_ZoneAt call in the resolver", "got %d" % RB.count("PA_ZoneAt("))
callsites = [i + 1 for i, l in enumerate(LINES)
             if "PA_ZoneAt(" in l and not l.strip().startswith("//")
             and not re.match(r"^bool\s+PA_ZoneAt\(", l)]
check(len(callsites) == 4,
      "C PA_ZoneAt has exactly 4 call sites file-wide (PA, CF, RM and now RS1) - "
      "each reuses the one zone scan", str(callsites))
check(6099 in callsites, "C the resolver's zone leg is one of them (L6099)",
      str(callsites))
check("vote[2]=g_rxn_best_buy.valid?1:(g_rxn_best_sell.valid?-1:0)" in RB,
      "C the reaction leg reads the published RXN snapshots, not raw buffers")
check("vote[3]=g_tac_dir;" in RB and "w[3]=InpResWeightTactical;" in RB,
      "C the tactical leg reads g_tac_dir, published by the execution entry")

check("if(buy>0 && sell>0)" in RB and "return 2;" in RB,
      "C both sides voting returns 2 = CONFLICT, never a coin flip")
CONFLICT_WHY = find_line(r'why="CONFLICT: BUY "', DEF)
check(CONFLICT_WHY > DEF and "disagreeing layers mean stand aside" in line_at(CONFLICT_WHY + 1),
      "C the CONFLICT why-text says stand aside (L%d)" % CONFLICT_WHY,
      "L%d is %r" % (CONFLICT_WHY + 1, line_at(CONFLICT_WHY + 1).strip()[:80]))
check('if(buy==0 && sell==0){ why="no layer voted - WAIT"; g_res_score=0; return 0; }' in RB,
      "C nothing voted returns 0 = WAIT and zeroes the score")
MINCHK = 6121
check(re.search(r"if\(g_res_score<InpResMinScore\)", line_at(MINCHK)),
      "C the minimum-score veto is at L%d" % MINCHK,
      "L%d is %r" % (MINCHK, line_at(MINCHK).strip()[:70]))
check("is below InpResMinScore " in body(MINCHK, MINCHK + 6)
      and '" - WAIT";' in body(MINCHK, MINCHK + 6),
      "C a lone side below InpResMinScore is reported as WAIT, with the threshold named")
CONF = 6128
check(re.search(r'why=\(side>0\?"BUY":"SELL"\)\+" CONFIRMED "', line_at(CONF)),
      "C only the CONFIRMED branch builds the winning why-text (L%d)" % CONF,
      "L%d is %r" % (CONF, line_at(CONF).strip()[:70]))
check("a weighted confluence count, not a probability" in line_at(CONF + 1),
      "C the why-text states the score is a confluence count, not a probability",
      "L%d is %r" % (CONF + 1, line_at(CONF + 1).strip()[:90]))
check("return side;" in body(CONF, END),
      "C the winning side is what gets returned")
check(RB.count("return ") == 5,
      "C five exits, no fall-through verdict", "got %d" % RB.count("return "))

# ------------------------------------------------------------- D. causality
check("rates_total" not in RB,
      "D the resolver never touches rates_total: no forming-bar access")
check("iClose(" not in RB and "iTime(" not in RB and "CopyClose(" not in RB,
      "D no series re-read inside the resolver (it reads published globals only)")
check(not re.search(r"for\(int i=0;i<(rates_total|Bars)", RB),
      "D no full-history loop: one call per closed bar, bounded work")
check("g_buf_c[closed]" in RB and "if(closed<0 || closed>=ArraySize(g_buf_c)) return 0;" in RB,
      "D the one price it reads is the closed bar's, and the index is bounds-checked")
check("ObjectCreate" not in RB and "DrawTradeBox" not in RB,
      "D the resolver draws nothing: it decides, the surfaces render")

# --------------------------------------------------------------- E. wiring
ON_INIT = 14566
check(re.search(r"if\(InpUseFinalResolver &&", line_at(ON_INIT))
      and "InpResWeightBias+InpResWeightZone+InpResWeightReaction+"
          "InpResWeightTactical!=100" in line_at(ON_INIT + 1),
      "E OnInit checks the weight sum at L%d-L%d" % (ON_INIT, ON_INIT + 1),
      "L%d is %r" % (ON_INIT, line_at(ON_INIT).strip()[:70]))
oi = body(ON_INIT, ON_INIT + 6)
check("return INIT_PARAMETERS_INCORRECT;" in oi,
      "E a bad weight sum REFUSES to initialise instead of renormalising")
check("must sum to exactly 100" in oi,
      "E the refusal message names the rule the operator broke")
check("renormalise" in line_at(ON_INIT - 1),
      "E the comment above it says why: refuse rather than renormalise",
      "L%d is %r" % (ON_INIT - 1, line_at(ON_INIT - 1).strip()[:80]))

FINALIZE = 15779
CALL_GATE = 15782
check("AlertDispatcherFinalize(rates_total);" in line_at(FINALIZE),
      "E AlertDispatcherFinalize is called at L%d" % FINALIZE,
      "L%d is %r" % (FINALIZE, line_at(FINALIZE).strip()[:70]))
check(re.search(r"if\(InpUseFinalResolver && \(is_new_bar \|\| detection_updated "
                r"\|\| prev_calculated==0\)\)", line_at(CALL_GATE)),
      "E the resolver runs at L%d, after the dispatcher, only on a closed-bar or "
      "detection event - never per tick" % CALL_GATE,
      "L%d is %r" % (CALL_GATE, line_at(CALL_GATE).strip()[:90]))
check(CALL_GATE > FINALIZE,
      "E ordering: dispatcher L%d < resolver L%d, so every layer has published"
      % (FINALIZE, CALL_GATE))
cb = body(CALL_GATE, CALL_GATE + 6)
check("g_final_signal=ResolveFinalSignal(closed,rs_why);" in cb
      and "g_final_why=rs_why;" in cb,
      "E the call site writes g_final_signal and g_final_why and nothing else")
check("g_alert_primary" not in cb,
      "E the resolver does not overwrite g_alert_primary: the arbiter still owns it")
check(TEXT.count("ResolveFinalSignal(closed") == 1,
      "E exactly one call site (a second verdict is how four opinions became one)")

CLEAR = 5862
check("g_tac_dir=0; g_tac_closed=false;" in line_at(CLEAR),
      "E ClearMTFExecutionEntry drops the tactical vote at L%d, so a cleared "
      "execution cannot keep voting" % CLEAR,
      "L%d is %r" % (CLEAR, line_at(CLEAR).strip()[:70]))
PUB = 5959
check("g_tac_dir=bull?1:-1; g_tac_closed=closed_confirm;" in line_at(PUB),
      "E the execution entry publishes its vote at L%d, after closed_confirm is "
      "computed" % PUB,
      "L%d is %r" % (PUB, line_at(PUB).strip()[:70]))
check(PUB < DEF,
      "E publication (L%d) precedes the resolver definition (L%d)" % (PUB, DEF))

# -------------------------------------------------------------- F. surfaces
DASH = 32935
check(line_at(DASH).strip() == "if(InpUseFinalResolver)",
      "F the dashboard override starts at L%d" % DASH,
      "L%d is %r" % (DASH, line_at(DASH).strip()[:70]))
db = body(DASH, DASH + 7)
check('status=(g_final_signal==1?"BUY":(g_final_signal==-1?"SELL":' in db
      and '(g_final_signal==2?"CONFLICT - WAIT":"WAIT"))' in db,
      "F with the flag on the card STATUS is the resolver verdict, CONFLICT included")
check("status_col=(g_final_signal==1?clrLimeGreen:" in db,
      "F the card colour follows the same verdict, not the old primary_dir")
check("primary_dir>0" in line_at(DASH - 4),
      "F with the flag off the card still reads primary_dir exactly as before",
      "L%d is %r" % (DASH - 4, line_at(DASH - 4).strip()[:70]))

TIP = 33103
check('"Resolver: "+(g_final_why==""?"none":g_final_why)' in line_at(TIP),
      "F the tooltip carries the resolver's own why-text at L%d" % TIP,
      "L%d is %r" % (TIP, line_at(TIP).strip()[:90]))
check("InpUseFinalResolver?" in line_at(TIP - 1),
      "F that line only appears when the flag is on (off = byte-identical tooltip)",
      "L%d is %r" % (TIP - 1, line_at(TIP - 1).strip()[:80]))

STATE = 5966
check('string state=closed_confirm?(InpUseFinalResolver?"INFO":"CONFIRMED"):"PREVIEW";'
      in line_at(STATE),
      "F the tactical word is demoted CONFIRMED -> INFO when the resolver is on "
      "(L%d)" % STATE,
      "L%d is %r" % (STATE, line_at(STATE).strip()[:90]))
check(TEXT.count('InpUseFinalResolver?"INFO":"CONFIRMED"') == 1,
      "F the demotion happens at the single place that built the word")
check(TEXT.count("InpUseFinalResolver") == 7,
      "F exactly seven references: the declaration, the OnInit refusal, the call "
      "gate, the state word, the dashboard override, the tooltip guard and the "
      "comment above the enum - no stray extra coupling",
      "got %d" % TEXT.count("InpUseFinalResolver"))

# ------------------------------------------------------- G. nothing weakened
check(re.search(r"^input int\s+InpRXNMinConfirmedScore\s*=\s*68;", TEXT, re.M),
      "G InpRXNMinConfirmedScore is still 68 (the resolver adds a verdict, it "
      "does not loosen a gate)")
check(re.search(r"^input ENUM_QSMC_GATE_PROFILE InpGateProfile = QSMC_GATE_STRICT;", TEXT, re.M),
      "G InpGateProfile still defaults to QSMC_GATE_STRICT (L1343)")
check(re.search(r"^input int\s+InpAlertCooldownBars\s*=\s*5;", TEXT, re.M),
      "G InpAlertCooldownBars is still 5")
check(re.search(r"^input int\s+InpCFMinDisplayScore\s*=\s*60;", TEXT, re.M),
      "G the Confluence Engine's own display threshold is untouched (60)")
for api in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen",
            "PositionClose", "PositionModify"):
    check(not re.search(r"\b%s\s*\(" % api, TEXT),
          "G no %s call: this is an indicator, execution lives in "
          "QSMC_AutoTrader.mq5" % api)
check(all(l.strip().startswith("//") for l in LINES if "OrderSend" in l),
      "G every remaining OrderSend mention is prose in a comment (%d of them), "
      "not code" % TEXT.count("OrderSend"))
check("OrderSend" not in RB and "ObjectCreate" not in RB,
      "G the resolver body itself is free of order and object APIs")

inputs = len(re.findall(r"(?m)^input\s", TEXT))
check(inputs == 558, "G nadir2.mq5 has 558 input lines (538 + 10 RS1 + 10 GS1)",
      "got %d" % inputs)
check(TEXT.count("{") == TEXT.count("}"),
      "G braces balance (%d/%d)" % (TEXT.count("{"), TEXT.count("}")))
check(TEXT.count("{") == 3764, "G brace count is the pinned 3764",
      "got %d" % TEXT.count("{"))
check("\n" not in RAW.replace("\r\n", ""),
      "G no bare LF: every line ends CRLF as .gitattributes requires")
check(len(RAW.replace("\r\n", "\n").split("\n")) - 1 == 45086,
      "G the file is 45086 lines - no scratch rewrite, only the RS1 + GS1 insertions",
      "got %d" % (len(RAW.replace("\r\n", "\n").split("\n")) - 1))
check(len(re.findall(r"(?m)^#include", TEXT)) == 1
      and "#include <QSMC/QSMC_Root.mqh>" in line_at(639),
      "G still exactly one #include (L639, QSMC_Root.mqh): no new header, no "
      "duplicated logic", str(re.findall(r"(?m)^#include.*", TEXT)))
check(len(re.findall(r"(?m)^#property indicator_buffers", TEXT)) == 1,
      "G the resolver added no buffers, so no existing plot index moved "
      "(the EA reads 7-12)")

# ------------------------------------------------------- H. doc and CI own it
for phrase in ("## 11.3 AUDIT-RS1", "ResolveFinalSignal()", "InpUseFinalResolver",
               "25 / 25 / 30 / 20 = 100", "CONFLICT → WAIT",
               "confluence count", "tools/test_resolver.py", "CI step 32",
               "548", "44 enums" if "44 enums" in DOCX else "44 `^enum ENUM_`"):
    check(phrase in DOCX, "H the doc states %r" % phrase)
check("L852" in DOCX and "L860" in DOCX,
      "H the doc cites the resolver's input block (L852-L860)")
check("L6089" in DOCX, "H the doc cites the resolver's definition line (L6089)")
check(re.search(r"run: python3 tools/test_resolver\.py", WFX),
      "H CI runs tools/test_resolver.py")
check(WFX.count("- name: ") == 32,
      "H the workflow has 32 named steps (31 + this suite)",
      "got %d" % WFX.count("- name: "))
check("AUDIT-RS1" in WFX, "H the CI step names the audit it enforces")

fails = sum(1 for ok, _, _ in RESULTS if not ok)
print("AUDIT-RS1 resolver checks: %d   failures: %d" % (len(RESULTS), fails))
sys.exit(1 if fails else 0)
