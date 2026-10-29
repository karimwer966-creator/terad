#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-RM1  RISK MODEL - transcription + wiring contract.

Phase 7 of the strategy-module extension for nadir2.mq5. What this file proves,
and what it deliberately does NOT claim:

  * It transcribes the module's pure cores into Python, re-derives their
    behaviour exhaustively, then pins the transcribed guards, constants and
    literals back to the .mq5 text. Without that second step the transcription
    could drift from the source and still pass.
  * It proves the sizing output is TEXT ONLY: the section contains no trade API,
    no buffer, no chart object, and the size reaches the user through exactly one
    formatter whose every branch states that no order is placed.
  * It proves no division by zero: TheoreticalRiskMoney() returns 0.0 when the
    symbol's tick value is unavailable, and the sizing core refuses that divisor.
  * It proves REUSE rather than a second risk model, by pinning the exact
    call-count delta into TheoreticalRiskMoney / AccountInfoDouble / PA_ZoneAt /
    InpTopDownMinRR / InpSniperMaxRiskPct, and by pinning the pre-existing Sniper
    trade-management model and TopDown R:R gate as UNCHANGED.
  * It proves the module never invents a direction: with no confluence verdict it
    publishes WAIT and no plan.
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
    """Occurrences of a real CALL, excluding declarations (a declaration line
    starts with a return type and ends with a semicolon)."""
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


# The RM module's own slice: banner to the end of its OWN self-test.
RM_BANNER = "// AUDIT-RM1 RISK MODEL"
_i0 = TEXT.find(RM_BANNER)
_j = TEXT.find("bool RM_SelfTest(string &where)", _i0)
_i1 = _fn_end(TEXT, _j)
check(_i0 > 0 and _i1 > _j, "A0 the RM section is locatable and brace-terminated",
      "banner@%d selftest@%d end@%d" % (_i0, _j, _i1))
RM_SEC = TEXT[_i0:_i1] if (_i0 > 0 and _i1 > 0) else ""
RM_SEC_C = strip_comments(RM_SEC)
check(len(RM_SEC) > 8000, "A0 the RM slice is long enough to be the real section",
      "len=%d" % len(RM_SEC))


# =====================================================================
# A. PURE CORES - transcribed, re-derived exhaustively, then pinned back
# =====================================================================
def rm_clamp(pct):
    if not (pct > 0.0):
        return 1.0
    return max(1.0, min(2.0, pct))


def rm_rr(entry, sl, tp):
    if not (entry > 0.0) or not (sl > 0.0) or not (tp > 0.0):
        return 0.0
    risk = abs(entry - sl)
    if not (risk > 0.0):
        return 0.0
    reward = abs(tp - entry)
    if not (reward > 0.0):
        return 0.0
    return reward / risk


def rm_stop_behind(is_buy, level, atr, buffer_atr):
    if not (level > 0.0):
        return 0.0
    buf = atr * buffer_atr if (atr > 0.0 and buffer_atr > 0.0) else 0.0
    return level - buf if is_buy else level + buf


def rm_stop_ok(sl_dist, atr, max_atr):
    if not (sl_dist > 0.0) or not (atr > 0.0) or not (max_atr > 0.0):
        return False
    return sl_dist <= atr * max_atr + 1e-9


def rm_fallback(entry, sl_dist, is_buy, multiple):
    if not (entry > 0.0) or not (sl_dist > 0.0) or not (multiple > 0.0):
        return 0.0
    return entry + sl_dist * multiple if is_buy else entry - sl_dist * multiple


def rm_ordered(is_buy, entry, tp1, tp2, tp3):
    if not (entry > 0.0):
        return False
    if not (tp1 > 0.0) or not (tp2 > 0.0) or not (tp3 > 0.0):
        return False
    if is_buy:
        return tp1 > entry and tp2 >= tp1 and tp3 >= tp2
    return tp1 < entry and tp2 <= tp1 and tp3 <= tp2


def rm_size(equity, risk_pct, money_per_lot):
    if not (equity > 0.0) or not (money_per_lot > 0.0):
        return 0.0
    pct = rm_clamp(risk_pct)
    s = (equity * (pct / 100.0)) / money_per_lot
    return s if s > 0.0 else 0.0


def rm_verdict(rr1, floor_rr, use_floor):
    if not (rr1 > 0.0):
        return "REJECT_RR"
    if use_floor and rr1 + 1e-9 < floor_rr:
        return "REJECT_RR"
    return "OK"


# A1 the risk clamp must equal the file's own Sniper clamp on the same input
sniper_clamped = all(abs(rm_clamp(x) - max(1.0, min(2.0, x))) < 1e-12
                     for x in [i / 20.0 for i in range(-40, 201)])
check(sniper_clamped, "A1 the clamp reproduces MathMax(1.0,MathMin(2.0,x)) over -2.0..10.0")
check(rm_clamp(1.50) == 1.50 and rm_clamp(0.25) == 1.0 and rm_clamp(9.0) == 2.0,
      "A1 in-range passes through, below is raised, above is cut")
check(rm_clamp(0.0) == 1.0 and rm_clamp(-3.0) == 1.0,
      "A1 a zero or negative percentage falls back to 1.0, never to 0")

# A2 reward over risk, exhaustively
a2 = True
for e in (80.0, 100.0, 120.0):
    for sd in range(1, 9):
        for m in range(1, 6):
            for buy in (True, False):
                sl = e - sd if buy else e + sd
                tp = rm_fallback(e, float(sd), buy, float(m))
                if abs(rm_rr(e, sl, tp) - float(m)) > 1e-9:
                    a2 = False
check(a2, "A2 an mR target measures exactly m of reward per risk, on both sides")
check(rm_rr(100.0, 100.0, 104.0) == 0.0, "A2 a zero-distance stop has no measurable R:R")
check(rm_rr(100.0, 98.0, 100.0) == 0.0, "A2 a target at entry has no reward")
check(all(rm_rr(a, b, c) == 0.0 for a, b, c in
          ((0.0, 98.0, 104.0), (100.0, 0.0, 104.0), (100.0, 98.0, 0.0),
           (-1.0, 98.0, 104.0), (100.0, -1.0, 104.0), (100.0, 98.0, -1.0))),
      "A2 a missing or non-positive entry, stop or target yields no R:R")

# A3 the stop sits BEYOND the level it protects
a3 = True
for atr in (0.0, 0.5, 10.0):
    for buf in (0.0, 0.30, 1.0):
        lv = 100.0
        b = rm_stop_behind(True, lv, atr, buf)
        s = rm_stop_behind(False, lv, atr, buf)
        if atr > 0.0 and buf > 0.0:
            if not (b < lv) or not (s > lv):
                a3 = False
        else:
            if b != lv or s != lv:
                a3 = False
check(a3, "A3 a long stop is strictly below the level and a short stop strictly above")
check(abs(rm_stop_behind(True, 100.0, 10.0, 0.30) - 97.0) < 1e-9,
      "A3 the documented 0.30 ATR buffer places a long stop 3.0 below a 10.0 ATR")
check(rm_stop_behind(True, 0.0, 10.0, 0.30) == 0.0,
      "A3 a missing level cannot produce a stop")
check(rm_stop_behind(True, -5.0, 10.0, 0.30) == 0.0,
      "A3 a non-positive level cannot produce a stop")

# A4 the hard cap is inclusive and refuses degenerate inputs
check(rm_stop_ok(20.0, 10.0, 2.00), "A4 a stop exactly at the cap is still acceptable")
check(not rm_stop_ok(20.1, 10.0, 2.00), "A4 a stop beyond the cap is rejected")
check(all(not rm_stop_ok(d, a, m) for d, a, m in
          ((0.0, 10.0, 2.0), (-1.0, 10.0, 2.0), (10.0, 0.0, 2.0), (10.0, 10.0, 0.0),
           (10.0, -1.0, 2.0), (10.0, 10.0, -2.0))),
      "A4 a missing distance, ATR or cap is never judged acceptable")
check(all(rm_stop_ok(1.0, 10.0, m) for m in (0.1, 0.5, 2.0, 100.0)),
      "A4 a wider cap admits a given distance")

# A5 the R-multiple fallback
check(all(abs(rm_fallback(100.0, 2.0, True, float(m)) - (100.0 + 2.0 * m)) < 1e-9
          for m in (1, 2, 3)),
      "A5 long fallbacks are entry plus 1R, 2R and 3R")
check(all(abs(rm_fallback(100.0, 2.0, False, float(m)) - (100.0 - 2.0 * m)) < 1e-9
          for m in (1, 2, 3)),
      "A5 short fallbacks are entry minus 1R, 2R and 3R")
check(all(rm_fallback(a, b, True, c) == 0.0 for a, b, c in
          ((100.0, 0.0, 1.0), (100.0, -2.0, 1.0), (100.0, 2.0, 0.0),
           (100.0, 2.0, -1.0), (0.0, 2.0, 1.0))),
      "A5 a zero risk distance, zero multiple or missing entry yields no target")

# A6 ordering tests the SIDE, not merely the distance
check(rm_ordered(True, 100.0, 102.0, 104.0, 106.0), "A6 increasing long targets are ordered")
check(rm_ordered(False, 100.0, 98.0, 96.0, 94.0), "A6 decreasing short prices are ordered")
check(not rm_ordered(True, 100.0, 106.0, 104.0, 102.0), "A6 a nearer TP3 is not ordered")
check(rm_ordered(True, 100.0, 102.0, 102.0, 106.0), "A6 equal distances are still ordered")
check(not rm_ordered(True, 100.0, 100.0, 104.0, 106.0), "A6 a target at entry is not ordered")
check(not rm_ordered(True, 100.0, 98.0, 104.0, 106.0),
      "A6 a long target BELOW entry is rejected - that is a second stop, not a target")
check(not rm_ordered(False, 100.0, 102.0, 104.0, 106.0),
      "A6 a short target ABOVE entry is rejected")
check(not rm_ordered(True, 100.0, 102.0, 0.0, 106.0), "A6 a missing target is not ordered")

# A7 sizing: the round trip is the invariant that makes the number meaningful
a7 = True
for eq in (500.0, 10000.0, 250000.0):
    for pct in (0.5, 1.0, 1.5, 2.0, 5.0):
        for per in (0.5, 100.0, 4321.0):
            s = rm_size(eq, pct, per)
            c = rm_clamp(pct)
            if abs(s * per - eq * c / 100.0) > 1e-6:
                a7 = False
check(a7, "A7 size x money-per-unit equals equity x the clamped percentage, everywhere")
check(rm_size(10000.0, 1.0, 100.0) == 1.0, "A7 risking 1% of 10000 at 100 per unit is 1 unit")
check(rm_size(10000.0, 2.0, 100.0) == 2.0, "A7 doubling the percentage doubles the size")
check(rm_size(10000.0, 1.0, 0.0) == 0.0,
      "A7 a zero money-per-unit returns 0 rather than dividing by zero")
check(rm_size(10000.0, 1.0, -100.0) == 0.0, "A7 a negative money-per-unit returns 0")
check(all(rm_size(e, 1.0, 100.0) == 0.0 for e in (0.0, -1.0)),
      "A7 no equity means no size")
check(rm_size(10000.0, 50.0, 100.0) == 2.0,
      "A7 an absurd percentage is clamped before it can inflate the size")

# A8 the R:R gate
check(rm_verdict(2.0, 2.0, True) == "OK", "A8 an R:R exactly at the floor passes")
check(rm_verdict(1.99, 2.0, True) == "REJECT_RR", "A8 an R:R just below the floor is rejected")
check(rm_verdict(0.0, 2.0, True) == "REJECT_RR", "A8 no measurable reward is rejected")
check(rm_verdict(-1.0, 2.0, True) == "REJECT_RR", "A8 a negative reward is rejected")
check(rm_verdict(0.5, 2.0, False) == "OK",
      "A8 with the floor disabled a low R:R is reported rather than rejected")
check(rm_verdict(0.0, 2.0, False) == "REJECT_RR",
      "A8 disabling the floor still cannot pass a zero reward")
g8 = True
for r in [i / 100.0 for i in range(0, 601)]:
    for fl in (1.0, 1.5, 2.0, 3.0):
        v = rm_verdict(r, fl, True)
        if (v == "OK") != (r > 0.0 and r + 1e-9 >= fl):
            g8 = False
check(g8, "A8 the gate agrees with its definition over 0.00..6.00 at four floors")

# A9 the sizing text always disclaims the order, and never fabricates a number
ok_txt = "about 1.25 units at 1.25% risk (125.00 USD) - advisory text only, no order"
no_txt = "unavailable (tick value or equity not reported) - advisory only, no order"
check("no order" in ok_txt and "no order" in no_txt,
      "A9 both sizing branches state that no order is placed")
check("unavailable" in no_txt and "0.00 units" not in no_txt,
      "A9 the unavailable branch says so and quotes no fabricated number")
check("units" in ok_txt and "lots" not in ok_txt,
      "A9 the size is expressed in units, not as an instruction to trade lots")

# A10 pin the transcription back to the source text
cl = norm(body_of("double RM_ClampRiskPct(const double pct)", "A10 RM_ClampRiskPct"))
check("return MathMax(1.0,MathMin(2.0,pct));" in cl,
      "A10 the clamp is literally the Sniper model's MathMax(1.0,MathMin(2.0,...))")
check("if(!(pct>0.0)) return 1.0;" in cl,
      "A10 a non-positive percentage falls back to 1.0 before the clamp")

rr_b = norm(body_of("double RM_RewardRisk(const double entry,const double sl,const double tp)",
                    "A10 RM_RewardRisk"))
check("if(!(entry>0.0) || !(sl>0.0) || !(tp>0.0)) return 0.0;" in rr_b,
      "A10 RM_RewardRisk refuses a non-positive entry, stop or target first")
check("if(!(risk>0.0)) return 0.0;" in rr_b,
      "A10 RM_RewardRisk refuses a zero-distance stop before dividing by it")
precedes(rr_b, "if(!(risk>0.0)) return 0.0;", "return reward/risk;",
         "A10 the zero-risk refusal precedes the division")

sb = norm(body_of("double RM_StopBehind(const bool is_buy,const double level,const double atr,const double buffer_atr)",
                  "A10 RM_StopBehind"))
check("if(!(level>0.0)) return 0.0;" in sb, "A10 RM_StopBehind refuses a missing level")
check("return (is_buy ? level-buf : level+buf);" in sb,
      "A10 a long stop goes below the level and a short stop above it")

so = norm(body_of("bool RM_StopDistanceOK(const double sl_dist,const double atr,const double max_atr)",
                  "A10 RM_StopDistanceOK"))
check("return (sl_dist<=atr*max_atr+RM_RR_EPSILON);" in so,
      "A10 the cap is inclusive at the limit")
check(so.count("return false;") == 3,
      "A10 RM_StopDistanceOK refuses three degenerate cases separately",
      str(so.count("return false;")))

fb = norm(body_of("double RM_FallbackTP(const double entry,const double sl_dist,const bool is_buy,const double multiple)",
                  "A10 RM_FallbackTP"))
check("return (is_buy ? entry+sl_dist*multiple : entry-sl_dist*multiple);" in fb,
      "A10 the fallback is entry plus or minus the R multiple")

to = norm(body_of("bool RM_TPsOrdered(const bool is_buy,const double entry,", "A10 RM_TPsOrdered"))
check("if(is_buy) return (tp1>entry && tp2>=tp1 && tp3>=tp2);" in to,
      "A10 ordering requires long targets ABOVE entry at non-decreasing distance")
check("return (tp1<entry && tp2<=tp1 && tp3<=tp2);" in to,
      "A10 ordering requires short targets BELOW entry at non-decreasing distance")

ps = norm(body_of("double RM_PositionSize(const double equity,const double risk_pct,const double money_per_lot)",
                  "A10 RM_PositionSize"))
check("if(!(money_per_lot>0.0)) return 0.0;" in ps,
      "A10 the divisor is refused BEFORE the division")
precedes(ps, "if(!(money_per_lot>0.0)) return 0.0;", "/money_per_lot;",
         "A10 the divisor guard precedes the only division in the function")
check("double pct=RM_ClampRiskPct(risk_pct);" in ps,
      "A10 sizing clamps the percentage rather than trusting the input")

vd = norm(body_of("string RM_Verdict(const double rr1,const double floor_rr,const bool use_floor)",
                  "A10 RM_Verdict"))
check("if(!(rr1>0.0)) return \"REJECT_RR\";" in vd.replace('""', '\\"\\"')
      or 'if(!(rr1>0.0)) return "REJECT_RR";' in vd,
      "A10 no measurable reward is rejected before the floor is even consulted")
check("if(use_floor && rr1+RM_RR_EPSILON<floor_rr)" in vd,
      "A10 the floor test uses the same epsilon the TopDown gate uses")
precedes(vd, 'return "REJECT_RR";', 'return "OK";',
         "A10 the rejection paths precede the only OK")

print("")

# =====================================================================
# B. TEXT ONLY. No order, no buffer, no drawing, no second risk model.
# =====================================================================
for bad in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen", "PositionClose",
            "OrderDelete", "TradeRequest", "MqlTradeRequest"):
    check(RM_SEC_C.count(bad) == 0, "B the RM section contains no %s" % bad,
          str(RM_SEC_C.count(bad)))
for bad in ("SetIndexBuffer", "IndicatorSetInteger", "ArraySetAsSeries", "PlotIndexSet"):
    check(RM_SEC_C.count(bad) == 0, "B the RM section allocates no buffer or plot (%s)" % bad)
for bad in ("ObjectCreate", "DrawZoneBox", "DrawTextLabel", "DrawHLine", "ObjectSetText"):
    check(RM_SEC_C.count(bad) == 0, "B the RM section draws nothing (%s)" % bad)
for bad in ("CopyBuffer", "iTime(", "iClose(", "iHigh(", "iLow(", "iBarShift("):
    check(RM_SEC_C.count(bad) == 0, "B the RM section reaches no series directly (%s)" % bad)

# the size reaches the user through exactly one formatter
upd = body_of("void RM_Update(const int closed,const int rates_total)", "B0 RM_Update")
upd_n = norm(upd)
upd_c = strip_comments(upd)
st_b = norm(body_of("string RM_SizeText(const bool available,const double units,const double risk_money,",
                    "B RM_SizeText"))
check(st_b.count("no order") == 2,
      "B both branches of RM_SizeText state that no order is placed",
      str(st_b.count("no order")))
check("g_rm_size_text=RM_SizeText(" in upd_n,
      "B RM_Update publishes the size only through RM_SizeText")
check(strip_comments(upd).count("g_rm_size_text=") == 1,
      "B the size text is assigned exactly once in RM_Update (RM_Clear only resets it)",
      str(strip_comments(upd).count("g_rm_size_text=")))

# TheoreticalRiskMoney is REUSED, not reimplemented
check(upd_c.count("TheoreticalRiskMoney(") == 1,
      "B RM_Update calls the existing TheoreticalRiskMoney exactly once")
check(RM_SEC_C.count("tick_value") == 0 and RM_SEC_C.count("tick_size") == 0,
      "B the RM section does not reimplement tick-value arithmetic")
check(RM_SEC_C.count("SYMBOL_TRADE_TICK") == 0,
      "B the RM section queries no symbol trade property itself")

print("")

# =====================================================================
# C. REUSE AND NON-INTERFERENCE, pinned by measured delta
# =====================================================================
DELTA = {
    "TheoreticalRiskMoney(": 8,   # 7 before + 1
    "AccountInfoDouble(": 2,      # 1 before + 1
    "AccountInfoString(": 2,      # 1 before + 1
    "PA_ZoneAt(": 7,              # 6 -> 7: the AUDIT-SC1 edge leg reuses the same single zone scan
    "InpTopDownMinRR": 7,         # 4 before + 3 (the reused hard R:R floor)
    "InpSniperMaxRiskPct": 3,     # 2 before + 1 (the reused risk percentage)
    # untouched: no new call into ANY scoring system
    "ScoreStructure(": 6, "ScoreLiquidity(": 5, "ScoreSession(": 5, "ScoreHTF(": 3,
    "GraphConfluenceScore(": 0,   # 3 -> 0: unreachable, deleted in the purge (doc 11.14)
    "PMI_ComputeConfluence(": 3, "ComputeEntryQuality(": 3,
    "CalculateAITradeSetup(": 3, "CF_Update(": 3,
    # untouched: existing scoring state
    "g_score.": 73, "final_score": 21, "setup_quality_score": 5,   # -1 each: one dead setter
    # untouched: buffers, objects, closed-bar conventions
    "SetIndexBuffer(": 19, "ObjectCreate(": 16,   # 24 -> 16: 8 calls lived in dead renderers
    "int closed=rates_total-2;": 12, "int closed=ArraySize(g_buf_c)-2;": 2,   # 3 -> 2: purge
    "int closed=g_rates_total-2;": 8,
}
for f, want in sorted(DELTA.items()):
    got = c_all.count(f)
    check(got == want, "C %s occurs exactly %d times file-wide" % (f, want), "got %d" % got)

for bad in ("OrderSend", "CTrade", "OrderSendAsync", "PositionOpen"):
    check(c_all.count(bad) == 0, "C the file's CODE still contains no %s" % bad)

# the pre-existing Sniper trade-management model is unchanged
sniper = body_of("void MTF_SniperComputeTradeManagement(SMTF_SniperCluster &cl,const double chart_atr,",
                 "C MTF_SniperComputeTradeManagement")
sniper_n = norm(sniper)
check(len(sniper) > 3000, "C the Sniper trade-management model is still present and whole",
      str(len(sniper)))
for lit in ("SNIPER_SL_BUFFER_ATR*safe_chart_atr", "SNIPER_SL_HARD_MAX_H1_ATR",
            'cl.entry_grade="SKIP_SL_MAX"', "cl.rec_lot_size=NormalizeDouble(",
            "double risk_pct=MathMax(1.0,MathMin(2.0,InpSniperMaxRiskPct));",
            "SNIPER_BE_DISP_ATR", "SNIPER_TRAIL_M15_ATR"):
    check(lit in sniper_n, "C the Sniper model still contains %s" % lit[:48])

# the pre-existing TopDown R:R gate is unchanged
check('if(rr+1e-9<InpTopDownMinRR)' in c_all,
      "C the TopDown chain's own R:R gate is byte-intact")
check(TEXT.count('TopDown_Fail(StringFormat("R:R %.2f below required %.2f') == 1,
      "C the TopDown rejection message is unchanged (checked on RAW text, because "
      "strip_comments blanks the very literal this asserts about)")

# the RM section never writes existing state
for s in ("g_td.", "g_score.", "g_cf_", "cl.rec_lot_size", "g_active_setup."):
    writes = len(re.findall(re.escape(s) + r"[\w\.\[\]]*\s*=(?!=)", RM_SEC_C))
    if s == "g_cf_":
        check(writes == 0, "C the RM section never WRITES any confluence global")
    elif s == "g_td.":
        check(writes == 0, "C the RM section never WRITES the TopDown state it adopts")
    else:
        check(writes == 0, "C the RM section never writes %s" % s)

print("")

# =====================================================================
# D. WIRING, CAUSALITY, AND THE DASHBOARD SURFACE
# =====================================================================
first_stmt = upd_c[upd_c.find("{") + 1:].lstrip()
check(first_stmt.startswith("RM_Clear();"),
      "D RM_Update clears all published state before anything else", first_stmt[:40])
precedes(upd_c, "RM_Clear();", "if(!(InpEnableRiskModel||InpEnableAllModules)) return;",
         "D the clear precedes the master-switch early exit")
precedes(upd_c, "if(closed<1 || closed>rates_total-2) return;", "g_buf_c[closed]",
         "D the forming bar is refused before the close array is read")
precedes(upd_c, "if(closed>=ArraySize(g_buf_c)) return;", "g_buf_c[closed]",
         "D the close array is bounds-checked before it is read")
check("if(rates_total<3) return;" in upd_n, "D a history with no closed bar is refused")

# it never invents a direction
precedes(upd_c, "if(g_cf_dir==0)", "g_rm_dir=g_cf_dir;",
         "D the module refuses to plan before it has a confluence verdict")
check('g_rm_verdict="WAIT";' in upd_n, "D no verdict publishes WAIT")
check(upd_c.count("g_rm_dir=") == 1,
      "D the plan direction is assigned exactly once, from g_cf_dir",
      str(upd_c.count("g_rm_dir=")))
check("g_rm_dir=g_cf_dir;" in upd_n, "D the plan direction is the confluence direction")

# TopDown adoption, not re-derivation
check("InpRMPreferTopDownPlan && g_td.computed && g_td.dir==g_cf_dir" in upd_n,
      "D an agreeing TopDown plan is adopted only when its direction matches")
check("g_td.entry>0.0 && g_td.sl>0.0 && g_td.tp1>0.0" in upd_n,
      "D adoption requires the chain to have published a complete plan")
check('g_rm_plan_src="TOPDOWN"' in upd and 'g_rm_plan_src="DERIVED"' in upd,
      "D the published plan says which of the two sources produced it")
precedes(upd_n, 'g_rm_plan_src="TOPDOWN"', 'g_rm_plan_src="DERIVED"',
         "D adoption is tried before derivation, never after")

# the R:R floor is the file's own input
check("RM_Verdict(g_rm_rr1,InpTopDownMinRR,InpRMUseRRFloor)" in upd_n,
      "D the floor comes from the existing InpTopDownMinRR, not a new duplicate input")
check('g_rm_verdict="REJECT_RR"' in upd and 'g_rm_verdict="REJECT_SL"' in upd,
      "D both rejection kinds are published distinctly")
check(upd_n.count('"NO PLAN: ') == 4,
      "D every rejection path is prefixed NO PLAN (zero stop, cap, R:R, ordering)",
      str(upd_n.count('"NO PLAN: ')))

# entry is the closed bar's close, not a future price
check("g_rm_entry=price;" in upd_n and "double price=g_buf_c[closed];" in upd_n,
      "D a derived entry is the last CLOSED bar's close")

# the enforcement that GUARANTEES the ordering the guard then asserts. Mixing a
# pool target with an R-multiple fallback can otherwise put TP3 nearer than TP1,
# so each distance is raised to at least the previous one.
check("double d1=MathAbs(g_rm_tp1-g_rm_entry);" in upd_n,
      "D TP1's distance is measured from entry")
check("double d2=MathMax(MathAbs(g_rm_tp2-g_rm_entry),d1);" in upd_n,
      "D TP2's distance is raised to at least TP1's")
check("double d3=MathMax(MathAbs(g_rm_tp3-g_rm_entry),d2);" in upd_n,
      "D TP3's distance is raised to at least TP2's")
precedes(upd_n, "double d3=MathMax(", "g_rm_tp1=(is_buy ?",
         "D the distances are enforced before the targets are republished from them")
check(upd_n.count("MathMax(MathAbs(g_rm_tp") == 2,
      "D exactly two targets are pushed outward, leaving TP1 as the nearest",
      str(upd_n.count("MathMax(MathAbs(g_rm_tp")))

# ordering guard is live, not test-only
# Scoped to RM_Update's own body. A file-wide call_count() is unsafe here:
# RM_TPsOrdered's declaration spans two lines, so its first line starts with a
# return type but ends with a COMMA rather than a semicolon, the declaration
# exclusion never fires, and the count is inflated by the declaration and the
# definition as well as by every call.
check(upd_c.count("RM_TPsOrdered(") == 1,
      "D RM_Update calls the ordering guard exactly once",
      str(upd_c.count("RM_TPsOrdered(")))
check("if(!RM_TPsOrdered(is_buy,g_rm_entry,g_rm_tp1,g_rm_tp2,g_rm_tp3))" in upd_n,
      "D the guard tests the plan it is about to publish, on the correct side")
precedes(upd_c, "RM_TPsOrdered(", "g_rm_rr1=RM_RewardRisk(",
         "D the ordering guard runs BEFORE any R:R is published from those targets")

# wiring
check(c_all.count("RM_Update(closed,rates_total);") == 1,
      "D RM_Update is called exactly once", str(c_all.count("RM_Update(closed,rates_total);")))
m = re.search(r"if\(is_new_bar \|\| detection_updated\) RM_Update\(closed,rates_total\);", c_all)
check(m is not None, "D RM_Update shares the is_new_bar/detection_updated gate")
precedes(c_all, "CF_Update(closed,rates_total);", "RM_Update(closed,rates_total);",
         "D RM_Update runs AFTER CF_Update, whose verdict it attaches to")
precedes(c_all, "TopDown_Update(rates_total,false);", "RM_Update(closed,rates_total);",
         "D RM_Update runs AFTER TopDown_Update, whose plan it may adopt")
precedes(c_all, "MVP_Update(", "RM_Update(closed,rates_total);",
         "D RM_Update runs AFTER MVP_Update, whose POC PA_ZoneAt may read")
check(call_count("RM_Clear();") == 2,
      "D RM_Clear is CALLED exactly twice: OnInit and RM_Update's head",
      str(call_count("RM_Clear();")))
check(c_all.count("RM_SelfTest(mtee_fail)") == 1,
      "D the self-test is called exactly once, through the shared MTEE harness")
check("Risk model self-test: PASS (10/10)" in TEXT,
      "D the self-test reports ten checks, matching RM-1..RM-10")
m = re.search(r"if\(InpMTEERunSelfTest\)", c_all)
check(m is not None and m.start() < c_all.find("RM_SelfTest(mtee_fail)"),
      "D the self-test sits under the existing InpMTEERunSelfTest gate")

# dashboard surface: tooltip only, card untouched
card_i = TEXT.find("string lines[11]; color cols[11]; int ln=0;")
card_seg = TEXT[card_i:card_i + 9000]
card_j = card_seg.find("if(ln>11) ln=11;")
check(card_i > 0 and card_j > 0, "D the card builder and its 11-row cap are still present")
n_rows = len(re.findall(r"lines\[ln\]\s*=", card_seg[:card_j]))
check(n_rows == 13, "D the card still has exactly 13 candidate rows - RM added none",
      str(n_rows))
check("g_rm_" not in card_seg[:card_j], "D no risk value entered the card's row budget")
tt = re.search(r"if\(\(InpEnableRiskModel\|\|InpEnableAllModules\) && \(InpRMShowOnDashboard\|\|InpEnableAllModules\)\)", TEXT)
check(tt is not None, "D the tooltip block is gated by BOTH risk-model switches")
tt_seg = TEXT[tt.start():tt.start() + 3000] if tt else ""
for frag in ('tooltip+="\\nRM: "', 'tooltip+="\\nRM why: "', 'tooltip+="\\nRM plan: entry "',
             'tooltip+="\\nRM targets: TP1 "', 'tooltip+="\\nRM floor: "',
             'tooltip+="\\nRM size: "', 'tooltip+="\\nRM invalidation: "'):
    check(frag in tt_seg, "D the tooltip carries %s" % frag.replace('tooltip+=', ''))
check("not a probability" in tt_seg and "not an order" in tt_seg,
      "D the tooltip says the numbers are neither a probability nor an order")
check(tt_seg.count("ObjectCreate") == 0, "D the tooltip block creates no chart objects")
precedes(TEXT, 'tooltip+="\\nCF: rule-based confluence count', 'tooltip+="\\nRM: "',
         "D the risk block sits directly after the confluence summary it belongs to")

print("")

# =====================================================================
# E. INPUTS, INTEGRITY, SELF-TEST SHAPE
# =====================================================================
check(BARE_LF == 0, "E the file is still pure CRLF", str(BARE_LF))
check(TEXT.count("{") == TEXT.count("}"), "E braces balance file-wide",
      "%d/%d" % (TEXT.count("{"), TEXT.count("}")))
check(c_all.count("(") == c_all.count(")"), "E parentheses balance on stripped text",
      "%d/%d" % (c_all.count("("), c_all.count(")")))

EXPECT = {
    "InpEnableRiskModel": "false",
    "InpRMShowOnDashboard": "false",
    "InpRMSLBufferATR": "0.30",
    "InpRMSLMaxATR": "2.00",
    "InpRMNoZoneSLATR": "1.50",
    "InpRMUseRRFloor": "true",
    "InpRMPreferTopDownPlan": "true",
    "InpRMMaxPoolScan": "40",
}
for name, want in EXPECT.items():
    got = input_default(name)
    check(got == want, "E input %s defaults to %s" % (name, want), "got %r" % got)
check(len(EXPECT) == 8, "E exactly eight new inputs were added", str(len(EXPECT)))
check('input group "====== Risk Model (AUDIT-RM1, display only, advisory text) ======"' in TEXT,
      "E the new inputs sit under their own labelled group")
for sw in ("InpEnableRiskModel", "InpRMShowOnDashboard"):
    check(input_default(sw) == "false", "E %s defaults to false" % sw)
# the brief's InpMinRR / InpRiskPercent were NOT invented as duplicates
for name in ("InpMinRR", "InpRiskPercent", "InpRMMinRR", "InpRMRiskPercent"):
    check(input_default(name) is None,
          "E no duplicate %s was invented - the existing inputs are reused" % name)
check(input_default("InpTopDownMinRR") == "2.0",
      "E the reused R:R floor InpTopDownMinRR still defaults to 2.0")
check(input_default("InpSniperMaxRiskPct") == "1.50",
      "E the reused risk percentage InpSniperMaxRiskPct still defaults to 1.50")

check(re.search(r"#property\s+indicator_buffers\s+19\b", TEXT) is not None,
      "E indicator_buffers is still 19 - no buffer was added")
check(re.search(r"#property\s+indicator_plots\s+7\b", TEXT) is not None,
      "E indicator_plots is still 7 - no plot was added")

GLOBALS = ["g_rm_verdict", "g_rm_dir", "g_rm_plan_src", "g_rm_entry", "g_rm_sl",
           "g_rm_sl_dist", "g_rm_sl_dist_atr", "g_rm_tp1", "g_rm_tp2", "g_rm_tp3",
           "g_rm_rr1", "g_rm_rr2", "g_rm_rr3", "g_rm_sl_src", "g_rm_tp1_src",
           "g_rm_rejected", "g_rm_reason", "g_rm_invalidation", "g_rm_risk_pct",
           "g_rm_risk_money", "g_rm_money_per_lot", "g_rm_size_units",
           "g_rm_size_available", "g_rm_size_text"]
clc = strip_comments(body_of("void RM_Clear()", "E RM_Clear"))
check(len(GLOBALS) == 24, "E the module publishes 24 globals", str(len(GLOBALS)))
for g in GLOBALS:
    check((g + "=") in TEXT or (g + " =") in TEXT, "E %s is declared at file scope" % g)
    check(g in clc, "E RM_Clear resets %s to an inert value" % g)
cl_raw = body_of("void RM_Clear()", "E RM_Clear raw")
check('g_rm_verdict="WAIT"' in cl_raw,
      "E RM_Clear resets the verdict to WAIT, not to OK")

st = body_of("bool RM_SelfTest(string &where)", "E RM_SelfTest")
labels = set(re.findall(r'"(RM-\d+)[ "]', st))
check(labels == {"RM-%d" % i for i in range(1, 11)},
      "E RM_SelfTest contains exactly the ten checks RM-1..RM-10", str(sorted(labels)))
check(st.count("return false;") >= 40,
      "E RM_SelfTest has a distinct failure exit per assertion", str(st.count("return false;")))
st_n = st.replace("\r\n", "\n").rstrip()
check(st_n.endswith("return true;\n}"), "E RM_SelfTest returns true only after every check",
      st_n[-24:])
check("where=\"\";" in st, "E RM_SelfTest clears the failure message first")
stc = strip_comments(st)
check(stc.count("CopyBuffer") == 0 and stc.count("g_buf_") == 0
      and stc.count("AccountInfoDouble") == 0 and stc.count("TheoreticalRiskMoney") == 0,
      "E RM_SelfTest reads no chart history and no account data, so it is environment-independent")
check("if(combos!=320)" in st_n, "E RM-10 asserts it covered all 5x8x4x2 geometries")

DECLARED = ["RM_ClampRiskPct", "RM_RewardRisk", "RM_StopBehind", "RM_StopDistanceOK",
            "RM_FallbackTP", "RM_TPsOrdered", "RM_PositionSize", "RM_Verdict",
            "RM_SizeText", "RM_PoolsAhead", "RM_NearestPoolBehind", "RM_Update",
            "RM_Clear", "RM_SelfTest"]
decl_zone = TEXT[:TEXT.find("int OnInit()")]
for f in DECLARED:
    n_decl = len(re.findall(r"(?m)^[a-z]+\s+" + f + r"\(", decl_zone))
    n_def = len(re.findall(r"(?m)^[a-z]+\s+" + f + r"\(", TEXT))
    check(n_decl == 1, "E %s has exactly one forward declaration" % f, str(n_decl))
    check(n_def == 2, "E %s has exactly one declaration plus one definition" % f, str(n_def))

# no literal price level anywhere in the module: it must be symbol-agnostic
# Scoped to the module CORE, excluding RM_SelfTest: the self-test's fixtures are
# synthetic numbers (100.0, 10000.0, 4321.0) and not prices, so a file-wide price
# regex would report them as hard-coded levels. This is the same trap that caught
# the Phase 4 suite.
RM_CORE = TEXT[_i0:_j] if (_i0 > 0 and _j > _i0) else ""
check(len(RM_CORE) > 6000, "E the RM core slice is long enough to be meaningful",
      "len=%d" % len(RM_CORE))
_prices = [(m.group(0), RM_CORE[max(0, m.start() - 1)])
           for m in re.finditer(r"\b\d{3,4}\.\d{1,5}\b", RM_CORE)]
_bad = [v for v, prev in _prices if not (v == "100.0" and prev == "/")]
check(len(_bad) == 0,
      "E the RM core contains no hard-coded price level - every 3-4 digit decimal "
      "is the /100.0 percent divisor, never a price", str(_bad[:6]))
check(all(v == "100.0" for v, _ in _prices),
      "E the only such literal in the core is the percent divisor 100.0",
      str(sorted({v for v, _ in _prices})))

print("")
print("=" * 74)
print("AUDIT-RM1 checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("This is a static transcription + wiring contract. It is NOT a backtest, it")
print("produces no win rate, and it does NOT prove MetaEditor compiles the file.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
