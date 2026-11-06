#!/usr/bin/env python3
"""Regression contracts for the 2026-11-06 "no CORE signal" incident.

The supplied XAUUSD journal showed, on every closed bar:

  [GateAudit] ... | top blocker: chain: structure event missing/invalidated in
  the graph (435)
  [GateLeg] XAUUSD ... sweep_bar 0 struct_bar <closed> bars_apart 50584 ...
  [CausalBranch] ROLLBACK CE_SETUP_... | OB exact displacement/structure binding
  mismatch: CE_ORDER_BLOCK_...
  signals CORE armed 0 confirmed 0  |  Total Signals Generated: 0

Three independent defects produced that picture. This suite pins the source
contracts that close them, so a later edit cannot quietly reopen the hole. It is
a source/regex contract, not an MT5 run and not a backtest.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "nadir2.mq5"
DEPLOYED = ROOT / "MQL5" / "Indicators" / "nadir2.mq5"
TEXT = HOST.read_text(encoding="utf-8", errors="replace")
FLAT = TEXT.replace("\r\n", "\n")
FAILURES = []


def check(ok, label):
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        FAILURES.append(label)


def definition(name):
    """Return the full body of a top-level function DEFINITION (not the prototype).

    Every function in this host is prototyped before it is defined, and several
    appear more than once as a prototype. The definition is the last match, the
    only one that carries a body (a closing brace at column 0).
    """
    pattern = re.compile(r"^(?:bool|void|int|double|string|ulong|long)\s+" + name +
                         r"\(.*?^\}", re.M | re.S)
    hits = pattern.findall(FLAT)
    if not hits:
        raise AssertionError("definition not found: " + name)
    return hits[-1]


# --------------------------------------------------------------- B1 (one line)
# ValidateCausalGraphInvariants compares SOrderBlock.source_structure_time with
# the structure event time. Before this fix the field was only ever zero
# initialised, so EVERY order block failed the invariant and every setup branch
# was rolled back -> zero CORE signals.
binding = FLAT[FLAT.index("         g_order_blocks[oi].source_displacement_event_id=did;"):]
binding = binding[:binding.index("}")]
check("g_order_blocks[oi].source_structure_time=t[st.bar];" in binding,
      "B1 the OB binding stage publishes source_structure_time (was zero-only)")
check(binding.index("source_structure_time=t[st.bar]") <
      binding.index('string oid="CE_ORDER_BLOCK_"'),
      "B1 it is published BEFORE the CE_ORDER_BLOCK event is created, so the "
      "invariant sees it on the same pass")
check("g_fvgs[fi].source_structure_time=t[st.bar];" in FLAT,
      "B1 control: the FVG path still publishes its equivalent field")
check("g_order_blocks[ev.source_index].source_structure_time!=g_causal_events[st].event_time"
      in FLAT,
      "B1 control: the invariant that compares the field still exists")

# ------------------------------------------------------- B2 (call-site guard)
# DetectOrderBlocks laundered "no aligned sweep" (-1) into bar 0 via MathMax, so
# the leg was measured across the whole loaded history (bars_apart 50584).
CODE = re.sub(r"//[^\n]*", "", FLAT)          # code only: prose may name the bug
check("MathMax(0,sweep_bar)" not in CODE,
      "B2 the OB scanner no longer clamps a missing sweep anchor to bar 0")
ob = definition("DetectOrderBlocks")
check("if(sweep_bar<0) continue;" in ob,
      "B2 a structure break with no aligned swept pool is skipped explicitly")
check("ValidateDisplacementLeg(sweep_bar,st.bar" in ob,
      "B2 the OB scanner passes the raw sweep_bar to the leg validator")

# ------------------------------------------- B3 (diagnostic contamination)
# The [GateLeg] snapshot must describe the CAUSAL-GRAPH evaluation only: the OB
# scanner rejects far more candidates and used to overwrite it, so the printed
# blocker was not the one the signal path acted on.
sig = definition("ValidateDisplacementLeg")
check("const bool record_diag)" in sig,
      "B3 the leg validator takes an explicit record_diag flag")
snapshot = sig[sig.index("if(record_diag)"):sig.index("// (best_k is diagnostic-only")]
check("g_gate_audit.leg_sweep_bar=sweep_bar;" in snapshot,
      "B3 the whole leg snapshot lives inside the flag")
tail = sig[sig.index("// (best_k is diagnostic-only"):]
writes = [m for m in re.finditer(r"g_gate_audit\.leg_\w+\s*=[^=]", tail)]
check(all(tail.rfind("if(record_diag)", 0, m.start()) >
          tail.rfind("\n   ", 0, m.start()) for m in writes),
      "B3 the only leg_* writes outside the snapshot block are the ones guarded "
      "by if(record_diag) themselves")
check(sig.count("LegNoteFail(") >= 6,
      "B3 every rejection still reaches the gate-audit funnel (counts preserved)")
norm = " ".join(CODE.split())
check(norm.count("ValidateDisplacementLeg(") == 4,
      "B3 two call sites plus one prototype and one definition (4 mentions)")
check("candidate_impulse,true)" in norm,
      "B3 the causal-graph call site is the one that records the snapshot")
check("impulse_bar,false)" in norm,
      "B3 the OB scanner is the one that does not")
check("leg_ok=ValidateDisplacementLeg(sweep_bar,st.bar,st.bullish,\n"
      "                                          st.price,o,h,l,c,impulse_bar,false);" in FLAT,
      "B3 the OB scanner call site does not record the snapshot")
check("(sweep_bar>=0 && sweep_bar<ArraySize(l) ? (bullish ? l[sweep_bar] : h[sweep_bar]) : 0.0)"
      in FLAT,
      "B3 sweep_extreme is not read from bar 0 when there is no sweep")
check("structure_bar>=0 ? g_atr_buf[structure_bar] : g_atr" in FLAT,
      "B3 the ATR read is range-checked before it is indexed")

# ------------------------------------------------- B4 (the preset that lied)
# InpDisplacementATR is a real gate (leg net >= atr*InpDisplacementATR) with no
# auto-heal, and the retention caps are literal. The practical preset is loaded
# by one click and used to ship InpDisplacementATR=0 with 3/4/2/2 caps and a
# causal-graph cap of ONE event - structurally incapable of a CORE signal.
preset = ROOT / "presets" / "nadir2_PRACTICAL_XAUUSD.set"
check(preset.is_file(), "B4 the practical XAUUSD preset still ships")
if preset.is_file():
    raw = preset.read_bytes()
    vals = dict(re.findall(r"^(Inp\w+)=(.*?)\r*$", raw.decode("utf-8", "replace"), re.M))
    check(vals.get("InpDisplacementATR", "").strip() not in ("", "0"),
          "B4 preset does not disable the displacement gate (InpDisplacementATR != 0)")
    check(int(vals.get("InpMaxStructuresKeep", "0")) >= 30,
          "B4 preset keeps enough structure history for an anchor")
    check(int(vals.get("InpMaxLiquidityKeep", "0")) >= 40,
          "B4 preset keeps pool+sweep pairs (sweep ancestry) instead of 4 rows")
    check(int(vals.get("InpMaxCausalEventsKeep", "0")) >= 160,
          "B4 preset keeps a full causal chain, not a single event")
    check(raw.count(b"\r\r\n") == raw.count(b"\n"),
          "B4 preset line endings are untouched (MetaEditor .set format)")
    declared = set(re.findall(r"^\s*(?:sinput|input)\s+\w+\s+(\w+)\s*=", FLAT, re.M))
    check(declared == set(vals),
          "B4 preset and host input surface are the same set (%d inputs)" % len(declared))

# ------------------------------------------- B5 (one timeframe, operator ask)
# The journal shows M1->M5->M15->H1->H4 cycling at 14:32-14:35; every change re-ran
# OnInit, restored DAY_BLOCKED and shut the indicator down. The companion now
# refuses a chart that is not on its pinned timeframe, and never switches it.
EA = (ROOT / "MQL5" / "Experts" / "QSMC_AutoTrader.mq5").read_text(
    encoding="utf-8", errors="replace")
EA_CODE = re.sub(r"//[^\n]*", "", EA.replace("\r\n", "\n"))
check("input int    InpPinTimeframeMinutes  = 0;" in EA,
      "B5 the pin is an input and is OFF by default (no silent behaviour change)")
check("return (PeriodSeconds(_Period)==(long)InpPinTimeframeMinutes*60);" in EA_CODE,
      "B5 the pin compares the chart bar length in seconds with the requested one")
check("ChartSetSymbolPeriod" not in EA_CODE and "ChartSetSymbolPeriod" not in CODE,
      "B5 neither the EA nor the indicator ever changes the chart timeframe")
_init = EA_CODE[EA_CODE.index("int OnInit()"):]
_init = _init[:_init.index("void OnDeinit")]
check(_init.index("TimeframePinRefusal()") < _init.index("iCustom("),
      "B5 the pin is enforced BEFORE any indicator handle is requested")
check("return INIT_PARAMETERS_INCORRECT;" in
      _init[_init.index("TimeframePinRefusal()"):][:300],
      "B5 a wrong chart timeframe stops OnInit instead of trading it")
for hook in ("void OnTick()", "void OnTimer()"):
    body = EA_CODE[EA_CODE.index(hook):]
    body = body[:body.index("DayGuardUpdate();")]
    check("if(!PinnedTimeframeMatches()) return;" in body,
          "B5 %s stays inert if the chart is moved while running" % hook)

# --------------------------------------- B6 (the day guard is not a mystery)
# day_base=5680.64 vs equity ~4999 with a 0.50% cap means a floor of 5652.24,
# i.e. above current equity: the guard trips on the first tick of every attach
# and restores DAY_BLOCKED on every re-attach. The baseline is PERSISTED, so a
# reload cannot fix it. Two supported remedies must therefore exist and agree.
check('return ("QSMC_AT_DAY_"+IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))+'
      '\n           "_"+IntegerToString(InpMagic)+"_"+_Symbol+"_"+leaf);' in
      EA.replace("\r\n", "\n"),
      "B6 control: the day key is (login, magic, symbol, leaf)")
check('return ("QSMC_AT_SESS_"+IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))+'
      '\n           "_"+IntegerToString(InpMagic)+"_"+_Symbol+"_"+leaf);' in
      EA.replace("\r\n", "\n"),
      "B6 control: the session key is (login, magic, symbol, leaf)")
reset = ROOT / "MQL5" / "Scripts" / "QSMC_ResetGuards.mq5"
check(reset.is_file(), "B6 an operator reset tool ships (no input flip on a live chart)")
if reset.is_file():
    rt = reset.read_text(encoding="utf-8", errors="replace")
    check('#define DAY_PREFIX  "QSMC_AT_DAY"' in rt and
          '#define SESS_PREFIX "QSMC_AT_SESS"' in rt,
          "B6 the tool builds on the same two key prefixes the EA writes")
    # the tool matches the whole three-field family, so it does not need to
    # enumerate leaves - but the header must state which ones exist.
    leaves = ("DAY", "EQ", "BLOCKED", "TRADES", "DDB", "LSB", "CL")
    check(all(lf in rt for lf in leaves),
          "B6 it documents every leaf the EA persists (%s)" % ", ".join(leaves))
    check("Leave InpResetBreakersAtInit=false" in rt,
          "B6 it tells the operator to leave the input off afterwards")
    check("input bool   InpApply        = false;" in rt,
          "B6 it is a DRY RUN by default (the first run only lists keys)")
    check("GlobalVariableDel(hits[i])" in rt and "GlobalVariablesFlush();" in rt,
          "B6 it deletes only the collected keys and flushes once")
    check(rt.count("OrderSend") == 0 and "CTrade" not in rt,
          "B6 the tool cannot trade (no OrderSend, no CTrade)")
    check("InpResetBreakersAtInit" in rt,
          "B6 it names the alternative, so the operator can choose")


# ------------------------------- B7 (any account: 0.10 lots + 200 money stop)
# "اريد ان يعمل علي اي حساب و حد الخسارة اليومية 200 و لوت صفقة 0.1"
# Three things had to be true, and none of them was: the hard clamps made a 2%
# day stop impossible on ANY account, the fixed-lot guard measured the wrong
# percentage, and the day guard could only express a percentage.
check("double HardMaxRiskPercent(){ return 5.00; }" in EA_CODE and
      "double HardMaxDailyPercent(){ return 10.00; }" in EA_CODE,
      "B7 the HARD ceilings are account-agnostic (5% risk / 10% day), not 0.25/1.00")
check("input double InpMaxDailyLossMoney    = 0.00;" in EA,
      "B7 the day stop can be expressed in MONEY (0 = off, so nothing changes by default)")
check("double money=DayStopMoney();" in EA_CODE and
      "if(money>0.0) return base-money;" in EA_CODE,
      "B7 when a money stop is set it WINS over the percentage stop")
check("return (hard>0.0 ? MathMin(InpMaxDailyLossMoney,hard) : InpMaxDailyLossMoney);"
      in EA_CODE,
      "B7 a fat-fingered money stop is still capped by HARD% of the day baseline")
check("if(InpMaxDailyLossMoney<0.0 || InpFixedLotsMaxRiskPercent<0.0)" in EA_CODE,
      "B7 a negative money stop is refused at init")
check("if(eq<=floor_eq && !g_day_blocked)" in EA_CODE and
      "DayFloorEquity(g_day_start_equity)" in EA_CODE,
      "B7 the trip test uses the single floor helper (percent or money)")
check("DAILY_LOSS_MONEY=" in EA and "AccountInfoString(ACCOUNT_CURRENCY)" in EA_CODE,
      "B7 the trip line reports the loss in the account currency")

# The attach banner is the contract an operator reads: it must state the ARMED
# plan, not only the ceilings, and in FIXED mode it must not print a % risk.
check("[QSMC_AT] ARMED PLAN" in EA, "B7 attach prints an ARMED PLAN block")
check('"mode ",(InpLotMode==QSMC_LOT_FIXED ? "FIXED "' in EA_CODE or
      'InpLotMode==QSMC_LOT_FIXED\n                    ? "FIXED "' in EA.replace("\r\n","\n"),
      "B7 the main banner names the FIXED volume instead of a % risk")
check("double guard_pct=InpFixedLotsMaxRiskPercent;" in EA_CODE and
      "if(guard_pct>0.0 && loss>eq*guard_pct/100.0)" in EA_CODE,
      "B7 the fixed-lot guard measures the STOP, not the irrelevant risk input")
check("if(InpLotMode==QSMC_LOT_FIXED && InpFixedLots<=0.0)" in EA_CODE,
      "B7 FIXED mode with no volume is refused at init instead of refusing every signal")

# The shipped demo preset carries his exact numbers, and still cannot arm a
# real account.
demo = ROOT / "presets" / "QSMC_AutoTrader_DEMO_PRODUCTION_0.10_200.set"
check(demo.is_file(), "B7 the demo production preset ships")
if demo.is_file():
    raw = demo.read_bytes()
    v = dict(re.findall(r"^(Inp\w+)=(.*?)\r*$", raw.decode("utf-8", "replace"), re.M))
    check(v.get("InpLotMode") == "QSMC_LOT_FIXED" and v.get("InpFixedLots") == "0.10",
          "B7 preset: 0.10 lots fixed")
    check(v.get("InpMaxDailyLossMoney") in ("200", "200.0", "200.00"),
          "B7 preset: daily stop 200 in account currency")
    check(v.get("InpEnableTrading") == "true" and v.get("InpDryRun") == "false",
          "B7 preset: armed (otherwise it is not ready for a demo)")
    check(v.get("InpDemoOnly") == "true" and v.get("InpRealAccountConfirm", "x") == "",
          "B7 preset: a REAL account is still refused (demo production, not live)")
    check(v.get("InpResetBreakersAtInit") == "true",
          "B7 preset: clears a stale day baseline on load")
    check(int(v.get("InpMaxTradesPerDay", "0")) == 3 and
          int(v.get("InpMaxOpenPositions", "0")) == 1,
          "B7 preset: the trial envelope is kept (3/day, 1 open)")
    check(raw.count(b"\r\r\n") in (0, raw.count(b"\n")) and
          raw.count(b"\n") == raw.count(b"\r\n"),
          "B7 preset line endings are valid for the MT5 .set reader")
    declared = set(re.findall(r"^\s*(?:sinput|input)\s+\w+\s+(\w+)\s*=",
                              EA.replace("\r\n", "\n"), re.M))
    check(set(v) <= declared, "B7 every preset key exists in the EA")


# ------------------------------------------------------------- house rules
check(TEXT == DEPLOYED.read_text(encoding="utf-8", errors="replace"),
      "deployment copy is synchronized")
check(DEPLOYED.read_bytes().count(b"\n") == DEPLOYED.read_bytes().count(b"\r\n"),
      "canonical host remains pure CRLF")

print("=" * 74)
print("causal-chain regression checks: failures=%d" % len(FAILURES))
print("This is a source contract, not an MT5 runtime run and not a backtest.")
sys.exit(1 if FAILURES else 0)
