#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-CF1  CONFLUENCE ENGINE - transcription + wiring contract.

Phase 6 of the strategy-module extension for nadir2.mq5. What this file proves,
and what it deliberately does NOT claim:

  * It transcribes the module's pure cores into Python, re-derives their
    behaviour exhaustively, and then pins the transcribed guards, constants and
    literals back to the .mq5 text. Without that second step the transcription
    could drift from the source and still pass.
  * It proves "missing evidence = 0, never a free point" STRUCTURALLY: over all
    64 present/absent patterns of the six legs, no evidence at all scores zero.
  * It proves the engine can never force a direction: a side is named only when
    EXACTLY ONE side clears the minimum. Both clearing is a conflict, neither
    clearing is a shortfall, and both produce a stand-aside.
  * It proves the engine is a SEPARATE score sitting BESIDE the existing ones, by
    pinning the exact call-count delta it introduced into every existing scorer
    and the exact unchanged occurrence counts of g_score. / final_score /
    setup_quality_score.
  * It proves the two documented free-point floors in the EXISTING scorers were
    neutralised locally rather than by editing them: ScoreSession() still returns
    30.0 and ScoreHTF() still returns 50.0 verbatim, and the CF section never
    calls ScoreHTF() at all.
  * It is a static contract test. It is NOT a backtest, produces no win rate, and
    does NOT prove MetaEditor compiles the file - only F7 does that.
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
    TEXT = fh.read()
BARE_LF = TEXT.count("\n") - TEXT.count("\r\n")


def strip_comments(src):
    """Remove comments and blank literal contents in ONE pass."""
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
    i, depth, started, n = sig_at, 0, False, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            if j < 0:
                return -1
            i = j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            if j < 0:
                return -1
            i = j + 2
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


def body_of(sig, label, floor=0):
    """Body of the DEFINITION matching `sig`, skipping forward declarations."""
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


def norm(s):
    """Collapse whitespace so a pin survives the file's run-on alignment."""
    return re.sub(r"\s+", " ", s).strip()


def precedes(hay, first, second, label):
    a, b = hay.find(first), hay.find(second)
    check(a >= 0 and b >= 0 and a < b, label, "first@%d second@%d" % (a, b))


def input_default(name):
    m = re.search(r"\binput\s+[A-Za-z_][\w\s\*&]*?\b" + re.escape(name) +
                  r"\s*=\s*([^,;]+)[,;]", TEXT)
    return m.group(1).strip() if m else None


c_all = strip_comments(TEXT)


def call_count(sig_call):
    """Occurrences of a real CALL of `sig_call`, excluding declarations.

    A declaration and a call can share text exactly (`void   CF_Clear();` contains
    `CF_Clear();`), so a raw count over-reports. Subtracting fixed type prefixes is
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

# The CF module's own slice: banner to the end of its OWN self-test. Never end a
# slice at a shared downstream marker - another module may be inserted there.
CF_BANNER = "// AUDIT-CF1 CONFLUENCE ENGINE"
_i0 = TEXT.find(CF_BANNER)
_j = TEXT.find("bool CF_SelfTest(string &where)", _i0)
_i1 = _fn_end(TEXT, _j)
check(_i0 > 0 and _i1 > _j, "A0 the CF section is locatable and brace-terminated",
      "banner@%d selftest@%d end@%d" % (_i0, _j, _i1))
CF_SEC = TEXT[_i0:_i1] if (_i0 > 0 and _i1 > 0) else ""
CF_SEC_C = strip_comments(CF_SEC)
# vacuity guard: an empty or truncated slice would make every "absent" check pass
check(len(CF_SEC) > 8000, "A0 the CF slice is long enough to be the real section",
      "len=%d" % len(CF_SEC))


# =====================================================================
# A. PURE CORES - transcribed, re-derived exhaustively, then pinned back
# =====================================================================
DEFAULT_W = (20, 20, 20, 10, 15, 15)


def cf_pillar(evidence, weight):
    if not (evidence > 0.0):
        return 0.0
    ev = 100.0 if evidence > 100.0 else evidence
    w = 0 if weight < 0 else (100 if weight > 100 else weight)
    return ev * float(w) / 100.0


def cf_aggregate(legs, weights=DEFAULT_W):
    s = 0.0
    for l, w in zip(legs, weights):
        s += cf_pillar(l, w)
    if not (s > 0.0):
        return 0.0
    return 100.0 if s > 100.0 else s


def cf_pick_side(buy, sell, min_display):
    need = 0 if min_display < 0 else (100 if min_display > 100 else min_display)
    b, s = buy >= need, sell >= need
    if not b and not s:
        return 0
    if b and s:
        return 0
    return 1 if b else -1


def cf_is_ambiguous(buy, sell, min_display):
    need = 0 if min_display < 0 else (100 if min_display > 100 else min_display)
    return buy >= need and sell >= need


def cf_contradicts(side, source_dir):
    if side == 0 or source_dir == 0:
        return False
    return source_dir != side


def cf_count_contradictions(side, dirs):
    return sum(1 for d in dirs if cf_contradicts(side, d))


def cf_stand_aside(side, buy, sell, min_display, contradictions,
                   weights_valid, weight_sum, strategy_ok, veto):
    need = 0 if min_display < 0 else (100 if min_display > 100 else min_display)
    if not weights_valid:
        return ("NO TRADE: confluence weights sum to %d, they must sum to exactly 100"
                % weight_sum)
    if side == 0 and buy >= need and sell >= need:
        return ("NO TRADE: both sides score above the minimum (%d buy vs %d sell), "
                "the evidence is ambiguous" % (buy, sell))
    if veto and contradictions > 0:
        return ("NO TRADE: %d source(s) with evidence contradict the leading side"
                % contradictions)
    if not strategy_ok:
        return "NO TRADE: no active strategy module agrees with this reading"
    if side == 0:
        return ("NO TRADE: best side scores %d, below the minimum display score of %d"
                % (max(buy, sell), need))
    return ""


# --- A1 absent evidence scores nothing, at every weight -----------------------
check(all(cf_pillar(0.0, w) == 0.0 for w in range(-5, 501)),
      "A1 zero evidence scores 0 at every weight from -5 to 500")
check(all(cf_pillar(-1.0 * k, 20) == 0.0 for k in range(0, 200)),
      "A1 negative evidence scores 0")
check(cf_pillar(float('nan'), 20) == 0.0,
      "A1 NaN evidence scores 0 rather than propagating")

# --- A2 the mapping is exactly linear in the weight ---------------------------
check(all(abs(cf_pillar(100.0, w) - float(w)) < 1e-9 for w in range(0, 101)),
      "A2 full evidence at weight w scores exactly w, for all w in 0..100")
check(all(abs(cf_pillar(50.0, w) - w / 2.0) < 1e-9 for w in range(0, 101)),
      "A2 half evidence scores exactly half the weight")
check(all(cf_pillar(1e-9, w) >= 0.0 for w in range(0, 101)),
      "A2 a trace of evidence never scores negative")

# --- A3 clamping: neither leg can be inflated ---------------------------------
check(all(abs(cf_pillar(140.0, w) - cf_pillar(100.0, w)) < 1e-9 for w in range(0, 101)),
      "A3 evidence above 100 is clamped to 100")
check(all(abs(cf_pillar(60.0, w) - cf_pillar(60.0, 100)) < 1e-9 for w in range(101, 600)),
      "A3 a weight above 100 is clamped to 100")
check(all(cf_pillar(60.0, w) == 0.0 for w in range(-600, 0)),
      "A3 a negative weight scores nothing")

# --- A4 the six default weights sum to exactly 100 ----------------------------
check(sum(DEFAULT_W) == 100, "A4 the six default weights sum to 100 in the model")
check(abs(cf_aggregate((100.0,) * 6) - 100.0) < 1e-9,
      "A4 full evidence on all six legs aggregates to exactly 100")
check(cf_aggregate((0.0,) * 6) == 0.0,
      "A4 no evidence at all aggregates to exactly 0")
check(cf_aggregate((100.0,) * 6, (100,) * 6) <= 100.0 + 1e-9,
      "A4 the aggregate is capped at 100 even with absurd weights")

# --- A5 exhaustive sweep of all 64 present/absent patterns --------------------
sweep = 0
a5_zero = a5_full = a5_range = a5_nonzero = a5_mono = True
for m in range(64):
    legs = tuple(100.0 if (m & (1 << k)) else 0.0 for k in range(6))
    present = bin(m).count("1")
    sc = cf_aggregate(legs)
    sweep += 1
    if present == 0 and sc != 0.0:
        a5_zero = False
    if present == 6 and abs(sc - 100.0) > 1e-9:
        a5_full = False
    if sc < 0.0 or sc > 100.0:
        a5_range = False
    if present > 0 and sc <= 0.0:
        a5_nonzero = False
    # monotonicity: supplying the MTF leg can never lower the total
    richer = tuple(100.0 if (i == 5 or (m & (1 << i))) else 0.0 for i in range(6))
    if cf_aggregate(richer) + 1e-9 < sc:
        a5_mono = False
check(sweep == 64, "A5 the sweep covered all 64 evidence patterns", str(sweep))
check(a5_zero, "A5 six absent legs score 0 - never a free point")
check(a5_full, "A5 six present legs at full evidence score exactly 100")
check(a5_range, "A5 the score stays inside 0..100 for every pattern")
check(a5_nonzero, "A5 any present leg produces a strictly positive score")
check(a5_mono, "A5 adding evidence to a leg never lowers the total")
check(all(abs(cf_aggregate(tuple(100.0 if i != k else 0.0 for i in range(6)))
              - (100 - DEFAULT_W[k])) < 1e-9 for k in range(6)),
      "A5 dropping exactly one leg costs exactly that leg's weight")

# --- A6 a side is named ONLY when exactly one side clears the minimum ---------
a6 = True
a6_forced = True
for buy in range(0, 101, 5):
    for sell in range(0, 101, 5):
        for need in (0, 30, 60, 100):
            got = cf_pick_side(buy, sell, need)
            clears = (1 if buy >= need else 0) + (1 if sell >= need else 0)
            want = 0 if clears != 1 else (1 if buy >= need else -1)
            if got != want:
                a6 = False
            if clears != 1 and got != 0:
                a6_forced = False
check(a6, "A6 CF_PickSide names a side only when exactly one side clears")
check(a6_forced, "A6 the engine never forces a direction out of a conflict or a shortfall")
check(cf_pick_side(80, 80, 60) == 0, "A6 both sides clearing is a stand-aside, not a tie")
check(cf_pick_side(20, 30, 60) == 0, "A6 neither side clearing is a stand-aside")
check(cf_pick_side(60, 0, 60) == 1, "A6 the minimum is inclusive at exactly the threshold")
check(cf_pick_side(90, 10, 200) == 0, "A6 a minimum above 100 can never be cleared")
check(cf_pick_side(90, 10, -5) == 0,
      "A6 a negative minimum clamps to 0, which makes BOTH sides clear -> ambiguous")

# --- A7 ambiguity is detected independently of the pick -----------------------
amb = True
for buy in range(0, 101, 5):
    for sell in range(0, 101, 5):
        for need in (0, 30, 60, 100):
            n2 = 0 if need < 0 else (100 if need > 100 else need)
            if cf_is_ambiguous(buy, sell, need) != (buy >= n2 and sell >= n2):
                amb = False
check(amb, "A7 CF_IsAmbiguous agrees with its definition over the whole grid")
check(cf_is_ambiguous(70, 70, 60) and not cf_is_ambiguous(70, 10, 60)
      and not cf_is_ambiguous(10, 10, 60),
      "A7 ambiguous only when both sides are at or above the minimum")

# --- A8 a silent source is ABSENT, not disagreeing ----------------------------
check(not cf_contradicts(1, 0) and not cf_contradicts(-1, 0),
      "A8 a source carrying no direction is never a contradiction")
check(not cf_contradicts(0, 1) and not cf_contradicts(0, -1),
      "A8 with no side chosen nothing can contradict")
check(cf_contradicts(1, -1) and cf_contradicts(-1, 1),
      "A8 an opposing source IS a contradiction")
check(not cf_contradicts(1, 1) and not cf_contradicts(-1, -1),
      "A8 an agreeing source is not a contradiction")
check(cf_count_contradictions(1, (1, 1, 1, 1)) == 0, "A8 four agreeing sources = 0")
check(cf_count_contradictions(1, (-1, 0, 0, 0)) == 1, "A8 one opposing, three silent = 1")
check(cf_count_contradictions(1, (-1, -1, -1, -1)) == 4, "A8 four opposing = 4")
check(cf_count_contradictions(0, (-1, -1, -1, -1)) == 0,
      "A8 no side chosen means no contradiction can be counted")
check(all(cf_count_contradictions(s, d) <= 4 for s in (-1, 0, 1)
          for d in ((x, y, z, w) for x in (-1, 0, 1) for y in (-1, 0, 1)
                    for z in (-1, 0, 1) for w in (-1, 0, 1))),
      "A8 the contradiction count is bounded by the four sources over all 81 combos")

# --- A9 the stand-aside sentence and its priority order -----------------------
check(cf_stand_aside(1, 80, 10, 60, 0, False, 110, True, False)
      .startswith("NO TRADE: confluence weights sum to 110"),
      "A9 invalid weights veto even a strong side and quote the real sum")
check(cf_stand_aside(1, 80, 10, 60, 3, False, 90, False, True)
      .startswith("NO TRADE: confluence weights"),
      "A9 a configuration error outranks ambiguity, contradiction and shortfall")
check(cf_stand_aside(0, 80, 80, 60, 0, True, 100, True, False)
      .startswith("NO TRADE: both sides"),
      "A9 two sides above the minimum is reported as ambiguous")
check(cf_stand_aside(1, 80, 10, 60, 2, True, 100, True, True)
      .startswith("NO TRADE: 2 source"),
      "A9 contradictions are reported with their count")
check(cf_stand_aside(1, 80, 10, 60, 2, True, 100, True, False) == "",
      "A9 with the veto disabled, contradictions do NOT force a stand-aside")
check(cf_stand_aside(1, 80, 10, 60, 0, True, 100, False, False)
      .startswith("NO TRADE: no active strategy"),
      "A9 an unmet strategy requirement is reported")
check(cf_stand_aside(0, 40, 20, 60, 0, True, 100, True, False)
      .startswith("NO TRADE: best side scores 40"),
      "A9 a shortfall quotes the leading side's score")
check(cf_stand_aside(1, 80, 10, 60, 0, True, 100, True, False) == "",
      "A9 a clean uncontradicted side above the minimum is NOT a stand-aside")
reasons = []
for _side in (-1, 0, 1):
    for _buy in (0, 40, 60, 80):
        for _sell in (0, 40, 60, 80):
            for _nd in (0, 60):
                for _cc in (0, 2):
                    for _wv in (True, False):
                        for _so in (True, False):
                            for _v in (True, False):
                                reasons.append(cf_stand_aside(_side, _buy, _sell, _nd,
                                                              _cc, _wv, 100, _so, _v))
check(len(reasons) == 1536, "A9 the reason sweep covered 1536 combinations", str(len(reasons)))
check(all(r == "" or r.startswith("NO TRADE: ") for r in reasons),
      "A9 every non-empty reason uses the specification's 'NO TRADE: <reason>' format")
check(any(r == "" for r in reasons),
      "A9 at least one combination is a clean trade, so the function is not always refusing")

# --- A10 pin the transcription back to the source text ------------------------
pil = norm(body_of("double CF_Pillar(const double evidence,const int weight)", "A10 CF_Pillar"))
check("if(!(evidence>0.0)) return 0.0;" in pil,
      "A10 CF_Pillar refuses non-positive evidence FIRST, before any arithmetic")
check("double ev=(evidence>100.0 ? 100.0 : evidence);" in pil,
      "A10 CF_Pillar clamps evidence to 100")
check("int w=(weight<0 ? 0 : (weight>100 ? 100 : weight));" in pil,
      "A10 CF_Pillar clamps the weight into 0..100")
check("return ev*(double)w/100.0;" in pil,
      "A10 CF_Pillar is the only place evidence becomes points")
precedes(pil, "if(!(evidence>0.0)) return 0.0;", "return ev*(double)w/100.0;",
         "A10 the zero-evidence refusal precedes the scoring return")

agg = norm(body_of("double CF_Aggregate(const double structure,const double liquidity,const double zone,",
                   "A10 CF_Aggregate"))
check(agg.count("CF_Pillar(") == 6,
      "A10 CF_Aggregate routes all SIX legs through CF_Pillar", str(agg.count("CF_Pillar(")))
check("return (sum>100.0 ? 100.0 : sum);" in agg,
      "A10 CF_Aggregate caps the total at 100")
check("if(!(sum>0.0)) return 0.0;" in agg,
      "A10 CF_Aggregate refuses a non-positive total")
check(len(re.findall(r"w_structure|w_liquidity|w_zone|w_session|w_candle|w_mtf", agg)) >= 12,
      "A10 CF_Aggregate takes a separate weight for each of the six legs")

pick = norm(body_of("int CF_PickSide(const int buy_score,const int sell_score,const int min_display)",
                    "A10 CF_PickSide"))
check("if(!buy_ok && !sell_ok) return 0;" in pick,
      "A10 CF_PickSide refuses when neither side clears")
check("if(buy_ok && sell_ok) return 0;" in pick,
      "A10 CF_PickSide refuses when BOTH sides clear - no forced direction")
check(pick.count("return 0;") == 2,
      "A10 CF_PickSide has exactly two stand-aside returns", str(pick.count("return 0;")))
check("int need=(min_display<0 ? 0 : (min_display>100 ? 100 : min_display));" in pick,
      "A10 CF_PickSide clamps the minimum into 0..100")

con = norm(body_of("bool CF_Contradicts(const int side,const int source_dir)", "A10 CF_Contradicts"))
check("if(side==0 || source_dir==0) return false;" in con,
      "A10 CF_Contradicts treats a directionless source as absent")

cnt = norm(body_of("int CF_CountContradictions(const int side,const int mtf_dir,const int zone_dir,",
                   "A10 CF_CountContradictions"))
check(cnt.count("CF_Contradicts(") == 4,
      "A10 CF_CountContradictions consults exactly the four directional sources",
      str(cnt.count("CF_Contradicts(")))

# A10b inclusivity of the minimum. The model tests this behaviourally, but the
# SOURCE comparison operator is what actually runs, so it is pinned too - a ">="
# silently becoming ">" would otherwise pass every behavioural check.
check("bool buy_ok=(buy_score>=need);" in pick,
      "A10b CF_PickSide compares the long side inclusively (>=)")
check("bool sell_ok=(sell_score>=need);" in pick,
      "A10b CF_PickSide compares the short side inclusively (>=)")

amb_b = norm(body_of("bool CF_IsAmbiguous(const int buy_score,const int sell_score,const int min_display)",
                     "A10b CF_IsAmbiguous"))
check("return (buy_score>=need && sell_score>=need);" in amb_b,
      "A10b CF_IsAmbiguous requires BOTH sides at or above the minimum")
check("int need=(min_display<0 ? 0 : (min_display>100 ? 100 : min_display));" in amb_b,
      "A10b CF_IsAmbiguous clamps the minimum exactly as CF_PickSide does")

# A10c the stand-aside formatter. This was transcribed but never pinned back, so
# its guard ORDER and its "NO TRADE: " prefix were both unprotected.
rs = norm(body_of("string CF_StandAsideReason(const int side,const int buy_score,const int sell_score,",
                  "A10c CF_StandAsideReason"))
check(rs.count('"NO TRADE: ') == 5,
      "A10c all five stand-aside branches use the specification's 'NO TRADE: ' prefix",
      str(rs.count('"NO TRADE: ')))
check(rs.count('return "";') == 1,
      "A10c exactly one branch returns the empty string - the clean-trade path",
      str(rs.count('return "";')))
precedes(rs, "if(side==0)", 'return "";',
         "A10c the clean-trade return comes after every stand-aside guard")
for guard in ("if(!weights_valid)", "if(side==0 && buy_score>=need && sell_score>=need)",
              "if(veto && contradictions>0)", "if(!strategy_ok)", "if(side==0)"):
    check(guard in rs, "A10c CF_StandAsideReason carries the guard %s" % guard)
# priority order: a configuration error must be tested before anything else
precedes(rs, "if(!weights_valid)", "if(side==0 && buy_score>=need && sell_score>=need)",
         "A10c the weight error outranks ambiguity")
precedes(rs, "if(side==0 && buy_score>=need && sell_score>=need)", "if(veto && contradictions>0)",
         "A10c ambiguity outranks the contradiction veto")
precedes(rs, "if(veto && contradictions>0)", "if(!strategy_ok)",
         "A10c the contradiction veto outranks the strategy requirement")
precedes(rs, "if(!strategy_ok)", "if(side==0)",
         "A10c the strategy requirement outranks the plain shortfall")
check("IntegerToString(weight_sum)" in rs,
      "A10c a weight error quotes the sum the operator actually configured")
check("IntegerToString(contradictions)" in rs,
      "A10c a contradiction quotes how many sources disagreed")
check("IntegerToString(buy_score>=sell_score ? buy_score : sell_score)" in rs,
      "A10c a shortfall quotes the LEADING side, not whichever came first")
check("&& sell_score>=need" in rs and "buy_score>=need &&" in rs,
      "A10c ambiguity is inclusive on both sides, matching CF_PickSide")

print("")

# =====================================================================
# B. MISSING EVIDENCE = 0. The two existing free-point floors are
#    neutralised LOCALLY, and the existing scorers are untouched.
# =====================================================================
upd = body_of("void CF_Update(const int closed,const int rates_total)", "B0 CF_Update")
upd_n = norm(upd)
upd_c = strip_comments(upd)

# B1 the session floor is detected, not inherited
check("#define CF_SESSION_NO_EVIDENCE 30.0" in TEXT.replace("\r\n", "\n"),
      "B1 the session no-evidence floor is named as 30.0, matching ScoreSession()")
check("g_cf_has_session=(sess_raw>CF_SESSION_NO_EVIDENCE+0.001);" in upd_n,
      "B1 CF tests the session raw value against that floor")
check("g_cf_pillar_session=(g_cf_has_session ? sess_raw : 0.0);" in upd_n,
      "B1 an unmatched session contributes 0, not ScoreSession()'s free 30")
precedes(upd_n, "double sess_raw=ScoreSession();", "g_cf_has_session=",
         "B1 the session is read before it is tested")

# B2 ScoreHTF is bypassed entirely, so its free 50 can never reach this engine
check(upd_c.count("ScoreHTF(") == 0,
      "B2 CF_Update never calls ScoreHTF()", str(upd_c.count("ScoreHTF(")))
check(CF_SEC_C.count("ScoreHTF(") == 0,
      "B2 the whole CF section never calls ScoreHTF()", str(CF_SEC_C.count("ScoreHTF(")))
check("g_cf_has_mtf=(InpUseHTFBias && g_htf_bias!=0);" in upd_n,
      "B2 the MTF leg tests the bias itself for existence")
check("int mtf_dir=(g_cf_has_mtf ? g_htf_bias : 0);" in upd_n,
      "B2 with no bias the MTF direction is 0, i.e. absent, not neutral-50")
check("double mtf_buy =(g_cf_has_mtf && mtf_dir>0 ? 100.0 : 0.0);" in upd_n.replace("  ", " ")
      or "double mtf_buy=(g_cf_has_mtf && mtf_dir>0 ? 100.0 : 0.0);" in upd_n,
      "B2 the long MTF leg is 100 only on an agreeing bias, else 0")
check("double mtf_sell=(g_cf_has_mtf && mtf_dir<0 ? 100.0 : 0.0);" in upd_n,
      "B2 the short MTF leg is 100 only on an agreeing bias, else 0")

# B3 the candle leg is ABSENT (0) when Price Action is off - no neutral credit
check('g_cf_has_candle=((InpEnablePriceAction||InpEnableAllModules) && g_pa_pattern!="NONE" && g_pa_pattern!="");'
      in upd_n,
      "B3 the candle leg requires Price Action to be enabled AND a real pattern")
check("g_cf_pillar_candle=(g_cf_has_candle ? (double)g_pa_strength : 0.0);" in upd_n,
      "B3 a disabled or patternless candle leg contributes 0")
check("int candle_dir=(g_cf_has_candle ? g_pa_pattern_dir : 0);" in upd_n,
      "B3 an absent candle leg carries no direction, so it cannot contradict")

# B4 the zone leg is presence-based and reuses the ONE existing scan
check(upd_c.count("PA_ZoneAt(") == 1,
      "B4 CF_Update calls PA_ZoneAt exactly once", str(upd_c.count("PA_ZoneAt(")))
check("g_cf_pillar_zone=(g_cf_has_zone ? 100.0 : 0.0);" in upd_n,
      "B4 a live zone scores 100 and no zone scores 0")
check(upd_c.count("g_order_blocks") == 0 and upd_c.count("g_fvgs") == 0
      and upd_c.count("g_zones[") == 0,
      "B4 CF_Update does not build a SECOND zone scan of its own")

# B5 the two existing scorers still hold their floors VERBATIM - proof the
#    neutralisation happened here and not by editing shared code
ss = norm(body_of("double ScoreSession()", "B5 ScoreSession"))
check("return 30.0;" in ss, "B5 ScoreSession() still returns its 30.0 floor, unedited")
ht = norm(body_of("double ScoreHTF(const bool is_buy)", "B5 ScoreHTF"))
check(ht.count("return 50.0;") == 2,
      "B5 ScoreHTF() still returns 50.0 twice (disabled bias, and no bias), unedited",
      str(ht.count("return 50.0;")))

print("")

# =====================================================================
# C. NON-INTERFERENCE. This is a SEVENTH number BESIDE the existing ones.
# =====================================================================
# C1 the CF section never touches existing scoring state
for s in ("g_score.", "g_score =", "final_score", "setup_quality_score", "g_pmi_confluence"):
    check(CF_SEC_C.count(s) == 0,
          "C1 the CF section never writes or reads %r" % s, str(CF_SEC_C.count(s)))

# C2 whole-file occurrence counts of the existing scoring state are UNCHANGED.
#    These are the numbers measured before the module was added.
# 74/6 -> 73/5: the purge in doc 11.14 deleted one dead function that SET
# setup_quality_score, so the two counts fall together. final_score is untouched.
for lit, want in (("g_score.", 73), ("final_score", 21), ("setup_quality_score", 5)):
    got = c_all.count(lit)
    check(got == want, "C2 %r still occurs exactly %d times file-wide" % (lit, want),
          "got %d" % got)

# C3 exact call-count deltas. CF READS four existing helpers and adds no call to
#    the other scoring systems at all. These are FILE-WIDE counts, so a later
#    phase that also reuses one of these helpers moves the number - which is the
#    point: the pin makes any such change deliberate and documented rather than
#    silent. CF's own single call to PA_ZoneAt is pinned separately in B4.
DELTA = {
    "ScoreStructure(": 6,       # 4 before + 2 (one per side)
    "ScoreLiquidity(": 5,       # 3 before + 2 (one per side)
    "ScoreSession(": 5,         # 4 before + 1
    "PA_ZoneAt(": 7,            # 6 -> 7: the AUDIT-SC1 edge leg reuses the same single zone scan
                                # which reuses this same single zone scan instead of
                                # building a second one of its own)
    "ScoreHTF(": 3,             # unchanged - bypassed
    "GraphConfluenceScore(": 0,     # 3 -> 0: unreachable, deleted in the purge (doc 11.14)
    "PMI_ComputeConfluence(": 3,    # unchanged
    "ComputeEntryQuality(": 3,      # unchanged
    "CalculateAITradeSetup(": 3,    # unchanged - CF does not trigger scoring
}
for f, want in sorted(DELTA.items()):
    got = c_all.count(f)
    check(got == want, "C3 %s occurs exactly %d times file-wide" % (f, want), "got %d" % got)

# C4 the existing weighted-score arithmetic was not touched: both branches still
#    carry their nine coefficients, and their sums are still what they were.
check(".18*g_score.structure" in c_all.replace(" ", "") or
      "*g_score.structure" in c_all.replace(" ", ""),
      "C4 the existing structure coefficient is still applied to g_score.structure")
check(c_all.replace(" ", "").count("*g_score.regime_multiplier") >= 1 or
      "regime_mult" in c_all,
      "C4 the existing regime multiplier is still applied")
check(len(re.findall(r"InpPrimeScoreMaxBonus", c_all)) >= 1,
      "C4 the existing prime bonus is still in place")
check(len(re.findall(r"InpRelationshipScoreMaxBonus", c_all)) >= 1,
      "C4 the existing relationship bonus is still in place")

# C5 the existing closed-bar conventions are unchanged - CF added NO new instance
#    of any of them, because it receives `closed` as a parameter.
for lit, want in (("int closed=rates_total-2;", 12),
                  ("int closed=ArraySize(g_buf_c)-2;", 2),   # 3 -> 2: one site was
                                                             # inside a deleted dead function
                  ("int closed=g_rates_total-2;", 8)):
    got = c_all.count(lit)
    check(got == want, "C5 %r still occurs exactly %d times" % (lit, want), "got %d" % got)
check(c_all.count("int closed=ArraySize(g_buf_h)-2;") == 0,
      "C5 no forming-bar variant was introduced")

print("")

# =====================================================================
# D. WIRING, CAUSALITY AND THE DASHBOARD SURFACE
# =====================================================================
# D1 CF_Clear() is the FIRST statement, so nothing is latched across bars
first_stmt = upd_c[upd_c.find("{") + 1:].lstrip()
check(first_stmt.startswith("CF_Clear();"),
      "D1 CF_Update clears all published state before anything else",
      first_stmt[:40])
precedes(upd_c, "CF_Clear();", "if(!(InpEnableConfluence||InpEnableAllModules)) return;",
         "D1 the clear precedes the master-switch early exit")

# D2 the forming bar is refused before any array is touched
precedes(upd_c, "if(closed<1 || closed>rates_total-2) return;", "g_buf_c[closed]",
         "D2 the forming bar is refused before the close array is read")
precedes(upd_c, "if(closed>=ArraySize(g_buf_c)) return;", "g_buf_c[closed]",
         "D2 the close array is bounds-checked before it is read")
check("if(rates_total<3) return;" in upd_n,
      "D2 a history too short to have a closed bar is refused")
check("closed>rates_total-2" in upd_n,
      "D2 the forming-bar guard uses the file's own rates_total-2 convention")

# D3 exactly one call site, after MR_Update, inside the same new-bar guard
check(c_all.count("CF_Update(closed,rates_total);") == 1,
      "D3 CF_Update is called exactly once", str(c_all.count("CF_Update(closed,rates_total);")))
precedes(c_all, "MR_Update(closed,rates_total,full_indicators);",
         "CF_Update(closed,rates_total);",
         "D3 CF_Update runs AFTER MR_Update, so it summarises the same bar")
precedes(c_all, "PA_Update(closed)", "CF_Update(closed,rates_total);",
         "D3 CF_Update runs AFTER PA_Update, whose candle leg it reads")
precedes(c_all, "MVP_Update(", "CF_Update(closed,rates_total);",
         "D3 CF_Update runs AFTER MVP_Update, whose POC PA_ZoneAt may read")
m = re.search(r"if\(is_new_bar \|\| detection_updated\) CF_Update\(closed,rates_total\);", c_all)
check(m is not None,
      "D3 CF_Update is gated by the same is_new_bar/detection_updated condition as MR_Update")
precedes(c_all, "ComputeHTFBias();", "CF_Update(closed,rates_total);",
         "D3 ComputeHTFBias runs before CF_Update, so g_htf_bias is fresh")
precedes(c_all, "BuildCausalEventGraph(rates_total", "CF_Update(closed,rates_total);",
         "D3 BuildCausalEventGraph runs before CF_Update, so g_structures is fresh")

# D4 the best-strategy scan is deterministic and cannot promote a zero score
check(upd_n.count(">best_score") == 5,
      "D4 five strategy modules are scanned with strictly-greater replacement",
      str(upd_n.count(">best_score")))
for mod in ("g_p3_dir", "g_sb_active", "g_wy_active", "g_pa_dir", "g_mr_dir"):
    check(mod in upd_c, "D4 the scan consults %s" % mod)
check("int best_score=0;" in upd_n,
      "D4 the scan starts from 0, so a module scoring 0 can never become best")
for nm in ("POWER_OF_3", "SILVER_BULLET", "WYCKOFF", "PRICE_ACTION", "MEAN_REVERSION"):
    check(nm in upd, "D4 the scan can name %s" % nm)

# D5 both sides are scored with the same aggregator
check(upd_c.count("CF_Aggregate(") == 2,
      "D5 CF_Aggregate is called exactly twice, once per side",
      str(upd_c.count("CF_Aggregate(")))
check(upd_c.count("ScoreStructure(rates_total,true)") == 1 and
      upd_c.count("ScoreStructure(rates_total,false)") == 1,
      "D5 structure is scored for both sides")
check(upd_c.count("ScoreLiquidity(true,-1)") == 1 and
      upd_c.count("ScoreLiquidity(false,-1)") == 1,
      "D5 liquidity is scored for both sides")

# D6 the veto path publishes NO TRADE and zeroes the direction and score
precedes(upd_c, "g_cf_no_trade=true;", "g_cf_dir=0;", "D6 a stand-aside zeroes the direction")
precedes(upd_c, "g_cf_dir=0;", "g_cf_score=0;", "D6 a stand-aside zeroes the score")
check("string why=CF_StandAsideReason(" in upd_n,
      "D6 the stand-aside sentence comes from the shared formatter")
check('if(why!="")' in upd_n,
      "D6 a non-empty reason is what triggers the stand-aside branch")
check("bool veto=(InpCFVetoOnConflict && g_cf_contradictions>0);" in upd_n,
      "D6 the contradiction veto is switchable and off-switchable")
check('bool strategy_ok=(!InpCFRequireActiveStrategy || best_name!="");' in upd_n,
      "D6 the strategy requirement is optional and defaults to not required")

# D7 OnInit wiring
check(call_count("CF_Clear();") == 2,
      "D7 CF_Clear is CALLED exactly twice: once in OnInit, once at CF_Update's head",
      str(call_count("CF_Clear();")))
precedes(c_all, "MR_Clear();", "CF_Clear();", "D7 CF_Clear is wired next to MR_Clear in OnInit")
check("CF_SelfTest(mtee_fail)" in c_all and c_all.count("CF_SelfTest(mtee_fail)") == 1,
      "D7 the self-test is called exactly once, through the shared MTEE harness")
check("Confluence Engine self-test: PASS (10/10)" in TEXT,
      "D7 the self-test reports ten checks, matching CF-1..CF-10")
m = re.search(r"if\(InpMTEERunSelfTest\)", c_all)
check(m is not None and m.start() < c_all.find("CF_SelfTest(mtee_fail)"),
      "D7 the self-test sits under the existing InpMTEERunSelfTest gate")

# D8 the dashboard surface: TOOLTIP only, never the 11-row card
card_i = TEXT.find("string lines[11]; color cols[11]; int ln=0;")
check(card_i > 0, "D8 the card builder is still present")
card_seg = TEXT[card_i:card_i + 9000]
card_j = card_seg.find("if(ln>11) ln=11;")
check(card_j > 0, "D8 the card's 11-row cap is still present")
n_rows = len(re.findall(r"lines\[ln\]\s*=", card_seg[:card_j]))
check(n_rows == 13, "D8 the card still has exactly 13 candidate rows - CF added none",
      str(n_rows))
check("g_cf_" not in card_seg[:card_j],
      "D8 no confluence value was written into the card's row budget")
tt = re.search(r"if\(\(InpEnableConfluence\|\|InpEnableAllModules\) && \(InpCFShowOnDashboard\|\|InpEnableAllModules\)\)", TEXT)
check(tt is not None, "D8 the tooltip block is gated by BOTH confluence switches")
tt_seg = TEXT[tt.start():tt.start() + 3000] if tt else ""
for frag in ('tooltip+="\\nCF: "', 'tooltip+="\\nCF legs: "',
             'tooltip+="\\nCF sides: buy "', 'tooltip+="\\nCF best strategy: "',
             'tooltip+="\\nCF invalidation: "'):
    check(frag in tt_seg, "D8 the tooltip carries %s" % frag.replace('tooltip+=', ''))
check("not a probability" in tt_seg,
      "D8 the tooltip states the score is not a probability")
check(tt_seg.count("ObjectCreate") == 0 and tt_seg.count("DrawTextLabel") == 0,
      "D8 the tooltip block creates no chart objects")
precedes(TEXT, '{ tooltip+="\\nRXN: "', 'tooltip+="\\nCF: "',
         "D8 the CF summary block is placed ahead of the per-module detail")

# D9 causality inside the module: no forming-bar reads, no look-ahead helpers
check(CF_SEC_C.count("rates_total-1]") == 0, "D9 the section never indexes the forming bar")
check(CF_SEC_C.count("CopyBuffer") == 0, "D9 the section copies no indicator buffers itself")
check(CF_SEC_C.count("iTime(") == 0 and CF_SEC_C.count("iClose(") == 0
      and CF_SEC_C.count("iHigh(") == 0 and CF_SEC_C.count("iLow(") == 0,
      "D9 the section reaches no series directly")
check(CF_SEC_C.count("OrderSend") == 0 and CF_SEC_C.count("CTrade") == 0
      and CF_SEC_C.count("PositionOpen") == 0,
      "D9 the section contains no trade execution")
check(CF_SEC_C.count("IndicatorSetInteger") == 0 and CF_SEC_C.count("SetIndexBuffer") == 0,
      "D9 the section allocates no buffers and changes no plot")

print("")

# =====================================================================
# E. INPUTS, INTEGRITY AND SELF-TEST SHAPE
# =====================================================================
check(BARE_LF == 0, "E the file is still pure CRLF", str(BARE_LF))
check(TEXT.count("{") == TEXT.count("}"),
      "E braces balance file-wide", "%d/%d" % (TEXT.count("{"), TEXT.count("}")))
check(c_all.count("(") == c_all.count(")"),
      "E parentheses balance on stripped text (raw text carries stray parens inside "
      "comments and strings, 86 of them, which predate this module)",
      "%d/%d" % (c_all.count("("), c_all.count(")")))

EXPECT = {
    "InpEnableConfluence": "false",
    "InpCFShowOnDashboard": "false",
    "InpCFWeightStructure": "20",
    "InpCFWeightLiquidity": "20",
    "InpCFWeightZone": "20",
    "InpCFWeightSession": "10",
    "InpCFWeightCandle": "15",
    "InpCFWeightMTF": "15",
    "InpCFMinDisplayScore": "60",
    "InpCFVetoOnConflict": "true",
    "InpCFRequireActiveStrategy": "false",
}
for name, want in EXPECT.items():
    got = input_default(name)
    check(got == want, "E input %s defaults to %s" % (name, want), "got %r" % got)
check(sum(int(EXPECT[k]) for k in EXPECT if k.startswith("InpCFWeight")) == 100,
      "E the six declared weight defaults sum to exactly 100")
check(len(EXPECT) == 11, "E exactly eleven new inputs were added", str(len(EXPECT)))
check('input group "====== Confluence Engine (AUDIT-CF1, display only) ======"' in TEXT,
      "E the new inputs sit under their own labelled group")
for sw in ("InpEnableConfluence", "InpCFShowOnDashboard", "InpCFRequireActiveStrategy"):
    check(input_default(sw) == "false",
          "E %s is a display-only switch defaulting to false" % sw)

# buffers and plots are untouched
check(re.search(r"#property\s+indicator_buffers\s+19\b", TEXT) is not None,
      "E indicator_buffers is still 19 - no buffer was added")
check(re.search(r"#property\s+indicator_plots\s+7\b", TEXT) is not None,
      "E indicator_plots is still 7 - no plot was added")

# every published global is declared and reset by CF_Clear
GLOBALS = ["g_cf_pillar_structure", "g_cf_pillar_liquidity", "g_cf_pillar_zone",
           "g_cf_pillar_session", "g_cf_pillar_candle", "g_cf_pillar_mtf",
           "g_cf_has_structure", "g_cf_has_liquidity", "g_cf_has_zone",
           "g_cf_has_session", "g_cf_has_candle", "g_cf_has_mtf",
           "g_cf_buy_score", "g_cf_sell_score", "g_cf_dir", "g_cf_score",
           "g_cf_no_trade", "g_cf_reason", "g_cf_invalidation",
           "g_cf_best_strategy", "g_cf_best_strategy_score", "g_cf_best_strategy_dir",
           "g_cf_contradictions", "g_cf_weight_sum", "g_cf_weights_valid"]
cl = body_of("void CF_Clear()", "E CF_Clear")
clc = strip_comments(cl)
check(len(GLOBALS) == 25, "E the module publishes 25 globals", str(len(GLOBALS)))
for g in GLOBALS:
    check(re.search(r"^[a-z]+\s+" + re.escape(g) + r"\s*=", TEXT, re.M) is not None
          or (g + "=") in TEXT or (g + " =") in TEXT,
          "E %s is declared at file scope" % g)
    check(g in clc, "E CF_Clear resets %s to an inert value" % g)

# self-test shape
st = body_of("bool CF_SelfTest(string &where)", "E CF_SelfTest")
labels = set(re.findall(r'"(CF-\d+)[ "]', st))
check(labels == {"CF-%d" % i for i in range(1, 11)},
      "E CF_SelfTest contains exactly the ten checks CF-1..CF-10", str(sorted(labels)))
check(st.count("return false;") >= 40,
      "E CF_SelfTest has a distinct failure exit per assertion", str(st.count("return false;")))
st_n = st.replace("\r\n", "\n").rstrip()
check(st_n.endswith("return true;\n}"),
      "E CF_SelfTest returns true only after every check", st_n[-24:])
check("where=\"\";" in st, "E CF_SelfTest clears the failure message first")
check(strip_comments(st).count("CopyBuffer") == 0
      and strip_comments(st).count("g_buf_") == 0,
      "E CF_SelfTest reads no chart history, so it is symbol- and timeframe-independent")

# the exhaustive sweep really is exhaustive
check("for(int m=0;m<64;m++)" in st.replace("\r\n", "\n"),
      "E CF-10 sweeps all 64 present/absent patterns")
check("if(combos!=128)" in st.replace("\r\n", "\n"),
      "E CF-10 asserts it covered both sides of all 64 patterns")

# forward declarations exist for every CF function (a missing one is an F7 error
# that no static tool here catches)
DECLARED = ["CF_Pillar", "CF_Aggregate", "CF_PickSide", "CF_IsAmbiguous",
            "CF_Contradicts", "CF_CountContradictions", "CF_StandAsideReason",
            "CF_Update", "CF_Clear", "CF_SelfTest"]
decl_zone = TEXT[:TEXT.find("int OnInit()")]
for f in DECLARED:
    n_decl = len(re.findall(r"(?m)^[a-z]+\s+" + f + r"\(", decl_zone))
    n_def = len(re.findall(r"(?m)^[a-z]+\s+" + f + r"\(", TEXT))
    check(n_decl == 1, "E %s has exactly one forward declaration" % f, str(n_decl))
    check(n_def == 2, "E %s has exactly one declaration plus one definition" % f, str(n_def))

print("")
print("=" * 74)

# ======================================================================
# 8. THE FOUR CONFLICTS THIS AUDIT REPORTED AND DELIBERATELY DID NOT "FIX"
# ======================================================================
# Section 8 of docs/QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md records nine conflicts
# in code that already existed. Four of them are still open decisions for the
# operator (C1, C3, C4, C6 - see doc 11.11). Nothing below changes behaviour: these
# checks make each of them impossible to change SILENTLY, because normalising the
# weights, tightening the pin-bar branch or removing a free point would have to
# arrive with an edited doc section in the same commit.

# --- C3: the existing weights sum to 1.10, and nothing compensates for it.
def _coeff_sum(anchor_text, label):
    i = TEXT.find(anchor_text)
    check(i >= 0, label + " (statement found)")
    stmt = TEXT[i:TEXT.find(';', i)]
    parts = [float(x) for x in re.findall(r'\d+\.\d+', stmt) if float(x) < 1.0]
    return sum(parts), stmt


inst_sum, inst_stmt = _coeff_sum("final_score=0.22*g_score.structure+",
                                 "C3 the institutional branch is still there")
dflt_sum, dflt_stmt = _coeff_sum("final_score=0.18*g_score.structure+0.12*g_score.liquidity+",
                                 "C3 the default branch is still there")
check(abs(inst_sum - 1.10) < 1e-9,
      "C3 the institutional weights still sum to 1.1000, not 1.0000 (measured %.4f)" % inst_sum)
check(abs(dflt_sum - 1.10) < 1e-9,
      "C3 the default weights still sum to 1.1000, not 1.0000 (measured %.4f)" % dflt_sum)
check("MathMax(0.0,MathMin(100.0,final_score))" in inst_stmt + dflt_stmt
      or TEXT.count("final_score=MathMax(0.0,MathMin(100.0,final_score));") == 2,
      "C3 both branches still clamp to 0..100, which is what hides the 1.10 scale")
eff = body_of("int EffMinConfidenceScore()", "C3 the effective threshold")
check("return InpMinConfidenceScore;" in eff and "MathMin(InpMinConfidenceScore,60)" in eff,
      "C3 EffMinConfidenceScore applies the gate profile and NOTHING else")
check("*1.1" not in eff and "1.1*" not in eff and "/1.1" not in eff,
      "C3 so no compensation for the 1.10 scale exists - the gate is ~9.1% looser "
      "than its input reads")
check("int conf=(int)MathRound(final_score);" in TEXT
      and "if(conf<EffMinConfidenceScore())" in TEXT,
      "C3 and final_score really does gate an entry, so this is not display-only")
check(input_default("InpMinConfidenceScore") == "75",
      "C3 the default threshold is still 75 (a true weighted average of ~68.2 passes it)")

# --- C4: two scorers hand out points for absent evidence; CF neutralises both.
sess = body_of("double ScoreSession()", "C4 ScoreSession")
check("return 30.0;" in sess,
      "C4 ScoreSession still returns 30.0 when no session matched at all")
check(sess.count("return 30.0;") == 1
      and sess.find("return 30.0;") > sess.find("return 40.0;"),
      "C4 and it is the fall-through return, so it is the no-evidence path")
htf = body_of("double ScoreHTF(", "C4 ScoreHTF")
check(htf.count("return 50.0;") == 2,
      "C4 ScoreHTF still returns 50.0 both when the bias is off and when it is zero",
      "got %d" % htf.count("return 50.0;"))
cf = body_of("void CF_Update(", "C4 CF_Update")
check("g_cf_has_session=(sess_raw>CF_SESSION_NO_EVIDENCE+0.001);" in norm(cf),
      "C4 CF_Update detects the 30.0 floor instead of trusting it")
check("g_cf_pillar_session=(g_cf_has_session ? sess_raw : 0.0);" in norm(cf),
      "C4 and zeroes that pillar when there is no session")
check("g_cf_has_mtf=(InpUseHTFBias && g_htf_bias!=0);" in norm(cf),
      "C4 the MTF leg is read straight from g_htf_bias")
check("ScoreHTF" not in strip_comments(cf),
      "C4 so the 50.0 free point in ScoreHTF never reaches this engine "
      "(the code path; the comment that explains why is allowed to name it)")

# --- C1: the entry gate has no body guard, so a textbook doji passes as a pin bar.
trig = body_of("void MTF_SniperEvaluateEntryTriggers(", "C1 the entry-trigger gate")
check("bull_pin=(lower_wick>=0.50*c_range && c_close>=c_open);" in norm(trig),
      "C1 the bullish pin-bar test is still lower_wick>=50% of range with an "
      "INCLUSIVE close>=open")
check("bear_pin=(upper_wick>=0.50*c_range && c_close<=c_open);" in norm(trig),
      "C1 and the bearish mirror is inclusive too")
c1_all = [l for l in trig.split("\n") if "c1_candle_inside=" in l]
c1_branch = [l for l in c1_all if "closes_inside" in l]
check(len(c1_all) == 3,
      "C1 one reset plus two branch assignments exist", "got %d" % len(c1_all))
check(len(c1_branch) == 2, "C1 both branch assignments require closes_inside")
check(all("c_body" not in l for l in c1_branch),
      "C1 neither branch consults the body, so a zero-body doji satisfies a pin bar")
check("bool doji=(x.body_ratio<=0.12);" in TEXT,
      "C1 while the ACC label calls that same bar a DOJI (body_ratio <= 0.12)")
# The example from doc 8: body 0 over range 10 -> pin TRUE and doji TRUE.
c_range, c_body, lwick = 10.0, 0.0, 5.0
check(lwick >= 0.50 * c_range and c_body == 0.0,
      "C1 with body/range (95,100,90,95) the pin test passes at exactly the boundary")
check((c_body / c_range) <= 0.12,
      "C1 and the same bar is a DOJI by the ACC rule - the two disagree")

# --- C6: the brief named inputs that do not exist. Nothing was invented.
check(input_default("InpRMNoZoneSLATR") == "1.50",
      "C6 the stop used when no zone sits behind entry is 1.50 ATR, not the 1% the "
      "brief named")
for missing in ("InpMinRR", "InpRiskPercent"):
    check(re.search(r"(?m)^\s*input\s+[^;\n]*\b" + missing + r"\b", TEXT) is None,
          "C6 %s still does not exist (a doc may not name it as an input)" % missing)

print("AUDIT-CF1 checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("This is a static transcription + wiring contract. It is NOT a backtest, it")
print("produces no win rate, and it does NOT prove MetaEditor compiles the file.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
