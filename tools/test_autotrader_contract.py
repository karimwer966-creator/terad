#!/usr/bin/env python3
"""Contract checks for the QSMC execution companion (MQL5/Experts/QSMC_AutoTrader.mq5).

The companion is the only file in this repository allowed to reach the trade API,
so these checks are deliberately about the things that lose money:
  * it consumes ONLY the CORE published-signal buffers, not previews or ZRE,
  * its buffer indices really are the indicator's CORE export slots,
  * it ships inert / dry-run / demo-only, with a 1% risk ceiling,
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
expected = {"DIR": 7, "ENTRY": 8, "SL": 9, "TP1": 10, "TP2": 11, "TP3": 12}
require(ea_bufs == expected, "the companion's CORE buffer map is 7..12 as documented")
for i, field in [(7, "Dir"), (8, "Entry"), (9, "SL"), (10, "TP1"), (11, "TP2"), (12, "TP3")]:
    require(buf_bind.get(str(i)) == f"BufSigCore{field}",
            f"indicator buffer {i} is still BufSigCore{field} (the companion reads this slot)")

require(re.search(r"input\s+bool\s+InpExportSignalBuffers\s*=\s*true", host),
        "the indicator still exports the CORE signal buffers by default")
require(all(t not in ea for t in ("QSMC_BUF_ZRE", "BufSigZRE", "BufPrevBuy", "BufEntryBuy")),
        "the companion reads no preview mark and no ZRE buffer - only published CORE facts")

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


require(inp_bool("InpEnableTrading") == "false",
        "ships INERT: InpEnableTrading=false (no order can be sent until a human says so)")
require(inp_bool("InpDryRun") == "true",
        "first switch-on is still a DRY RUN: InpDryRun=true")
require(inp_bool("InpDemoOnly") == "true",
        "refuses a real-money account by default: InpDemoOnly=true")

require(re.search(r"input\s+double\s+InpMaxRiskPercent\s*=\s*1\.0*\s*;", ea) is not None,
        "hard risk ceiling: InpMaxRiskPercent defaults to 1% of equity per trade")
require("if(vmax_cap>1.0) vmax_cap=1.0;" in code,
        "the ceiling cannot be raised above 1% by the operator")
require("double pct=MathMin(InpRiskPercent,vmax_cap);" in code,
        "the requested risk is clamped to the ceiling before sizing")
require("AccountInfoDouble(ACCOUNT_EQUITY)*pct/100.0" in code,
        "risk is a fraction of current equity, not of balance or a fixed lot guess")

# MQL5's integer-to-string converter is IntegerToString(long); there is no
# LongToString(). One invented name produced 27 compile errors in this file.
require("LongToString" not in code,
        "no invented LongToString() - MQL5 spells the converter IntegerToString()")
require(re.search(r'input\s+string\s+InpRealAccountConfirm\s*=\s*""\s*;', ea) is not None,
        "a real account must be NAMED: InpRealAccountConfirm ships empty")
require("InpRealAccountConfirm!=IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))" in code,
        "the real-account check compares the input to the actual account number "
        "(a preset copied from a demo chart cannot arm real money)")
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
    "daily loss guard": 'daily loss guard',
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
require("if(shift>max_age) continue;" in code,
        "a signal older than InpMaxSignalAgeBars is ignored instead of traded late")
require("PositionGetInteger(POSITION_MAGIC)!=InpMagic" in code,
        "only positions carrying this EA's magic number are counted or managed")
require("GlobalVariableCheck(GlobName(bar_time,dir))" in code,
        "a terminal-session global prevents re-firing the same signal after a reload")

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

require("loss>eq*InpMaxRiskPercent/100.0) return 0.0;" in code,
        "the fixed-lot path really refuses a size above the ceiling")

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

print("AutoTrader contract checks passed; this is not an MT5 run and not a backtest.")
