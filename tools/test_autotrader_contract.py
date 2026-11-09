#!/usr/bin/env python3
"""Contract checks for the QSMC execution companion (MQL5/Experts/QSMC_AutoTrader.mq5).

The companion is the only file in this repository allowed to reach the trade API,
so these checks are deliberately about the things that lose money:
  * it consumes ONLY the CORE published-signal buffers, not previews or ZRE,
  * its buffer indices really are the indicator's CORE export slots,
  * it ships ARMED ON DEMO (EXECUTION_DEMO) with REAL disarmed, detection-derived mode,
  * its sizing rounds DOWN and refuses rather than rounding risk up,
  * it refuses a signal with no stop or with a stop on the wrong side,
  * nothing in the layer can trade with it, and it cannot martingale.

There is no MetaTrader here: this is a source + reference-arithmetic contract, not
an MT5 run, and no number below is a profitability claim.
"""
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "MQL5/Experts/QSMC_AutoTrader.mq5"
HOST = ROOT / "nadir2.mq5"
INC = ROOT / "MQL5/Include/QSMC"


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS  {message}")


require(EA.is_file(), "the execution companion exists as its own program")
ea = EA.read_text(encoding="utf-8")
host = HOST.read_text(encoding="utf-8", errors="replace")
code = re.sub(r"//[^\n]*", "", ea)
code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)

# --------------------------------------------------------------- the boundary
# The indicator and the 18 headers must stay unable to trade. That is the whole
# reason execution was put in a separate file, so it is checked here as well as
# in the release gate (defence in depth: one of the two could be edited).
TRADE_RX = r"\b(OrderSend|OrderCheck|OrderCalcMargin|PositionOpen|PositionModify|PositionClose|CTrade)\b"
for path in [HOST, *sorted(INC.glob("*.mqh"))]:
    src = path.read_text(encoding="utf-8", errors="replace")
    src = re.sub(r"//[^\n]*", "", src)
    require(not re.search(TRADE_RX, src),
            f"no trade API in {path.relative_to(ROOT)} (observation layer stays observation-only)")

require(re.search(TRADE_RX, code) is not None,
        "the companion does reach the trade API (otherwise it cannot execute anything)")
require("#include <Trade/Trade.mqh>" in ea,
        "the companion uses the standard terminal trade library, not a hand-rolled OrderSend")

# ------------------------------------------------------- buffer contract (CORE)
buf_bind = dict(re.findall(r"SetIndexBuffer\((\d+),\s*(BufSig\w+)", host))
ea_bufs = {name: int(num) for name, num in
           re.findall(r"#define\s+QSMC_BUF_CORE_(\w+)\s+(\d+)", ea)}
expected = {"DIR": 7, "ENTRY": 8, "SL": 9, "TP1": 10, "TP2": 11, "TP3": 12, "VCODE": 19}
require(ea_bufs == expected,
        "the companion's CORE buffer map is 7..12 plus VCODE=19 (v6.6.14)")
for i, field in [(7, "Dir"), (8, "Entry"), (9, "SL"), (10, "TP1"), (11, "TP2"), (12, "TP3"),
                 (19, "Verdict"), (20, "ZREVerdict")]:
    require(buf_bind.get(str(i)) == f"BufSigCore{field}" or
            (i == 20 and buf_bind.get(str(i)) == "BufSigZREVerdict"),
            f"indicator buffer {i} is still the documented slot (the companion reads this slot)")

require(re.search(r"input\s+bool\s+InpExportSignalBuffers\s*=\s*true", host),
        "the indicator still exports the CORE signal buffers by default")
# Companion may read the ZRE_VERDICT telemetry buffer (it is a diagnostic/telemetry
# channel, not a painted mark), but it must still NOT place orders from BufSigZRE
# or preview mark buffers.
require(all(t not in ea for t in ("BufSigZREDir", "BufSigZREEntry", "BufSigZRESL",
                                   "BufPrevBuy", "BufEntryBuy")),
        "the companion does not place orders from preview/ZRE entry buffers - only published CORE facts")

# The companion creates its own indicator instance. It passes no inputs, so the
# gates it trades are the indicator's DEFAULTS; that is why the docs must pin the
# defaults and why the test asserts it: no input is smuggled past the gate chain.
require(re.search(r"iCustom\(_Symbol,_Period,InpIndicatorName\)", ea) is not None,
        "the companion reads the published indicator with no overridden inputs "
        "(entry gates cannot be reached, let alone relaxed, from here)")

# Preview bars are never traded: the newest slot read is shift 1, never 0.
require("for(int shift=count-1;shift>=1;shift--)" in code,
        "the companion never reads the forming bar (shift 0)")

# ---------------------------------------------------------------- safety switches
def inp_bool(name):
    m = re.search(r"^input\s+bool\s+" + name + r"\s*=\s*(true|false)", ea, re.M)
    return m.group(1) if m else None


# 2026-11-09 (demo-first delivery): the compiled defaults are now the production
# preset, armed, for a DEMO account. These three lines replaced "ships INERT /
# DRY RUN" - the invariant they protect is the same one (a fresh attach cannot
# lose real money), and it now lives in the real-account refusal below.
require(inp_bool("InpEnableTrading") == "true",
        "ships ARMED for demo: InpEnableTrading=true (no .set, no Inputs editing)")
require(inp_bool("InpDryRun") == "false",
        "orders are actually sent: InpDryRun=false")
# 2026-11-09 (unified DEMO & REAL): the account class is DETECTED from
# AccountInfoInteger(ACCOUNT_TRADE_MODE), never typed in. DEMO trades with the
# DEMO profile. REAL trades only behind the mandatory authorization: the
# InpAllowRealTrading switch (default OFF) AND the exact login AND the exact
# server, re-verified at init AND before every order. CONTEST and UNKNOWN are
# rejected; identity drift blocks new entries until a re-attach.
require(inp_bool("InpAllowRealTrading") == "false",
        "REAL is disarmed by default: InpAllowRealTrading=false (REAL never arms itself)")
require(re.search(r'input\s+string\s+InpRealAccountConfirm\s*=\s*""', ea) is not None,
        "the REAL login confirmation ships empty (exact login of THIS account required)")
require(re.search(r'input\s+string\s+InpRealServerConfirm\s*=\s*""', ea) is not None,
        "the REAL server confirmation ships empty (exact broker server required)")
for name, want in (("InpRealMaxRiskPercent", "0.25"), ("InpRealMaxDailyLossPercent", "1.00"),
                   ("InpRealMaxAccountDrawdownPct", "5.00"), ("InpRealMaxAggregateRiskPercent", "0.50"),
                   ("InpRealMaxOpenPositions", "1"), ("InpRealMaxTradesPerDay", "2")):
    require(re.search(r"input\s+\w+\s+" + name + r"\s*=\s*" + want + r"\s*;", ea) is not None,
            "the REAL profile is separately configured and conservative: %s=%s" % (name, want))
require(inp_bool("InpDemoOnly") is None,
        "the old binary demo-only toggle is gone: detection + authorization replaced it")

# The guard that makes the armed default safe: an account that is not a
# verified DEMO must fail BEFORE the first tick, whatever the inputs say.
# Phase 2-B (2026-11-09): DEMO is the only tradeable class; REAL and CONTEST
# are refused, and an unverifiable account is refused too (fail closed).
require("AccountModeKnown(acct_mode)" in code,
        "one resolver verifies the account mode (login + server corroborated, enum checked)")
require("INIT REFUSED: REAL account detected" in ea,
        "OnInit refuses a REAL account that does not complete authorization (INIT_FAILED, no orders)")
require("INIT REFUSED: this is a CONTEST account" in ea,
        "OnInit refuses a CONTEST account (not a demo, not a sandbox)")
require("the account mode cannot be verified" in ea,
        "an unverifiable account mode refuses to initialise (fail closed)")
require("IdentityMatchesSnapshot()" in code,
        "the account identity is snapshotted at init and re-verified before every order")
require("RealAuthorized(why)" in code or "RealAuthorized(why2)" in code or
        "RealAuthorized(" in code,
        "one authorization resolver answers REAL questions everywhere (init AND pre-submit)")

require(re.search(r"input\s+double\s+InpMaxRiskPercent\s*=\s*0\.10\s*;", ea) is not None,
        "hard risk ceiling: InpMaxRiskPercent defaults to 0.10% of equity per trade")
require(re.search(r"double\s+HardMaxRiskPercent\(\)\{\s*return\s*0\.5", ea) is not None and
        re.search(r"double\s+HardMaxDailyPercent\(\)\{\s*return\s*2\.0", ea) is not None and
        re.search(r"double\s+HardMaxDDPercent\(\)\{\s*return\s*8\.0", ea) is not None,
        "F8 the HARD ceilings are 0.50% / 2.00% / 8.00%")
# 2026-11-06 audit (A1/A2): this used to pin a SECOND, undocumented 1.0% clamp
# inside CalcLots while HardMaxRiskPercent() was 5.00 and OnInit rejected
# anything above 1.0 - three different ceilings for one limit, and the operator
# could only discover it from a generic log line. The property worth pinning is
# not "a 1.0 literal exists" but "the operator cannot raise the ceiling past the
# HARD value, and exactly one place decides it".
require("if(vmax_cap>HardMaxRiskPercent()) vmax_cap=HardMaxRiskPercent();" in code,
        "the sizing ceiling is the HARD ceiling, not a second hard-coded literal")
require("if(vmax_cap>1.0) vmax_cap=1.0;" not in code,
        "the undocumented 1.0% clamp is gone: allowed and clamped cannot disagree")
require("InpMaxRiskPercent>HardMaxRiskPercent()" in code,
        "OnInit validates the operator's ceiling against the same HARD value the "
        "sizing path enforces")
require("double pct=(RealProfileActive() ? vmax_cap : MathMin(InpRiskPercent,vmax_cap));" in code,
        "the requested risk is clamped to the ceiling before sizing (per profile)")
require("eq_sizing*pct/100.0" in code and
        "double eq_sizing=AccountInfoDouble(ACCOUNT_EQUITY);" in code,
        "risk is a fraction of current equity, not of balance or a fixed lot guess")
# F3 (2026-11-09): the size AND the printed risk now come from OrderCalcProfit().
# The tick arithmetic (dist/tick_size)*tick_value assumed a per-price tick value
# and a contract multiplier of 1.0; where that is false the journal printed one
# risk and the account took another.
require("if(!EstimateLossAtSL(sym,buy,1.0,entry,sl,loss_per_lot))" in code,
        "F3 RISK% sizing measures one lot with OrderCalcProfit() and fails closed")
require("(dist/tick_size)*tick_value" not in code,
        "F3 the tick-arithmetic size is gone from CalcLots")
require("if(!EstimateLossAtSL(sym,buy,lots,price,s.sl,risk_money))" in code,
        "F3 the risk printed in HandleSignal is measured at the volume being sent")
require("if(measured<=risk_money*1.0000001) break;" in code,
        "F3 the volume is stepped DOWN until the measured loss fits the target")

# MQL5's integer-to-string converter is IntegerToString(long); there is no
# LongToString(). One invented name produced 27 compile errors in this file.
require("LongToString" not in code,
        "no invented LongToString() - MQL5 spells the converter IntegerToString()")
require("ACCOUNT_TRADE_MODE_CONTEST" in code and "ACCOUNT_TRADE_MODE_REAL" in code,
        "both non-DEMO classes are tested explicitly, not covered by one != DEMO comparison")
require("TradeEnvBlock(buy)" in code and
        code.count("AccountModeKnown(") >= 2,
        "the pre-submit gate runs the same resolver (a re-attach cannot inherit a stale decision)")
require("REAL authorization re-verified before every order" in ea or
        "re-verified before every order" in ea or
        "every authorization condition, re-verified NOW" in code,
        "REAL authorization is re-verified at the order, not only at attach")
require("if(!(bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))" in code and
        "if(!(bool)MQLInfoInteger(MQL_TRADE_ALLOWED))" in code,
        "the companion names a switched-off Algo Trading button as the blocker "
        "instead of silently doing nothing")
require("if(!(bool)AccountInfoInteger(ACCOUNT_TRADE_EXPERT))" in code,
        "server-side expert-trading permission is checked too")
require("SYMBOL_TRADE_MODE_CLOSEONLY" in code and "SYMBOL_TRADE_MODE_DISABLED" in code,
        "a disabled / close-only symbol is reported, not traded")
require('state BLOCKED: ' in ea and 'state ARMED: ' in ea,
        "the attach banner states INERT / DRY RUN / BLOCKED / ARMED in one line")

# ------------------------------------------------------- stop / geometry refusals
must = {
    "no stop, no trade": 'signal has no stop',
    "no target, no trade": 'signal has no target',
    "buy geometry (sl<entry<tp)": 'BUY geometry is not',
    "sell geometry (tp<entry<sl)": 'SELL geometry is not',
    "stop below the minimum distance": 'under the minimum',
    "stop above the maximum distance": 'over the maximum',
    "stop already breached by price": 'price already at/below the BUY stop',
    "sell stop already breached": 'price already at/above the SELL stop',
    "target already reached (no chase)": 'not chasing',
    "broker stops level": 'broker stops level rejects',
    "spread filter": 'spread above',
    # 2026-11-06 audit (D5): the refusal says it is a LATCH and names the way out.
    # 2026-11-09 (F6): that way out was WRONG for the day guard - a restart never
    # cleared it and no restart is needed, because it clears at the server-day
    # roll. The needle now asserts the sentence that is true.
    "daily loss guard": 'DAILY-LOSS breaker tripped for this server day - it clears by itself at the next server day roll',
    "open-position cap": 'position(s) open',
    "signal age": 'aged out',
}
for why, needle in must.items():
    require(needle in ea, f"the companion can refuse a signal because of {why}")

# ------------------------------------------------------- local call arity (D17)
# MQL5 concatenates arguments only for Print/Alert/Comment/StringFormat. A call to
# an ordinary function with one argument too many is a hard compile error, and an
# EA that cannot compile is an EA nobody notices is missing from the chart. This
# is the same class of bug as the v6.6.1 dialect failures, checked here for the
# companion's own helpers.
def local_calls_ok(src):
    defs = {}
    for m in re.finditer(
            r'^(?:void|string|bool|double|int|long|ulong|datetime|color)\s+(\w+)\s*\(([^)]*)\)\s*$',
            src, re.M):
        params = [p for p in m.group(2).split(",") if p.strip()]
        defs[m.group(1)] = len(params)
    bad = []
    for name, arity in defs.items():
        if name in ("Print", "Alert", "Comment", "StringFormat", "OnInit", "OnDeinit",
                    "OnTick", "OnTimer"):
            continue
        for m in re.finditer(r'\b' + re.escape(name) + r'\s*\(', src):
            depth, args, started = 1, 1, False
            i = m.end()
            while i < len(src) and depth > 0:
                c = src[i]
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                elif c == ',' and depth == 1:
                    args += 1
                elif not c.isspace():
                    started = True
                i += 1
            given = args if started else 0
            if given != arity:
                bad.append((name, arity, given, src[:m.start()].count("\n") + 1))
    return bad


arity_problems = local_calls_ok(code)
require(not arity_problems,
        "every call to a local helper passes the number of arguments it declares "
        + ("" if not arity_problems else " - offenders: %s" % arity_problems[:3]))

require("if(bt<g_start_bar) continue;" in code,
        "signals that existed before the EA was attached are never traded")
# 2026-11-06 audit (D3): the age check is a block now, so an aged-out signal is
# classified EXPIRED and counted rather than vanishing. The property is
# unchanged: a late signal is never traded.
require("if(shift>max_age)" in code and "REJECT_EXPIRED" in code,
        "a signal older than InpMaxSignalAgeBars is classified EXPIRED and never "
        "traded late")
require("PositionGetInteger(POSITION_MAGIC)!=InpMagic" in code,
        "only positions carrying this EA's magic number are counted or managed")
require("GlobalVariableCheck(GlobName(bar_time,dir))" in code,
        "a terminal-session global prevents re-firing the same signal after a reload")

# ------------------------------------------------------------- heartbeat diagnostics
# A silent chart cannot distinguish "the indicator published nothing" from "the
# EA refused every signal". The heartbeat is a throttled, read-only diagnostic
# that copies buffer 7 over a deep window and names which root cause applies.
hb = re.search(r"input\s+int\s+InpHeartbeatSeconds\s*=\s*(\d+)\s*;", ea)
require(hb is not None and int(hb.group(1)) > 0,
        "a throttled diagnostic heartbeat exists and is on by default (InpHeartbeatSeconds)")
require(re.search(r"input\s+int\s+InpHeartbeatLookback\s*=\s*(\d+)\s*;", ea) is not None,
        "the heartbeat scans a configurable lookback window (InpHeartbeatLookback)")
require("void DiagnosticHeartbeat()" in code, "the heartbeat is one named function")
hb_body = code[code.index("void DiagnosticHeartbeat()"):code.index("void ManageOpenPositions()")]
require("CopyBuffer(g_handle,QSMC_BUF_CORE_DIR" in hb_body,
        "the heartbeat reads the CORE direction buffer (7) itself, not an internal indicator state")
require(not re.search(r"g_trade\.|OrderSend|PositionOpen|PositionModify|PositionClose", hb_body),
        "the heartbeat is strictly read-only: no order, modify or close call can hide in it")
require('if(InpHeartbeatSeconds<=0) return;' in hb_body,
        "InpHeartbeatSeconds=0 switches the heartbeat off (quiet on demand)")
require("published NO CORE setup" in ea,
        "when the window has zero signals the heartbeat says so explicitly instead of staying silent")
require(code.count("DiagnosticHeartbeat();") >= 2,
        "the heartbeat runs from both OnTick and OnTimer (a quiet symbol must still report)")

# --------------------------------------------------------- sizing reference model
# Mirrors NormalizeLots() + CalcLots(): the arithmetic is small enough to restate,
# and restating it is the only way to show that rounding never increases risk.
def normalize_lots(raw, step, vmin, vmax, digits):
    if step <= 0:
        step = 0.01
    v = math.floor(raw / step + 1e-9) * step
    if v < vmin:
        return 0.0
    if vmax > 0 and v > vmax:
        v = vmax
    return round(v, max(0, digits))


def risk_lots(equity, pct, entry, sl, tick_size, tick_value, step, vmin, vmax, digits):
    if pct <= 0:
        return 0.0
    money = equity * pct / 100.0
    dist = abs(entry - sl)
    if dist <= 0 or tick_size <= 0 or tick_value <= 0 or money <= 0:
        return 0.0
    loss_per_lot = (dist / tick_size) * tick_value
    if loss_per_lot <= 0:
        return 0.0
    return normalize_lots(money / loss_per_lot, step, vmin, vmax, digits)


# XAUUSD-like contract: tick 0.01, $1 per tick per lot, 0.01 lot step.
# $25 of risk, a $1 stop = 100 ticks = $100 per lot -> 0.25 lots exactly.
lots = risk_lots(10000.0, 0.25, 2400.00, 2399.00, 0.01, 1.0, 0.01, 0.01, 100.0, 2)
require(abs(lots - 0.25) < 1e-9,
        "reference: $25 of risk over a $1 stop at $1/tick/lot is 0.25 lots")
real_risk = abs(2400.00 - 2399.00) / 0.01 * 1.0 * lots
require(real_risk <= 10000.0 * 0.0025 + 1e-6,
        "reference: the rounded volume does not exceed the requested 0.25%")

# A stop twice as wide yields half the volume: sizing follows the setup, the
# stop is never widened to fit a preferred lot size.
lots_wide = risk_lots(10000.0, 0.25, 2400.00, 2398.00, 0.01, 1.0, 0.01, 0.01, 100.0, 2)
require(lots_wide == 0.12,
        "reference: a $2 stop yields 0.12 lots, not a widened stop to keep 0.25")
require(abs(2400.00 - 2398.00) / 0.01 * 1.0 * lots_wide <= 10000.0 * 0.0025 + 1e-6,
        "reference: the wider stop still lands under the risk budget, rounded down")

# Rounding must go down, never up: raw 0.2499 -> 0.24, so risk stays below the ask.
require(normalize_lots(0.2499, 0.01, 0.01, 100.0, 2) == 0.24,
        "reference: a volume is floored to the broker step, never rounded up")

# Below the broker minimum the answer is "no trade", not "the minimum lot".
require(normalize_lots(0.004, 0.01, 0.01, 100.0, 2) == 0.0,
        "reference: under the broker minimum the companion trades nothing "
        "(silently using the minimum lot is how risk doubles)")

# A fixed lot that breaks the ceiling is refused, not accepted.
def fixed_refused(equity, cap, entry, sl, tick_size, tick_value, lots_):
    loss = (abs(entry - sl) / tick_size) * tick_value * lots_
    return loss > equity * cap / 100.0


require(fixed_refused(10000.0, 1.0, 2400.0, 2380.0, 0.01, 1.0, 1.0) is True,
        "reference: a fixed 1.0 lot with a $20 stop risks 10% of a $10k account -> refused")
require(fixed_refused(10000.0, 1.0, 2400.0, 2398.0, 0.01, 1.0, 0.4) is False,
        "reference: a fixed 0.4 lot with a $2 stop risks 0.8% -> allowed")

# 2026-11-06: the guard now measures the STOP that is about to be sent against
# its own cap (InpFixedLotsMaxRiskPercent) instead of the per-trade risk input,
# which is meaningless in FIXED mode. It must still refuse, and must say why.
# 2026-11-06 audit (B1-B4): the comparison is against a money cap derived from
# min(operator cap, HARD ceiling) for BOTH lot modes, and the loss itself is
# measured with OrderCalcProfit() instead of a tick-value identity.
require("if(loss>cap_money)" in code,
        "the fixed-lot path really refuses a size above the ceiling")
require('Note("FIXED_LOT_TOO_BIG"' in ea,
        "and it names the refusal, so a silent no-trade is not mistaken for a bug")
require("double guard_pct=EffFixedLotRiskPct();" in code,
        "F2 the fixed-lot cap is resolved by ONE function, not recomputed per site")
require("double EffFixedLotRiskPct()" in code and
        "double cap_pct=EffFixedLotRiskPct();" in code and
        "MathMin(InpMaxRiskPercent,1.0)" not in code,
        "F2 the banner prints the ceiling the guard enforces (no third number; "
        "0 or an over-limit value falls back to the ONE HARD ceiling)")
require("!OrderCalcProfit(" in code and "if(!measured)" in code,
        "an unmeasurable loss fails closed instead of being sent")
require("if(step<=0.0 || tick_size<=0.0 || tick_value<=0.0) return fixed_v;" not in code,
        "missing tick metadata never returns a tradable fixed lot (defect B1)")

# ------------------------------------------------------------- no martingale
require(not re.search(r"MathPow\(\s*2", code), "no lot doubling (martingale) in the companion")
require(not re.search(r"lots\s*\*\s*2", code), "no lot doubling written as lots*2")
require("lots=NormalizeLots(sym,lots*0.5)" in code,
        "the only volume adjustment on failure is HALVING, for margin, never doubling")
require("never averages down" in ea and "widens a stop" in ea,
        "the header states the no-averaging / no-widening policy it is checked against")

# Break-even is the only position modify, and it only moves toward the entry.
require("InpBreakEvenAtR" in ea and "g_trade.PositionModify(ticket,new_sl,tp)" in ea,
        "the only position modification is the break-even move")
require("double new_sl=NormalizeDouble(entry,_Digits);" in code,
        "break-even stops are placed exactly at the entry, never beyond it")
require("if(buy && sl>=entry) continue;" in code and "if(!buy && sl<=entry) continue;" in code,
        "a stop that is already at or past break-even is left alone (never widened)")

# ------------------------------------------------- the shipped 0.05 preset
# A preset is an input surface the operator loads with one click, so it is
# checked like code: it must not arm anything, and the numbers must be the
# request it claims to answer (0.05 lots, 100/200/300, 40% + 40%).
PRESET = ROOT / "presets/QSMC_fixed005_tp100_200_300.set"
require(PRESET.is_file(), "the fixed-0.05 / 100-200-300 preset ships with the repository")
pset = PRESET.read_text(encoding="utf-8", errors="replace")
vals = dict(re.findall(r"^(Inp\w+)=(.*)$", pset, re.M))
require(vals.get("InpEnableTrading") == "false" and vals.get("InpDryRun") == "true",
        "the preset does NOT arm the account (INERT then DRY RUN, by hand)")
require(vals.get("InpLotMode") == "1" and vals.get("InpFixedLots") == "0.05",
        "the preset is fixed volume 0.05, not a risk-derived size")
require(vals.get("InpUseTPPips") == "true" and
        (vals.get("InpTP1Pips"), vals.get("InpTP2Pips"), vals.get("InpTP3Pips")) == ("100", "200", "300"),
        "the preset asks for the 100/200/300 pip ladder")
require(vals.get("InpTP1ClosePercent") == "40.0" and vals.get("InpTP2ClosePercent") == "40.0",
        "the preset banks 40% + 40% and leaves 20% for rung 3")
require(vals.get("InpMaxRiskPercent", "1.0") in ("1.0", "1", "1.00"),
        "the preset keeps the 1% ceiling")
require(vals.get("InpPartialCloseAtR") == "0.0",
        "the preset disables the R-based partial, so ONE exit manager owns the position")
require("pip ladder ON" in pset or "pip ladder" in pset,
        "the preset explains the pip convention it relies on")

# ---------------------------------------------------------------------------
# 2026-11-09 delivery: the eight fixes that shipped with the demo-first defaults
# ---------------------------------------------------------------------------
# F1 the consecutive-loss streak is counted from the last REVIEWED reset. Without
# this, InpResetBreakersAtInit cleared the flag and the next tick recomputed the
# same streak from the same deals.
require("string ResetStampKey()" in code and 'QSMC_AT_RST_' in ea,
        "F1 the reset writes a timestamp under its own GV namespace")
require("GlobalVariableSet(ResetStampKey(),(double)(long)TimeCurrent());" in code,
        "F1 a reviewed reset stamps the review time")
require("datetime rst=ResetStamp();" in code and
        "if(rst>0 && (datetime)HistoryDealGetInteger(t,DEAL_TIME)<=rst) break;" in code,
        "F1 the streak walk stops at the reset, so the reset survives the next tick")

# F4 the account-DD breaker measures from the equity HIGH-WATER MARK, persisted,
# not from the equity captured at the first attach.
require("double    g_equity_hwm=0.0;" in code, "F4 the EA tracks an equity high-water mark")
require("double dd_ref=(g_equity_hwm>0.0 ? g_equity_hwm : g_session_start_equity);" in code,
        "F4 the DD breaker measures from the HWM (with the legacy baseline as fallback)")
require('SessionGuardKey("_HWM")' in ea and "GlobalVariableSet(SessionGuardKey(\"_HWM\"),g_equity_hwm);" in ea,
        "F4 the HWM is persisted, so a reload cannot lower the drawdown reference")
require("g_equity_hwm=MathMax(hwm_stored,MathMax(g_session_start_equity,AccountInfoDouble(ACCOUNT_EQUITY)));" in code,
        "F4 restore takes the highest of stored HWM, session baseline and equity")
require('GlobalVariableDel(SessionGuardKey("_HWM"))' in ea,
        "F4 a reviewed reset clears the stale HWM instead of resurrecting it")

# F5 the guard-key namespaces are KeySafe()-sanitised. GlobalVariableSet() rejects
# names outside [A-Za-z0-9_] SILENTLY, so "XAUUSD.m" never persisted a baseline.
require('"_"+KeySafe(_Symbol)+"_"+leaf' in ea,
        "F5 day and session keys sanitise the symbol")
require('"_"+_Symbol+"_"+leaf' not in ea and '"_"+_Symbol+"_"+leaf' not in code,
        "F5 no guard key uses the raw symbol name any more")

# F6 the messages name what actually clears each breaker.
for stale in ("EA restart required to resume",
              "requires EA restart to clear",
              "restart required"):
    require(stale not in ea,
            "F6 the retired sentence %r is gone from the file outside its own "
            "audit note (a restart never cleared a persisted breaker)" % stale)
require("clears by itself at the next server day roll" in ea,
        "F6 the daily refusal says it clears at the server-day roll")

# F7 a dry run has its own counter (see tools/test_execution_safety.py for the full
# set of assertions); here: the counters are separate objects.
require("int DryTradesToday()" in code and "void CountOneDryTrade()" in code,
        "F7 dry rehearsals have their own persisted counter")

print("AutoTrader contract checks passed; this is not an MT5 run and not a backtest.")
