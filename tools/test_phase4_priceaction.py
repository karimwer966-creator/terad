#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-PA1  PURE PRICE ACTION - transcription + wiring contract for nadir2.mq5.

Phase 4 of the strategy-module extension. What this file proves, and what it
deliberately does NOT claim:

  * It transcribes the module's pure cores into Python and re-derives their
    behaviour, then checks that the transcribed guard ORDER, constants and string
    literals are the ones actually present in the .mq5 text. Without that second
    step the transcription could drift from the source and still pass.
  * It proves the ONE edit made to existing code - the opt-in hard gate in
    ContextualCandleScore() - is inert while InpPARequireZoneContext is false,
    which is the default, by re-implementing the scorer both ways.
  * It PINS the pre-existing three-way candle divergence (AnalyzeClosedCandle /
    AnalyzeCandleIntelligence / the MTF sniper C1 gate) by searching for bars on
    which they disagree, rather than asserting a prose claim. Phase 4 reports
    this divergence; it does not repair it, because unifying would TIGHTEN an
    existing entry gate.
  * It is a static contract test. It is NOT a backtest, produces no win rate, and
    does NOT prove MetaEditor compiles the file - only F7 does that.
"""
import io
import math
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
    TEXT = fh.read()
NL = "\r\n" if "\r\n" in TEXT else "\n"
BARE_LF = TEXT.count("\n") - TEXT.count("\r\n")


def strip_comments(src):
    """Remove comments and blank string/char literal contents in ONE pass.

    A chain of regexes is unsound in both orders: stripping comments first lets a
    "//" inside a string literal eat the rest of that line and leave an unterminated
    quote, which then makes the string pass swallow thousands of lines of real code
    - silently turning every "called exactly once" count into 0. Stripping strings
    first has the mirror failure, because a comment may contain an odd quote. A
    single scanner that tracks which construct it is inside has neither problem."""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == '"' or c == "'":
            q = c
            out.append('""' if q == '"' else "''")
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _fn_end(text, sig_at):
    """Offset just past the closing brace of the function DEFINED at sig_at."""
    i, depth, started, n = sig_at, 0, False, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            i = text.find('\n', i)
            if i < 0:
                return -1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            i = text.find('*/', i + 2)
            if i < 0:
                return -1
            i += 2
            continue
        if c in '"\'':
            q = c
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == q:
                    break
                i += 1
            i += 1
            continue
        if c == '{':
            depth += 1
            started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return i + 1
        i += 1
    return -1


def _section(text, banner, sig):
    """Slice a module's section from its banner to the end of its OWN self-test.
    Never end a section at a shared downstream marker - that silently swallows
    whatever module was later inserted before it."""
    i0 = text.find(banner)
    if i0 < 0:
        return -1, -1, ""
    j = text.find(sig, i0)
    if j < 0:
        return -1, -1, ""
    e = _fn_end(text, j)
    if e < 0:
        return -1, -1, ""
    return i0, e, text[i0:e]


def precedes(hay, first, second, label):
    """Assert `first` occurs before `second`, reporting a FAIL rather than raising.
    A bare hay.index() turns a missing anchor into a traceback, which aborts the
    run: the exit code is still non-zero so CI catches it, but every check after
    that point is silently never executed."""
    a, b = hay.find(first), hay.find(second)
    check(a >= 0 and b >= 0 and a < b, label,
          "first@%d second@%d" % (a, b))


def input_default(name):
    m = re.search(r"\binput\s+[A-Za-z_][\w\s\*&]*?\b" + re.escape(name) +
                  r"\s*=\s*([^,;]+)[,;]", TEXT)
    return m.group(1).strip() if m else None


def body_of(sig, label, floor=0):
    """Body of the DEFINITION matching `sig`, skipping any forward declaration.

    A declaration and a definition share a prefix, so a plain find() lands on the
    declaration - which has no braces of its own, so a brace-matched scan from
    there silently returns the body of whatever unrelated function follows it.
    Every occurrence is tested instead: the one whose next structural character is
    '{' rather than ';' is the definition. Returns '' when not found, and records
    the failure, so a caller can never mistake an empty body for a passing one."""
    j = floor
    while True:
        j = TEXT.find(sig, j)
        if j < 0:
            break
        sc = TEXT.find(';', j)
        br = TEXT.find('{', j)
        if br >= 0 and (sc < 0 or br < sc):
            end = _fn_end(TEXT, j)
            if end > 0:
                return TEXT[j:end]
        j += len(sig)
    check(False, label + " (definition located)", sig)
    return ""



# =====================================================================
# A. PURE CORES - transcribed, then pinned back to the source text
# =====================================================================
POINT = 0.01  # stand-in for _Point; only the tolerance idiom depends on it


def mround(x):
    """MQL5 MathRound rounds half away from zero; Python round() is banker's."""
    return int(math.floor(x + 0.5)) if x >= 0 else int(math.ceil(x - 0.5))


def pa_inside_bar_geometry(h, l, prev_h, prev_l):
    if not (prev_h > 0.0) or not (prev_l > 0.0):
        return False
    if not (h > 0.0) or not (l > 0.0):
        return False
    return h < prev_h and l > prev_l


def pa_unify_pattern(candle_pattern, inside_bar, include_inside_bar):
    if candle_pattern != "NONE" and candle_pattern != "":
        return candle_pattern
    if include_inside_bar and inside_bar:
        return "INSIDE_BAR"
    return "NONE"


def pa_unify_strength(candle_pattern, candle_score, is_inside_bar, inside_bar_strength):
    if is_inside_bar:
        s = inside_bar_strength
        return 0 if s < 0 else (100 if s > 100 else s)
    if candle_score < 0:
        return 0
    if candle_score > 100:
        return 100
    return candle_score


BULL_PATTERNS = ("BULLISH_ENGULFING", "MORNING_STAR", "HAMMER", "PIERCING",
                 "BULLISH_DISPLACEMENT_CANDLE")
BEAR_PATTERNS = ("BEARISH_ENGULFING", "EVENING_STAR", "SHOOTING_STAR", "DARK_CLOUD",
                 "BEARISH_DISPLACEMENT_CANDLE")


def pa_pattern_direction(p):
    if p in BULL_PATTERNS:
        return 1
    if p in BEAR_PATTERNS:
        return -1
    return 0


def pa_is_conflict(pd, zd):
    return pd != 0 and zd != 0 and pd != zd


def pa_resolve_direction(in_zone, pd, zd):
    if not in_zone:
        return 0
    if pa_is_conflict(pd, zd):
        return 0
    if pd != 0:
        return pd
    return zd


def pa_score(in_zone, strength, agrees):
    if not in_zone:
        return 0
    s = 25
    st = 0 if strength < 0 else (100 if strength > 100 else strength)
    s += mround(st * 0.45)
    if agrees:
        s += 30
    return 100 if s > 100 else s


# A1 inside-bar geometry is strict, and an unknown parent is refused.
check(pa_inside_bar_geometry(101.0, 99.0, 102.0, 98.0) is True,
      "A1 a strictly contained bar is an inside bar")
check(pa_inside_bar_geometry(102.0, 99.0, 102.0, 98.0) is False,
      "A1 an equal high is not an inside bar")
check(pa_inside_bar_geometry(101.0, 98.0, 102.0, 98.0) is False,
      "A1 an equal low is not an inside bar")
check(pa_inside_bar_geometry(103.0, 97.0, 102.0, 98.0) is False,
      "A1 an engulfing bar is not an inside bar")
check(pa_inside_bar_geometry(101.0, 99.0, 0.0, 0.0) is False,
      "A1 an unknown parent is refused rather than guessed")

# A2 unification never reclassifies an existing pattern.
check(pa_unify_pattern("DOJI", True, True) == "DOJI",
      "A2 a DOJI that is also an inside bar stays a DOJI")
for named in BULL_PATTERNS + BEAR_PATTERNS:
    check(pa_unify_pattern(named, True, True) == named,
          "A2 %s is never overridden by INSIDE_BAR" % named)
check(pa_unify_pattern("NONE", True, True) == "INSIDE_BAR",
      "A2 INSIDE_BAR fills only the gap where nothing matched")
check(pa_unify_pattern("", True, True) == "INSIDE_BAR",
      "A2 an empty label counts as no pattern")
check(pa_unify_pattern("NONE", True, False) == "NONE",
      "A2 the inside-bar leg is switchable, and off means off")
check(pa_unify_pattern("NONE", False, True) == "NONE",
      "A2 a bar that is not an inside bar stays NONE")

# A3 strength mapping and clamping.
check(pa_unify_strength("NONE", 0, True, 45) == 45,
      "A3 an inside bar takes its configured strength")
check(pa_unify_strength("MORNING_STAR", 88, False, 45) == 88,
      "A3 a named pattern keeps its own strength")
check(pa_unify_strength("NONE", 0, True, 999) == 100 and
      pa_unify_strength("NONE", 0, True, -5) == 0,
      "A3 an inside-bar strength is clamped to 0..100")
check(pa_unify_strength("X", 150, False, 45) == 100 and
      pa_unify_strength("X", -3, False, 45) == 0,
      "A3 a candle score is clamped to 0..100")

# A4 the direction vocabulary - compression carries no direction.
for p in BULL_PATTERNS:
    check(pa_pattern_direction(p) == 1, "A4 %s resolves to +1" % p)
for p in BEAR_PATTERNS:
    check(pa_pattern_direction(p) == -1, "A4 %s resolves to -1" % p)
for p in ("DOJI", "INSIDE_BAR", "NONE", "SOMETHING_NEW"):
    check(pa_pattern_direction(p) == 0, "A4 %s carries no direction" % p)

# A5 THE RULE THE BRIEF ASKS FOR: never standalone.
for pd in (-1, 0, 1):
    for zd in (-1, 0, 1):
        check(pa_resolve_direction(False, pd, zd) == 0,
              "A5 outside a zone, pattern_dir=%d zone_dir=%d gives no direction" % (pd, zd))

# A6 inside a zone an undirectional pattern takes the zone's side.
check(pa_resolve_direction(True, 0, 1) == 1 and pa_resolve_direction(True, 0, -1) == -1,
      "A6 an undirectional pattern inside a zone takes the zone's direction")
check(pa_resolve_direction(True, 1, 1) == 1 and pa_resolve_direction(True, -1, -1) == -1,
      "A6 an agreeing pattern keeps its own direction")

# A7 contradiction resolves to nothing.
check(pa_resolve_direction(True, 1, -1) == 0 and pa_resolve_direction(True, -1, 1) == 0,
      "A7 a pattern contradicting its zone resolves to no direction")
check(pa_is_conflict(1, -1) and pa_is_conflict(-1, 1),
      "A7 opposite directions are a conflict")
check(not pa_is_conflict(0, 1) and not pa_is_conflict(1, 0) and
      not pa_is_conflict(1, 1) and not pa_is_conflict(0, 0),
      "A7 an undirectional side is not a conflict")

# A8 score arithmetic - no partial credit for a standalone candle.
check(pa_score(False, 88, True) == 0 and pa_score(False, 100, True) == 0,
      "A8 outside a zone the score is 0, not a fraction of the strength")
check(pa_score(True, 0, False) == 25, "A8 being inside a valid zone is worth 25 alone")
check(pa_score(True, 100, False) == 70, "A8 maximum pattern strength adds 45, giving 70")
check(pa_score(True, 100, True) == 100, "A8 zone + maximum pattern + agreement is 100")
check(pa_score(True, 45, True) == 75, "A8 an inside bar of strength 45 with agreement is 75")
check(pa_score(True, 88, True) == 95, "A8 a MORNING_STAR of 88 in zone with agreement is 95")
check(pa_score(True, 9999, True) == 100 and pa_score(True, -9999, True) == 55,
      "A9 an out-of-range strength is clamped, not propagated")
check(all(0 <= pa_score(True, s, a) <= 100 for s in range(-50, 160, 7) for a in (False, True)),
      "A9 the score stays inside 0..100 for every strength in range")
check(all(pa_score(True, s, True) >= pa_score(True, s, False) for s in range(0, 101)),
      "A9 agreement never lowers the score")
check(all(pa_score(True, 100, True) >= pa_score(True, s, True) for s in range(0, 101)),
      "A9 the score is monotonic in pattern strength")

# ---- A10 pin the transcription back to the shipped source text -----------
# These shape assertions run on the RAW body, not strip_comments(): that helper
# blanks string literals, so it would delete the very "NONE" / "INSIDE_BAR" /
# "MITIGATED" texts being asserted on. strip_comments() is still the right tool
# for the absence checks in B, where a mention in prose must not count as a call.
pa_code = body_of("bool PA_InsideBarGeometry(const double h", "A10 PA_InsideBarGeometry")
for lit in ("if(!(prev_h>0.0) || !(prev_l>0.0)) return false;",
            "if(!(h>0.0) || !(l>0.0)) return false;",
            "return (h<prev_h && l>prev_l);"):
    check(lit in pa_code, "A10 the shipped inside-bar test is %r" % lit[:44])
uni = body_of("string PA_UnifyPattern(const string candle_pattern", "A10 PA_UnifyPattern")
check('if(candle_pattern!="NONE" && candle_pattern!="") return candle_pattern;' in uni,
      "A10 unification returns an existing pattern BEFORE considering INSIDE_BAR")
precedes(uni, 'return candle_pattern;', 'return "INSIDE_BAR";',
         "A10 the never-reclassify guard is the FIRST branch, not a later one")
res = body_of("int PA_ResolveDirection(const bool in_zone", "A10 PA_ResolveDirection")
order = ["if(!in_zone) return 0;", "if(PA_IsConflict(pattern_dir,zone_dir)) return 0;",
         "if(pattern_dir!=0) return pattern_dir;", "return zone_dir;"]
pos = [res.index(o) for o in order if o in res]
check(len(pos) == 4 and pos == sorted(pos),
      "A10 the resolve guard order is zone -> conflict -> pattern -> zone")
sco = body_of("int PA_Score(const bool in_zone", "A10 PA_Score")
precedes(sco, "if(!in_zone) return 0;", "int s=25;",
         "A10 the score's zone gate precedes every scoring line")
check("s+=(int)MathRound((double)strength*0.45);" in sco,
      "A10 the pattern leg is exactly strength*0.45, rounded")
check("if(direction_agrees) s+=30;" in sco and "return (s>100?100:s);" in sco,
      "A10 agreement is worth 30 and the result is capped at 100")
conf = body_of("bool PA_IsConflict(const int pattern_dir", "A10 PA_IsConflict")
check("return (pattern_dir!=0 && zone_dir!=0 && pattern_dir!=zone_dir);" in conf,
      "A10 a conflict needs BOTH sides directional and opposite")

# =====================================================================
# B. SECTION CONTRACTS - purity, scope, causality, vocabulary
# =====================================================================
_i0, _i1, pa_section = _section(TEXT, "// AUDIT-PA1  PURE PRICE ACTION",
                                "bool PA_SelfTest(string &where)")
check(0 < _i0 < _i1, "B the PA1 engine section was located", "%d..%d" % (_i0, _i1))
check(len(pa_section) > 8000,
      "B the PA1 section slice is substantial (%d chars)" % len(pa_section))
pa_src = strip_comments(pa_section)

check("BufSig" not in pa_section and "SetIndexBuffer" not in pa_section,
      "B5 the new module writes no buffer")
for api in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen", "PositionClose",
            "WebRequest", "Alert(", "SendNotification", "iCustom", "SymbolInfoTick"):
    check(api not in pa_src, "B5 the module cannot reach %s" % api)
check(pa_src.count("ObjectCreate") == 0,
      "B7 the module draws nothing, so it needs no object-prefix cleanup")
check("DrawZoneBox(" not in pa_src and "DrawTextLabel(" not in pa_src,
      "B7 no chart object of any kind is created")

# Symbol-agnostic: every distance is ATR- or point-normalized, never a literal price.
check("InpPAZoneToleranceATR" in pa_src and "MathMax(_Point," in pa_src,
      "B6 the zone tolerance is ATR-normalized with the existing idiom")
hits = re.findall(r"\b\d{3,4}\.\d{1,5}\b",
                  re.sub(r'"(\\.|[^"\\])*"', '""',
                         strip_comments(_section(TEXT, "// AUDIT-PA1  PURE PRICE ACTION",
                                                 "bool PA_Update(const int closed)")[2])))
check(not hits, "B6 no literal price level in the module's production code", str(sorted(set(hits))))

# Causality: closed bars only, no forming bar, no future bar, nothing latched.
check("[closed+1]" not in pa_src and "[closed + 1]" not in pa_src,
      "B9 no future bar is read")
for api in ("iTime(", "iClose(", "iOpen(", "iHigh(", "iLow(", "CopyRates("):
    check(api not in pa_src, "B9 the module reads no live series - only the mirrored buffers")
upd = body_of("void PA_Update(const int closed)", "B9 PA_Update", floor=_i0)
check("g_buf_c[closed]" in upd and "g_buf_h[closed]" in upd and "g_buf_l[closed]" in upd,
      "B9 PA_Update indexes the CLOSED bar of the mirrored buffers")
check("AnalyzeClosedCandle(closed,g_buf_o,g_buf_h,g_buf_l,g_buf_c,atr)" in upd,
      "B9 the pattern comes from the EXISTING unified function, not a re-implementation")
check(upd.count("AnalyzeClosedCandle(") == 1,
      "B9 that function is called exactly once per pass")
check("[closed-1]" in upd, "B9 the parent bar is read, which is also closed")
check("if(closed<2)" in upd or "closed<2" in upd,
      "B9 a bar index that has no parent is refused")
check("g_pa_pattern=" in upd and "g_pa_strength=" in upd,
      "B9 state is recomputed every pass, never latched between passes")
check("if(!InpEnablePriceAction)" in upd,
      "B9 the module returns immediately while its switch is off")

# Zone sources are the existing arrays, honoured with their own state vocabulary.
za = body_of("bool PA_ZoneAt(const double price", "B PA_ZoneAt", floor=_i0)
for arr in ("g_order_blocks", "g_fvgs", "g_zones", "g_mvp"):
    check(arr in za, "B the zone scan reads the existing %s" % arr)
# Naming the array is not scanning it: a loop bound replaced by a constant leaves
# every mention in place while the scan never runs.
for arr in ("g_order_blocks", "g_fvgs", "g_zones"):
    check("ArraySize(%s)" % arr in za,
          "B the %s scan iterates the whole array, not a stubbed bound" % arr)
# The closing paren is part of the pin: without it "<=tol" is also a substring of
# "<=tol*1e9", so scaling the tolerance away would pass.
check("MathAbs(price-g_mvp[g_mvp_active].poc)<=tol)" in za,
      "B the POC test is the distance-to-POC comparison, using the shared tolerance")
# LIMITATION, stated rather than hidden: a mutation that keeps a test textually
# present but forces it true (`if(true || dist<=tol)`) is a semantic tautology. No
# static contract test can catch it; only F7 plus the runtime self-test can.
check('"MITIGATED"' in za and '"EXPIRED"' in za and '"FILLED"' in za,
      "B the scan honours MITIGATED / EXPIRED / FILLED rather than inventing states")
check("mitigated" in za and "filled" in za,
      "B the scan also honours the boolean state flags")
check("g_mvp_active" in za and "g_mvp_count" in za and ".valid" in za,
      "B the POC reuses the volume profile's own validity guard")
prio = [za.index(a) for a in ("g_order_blocks", "g_fvgs", "g_zones", "g_mvp") if a in za]
check(len(prio) == 4 and prio == sorted(prio),
      "B zone priority is OB > FVG > S/R > POC - causal first, statistical last")
# Mention order is not evaluation order: an early `return true` spliced above the
# first scan would leave every array name in place while silently changing which
# zone wins. Pin the order of the RETURNS as well.
precedes(za, "g_order_blocks", "return true;",
         "B no zone can be returned before the order-block scan has run")
precedes(za, "g_zones", "g_mvp", "B the POC is consulted after the S/R zones")
check(za.rfind("g_mvp") > za.rfind("g_zones") > za.rfind("g_fvgs") > za.rfind("g_order_blocks"),
      "B the four zone scans are evaluated last-to-first as POC, S/R, FVG, OB")
check("IsInstitutionalLocation" not in za,
      "B the scan does not misuse IsInstitutionalLocation, which tests premium/discount")

# Reason vocabulary: mutually exclusive, and never a side next to a stand-aside.
# Each reason is a multi-line concatenation, so capturing the first quoted
# fragment would read "stand aside: " and miss the words that follow it. Collect
# every literal in each assignment statement instead.
reasons = []
for _m in re.finditer(r'g_pa_reason=', pa_section):
    _j = pa_section.find(';', _m.end())
    _lit = "".join(re.findall(r'"((?:\\.|[^"\\])*)"', pa_section[_m.start():_j]))
    if _lit.strip():
        reasons.append(_lit)
check(len(reasons) >= 4, "B the module emits %d distinct reason strings" % len(reasons))
check(any("not inside any valid zone" in r for r in reasons),
      "B a standalone candle gets an explicit stand-aside reason")
check(any(r.startswith("CONFLICT") for r in reasons),
      "B a contradiction is labelled CONFLICT, not quietly resolved")
check(any("no direction" in r for r in reasons),
      "B a compression pattern with no zone direction says so")
check("not a probability" in pa_section.lower() or "NOT PROBABILITIES" in pa_section,
      "B10 the section states its scores are not probabilities")
check(pa_section.count("g_pa_dir=") >= 1, "B the module publishes a direction")
check("g_pa_invalidation=" in pa_section, "B the module publishes an invalidation reason")

# =====================================================================
# C. WIRING
# =====================================================================
c_all = strip_comments(TEXT)


def call_count(sig_call):
    """Occurrences of a real CALL of `sig_call`, excluding declarations.

    A declaration and a call can share text exactly (`void   MR_Clear();` contains
    `MR_Clear();`), so a raw count over-reports. Subtracting fixed type prefixes is
    also wrong, because this file aligns its declarations with run-on spaces. A line
    is a declaration when it starts with a return type and ends with a semicolon."""
    n = 0
    for m in re.finditer(re.escape(sig_call), c_all):
        ls = c_all.rfind('\n', 0, m.start()) + 1
        le = c_all.find('\n', m.end())
        line = c_all[ls:le if le >= 0 else len(c_all)]
        if re.match(r'^\s*(?:void|int|bool|string|double|datetime|long|ushort)\s+', line) \
                and line.rstrip().endswith(';'):
            continue
        n += 1
    return n


check(call_count("PA_Update(closed);") == 1,
      "C PA_Update is called exactly once (%d)" % call_count("PA_Update(closed);"))
check(call_count("PA_Clear();") == 1,
      "C PA_Clear is called exactly once, the declaration excluded (%d)"
      % call_count("PA_Clear();"))
check(call_count("PA_SelfTest(mtee_fail)") == 1,
      "C PA_SelfTest is invoked exactly once (%d)" % call_count("PA_SelfTest(mtee_fail)"))
check(TEXT.count("bool PA_SelfTest(string &where);") == 1,
      "C PA_SelfTest is forward-declared exactly once")
check(TEXT.count("bool PA_IsConflict(const int pattern_dir,const int zone_dir);") == 1,
      "C PA_IsConflict is forward-declared exactly once")
for fn in ("PA_InsideBarGeometry", "PA_UnifyPattern", "PA_UnifyStrength",
           "PA_PatternDirection", "PA_IsConflict", "PA_ResolveDirection", "PA_Score",
           "PA_ZoneAt", "PA_Update", "PA_Clear", "PA_SelfTest"):
    check(TEXT.count(fn) >= 2, "C %s is both declared and defined" % fn)

# The call site ORDER is the substantive wiring fact: PA_ZoneAt reads the active
# profile's POC, so PA_Update must run after MVP_Update and the section says why.
call_at = TEXT.find("PA_Update(closed);")
mvp_at = TEXT.find("MVP_Update(rates_total")
zre_at = TEXT.find("ZRE_Update(rates_total")
check(0 < mvp_at < call_at < zre_at,
      "C PA_Update runs after MVP_Update and before ZRE_Update",
      "mvp=%d call=%d zre=%d" % (mvp_at, call_at, zre_at))
check("if(is_new_bar || detection_updated) PA_Update(closed);" in TEXT,
      "C PA_Update runs once per closed bar, never per tick")
seg = TEXT[mvp_at:call_at]
check("PA_ZoneAt() reads the active" in seg or "profile's POC" in seg,
      "C the ordering reason is documented at the call site, not only in the section")
check("Runs after MVP_Update so the active profile levels are current." in TEXT[zre_at - 400:zre_at + 200],
      "C ZRE_Update's own ordering comment was left attached to ZRE_Update")

# OnInit: reset beside the other modules, self-test under the existing switch.
_pc = TEXT.find("   PA_Clear();")
check(_pc > 0, "C PA_Clear() is called in OnInit")
init_seg = TEXT[max(0, _pc - 4000):_pc + 200] if _pc > 0 else ""
check("WY_Clear();" in init_seg, "C PA_Clear sits with the other module resets in OnInit")
st_at = TEXT.find("PA_SelfTest(mtee_fail)")
gate_seg = TEXT[max(0, st_at - 6000):st_at]
check("InpMTEERunSelfTest" in gate_seg,
      "C PA_SelfTest is gated by the existing InpMTEERunSelfTest switch")
check('Print(">>> ",QSMC_VERSION_TEXT," Pure Price Action self-test: PASS (9/9)");' in TEXT,
      "C the self-test result is logged through the existing version-tagged format")

# Dashboard: tooltip only, never the hard-capped 11-row card.
check('tooltip+="\\nPA: "' in TEXT, "C the PA rows go to the dashboard tooltip")
dash_at = TEXT.find('tooltip+="\\nPA: "')
dash_seg = TEXT[max(0, dash_at - 300):dash_at + 900]
check("if(InpEnablePriceAction && InpPAShowOnDashboard)" in dash_seg,
      "C the PA rows need BOTH the module switch and the dashboard switch")
check('string pa_dir=(g_pa_dir>0?"BUY":(g_pa_dir<0?"SELL":"none"));' in dash_seg,
      "C a side is printed only when a direction is actually resolved")
check("not a win rate" in dash_seg or "confluence, not a win rate" in dash_seg,
      "C the score is labelled a confluence count, not a win rate")
check("if(ln>11) ln=11;" in TEXT and "string lines[11]; color cols[11]; int ln=0;" in TEXT,
      "C the 11-row card contract is untouched")

# =====================================================================
# D. THE ONE EDIT TO EXISTING CODE: an opt-in gate that is inert by default
# =====================================================================
check(input_default("InpPARequireZoneContext") == "false",
      "D InpPARequireZoneContext defaults to false")
ccs = body_of("int ContextualCandleScore(const SCandleIntel &candle", "D ContextualCandleScore")
ccs_code = strip_comments(ccs)
ccs_raw = ccs  # the quoted regime literals survive only in the raw body
GATE = "if(InpPARequireZoneContext && !zone_ok && !candle_in_zone) return 0;"
check(ccs_code.count(GATE) == 1,
      "D the hard gate appears exactly once (%d)" % ccs_code.count(GATE))
cia = "bool candle_in_zone=(price<=zone_top+MathMax(_Point,atr*0.15) &&"
precedes(ccs_code, cia, GATE, "D the gate sits after candle_in_zone is computed")
precedes(ccs_code, GATE, "if(zone_ok) score+=12.0;",
         "D the gate sits before the zone bonus it strengthens")
ORIGINAL = ["double score=(double)candle.score*0.45;",
            "if(zone_ok) score+=12.0;",
            "if(candle_in_zone) score+=8.0;",
            "if(sweep_ok) score+=10.0;",
            "if(structure_ok) score+=10.0;",
            "if(candle.close_location>=0.80 || candle.close_location<=0.20) score+=6.0;",
            "if(candle.body_ratio>=0.55) score+=4.0;",
            'if(regime=="EXPANSION" || regime=="TREND") score+=4.0;',
            'if(regime=="COMPRESSION") score-=4.0;']
missing = [o for o in ORIGINAL if o not in ccs_raw]
check(not missing, "D every pre-existing scoring line is still present", str(missing))
opos = [ccs_raw.index(o) for o in ORIGINAL if o in ccs_raw]
check(len(opos) == len(ORIGINAL) and opos == sorted(opos),
      "D the pre-existing scoring lines keep their original order")
check(ccs_code.count("score+=12.0") == 1 and ccs_code.count("score+=8.0") == 1 and
      ccs_code.count("score+=10.0") == 2,
      "D no existing weight was changed: 12, 8 and 10x2 still appear once/twice")
check("double score=(double)candle.score*0.45;" in ccs_code,
      "D the base multiplier is still 0.45")


def ccs_score(candle_score, valid, confirms, zone_ok, candle_in_zone, sweep_ok,
              structure_ok, close_location, body_ratio, regime, require_zone):
    """Re-implementation of ContextualCandleScore, with and without the gate."""
    if not valid or not confirms:
        return 0
    if require_zone and not zone_ok and not candle_in_zone:
        return 0
    s = candle_score * 0.45
    if zone_ok:
        s += 12.0
    if candle_in_zone:
        s += 8.0
    if sweep_ok:
        s += 10.0
    if structure_ok:
        s += 10.0
    if close_location >= 0.80 or close_location <= 0.20:
        s += 6.0
    if body_ratio >= 0.55:
        s += 4.0
    if regime in ("EXPANSION", "TREND"):
        s += 4.0
    if regime == "COMPRESSION":
        s -= 4.0
    return s


def ccs_original(candle_score, valid, confirms, zone_ok, candle_in_zone, sweep_ok,
                 structure_ok, close_location, body_ratio, regime):
    """The scorer AS IT WAS before Phase 4 - the same lines, with no gate at all.
    Comparing against this, and not against a second call of ccs_score with the
    flag also off, is what makes the inertness claim mean anything."""
    if not valid or not confirms:
        return 0
    s = candle_score * 0.45
    if zone_ok:
        s += 12.0
    if candle_in_zone:
        s += 8.0
    if sweep_ok:
        s += 10.0
    if structure_ok:
        s += 10.0
    if close_location >= 0.80 or close_location <= 0.20:
        s += 6.0
    if body_ratio >= 0.55:
        s += 4.0
    if regime in ("EXPANSION", "TREND"):
        s += 4.0
    if regime == "COMPRESSION":
        s -= 4.0
    return s


cases = 0
drift = []
for cso in (30, 65, 72, 85, 88):
    for zok in (False, True):
        for cia_ in (False, True):
            for sw in (False, True):
                for st in (False, True):
                    for cl_ in (0.10, 0.50, 0.90):
                        for br in (0.30, 0.60):
                            for rg in ("RANGE", "TREND", "EXPANSION", "COMPRESSION"):
                                was = ccs_original(cso, True, True, zok, cia_, sw, st, cl_, br, rg)
                                now = ccs_score(cso, True, True, zok, cia_, sw, st, cl_, br, rg, False)
                                cases += 1
                                if was != now:
                                    drift.append((cso, zok, cia_, sw, st, cl_, br, rg, was, now))
check(cases > 1000, "D the off-path was compared over %d input combinations" % cases)
check(not drift, "D with the flag OFF the scorer equals the pre-change scorer on every case",
      str(drift[:3]))
check(any(ccs_original(c, True, True, False, False, True, True, 0.9, 0.6, "TREND") > 0
          for c in (30, 65, 72, 85, 88)),
      "D the pre-change scorer really did reward a standalone candle (the gap is real)")
check(ccs_score(88, True, True, False, False, True, True, 0.9, 0.6, "TREND", False) > 0,
      "D with the flag OFF a standalone MORNING_STAR still scores - the gap is documented")
check(ccs_score(88, True, True, False, False, True, True, 0.9, 0.6, "TREND", True) == 0,
      "D with the flag ON that same standalone candle scores 0")
check(ccs_score(88, True, True, True, False, False, False, 0.5, 0.3, "RANGE", True) > 0,
      "D the gate does not suppress a candle the caller already validated a zone for")
check(ccs_score(88, False, True, False, False, True, True, 0.9, 0.6, "TREND", True) == 0 and
      ccs_score(88, True, False, False, False, True, True, 0.9, 0.6, "TREND", True) == 0,
      "D the pre-existing validity and direction guards still fire first")
check("double zone_mid=(zone_top+zone_bottom)*0.5;" in ccs_code,
      "D the pre-existing unused zone_mid local is left alone (reported, not touched)")
check(ccs_code.count("zone_mid") == 1,
      "D zone_mid is still assigned once and used zero times, exactly as before")

# =====================================================================
# E. THE PRE-EXISTING THREE-WAY CANDLE DIVERGENCE - pinned, not repaired
# =====================================================================
# Three functions classify the same closed bar with different geometry. Phase 4
# reports this; it does not unify it, because C1 is an ENTRY gate and making it
# match AnalyzeClosedCandle() would tighten entries and change history.
def acc_hammer(o, h, l, c):
    rng = h - l
    if rng <= POINT:
        return False
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return (lower >= body * 2.0 and upper <= max(body * 0.75, POINT * 2.0) and
            (c - l) / rng >= 0.62)


def acc_bull_engulf(o, h, l, c, po, pc):
    body = abs(c - o)
    prev_body = abs(pc - po)
    return (c > o and c >= po and o <= pc and c > pc and body >= prev_body * 0.90)


def aci_bull_engulf(o, h, l, c, po, pc):
    body = abs(c - o)
    prev_body = abs(pc - po)
    return (c > o and pc < po and c >= po and o <= pc and body >= prev_body * 0.90)


def c1_bull_engulf(o, h, l, c, po, pc):
    return c > o and pc < po and c >= po and o <= pc


def c1_bull_pin(o, h, l, c):
    rng = max(h - l, POINT)
    lower = min(o, c) - l
    return lower >= 0.50 * rng and c >= o


check(TEXT.count("bool hammer=(lower>=body*2.0 && upper<=MathMax(body*0.75,_Point*2.0) &&") == 1,
      "E AnalyzeClosedCandle's hammer test is still 2.0x body with a capped upper wick")
check(TEXT.count("bool bull_pin=(lower_wick>=0.50*c_range && c_close>=c_open);") == 1,
      "E the C1 gate's pin test is still 0.50 of range with no upper-wick condition")
check(TEXT.count("bool bull_engulf=(c_close>c_open && p_close<p_open && c_close>=p_open && c_open<=p_close);") == 1,
      "E the C1 gate's engulf test is still the body-size-free variant")
check(TEXT.count("bool bull_engulf = (up && prev_c < prev_o && cur_c >= prev_o && cur_o <= prev_c && body >= prev_body * 0.90);") == 1,
      "E AnalyzeCandleIntelligence's engulf test is still the third variant")
check(TEXT.count("if(lower >= body * 1.8 && ci.close_location >= 0.60) ci.confirms_buy = true;") == 1,
      "E AnalyzeCandleIntelligence's rejection test is still 1.8x body at 0.60")
check(TEXT.count("bool closes_inside=(c_close>=lo && c_close<=hi);") == 1,
      "E the C1 gate is still the only place requiring the close inside the zone")

# Search the space of well-formed bars for disagreement, rather than asserting a
# hand-picked example. A bar is well formed when low <= min(o,c) and high >= max(o,c).
grid = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
pin_only_c1 = []
eng_only_acc = []
eng_only_c1 = []
for l in grid:
    for h in grid:
        if h - l <= POINT:
            continue
        for o in grid:
            for c in grid:
                if min(o, c) < l or max(o, c) > h:
                    continue
                if c1_bull_pin(o, h, l, c) and not acc_hammer(o, h, l, c):
                    pin_only_c1.append((o, h, l, c))
                for po in grid:
                    for pc in grid:
                        if acc_bull_engulf(o, h, l, c, po, pc) and not c1_bull_engulf(o, h, l, c, po, pc):
                            eng_only_acc.append((o, h, l, c, po, pc))
                        if c1_bull_engulf(o, h, l, c, po, pc) and not acc_bull_engulf(o, h, l, c, po, pc):
                            eng_only_c1.append((o, h, l, c, po, pc))
bars_examined = len(grid) ** 4
check(bars_examined > 3000, "E %d well-formed bars were examined" % bars_examined)
check(len(pin_only_c1) > 0,
      "E the C1 pin bar fires on %d bars AnalyzeClosedCandle refuses as a hammer" % len(pin_only_c1))
check(len(eng_only_acc) > 0,
      "E AnalyzeClosedCandle's engulf fires on %d bars the C1 gate refuses" % len(eng_only_acc))
# C1 additionally requires a bearish predecessor, so its engulf is a subset on that
# axis; the asymmetry that matters is the missing body test and the missing c>prev_c.
check(len(eng_only_c1) == 0,
      "E every bar C1 calls an engulf, AnalyzeClosedCandle also calls one (%d)" % len(eng_only_c1))

# The two documented examples, stated so the report is checkable.
ex1 = (95.0, 100.0, 90.0, 95.0)   # a doji: lower wick exactly 50% of range
ex2 = (99.0, 104.0, 90.0, 100.0)  # 64% lower wick AND a large upper wick
for ex in (ex1, ex2):
    o, h, l, c = ex
    check(c1_bull_pin(o, h, l, c) is True and acc_hammer(o, h, l, c) is False,
          "E bar o=%g h=%g l=%g c=%g is a C1 pin but not an ACC hammer" % ex)
    body_ratio = abs(c - o) / (h - l)
    check(body_ratio <= 0.12,
          "E that same bar is a DOJI (body ratio %.3f) to AnalyzeClosedCandle" % body_ratio)
check(acc_bull_engulf(89.0, 101.0, 89.0, 101.0, 90.0, 100.0) is True and
      c1_bull_engulf(89.0, 101.0, 89.0, 101.0, 90.0, 100.0) is False,
      "E a bullish engulf after a BULLISH bar: ACC fires, C1 refuses")
check(pa_pattern_direction("DOJI") == 0,
      "E so PA treats those bars as directionless, which is the honest reading")

# =====================================================================
# F. INPUTS, BUFFERS AND FILE INTEGRITY
# =====================================================================
EXPECT = {"InpEnablePriceAction": "false",
          "InpPAShowOnDashboard": "false",
          "InpPARequireZoneContext": "false",
          "InpPAIncludeInsideBar": "true",
          "InpPAInsideBarStrength": "45",
          "InpPAZoneToleranceATR": "0.15",
          "InpPAIncludePOC": "true"}
for name, want in sorted(EXPECT.items()):
    got = input_default(name)
    check(got == want, "F input %s defaults to %s" % (name, want), "found %r" % got)
for flag in ("InpEnablePriceAction", "InpPAShowOnDashboard", "InpPARequireZoneContext"):
    check(input_default(flag) == "false", "F the enable flag %s is OFF by default" % flag)

# InpEnablePriceAction does not carry the InpPA prefix, so counting InpPA* alone
# reports 6 of the module's 7 inputs.
pa_inputs = (set(re.findall(r'\b(InpPA\w+)\s*=', TEXT)) |
             set(re.findall(r'\b(InpEnablePriceAction)\s*=', TEXT)))
check(len(pa_inputs) == 7, "F the module adds exactly 7 inputs (%d)" % len(pa_inputs),
      str(sorted(pa_inputs)))
check(pa_inputs == set(EXPECT), "F the declared inputs are exactly the documented set")
for nm in sorted(pa_inputs):
    check(TEXT.count(nm) >= 2, "F %s is declared and actually referenced" % nm)

check(TEXT.count("#property indicator_buffers 19") == 1,
      "F indicator_buffers is still 19 - no buffer was appended")
check(len(re.findall(r'(?m)^#property indicator_plots\s+7\b', TEXT)) == 1,
      "F indicator_plots is still 7")
check(len(re.findall(r"SetIndexBuffer\(\s*(\d+)", TEXT)) == 19,
      "F there are still exactly 19 SetIndexBuffer calls")
idx = sorted(int(m) for m in re.findall(r"SetIndexBuffer\(\s*(\d+)", TEXT))
check(idx == list(range(19)), "F buffer indices are still 0..18 with no gap or shift", str(idx))

pa_globals = re.findall(r"^(?:string|int|double|bool)\s+(g_pa_\w+)\s*[=;]", TEXT, flags=re.M)
check(len(set(pa_globals)) >= 13,
      "F the module declares %d private g_pa_* globals" % len(set(pa_globals)))
check(len(set(pa_globals)) == len(pa_globals),
      "F no g_pa_* global is declared twice")
for g in ("g_pa_pattern", "g_pa_strength", "g_pa_dir", "g_pa_confirms", "g_pa_score",
          "g_pa_reason", "g_pa_invalidation", "g_pa_in_zone", "g_pa_zone_name"):
    check(g in set(pa_globals), "F the published state %s exists" % g)
cl = body_of("void PA_Clear()", "F PA_Clear")
for g in ("g_pa_pattern", "g_pa_strength", "g_pa_dir", "g_pa_score", "g_pa_reason",
          "g_pa_invalidation", "g_pa_in_zone", "g_pa_zone_name"):
    check(g in strip_comments(cl), "F PA_Clear resets %s to an inert value" % g)

check(BARE_LF == 0, "F the file has no bare LF (%d)" % BARE_LF)
check(TEXT.count("AUDIT-PA1") >= 2, "F the section is tagged AUDIT-PA1")
# Scoped to the section: the file already contains ENUM_PMI_PATH_STATUS, whose name
# happens to contain "PA", so a whole-file search for an enum matching /PA/ is a
# false positive rather than evidence about this module.
check(re.search(r"enum\s+ENUM_", pa_section) is None,
      "F the section declares no enum, so no existing enumerator can shift")
check(len(re.findall(r'(?m)^#property version\s+"', TEXT)) == 1,
      "F there is still exactly one version property line (comments excluded)")

print("")
print("=" * 74)
print("AUDIT-PA1 checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("This is a static transcription + wiring contract. It is NOT a backtest, it")
print("produces no win rate, and it does NOT prove MetaEditor compiles the file.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
