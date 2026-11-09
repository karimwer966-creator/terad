#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QSMC_AT v6.6.20 execution-companion audit.

Sections:
  A  one source of truth for the hard ceilings (displayed == enforced)
  B  FIXED-lot mode must fail closed and enforce the same ceiling as RISK%
  C  the day guard has three states and reports the one it is in
  D  every rejection is TRANSIENT / PERMANENT / EXPIRED
  E  the indicator ABI the companion reads is the one the host binds
  F  no martingale, no widening, still inert by default
  G  STRUCTURAL integrity of the patched file (see the note below)

Section G exists because there is no MetaEditor in this environment. It is a
brace/quote/paren balance walk over the whole file plus a prototype-vs-definition
check, so an unbalanced edit cannot masquerade as a passing patch. It is NOT a
compiler and the footer says so.

Scope of the evidence this produces: SOURCE-LEVEL ONLY.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "MQL5" / "Experts" / "QSMC_AutoTrader.mq5"
HOST = ROOT / "nadir2.mq5"

RAW = EA.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
CODE = re.sub(r"//[^\n]*", "", RAW)
HOST_RAW = HOST.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")

RESULTS = []


def check(cond, label, detail=""):
    RESULTS.append((bool(cond), label, detail))
    print(("PASS  " if cond else "FAIL  ") + label
          + (("  [%s]" % detail) if detail and not cond else ""))


def fn_body(name, sig=None):
    """Body of the DEFINITION of `name`, never its prototype.

    A prototype ends in ';' before any '{'. Landing on the declaration and
    reading an empty body is how a suite silently asserts nothing, so the
    signature must be followed by a brace."""
    pat = sig or (r"^(?:void|bool|double|int|string|ulong|long|datetime)\s+" + name + r"\s*\(")
    m = None
    for cand in re.finditer(pat, CODE, re.M):
        tail = CODE[cand.end():cand.end() + 400]
        semi, brace = tail.find(";"), tail.find("{")
        if brace >= 0 and (semi < 0 or brace < semi):
            m = cand
            break
    if m is None:
        return ""
    depth, started = 0, False
    for i in range(m.start(), len(CODE)):
        c = CODE[i]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return CODE[m.start():i + 1]
    return ""


# ===================================================== A. one source of truth
init_body = fn_body("OnInit")
calc = fn_body("CalcLots")

# A1: OnInit used to reject InpMaxRiskPercent > 1.0 while the documented HARD
# ceiling was 5.00 and the attach line printed 5.00.
check("InpMaxRiskPercent>HardMaxRiskPercent()" in init_body,
      "A1 OnInit validates InpMaxRiskPercent against the HARD ceiling")
check("InpMaxRiskPercent>1.0" not in init_body,
      "A1 the contradictory literal 1.0 check is gone from OnInit")

# A2: CalcLots applied a SECOND, undocumented 1.0% clamp.
check("if(vmax_cap>1.0) vmax_cap=1.0;" not in calc,
      "A2 CalcLots no longer applies a second, undocumented 1.0% ceiling")
check("if(vmax_cap>HardMaxRiskPercent()) vmax_cap=HardMaxRiskPercent();" in calc,
      "A2 the enforced per-trade ceiling is HardMaxRiskPercent() and nothing else")

# A3: one resolver per limit.
for fname in ("EffectiveRiskPercent", "EffectiveDailyPercent", "EffectiveDDPct", "DayStopState"):
    check(re.search(r"^(?:double|string)\s+" + fname + r"\s*\(", CODE, re.M) is not None,
          "A3 %s() exists: the limit is resolved in exactly one place" % fname)
check(CODE.count("MathMin(InpMaxDailyLossPercent,HardMaxDailyPercent())") == 1,
      "A3 the daily cap is not re-derived at each print site",
      "%d copies" % CODE.count("MathMin(InpMaxDailyLossPercent,HardMaxDailyPercent())"))
check("double eff_risk=EffectiveRiskPercent();" in CODE
      and "double eff_daily=EffectiveDailyPercent();" in CODE
      and "double eff_dd=EffectiveDDPct();" in CODE,
      "A3 the attach banner prints the resolver's answer, not its own arithmetic")
check("double _effDaily=EffectiveDailyPercent();" in CODE,
      "A3 the heartbeat prints the resolver's answer too")

# A4: the trip line must name the stop that fired.
dgu = fn_body("DayGuardUpdate")
check("DAY_STOP_STATE=" in dgu,
      "A4 the trip line states WHICH stop fired (MONEY / PERCENT / DISABLED)")
check("daily_cap=HardMaxDailyPercent()" not in dgu,
      "A4 the daily guard no longer invents a 10% cap when the percent input is 0")

# ============================================ B. fixed lot: fail closed, capped
est = fn_body("EstimateLossAtSL")
# B1: the old code returned a TRADABLE volume exactly when the metadata needed
# to price its risk was missing.
check("if(step<=0.0 || tick_size<=0.0 || tick_value<=0.0) return fixed_v;" not in CODE,
      "B1 a fixed lot is never returned when tick metadata is missing")
check(re.search(r"if\(step<=0\.0 \|\| tick_size<=0\.0 \|\| tick_value<=0\.0\)\s*\n?\s*\{", CODE) is not None,
      "B1 missing tick metadata is a refusal block that logs and returns 0.0")

# B2: measured with OrderCalcProfit(), fail closed.
check("if(!OrderCalcProfit(" in est,
      "B2 the expected loss at the actual SL is measured with OrderCalcProfit()")
check("if(!mathisvalidnumber" in est.lower() or "MathIsValidNumber(pnl)" in est,
      "B2 a non-numeric P&L is rejected")
check("loss_out=-pnl;" in est,
      "B2 the loss is taken from the computed P&L with its sign")
check("if(!measured)" in calc,
      "B2 CalcLots refuses when the loss could not be measured")
check("FIXED_LOT_REPORT" in calc and "REFUSED: OrderCalcProfit()" in calc,
      "B2 an unmeasurable risk is reported as a refusal, never as zero risk")

# B3: the HARD ceiling applies to FIXED as well.
fixed_branch = calc[calc.index("if(InpLotMode==QSMC_LOT_FIXED)"):]
fixed_branch = fixed_branch[:fixed_branch.index("double pct=(RealProfileActive()")]
check("EffFixedLotRiskPct()" in fixed_branch and "HardMaxRiskPercent()" in fn_body("EffFixedLotRiskPct"),
      "B3 the HARD per-trade ceiling is enforced in FIXED mode as well (via the one resolver)")
# 2026-11-09 (F2): the clamp moved into EffFixedLotRiskPct(), which the guard AND
# the banner call. Pinning the old inline clamp would pin the duplication.
check("double guard_pct=EffFixedLotRiskPct();" in fixed_branch and
      "double cap_pct=EffFixedLotRiskPct();" in RAW,
      "B3 a fixed-lot guard of 0 no longer means 'no ceiling at all'")

# B4: the five required fields.
for field in ("REQUESTED=", "NORMALIZED=", "EST_SL_LOSS=", "EFFECTIVE_RISK_PCT="):
    check(field in calc, "B4 the fixed-lot decision logs %s" % field)
check("AccountInfoString(ACCOUNT_CURRENCY)" in fixed_branch,
      "B4 the account currency is in the log line")
check("| ACCEPTED" in fixed_branch and "| REFUSED" in fixed_branch,
      "B4 accept and refuse print the same fields, so they are comparable")

# ============================================================ C. day guard
check(re.search(r"^string\s+DayStopState\s*\(", CODE, re.M) is not None,
      "C2 one function names the guard state: MONEY / PERCENT / DISABLED")
dstate = fn_body("DayStopState")
for word in ('"MONEY"', '"PERCENT"', '"DISABLED"'):
    check(word in dstate, "C2 DayStopState() can return %s" % word)

# C1: 0 means OFF, not the loosest allowed value.
check("if(daily_cap<=0.0 || daily_cap>HardMaxDailyPercent()) daily_cap=HardMaxDailyPercent();" not in dgu,
      "C1 a disabled percent stop is not replaced by the 10% HARD ceiling")
check("double daily_cap=EffectiveDailyPercent();" in dgu,
      "C1 the guard asks the resolver")
check(re.search(r"double pct=EffectiveDailyPercent\(\);\s*\n\s*if\(pct<=0\.0\) return 0\.0;",
                fn_body("DayFloorEquity")) is not None,
      "C1 a disabled guard produces no floor, so nothing can trip it")

hb = fn_body("DiagnosticHeartbeat")
check("DAY_STOP_STATE=" in hb, "C2 the heartbeat prints the guard state")
check("DAY_BLOCKED" in hb and '" ARMED"' in hb,
      "C2 the heartbeat distinguishes blocked from armed")
check("expired " in hb, "C2 the heartbeat reports EXPIRED signals separately")

# C3: the baseline key must not depend on the timeframe.
dgk = fn_body("DayGuardKey")
check("_Period" not in dgk and "PERIOD_" not in dgk,
      "C3 the daily baseline key is timeframe-independent")
check("ACCOUNT_LOGIN" in dgk and "InpMagic" in dgk and "_Symbol" in dgk,
      "C3 the baseline is scoped per (login, magic, symbol)")

# C4: persistence of the tripped state.
check('GlobalVariableSet(DayGuardKey("BLOCKED"),1.0)' in CODE,
      "C4 a tripped daily breaker is persisted")
check("g_day_blocked=(GlobalVariableCheck(kblk)" in CODE,
      "C4 the persisted breaker is restored on reload")
check("InpResetBreakersAtInit" in CODE,
      "C4 clearing it needs an explicit, logged operator input")

# ==================================================== D. rejection lifecycle
check(re.search(r"enum\s+ENUM_AT_REJECT", CODE) is not None,
      "D1 rejections carry a class enum")
for cls in ("REJECT_PERMANENT", "REJECT_TRANSIENT", "REJECT_EXPIRED"):
    check(cls in CODE, "D1 the class %s exists and is used" % cls)
check(re.search(r"^string\s+RejectClassText\s*\(", CODE, re.M) is not None,
      "D1 one function renders the class as text, so the log word is stable")
check(re.search(r"^void\s+NoteClass\s*\(", CODE, re.M) is not None,
      "D1 every refusal goes through a classifying note")

hs = fn_body("HandleSignal")
ps = fn_body("ProcessSignals")
# D2: two contradictory `if(g_day_blocked)` blocks, the second dead code.
check(hs.count("if(g_day_blocked)") == 1,
      "D2 the daily breaker is tested once, not twice with two meanings",
      "%d copies" % hs.count("if(g_day_blocked)"))
check("NoteClass(key," in hs,
      "D2 refusal sites in HandleSignal are classified")
# D3: expired handling and a bounded retry.
check("REJECT_EXPIRED" in ps and "g_expired++" in ps,
      "D3 an aged-out signal is classified EXPIRED and counted")
check("InpOrderRetryMax" in hs, "D3 transient retries are bounded by InpOrderRetryMax")
# D4: counters.
for name in ("g_signals", "g_sent", "g_dry", "g_refused", "g_expired"):
    check(re.search(r"^int\s+%s=0;" % name, RAW, re.M) is not None,
          "D4 counter %s is declared once" % name)
check("g_refused++" in hs, "D4 a refusal is counted, not only printed")

# ======================================================= E. indicator ABI
check(re.search(r"^string\s+IndicatorIdentityLine\s*\(", CODE, re.M) is not None,
      "E1 one function reports the indicator build/ABI actually being read")
ident = fn_body("IndicatorIdentityLine")
for field in ("INDICATOR_ABI=", "INDICATOR_TIMEFRAME=", "INDICATOR_BUILD=", "INDICATOR_SYMBOL="):
    check(field in ident, "E1 the identity line carries %s" % field)
check("BarsCalculated(" in ident,
      "E1 the line proves the instance is calculating")
check(ident.count("CopyBuffer(g_handle,slots[i]") == 1 and "present==6" in ident,
      "E2 all six CORE slots are probed and a partial map is named INCOMPLETE")

bound = dict(re.findall(r"SetIndexBuffer\((\d+),\s*(BufSig\w+)", HOST_RAW))
for slot, name in ((7, "BufSigCoreDir"), (8, "BufSigCoreEntry"), (9, "BufSigCoreSL"),
                   (10, "BufSigCoreTP1"), (11, "BufSigCoreTP2"), (12, "BufSigCoreTP3")):
    check(bound.get(str(slot)) == name,
          "E2 indicator slot %d is %s" % (slot, name))
ea_bufs = {n: int(v) for n, v in re.findall(r"#define\s+QSMC_BUF_CORE_(\w+)\s+(\d+)", RAW)}
check(ea_bufs.get("DIR") == 7 and ea_bufs.get("ENTRY") == 8 and ea_bufs.get("SL") == 9
      and ea_bufs.get("TP1") == 10 and ea_bufs.get("TP2") == 11 and ea_bufs.get("TP3") == 12,
      "E2 the companion's slot map is 7..12", str(ea_bufs))

# E3: no input list, and the timeframe is stated.
check("iCustom(_Symbol,_Period,InpIndicatorName)" in CODE,
      "E3 the companion still passes no overridden inputs")
check("a chart .set cannot reach this instance" in ident,
      "E3 the identity line states that a chart .set cannot reach this instance")

# =================================================== F. prohibitions (unchanged)
# 2026-11-09 (unified DEMO & REAL): the shipping default is ARMED ON DEMO and
# REAL is a first-class EXECUTION_REAL mode that ships DISARMED. The prohibition
# these checks encode - "a fresh attach cannot lose real money" - is enforced by
# the blockers below: REAL stays disarmed (arming switch OFF, empty login/server
# confirmations), authorization is re-verified before every order, and an
# unauthorized REAL attach is refused in OnInit before the first tick.
check(re.search(r"input\s+bool\s+InpEnableTrading\s*=\s*true", RAW) is not None,
      "F1 ships ARMED for demo")
check(re.search(r"input\s+bool\s+InpDryRun\s*=\s*false", RAW) is not None,
      "F1 sends orders instead of printing them")
check("if(!RealAuthorized(why))" in CODE and "INIT REFUSED: REAL account detected" in RAW,
      "F1b an unauthorized REAL account is refused in OnInit before the first tick")
check(re.search(r"input\s+bool\s+InpAllowRealTrading\s*=\s*false", RAW) is not None,
      "F1 REAL is disarmed by default (the single arming switch ships OFF)")
check(re.search(r'input\s+string\s+InpRealAccountConfirm\s*=\s*""', RAW) is not None and
      re.search(r'input\s+string\s+InpRealServerConfirm\s*=\s*""', RAW) is not None,
      "F1 REAL ships without login/server confirmations")
check("for(int shift=count-1;shift>=1;shift--)" in CODE,
      "F2 never reads the forming bar (shift 0)")
check(re.search(r"MathPow\(\s*2", CODE) is None and re.search(r"lots\s*\*\s*2", CODE) is None,
      "F3 no martingale")
check("PositionModify(ticket,new_sl,tp)" in CODE and "buy && sl>=entry" in CODE,
      "F3 a stop already at or beyond break-even is left alone")

# ------------------------------- F4. no comment may state a ceiling the code does not
# The Phase 5 theme, applied to prose. Every one of these numbers was, at some
# point in this file's history, a real clamp described in a comment long after
# the clamp was removed or raised. The operator's only way to predict a position
# size is to believe the comments; a stale one is a defect of the same severity
# as a stale clamp, because it produces the same wrong plan.
_risk   = re.search(r"double\s+HardMaxRiskPercent\(\)\s*\{\s*return\s+([0-9.]+)", CODE)
_daily  = re.search(r"double\s+HardMaxDailyPercent\(\)\s*\{\s*return\s+([0-9.]+)", CODE)
_dd     = re.search(r"double\s+HardMaxDDPercent\(\)\s*\{\s*return\s+([0-9.]+)", CODE)
check(_risk and _daily and _dd, "F4 the three HARD ceilings are readable literals")
_HARD = {"risk": _risk.group(1) if _risk else "", "daily": _daily.group(1) if _daily else "",
         "dd": _dd.group(1) if _dd else ""}
check(_HARD["risk"] == "0.50" and _HARD["daily"] == "2.00" and _HARD["dd"] == "8.00",
      "F4 the HARD ceilings are 0.50 / 2.00 / 8.00 (tightened 2026-11-09)")

# The exact stale sentences that contradicted them. Each is asserted ABSENT.
for stale, why in [
    ("the v6.6.16 HARD ceiling in code (0.25%) always wins",
     "the input comment no longer claims a 0.25% code ceiling"),
    ("at HardMaxRiskPercent() = 0.25% at sizing time",
     "the init policy block no longer restates a 0.25% sizing cap"),
    ("daily loss HARD\r\n   //      at 1.00%; DD HARD at 3.00%",
     "the init policy block no longer restates a 1%/3% daily and DD cap"),
    ("a 0.25% hotfix) that no longer exist",
     "CalcLots does not describe a removed 0.25% hotfix as if it were live"),
]:
    check(stale not in RAW, "F4 " + why + "  [the old text must be absent]")
check("0.25%" not in CODE, "F4 no executable value is 0.25%")
# Positive form: the policy block must point AT the functions, not restate them.
check("HardMaxDailyPercent(); account DD at HardMaxDDPercent()" in RAW or
      "HardMaxDailyPercent()" in RAW,
      "F4 the init policy block names the ceiling functions instead of copying "
      "their values, so it cannot drift again")

# ==================================== G. structural integrity (NOT a compiler)
# Strip string literals and character literals the way the MQL5 lexer would,
# then walk braces. An edit that unbalances the file would fail to compile in
# MetaEditor; this at least refuses to call such an edit "done".
def lex_clean(text):
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
        elif c == '"' or c == "'":
            q = c
            i += 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


CLEAN = lex_clean(RAW)
for open_c, close_c, label in (("{", "}", "braces"), ("(", ")", "parentheses")):
    opens, closes = CLEAN.count(open_c), CLEAN.count(close_c)
    check(opens == closes, "G1 %s balance (%d/%d)" % (label, opens, closes))
    depth, low = 0, 0
    for ch in CLEAN:
        if ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            low = min(low, depth)
    check(low >= 0, "G1 %s never go negative (no premature close)" % label)
check(CLEAN.count('"') == 0 and CLEAN.count("'") == 0,
      "G1 the lexer pass terminates: no unterminated string or char literal")

# Every helper this patch introduced must have exactly one definition and must be
# visible from its call site (MQL5 allows forward declarations; we require the
# definition to precede no call at all, i.e. the file compiles as written).
for fname in ("EffectiveRiskPercent", "EffectiveDailyPercent", "EffectiveDDPct",
              "DayStopState", "EstimateLossAtSL", "RejectClassText", "NoteClass",
              "IndicatorIdentityLine"):
    defs = len(re.findall(r"^(?:double|string|bool|void)\s+" + fname + r"\s*\([^;]*\)\s*\n?\s*\{",
                          CODE, re.M))
    check(defs == 1, "G2 %s() has exactly one definition" % fname, "%d found" % defs)

check("noteClass(" not in CODE.replace("NoteClass(", ""),
      "G2 no mis-cased call to NoteClass (MQL5 is case-sensitive)")
check("LongToString" not in CODE,
      "G2 no invented LongToString()")

print("")
print("=" * 74)
fails = [r for r in RESULTS if not r[0]]
print("QSMC-AT audit checks: %d   failures: %d" % (len(RESULTS), len(fails)))
if fails:
    print("")
    for _, label, detail in fails:
        print("  FAILED: %s%s" % (label, ("  [%s]" % detail) if detail else ""))
print("")
print("Evidence produced by this suite: SOURCE-LEVEL ONLY.")
print("  * It proves the MQL5 text states and enforces what the audit required,")
print("    and that the file is structurally balanced (G).")
print("  * It does NOT compile: there is no MetaEditor in this environment.")
print("  * It does NOT run in a Strategy Tester and says nothing about a demo run.")
print("=" * 74)
sys.exit(1 if fails else 0)
