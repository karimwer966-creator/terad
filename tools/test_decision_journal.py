#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-OBS1 contract: the per-bar decision journal (display and audit only).

Phase 1 defect F was that nothing kept a per-bar transcript. The file could say
why the LAST alert was suppressed (AlertWhyNoPopup) and could count gate outcomes
in aggregate (SSignalGateAudit), but on a live chart an operator could not ask
"what did each layer say on the 09:45 bar, and which one said no?". OBS1 is that
record, and this suite pins what makes it trustworthy:

  A  inputs: the flag defaults false, the eight inputs are exactly as declared and
     contiguous, and the journal is not folded into InpEnableAllModules
  B  state: the row struct, the four g_obs_* globals, one declaration each, no
     price inside a row, no new plot buffer and no new enum
  C  the five PURE cores, line for line: ring wrap, state names, veto-outranks-
     score, the inclusive minimum, reason precedence, and the alert-source names
  D  reuse, not re-derivation: the record reads what the layers already published,
     gated by each layer's own flag, and calls no engine and no zone scan
  E  record discipline: closed bar only, one row per bar, a bounded ring, counters
     reset on resize, an event-driven opt-in log that cannot flood
  F  advisory boundary: no drawing, no object, no series write, no order API, and
     the module assigns only g_obs_*
  G  causality and hygiene: never the forming bar, no per-tick full-history loop,
     the tooltip walks at most the rows it is allowed to show
  H  wiring: OnInit refuses impossible sizes, the self-test hook sits inside the
     file's general self-test switch, and - the load-bearing one - OBS_Record runs
     AFTER the resolver, never next to SCALP_Update
  I  the self-test really has eleven numbered deterministic checks
  J  nothing pre-existing was weakened, and the counts moved only as declared
  K  the doc and CI own the same facts

Every number below was measured against nadir2.mq5, not computed from a diff.
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
TEXT = RAW.replace("\r\n", "\n")
LINES = TEXT.split("\n")
DOCX = io.open(DOC, encoding="utf-8").read()
WFX = io.open(WF, encoding="utf-8").read()

RESULTS = []


def check(ok, label, detail=""):
    RESULTS.append((bool(ok), label, detail))
    out = ("PASS  " if ok else "FAIL  ") + label
    if detail and not ok:
        out += "  [%s]" % detail
    print(out)


def line_at(n):
    return LINES[n - 1]


def body(a, b):
    return "\n".join(LINES[a - 1:b])


def fn_end(start):
    """Closing-brace line of the function whose signature begins at `start`.

    Depth is ignored until a brace has actually opened, so a signature spread
    over several lines cannot "end" the function on line two.
    """
    depth = 0
    opened = False
    for i in range(start - 1, len(LINES)):
        depth += LINES[i].count("{") - LINES[i].count("}")
        if depth > 0:
            opened = True
        if opened and depth <= 0:
            return i + 1
    return len(LINES)


# ---------------------------------------------------- measured anchors
GRP, FLAG, BARS, TIPB, LOG = 888, 889, 890, 891, 892
SH_RES, SH_GATE, SH_SCALP, SH_PRI, UX1_GRP = 893, 894, 895, 896, 897
STRUCT, ROWS, FILLED, NEXTG, LASTBAR = 4490, 4503, 4504, 4505, 4506
NEXTIDX, STNAME, STSTATE = 6146, 6156, 6167
REASON, SRCNAME, RECORD, JTEXT, SELFTEST = 6178, 6195, 6205, 6248, 6283
INIT_REFUSE, INIT_ANNOUNCE, V580 = 14560, 14564, 14567
GUARD, SCALP_HOOK, HOOK_PASS, HOOK_FAIL = 14919, 14955, 14959, 14961
ONCALC = 15097
OC_CF, OC_RM, OC_SCALP = 15711, 15716, 15720
OC_DISP, OC_RES, OC_RESWHY, OBS_GUARD, OBS_CALL = 15736, 15742, 15743, 15748, 15749
TIP_SCALP, TIP_GUARD, TIP_OBS = 32027, 32028, 32029

MOD_A, MOD_Z = NEXTIDX, fn_end(SELFTEST)
MOD = body(MOD_A, MOD_Z)
REC = body(RECORD, fn_end(RECORD))
JT = body(JTEXT, fn_end(JTEXT))
ST = body(SELFTEST, fn_end(SELFTEST))
STRUCT_B = body(STRUCT, fn_end(STRUCT))

check(MOD_Z > SELFTEST, "A the module region closes after the self-test",
      "region is L%d-L%d" % (MOD_A, MOD_Z))

# ------------------------------------------------------- A. inputs
A_EXACT = {
    GRP: 'input group "====== Decision Journal (AUDIT-OBS1, per-bar why-no-entry, display only) ======"',
    FLAG: "input bool   InpEnableDecisionJournal  = false; // record one row per CLOSED bar",
    BARS: "input int    InpObsJournalBars         = 60;    // rows kept in the ring buffer (10..500)",
    TIPB: "input int    InpObsTooltipBars         = 8;     // rows shown in the tooltip, newest first",
    LOG: "input bool   InpObsLogEvents           = false; // Print only bars where something decided",
    SH_RES: "input bool   InpObsShowResolver        = true;  // column: the resolver's verdict",
    SH_GATE: "input bool   InpObsShowGate            = true;  // column: the weighted gate's outcome",
    SH_SCALP: "input bool   InpObsShowScalp           = true;  // column: the scalping overlay's verdict",
    SH_PRI: "input bool   InpObsShowPrimary         = true;  // column: what was actually published",
}
for ln, want in sorted(A_EXACT.items()):
    check(line_at(ln) == want, "A L%d is exactly %r" % (ln, want[:56]),
          "got %r" % line_at(ln)[:80])

check("InpEnableDecisionJournal  = false" in line_at(FLAG),
      "A the journal defaults OFF, as every new module in this file must")
check("InpObsLogEvents           = false" in line_at(LOG),
      "A the event log defaults OFF too: printing is the operator's choice")
check(GRP + 1 == FLAG, "A the group header sits directly above the flag")
check(all(line_at(n).startswith("input ") for n in range(FLAG, SH_PRI + 1)),
      "A the eight inputs are contiguous, so none can be reordered unnoticed")
check(line_at(UX1_GRP).startswith('input group "====== All Seven Modules At Once'),
      "A the block ends where the AUDIT-UX1 group begins (L%d)" % UX1_GRP,
      "got %r" % line_at(UX1_GRP)[:60])
check("InpEnableAllModules" not in body(GRP, UX1_GRP),
      "A the journal is NOT folded into InpEnableAllModules: that switch is pinned "
      "to the seven strategy modules, and a transcript is not an eighth one")
for name in ("InpObsJournalBars", "InpObsTooltipBars", "InpObsLogEvents",
             "InpObsShowResolver", "InpObsShowGate", "InpObsShowScalp",
             "InpObsShowPrimary", "InpEnableDecisionJournal"):
    decl = len(re.findall(r"(?m)^input .*%s\b" % name, TEXT))
    check(decl == 1, "A %s is declared exactly once" % name, "got %d" % decl)
check("(10..500)" in line_at(BARS), "A the kept-rows label states its own bounds")
check("newest first" in line_at(TIPB), "A the shown-rows label states the order")

# ------------------------------------------------------- B. state and ownership
for ln, want in ((ROWS, "SObsJournalRow g_obs_rows[];"),
                 (FILLED, "int      g_obs_filled=0;"),
                 (NEXTG, "int      g_obs_next=0;"),
                 (LASTBAR, "datetime g_obs_last_bar_time=0;")):
    check(line_at(ln).startswith(want), "B L%d declares %s" % (ln, want[:34]),
          "got %r" % line_at(ln)[:70])
for g in ("g_obs_rows", "g_obs_filled", "g_obs_next", "g_obs_last_bar_time"):
    decl = len(re.findall(r"(?m)^(?:SObsJournalRow|int|datetime)\s+%s\b" % g, TEXT))
    check(decl == 1, "B %s is declared exactly once" % g, "got %d" % decl)
check(line_at(STRUCT) == "struct SObsJournalRow", "B the row struct is L%d" % STRUCT)
FIELDS = ("bar_time", "final_signal", "res_score", "gate_state", "gate_score",
          "scalp_dir", "scalp_score", "primary_dir", "primary_src", "why")
pos = [STRUCT_B.find(f + ";") for f in FIELDS]
check(all(p > 0 for p in pos), "B the struct declares all ten columns", str(pos))
check(pos == sorted(pos), "B the columns are declared in the order the tooltip prints them")
check("double" not in STRUCT_B,
      "B a row holds verdicts and text, never a price: no double field")
check("[]" not in STRUCT_B, "B a row holds no array: the ring buffer is the only collection")
check("0 not run, 1 published, 2 evidence below minimum, 3 hard veto" in body(STRUCT - 3, STRUCT),
      "B the gate_state encoding is written down where the struct is declared")
check("CLOSED bar" in body(STRUCT - 3, STRUCT),
      "B the ownership comment says the row belongs to a CLOSED bar")
check("CORE / RXN / ZRE / unset" in line_at(STRUCT + 10),
      "B the primary_src comment names every value OBS_SourceName can return",
      "got %r" % line_at(STRUCT + 10)[:80])
check(TEXT.count("indicator_buffers") == 1,
      "B the journal adds no plot buffer: the file still declares one",
      "got %d" % TEXT.count("indicator_buffers"))
check(len(re.findall(r"(?m)^enum\s+ENUM_", TEXT)) == 44,
      "B the journal adds no enum: gate_state stays an int with a named mapping",
      "got %d" % len(re.findall(r"(?m)^enum\s+ENUM_", TEXT)))

# ------------------------------------------------------- C. the pure cores
NI = body(NEXTIDX, fn_end(NEXTIDX))
check(line_at(NEXTIDX) == "int OBS_NextIndex(const int current,const int cap)",
      "C OBS_NextIndex takes only its two arguments")
for want in ("   if(cap<=0) return 0;", "   int n=current+1;",
             "   if(n>=cap) n=0;", "   return n;"):
    check(want in NI, "C the ring core contains %r" % want.strip())
check("g_" not in NI, "C the ring core reads no global state at all")

SN = body(STNAME, fn_end(STNAME))
check(line_at(STNAME) == "string OBS_GateStateName(const int state)",
      "C OBS_GateStateName takes only the state")
for st, name in ((1, "PUBLISHED"), (2, "BELOW-MIN"), (3, "HARD-VETO")):
    check('if(state==%d) return "%s";' % (st, name) in SN,
          "C state %d is named %s" % (st, name))
check(SN.rstrip().endswith('return "not-run";\n  }'),
      "C an unrecognised state falls through to not-run, never to a blank cell")
check("g_" not in SN, "C the state-name core reads no global state")

GS = body(STSTATE, fn_end(STSTATE))
check(line_at(STSTATE) ==
      "int OBS_GateState(const bool ran,const bool veto,const int score,const int min_score)",
      "C OBS_GateState takes facts, not globals")
ORDER = ("   if(!ran) return 0;", "   if(veto) return 3;",
         "   if(score<min_score) return 2;", "   return 1;")
gp = [GS.find(o) for o in ORDER]
check(all(p > 0 for p in gp), "C the gate-state core has all four outcomes", str(gp))
check(gp == sorted(gp), "C and tests them in this order: not-run, veto, below-minimum, published")
check(gp[1] < gp[2], "C a veto outranks a strong evidence score, on purpose")
check("score<min_score" in GS and "score<=min_score" not in GS,
      "C the minimum is inclusive: score==min publishes, exactly like every other floor here")
check("g_" not in GS, "C the gate-state core reads no global state")

RS = body(REASON, fn_end(REASON))
check(line_at(REASON) ==
      "string OBS_Reason(const int gate_state,const string gate_why,const int final_signal,",
      "C OBS_Reason is declared at L%d" % REASON)
R_ORDER = ('if(gate_state==3) return gate_why;', 'if(gate_state==2) return gate_why;',
           'if(final_signal==2) return "resolver CONFLICT - "+final_why;',
           'if(scalp_dir==2) return "scalp CONFLICT - "+scalp_why;',
           'if(final_signal!=0) return final_why;', 'if(scalp_dir!=0) return scalp_why;',
           'if(gate_state==1) return gate_why;',
           'return "no layer produced a verdict this bar";')
rp = [RS.find(o) for o in R_ORDER]
check(all(p >= 0 for p in rp), "C the reason core has all eight branches", str(rp))
check(rp == sorted(rp), "C and ranks them: veto, thin evidence, resolver conflict, scalp "
                        "conflict, resolver, scalp, published gate, silence")
check(rp[0] < rp[2] < rp[4], "C a veto is reported before any side is named")
check('"resolver CONFLICT - "' in RS, "C a resolver conflict is labelled as a conflict")
check('"scalp CONFLICT - "' in RS, "C a scalping conflict is labelled as a conflict")
check('"no layer produced a verdict this bar"' in RS,
      "C silence is reported as silence instead of an empty cell")
check("g_" not in RS, "C the reason core reads no global state")

SRCN = body(SRCNAME, fn_end(SRCNAME))
check(line_at(SRCNAME) == "string OBS_SourceName(const int source)",
      "C OBS_SourceName takes only the source int")
for val, name in ((3, "CORE"), (2, "RXN"), (1, "ZRE")):
    check('if(source==%d) return "%s";' % (val, name) in SRCN,
          "C source %d is named %s, matching the dispatcher's own field comment" % (val, name))
check(SRCN.rstrip().endswith('return "unset";\n  }'),
      "C an unexpected source is named unset rather than relabelled as one of the three")
check('1=ZRE, 2=RXN, 3=CORE legacy' in body(SRCNAME - 4, SRCNAME),
      "C the mapping cites the encoding it was read from")
check("g_" not in SRCN, "C the source-name core reads no global state")
DISPATCH = [n + 1 for n, l in enumerate(LINES)
            if re.match(r"\s*int\s+source;\s*// 1=ZRE, 2=RXN, 3=CORE legacy", l)]
check(len(DISPATCH) == 1, "C that encoding is declared once in the file (L%s)" % DISPATCH,
      "got %s" % DISPATCH)

# ------------------------------------------------------- D. reuse, not re-derivation
READS = ("g_final_signal", "g_res_score", "g_wgate_veto", "g_wgate_score", "g_wgate_why",
         "g_sc_dir", "g_sc_score", "g_sc_why", "g_alert_primary.valid",
         "g_alert_primary.direction", "g_alert_primary.source", "g_buf_t[closed]")
for r in READS:
    check(r in REC, "D the record reads %s, which a layer already published" % r)
for exact in ("   int gs=OBS_GateState(InpUseWeightedGates,g_wgate_veto,g_wgate_score,InpWGMinScore);",
              "   r.final_signal=(InpUseFinalResolver?g_final_signal:0);",
              "   r.res_score=(InpUseFinalResolver?g_res_score:0);",
              "   r.scalp_dir=(InpEnableScalping?g_sc_dir:0);",
              "   r.scalp_score=(InpEnableScalping?g_sc_score:0);",
              '   r.primary_dir=(g_alert_primary.valid?g_alert_primary.direction:0);',
              '   r.primary_src=(g_alert_primary.valid?OBS_SourceName(g_alert_primary.source):"none");'):
    check(exact in REC, "D %r" % exact.strip()[:74])
check("InpUseFinalResolver?g_final_signal:0" in REC,
      "D a layer that is switched off contributes 0, not a stale verdict")
check("InpEnableScalping?g_sc_dir:0" in REC,
      "D the scalping column is gated by the scalping overlay's own flag")
check("InpUseWeightedGates,g_wgate_veto" in REC,
      "D whether the gate ran is the gate's own flag, passed into the pure core")
check("InpWGMinScore" in REC and "60" not in REC,
      "D the minimum comes from InpWGMinScore, never from a number typed in the journal")
NEVER = ("PA_ZoneAt(", "IsInSession(", "MTF_SniperIsNewsBlackout(", "ResolveFinalSignal(",
         "WeightedGateAllows(", "SCALP_ScoreSide(", "SCALP_Decide(", "SCALP_Votes(",
         "CopyBuffer(", "iCustom(", "iBarShift(", "g_atr_buf", "g_spread")
for n in NEVER:
    check(n not in REC, "D the record never calls or reads %s: it re-derives nothing" % n)
check(REC.count("OBS_GateState(") == 1 and REC.count("OBS_Reason(") == 1
      and REC.count("OBS_SourceName(") == 1 and REC.count("OBS_NextIndex(") == 1,
      "D the record calls each of its own pure cores exactly once")

# ------------------------------------------------------- E. record discipline
for exact in ("   if(closed<1 || closed>rates_total-2 || closed>=ArraySize(g_buf_t)) return;",
              "   datetime bt=g_buf_t[closed];",
              "   if(bt<=0 || bt==g_obs_last_bar_time) return;",
              "   int cap=(int)MathMax(10,MathMin(500,InpObsJournalBars));",
              "   if(ArraySize(g_obs_rows)!=cap)",
              "      ArrayResize(g_obs_rows,cap);",
              "      g_obs_filled=0; g_obs_next=0; g_obs_last_bar_time=0;",
              "   g_obs_rows[g_obs_next]=r;",
              "   g_obs_next=OBS_NextIndex(g_obs_next,cap);",
              "   if(g_obs_filled<cap) g_obs_filled++;",
              "   g_obs_last_bar_time=bt;"):
    check(exact in REC, "E %r" % exact.strip()[:74])
check(REC.find("if(closed<1 ||") < REC.find("datetime bt="),
      "E the closed-bar guard is the first statement, before anything is read")
check(REC.find("bt==g_obs_last_bar_time") < REC.find("ArrayResize"),
      "E the one-row-per-bar guard precedes any resize")
check("MathMax(10,MathMin(500," in REC,
      "E the ring is clamped to 10..500 rows, so memory cannot grow with history")
check("g_obs_next=OBS_NextIndex(" in REC and "g_obs_next++" not in REC,
      "E the write slot advances through the pure core, never by a bare ++")
check("if(g_obs_filled<cap)" in REC,
      "E the row count saturates at the cap instead of overflowing it")
check("g_obs_last_bar_time=bt;" in REC,
      "E the bar stamp is written last, so a refused bar cannot block the next one")
LOGGATE = ("   if(InpObsLogEvents && (r.final_signal!=0 || r.gate_state==1 || r.gate_state==3 ||\n"
           "      r.scalp_dir!=0))")
check(LOGGATE in REC, "E the log is opt-in AND event-driven, character for character")
check(REC.count("Print(") == 1, "E the record prints at most once per bar",
      "got %d" % REC.count("Print("))
check(REC.find("if(InpObsLogEvents") > REC.find("g_obs_last_bar_time=bt;"),
      "E the journal is written before the optional log, so a log line is never the only record")
check('"QSMC OBS "' in REC, "E the log line is prefixed, so it can be filtered out of a tester log")
for col in ('" published="', '" resolver="', '" gate="', '" scalp="'):
    check(col in REC, "E the log line carries the %s column" % col.strip('"').strip())
check("OBS_GateStateName(r.gate_state)" in REC,
      "E the log names the gate state instead of printing a bare int")

# ------------------------------------------------------- F. advisory boundary
FORBIDDEN = ("ObjectCreate", "ObjectSetText", "ObjectDelete", "ObjectSetString",
             "ObjectSetInteger", "ObjectSetDouble", "DrawTextLabel", "DrawZoneBox",
             "Comment(", "SetIndexBuffer", "ArraySetAsSeries", "OrderSend",
             "OrderSendAsync", "CTrade", "PlotIndexSet", "Alert(", "SendNotification",
             "PlaySound", "MessageBox")
for f in FORBIDDEN:
    check(f not in MOD, "F the module never touches %s" % f.strip("("))
check(not re.search(r"OrderSend\s*\(|OrderSendAsync\s*\(", TEXT) and "CTrade" not in TEXT,
      "F the whole indicator still calls no order API: the five OrderSend mentions in\n"
      "this file are the comments that forbid it, and execution lives in the EA")
WRITES = re.findall(r"(?m)^\s*(g_[A-Za-z0-9_]+)\s*=[^=]", MOD)
check(WRITES and set(WRITES) <= {"g_obs_rows", "g_obs_filled", "g_obs_next",
                                "g_obs_last_bar_time"},
      "F the module assigns only its own four globals", "got %s" % sorted(set(WRITES)))
check(not re.search(r"g_(final_signal|final_why|res_score|wgate_\w+|sc_\w+|alert_primary"
                    r"|trade_setup|active_setup)\s*=[^=]", MOD),
      "F no other layer's verdict is written here: the journal is a transcript, not a voter")
check("g_buf_c[" not in MOD and "g_buf_t[" in MOD,
      "F the module reads the closed-bar time only, and never a price buffer")
check(not re.search(r"g_buf_t\[[^\]]+\]\s*=[^=]", MOD),
      "F no series is written by the module")

# ------------------------------------------------------- G. causality and hygiene
check("closed>rates_total-2" in REC,
      "G the forming bar is refused: rates_total-2 is the last closed bar")
check("closed>=ArraySize(g_buf_t)" in REC,
      "G the index is bounds-checked against the series it is read from")
check(not re.search(r"for\([^)]*rates_total", MOD),
      "G no loop walks the whole history: the journal is written once per closed bar")
check("for(int k=0;k<want;k++)" in JT,
      "G the tooltip loop is bounded by the rows it is allowed to show")
check("int want=(int)MathMax(1,MathMin(max_rows,g_obs_filled));" in JT,
      "G that bound is clamped to what the ring actually holds")
check("if(g_obs_filled<=0) return \"\";" in JT,
      "G an empty journal renders as nothing, not as a header with no rows")
check("int slot=g_obs_next-1;" in JT and "if(slot<0) slot=ArraySize(g_obs_rows)-1;" in JT,
      "G the tooltip walks backwards from the newest row and wraps like the ring does")
check("slot--;" in JT, "G and steps one row at a time, newest first")
check('"Decision journal (last "' in JT and '" closed bars, newest first):\\n"' in JT,
      "G the block says how many rows it shows and in which order")
for col in ("InpObsShowPrimary", "InpObsShowResolver", "InpObsShowGate", "InpObsShowScalp"):
    check("if(%s)" % col in JT, "G the %s column can be switched off" % col)
check("out+=\"\\n     why: \"+r.why+\"\\n\";" in JT,
      "G every row carries its reason, indented under the columns")
check("TimeToString(r.bar_time,TIME_MINUTES)" in JT,
      "G a row is labelled with its own bar time, so it cannot be mistaken for now")

# ------------------------------------------------------- H. wiring
check(line_at(INIT_REFUSE).startswith(
        '      Print("Invalid Quantum SMC decision journal: keep 10-500 closed bars'),
      "H OnInit refuses an impossible journal size with a message an operator can act on")
check(line_at(INIT_REFUSE + 1) == "      return INIT_PARAMETERS_INCORRECT;",
      "H and refuses to initialise rather than clamping silently")
check(INIT_REFUSE < V580, "H that refusal sits above the v5.8.0 quant/scaling validation (L%d)" % V580)
check(body(INIT_REFUSE - 4, INIT_REFUSE).count("InpEnableDecisionJournal &&") == 1,
      "H the refusal is gated by the journal's own flag, so a disabled journal cannot block OnInit")
check("InpObsTooltipBars>InpObsJournalBars" in body(INIT_REFUSE - 3, INIT_REFUSE),
      "H showing more rows than are kept is refused: that would display rows that do not exist")
check(line_at(INIT_ANNOUNCE).startswith('      Print(">>> ",QSMC_VERSION_TEXT," Decision journal: ON'),
      "H enabling it announces itself, including that it is display and audit only")
check("keeps \",InpObsJournalBars,\" shows \",InpObsTooltipBars" in line_at(INIT_ANNOUNCE + 1),
      "H the announcement states the sizes actually in force")
check(line_at(GUARD) == "   if(InpMTEERunSelfTest)",
      "H the self-test hook lives inside the file's general self-test switch (L%d)" % GUARD)
GUARD_END = fn_end(GUARD)
check(HOOK_PASS < GUARD_END and HOOK_FAIL < GUARD_END,
      "H both hook branches are inside that guarded block, which closes at L%d" % GUARD_END)
check(HOOK_PASS > SCALP_HOOK, "H the journal's hook runs after the scalping overlay's (L%d)" % SCALP_HOOK)
check(line_at(HOOK_PASS - 1) == "      if(OBS_SelfTest(mtee_fail))",
      "H the hook calls OBS_SelfTest with the file's shared failure string")
check("PASS (11/11)" in line_at(HOOK_PASS), "H the pass line states the number of checks it runs",
      "got %r" % line_at(HOOK_PASS)[:80])
check(line_at(HOOK_FAIL).strip().endswith('self-test: FAIL - ",mtee_fail);'),
      "H the fail line reports the reason, like every other self-test hook here")
check(line_at(ONCALC) == "int OnCalculate(const int rates_total, const int prev_calculated,",
      "H OnCalculate still begins at L%d" % ONCALC, "got %r" % line_at(ONCALC)[:70])
CHAIN = (("confluence", OC_CF), ("risk model", OC_RM), ("scalping overlay", OC_SCALP),
         ("alert dispatcher", OC_DISP), ("resolver verdict", OC_RES),
         ("resolver why-text", OC_RESWHY), ("journal record", OBS_CALL))
for (nm, ln), (_, nxt) in zip(CHAIN, CHAIN[1:]):
    check(ln < nxt, "H in OnCalculate the %s (L%d) runs before the %s (L%d)"
          % (nm, ln, CHAIN[CHAIN.index((nm, ln)) + 1][0], nxt))
check(OBS_CALL > OC_RESWHY,
      "H THE LOAD-BEARING ORDER: OBS_Record runs after the resolver has published, "
      "so the journal never transcribes the previous bar's verdict")
check(OBS_CALL > OC_DISP, "H and after the alert dispatcher, so the published column is this bar's")
check(OBS_CALL > OC_SCALP, "H and after the scalping overlay")
check(OBS_CALL - OC_RESWHY < 12,
      "H the record is still adjacent to the resolver block, not buried further down OnCalculate",
      "gap is %d lines" % (OBS_CALL - OC_RESWHY))

# The chain above compares pinned constants, which cannot themselves go stale in
# the right direction: if the calls moved, those constants would still be ordered.
# So the order is re-derived by SEARCHING OnCalculate, and the search results are
# also required to equal the constants - a moved call fails both ways, and the
# reason printed is the ordering, which is the property that actually matters.
PATTERNS = (("confluence", r"CF_Update\(closed"),
            ("risk model", r"RM_Update\(closed"),
            ("scalping overlay", r"SCALP_Update\(closed"),
            ("alert dispatcher", r"AlertDispatcherFinalize\("),
            ("resolver verdict", r"g_final_signal=ResolveFinalSignal\("),
            ("resolver why-text", r"^      g_final_why=rs_why;$"),
            ("journal record", r"OBS_Record\(closed,rates_total\);"))
OC_END = fn_end(ONCALC)
check(OC_END > OBS_CALL, "H OnCalculate still encloses the record call",
      "OnCalculate closes at L%d" % OC_END)
FOUND = {}
for nm, pat in PATTERNS:
    hits = [n for n in range(ONCALC, OC_END + 1) if re.search(pat, LINES[n - 1])]
    check(len(hits) == 1, "H OnCalculate contains exactly one %s call" % nm,
          "found %s" % hits[:4])
    FOUND[nm] = hits[0] if len(hits) == 1 else None
PINNED = {"confluence": OC_CF, "risk model": OC_RM, "scalping overlay": OC_SCALP,
          "alert dispatcher": OC_DISP, "resolver verdict": OC_RES,
          "resolver why-text": OC_RESWHY, "journal record": OBS_CALL}
for nm, want in PINNED.items():
    check(FOUND.get(nm) == want, "H the %s call is where this suite says it is (L%d)" % (nm, want),
          "found at L%s" % FOUND.get(nm))
names = [nm for nm, _ in PATTERNS]
for a, b in zip(names, names[1:]):
    if FOUND.get(a) and FOUND.get(b):
        check(FOUND[a] < FOUND[b],
              "H MEASURED ORDER: the %s (L%d) runs before the %s (L%d)"
              % (a, FOUND[a], b, FOUND[b]))
if FOUND.get("journal record") and FOUND.get("resolver why-text"):
    check(FOUND["journal record"] > FOUND["resolver why-text"],
          "H MEASURED, not pinned: the journal is written after the resolver publishes, "
          "so no row can carry the previous bar's verdict")
    check(FOUND["journal record"] > FOUND["alert dispatcher"],
          "H MEASURED: and after the dispatcher, so the published column is this bar's")
check(line_at(OBS_CALL) == "      OBS_Record(closed,rates_total);",
      "H the call passes the same closed index and total every other layer gets")
check(line_at(OBS_GUARD) ==
      "   if(InpEnableDecisionJournal && (is_new_bar || detection_updated || prev_calculated==0))",
      "H the call is gated by the journal flag and by the file's own closed-bar condition, "
      "mirroring the resolver's", "got %r" % line_at(OBS_GUARD)[:96])
check("recorded LAST" in body(OBS_GUARD - 3, OBS_GUARD),
      "H the call site says out loud why it is last")
check("writes only the journal" in body(OBS_GUARD - 3, OBS_GUARD),
      "H and says what it does and does not touch")
check(line_at(TIP_GUARD) == "                  (InpEnableDecisionJournal?",
      "H the tooltip block is gated by the journal's own flag")
check(line_at(TIP_OBS) == '                   OBS_JournalText(InpObsTooltipBars):"")+',
      "H and shows exactly InpObsTooltipBars rows")
check(TIP_OBS > TIP_SCALP, "H the journal is appended after the scalping line (L%d), not before it"
      % TIP_SCALP)
check(line_at(TIP_OBS + 1).startswith('                  "Core state: "'),
      "H the existing tooltip lines below are untouched")

# ------------------------------------------------------- I. the self-test
for i in range(1, 12):
    tag = "OBS-%d" % i
    hits = len(re.findall(r"\b%s\b" % tag, ST))
    check(hits == 2, "I %s appears twice: as the comment and as the failure reason" % tag,
          "got %d" % hits)
check(ST.count("return false; }") == 11, "I all eleven checks can fail the self-test",
      "got %d" % ST.count("return false; }"))
check(ST.rstrip().endswith("return true;\n  }"), "I the self-test ends by passing")
check(line_at(SELFTEST) == "bool OBS_SelfTest(string &where)",
      "I the self-test reports its failure through the shared where-string")
check('where="";' in ST, "I and clears it first, so a stale reason is never reported")
for bad in ("g_buf_", "g_obs_", "ObjectCreate", "Print(", "iTime(", "CopyBuffer(",
            "g_final_signal", "g_wgate_", "g_sc_", "g_alert_primary"):
    check(bad not in ST, "I the self-test touches no %s: it is deterministic and chart-free" % bad)
check("OBS_NextIndex(9,10)!=0" in ST, "I OBS-1 pins the wrap at the cap")
check("OBS_NextIndex(5,-3)!=0" in ST, "I OBS-2 pins a negative cap")
check('OBS_GateStateName(99)!="not-run"' in ST, "I OBS-3 pins an unknown state name")
check("OBS_GateState(false,false,95,60)!=0" in ST,
      "I OBS-4 pins that an unused gate claims no verdict even at 95 points")
check("OBS_GateState(true,true,95,60)!=3" in ST, "I OBS-5 pins that a veto outranks 95 points")
check("OBS_GateState(true,false,59,60)!=2" in ST and "OBS_GateState(true,false,60,60)!=1" in ST,
      "I OBS-6 pins the inclusive minimum from both sides")
check('OBS_Reason(3,"HARD VETO: spread",1,"resolver BUY",0,"")!="HARD VETO: spread"' in ST,
      "I OBS-7 pins that a veto outranks a resolver verdict in the reason text")
check('OBS_Reason(0,"-",2,"both voted",0,"")' in ST, "I OBS-8 pins the resolver-conflict label")
check('OBS_Reason(0,"-",0,"-",2,"legs disagree")' in ST, "I OBS-9 pins the scalping-conflict label")
check('OBS_Reason(0,"-",0,"-",0,"")!="no layer produced a verdict this bar"' in ST,
      "I OBS-10 pins that silence is reported as silence")
check("OBS_SourceName(0)!=\"unset\"" in ST and "OBS_SourceName(9)!=\"unset\"" in ST,
      "I OBS-11 pins that an unknown source is never relabelled")

# ------------------------------------------------------- J. nothing weakened
J_EXACT = {
    853: "input bool   InpUseFinalResolver     = false; // ONE verdict for card STATUS, tactical",
    862: "input bool   InpUseWeightedGates     = false; // OFF = the existing hard-AND chain, unchanged",
    868: "input int    InpWGMinScore           = 60;    // weighted points a candidate needs to be published",
    873: "input bool   InpEnableScalping           = false; // overlay switch: six scalping strategies",
    881: "input int    InpScalpMinScore            = 60;    // weighted points needed to name a scalp",
    885: "input double InpScalpMinRR               = 1.20;  // refuse below this RR (SCALPER preset)",
    5993: '      g_sc_why="HARD VETO: no ATR for this closed bar - a scalp has no cost model - WAIT";',
    6010: '      g_sc_why="HARD VETO: outside the London/New York kill zones - WAIT";',
    6016: '      g_sc_why="HARD VETO: high-impact news blackout (Golden Rule 6) - WAIT";',
    40031: '      why="HARD VETO: invalid candidate data (no direction or no closed bar) - WAIT";',
    40044: '      why="HARD VETO: high-impact news blackout (Golden Rule 6) - WAIT";',
    5829: '   w[1]=InpResWeightZone; nm[1]="zone";',
    5832: "   vote[3]=g_tac_dir;",
}
for ln, want in sorted(J_EXACT.items()):
    check(line_at(ln) == want, "J L%d is unchanged: %r" % (ln, want.strip()[:64]),
          "got %r" % line_at(ln)[:80])
check("InpEnableAllModules        = false" in line_at(898),
      "J the master switch still defaults false and still covers seven modules")
check("OBS" not in line_at(898) and "journal" not in line_at(898).lower(),
      "J the master switch was not widened to include the journal")
check(len(re.findall(r"(?m)^input\s", TEXT)) == 583,
      "J 583 input lines: the 574 already there plus the journal's own nine",
      "got %d" % len(re.findall(r"(?m)^input\s", TEXT)))
check(TEXT.count("{") == TEXT.count("}") == 3593, "J braces balance at 3593",
      "got %d / %d" % (TEXT.count("{"), TEXT.count("}")))
check(len(TEXT.split("\n")) - 1 == 43352, "J the file is 43352 lines",
      "got %d" % (len(TEXT.split("\n")) - 1))
check(RAW.replace("\r\n", "").count("\n") == 0, "J every line still ends CRLF: no bare LF was introduced")
check(TEXT.count("#include") == 1, "J still exactly one #include", "got %d" % TEXT.count("#include"))
check(TEXT.count("PA_ZoneAt(") == 11,
      "J the journal adds no zone scan: PA_ZoneAt( is still at its pre-OBS1 count of 11",
      "got %d" % TEXT.count("PA_ZoneAt("))
check(TEXT.count("WeightedGateAllows(") == 4,
      "J the gate still has one definition and its own call sites: no third opinion",
      "got %d" % TEXT.count("WeightedGateAllows("))
check(TEXT.count("ResolveFinalSignal(") == 4,
      "J the resolver is still one definition, one call, one forward declaration and\n"
      "one comment: the journal adds no fourth opinion",
      "got %d" % TEXT.count("ResolveFinalSignal("))
for name in ("OBS_NextIndex", "OBS_GateStateName", "OBS_GateState", "OBS_Reason",
             "OBS_SourceName", "OBS_Record", "OBS_JournalText", "OBS_SelfTest"):
    defs = len(re.findall(r"(?m)^(?:int|string|void|bool) %s\(" % name, TEXT))
    check(defs == 1, "J %s is defined exactly once" % name, "got %d" % defs)

# ------------------------------------------------------- K. doc and CI
for phrase in ("## 11.6 AUDIT-OBS1", "InpEnableDecisionJournal", "OBS_Record", "OBS_Reason",
               "OBS_SourceName", "ring buffer", "recorded LAST", "1=ZRE, 2=RXN, 3=CORE legacy",
               "tools/test_decision_journal.py", "CI step 35", "583",
               "transcript, not a voter", "no layer produced a verdict this bar"):
    check(phrase in DOCX, "K the doc states %r" % phrase)
check("L6205" in DOCX, "K the doc cites OBS_Record's definition line (L6205)")
check("L889" in DOCX, "K the doc cites the journal flag's line (L889)")
check("L4490" in DOCX, "K the doc cites the row struct's line (L4490)")
check("L15749" in DOCX, "K the doc cites the OnCalculate record call (L15749)")
check(re.search(r"run: python3 tools/test_decision_journal\.py", WFX),
      "K CI runs tools/test_decision_journal.py")
check(WFX.count("- name: ") == 36, "K the workflow has 36 named steps",
      "got %d" % WFX.count("- name: "))
check("AUDIT-OBS1" in WFX, "K the CI step names the audit it enforces")

fails = sum(1 for ok, _, _ in RESULTS if not ok)
print("AUDIT-OBS1 decision journal checks: %d   failures: %d" % (len(RESULTS), fails))
sys.exit(1 if fails else 0)
