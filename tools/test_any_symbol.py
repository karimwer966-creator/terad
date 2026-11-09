#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QSMC_AT "any pair" contract (2026-11-07 request: "اريده يعمل علي كل الازواج").

WHAT THIS PINS
--------------
The companion had no symbol filter, but it had something worse: three limits
expressed in POINTS, and a point is not the same distance on two instruments.
The numbers shipped tuned on a 2-digit XAUUSD quote, and the measured effect on
other symbols was not "slightly off", it was a permanent refusal:

    InpMaxSpreadPoints = 30    gold(2d) OK | gold(3d) ~300 REFUSED | US30 ~300
                               REFUSED | USOIL ~40 REFUSED | BTCUSD ~2000 REFUSED
    InpMaxStopPoints   = 5000  BTCUSD typical stop ~6000 -> REFUSED on every setup
    InpTP{1,2,3}Pips = 100/200/300   1000 pts on gold, 1000 on EURUSD, but 100 pts
                               on US30 and BTCUSD - a 3-point move on an index

So the contract is: every distance limit is derived from the SYMBOL'S OWN
volatility (ATR on the chart's timeframe), an explicit point override is still
honoured, and when the reference cannot be read the EA REFUSES rather than
falling back to a gold-shaped constant.

Sections:
  A  one volatility reference, read once per closed bar, never the forming bar
  B  the stop window is per symbol (and never a zero-width window)
  C  the spread cap is per symbol, and fails CLOSED when unmeasurable
  D  the TP ladder is scale-free, and its rungs agree with PlanTP()
  E  the operator can see what the limits became on THIS symbol
  F  nothing that made the EA safe was weakened; still inert and dry by default
  G  structural integrity of the file after the change (NOT a compiler)

Evidence produced: SOURCE-LEVEL ONLY. No MetaEditor, no Strategy Tester, no demo
run - see the footer.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "MQL5" / "Experts" / "QSMC_AutoTrader.mq5"
PRESET = ROOT / "presets" / "QSMC_AutoTrader_DEMO_0.10_200.set"
GEN = ROOT / "tools" / "generate_set_presets.py"

RAW = EA.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
CODE = re.sub(r"//[^\n]*", "", RAW)

RESULTS = []


def check(cond, label, detail=""):
    RESULTS.append((bool(cond), label, detail))
    print(("PASS  " if cond else "FAIL  ") + label
          + (("  [%s]" % detail) if detail and not cond else ""))


def fn_body(name, sig=None):
    """Body of the DEFINITION of `name` (prototypes end in ';' before any '{')."""
    pat = sig or (r"^(?:void|bool|double|int|string|ulong|long|datetime)\s+"
                  + name + r"\s*\(")
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


def input_default(name):
    m = re.search(r"(?m)^input\s+\w+\s+" + name + r"\s*=\s*([^;]+);", RAW)
    return m.group(1).strip() if m else None


# ============================================ A. one volatility reference
atr = fn_body("AtrRefresh")
check(atr != "", "A1 a single ATR reader exists (AtrRefresh)")
check("iATR(" in atr, "A1 it asks the terminal for the chart symbol's ATR",
      "no ATR source")
check(re.search(r"iATR\(_Symbol,_Period", atr) is not None,
      "A1 the ATR is the symbol the EA trades, on the chart's own timeframe - "
      "no second data stream")
check("CopyBuffer(g_atr_handle,0,0,2,buf)" in atr and "buf[1]" in atr,
      "A1 it reads index 1 and only index 1: the last CLOSED bar, never the "
      "forming one")
check("g_atr_bar=bt" in atr and "bt==" + "g_atr_bar" in atr,
      "A1 the value is refreshed once per bar, so limits cannot re-scale "
      "mid-position")
check("SERIES_LASTBAR_DATE" in atr,
      "A1 bar identity comes from the series, not a tick counter")
check(re.search(r"if\(!MathIsValidNumber\(v\) \|\| v<=0\.0\) return false", atr)
      is not None,
      "A1 a NaN or non-positive ATR is a failure, not a value")

atrv = fn_body("AtrValue")
check(atrv != "", "A1 AtrValue() is the accessor every caller uses")
check("return 0.0" in atrv and "return g_atr" in atrv,
      "A1 it returns 0.0 for 'unavailable' and never a convenient 1.0")
check("1.0" not in atrv.replace("0.0", ""),
      "A1 no magic fallback constant in the accessor")

check(input_default("InpATRPeriod") == "14",
      "A1 the ATR period is an input with a stated default",
      str(input_default("InpATRPeriod")))

# The handle has to be released, or every attach leaks one indicator.
check(re.search(r"IndicatorRelease\(g_atr_handle\)", CODE) is not None,
      "A1 the ATR handle is released in OnDeinit")

# ================================================ B. the stop window
sb = fn_body("StopBoundsPoints")
check(sb != "", "B1 StopBoundsPoints() exists")
check("InpMinStopPoints" in sb and "InpMaxStopPoints" in sb,
      "B1 an explicit point override is still honoured verbatim")
check("AtrValue()" in sb and "return false" in sb,
      "B1 the automatic form derives from ATR and FAILS if it cannot")
check("InpMinStopATR*atr" in sb.replace(" ", "") or
      "InpMinStopATR*atr" in sb,
      "B1 the floor is expressed as a multiple of ATR, not points")
check("InpMaxStopATR*atr" in sb,
      "B1 and so is the ceiling")
check(re.search(r"return\s*\(min_pts>0\.0 && max_pts>min_pts\)", sb) is not None,
      "B1 a zero-width or inverted window is rejected, so a clamp can never "
      "silently accept everything")

check(input_default("InpMinStopPoints") == "0",
      "B1 the shipped default is 0 = auto, not a gold point count",
      str(input_default("InpMinStopPoints")))
check(input_default("InpMaxStopPoints") == "0",
      "B1 same for the ceiling", str(input_default("InpMaxStopPoints")))
check(input_default("InpMinStopATR") == "0.05" and input_default("InpMaxStopATR") == "6.00",
      "B1 the auto window has stated bounds (0.05 .. 6.00 ATR)")

# The enforcement site must use the resolved window, never the raw inputs.
hs = fn_body("HandleSignal")
check(hs != "", "B1 HandleSignal() is readable")
check("StopBoundsPoints(min_stop,max_stop)" in hs,
      "B1 the stop gate consults the resolver, not InpMinStopPoints directly")
check("dist_pts<(double)InpMinStopPoints" not in hs
      and "dist_pts>(double)InpMaxStopPoints" not in hs,
      "B1 the unconditional point comparison is gone  [the old form must be absent]")
check("no ATR yet" in hs,
      "B1 an unresolvable window is reported as TRANSIENT with a reason, so a "
      "fresh chart is not mistaken for a rejected setup")

# ================================================ C. the spread cap
ok = fn_body("SpreadOK")
check(ok != "", "C1 SpreadOK() exists")
check("SpreadCapPoints()" in ok,
      "C1 the gate reads the per-symbol cap")
check("if(InpMaxSpreadPoints<=0) return true;" not in ok,
      "C1 a zero cap no longer waves every trade through  [the old form must be absent]")
check("return false" in ok,
      "C1 an unmeasurable cap REFUSES: fail closed, not open")

sc = fn_body("SpreadCapPoints")
check(sc != "", "C1 SpreadCapPoints() exists")
check("InpMaxSpreadATRFrac*atr" in sc.replace(" ", ""),
      "C1 the automatic cap is a fraction of ATR - one meaning on every symbol")
check(re.search(r"if\(InpMaxSpreadPoints>0\)\s*return \(double\)InpMaxSpreadPoints", sc)
      is not None,
      "C1 an explicit point cap still wins, so an existing preset keeps its meaning")

check(input_default("InpMaxSpreadPoints") == "0",
      "C1 the shipped default is 0 = auto, not 30 gold points",
      str(input_default("InpMaxSpreadPoints")))
check(input_default("InpMaxSpreadATRFrac") == "0.25",
      "C1 the auto fraction is stated (0.25 x ATR)")

# The refusal text has to name the number that actually refused.
check('"spread above "+IntegerToString(InpMaxSpreadPoints)+" pts"' not in RAW,
      "C1 the refusal no longer prints the raw input (which is 0 when auto is "
      "on)  [the old form must be absent]")
check("DoubleToString(SpreadCapPoints(),1)" in RAW,
      "C1 the refusal prints the cap that was actually enforced")

# ================================================ D. the TP ladder
check(re.search(r"(?m)^input\s+bool\s+InpUseTPATR\s*=", RAW) is not None,
      "D1 an ATR-denominated ladder exists as an explicit switch")
check(input_default("InpUseTPATR") == "false",
      "D1 it ships OFF, so an existing installation is unchanged")
check(input_default("InpTP1ATR") == "1.00" and input_default("InpTP2ATR") == "2.00"
      and input_default("InpTP3ATR") == "3.00",
      "D1 the rungs are ATR multiples with stated defaults")

pt = fn_body("PlanTP")
check("InpUseTPATR" in pt and "InpTP3ATR*atr" in pt,
      "D1 PlanTP() sends rung 3 of the ATR ladder when the ladder is on")
check("if(atr<=0.0) return 0.0;" in pt,
      "D1 no ATR means no target returned, so the caller refuses instead of "
      "placing a target at the entry")

lad = fn_body("ManagePipLadder")
check(lad != "", "D1 the ladder manager is readable")
check("InpUseTP1ATR" not in lad and "InpTP1ATR*atr" in lad and "InpTP2ATR*atr" in lad,
      "D1 the partial-close rungs are the SAME rungs PlanTP() sends, so the "
      "ticket TP and the ladder cannot disagree")
check(lad.count("AtrValue()") >= 1 and "if(atr<=0.0) return;" in lad,
      "D1 and it refuses rather than guessing a rung without an ATR")

# Both ladders at once must be an init error, not a silent precedence.
oi = fn_body("OnInit")
check(oi != "", "D1 OnInit() is readable")
check("InpUseTPATR && InpUseTPPips" in oi.replace("\n", " ").replace("  ", " ")
      or re.search(r"InpUseTPATR\s*&&\s*InpUseTPPips", oi) is not None,
      "D1 enabling both ladders is REFUSED at init instead of silently picking one")
check(re.search(r"InpTP2ATR<=InpTP1ATR\s*\|\|\s*InpTP3ATR<=InpTP2ATR", oi) is not None,
      "D1 the ladder must be strictly increasing, as the pip one must be")
check(re.search(r"InpMaxStopATR<=InpMinStopATR", oi) is not None,
      "D1 and the auto stop window is validated at init")

# ============================================ E. the operator can see it
check("SYMBOL PROFILE" in RAW,
      "E1 attach prints a symbol profile instead of assuming an instrument")
for field in ("digits", "point", "tick value", "ATR"):
    check(field in RAW, "E1 the profile names %s" % field)
check("DERIVED LIMITS" in RAW,
      "E1 and prints the limits it derived, because an 'auto' number that is "
      "never shown is just a hidden constant")
check("ATR LADDER ON" in RAW,
      "E1 when the ladder is on, the points it resolves to are printed")
check('" | spread<= ",(spread_cap_pts>0.0 ?' in RAW,
      "E1 the summary line prints the enforced spread cap, not the raw input")
check('(bounds_ok ? DoubleToString(min_stop_pts,0)' in RAW,
      "E1 the same for the stop window")
check("ATR=" in RAW and "UNAVAILABLE" in RAW,
      "E1 the heartbeat carries the ATR, so 'limits look wrong' and 'no ATR' "
      "are distinguishable from a log")

# ==================================== F. nothing safe was weakened
check(re.search(r"input\s+bool\s+InpEnableTrading\s*=\s*false", RAW) is not None,
      "F1 still ships INERT")
check(re.search(r"input\s+bool\s+InpDryRun\s*=\s*true", RAW) is not None,
      "F1 still ships DRY RUN")
check(re.search(r"input\s+bool\s+InpDemoOnly\s*=\s*true", RAW) is not None,
      "F1 still demo-only")
check("for(int shift=count-1;shift>=1;shift--)" in CODE,
      "F1 still never reads the forming bar (shift 0)")
check(re.search(r"MathPow\(\s*2", CODE) is None and re.search(r"lots\s*\*\s*2", CODE) is None,
      "F1 still no martingale")
check("MathMax(1.0,MathRound(0.10/point))" in RAW,
      "F1 the gold pip convention is still available for gold, unchanged")
# The symbol-agnostic claim must not have introduced a symbol ALLOW/REFUSE list.
# A symbol allow/deny list would be the obvious wrong way to "support more
# pairs": it turns a broker naming difference into a silent no-trade. Match only
# a comparison of the symbol NAME against a literal, not every SymbolInfo*() call.
_symbol_filter = [
    r'_?Symbol\s*\)?\s*==\s*"',
    r'_?Symbol\s*\)?\s*!=\s*"',
    r'StringFind\s*\(\s*_Symbol\s*,\s*"',
    r"StringFind\s*\(\s*_Symbol\s*,\s*'",
]
check(not any(re.search(rx, CODE) for rx in _symbol_filter),
      "F1 no allow-list / refuse-list was introduced: any symbol the broker "
      "offers is tradeable, the limits adapt instead")
check("InpMaxRiskPercent>HardMaxRiskPercent()" in CODE,
      "F1 the risk ceiling still validates against the ONE HARD value")
check("if(loss>cap_money)" in CODE,
      "F1 the fixed-lot guard still fails closed")

# The preset must not re-introduce a gold point count.
if PRESET.is_file():
    body = PRESET.read_text(encoding="utf-8", errors="replace")
    for key in ("InpMaxSpreadPoints=0", "InpMinStopPoints=0", "InpMaxStopPoints=0"):
        check(key in body, "F2 the demo preset ships %s (derived, not gold)" % key)
    check("InpMaxSpreadPoints=60" not in body,
          "F2 the 60-point gold cap is gone from the preset  [the old form must "
          "be absent]")
else:
    check(False, "F2 the demo preset exists")
if GEN.is_file():
    gtxt = GEN.read_text(encoding="utf-8", errors="replace")
    check('"InpMaxSpreadPoints": "60"' not in gtxt,
          "F2 the generator cannot re-emit the gold point cap  [the old form "
          "must be absent]")
    check("gold spreads are wide; 60 points" not in gtxt,
          "F2 and it does not describe a cap it no longer emits")

# ================================ G. structural integrity (NOT a compiler)
def lex_clean(text):
    """Strip comments and string/char literals the way the MQL5 lexer would."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "\"'":
            q, i = c, i + 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


clean = lex_clean(RAW)
check(clean.count("{") == clean.count("}"),
      "G1 braces balance (%d/%d)" % (clean.count("{"), clean.count("}")),
      "an unbalanced file cannot compile")
check(clean.count("(") == clean.count(")"),
      "G2 parens balance (%d/%d)" % (clean.count("("), clean.count(")")),
      "the new calls are multi-line; a dropped paren is invisible without this")
depth, min_depth = 0, 0
for ch in clean:
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
        min_depth = min(min_depth, depth)
check(depth == 0 and min_depth == 0,
      "G3 the brace walk ends at 0 and never goes negative",
      "final %d, min %d" % (depth, min_depth))

raw_bytes = EA.read_bytes()
check(raw_bytes.count(b"\n") == raw_bytes.count(b"\r\n"),
      "G4 the file is pure CRLF, as .gitattributes requires",
      "a single LF-only line shows up as a whole-file diff")

for helper in ("AtrRefresh", "AtrValue", "StopBoundsPoints", "SpreadCapPoints",
               "PlanTP", "SpreadOK"):
    defs = len(re.findall(r"(?m)^(?:bool|double)\s+" + helper + r"\s*\(", CODE))
    check(defs == 1, "G5 %s is defined exactly once" % helper, "got %d" % defs)

check("g_atr_handle" in RAW and "INVALID_HANDLE" in RAW,
      "G6 the ATR handle has an INVALID_HANDLE sentinel like every other handle")

# ==================================== H. FX: the same rule, and a legible refusal
# FX is where the ATR cap is TIGHTEST rather than loosest, because an FX spread
# is a large fraction of a low-timeframe ATR:
#
#   EURUSD, 1.0-pip spread, 0.25 x ATR   M1 ATR 2.0 pips -> cap 0.50  REFUSE
#                                        M5 ATR 4.5 pips -> cap 1.12  PASS
#                                        M15 ATR 12  pips -> cap 3.00  PASS
#
# The refusal is economically right (a cost worth half the bar is not an edge)
# and it must stay: silently loosening the cap for FX would buy a trade at a
# price the account cannot afford. What must NOT stay is the silence.
reason = fn_body("SpreadCapReason")
check(reason != "", "H1 the spread refusal has a reason helper, not a bare return")
check("InpMaxSpreadPoints>0" in reason,
      "H1 it distinguishes an explicit point cap from the derived one, so the "
      "operator is never told to tune a number that is not in force")
check("InpMaxSpreadATRFrac" in reason,
      "H1 it names the multiple that produced the cap")
check("% of one ATR" in reason,
      "H1 it states the spread as a percentage of ATR - the quantity that "
      "explains WHY FX on M1 refuses and FX on M15 does not")
check("higher timeframe" in reason,
      "H1 and names the one remedy that does not change the risk rule")
check("UNRESOLVED" in reason,
      "H1 an unreadable ATR says so instead of reporting a zero cap")

hs2 = fn_body("HandleSignal")
check("SpreadCapReason()" in hs2,
      "H1 the refusal is actually reported at the gate  [a helper nobody calls "
      "is still a silent refusal]")
check(re.search(r"if\(!SpreadOK\(sym\)\)\s*\{\s*NoteClass", hs2.replace("\n", " "))
      is not None or "NoteClass(key,SpreadCapReason()" in hs2,
      "H1 and it is classified TRANSIENT: a wider spread on the next bar may "
      "pass, so the setup is retried rather than burned")

# The pip convention must remain correct for every FX quote style.
pipfn = fn_body("PipPointsFor")
check(pipfn != "", "H2 the pip convention is unchanged for gold and FX")
check("digits==3 || digits==5" in pipfn,
      "H2 FX quote styles are 3- or 5-digit")
# 4-digit FX: point == pip, which is what the digits!=3/5 branch already returns.
check("return 1.0" in pipfn,
      "H2 and a 4-digit FX quote gets 1 point per pip, which is correct there: "
      "on a 4-digit quote one point IS one pip")
check("0.10/point" in pipfn.replace(" ", ""),
      "H2 the gold convention (1 pip = 0.10 of price) is untouched")

# No FX-vs-metal branch may exist in the risk/limit path: the ATR makes the
# instrument irrelevant, and an instrument branch is how a gold-shaped constant
# comes back under a new name.
limit_fns = " ".join([fn_body("StopBoundsPoints"), fn_body("SpreadCapPoints"),
                      fn_body("PlanTP"), fn_body("AtrRefresh")])
for word in ("XAU", "GOLD", "XAG", "BTC", "is_metal", "is_crypto"):
    check(word not in limit_fns,
          "H2 no %s branch in the limit path: the limits follow ATR, not the "
          "instrument" % word)

# ======================================= H3. the FX preset surface
# A preset that says "0.25 x ATR" is portable; one that says "60 points" is not.
if PRESET.is_file():
    body = PRESET.read_text(encoding="utf-8", errors="replace")
    check("InpMaxSpreadATRFrac=" in body,
          "H3 the demo preset expresses the spread bound as an ATR fraction")
    check(re.search(r"(?m)^InpMaxSpreadPoints=(?:0)\r?$", body) is not None,
          "H3 and leaves the point cap at 0 = derived, so the same file can be "
          "loaded on an FX chart")

# ---------------------------------------------------------------- report
fails = [r for r in RESULTS if not r[0]]
print("")
print("=" * 74)
print("QSMC-AT any-pair checks: %d   failures: %d" % (len(RESULTS), len(fails)))
for ok_, label, detail in fails:
    print("  FAILED: %s  [%s]" % (label, detail))
print("")
print("Evidence produced by this suite: SOURCE-LEVEL ONLY.")
print("  * It proves every distance limit the companion enforces is derived from")
print("    the symbol it is running on, that an explicit point override still")
print("    works, and that an unmeasurable reference REFUSES rather than")
print("    substituting a gold-shaped constant.")
print("  * It does NOT compile: there is no MetaEditor in this environment.")
print("  * It does NOT prove the ATR on any particular broker feed is sensible;")
print("    that needs one attached chart per instrument.")
print("=" * 74)
raise SystemExit(1 if fails else 0)
