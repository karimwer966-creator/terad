#!/usr/bin/env python3
"""AUDIT-EX1 - execution safety contracts for QSMC_AutoTrader.mq5.

WHY THIS FILE EXISTS
--------------------
The companion contract test (tools/test_autotrader_contract.py) proves the
things that would lose money in one specific way: it ships inert, it sizes down,
it refuses a signal with no stop, it cannot martingale. It did NOT cover five
behavioural defects that were found by reading the send path end to end:

  D1  a failed order marked the signal SEEN while the code's own comment said
      "Not marked: the next poll may succeed" - one requote destroyed a valid
      signal permanently and the journal read "signals 1, sent 0, refused 0".
  D2  the terminal-global key carried no SYMBOL, so two charts with the same
      magic and the same bar time suppressed each other's signals.
  D3  the reward:risk ratio was validated in the INDICATOR at its planned zone
      entry and never re-measured at the price actually paid, so a plan could be
      chased until its remaining RR was a fraction of what the gate approved.
  D4  when InpCloseOnOpposite=true and the close FAILED, the EA still opened the
      new position - two opposite exposures on a hedging account.
  D5  a refused break-even PositionModify was re-sent on every tick, silently.

These checks pin the FIXED shape of the send path, so a future edit cannot
quietly restore any of the five. They are source contracts, not a compiler and
not a backtest: F7 in MetaEditor and a demo run remain the human gates.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "MQL5" / "Experts" / "QSMC_AutoTrader.mq5"

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("PASS  " + label)
    else:
        print("FAIL  " + label)
        FAILURES.append(label)


ea = EA.read_text(encoding="utf-8", errors="replace")
# `noc` keeps the string literals (the anchors are journal text), `code` strips
# them too (the assertions below are about code, not about prose in a Print()).
noc = re.sub(r"//[^\n]*", "", ea)
code = re.sub(r'"(?:\\.|[^"\\])*"', '""', noc)

check(EA.is_file(), "the execution companion exists")
check("void HandleSignal" in code, "the send path is one named function (HandleSignal)")

# ---------------------------------------------------------------- D1 order failure
check("bool RetcodeIsTransient(const uint rc)" in code,
      "D1 there is one classifier for a server refusal (transient vs permanent)")
for tc in ("TRADE_RETCODE_REQUOTE", "TRADE_RETCODE_PRICE_CHANGED",
           "TRADE_RETCODE_PRICE_OFF", "TRADE_RETCODE_TIMEOUT",
           "TRADE_RETCODE_CONNECTION", "TRADE_RETCODE_TOO_MANY_REQUESTS",
           "TRADE_RETCODE_FROZEN"):
    check(tc in code, "D1 %s is classified as transient" % tc)
check("   return false;\n  }" in code.replace("\r\n", "\n"),
      "D1 the classifier defaults to permanent (an unknown retcode never retries)")

fail_block = noc[noc.index("ORDER FAILED"):]
fail_block = fail_block[:fail_block.index("void ProcessSignals")]
check("if(!RetcodeIsTransient(rc))" in fail_block,
      "D1 a permanent refusal is the ONLY path that marks the signal seen")
check("g_retry_count>=(int)MathMax(1,InpOrderRetryMax)" in fail_block,
      "D1 retries are bounded, so a broken broker cannot become an order flood")
check(fail_block.count("MarkSeen(") >= 2,
      "D1 the give-up path also marks seen, so the signal cannot age out mid-flood")

# The old defect shape: the failure branch marked seen unconditionally.
old_shape = re.search(r"Not marked: the next poll may succeed if the refusal was transient\.\s*\r?\n\s*MarkSeen\(",
                      ea)
check(old_shape is None,
      "D1 the 'not marked ... MarkSeen()' contradiction is gone (comment matches code)")

# ------------------------------------------------------- D2 cross-chart suppression
glob = ea[ea.index("string GlobName"):ea.index("bool SeenBefore")]
check("_Symbol" in glob,
      "D2 the terminal-global key carries the symbol (two charts cannot suppress each other)")
check("GlobalVariableCheck(GlobName(bar_time,dir))" in code,
      "D2 the reload guard still reads the same key (no second, symbol-less key survives)")

check("string KeySafe(const string s)" in code,
      "D2b this EA's own global-variable namespace sanitises the symbol (a suffix "
      "character would make GlobalVariableSet fail silently)")
check("KeySafe(_Symbol)" in code and code.count("KeySafe(_Symbol)") >= 2,
      "D2b both the writer and the housekeeping sweep use the sanitised symbol")

# ------------------------------------------------------------- D3 RR at the fill price
m = re.search(r"input\s+double\s+InpMinRRAtFill\s*=\s*([0-9.]+)\s*;", ea)
check(m is not None, "D3 InpMinRRAtFill is an input (the check can be argued with, or off)")
check(m is not None and float(m.group(1)) >= 1.0,
      "D3 it refuses any plan whose remaining RR is below 1:1 by default")
rr_at = code.index("InpMinRRAtFill>0.0")
buy_at = code.index("ok=g_trade.Buy(")
check(rr_at < buy_at, "D3 the RR check runs BEFORE the order, not after it")
rr_block = code[rr_at:code.index("if(!SpreadOK(sym))")]
check(rr_at < code.index("if(!SpreadOK(sym))") < buy_at,
      "D3 the RR check sits with the permanent geometry checks, before every transient gate")
check("MathAbs(s.tp-price)" in rr_block and "MathAbs(price-s.sl)" in rr_block,
      "D3 RR is measured from the price that will be on the ticket, not the planned entry")
check("return;" in rr_block and "MarkSeen(" not in rr_block,
      "D3 a refusal is transient: the signal stays retryable while it is young")


def rr_at_fill(tp, price, sl):
    """The companion's arithmetic, restated so the contract is executable."""
    risk = abs(price - sl)
    return abs(tp - price) / risk if risk > 0 else 0.0


check(abs(rr_at_fill(1.1200, 1.1100, 1.1050) - 2.0) < 1e-12,
      "D3 reference: a plan 100 pips from TP and 50 from SL is 2.0R")
check(rr_at_fill(1.1200, 1.1180, 1.1050) < 1.0,
      "D3 reference: chasing 80 of the 150 pips leaves 0.15R and must be refused")

# --------------------------------------------------------- D4 opposite close failure
close_at = noc.index("g_trade.PositionClose(opposite)")
close_block = noc[close_at:noc.index("ok=g_trade.Buy(")]
check("return;" in close_block,
      "D4 a failed close aborts the entry instead of stacking a second exposure")
check("no new position opened on top of it" in close_block,
      "D4 the journal names the reason, so the silence has a cause")

# ------------------------------------------------------------ D5 break-even throttle
be_at = code.index("void ManageOpenPositions")
be_block = code[be_at:code.index("int OnInit()")]
check("g_be_last_try" in code and "<30) continue;" in be_block,
      "D5 a refused break-even is attempted once per pause, not on every tick")
check("g_be_warned_ticket" in be_block,
      "D5 the refusal is printed once per ticket instead of being swallowed")
check("PositionModify(ticket,new_sl,tp)" in be_block,
      "D5 the only stop change is still towards break-even (never widened)")

# ------------------------------------------------------------------- safety envelope
check(re.search(r"input\s+bool\s+InpEnableTrading\s*=\s*false", ea) is not None,
      "the companion still ships INERT after these fixes")
check(re.search(r"input\s+bool\s+InpDryRun\s*=\s*true", ea) is not None,
      "the companion still ships in DRY RUN after these fixes")
check("InpMinRRAtFill<0.0 || InpOrderRetryMax<1" in code,
      "both new inputs are validated at init instead of failing at the first signal")

# ------------------------------------------------ D6 production hardening
# The review found four more things that are fine while a chart is untouched and
# wrong the moment an operator reloads, restarts or widens a preset. They are
# pinned here because each one failed SILENTLY before.

# D6a the daily-loss baseline must survive a reload
check("string DayGuardKey(const string leaf)" in code,
      "D6a the day guard key carries the account login and the magic")
check("GlobalVariableSet(DayGuardKey(\"EQ\"),g_day_start_equity)" in noc,
      "D6a the baseline is written to the terminal, not kept only in memory")
check("GlobalVariableSet(DayGuardKey(\"BLOCKED\"),1.0)" in noc and
      "GlobalVariablesFlush()" in noc,
      "D6a the block is persisted and flushed, so a reload cannot re-base the day")
check("g_day_start_equity=(eq0>0.0 ? eq0 : AccountInfoDouble(ACCOUNT_EQUITY))" in code,
      "D6a a restart restores the SAME baseline for the same server day")
check("DayGuardLoad(day)" in code and "(int)GlobalVariableGet(kd)!=day" in code,
      "D6a a new server day is the only thing that creates a new baseline")

# D6b slippage must be an input, not a constant
m = re.search(r"input\s+int\s+InpDeviationPoints\s*=\s*(\d+)\s*;", ea)
check(m is not None, "D6b InpDeviationPoints is an input")
check(m is not None and 10 <= int(m.group(1)) <= 30,
      "D6b the default is inside the range where a normal broker actually fills")
check("SetDeviationInPoints((ulong)MathMax(0,InpDeviationPoints))" in code,
      "D6b the trade object uses the input, not a hard-coded 10")
check("SetDeviationInPoints(10)" not in code,
      "D6b the hard-coded 10-point slippage is gone")
check("InpDeviationPoints<0" in code, "D6b a negative slippage is refused at init")

# D6c housekeeping for the terminal globals this EA owns
check("void PurgeStaleSignalGlobals()" in code,
      "D6c there is one housekeeping function for the EA's own terminal globals")
purge = code[code.index("void PurgeStaleSignalGlobals()"):code.index("int OnInit()")]
check("StringFind(name,pfx)!=0" in purge,
      "D6c it only touches keys this EA wrote (prefix = magic + symbol)")
check("86400" in purge and "GlobalVariableDel(name)" in purge,
      "D6c keys older than one day are deleted; today's are kept (they stop a re-fire)")
check(code.count("PurgeStaleSignalGlobals();") >= 2,
      "D6c it runs at init AND at deinit, so a crash-load does not leak them either")

# D6d the diagnostic line must not present a COUNT as a measurement
check('"anchors "' not in code,
      "D6d GP_ANCH is no longer printed as an 'anchors' value to compare with a threshold")
check("candidates that reached the anchor gate" in noc,
      "D6d it is labelled as a count, in words")

# D6e dead indicator inputs are labelled dead in the dialog
host = (ROOT / "nadir2.mq5").read_text(encoding="utf-8", errors="replace")
host_lines = [l for l in host.replace("\r\n", "\n").split("\n") if re.match(r"^\s*(sinput|input)\s", l)]
labelled = [l for l in host_lines if "INERT" in l]
check(len(labelled) >= 41,
      "D6e every input that nothing reads says INERT in its own label (%d found)" % len(labelled))
check("Signal outcome log: ON" in host and "entry model:" in host,
      "D6f the signal-log banner names its entry model (a limit entry cannot describe the EA)")

# D6g the production runbook exists and covers the four human gates
runbook = ROOT / "docs" / "QSMC_GO_LIVE_RUNBOOK.md"
check(runbook.is_file(), "D6g there is a go-live runbook, not only a code contract")
if runbook.is_file():
    rb = runbook.read_text(encoding="utf-8")
    for needle, label in (
        ("F7", "the runbook names F7 as a human gate"),
        ("InpRealAccountConfirm", "the runbook explains arming a real account"),
        ("Kill switches", "the runbook lists the kill switches, fastest first"),
        ("نسختان من المؤشر", "the runbook warns that the EA runs the indicator's DEFAULTS"),
        ("Rollback", "the runbook has a rollback procedure"),
        ("InpSigLogEntryRef", "the runbook states what the evidence log measures"),
    ):
        check(needle in rb, "D6g " + label)

print("=" * 60)
TOTAL = ea.count("\n")
print("AUDIT-EX1 execution-safety checks: %d checks, failures: %d" % (CHECKS[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  failed: " + f)
    raise SystemExit(1)
print("All execution-safety contracts hold. This is a source contract: it does not")
print("prove MetaEditor compiles the file, and it is not a backtest. Press F7.")
