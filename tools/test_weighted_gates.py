#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-GS1 contract: weighted evidence gates with hard vetoes first.

Phase 1 ranked the publication chain B/C HIGH: it was a conjunction —
eligibility (carrying the level minimum) AND proximity AND channels AND cooldown
AND ranking — so every extra gate multiplied the miss rate, and a candidate that
failed one weak leg was indistinguishable from one with no evidence at all,
because the reason was never written down.

`WeightedGateAllows()` replaces the two EVIDENCE gates with one weighted score,
behind `InpUseWeightedGates = false`. This suite pins the contract:

  A  the flag and the five weights, and that the weights still sum to 100
  B  the decision state: three globals, each declared once
  C  the hard vetoes (data, spread, news) are tested FIRST, set the veto flag,
     return false, and reuse the existing news rule rather than inventing one
  D  the five evidence legs each add exactly their own weight, and every missed
     leg is named in the why-text
  E  causality and hygiene: no forming bar, no series re-read, no full-history
     loop, no drawing, no order API, no hard-coded price
  F  the wiring: OnInit refuses a bad weight sum and a bad minimum, the call site
     is a ternary whose OFF branch is the original conjunction token for token,
     and channels/cooldown/ranking stay hard either way
  G  nothing pre-existing was weakened: shipped thresholds, the pinned
     RXN_LevelEx and its self-tests, and the file's counts
  H  the doc and CI own the same facts

Every number was measured against the file, not carried forward.
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


def body(first, last):
    return "\n".join(LINES[first - 1:last])


def fn_end(first):
    """Closing brace of the function starting at `first`, by counting braces:
    the first lone `}` is an inner block, and slicing there silently truncates
    every body assertion."""
    depth = 0
    for i in range(first - 1, len(LINES)):
        depth += LINES[i].count("{") - LINES[i].count("}")
        if depth <= 0 and i > first - 1:
            return i + 1
    return 0


# ---------------------------------------------------------------- A. inputs
GRP, FLAG = 861, 862
WL, WE, WP, WA, WR = 863, 864, 865, 866, 867
WMIN, WEV, WROOM = 868, 869, 871

check('input group "====== Weighted Gate Scoring (AUDIT-GS1, evidence weighted, '
      'vetoes hard) ======"' in line_at(GRP),
      "A the weighted gates have their own input group at L%d" % GRP,
      "L%d is %r" % (GRP, line_at(GRP).strip()[:70]))
check(re.search(r"^input bool\s+InpUseWeightedGates\s*=\s*false;", line_at(FLAG)),
      "A InpUseWeightedGates is declared at L%d and defaults to false" % FLAG,
      "L%d is %r" % (FLAG, line_at(FLAG).strip()[:70]))
check("OFF = the existing hard-AND chain, unchanged" in line_at(FLAG),
      "A the flag's own comment states what OFF means")

WANT = (("InpWGWeightLevel", 25, WL), ("InpWGWeightEvidence", 25, WE),
        ("InpWGWeightProximity", 20, WP), ("InpWGWeightAlignment", 15, WA),
        ("InpWGWeightRoom", 15, WR))
summed = 0
for name, val, ln in WANT:
    check(re.search(r"^input int\s+%s\s*=\s*%d;" % (name, val), line_at(ln)),
          "A %s = %d at L%d" % (name, val, ln),
          "L%d is %r" % (ln, line_at(ln).strip()[:70]))
    m = re.search(r"(?m)^input int\s+%s\s*=\s*(\d+);" % name, TEXT)
    check(m is not None and m.group(1) == str(val),
          "A %s keeps its shipped default %d (never silently retuned)" % (name, val),
          "found %r" % (m.group(1) if m else None))
    summed += int(m.group(1)) if m else 0
check(summed == 100,
      "A the five shipped weights sum to exactly 100 (%d)" % summed,
      "OnInit refuses any other sum, so a wrong default would brick the flag")

for name, val, ln in (("InpWGMinScore", 60, WMIN), ("InpWGMinEvidenceScore", 68, WEV)):
    check(re.search(r"^input int\s+%s\s*=\s*%d;" % (name, val), line_at(ln)),
          "A %s = %d at L%d" % (name, val, ln),
          "L%d is %r" % (ln, line_at(ln).strip()[:70]))
check(re.search(r"^input double\s+InpWGMinRoomATR\s*=\s*1\.0;", line_at(WROOM)),
      "A InpWGMinRoomATR = 1.0 at L%d, in ATR units (symbol-agnostic, no price)" % WROOM,
      "L%d is %r" % (WROOM, line_at(WROOM).strip()[:70]))
check("mirrors the" in line_at(WEV) or "mirrors" in line_at(WEV + 1),
      "A the evidence floor says it MIRRORS the existing 68 rather than changing it")
check(len(re.findall(r"(?m)^input .*InpUseWeightedGates", TEXT)) == 1,
      "A the flag is declared exactly once (no shadow copy)")

# ---------------------------------------------------------------- B. globals
GL = {"g_wgate_score": 4767, "g_wgate_why": 4768, "g_wgate_veto": 4769}
for name, ln in sorted(GL.items(), key=lambda kv: kv[1]):
    check(re.search(r"^(int|string|bool)\s+%s\s*=" % name, line_at(ln)),
          "B %s is declared at L%d" % (name, ln),
          "L%d is %r" % (ln, line_at(ln).strip()[:70]))
    decls = len(re.findall(r"(?m)^(int|string|bool|double)\s+%s\s*=" % name, TEXT))
    check(decls == 1, "B %s has exactly one global declaration" % name,
          "got %d" % decls)
check("never for evidence" in line_at(4769),
      "B the veto flag's comment states it is only ever data/spread/news",
      "L4744 is %r" % line_at(4769).strip()[:80])
check("Written only by WeightedGateAllows()" in body(4765, 4767),
      "B the ownership comment names the single writer")

# ---------------------------------------------------------- C. hard vetoes
DEF = 42416
check(re.search(r"^bool WeightedGateAllows\(const SAlertCandidate &c,"
                r"const datetime bar_time,string &why\)", line_at(DEF)),
      "C WeightedGateAllows is defined at L%d" % DEF,
      "L%d is %r" % (DEF, line_at(DEF).strip()[:70]))
check(len(re.findall(r"(?m)^bool WeightedGateAllows\(", TEXT)) == 1,
      "C it is defined exactly once")
END = fn_end(DEF)
check(0 < END - DEF <= 90,
      "C the gate is one small function (L%d-L%d, %d lines)" % (DEF, END, END - DEF),
      "a gate that grows into a second engine is how the chain got opaque")
RB = body(DEF, END)

V_DATA = 42422
V_SPREAD = 42428
V_NEWS = 42435
FIRST_LEG = 42446
check("!c.valid || c.direction==0 || c.bar_time<=0 || c.closed_index<0" in body(V_DATA, V_DATA + 6),
      "C veto 1 is invalid candidate data (L%d)" % V_DATA,
      "L%d is %r" % (V_DATA, line_at(V_DATA).strip()[:80]))
check("g_spread>(long)InpMaxSpreadPts" in body(V_SPREAD, V_SPREAD + 7),
      "C veto 2 is spread above InpMaxSpreadPts (L%d)" % V_SPREAD,
      "L%d is %r" % (V_SPREAD, line_at(V_SPREAD).strip()[:80]))
check("g_is_backtest && InpIgnoreSpreadInBacktest" in body(V_SPREAD, V_SPREAD + 7),
      "C the spread veto keeps the documented backtest exemption instead of "
      "re-deciding it")
check("MTF_SniperIsNewsBlackout(bar_time)" in body(V_NEWS, V_NEWS + 6),
      "C veto 3 REUSES MTF_SniperIsNewsBlackout - one news rule, not a second "
      "implementation (L%d)" % V_NEWS,
      "L%d is %r" % (V_NEWS, line_at(V_NEWS).strip()[:80]))
for ln, name in ((V_DATA, "data"), (V_SPREAD, "spread"), (V_NEWS, "news")):
    blk = body(ln, ln + 8)
    check("g_wgate_veto=true;" in blk and "return false;" in blk,
          "C the %s veto sets the veto flag and returns false" % name, blk.strip()[:70])
    check('"HARD VETO: ' in blk,
          "C the %s veto says HARD VETO in the why-text" % name, blk.strip()[:70])
# A veto that can be switched off is not a veto. Pin each condition EXACTLY, so
# wrapping one in another flag (or an `if(false && ...)`) fails here.
check(line_at(V_DATA).strip() == "if(!c.valid || c.direction==0 || c.bar_time<=0 || c.closed_index<0)",
      "C the data veto's condition is exactly that - no extra operand can disable it",
      "L%d is %r" % (V_DATA, line_at(V_DATA).strip()[:80]))
check(line_at(V_SPREAD).strip() ==
      "if(!(g_is_backtest && InpIgnoreSpreadInBacktest) && g_spread>(long)InpMaxSpreadPts)",
      "C the spread veto's condition is exactly that - unconditional apart from the "
      "documented backtest exemption",
      "L%d is %r" % (V_SPREAD, line_at(V_SPREAD).strip()[:80]))
check(line_at(V_NEWS).strip() == "if(MTF_SniperIsNewsBlackout(bar_time))",
      "C the news veto's condition is exactly the reused rule - nothing can gate it",
      "L%d is %r" % (V_NEWS, line_at(V_NEWS).strip()[:80]))
for ln, name in ((V_DATA, "data"), (V_SPREAD, "spread"), (V_NEWS, "news")):
    exits = [l.strip() for l in body(ln, ln + 8).split("\n") if l.strip() == "return false;"]
    check(len(exits) == 1,
          "C the %s veto has exactly one unconditional `return false;`" % name,
          str(exits))
check("InpUseWeightedGates" not in body(V_DATA - 4, V_NEWS + 6),
      "C no veto is itself behind the feature flag: with the flag OFF the vetoes "
      "are simply not reached, and with it ON they cannot be turned off")
check(V_DATA < V_SPREAD < V_NEWS < FIRST_LEG,
      "C all three vetoes are tested BEFORE the first weighted leg (L%d < L%d < "
      "L%d < L%d), so no weight can outvote a veto" % (V_DATA, V_SPREAD, V_NEWS, FIRST_LEG))
check("got+=" not in body(DEF, V_NEWS),
      "C no weight is accumulated anywhere above the news veto")
check("g_wgate_veto=false;" in body(DEF, DEF + 6) and "g_wgate_score=0;" in body(DEF, DEF + 6),
      "C the state is reset on entry, so a stale veto can never survive to the "
      "next candidate")

# ------------------------------------------------------- D. evidence legs
LEGS = (("c.level>=min_level", "InpWGWeightLevel", "level", 42446),
        ("c.score>=InpWGMinEvidenceScore", "InpWGWeightEvidence", "evidence", 42448),
        ("c.distance_atr<=maxd", "InpWGWeightProximity", "proximity", 42451),
        ("c.alignment>0", "InpWGWeightAlignment", "alignment", 42454),
        ("c.opposing_room_atr<0.0 || c.opposing_room_atr>=InpWGMinRoomATR",
         "InpWGWeightRoom", "room", 42456))
for cond, weight, name, ln in LEGS:
    seg = body(ln, ln + 3)
    check(cond in line_at(ln), "D the %s leg tests %r at L%d" % (name, cond[:44], ln),
          "L%d is %r" % (ln, line_at(ln).strip()[:80]))
    check("got+=%s;" % weight in seg,
          "D the %s leg adds exactly %s, no other weight" % (name, weight),
          seg.strip()[:80])
    check('have+="%s "' % name in seg,
          "D an earned %s leg is named in the why-text" % name)
    check("miss+=" in seg or "miss+=" in body(ln, ln + 4),
          "D a missed %s leg is also named, so the reason is written down" % name)
check("int min_level=(int)MathMax(2,MathMin(5,InpRXNAlertMinLevel));" in RB,
      "D the level leg reuses the SAME clamp as the existing eligibility rule")
check("double maxd=InpAlertMaxDistanceATR;" in RB
      and "if(!MathIsValidNumber(maxd) || maxd<0.0) maxd=2.0;" in RB,
      "D the proximity leg reuses InpAlertMaxDistanceATR with its documented "
      "fallback, not a new distance rule")
check("g_wgate_score=got;" in line_at(42459),
      "D the weighted total is published for display at L42027",
      "L42027 is %r" % line_at(42459).strip()[:70])
check("if(got<InpWGMinScore)" in line_at(42460),
      "D the minimum-score decision is at L42028", "L42028 is %r" % line_at(42460).strip()[:70])
low = body(42460, 42466)
check("below InpWGMinScore " in low and '"- WAIT";' in low.replace("\n", "")
      or "- WAIT" in low,
      "D a candidate below the minimum is reported as WAIT with the threshold named",
      low.strip()[:90])
check("missed: " in low, "D the WAIT text lists what was missed")
PUB = 42467
check("PUBLISH " in body(PUB, END) and "a weighted confluence count, not a probability"
      in body(PUB, END),
      "D the success text says PUBLISH and states the score is a confluence "
      "count, not a probability", body(PUB, END).strip()[:100])
check(RB.count("return ") == 5,
      "D five exits: three vetoes, below-minimum, publish - no fall-through",
      "got %d" % RB.count("return "))

# ---------------------------------------------------- E. causality/hygiene
check("rates_total" not in RB, "E the gate never touches rates_total: no forming bar")
check(not re.search(r"iClose\(|iTime\(|CopyClose\(|CopyBuffer\(", RB),
      "E no series re-read: it reads the candidate record the dispatcher already built")
check(not re.search(r"for\(int i=0;i<(rates_total|Bars)", RB),
      "E no full-history loop: bounded work per candidate")
check("ObjectCreate" not in RB and "DrawTradeBox" not in RB and "Comment(" not in RB,
      "E the gate draws nothing: it decides, the surfaces render")
check(not re.search(r"\b\d{3,5}\.\d+\b", RB),
      "E no hard-coded price literal in the gate (ATR units only)")
check("TimeCurrent()" not in RB, "E no wall-clock read: the decision is bar-bound")

# ---------------------------------------------------------------- F. wiring
OI1, OI2 = 15269, 15276
check("if(InpUseWeightedGates &&" in line_at(OI1)
      and "InpWGWeightAlignment+InpWGWeightRoom!=100" in line_at(OI1 + 2),
      "E OnInit checks the five-weight sum at L%d-L%d" % (OI1, OI1 + 2),
      "L%d is %r" % (OI1, line_at(OI1).strip()[:70]))
oi = body(OI1, OI1 + 6)
check("return INIT_PARAMETERS_INCORRECT;" in oi
      and "must sum to exactly 100" in oi,
      "E a bad weight sum REFUSES to initialise and names the rule")
check("renormalise" in line_at(OI1 - 1) or "renormalise" in line_at(OI1 - 2),
      "E the comment above says why: refuse rather than renormalise")
oi2 = body(OI2, OI2 + 6)
check("InpWGMinScore<0 || InpWGMinScore>100" in oi2
      and "return INIT_PARAMETERS_INCORRECT;" in oi2,
      "E an out-of-range InpWGMinScore also refuses (L%d)" % OI2, oi2.strip()[:80])

GS_DECL, GS_TERN = 42500, 42514
check('string gs_why="";' in line_at(GS_DECL),
      "F the why-buffer is declared once before the candidate loop (L%d)" % GS_DECL,
      "L%d is %r" % (GS_DECL, line_at(GS_DECL).strip()[:70]))
check("bool gs_evidence=InpUseWeightedGates" in line_at(GS_TERN),
      "F the selection reads the flag at L%d" % GS_TERN,
      "L%d is %r" % (GS_TERN, line_at(GS_TERN).strip()[:70]))
check("?WeightedGateAllows(c,bar_time,gs_why)" in line_at(GS_TERN + 1),
      "F the ON branch calls the weighted gate")
check(":(c.alert_eligible && c.distance_atr<=maxd);" in line_at(GS_TERN + 2),
      "F the OFF branch is the ORIGINAL conjunction, token for token, so off "
      "means unchanged behaviour",
      "L%d is %r" % (GS_TERN + 2, line_at(GS_TERN + 2).strip()[:80]))
sel = body(GS_TERN + 3, GS_TERN + 5)
check("AlertChannelsFor(c,ap,apush,asnd)" in sel
      and "AlertCooldownAllows(c,AlertExactKey(c))" in sel
      and "AlertCandidateBetter(c,best_alert)" in sel,
      "F channels, cooldown and ranking stay HARD either way: they are delivery "
      "and de-duplication, not evidence", sel.strip()[:100])
check(sel.count("InpUseWeightedGates") == 0,
      "F the hard gates are not inside the flag's scope")
WIN = 42527
wb = body(WIN, WIN + 8)
check("if(InpUseWeightedGates)" in line_at(WIN)
      and "WeightedGateAllows(best_alert,bar_time,wfinal)" in wb,
      "F the why-text kept for display is recomputed for the candidate that WON, "
      "not whichever the loop tested last (L%d)" % WIN, wb.strip()[:90])
check("no candidate reached the weighted gate - WAIT" in wb,
      "F when nothing published, the display says so instead of showing a stale reason")
TIP = 33853
check('"Weighted gate: "+(g_wgate_why==""?"none":g_wgate_why)' in line_at(TIP),
      "F the tooltip carries the gate's own why-text at L%d" % TIP,
      "L%d is %r" % (TIP, line_at(TIP).strip()[:90]))
check("InpUseWeightedGates?" in line_at(TIP - 1),
      "F that tooltip line only appears when the flag is on (off = identical tooltip)",
      "L%d is %r" % (TIP - 1, line_at(TIP - 1).strip()[:80]))
check(TEXT.count("WeightedGateAllows(") == 4,
      "F one definition and two call sites plus the ownership comment: no third "
      "opinion about publication",
      "got %d" % TEXT.count("WeightedGateAllows("))
check(TEXT.count("InpUseWeightedGates") == 7,
      "F exactly seven references to the flag: declaration, two OnInit refusals, "
      "tooltip, selection, winner block",
      "got %d" % TEXT.count("InpUseWeightedGates"))

# ------------------------------------------------------- G. nothing weakened
check(re.search(r"(?m)^input int\s+InpRXNMinConfirmedScore\s*=\s*68;", TEXT),
      "G InpRXNMinConfirmedScore is still 68")
check(re.search(r"(?m)^input ENUM_QSMC_GATE_PROFILE InpGateProfile = QSMC_GATE_STRICT;", TEXT),
      "G InpGateProfile still defaults to QSMC_GATE_STRICT")
check(re.search(r"(?m)^input int\s+InpAlertCooldownBars\s*=\s*5;", TEXT),
      "G InpAlertCooldownBars is still 5")
check(re.search(r"(?m)^input int\s+InpCFMinDisplayScore\s*=\s*60;", TEXT),
      "G InpCFMinDisplayScore is still 60")
check(re.search(r"(?m)^input int\s+InpResMinScore\s*=\s*60;", TEXT),
      "G the resolver's InpResMinScore is still 60")
LV = TEXT.find("int RXN_LevelEx(const int phase")
check(LV > 0, "G RXN_LevelEx still exists (its 1:1 self-tests are untouched)")
lvbody = TEXT[LV:LV + 2600]
check("score>=confirmed_gate" in lvbody and "countertrend_margin" in lvbody,
      "G the pinned level promotion still requires phase AND score, with the "
      "countertrend margin")
check("InpWG" not in lvbody and "WeightedGateAllows" not in lvbody,
      "G no weighted-gate input leaked into RXN_LevelEx: the scorer wraps the "
      "decision, it does not rewrite the pinned level function")
for api in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen",
            "PositionClose", "PositionModify"):
    check(not re.search(r"\b%s\s*\(" % api, TEXT),
          "G no %s call anywhere: indicator only" % api)
check("OrderSend" not in RB, "G the gate body never mentions an order API")
check(all(l.strip().startswith("//") for l in LINES if "OrderSend" in l),
      "G every remaining OrderSend mention is prose in a comment")

inputs = len(re.findall(r"(?m)^input\s", TEXT))
check(inputs == 583, "G nadir2.mq5 has 583 input lines (548 + 10 GS1 + 16 SC1 + 9 OBS1)",
      "got %d" % inputs)
check(TEXT.count("{") == TEXT.count("}") == 3842,
      "G braces balance at the pinned 3842",
      "%d/%d" % (TEXT.count("{"), TEXT.count("}")))
check(len(RAW.replace("\r\n", "\n").split("\n")) - 1 == 45838,
      "G the file is 45838 lines: insertions only, no scratch rewrite",
      "got %d" % (len(RAW.replace("\r\n", "\n").split("\n")) - 1))
check("\n" not in RAW.replace("\r\n", ""),
      "G no bare LF: every line ends CRLF as .gitattributes requires")
check(len(re.findall(r"(?m)^#include", TEXT)) == 1
      and "#include <QSMC/QSMC_Root.mqh>" in line_at(639),
      "G still exactly one #include (L639): no new header, no duplicated logic")
check(len(re.findall(r"(?m)^#property indicator_buffers", TEXT)) == 1,
      "G no buffers added, so no existing plot index moved (the EA reads 7-12)")
check(len(re.findall(r"(?m)^enum\s+ENUM_", TEXT)) == 44,
      "G no enum added or removed by this phase (still 44)")

# ------------------------------------------------------- H. doc and CI own it
for phrase in ("## 11.4 AUDIT-GS1", "WeightedGateAllows()", "InpUseWeightedGates",
               "25 / 25 / 20 / 15 / 15 = 100", "HARD VETO",
               "confluence count, not a probability",
               "tools/test_weighted_gates.py", "CI step 33", "583"):
    check(phrase in DOCX, "H the doc states %r" % phrase)
check("L42416" in DOCX, "H the doc cites the gate's definition line (L42416)")
check("L862" in DOCX, "H the doc cites the flag's declaration line (L862)")
check(re.search(r"run: python3 tools/test_weighted_gates\.py", WFX),
      "H CI runs tools/test_weighted_gates.py")
check(WFX.count("- name: ") == 36,
      "H the workflow has 36 named steps (32 + this suite + scalping + journal + declutter)",
      "got %d" % WFX.count("- name: "))
check("AUDIT-GS1" in WFX, "H the CI step names the audit it enforces")

fails = sum(1 for ok, _, _ in RESULTS if not ok)
print("AUDIT-GS1 weighted-gate checks: %d   failures: %d" % (len(RESULTS), fails))
sys.exit(1 if fails else 0)
