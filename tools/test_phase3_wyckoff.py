#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract suite for WYCKOFF SPRING / UPTHRUST (AUDIT-WY1).

WHY THIS FILE EXISTS
--------------------
Phase 3 adds a module that reads a RANGE and a SWEEP of it - two things this file
already has opinions about. DetectJudasSwing() sweeps the Asia session range, and
DetectLiquidity() clusters equal highs and lows into EQH/EQL pools. A new Wyckoff
module could have quietly become a third, contradictory opinion about the same bar.

So the contracts that matter here are the ones about RELATIONSHIPS, not just the
ones about the new code in isolation:

  1. Does the module reuse the existing sweep confirmation, or invent a second,
     looser idea of what makes a wick credible?
  2. Can it contradict the Judas verdict on the same bar and still show a
     direction?
  3. Can the bar being tested widen the range it is supposed to pierce? That would
     be a look-ahead in disguise: a Spring whose own wick defines the range low can
     never fail to pierce it.
  4. Did anything that already worked move?

WHAT IS TESTED
--------------
Part A  an independent re-implementation of the PURE cores, transcribed from
        nadir2.mq5. There is no MetaEditor here, so a transcription is the only
        executable proof available. Every case asserts the resulting EVENT, SCORE
        or BOOLEAN, never merely "a non-empty result". A11 pins the transcription
        to the source's own constants and branch order, because a transcription
        that can drift is not evidence.
Part B  source contracts, including the four relationships above.

   A1  range validity: enough bars, height inside the cap, two touches per side
   A2  nothing is given the benefit of the doubt (unmeasured height, bad cap)
   A3  Spring, A4 Upthrust
   A5  both boundaries pierced and closed inside: refuses to name a side
   A6  pierced but closed OUTSIDE is a break, and is named as one
   A7  no range, no event
   A8  score arithmetic, and a conflict scores 0
   A9  event vocabulary, A10 monotonicity
   A11 the transcription is pinned to the source

   B1  nothing that already worked moved (buffers, plots, indices, card, defaults)
   B2  every new function declared once, defined once, signatures identical
   B3  WY_Update is called once per pass, after the state it reads is final
   B4  reset and self-test are wired into OnInit
   B5  DISPLAY ONLY: no execution-adjacent function can read the new state
   B6  symbol-agnostic, no trade API
   B7  tooltip rows, never the 11-row card
   B8  every object is inside the cleanup sweep
   B9  CAUSALITY: the range ends at closed-1, so the test bar cannot widen it
   B10 no probability claim, no direction unless active, conflict has no direction
   B11 REUSE: the existing sweep validator, tolerance idiom and Judas reconciliation

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


# A declaration or definition site is one where the name is the first token on its
# line preceded only by a RETURN TYPE. That single rule rejects indented call
# sites, `Type x = Fn(` assignments, and the box comments and design prose that
# mention these functions by name.
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


def body_of(fn_name, label):
    """Body of the DEFINITION of fn_name (this file's column-0 brace style)."""
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


def input_default(name):
    """Default of `name`, handling the file's comma-packed input lines."""
    m = re.search(r"(?:^input\s+[\w<>:]+\s+|,\s*)" + name + r"\s*=\s*([^,;]+)",
                  TEXT, re.M)
    return m.group(1).strip() if m else None


# =====================================================================
# Part A - transcription of the PURE cores
# =====================================================================
WY_NONE, WY_SPRING, WY_UPTHRUST = 0, 1, 2
WY_NAMES = {WY_NONE: "NONE", WY_SPRING: "SPRING", WY_UPTHRUST: "UPTHRUST"}


def wy_event_name(event):
    return WY_NAMES.get(event, "UNKNOWN")


def wy_range_valid(bars_in_range, min_bars, height_atr, max_height_atr,
                   touches_high, touches_low, min_touches):
    """Transcribed from WY_RangeValid()."""
    if bars_in_range < 3:
        return False
    if min_bars > 0 and bars_in_range < min_bars:
        return False
    if max_height_atr <= 0.0:
        return False
    if not height_atr > 0.0:
        return False
    if height_atr >= max_height_atr:
        return False
    if min_touches > 0:
        if touches_high < min_touches:
            return False
        if touches_low < min_touches:
            return False
    return True


def wy_detect(range_valid, pierced_low, closed_above_low,
              pierced_high, closed_below_high):
    """Transcribed from WY_Detect(). Returns (event, reason, invalidation)."""
    if not range_valid:
        return WY_NONE, "no qualifying Wyckoff range on the closed bars", ""
    spring = pierced_low and closed_above_low
    upthrust = pierced_high and closed_below_high
    if spring and upthrust:
        return (WY_NONE,
                "both boundaries were pierced on the same bar and it closed inside - no side", "")
    if spring:
        return (WY_SPRING,
                "the range low was pierced and the bar closed back inside the range",
                "a closed bar below the spring's wick low")
    if upthrust:
        return (WY_UPTHRUST,
                "the range high was pierced and the bar closed back inside the range",
                "a closed bar above the upthrust's wick high")
    if pierced_low:
        return (WY_NONE,
                "the range low was pierced but the bar closed BELOW it - a break, not a spring", "")
    if pierced_high:
        return (WY_NONE,
                "the range high was pierced but the bar closed ABOVE it - a break, not an upthrust", "")
    return WY_NONE, "the range held - no boundary was pierced and closed back inside", ""


def wy_score(range_valid, touches_ok, event_ok, volume_ok, conflicted):
    """Transcribed from WY_Score(): 25 / 20 / 30 / 25, conflict scores 0."""
    if conflicted:
        return 0
    s = 0
    if range_valid:
        s += 25
    if touches_ok:
        s += 20
    if event_ok:
        s += 30
    if volume_ok:
        s += 25
    return min(s, 100)


# --- A1 range validity --------------------------------------------------
check(wy_range_valid(20, 16, 4.0, 6.0, 3, 3, 2),
      "A1 a 20-bar range of 4 ATR with 3 touches per side is valid")
check(not wy_range_valid(10, 16, 4.0, 6.0, 3, 3, 2),
      "A1 a range shorter than the minimum bar count is rejected")
check(not wy_range_valid(20, 16, 7.0, 6.0, 3, 3, 2),
      "A1 a range taller than the cap is a trend, not a range")
check(not wy_range_valid(20, 16, 4.0, 6.0, 1, 3, 2),
      "A1 one touch of the UPPER boundary is not two")
check(not wy_range_valid(20, 16, 4.0, 6.0, 3, 1, 2),
      "A1 one touch of the LOWER boundary is not two")
check(not wy_range_valid(20, 16, 6.0, 6.0, 3, 3, 2),
      "A1 the height cap is exclusive (height == cap is too tall)")
check(wy_range_valid(16, 16, 4.0, 6.0, 2, 2, 2),
      "A1 the minimums are inclusive (exactly min bars, exactly min touches)")
check(wy_range_valid(20, 0, 4.0, 6.0, 1, 1, 0),
      "A1 a non-positive min_touches disables that test rather than failing it")
check(not wy_range_valid(2, 0, 4.0, 6.0, 1, 1, 0),
      "A1 but the three-bar floor still holds when the minimums are disabled")

# --- A2 nothing is given the benefit of the doubt -----------------------
check(not wy_range_valid(20, 16, -1.0, 6.0, 3, 3, 2),
      "A2 an unmeasured height (ATR unavailable) must not validate")
check(not wy_range_valid(20, 16, 0.0, 6.0, 3, 3, 2),
      "A2 a zero height is degenerate and must not validate")
check(not wy_range_valid(20, 16, 4.0, 0.0, 3, 3, 2),
      "A2 a zero height cap would accept a trend and must be refused")
check(not wy_range_valid(20, 16, 4.0, -1.0, 3, 3, 2),
      "A2 a negative height cap must be refused")
check(not wy_range_valid(2, 0, 4.0, 6.0, 3, 3, 0),
      "A2 fewer than three bars cannot have two sides")
check(not wy_range_valid(-5, 0, 4.0, 6.0, 3, 3, 0),
      "A2 a negative bar count must be refused, not treated as small")

# --- A3 Spring / A4 Upthrust -------------------------------------------
ev, r, iv = wy_detect(True, True, True, False, False)
check(ev == WY_SPRING, "A3 a pierced low with a close back inside is a SPRING")
check(iv != "", "A3 the Spring carries its invalidation")
ev, r, iv = wy_detect(True, False, False, True, True)
check(ev == WY_UPTHRUST, "A4 a pierced high with a close back inside is an UPTHRUST")
check(iv != "", "A4 the Upthrust carries its invalidation")
check(wy_detect(True, True, True, False, False)[0] !=
      wy_detect(True, False, False, True, True)[0],
      "A3/A4 the two events are distinct and are not mirrors of one label")

# --- A5 both pierced: refuses to name a side ---------------------------
ev, r, iv = wy_detect(True, True, True, True, True)
check(ev == WY_NONE, "A5 a bar that pierced both sides and closed inside names neither")
check("both boundaries" in r,
      "A5 the refusal says WHY, rather than reporting a quiet no-event")

# --- A6 pierced but closed outside is a BREAK --------------------------
ev, r, _ = wy_detect(True, True, False, False, False)
check(ev == WY_NONE and "break, not a spring" in r,
      "A6 a close below the pierced low is named a BREAK, not a Spring")
ev, r, _ = wy_detect(True, False, False, True, False)
check(ev == WY_NONE and "break, not an upthrust" in r,
      "A6 a close above the pierced high is named a BREAK, not an Upthrust")
# This is the mistake that would cost the most: a break reported as a Spring.
check(wy_detect(True, True, False, False, False)[0] != WY_SPRING,
      "A6 a break is never reported as a Spring")
check(wy_detect(True, False, False, True, False)[0] != WY_UPTHRUST,
      "A6 a break is never reported as an Upthrust")

# --- A7 no range, no event --------------------------------------------
check(wy_detect(False, True, True, True, True)[0] == WY_NONE,
      "A7 without a valid range there is no event however dramatic the bar")
check(wy_detect(False, True, True, False, False)[2] == "",
      "A7 a refused event invents no invalidation")
ev, r, _ = wy_detect(True, False, True, False, True)
check(ev == WY_NONE and "the range held" in r,
      "A7 an unpierced range reports that it held")

# --- A8 score arithmetic ----------------------------------------------
check(wy_score(False, False, False, False, False) == 0, "A8 no evidence scores 0")
check(wy_score(True, False, False, False, False) == 25, "A8 the range leg is worth 25")
check(wy_score(True, True, False, False, False) == 45, "A8 range + touches is worth 45")
check(wy_score(True, True, True, False, False) == 75,
      "A8 an event without confirmation is worth 75, not 100")
check(wy_score(True, True, True, True, False) == 100,
      "A8 the fully confirmed event is worth exactly 100")
check(wy_score(True, True, True, True, True) == 0,
      "A8 a CONFLICT scores 0 - disagreement is a stand-aside, not partial credit")
check(wy_score(False, False, False, False, True) == 0,
      "A8 a conflict scores 0 even with no evidence either")
check(all(0 <= wy_score(a, b, c, d, e) <= 100
          for a in (True, False) for b in (True, False) for c in (True, False)
          for d in (True, False) for e in (True, False)),
      "A8 every score is inside 0..100")

# --- A9 vocabulary -----------------------------------------------------
names = [wy_event_name(e) for e in (WY_NONE, WY_SPRING, WY_UPTHRUST)]
check(len(set(names)) == 3 and all(names),
      "A9 all three events have a distinct non-empty name")
check(wy_event_name(999) == "UNKNOWN" and wy_event_name(-1) == "UNKNOWN",
      "A9 an out-of-range event is labelled UNKNOWN, not guessed")

# --- A10 monotonicity --------------------------------------------------
mono = True
for a in (True, False):
    for b in (True, False):
        for c in (True, False):
            for d in (True, False):
                base = wy_score(a, b, c, d, False)
                if wy_score(True, b, c, d, False) < base:
                    mono = False
                if wy_score(a, True, c, d, False) < base:
                    mono = False
check(mono, "A10 adding evidence never lowers the score")
check(all(wy_score(a, b, c, d, True) <= wy_score(a, b, c, d, False)
          for a in (True, False) for b in (True, False) for c in (True, False)
          for d in (True, False)),
      "A10 a conflict never scores higher than the same event without one")

# --- A11 the transcription is pinned to the source ---------------------
src_rv = body_of("WY_RangeValid", "WY_RangeValid")
src_det = body_of("WY_Detect", "WY_Detect")
src_sc = body_of("WY_Score", "WY_Score")
check(src_rv.index("if(bars_in_range<3)") < src_rv.index("if(min_bars>0")
      < src_rv.index("if(max_height_atr<=0.0)") < src_rv.index("if(!(height_atr>0.0))")
      < src_rv.index("if(height_atr>=max_height_atr)"),
      "A11 the source's WY_RangeValid guard order matches the transcription")
check(src_det.index("if(spring && upthrust)") < src_det.index("if(spring)")
      < src_det.index("if(upthrust)") < src_det.index("if(pierced_low)")
      < src_det.index("if(pierced_high)"),
      "A11 the source's WY_Detect branch order matches the transcription")
check("if(conflicted) return 0;" in src_sc,
      "A11 the source zeroes a conflicted event before counting legs")
check("s+=25" in src_sc and "s+=20" in src_sc and "s+=30" in src_sc and "s+=25" in src_sc,
      "A11 the source's Wyckoff leg weights are 25/20/30/25 as transcribed")
check('return "SPRING"' in TEXT and 'return "UPTHRUST"' in TEXT
      and 'return "UNKNOWN"' in TEXT,
      "A11 the source's event names match the transcribed vocabulary")
check("break, not a spring" in src_det and "break, not an upthrust" in src_det,
      "A11 the source distinguishes a break from a failed Spring/Upthrust")

# =====================================================================
# Part B - source contracts
# =====================================================================
NEW_FUNCS = ["WY_EventName", "WY_RangeValid", "WY_Detect", "WY_Score",
             "WY_BuildRange", "WY_Update", "WY_DrawRange", "WY_Clear", "WY_SelfTest"]

# --- B1 nothing that already worked moved ------------------------------
m = re.search(r"^#property indicator_buffers\s+(\d+)", TEXT, re.M)
check(m and m.group(1) == "19", "B1 indicator_buffers is still 19 - no buffer was added")
m = re.search(r"^#property indicator_plots\s+(\d+)", TEXT, re.M)
check(m and m.group(1) == "7", "B1 indicator_plots is still 7")
idx = sorted(int(x) for x in re.findall(r"SetIndexBuffer\((\d+),", TEXT))
check(idx == list(range(19)), "B1 buffer indices are still exactly 0..18", str(idx))
check("string lines[11]; color cols[11]; int ln=0;" in TEXT,
      "B1 the pinned 11-row dashboard card is untouched")
check("if(ln>11) ln=11;" in TEXT, "B1 the card's row clamp is untouched")
for name, want in (("InpDetectJudas", "true"), ("InpLiquidityFractalN", "2"),
                   ("InpLiqToleranceATR", "0.15"), ("InpSwingLookback", "120"),
                   ("InpDisplacementATR", "0.9"),
                   # Phase 1 and Phase 2 defaults must survive Phase 3 too.
                   ("InpOBUseAgeExpiry", "false"), ("InpOBMaxAgeBars", "200"),
                   ("InpEnablePowerOf3", "false"), ("InpEnableSilverBullet", "false"),
                   ("InpSBWin1Start", "180"), ("InpSBChainMaxAgeBars", "240")):
    got = input_default(name)
    check(got == want, "B1 existing input %s still defaults to %s" % (name, want),
          "found %r" % got)

# --- B1b every NEW input ----------------------------------------------
for name in ("InpEnableWyckoff", "InpWyckoffShowOnDashboard", "InpWyckoffShowRange"):
    got = input_default(name)
    check(got == "false", "B1b new switch %s defaults to false" % name, "found %r" % got)
for name, want in (("InpWyckoffMinRangeBars", "16"), ("InpWyckoffMaxRangeBars", "240"),
                   ("InpWyckoffMaxRangeATR", "6.00"), ("InpWyckoffMinTouches", "2"),
                   ("InpWyckoffTouchTolATR", "0.25"),
                   ("InpWyckoffRequireVolume", "true"), ("InpWyckoffMaxAgeBars", "96")):
    got = input_default(name)
    check(got == want, "B1b new input %s defaults to %s" % (name, want), "found %r" % got)

# --- B2 declared once, defined once, signatures identical --------------
for fn in NEW_FUNCS:
    decls, defs = [], []
    pos = 0
    while True:
        i = TEXT.find(fn + "(", pos)
        if i < 0:
            break
        pos = i + 1
        if i and (TEXT[i - 1].isalnum() or TEXT[i - 1] == "_"):
            continue
        if not is_decl_or_def(i):
            continue
        p, after = params_at(i + len(fn))
        (decls if after == ";" else defs if after == "{" else []).append(p)
    check(len(decls) == 1, "B2 %s is declared exactly once" % fn, "%d decls" % len(decls))
    check(len(defs) == 1, "B2 %s is defined exactly once" % fn, "%d defs" % len(defs))
    if len(decls) == 1 and len(defs) == 1:
        check(decls[0] == defs[0], "B2 %s declaration and definition agree" % fn,
              "\n      decl: %s\n      defn: %s" % (decls[0], defs[0]))

# --- B3 called once per pass, after its inputs are final ---------------
oncalc = body_of("OnCalculate", "OnCalculate")
check(oncalc.count("WY_Update(closed);") == 1,
      "B3 WY_Update is called exactly once in OnCalculate")
i_gate = oncalc.find("if(detection_updated)")
i_wy = oncalc.find("WY_Update(closed);")
i_p3 = oncalc.find("P3_Update(closed);")
check(0 < i_gate < i_p3 < i_wy,
      "B3 WY_Update is inside the detection_updated gate, after the Phase 2 adapters",
      "gate=%d p3=%d wy=%d" % (i_gate, i_p3, i_wy))
# It reads g_judas, so it must run after DetectJudasSwing has published it.
i_judas = oncalc.find("DetectJudasSwing(rates_total,")
check(0 < i_judas < i_wy,
      "B3 WY_Update runs after DetectJudasSwing, whose verdict it reconciles against")

# --- B4 reset and self-test wired into OnInit --------------------------
oninit = TEXT[TEXT.find("int OnInit()"):]
oninit = oninit[:oninit.find("\r\nint OnCalculate(")]
check("WY_Clear();" in oninit, "B4 WY_Clear is called from OnInit")
check(oninit.find("SBP3_Clear();") < oninit.find("WY_Clear();"),
      "B4 WY_Clear sits beside the other module resets")
check("if(WY_SelfTest(mtee_fail))" in oninit, "B4 the self-test is invoked from OnInit")
check(0 < oninit.find("if(InpMTEERunSelfTest)") < oninit.find("if(WY_SelfTest(mtee_fail))"),
      "B4 the self-test is inside the existing InpMTEERunSelfTest gate")
st = body_of("WY_SelfTest", "WY_SelfTest")
groups = sorted(set(re.findall(r'WY-(\d+)', st)))
check(len(groups) >= 9, "B4 the self-test covers %d groups" % len(groups), str(groups))

# --- B5 DISPLAY ONLY ---------------------------------------------------
NEW_STATE = ["g_wy_range_high", "g_wy_range_low", "g_wy_range_start", "g_wy_range_end",
             "g_wy_range_valid", "g_wy_touches_high", "g_wy_touches_low", "g_wy_event",
             "g_wy_dir", "g_wy_bar", "g_wy_extreme", "g_wy_active", "g_wy_volume_ok",
             "g_wy_conflict", "g_wy_score", "g_wy_reason", "g_wy_invalidation"]
CONSUMERS = ["QSMC_ArbiterFeedAndFinalize", "UpdateSignalMask",
             # GraphConfluenceScore was unreachable and was deleted (doc 11.14):
             # a function that no longer exists cannot be a consumer.
             "PMI_ComputeConfluence", "ScenarioUpdate", "ScenarioDashFull",
             "ScoreOrderBlock", "PMI_BuildLocation", "CoreDashChain",
             "TacticalAuthorityDecide", "ValidateCausalGraphInvariants",
             "ReplayClosedBarStates", "BuildCausalEventGraph", "DetectOrderBlocks",
             "DetectJudasSwing", "DetectLiquidity", "SweepHasDisplacementOrVolume",
             "P3_Update", "SB_Update"]
consumers_checked = 0
for fn in CONSUMERS:
    b = body_of(fn, fn) if TEXT.find(fn + "(") >= 0 else ""
    if not b:
        continue
    consumers_checked += 1
    hit = [s for s in NEW_STATE if s in b]
    check(not hit, "B5 %s cannot read the Wyckoff state" % fn, str(hit))
check(consumers_checked >= 14,
      "B5 the display-only claim was checked against %d real function bodies"
      % consumers_checked, "too few located - the check would be vacuous")

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
_i0, _i1, wy_section = _section(TEXT, "// AUDIT-WY1  WYCKOFF SPRING", "bool WY_SelfTest(string &where)")
check(0 < _i0 < _i1, "B the WY1 engine section was located", "%d..%d" % (_i0, _i1))
check(len(wy_section) > 8000,
      "B the WY1 section slice is substantial (%d chars)" % len(wy_section))
check("BufSig" not in wy_section and "SetIndexBuffer" not in wy_section,
      "B5 the module writes no buffer")
for api in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen", "PositionModify",
            "OrderCheck", "WebRequest"):
    check(api not in strip_comments(wy_section), "B5 the module cannot reach %s" % api)

# --- B6 symbol-agnostic, no hard-coded price ---------------------------
code = strip_comments(wy_section)
code = re.sub(r'"(\\.|[^"\\])*"', '""', code)
for sym in ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"):
    check(sym not in code, "B6 no hard-coded %s in the new code" % sym)
check(not re.search(r"\b\d{3,4}\.\d{1,5}\b", code),
      "B6 no literal price level in the new code")
check("PipSize()" in wy_section,
      "B6 tolerances carry a PipSize floor, so they work on any symbol")
check("g_atr_buf" in wy_section and "g_atr" in wy_section,
      "B6 the ATR read reuses the per-bar buffer with its scalar fallback")

# --- B7 tooltip, never the card ---------------------------------------
dash = body_of("DrawQuantumDashboard", "DrawQuantumDashboard")
check('tooltip+="\\nWY: "' in dash, "B7 the Wyckoff row is merged into the tooltip")
tail = dash.split('tooltip+="\\nWY: "')[1].split("int chart_w=")[0]
check("lines[ln]=" not in tail, "B7 the Wyckoff module writes no card row")
check(dash.count("WY_DrawRange(closed);") == 1,
      "B7 the optional range box is drawn from the dashboard pass")
i_sweep = oncalc.find("PrepareDynamicRedraw();")
i_dash = oncalc.find("DrawQuantumDashboard(rates_total,")
check(0 < i_sweep < i_dash,
      "B7 the dashboard (which draws the box) runs AFTER the object sweep")

# --- B8 object cleanup -------------------------------------------------
created = set(re.findall(r'PFX\+"(WY_[A-Z_]*)"', wy_section + dash))
check(created, "B8 the module names its objects with the WY_ prefix", str(created))
sweep = body_of("PrepareDynamicRedraw", "PrepareDynamicRedraw")
check('ObjectsDeleteAll(0,PFX+"WY_")' in sweep,
      "B8 PrepareDynamicRedraw sweeps the WY_ prefix")
check(wy_section.count("ObjectCreate") == 0,
      "B8 the module creates no object directly - it reuses DrawZoneBox")
check("DrawZoneBox(" in wy_section, "B8 the range box reuses the existing DrawZoneBox")

# --- B9 CAUSALITY: the test bar cannot widen its own range -------------
wyupd = body_of("WY_Update", "WY_Update")
check("WY_BuildRange(b-1," in wyupd,
      "B9 the range window ends at b-1, so the bar under test is outside its own range")
check("WY_BuildRange(b," not in wyupd,
      "B9 the range is never built including the bar being tested")
check("WY_BuildRange(end_bar-1" not in body_of("WY_BuildRange", "WY_BuildRange"),
      "B9 WY_BuildRange does not itself reach past the bar it was given")
check("int closed=total-2" not in wyupd and "closed=total-2" in TEXT,
      "B9 WY_Update takes the caller's closed bar rather than recomputing a different one")
check("TimeCurrent()" not in code, "B9 no wall-clock time in the new code")
check("rates_total-1" not in code and "rates_total - 1" not in code,
      "B9 no forming-bar index in the new code")
check("for(int k=b+1;k<=closed;k++)" in wyupd,
      "B9 a later closed bar can invalidate an event - it is not latched forever")
check("if(atr<=0.0)" in wyupd,
      "B9 an unavailable ATR is refused rather than silently treated as a valid range")
check("no repaint" in wy_section.lower() or "RE-DERIVES" in wy_section,
      "B9 the replay-determinism claim is documented where the module is defined")

# --- B10 no probability claim, no direction unless active --------------
check("not a win rate" in dash, "B10 the Wyckoff dashboard row disclaims probability")
check("confluence, not a win rate" in dash, "B10 the score is labelled a confluence count")
check('wy_dir=(g_wy_active?' in dash,
      "B10 no direction is printed unless the event is ACTIVE")
check("g_wy_dir=(dead||conflict ? 0 : dir);" in wyupd,
      "B10 an invalidated or conflicted event publishes NO direction")
check("CONFLICT - " in wyupd, "B10 a conflict with Judas is reported as one, explicitly")
check("INVALIDATED - " in wyupd, "B10 an already-invalidated event says so")
check("NOT AN ENTRY" in wy_section, "B10 the drawn range box says it is context, not an entry")
check("NOT PROBABILITIES" in wy_section or "not a probability" in wy_section.lower(),
      "B10 the module states its scores are not probabilities")

# --- B11 REUSE, not duplication ---------------------------------------
check("SweepHasDisplacementOrVolume(" in wyupd,
      "B11 confirmation reuses the existing sweep validator")
# Counted on the comment-stripped body: WY_Update's own prose names the validator,
# so counting the raw text saw two hits where there is exactly one call.
wyupd_code = strip_comments(wyupd)
check(wyupd_code.count("SweepHasDisplacementOrVolume(") == 1,
      "B11 it is the ONLY confirmation call - no second, looser opinion exists")
check("g_buf_tv" in wy_section and "g_buf_rv" not in wy_section,
      "B11 it reads the tick volume the validator already uses, adding no volume source")
check("MathMax(atr*0.15,3.0*PipSize())" in wyupd,
      "B11 the minimum wick is the SAME threshold the validator enforces")
check("InpWyckoffRequireVolume" in wyupd,
      "B11 confirmation is switchable, and the switch is honoured")
check("g_judas" in wyupd and "g_judas_bar" in wyupd,
      "B11 the module reconciles against the Judas verdict instead of ignoring it")
check("InpDetectJudas" in wyupd,
      "B11 the reconciliation is skipped when the Judas detector itself is off")
check("atr*touch_tol" in body_of("WY_BuildRange", "WY_BuildRange")
      and "PipSize()" in body_of("WY_BuildRange", "WY_BuildRange"),
      "B11 the touch tolerance follows DetectLiquidity's ATR-with-pip-floor idiom")
check("DetectDealingRange" not in wyupd,
      "B11 it does not call the swing dealing range - a different measurement")
check("g_liquidity" not in wyupd,
      "B11 it does not read the liquidity ledger, whose EQH/EQL pools keep no touch count")
check("InpLogLifecycleTransitions" in wyupd and "LogLifecycle(" in wyupd,
      "B11 events log through the existing lifecycle log, in the existing format")

print("-" * 74)
print("Wyckoff Spring/Upthrust contracts: %d checked, %d failed" % (N[0], len(FAILS)))
print("-" * 74)
if FAILS:
    print("RESULT: %d contract(s) FAILED" % len(FAILS))
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("RESULT: all Wyckoff Spring/Upthrust contracts hold")
print("-" * 74)
print("The module defaults to OFF, is display only, and adds no buffer, so with its")
print("switch off nothing is detected, scored, drawn or retired any differently than")
print("before. This is a transcription + wiring contract. It is NOT a backtest, it")
print("produces no win rate, and it does NOT prove MetaEditor compilation. Press F7.")
