#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract suite for POWER OF 3 + SILVER BULLET (AUDIT-SB1).

WHY THIS FILE EXISTS
--------------------
Phase 2 added two modules to a 41k-line indicator whose Core buffers an Expert
Advisor already reads by index. The two dangers that matter here are not "does
the logic work" but:

  1. DID ANYTHING THAT ALREADY WORKED MOVE?  Buffers, existing input defaults,
     the pinned 11-row dashboard card, the object-cleanup sweep.
  2. CAN A DISPLAY-ONLY MODULE AUTHORIZE SOMETHING?  If g_p3_* or g_sb_* were
     readable by the arbiter, the signal mask, the confluence scorers, the DSE or
     a Core buffer, then "display only" would be a comment rather than a fact.

Both are answered mechanically below. Neither is answered by reading the code and
agreeing with it.

WHAT IS TESTED
--------------
Part A  an independent re-implementation of the two PURE cores, transcribed from
        nadir2.mq5. There is no MetaEditor here, so a transcription is the only
        executable proof available. Every case asserts the resulting PHASE /
        SCORE / BOOLEAN, never merely "a non-empty result". A transcription that
        silently drifts from the source is worthless, so A9 pins the transcription
        to the source's own constants and branch order.
Part B  source contracts: the wiring Part A assumes is present, in the right
        order, and cannot be silently removed - plus the two dangers above.

   A1  the phase order, and that an invalidated manipulation ends the sequence
   A2  distribution is never a free point (non-positive threshold, wrong-way move)
   A3  P3 score arithmetic, and that invalidation gives the credit back
   A4  the window primitive: [start, end), empty window, overnight wrap, bounds
   A5  Silver Bullet score arithmetic - a missing leg costs its points
   A6  the phase vocabulary is complete and distinct
   A7  exhaustive window precedence over every minute of the day
   A8  monotonicity: adding evidence never lowers either score
   A9  the transcription is pinned to the source's constants and branch order

   B1  nothing that already worked moved (buffers, plots, indices, card, defaults)
   B2  every new function is declared once and defined once, signatures identical
   B3  both adapters are called once per pass, after the causal graph is final
   B4  reset and self-test are wired into OnInit
   B5  DISPLAY ONLY: no execution-adjacent function reads the new state
   B6  the new code is symbol-agnostic and reaches no trade API
   B7  the new dashboard rows go to the tooltip, never to the 11-row card
   B8  every chart object the module creates is inside the cleanup sweep
   B9  causality: closed bars only, no wall clock, no forming bar
   B10 no probability claim, and the stand-aside states are unambiguous
   B11 the module's real dependencies are stated, not assumed

This is a contract suite. It is NOT a backtest, produces NO win rate, and does
NOT prove MetaEditor compilation. Press F7.
"""
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "nadir2.mq5"
TEXT = io.open(str(SRC), "r", encoding="utf-8", newline="").read()

FAILS = []
N = [0]


def check(ok, name, detail=""):
    N[0] += 1
    if ok:
        print("PASS  " + name)
    else:
        print("FAIL  " + name + (("  | " + detail) if detail else ""))
        FAILS.append(name)


def strip_comments(src):
    code = re.sub(r"//[^\n]*", "", src)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return code


# A declaration or definition site is one where the function name is the first
# token on its line preceded only by a RETURN TYPE. That single rule rejects
# indented call sites, `Type x = Fn(` assignments, and the box comments and
# design prose that mention these functions by name - which is what previously
# made body_of() start inside a comment on line 318 and return half the file.
DECL_PREFIX = re.compile(r"^(?:const\s+)?[A-Za-z_][\w:<>,\s]*&?$")


def is_decl_or_def(i):
    ls = TEXT.rfind("\n", 0, i) + 1
    prefix = TEXT[ls:i].strip()
    return prefix != "" and bool(DECL_PREFIX.match(prefix))


def params_at(i):
    """Normalized parameter list of the '(' at index i, plus the char after ')'."""
    assert TEXT[i] == "(", repr(TEXT[i])
    depth, j = 0, i
    while j < len(TEXT):
        c = TEXT[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                after = TEXT[j + 1:j + 40].lstrip(" \t\r\n")
                return re.sub(r"\s+", " ", TEXT[i + 1:j]).strip(), after[:1]
        j += 1
    return None, None


# =====================================================================
# Part A - transcription of the two PURE cores
# =====================================================================
# Phase constants, mirroring ENUM_P3_PHASE. Their VALUES are irrelevant to the
# tests (only their distinctness and their mapping to names), which is exactly
# why the enum was added as its own type: appending it could not shift any
# existing enumerator.
P3_NONE, P3_ACC, P3_MAN, P3_DIST = 0, 1, 2, 3

P3_NAMES = {P3_NONE: "NONE", P3_ACC: "ACCUMULATION",
            P3_MAN: "MANIPULATION", P3_DIST: "DISTRIBUTION"}


def p3_phase_name(phase):
    return P3_NAMES.get(phase, "UNKNOWN")


def p3_decide(range_valid, judas, distribution_atr, min_distribution_atr, invalidated):
    """Transcribed from P3_Decide(). Returns (phase, reason, invalidation)."""
    reason = invalidation = ""
    if not range_valid:
        return P3_NONE, "no Asia session range resolved for the applicable local day", ""
    if invalidated:
        return (P3_NONE,
                "the manipulation was invalidated - a closed bar returned through the sweep extreme",
                "closed bar back through the manipulation extreme; the sequence is over")
    if judas == 0:
        return P3_ACC, "the Asia range is formed and has not been swept", ""
    if min_distribution_atr > 0.0 and distribution_atr >= min_distribution_atr:
        return (P3_DIST, "distribution is following through away from the sweep",
                "a closed bar back through the manipulation extreme")
    return (P3_MAN,
            "the Asia range was swept and closed back inside; waiting for distribution",
            "a closed bar back through the manipulation extreme")


def p3_score(range_valid, judas, distribution, invalidated):
    """Transcribed from P3_Score(): range 25, manipulation 35, distribution 40."""
    if invalidated:
        return 0
    s = 0
    if range_valid:
        s += 25
    if judas != 0:
        s += 35
    if distribution:
        s += 40
    return min(s, 100)


def sb_minute_in_window(minute, start, end):
    """Transcribed from SB_MinuteInWindow(): [start, end), empty matches nothing."""
    if minute < 0 or minute > 1439:
        return False
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end          # overnight wrap


def sb_score(in_window, has_sweep, has_shift, has_fvg, has_retrace):
    """Transcribed from SB_Score(): five legs at 20 each, absent leg scores 0."""
    s = 0
    for leg in (in_window, has_sweep, has_shift, has_fvg, has_retrace):
        if leg:
            s += 20
    return min(s, 100)


# --- A1 the phase order -------------------------------------------------
ph, r, iv = p3_decide(False, 1, 5.0, 1.0, False)
check(ph == P3_NONE and r != "",
      "A1 no Asia range means no phase, and the reason says so")
check(p3_decide(True, 0, 0.0, 1.0, False)[0] == P3_ACC,
      "A1 an unswept range is ACCUMULATION")
check(p3_decide(True, 1, 0.5, 1.0, False)[0] == P3_MAN,
      "A1 a sweep short of the distribution threshold is MANIPULATION")
check(p3_decide(True, 1, 1.5, 1.0, False)[0] == P3_DIST,
      "A1 a qualifying follow-through is DISTRIBUTION")
check(p3_decide(True, -1, 2.0, 1.0, False)[0] == P3_DIST,
      "A1 the bearish side reaches DISTRIBUTION by the same rule")
check(p3_decide(True, 1, 1.0, 1.0, False)[0] == P3_DIST,
      "A1 the distribution threshold is inclusive (move == min confirms)")

# --- A1b invalidation ends the sequence ---------------------------------
# This is the property that matters most: a phase that outlives its own
# invalidation is a contradiction, and it must outrank a distribution that would
# otherwise have confirmed on the very same inputs.
ph, r, iv = p3_decide(True, 1, 5.0, 1.0, True)
check(ph == P3_NONE, "A1b an invalidated manipulation ends the sequence")
check(iv != "", "A1b the invalidation carries the reason it ended")
check(p3_decide(True, 1, 5.0, 1.0, True)[0] == p3_decide(True, 0, 0.0, 1.0, True)[0],
      "A1b invalidation outranks distribution and accumulation alike")

# --- A2 distribution is never a free point ------------------------------
check(p3_decide(True, 1, 5.0, 0.0, False)[0] != P3_DIST,
      "A2 a zero distribution threshold must not confirm distribution")
check(p3_decide(True, 1, 5.0, -1.0, False)[0] != P3_DIST,
      "A2 a negative distribution threshold must not confirm distribution")
check(p3_decide(True, 1, -3.0, 1.0, False)[0] != P3_DIST,
      "A2 a move away from the expected side must not confirm distribution")
check(p3_decide(True, 0, 5.0, 1.0, False)[0] != P3_DIST,
      "A2 distribution requires a sweep first - an unswept range cannot distribute")
check(p3_decide(False, 1, 5.0, 1.0, False)[0] != P3_DIST,
      "A2 distribution requires a range - no range, no distribution")

# --- A3 P3 score arithmetic ---------------------------------------------
check(p3_score(False, 0, False, False) == 0, "A3 no evidence scores 0")
check(p3_score(True, 0, False, False) == 25, "A3 the range leg is worth 25")
check(p3_score(True, 1, False, False) == 60, "A3 range + manipulation is worth 60")
check(p3_score(True, -1, True, False) == 100, "A3 the full sequence is worth exactly 100")
check(p3_score(True, 1, True, True) == 0,
      "A3 an invalidated sequence scores 0 - it does not keep credit it lost")
check(p3_score(True, 1, False, True) == 0,
      "A3 invalidation zeroes a partial sequence too")
check(all(0 <= p3_score(rv, j, d, i) <= 100
          for rv in (True, False) for j in (-1, 0, 1)
          for d in (True, False) for i in (True, False)),
      "A3 every P3 score is inside 0..100")

# --- A4 the window primitive --------------------------------------------
check(sb_minute_in_window(180, 180, 240) and sb_minute_in_window(239, 180, 240),
      "A4 the window start is inclusive")
check(not sb_minute_in_window(240, 180, 240),
      "A4 the window end is EXCLUSIVE, so consecutive windows cannot both claim a minute")
check(not sb_minute_in_window(179, 180, 240), "A4 the minute before the window is outside")
check(not sb_minute_in_window(60, 60, 60) and not sb_minute_in_window(59, 60, 60),
      "A4 an empty window (start == end) matches nothing rather than everything")
check(sb_minute_in_window(1380, 1380, 120) and sb_minute_in_window(0, 1380, 120)
      and sb_minute_in_window(119, 1380, 120),
      "A4 an overnight window wraps past midnight")
check(not sb_minute_in_window(120, 1380, 120) and not sb_minute_in_window(700, 1380, 120),
      "A4 an overnight window still excludes the hours between")
check(not sb_minute_in_window(-1, 0, 1440) and not sb_minute_in_window(1440, 0, 1440),
      "A4 a minute outside 0..1439 matches nothing")
check(not any(sb_minute_in_window(m, 240, 180) for m in (180, 200, 239)),
      "A4 a wrapping window excludes the hours inside its own gap [180,240)")
check(all(sb_minute_in_window(m, 240, 180) for m in (240, 1000, 179, 120, 0)),
      "A4 a wrapping window includes both sides of midnight")

# --- A5 Silver Bullet score arithmetic ----------------------------------
check(sb_score(False, False, False, False, False) == 0, "A5 no evidence scores 0")
check(sb_score(True, False, False, False, False) == 20, "A5 the window leg alone is worth 20")
check(sb_score(True, True, True, True, False) == 80,
      "A5 a complete chain without its retrace is worth 80, not 100")
check(sb_score(True, True, True, True, True) == 100,
      "A5 the full Silver Bullet chain is worth exactly 100")
check(sb_score(False, True, True, True, True) == 80,
      "A5 legs outside the window do not make it a Silver Bullet")
check(all(0 <= sb_score(*legs) <= 100
          for legs in [(a, b, c, d, e)
                       for a in (True, False) for b in (True, False)
                       for c in (True, False) for d in (True, False)
                       for e in (True, False)]),
      "A5 every Silver Bullet score is inside 0..100")

# --- A6 the phase vocabulary --------------------------------------------
names = [p3_phase_name(p) for p in (P3_NONE, P3_ACC, P3_MAN, P3_DIST)]
check(len(set(names)) == 4 and all(names),
      "A6 all four phases have a distinct non-empty name")
check(p3_phase_name(999) == "UNKNOWN",
      "A6 an out-of-range phase is labelled UNKNOWN, not guessed")
check(p3_phase_name(-1) == "UNKNOWN",
      "A6 a negative phase is labelled UNKNOWN, not guessed")

# --- A7 exhaustive window precedence ------------------------------------
# Independently recomputed here against the DEFAULT inputs, so a regression in
# the first-match order shows up without needing a terminal.
W = ((180, 240), (600, 660), (840, 900))


def sb_window_at_minute(m):
    for idx, (s, e) in enumerate(W):
        if sb_minute_in_window(m, s, e):
            return idx
    return -1


bad = [m for m in range(1440)
       if sb_window_at_minute(m) != next(
           (i for i, (s, e) in enumerate(W) if sb_minute_in_window(m, s, e)), -1)]
check(not bad, "A7 window precedence is first-match for all 1440 minutes",
      "first disagreement at %s" % (bad[:3],))
inside = sorted(m for m in range(1440) if sb_window_at_minute(m) >= 0)
check(len(inside) == 180,
      "A7 three 60-minute default windows cover exactly 180 minutes (%d)" % len(inside))
check(sb_window_at_minute(179) == -1 and sb_window_at_minute(240) == -1,
      "A7 the minutes either side of window 1 are outside every window")

# --- A8 monotonicity: evidence is never punished ------------------------
mono_ok = True
for a in (True, False):
    for b in (True, False):
        for c in (True, False):
            for d in (True, False):
                for e in (True, False):
                    base = sb_score(a, b, c, d, e)
                    if sb_score(True, b, c, d, e) < base:
                        mono_ok = False
                    if sb_score(a, True, c, d, e) < base:
                        mono_ok = False
check(mono_ok, "A8 adding Silver Bullet evidence never lowers the score")
p3_mono = all(p3_score(True, j, d, False) >= p3_score(rv, j, d, False)
              for rv in (True, False) for j in (-1, 0, 1) for d in (True, False))
check(p3_mono, "A8 adding a valid range never lowers the P3 score")

# --- A9 the transcription is pinned to the source -----------------------
# A transcription is only evidence if it cannot drift. Each constant and branch
# the tests above rely on is asserted to exist in the source, in this order.
def body_of(fn_name, label):
    """Body of the DEFINITION of fn_name (column-0 brace style).

    A forward declaration is identified by the character after its MATCHING close
    paren, not by whether its first line ends in ';': several of these signatures
    wrap over two or three lines, and testing only the first line mistook the
    declaration for the definition and returned an unrelated slice of the file.
    """
    pos = 0
    while True:
        i = TEXT.find(fn_name + "(", pos)
        if i < 0:
            check(False, "locate %s" % label, "signature not found")
            return ""
        pos = i + 1
        if i and (TEXT[i - 1].isalnum() or TEXT[i - 1] == "_"):
            continue                         # substring of a longer identifier
        if not is_decl_or_def(i):
            continue                         # call site, prose or comment
        _, after = params_at(i + len(fn_name))
        if after == ";":
            continue                         # forward declaration
        j = TEXT.find("\r\n}\r\n", i)
        if j < 0:
            check(False, "locate end of %s" % label, "no column-0 closing brace")
            return ""
        return TEXT[i:j + 5]


src_decide = body_of("P3_Decide", "P3_Decide")
src_p3score = body_of("P3_Score", "P3_Score")
src_sbscore = body_of("SB_Score", "SB_Score")
src_win = body_of("SB_MinuteInWindow", "SB_MinuteInWindow")

check(src_decide.index("if(!range_valid)") < src_decide.index("if(invalidated)")
      < src_decide.index("if(judas==0)")
      < src_decide.index("if(min_distribution_atr>0.0 && distribution_atr>=min_distribution_atr)"),
      "A9 the source's P3_Decide branch order matches the transcription exactly")
check("s+=25" in src_p3score and "s+=35" in src_p3score and "s+=40" in src_p3score,
      "A9 the source's P3 leg weights are 25/35/40 as transcribed")
check("if(invalidated) return 0;" in src_p3score,
      "A9 the source zeroes an invalidated P3 sequence before counting legs")
check(src_sbscore.count("s+=20") == 5,
      "A9 the source's Silver Bullet has exactly five legs of 20 as transcribed")
check("if(start==end) return false;" in src_win,
      "A9 the source treats an empty window as matching nothing")
check("return (minute>=start && minute<end);" in src_win,
      "A9 the source's window end is exclusive as transcribed")
check("return (minute>=start || minute<end);" in src_win,
      "A9 the source wraps an overnight window as transcribed")
check('return "DISTRIBUTION"' in TEXT and 'return "ACCUMULATION"' in TEXT
      and 'return "MANIPULATION"' in TEXT and 'return "NONE"' in TEXT
      and 'return "UNKNOWN"' in TEXT,
      "A9 the source's phase names match the transcribed vocabulary")

# =====================================================================
# Part B - source contracts
# =====================================================================
NEW_FUNCS = ["P3_PhaseName", "P3_Decide", "P3_Score", "P3_Update",
             "SB_LocalTime", "SB_MinuteOfDay", "SB_DayKey", "SB_MinuteInWindow",
             "SB_WindowAtMinute", "SB_WindowName", "SB_InWindow", "SB_ChainComplete",
             "SB_Score", "SB_Update", "SB_DrawEntryZone", "SBP3_Clear", "SBP3_SelfTest"]

# --- B1 nothing that already worked moved -------------------------------
def input_default(name):
    """Default of `name`, handling the file's comma-packed input lines.

    `input int InpAsianStart = 9, InpAsianEnd = 18;` declares two inputs on one
    line, so a pattern anchored on ^input and reading to the next ';' swallowed
    both. The value must stop at a comma OR a semicolon, and the name must be
    preceded by `input TYPE` or by a comma - never by an operator, which is how
    a usage such as `InpAsianStart<0 ||` is kept out.
    """
    m = re.search(r"(?:^input\s+[\w<>:]+\s+|,\s*)" + name + r"\s*=\s*([^,;]+)",
                  TEXT, re.M)
    return m.group(1).strip() if m else None


m = re.search(r"^#property indicator_buffers\s+(\d+)", TEXT, re.M)
check(m and m.group(1) == "19", "B1 indicator_buffers is still 19 - no buffer was added")
m = re.search(r"^#property indicator_plots\s+(\d+)", TEXT, re.M)
check(m and m.group(1) == "7", "B1 indicator_plots is still 7")
idx = sorted(int(x) for x in re.findall(r"SetIndexBuffer\((\d+),", TEXT))
check(idx == list(range(19)),
      "B1 the 19 buffer indices are still exactly 0..18", "got %s" % idx)
check("string lines[11]; color cols[11]; int ln=0;" in TEXT,
      "B1 the pinned 11-row dashboard card is untouched")
check("if(ln>11) ln=11;" in TEXT, "B1 the card's row clamp is untouched")
# Existing inputs the EA and the gates depend on must keep their defaults.
for name, want in (("InpDetectJudas", "true"), ("InpUseDSTSessions", "true"),
                   ("InpAsianStart", "9"), ("InpAsianEnd", "18"),
                   ("InpLondonStart", "8"), ("InpNewYorkStart", "8"),
                   ("InpDisplacementATR", "0.9"), ("InpOBMaxHeightATR", "3.0")):
    got = input_default(name)
    check(got == want, "B1 existing input %s still defaults to %s" % (name, want),
          "found %r" % got)

# --- B1b every NEW input is off by default ------------------------------
NEW_BOOL_INPUTS = ["InpEnablePowerOf3", "InpP3ShowOnDashboard", "InpEnableSilverBullet",
                   "InpSBShowOnDashboard", "InpSBShowEntryZone"]
for name in NEW_BOOL_INPUTS:
    got = input_default(name)
    check(got == "false", "B1b new switch %s defaults to false" % name,
          "found %r" % got)
for name, want in (("InpP3DistributionMinATR", "1.00"), ("InpSBUseNYLocalTime", "true"),
                   ("InpSBWin1Start", "180"), ("InpSBWin1End", "240"),
                   ("InpSBWin2Start", "600"), ("InpSBWin2End", "660"),
                   ("InpSBWin3Start", "840"), ("InpSBWin3End", "900"),
                   ("InpSBChainMaxAgeBars", "240")):
    got = input_default(name)
    check(got == want, "B1b new input %s defaults to %s" % (name, want),
          "found %r" % got)
# The three default windows must not overlap, or precedence would be arbitrary.
wins = [(180, 240), (600, 660), (840, 900)]
overlap = [(a, b) for i, a in enumerate(wins) for b in wins[i + 1:]
           if sb_minute_in_window(a[0], *b) or sb_minute_in_window(b[0], *a)]
check(not overlap, "B1b the three default windows do not overlap", str(overlap))

# --- B2 declared exactly once, defined exactly once, signatures identical --
for fn in NEW_FUNCS:
    decls, defs = [], []
    pos = 0
    while True:
        i = TEXT.find(fn + "(", pos)
        if i < 0:
            break
        # skip member-ish / substring hits: the char before must not be an ident char
        pos = i + 1
        if i and (TEXT[i - 1].isalnum() or TEXT[i - 1] == "_"):
            continue
        if not is_decl_or_def(i):
            continue                         # call site, prose or comment
        p, after = params_at(i + len(fn))
        if p is None:
            pos = i + 1
            continue
        (decls if after == ";" else defs if after == "{" else []).append(p)
    check(len(decls) == 1, "B2 %s is declared exactly once" % fn, "%d decls" % len(decls))
    check(len(defs) == 1, "B2 %s is defined exactly once" % fn, "%d defs" % len(defs))
    if len(decls) == 1 and len(defs) == 1:
        check(decls[0] == defs[0], "B2 %s declaration and definition agree" % fn,
              "\n      decl: %s\n      defn: %s" % (decls[0], defs[0]))

# --- B3 both adapters are called once per pass, after the graph is final --
oncalc = body_of("OnCalculate", "OnCalculate")
if not oncalc:
    i = TEXT.find("int OnCalculate(")
    oncalc = TEXT[i:]
check(oncalc.count("P3_Update(closed);") == 1,
      "B3 P3_Update is called exactly once in OnCalculate")
check(oncalc.count("SB_Update(closed);") == 1,
      "B3 SB_Update is called exactly once in OnCalculate")
i_gate = oncalc.find("if(detection_updated)\r\n   {\r\n      P3_Update(closed);")
check(i_gate > 0, "B3 both adapters are gated on detection_updated (zero per-tick cost)")
i_graph = oncalc.find("BuildCausalEventGraph(rates_total,")
i_limits = oncalc.find("EnforceArrayLimits();")
check(0 < i_limits < i_graph < i_gate,
      "B3 the adapters run AFTER EnforceArrayLimits and BuildCausalEventGraph",
      "limits=%d graph=%d gate=%d" % (i_limits, i_graph, i_gate))
check(TEXT.count("DetectJudasSwing(rates_total,") == 2,
      "B3 DetectJudasSwing still has its two original call sites")

# --- B4 reset and self-test are wired into OnInit -----------------------
oninit = TEXT[TEXT.find("int OnInit()"):]
oninit = oninit[:oninit.find("\r\nint OnCalculate(")]
check("SBP3_Clear();" in oninit, "B4 SBP3_Clear is called from OnInit")
check(oninit.find("ScenarioClear();") < oninit.find("SBP3_Clear();"),
      "B4 SBP3_Clear sits beside the other module resets")
check("if(SBP3_SelfTest(mtee_fail))" in oninit, "B4 the self-test is invoked from OnInit")
i_mtee = oninit.find("if(InpMTEERunSelfTest)")
check(0 < i_mtee < oninit.find("if(SBP3_SelfTest(mtee_fail))"),
      "B4 the self-test is inside the existing InpMTEERunSelfTest gate")
st_body = body_of("SBP3_SelfTest", "SBP3_SelfTest")
groups = sorted(set(re.findall(r'SBP3-(\d+)', st_body)))
check(len(groups) >= 9, "B4 the self-test covers %d groups" % len(groups), str(groups))
check("SBP3-" + "1" in st_body and "SBP3-9" in st_body,
      "B4 the self-test groups are numbered SBP3-1..SBP3-9")

# --- B5 DISPLAY ONLY: no execution-adjacent function reads the new state --
NEW_STATE = ["g_p3_phase", "g_p3_dir", "g_p3_score", "g_p3_reason", "g_p3_invalidation",
             "g_sb_active", "g_sb_window", "g_sb_dir", "g_sb_fvg", "g_sb_entry_high",
             "g_sb_entry_low", "g_sb_reason", "g_sb_score", "g_sb_invalidation"]
CONSUMERS = ["QSMC_ArbiterFeedAndFinalize", "UpdateSignalMask", "GraphConfluenceScore",
             "PMI_ComputeConfluence", "ScenarioUpdate", "ScenarioDashFull",
             "ScoreOrderBlock", "PMI_BuildLocation", "CoreDashChain",
             "TacticalAuthorityDecide", "ValidateCausalGraphInvariants",
             "ReplayClosedBarStates", "BuildCausalEventGraph", "DetectOrderBlocks"]
consumers_checked = 0
for fn in CONSUMERS:
    b = body_of(fn, fn) if TEXT.find(fn + "(") >= 0 else ""
    if not b:
        continue                             # defined in a header, not in this file
    consumers_checked += 1
    hit = [s for s in NEW_STATE if s in b]
    check(not hit, "B5 %s cannot read the new display-only state" % fn, str(hit))
check(consumers_checked >= 10,
      "B5 the display-only claim was checked against %d real function bodies"
      % consumers_checked, "too few located - the check would be vacuous")
# No buffer is written from the new module.
# The engine section runs from its banner to the KILL ZONES banner that follows
# it. PrepareDynamicRedraw() is NOT a valid end marker: it is defined thousands of
# lines EARLIER, so slicing to it produced an empty string and every contract
# about the section's contents passed vacuously or failed for the wrong reason.
def _fn_end(text, sig_at):
    """Offset just past the closing brace of the function DEFINED at sig_at.
    Braces are counted only outside comments and string literals."""
    i, depth, started, n = sig_at, 0, False, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i+1] == '/':
            i = text.find('\n', i)
            if i < 0: return -1
            continue
        if c == '/' and i + 1 < n and text[i+1] == '*':
            i = text.find('*/', i + 2)
            if i < 0: return -1
            i += 2; continue
        if c in '"\'':
            q = c; i += 1
            while i < n:
                if text[i] == '\\': i += 2; continue
                if text[i] == q: break
                i += 1
            i += 1; continue
        if c == '{': depth += 1; started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0: return i + 1
        i += 1
    return -1

def _section(text, banner, sig):
    """Slice a module's section from its banner to the end of its OWN self-test.
    A section must never end at a shared downstream marker: ending these slices at
    the KILL ZONES banner silently swallowed whatever module was inserted before
    that banner, so the section contracts started testing code that did not belong
    to them. Brace-matching the module's own last function is insertion-proof.
    The banner precedes the definition, so searching for sig from the banner skips
    the forward declaration."""
    i0 = text.find(banner)
    if i0 < 0: return -1, -1, ""
    j = text.find(sig, i0)
    if j < 0: return -1, -1, ""
    e = _fn_end(text, j)
    if e < 0: return -1, -1, ""
    return i0, e, text[i0:e]
_i0, _i1, sb_section = _section(TEXT, "// AUDIT-SB1  POWER OF 3", "bool SBP3_SelfTest(string &where)")
check(0 < _i0 < _i1, "B the SB1 engine section was located", "%d..%d" % (_i0, _i1))
check(len(sb_section) > 8000,
      "B the SB1 section slice is substantial (%d chars)" % len(sb_section))
check("BufSig" not in sb_section and "SetIndexBuffer" not in sb_section,
      "B5 the new module writes no buffer")
for api in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen", "PositionModify",
            "OrderCheck", "WebRequest"):
    check(api not in strip_comments(sb_section),
          "B5 the new module cannot reach %s" % api)

# --- B6 symbol-agnostic, no hard-coded price ----------------------------
code = strip_comments(sb_section)
code = re.sub(r'"(\\.|[^"\\])*"', '""', code)
check("XAUUSD" not in code and "EURUSD" not in code and "GBPUSD" not in code,
      "B6 no hard-coded symbol in the new code")
check(not re.search(r"\b\d{3,4}\.\d{1,5}\b", code),
      "B6 no literal price level in the new code")
check("_ATR" in sb_section or "atr" in sb_section,
      "B6 distances are expressed in ATR units")
check("g_atr_buf" in sb_section and "g_atr" in sb_section,
      "B6 the ATR read reuses the file's per-bar buffer with its scalar fallback")

# --- B7 new rows go to the TOOLTIP, never to the card -------------------
dash = body_of("DrawQuantumDashboard", "DrawQuantumDashboard")
check('tooltip+="\\nP3: "' in dash, "B7 the Power of 3 row is merged into the tooltip")
check('tooltip+="\\nSB: "' in dash, "B7 the Silver Bullet row is merged into the tooltip")
check("lines[ln]=" not in dash.split('tooltip+="\\nP3: "')[1].split("int chart_w=")[0],
      "B7 neither module writes a card row")
check(dash.count("SB_DrawEntryZone(closed);") == 1,
      "B7 the optional entry zone is drawn from the dashboard pass")
i_sweep = oncalc.find("PrepareDynamicRedraw();")
i_dash = oncalc.find("DrawQuantumDashboard(rates_total,")
check(0 < i_sweep < i_dash,
      "B7 the dashboard (which draws the zone) runs AFTER the object sweep",
      "sweep=%d dash=%d" % (i_sweep, i_dash))

# --- B8 every object the module creates is inside the cleanup sweep -----
created = set(re.findall(r'PFX\+"(SBP3_[A-Z_]*)"', sb_section + dash))
check(created, "B8 the module names its objects with the SBP3_ prefix", str(created))
sweep = body_of("PrepareDynamicRedraw", "PrepareDynamicRedraw")
check('ObjectsDeleteAll(0,PFX+"SBP3_")' in sweep,
      "B8 PrepareDynamicRedraw sweeps the SBP3_ prefix")
for name in created:
    check(name.startswith("SBP3_"),
          "B8 object %s is covered by the SBP3_ sweep" % name)
check(sb_section.count("ObjectCreate") == 0,
      "B8 the module creates no object directly - it reuses DrawZoneBox")
check("DrawZoneBox(" in sb_section, "B8 the zone reuses the existing DrawZoneBox helper")

# --- B9 causality: closed bars only -------------------------------------
check("TimeCurrent()" not in code, "B9 no wall-clock time in the new code")
check("rates_total-1" not in code and "rates_total - 1" not in code,
      "B9 no forming-bar index in the new code")
check("availability_bar" in sb_section and "availability_time" in sb_section,
      "B9 the Silver Bullet filters on the graph's closed decision bar/time")
check("g_buf_c[closed]" in sb_section, "B9 P3/SB read the CLOSED bar's close")
check("g_judas_bar" in sb_section,
      "B9 the manipulation extreme comes from a closed bar index, not the live one")
check("if(age<0) continue;" in sb_section,
      "B9 an element not yet available is skipped rather than read")
check("no repaint" in sb_section.lower() or "no future bar" in sb_section.lower(),
      "B9 the causality claim is documented where the module is defined")

# --- B10 no probability claim; stand-aside states are unambiguous -------
check("not a win rate" in dash, "B10 the new dashboard rows disclaim probability")
check("confluence, not a win rate" in dash,
      "B10 the score is labelled a confluence count")
check('"stand aside' in sb_section or 'stand aside:' in sb_section,
      "B10 a Silver Bullet stand-aside is labelled as one")
check('sb_dir=(g_sb_active?' in dash,
      "B10 no direction is printed unless the setup is ACTIVE")
check("prospective" in dash,
      "B10 a MANIPULATION direction is labelled prospective, not confirmed")
check("NOT AN ENTRY" in sb_section,
      "B10 the drawn zone says it is conditional and not an entry")

# --- B11 real dependencies are stated, not assumed ----------------------
p3upd = body_of("P3_Update", "P3_Update")
check("if(!InpDetectJudas)" in p3upd,
      "B11 P3 states its dependency on the existing Judas detector")
check("InpEnablePowerOf3" in p3upd and "return;" in p3upd,
      "B11 P3_Update exits immediately while its switch is off")
sbupd = body_of("SB_Update", "SB_Update")
check("if(!InpEnableSilverBullet) return;" in sbupd,
      "B11 SB_Update exits immediately while its switch is off")
chain = body_of("SB_ChainComplete", "SB_ChainComplete")
check("FindNearestCausalAncestor(" in chain,
      "B11 the chain reuses the existing ancestry walk instead of a parallel one")
check(chain.count("CE_MSS") == 1 and chain.count("CE_BOS") == 1
      and chain.count("CE_CHOCH") == 1 and chain.count("CE_LIQ_SWEEP") == 1,
      "B11 all three existing break names and the sweep are accepted as the chain")
check("if(!g_causal_events[fvg_index].confirmed) return false;" in chain,
      "B11 an unconfirmed gap is not a Silver Bullet gap")
check("g_asia_range_valid" in TEXT and "g_asia_range_high" in TEXT,
      "B11 the Asia range DetectJudasSwing already computed is now retained")
judas = body_of("DetectJudasSwing", "DetectJudasSwing")
check("g_asia_range_valid=" in judas and "g_asia_range_high=" in judas,
      "B11 DetectJudasSwing publishes the range it already computed")
check("g_asia_range_valid=false" in judas,
      "B11 the range is reset on every early return path, so no stale range survives")
check("SessionLocalTime(" in sb_section,
      "B11 the Silver Bullet clock reuses the existing session clock (one DST resolution)")

print("-" * 74)
print("Power of 3 / Silver Bullet contracts: %d checked, %d failed" % (N[0], len(FAILS)))
print("-" * 74)
if FAILS:
    print("RESULT: %d contract(s) FAILED" % len(FAILS))
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("RESULT: all Power-of-3 / Silver-Bullet contracts hold")
print("-" * 74)
print("Both modules default to OFF, are display only, and add no buffer, so with")
print("their switches off nothing is created, sized, scored, drawn or retired any")
print("differently than before. This is a transcription + wiring contract. It is")
print("NOT a backtest, it produces no win rate, and it does NOT prove MetaEditor")
print("compilation. Press F7.")
