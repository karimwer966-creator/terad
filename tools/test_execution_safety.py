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

v6.6.20 Phase 1 additions (2026-11-09, "Execution Safety & Demo Readiness"):
  D9  unified DEMO & REAL execution: automatic detection from
      ACCOUNT_TRADE_MODE; DEMO accepted with the DEMO profile; REAL accepted
      ONLY behind the explicit authorization (InpAllowRealTrading + exact
      login + exact server), re-verified at init AND before every order;
      CONTEST and UNKNOWN rejected; identity drift latches an emergency
      lockout until a re-attach; REAL risk profile is separate and
      conservative; DEMO cannot become REAL and REAL never arms itself.
  D10 the order is not the execution: retcode classification, position/deal
      confirmation BEFORE g_sent, server-side SL/TP verified on the position,
      emergency repair/close when protection is missing, partial fills named,
      anything unverifiable counted in g_unconfirmed - never in g_sent.
  D11 buffer garbage can never become an order: NaN/huge sentinels in
      dir/entry/sl/tp are refused permanently; a duplicate signal stays
      marked seen after ANY outcome.
  Each scenario below also runs a Python reference model of the decision
  logic (the same shape as the MQL5), so the behaviour is executable here.
"""
import math
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
check("!QER_RetryAllows(g_retry_counts[slot],InpOrderRetryMax)" in fail_block,
      "D1 retries are bounded, so a broken broker cannot become an order flood")
check(fail_block.count("MarkSeen(") >= 2,
      "D1 the give-up path also marks seen, so the signal cannot age out mid-flood")

# The old defect shape: the failure branch marked seen unconditionally.
old_shape = re.search(r"Not marked: the next poll may succeed if the refusal was transient\.\s*\r?\n\s*MarkSeen\(",
                      ea)
check(old_shape is None,
      "D1 the 'not marked ... MarkSeen()' contradiction is gone (comment matches code)")

# ------------------------------------------------------- D2 cross-chart suppression
# v6.6.24 (F-011): the namespace now has one definition, so the symbol check
# follows it there instead of looking for the literal inside GlobName().
glob = ea[ea.index("string SeenNamespace"):ea.index("bool SeenBefore")]
check("KeySafe(_Symbol)" in glob and "ACCOUNT_LOGIN" in glob,
      "D2 the terminal-global key carries the symbol and the account (two charts / "
      "two logins cannot suppress each other)")
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
# 2026-11-09: the shipping default changed from "inert + dry run" to "armed on
# demo". The property these two checks protected is unchanged - a fresh attach
# must not be able to lose real money - so it is now asserted where it lives: the
# disarmed REAL (arming switch OFF, empty login/server), and the unconditional refusal
# in OnInit. Asserting the old literals would assert the wrong invariant.
check(re.search(r"input\s+bool\s+InpEnableTrading\s*=\s*true", ea) is not None,
      "the companion ships ARMED (demo-first delivery): InpEnableTrading=true")
check(re.search(r"input\s+bool\s+InpDryRun\s*=\s*false", ea) is not None,
      "orders are really sent, so the demo run is not a second dry run: InpDryRun=false")
check(re.search(r"input\s+bool\s+InpDemoOnly", ea) is None,
      "the old binary demo-only toggle is gone: detection + authorization replaced it")
check("AccountModeKnown(acct_mode)" in code and
      "INIT REFUSED: REAL account detected" in noc,
      "OnInit refuses an unauthorized REAL account before the first tick")
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
check(len(labelled) >= 40,  # v6.6.19 wires InpShowPerfMeter, so one fewer INERT label
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
        ("EXECUTION_REAL", "the runbook names the unified execution modes"),
        ("Kill switches", "the runbook lists the kill switches, fastest first"),
        ("نسختان من المؤشر", "the runbook warns that the EA runs the indicator's DEFAULTS"),
        ("Rollback", "the runbook has a rollback procedure"),
        ("InpSigLogEntryRef", "the runbook states what the evidence log measures"),
    ):
        check(needle in rb, "D6g " + label)

# ---------------------------------------------------------------- D7 discipline
# The indicator SCORES the session (100 in a kill zone, 75 London/NY, 40 Asia,
# 30 off) but that score is 5% of a reliability blend: it can never stop an
# entry at 03:00. The four habits below live in the EXECUTION layer, because a
# professional trader's discipline is not a number in a formula - it is a
# refusal. All four default to OFF so shipped behaviour is unchanged.
check("InpSessionStartHour" in code and "InpSessionEndHour" in code,
      "D7a the session window is an explicit input pair, not an implicit hour test")
check("bool SessionOpenNow(string &why)" in code,
      "D7b one function decides the session, so the gate and the journal cannot disagree")
# v6.6.24: the window arithmetic moved into the pure rules header, so the wrap
# case is pinned where it now lives AND the EA is pinned to call it.
RULES = ROOT / "MQL5" / "Include" / "QSMC" / "QSMC_ExecutionRules.mqh"
rules = RULES.read_text(encoding="utf-8", errors="replace")
check("return (hour>=start || hour<end);" in rules and
      "QER_SessionInside(h,InpSessionStartHour,InpSessionEndHour)" in code,
      "D7c a window may wrap midnight (Asia / NY-only mandates), not only sit inside one day")
check("if(!SessionOpenNow(dis))" in code and "Note(key,dis);" in code,
      "D7d a closed window REFUSES the entry and prints the reason")
check("InpMaxTradesPerDay" in code and "void CountOneTrade()" in code,
      "D7e entries per day are capped and counted")
# F-011 (v6.6.24): the seen-key namespace must have ONE definition, or the
# purge and the writer disagree again and the purge silently matches nothing.
check("string SeenNamespace()" in code,
      "F-011 the seen-key namespace is defined once")
check(code.count("SeenNamespace()") >= 3,
      "F-011 both GlobName() and the purge use that one definition")
check('string pfx="QSMC_AT_"+IntegerToString(InpMagic)' not in code,
      "F-011 the login-less purge prefix is gone (it could never match)")
check('DayGuardKey("TRADES")' in noc,
      "D7f the daily count is persisted in the day-guard namespace, so a reload cannot reset it")
check('GlobalVariableSet(DayGuardKey("TRADES"),0.0);' in noc,
      "D7g the counter resets on a NEW server day, together with the equity baseline")
check("bool CooldownActive(string &why)" in code,
      "D7h there is a cooldown after a losing close (no revenge re-entry)")
check("(ENUM_DEAL_ENTRY)HistoryDealGetInteger(t,DEAL_ENTRY)!=DEAL_ENTRY_OUT" in code,
      "D7i the cooldown reads CLOSING deals only, not entries")
check("HistoryDealGetDouble(t,DEAL_COMMISSION)" in code and "HistoryDealGetDouble(t,DEAL_SWAP)" in code,
      "D7j the cooldown classifies a loss NET of commission and swap, not gross")
check("InpPartialCloseAtR" in code and "InpPartialClosePercent" in code,
      "D7k a partial can be banked at +R (default off)")
check("g_trade.PositionClosePartial(ticket,part)" in code,
      "D7l the partial is a real partial close, not a second opposite order")
check("PosRiskRemember(ticket,risk)" in code and "g_pos_risk" in code,
      "D7m the ORIGINAL R is remembered per ticket (break-even erases it)")
check("if(part<vmin || remain<vmin)" in code,
      "D7n a lot size that cannot be split is skipped and counted, not sent and rejected")
check("moved>=InpPartialCloseAtR*risk" in code,
      "D7o the partial triggers on R moved from the real entry")
# Ordering: the partial must be evaluated before break-even moves the stop.
check(code.find("moved>=InpPartialCloseAtR*risk") < code.find("moved<InpBreakEvenAtR*risk") or
      code.find("InpPartialCloseAtR>0.0 && moved") < code.find("moved<InpBreakEvenAtR*risk"),
      "D7p the partial is taken BEFORE break-even can overwrite the stop distance")
# 2026-11-09 (F7): the old rule was "a dry run counts toward InpMaxTradesPerDay so
# the cap is rehearsable". In practice it meant three rehearsed plans consumed the
# budget and the first REAL signal of the day was refused. The cap is still
# rehearsable - the dry counter is persisted and printed - but it is counted apart.
check('CountOneDryTrade();' in code,
      "F7 a DRY RUN entry is counted in its own counter, not in the live entry budget")
check('CountOneTrade();' in code and
      code.count("CountOneDryTrade();") >= 1 and
      "CountOneTrade();\r\n      g_dry++;" not in code and
      "CountOneTrade();\n      g_dry++;" not in code,
      "F7 a dry run can no longer spend the live budget (the g_dry branch counts dry only)")
check("entries today " in ea and "dry rehearsals today " in ea,
      "F7 the heartbeat prints both counters, so a rehearsal is visible without being spent")
check("DisciplineSuffix()" in code,
      "D7q the heartbeat names the discipline layer instead of leaving 'CORE 1, sent 0' unexplained")
check("discipline: " in noc,
      "D7r the init banner states all four discipline settings, so a preset is visible")

# --------------------------------------------------- D8 fixed pip ladder (opt-in)
# "Open 0.05 lots and take 100/200/300 pips" cannot be expressed with InpTPLevel,
# so the execution layer now owns a three-rung ladder. These are the properties
# that would cost money if they broke: the ladder is OFF by default, it changes
# the TP BEFORE the geometry checks, it banks from the ORIGINAL volume, it never
# moves a stop away from the entry, it survives a reload, and it cannot try to
# close a size the broker refuses eight times a second.
check(re.search(r"input\s+bool\s+InpUseTPPips\s*=\s*false", ea) is not None,
      "D8a the pip ladder ships OFF - the default behaviour of the EA is unchanged")
check(re.search(r"input\s+int\s+InpTP1Pips\s*=\s*100", ea) is not None and
      re.search(r"input\s+int\s+InpTP2Pips\s*=\s*200", ea) is not None and
      re.search(r"input\s+int\s+InpTP3Pips\s*=\s*300", ea) is not None,
      "D8b the three rungs default to 100 / 200 / 300 pips")
check("double PipPointsFor(const string sym)" in code and "double PipsToPrice(" in code,
      "D8c pip size is resolved per symbol in one pure helper, not hard-coded at the call site")
check('StringFind(u,"XAU")' in noc and "return 10.0;" in code,
      "D8d gold resolves one pip to 0.10 of price and 5/3-digit FX to 10 points")
check("input int    InpPipPoints            = 0;" in ea,
      "D8e the operator can override the pip definition (0 = auto)")
check("double PlanTP(const int shift,const double base,const bool buy)" in code,
      "D8f one function decides the TP for both modes, so checks and the ticket cannot disagree")
# 2026-11-06: refusal sites are classified now (NoteClass(key,...,REJECT_*)), so
# this probe matches the MESSAGE rather than the call form. The ordering claim is
# unchanged: the ladder TP is decided before the first geometry refusal.
_m_ladder=noc.find("double ladder_tp=PlanTP(s.shift,price,buy);")
_m_stop=noc.find('"signal has no stop"')
check(_m_ladder>=0 and _m_stop>=0 and _m_ladder<_m_stop,
      "D8g the ladder TP is applied BEFORE every geometry check (no-chase, RR, stops level)")
check(code.find("if(InpUseTPPips)") < code.find("double lots=CalcLots("),
      "D8h the ladder decision happens before sizing and before any order call")
check("double v0=PosVolume0(ticket,PositionGetDouble(POSITION_VOLUME));" in code,
      "D8i rung percentages are of the ORIGINAL volume, not of what is left")
check("for(int guard=0;guard<2;guard++)" in code,
      "D8j a gap through both rungs is banked in one pass (no skipped partial)")
check("if(!LadderClose(ticket,step+1,v0,live)) break;" in code,
      "D8k a refused close stops the pass instead of looping on the server")
check("if(part>live) part=NormalizeDouble(live,3);" in code and
      "remain>0.0 && remain<vmin" in code,
      "D8l the close never exceeds the live volume and never leaves a sub-minimum remainder unattempted")
check("if(buy)\n     {\n      if(sl>=want_sl || want_sl>=cur) return;" in code and
      "if(sl<=want_sl || want_sl<=cur) return;" in code,
      "D8m the ladder stop only moves toward profit: a stop already past the rung is left alone")
check("if(done>=2 && InpMoveSLToTP1AtTP2)      want_sl=l1;" in code,
      "D8n after rung 2 the stop moves to rung 1 (locked), not beyond it")
check('GlobalVariableSet(LadderKey(ticket,"STEP"),(double)step);' in noc and
      'GlobalVariableGet(k)' in noc,
      "D8o the rung counter is persisted per ticket, so a reload cannot bank the same rung twice")
check('GlobalVariableSet(k,live);' in code,
      "D8p the original volume is persisted too (the in-memory ring dies with the EA)")
check("void PurgeLadderGlobals()" in code and "if(PositionSelectByTicket(t)) continue;" in code,
      "D8q ladder memory is purged for tickets that no longer exist, and only for those")
check("if(InpUseTPPips)\n        {\n         ManagePipLadder(ticket,buy,entry,cur,sl,tp);\n         continue;" in code,
      "D8r exactly ONE exit manager owns a position: the ladder replaces the R partial and the R break-even")
check('if(InpTP1Pips<=0 || InpTP2Pips<=InpTP1Pips || InpTP3Pips<=InpTP2Pips)' in code,
      "D8s a ladder that is not strictly ascending is refused at init, not at the first signal")
check("InpTP1ClosePercent+InpTP2ClosePercent>99.0" in code,
      "D8t two rungs that together close everything are refused (nothing would reach rung 3)")
check("0 < InpTP1Pips < InpTP2Pips < InpTP3Pips" in ea,
      "D8u the refusal names the exact constraint instead of failing silently")
check("1 pip = " in ea and "the stop may be at most " in ea,
      "D8v the attach banner prints the resolved pip size, the money per rung and the widest stop the 1% cap can pay for")
_init_ladder = noc[noc.find("0 < InpTP1Pips < InpTP2Pips < InpTP3Pips"):]
check("return INIT_PARAMETERS_INCORRECT;" in _init_ladder[:1600],
      "D8w bad ladder inputs stop OnInit instead of running with a half-configured exit")

# Reference arithmetic for LadderClose(): 0.05 lots, 40% + 40%, step 0.01,
# minimum 0.01 -> 0.02 banked, 0.03 left, 0.02 banked, 0.01 runs to rung 3.
def ladder_split(v0, pct, live, step, vmin):
    part = math.floor((v0 * pct / 100.0) / step + 0.0000001) * step
    part = round(part, 3)
    if part <= 0.0:
        return 0.0, live
    if part > live:
        part = live
    remain = round(live - part, 3)
    if remain > 0.0 and remain < vmin:
        return 0.0, live
    return part, remain


p1, left1 = ladder_split(0.05, 40.0, 0.05, 0.01, 0.01)
p2, left2 = ladder_split(0.05, 40.0, left1, 0.01, 0.01)
check(abs(p1 - 0.02) < 1e-9 and abs(left1 - 0.03) < 1e-9,
      "D8x reference: 0.05 lot ladder banks 0.02 at rung 1 and leaves 0.03")
check(abs(p2 - 0.02) < 1e-9 and abs(left2 - 0.01) < 1e-9,
      "D8y reference: rung 2 banks another 0.02 and leaves 0.01 for rung 3")
p3, left3 = ladder_split(0.02, 40.0, 0.02, 0.01, 0.01)
check(p3 == 0.0 and left3 == 0.02,
      "D8z reference: when 40% is under one volume step the rung closes nothing and is not retried")


# ================================================================ D9 unified
# Scenarios: DEMO detected+accepted / REAL rejected without authorization /
# REAL accepted only with exact login+server+arming / CONTEST rejected /
# UNKNOWN rejected / wrong login / wrong server / identity drift at runtime /
# risk-profile isolation.
check("bool AccountModeKnown(long &mode)" in code,
      "D9 one account-mode resolver (login + server corroborated, enum checked)")
check("StringLen(server) == 0" in code and "login <= 0" in code,
      "D9 an account with unreadable login/server CANNOT look like a demo")
check("ACCOUNT_TRADE_MODE_CONTEST" in code and "ACCOUNT_TRADE_MODE_REAL" in code,
      "D9 all three known modes are handled explicitly")
check("m != (long)ACCOUNT_TRADE_MODE_CONTEST" in code and
      "m != (long)ACCOUNT_TRADE_MODE_REAL" in code,
      "D9 an enum value outside the three known ones fails closed")
check("bool RealAuthorized(string &why)" in code,
      "D9 the REAL authorization is ONE function - init and pre-submit cannot disagree")
check("if(!InpAllowRealTrading)" in code,
      "D9 REAL is armed only by the explicit switch, default OFF")
check('StringLen(InpRealAccountConfirm) == 0' in code and
      'InpRealAccountConfirm != login_s' in code,
      "D9 REAL requires the EXACT login of THIS account")
check('StringLen(InpRealServerConfirm) == 0' in code and
      'InpRealServerConfirm != server' in code,
      "D9 REAL requires the EXACT broker server of THIS account")
check("g_emergency_lockout || g_acct_changed" in code,
      "D9 no emergency lockout may coexist with REAL authorization")
check("g_day_blocked || g_drawdown_blocked || g_loss_streak_blocked" in code,
      "D9 a latched risk breaker revokes REAL authorization too")
check("bool IdentityMatchesSnapshot()" in code and "g_acct_login" in code and
      "g_acct_server" in code and "g_acct_mode" in code,
      "D9 the account identity is snapshotted at init (login+server+mode)")
check("g_acct_changed = true;" in code and "g_emergency_lockout = true;" in code,
      "D9 identity drift blocks new entries and latches the lockout until a re-attach")
check("INIT REFUSED: REAL account detected" in noc,
      "D9 REAL without authorization fails at init (INIT_FAILED, no orders)")
check("INIT REFUSED: this is a CONTEST account" in noc,
      "D9 CONTEST fails at init (INIT_FAILED, no orders)")
check("the account mode cannot be verified" in noc,
      "D9 UNKNOWN fails at init (fail closed)")
check("EXECUTION_DEMO" in noc and "EXECUTION_REAL" in noc and "EXECUTION_BLOCKED" in noc,
      "D9 the execution mode is derived, named and logged (never typed in)")
# the pre-submit gate re-runs everything
check("if(!IdentityMatchesSnapshot())" in code and
      "the account identity changed after attach" in noc,
      "D9 identity is re-verified immediately before every order")
check("REAL account detected but NOT authorized: " in noc,
      "D9 REAL without authorization is refused at the order, every order")
# risk profile isolation
check("bool RealProfileActive()" in code and "g_exec_mode == 2" in code,
      "D9 one predicate ties the profile to the authorized state")
for name, want in (("InpRealMaxRiskPercent", "0.25"),
                   ("InpRealMaxDailyLossPercent", "1.00"),
                   ("InpRealMaxAccountDrawdownPct", "5.00"),
                   ("InpRealMaxAggregateRiskPercent", "0.50"),
                   ("InpRealMaxOpenPositions", "1"),
                   ("InpRealMaxTradesPerDay", "2")):
    check(re.search(r"input\s+\w+\s+" + name + r"\s*=\s*" + want + r"\s*;", ea) is not None,
          "D9 the REAL profile is separately configured and conservative: %s=%s" % (name, want))
check("double HardMaxAggregateRiskPercent(){ return 2.00; }" in code,
      "D9 the aggregate-risk input is HARD-bounded for both profiles")
check("double EffectiveAggregateRiskPct()" in code and
      "InpRealMaxAggregateRiskPercent" in code and "InpMaxAggregateRiskPercent" in code,
      "D9 aggregate open risk exists for BOTH profiles (REAL's separate input)")
check("int MaxOpenPositionsNow()" in code and "int MaxTradesPerDayNow()" in code,
      "D9 position and daily-entry caps are profile-aware")
check("OpenRiskMoney()" in code and "EffectiveAggregateRiskPct()" in code,
      "D9 aggregate open risk is enforced at the order, not only printed")
check("WITH a server-side stop" not in ea and
      "an EA position is open WITHOUT a server-side stop" in noc,
      "D9 an unprotectable open position blocks new entries (fail closed)")
check("REAL profile: risk<=" in noc or "REAL profile" in noc,
      "D9 the REAL attach banner prints the REAL profile ceilings")

def acct_decision(login, server, mode_raw, allow_real, login_input, server_input,
                  permissions_ok=True, lockout=False):
    """Reference model of the unified detection + REAL authorization."""
    KNOWN = (0, 1, 2)  # DEMO, CONTEST, REAL
    if login is None or login <= 0:
        return "BLOCKED (unverifiable)"
    if not server:
        return "BLOCKED (unverifiable)"
    if mode_raw not in KNOWN:
        return "BLOCKED (unverifiable)"
    if mode_raw == 0:
        return "EXECUTION_DEMO (DEMO profile)"
    if mode_raw == 1:
        return "BLOCKED (CONTEST)"
    # REAL: every condition, in order
    if not allow_real:
        return "BLOCKED (REAL not armed)"
    if not login_input:
        return "BLOCKED (REAL login confirmation empty)"
    if login_input != str(login):
        return "BLOCKED (REAL login mismatch)"
    if not server_input:
        return "BLOCKED (REAL server confirmation empty)"
    if server_input != server:
        return "BLOCKED (REAL server mismatch)"
    if not permissions_ok:
        return "BLOCKED (permissions)"
    if lockout:
        return "BLOCKED (emergency lockout)"
    return "EXECUTION_REAL (authorized)"

L, S = 8100123, "Broker-DemoServer"
check(acct_decision(L, S, 0, False, "", "").startswith("EXECUTION_DEMO"),
      "D9 reference: a verified DEMO account is accepted (scenario: DEMO accepted)")
check(acct_decision(L, S, 2, False, "", "") == "BLOCKED (REAL not armed)",
      "D9 reference: REAL detected but unarmed is rejected (scenario: REAL rejected)")
check(acct_decision(L, S, 2, True, str(L), S) == "EXECUTION_REAL (authorized)",
      "D9 reference: REAL with arming + exact login + exact server is accepted")
check(acct_decision(L, S, 2, True, "8100124", S) == "BLOCKED (REAL login mismatch)",
      "D9 reference: a wrong login is rejected (scenario: wrong login)")
check(acct_decision(L, S, 2, True, str(L), "Other-Server") == "BLOCKED (REAL server mismatch)",
      "D9 reference: a wrong server is rejected (scenario: wrong server)")
check(acct_decision(L, S, 2, True, str(L), "") == "BLOCKED (REAL server confirmation empty)",
      "D9 reference: a missing server confirmation is rejected")
check(acct_decision(L, S, 1, True, str(L), S) == "BLOCKED (CONTEST)",
      "D9 reference: CONTEST is rejected even fully 'confirmed' (scenario: CONTEST)")
check(acct_decision(L, S, 7, True, str(L), S) == "BLOCKED (unverifiable)",
      "D9 reference: an unknown enum value is rejected (scenario: unknown mode)")
check(acct_decision(0, S, 0, False, "", "") == "BLOCKED (unverifiable)",
      "D9 reference: an unreadable login is rejected even for an enum that says DEMO")
check(acct_decision(L, "", 0, False, "", "") == "BLOCKED (unverifiable)",
      "D9 reference: an unreadable server name is rejected even for an enum that says DEMO")
check(acct_decision(L, S, 2, True, str(L), S, permissions_ok=False) == "BLOCKED (permissions)",
      "D9 reference: REAL without trading permissions is rejected (scenario: permissions)")
check(acct_decision(L, S, 2, True, str(L), S, lockout=True) == "BLOCKED (emergency lockout)",
      "D9 reference: a lockout revokes REAL authorization (scenario: authorization removed at runtime)")
# a DEMO account with REAL credentials typed in is still ONLY a demo
check(acct_decision(L, S, 0, True, str(L), S).startswith("EXECUTION_DEMO"),
      "D9 reference: REAL credentials can never promote a DEMO account (no silent DEMO->REAL)")

# ================================================================ D10 execution
# Scenario 9 partial fills / 5 rejects not counted / 6 duplicates / 8 SL-TP.
check("bool filled_full=(rc==TRADE_RETCODE_DONE);" in code and
      "bool filled_partial=(rc==TRADE_RETCODE_DONE_PARTIAL);" in code and
      "bool accepted_placed=(rc==TRADE_RETCODE_PLACED);" in code,
      "D10 the retcode is classified into fill classes, not a bool")
check("ulong deal_ticket=g_trade.ResultDeal();" in code and
      "ulong pos_ticket=g_trade.ResultOrder();" in code and
      "double filled_vol=g_trade.ResultVolume();" in code,
      "D10 the fill (deal/position ticket, volume) is read from the trade result")
# the confirmed branch is the ONLY place g_sent is incremented
send_block = code[code.index("if(ok && (filled_full || filled_partial) && pos_ok)"):code.index("if(!ok)")]
check(send_block.count("g_sent++") == 2,
      "D10 g_sent is incremented only in the verified-SENT path and the repaired-SENT path")
check(send_block.count("MarkSeen(") >= 3 and send_block.count("CountOneTrade();") >= 2,
      "D10 the confirmed paths mark seen and count the entry, atomically with the decision")
resolve_block = code[code.index("bool pos_ok=false;"):code.index("if(ok && (filled_full")]
check("PositionSelectByTicket(pt)" in resolve_block and
      "POSITION_MAGIC" in resolve_block and "POSITION_SYMBOL" in resolve_block and
      "POSITION_TYPE" in resolve_block,
      "D10 the position is re-read from the account and must match magic/symbol/side")
check("FindOurPosition(sym,(buy ? 1 : -1))" in resolve_block,
      "D10 if the server names no position ticket, our own scan finds it (magic+symbol+side)")
check("pt=FindOurPosition(sym,(buy ? 1 : -1));" in resolve_block and
      "if(pt==0 || !PositionSelectByTicket(pt)) continue;" in resolve_block,
      "D10 if the server order ticket does not select a position, the scan is the fallback (CTrade has no ResultPosition)")
check("for(int attempt=0; attempt<3 && !pos_ok; attempt++)" in resolve_block and
      "Sleep(50)" in resolve_block,
      "D10 a short bounded retry absorbs the fill/position race - never unbounded")
check("sl_present" in send_block and "tp_present" in send_block and
      "sl_side_ok" in send_block and "tp_side_ok" in send_block and
      "sl_match" in send_block and "tp_match" in send_block,
      "D10 server-side SL and TP are verified on the position, with a tolerance")
check("if(filled_partial) g_partial++" in send_block,
      "D10 scenario 9: a partial fill is named and counted separately")
check("PARTIAL FILL" in noc and "requested" in noc,
      "D10 scenario 9: the journal names the partial fill and both volumes")
check(send_block.count("MarkSeen(") >= 3,
      "D10 every confirmed outcome marks the signal seen (no re-fire next poll)")
check("[QSMC_AT] SENT " in noc and "| deal #" in noc and "| position #" in noc,
      "D10 the success line logs symbol, direction, volume, SL, TP, retcode, deal and position tickets")
# the unconfirmed path
unconf = code[code.index("if(ok && (filled_full || filled_partial || accepted_placed))"):code.index("if(!ok)")]
check("g_unconfirmed++" in unconf and "g_sent++" not in unconf,
      "D10 scenario 5/6: an unverifiable fill is logged, marked seen, and NOT counted as sent")
check("UNCONFIRMED" in noc and "| position #" in noc and "deal #" in noc,
      "D10 the unconfirmed line logs the deal and position tickets for the operator")
# the failure path never counts success
fail_at = code.index("if(!ok)")
fail_block = code[fail_at:code.index("void ProcessSignals", fail_at)]
check("g_sent++" not in fail_block,
      "D10 scenario 5: a rejected Buy/Sell can never increment the success counter")
check("g_refused++" in fail_block or "g_retry_count" in fail_block,
      "D10 a rejection is a refusal (permanent) or a bounded retry (transient) - never a success")
# the catch-all for ok==true with an unexpected retcode
catchall = code[fail_at:]
check("unexpected retcode=" in noc and "g_unconfirmed++" in catchall,
      "D10 an ok==true with a non-fill retcode is caught, logged, marked seen - never silent")
# the emergency path
emergency = noc[noc.index("[QSMC_AT][EMERGENCY]"):noc.index("if(!ok)")]
check("g_unprotected++" in emergency,
      "D10 scenario 8: the unresolved emergency is counted and never counted as sent")
check("sl_bounds_loss" in emergency,
      "D10 scenario 8: SL-valid-but-TP-missing keeps the bounded position with a loud alert; no SL -> close")
check("PositionClose(pos_ticket)" in emergency,
      "D10 scenario 8: an unbounded position is closed - it is never left in the market unprotected")
check("MANUAL INTERVENTION REQUIRED" in noc,
      "D10 scenario 8: a failed emergency close demands a human, by name")
check("server SL/TP confirmed on the position" in noc or
      "server SL/TP confirmed after emergency repair" in noc,
      "D10 scenario 8: only a verified server-side SL/TP earns the word SENT")

def outcome(ok, rc, pos_ok, protection_ok):
    """Reference model of the Phase 2-A send-outcome classification."""
    DONE, PARTIAL, PLACED = 10009, 10010, 10008  # TRADE_RETCODE_*
    if not ok:
        return "REJECTED (retry if transient, else abandon)"
    if rc in (DONE, PARTIAL) and pos_ok:
        return "SENT" if protection_ok else "UNPROTECTED (repair or close)"
    return "UNCONFIRMED (marked seen, not counted sent)"

check(outcome(True, 10009, True, True) == "SENT",
      "D10 reference: DONE + position + verified protection = SENT")
check(outcome(True, 10010, True, True) == "SENT",
      "D10 reference: a partial fill that verifies is still an execution (scenario 9)")
check(outcome(True, 10009, False, True) == "UNCONFIRMED (marked seen, not counted sent)",
      "D10 reference: no position found -> NOT sent, marked seen (scenario 5/6)")
check(outcome(True, 10008, False, True) == "UNCONFIRMED (marked seen, not counted sent)",
      "D10 reference: PLACED is accepted-not-filled -> not a success")
check(outcome(True, 10009, True, False) == "UNPROTECTED (repair or close)",
      "D10 reference: position without verified server-side SL/TP is an emergency (scenario 8)")
check(outcome(False, 10004, False, False) == "REJECTED (retry if transient, else abandon)",
      "D10 reference: a requote (trade-server busy) never counts as sent (scenario 5)")

# ================================================================ D11 buffers
# Scenario 10: empty/invalid buffers never trigger trades / scenario 6: duplicates
check("if(CopyBuffer(g_handle,QSMC_BUF_CORE_DIR,0,count,g_dir)<count) { g_signal_copy_failures++; return false; }" in code,
      "D11 a short copy is a refusal, never a partial read")
check("if(!CopySignalBuffers(count)) return;" in code,
      "D11 ProcessSignals refuses to evaluate anything on a failed copy")
check("if(g_dir[shift]==0.0) continue;" in code,
      "D11 the indicator's 0.0 = no-signal contract is still honoured")
check("MathIsValidNumber(d0)" in code and "MathIsValidNumber(e0)" in code and
      "MathIsValidNumber(s0)" in code and "1e30" in code,
      "D11 NaN/huge sentinels in dir/entry/sl are refused as permanent garbage")
check("the selected target buffer is not a finite price" in noc,
      "D11 a garbage target is refused too (unless the pip ladder overrides TP)")
check(code.count("REJECT_PERMANENT") >= 10,
      "D11 invalid-signal refusals are classified permanent (no retry flood)")
check("if(SeenBefore(key,bt,dir)) continue;" in code,
      "D11 scenario 6: the seen-key is consulted before any decision")
check("MarkSeen(key,s.bar_time,s.dir);" in code,
      "D11 scenario 6: every outcome path marks seen (confirmed, repaired, unconfirmed, rejected)")
check("!QER_RetryAllows(g_retry_counts[slot],InpOrderRetryMax)" in code,
      "D11 scenario 6: transient retries are bounded (no duplicate flood)")
# scenario 7: invalid SL/TP prevents entry
check("s.sl = NormalizeDouble(s.sl, _Digits);" in code and
      "s.tp = NormalizeDouble(s.tp, _Digits);" in code,
      "D11 scenario 7: SL/TP are normalized to the symbol's digits before any distance check")
check("signal has no stop" in noc and "signal has no target" in noc,
      "D11 scenario 7: a signal without both levels never reaches the order call")
check("under the minimum" in noc and "over the maximum" in noc and
      "broker stops level rejects this SL/TP" in noc,
      "D11 scenario 7: distance vs InpMin/MaxStopPoints and the broker's stops level are enforced pre-send")
check("StopsModifyDistanceOK" in code,
      "D11 the repair path honours max(stops, freeze) and refuses to widen the stop to pass")

# ------------------------------------------- D12 (AUD-05) freshness fails CLOSED
# The data-age guard asked SymbolInfoTick() and only acted when the call SUCCEEDED.
# A symbol for which the terminal holds no tick at all returned false, the whole
# freshness test was skipped, and control fell through to the order send: the one
# situation where the feed's age is truly unknowable was the one that was never
# refused. Unknown age must refuse, exactly like old age.
def _matched(src: str, open_pos: int) -> str:
    """Text of the {...} block whose '{' is at/after open_pos, braces counted."""
    i = src.index("{", open_pos)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return src[i:]

_pos = code.index("SymbolInfoTick(sym,tk)")
# HandleSignal's copy, not the OnInit one (that guard reads SYMBOL_TIME instead).
_i = code.rindex("if(InpMaxDataAgeSeconds>0)", 0, _pos)
_guard = _matched(code, _i)
check(_guard.count("SymbolInfoTick(sym,tk)") == 1,
      "D12 the freshness guard asks for a tick exactly once")
check("SymbolInfoTick(sym,tk)" in _guard,
      "D12 the guard under test is the SymbolInfoTick one")
_after = _guard[_guard.index("SymbolInfoTick(sym,tk)"):]
check(re.search(r"\}\s*else\s*\{", _after) is not None,
      "D12 SymbolInfoTick()==false has its own branch (the old shape had no else)")
_else = _after[re.search(r"\}\s*else\s*\{", _after).end():]
check("return;" in _else.split("\n")[0:12][0] or "return;" in _else[:600],
      "D12 a symbol with no tick is refused, never sent (fail closed)")
check("SymbolInfoTick() returned false" in noc,
      "D12 the refusal names its cause, so the journal does not read as a mystery")
check(_guard.count("return;") >= 2,
      "D12 both the stale-tick and the no-tick branches refuse (two refusals, one send)")

# ------------------------------------------- D13 (AUD-06) session hours are real hours
# The session window is a pair of server hours. QER_SessionInside() handles the
# half-open window and the wrap over midnight correctly, so 22 -> 6 is a
# legitimate window - but 25 -> 6 is not, and nothing said so. OnInit returned
# INIT_SUCCEEDED with a window no hour can ever satisfy, so the session filter
# refused every signal for the entire session and the operator's only evidence
# was an absence. A window that can never open is a configuration error, and a
# configuration error belongs at attach, not at the fortieth refused signal.
#
# Every lookup below uses .find() and reports a clean FAIL on -1. The first
# draft used .index(), so removing the validation crashed the suite with a
# ValueError instead of naming what was missing - red either way, but a gate
# that cannot say why it is red is a gate nobody can act on.
_on = code.index("int OnInit()")
_init = _matched(code, _on)

RANGE = ("InpSessionStartHour<0", "InpSessionStartHour>23",
         "InpSessionEndHour<0", "InpSessionEndHour>23")
# A range comparison anywhere in the file is not the same as one in OnInit:
# InpSessionEndHour also appears in the preset-delta rows and the attach line.
_i = _init.find(RANGE[0])
check(_i >= 0, "D13 OnInit range-checks InpSessionStartHour against 0",
      )
check(_init.find(RANGE[1]) >= 0, "D13 OnInit range-checks InpSessionStartHour against 23")
check(_init.find(RANGE[2]) >= 0, "D13 OnInit range-checks InpSessionEndHour against 0")
check(_init.find(RANGE[3]) >= 0, "D13 OnInit range-checks InpSessionEndHour against 23")

if _i >= 0:
    # _matched() returns the brace block only, so the condition is taken
    # separately: the four comparisons live in the if(...) and the refusal in
    # the {...}.
    _ifpos = _init.rindex("if(", 0, _i)
    _bstart = _init.index("{", _ifpos)
    _body = _matched(_init, _bstart)
    _blk = _init[_ifpos:_bstart + len(_body)]
    check(all(p in _blk for p in RANGE),
          "D13 all four comparisons sit in ONE condition, not scattered")
    check("INIT_PARAMETERS_INCORRECT" in _blk,
          "D13 an impossible session window refuses the attach, it does not run")
    check(_blk.count("INIT_PARAMETERS_INCORRECT") == 1,
          "D13 and it refuses exactly once, on its own branch")
    check("InpSessionStartHour==InpSessionEndHour" not in _blk,
          "D13 the range check leaves the documented OFF switch alone")
else:
    for _ in range(5):
        check(False, "D13 (skipped - the range check is absent, so its shape "
                     "cannot be examined)")

check("session hours out of range" in ea,
      "D13 the refusal says what is wrong and prints both values it was given")
check("wrap over midnight" in ea,
      "D13 the message keeps the documented wrap-around legal, so the fix does "
      "not read as a new restriction")
check("InpSessionStartHour==InpSessionEndHour" in code,
      "D13 Start == End is still the way to switch the filter off")

# ---------------------------------------------------------------- D14
# docs/EA_RISK_INPUTS.md §5 states which sizing inputs have NO attach-time
# validation, and it cites the line range of OnInit() that was searched to
# prove it. That citation went stale when AUD-06 (D13 above) inserted 17 lines
# into the same function: the searched range :4490-5180 became :4490-5197, so a
# reader who re-ran the search over the cited range would have stopped 17 lines
# short of the end of OnInit(). A citation that names a function range has to be
# measured against the function, not remembered.
EA_DOC = ROOT / "docs" / "EA_RISK_INPUTS.md"
ea_doc = EA_DOC.read_text(encoding="utf-8", errors="replace")
ea_lines = ea.split("\n")

oninit_start = 0
for n, ln in enumerate(ea_lines, 1):
    if ln.startswith("int OnInit()"):
        oninit_start = n
        break
oninit_end = 0
if oninit_start:
    depth = 0
    seen = False
    for n in range(oninit_start, len(ea_lines) + 1):
        depth += ea_lines[n - 1].count("{") - ea_lines[n - 1].count("}")
        if "{" in ea_lines[n - 1]:
            seen = True
        if seen and depth <= 0:
            oninit_end = n
            break
check(oninit_start > 0 and oninit_end > oninit_start,
      "D14 OnInit() located in QSMC_AutoTrader.mq5 by brace matching")

m = re.search(r"`OnInit\(\)`\s*\(`:(\d+)-(\d+)`\)", ea_doc)
check(m is not None,
      "D14 EA_RISK_INPUTS.md section 5 cites the OnInit() range it searched")
if m:
    cited_start, cited_end = int(m.group(1)), int(m.group(2))
    check((cited_start, cited_end) == (oninit_start, oninit_end),
          "D14 the cited OnInit() range %d-%d is the function's real range "
          "%d-%d (the doc is not stale)"
          % (cited_start, cited_end, oninit_start, oninit_end))

FOUR_NUMERIC = ("InpWeakRiskMultiplier", "InpModerateRiskMultiplier",
                "InpStrongRiskMultiplier", "InpMaxAggregateRiskPercent")
inside = {name: [n for n in range(oninit_start, oninit_end + 1)
                 if name in ea_lines[n - 1]] for name in FOUR_NUMERIC}
for name in FOUR_NUMERIC:
    check(bool(inside[name]),
          "D14 %s is named inside OnInit() - it is no longer an input the "
          "attach never looks at" % name)
# Scanned over the comment-stripped view on purpose: the block's own comment
# names InpRequireProfileMatch to explain why there is no check for it, and a
# scan over raw text would report that sentence as a range check.
code_lines = code.split("\n")
check(not [n for n in range(oninit_start, oninit_end + 1)
           if "InpRequireProfileMatch" in code_lines[n - 1]],
      "D14 InpRequireProfileMatch is a bool, so OnInit() invents no range "
      "check for it")
# Scoped to section 5 on purpose: all five names also appear in section 4's
# heading, so a document-wide search would keep passing after the table that
# makes the claim was edited.
sec5_start = ea_doc.find("## 5.")
sec6_start = ea_doc.find("## 6.", sec5_start + 1)
check(sec5_start >= 0 and sec6_start > sec5_start,
      "D14 EA_RISK_INPUTS.md section 5 located (the section that makes the claim)")
sec5 = ea_doc[sec5_start:sec6_start] if sec5_start >= 0 else ""
FIVE_SIZING = FOUR_NUMERIC + ("InpRequireProfileMatch",)
for name in FIVE_SIZING:
    check(("| `%s` |" % name) in sec5,
          "D14 section 5's table still accounts for %s" % name)

# ---------------------------------------------------------------- D16
# Section 5 used to be the document that said these inputs are NOT checked. It
# cannot keep saying that, and it cannot quietly become a table that lists the
# new bounds either: the numbers it states have to be the numbers the source
# enforces, or the document is a second, drifting copy of the gate.
for name in ("InpWeakRiskMultiplier", "InpModerateRiskMultiplier",
             "InpStrongRiskMultiplier"):
    check(("| `%s` | `0.00`" % name) in sec5,
          "D16 section 5 states the 0.00..1.00 bound for %s" % name)
# Scoped to the table row: the prose paragraph below the table also names the
# function, so a document-wide search would keep passing after the row itself
# was edited to copy the literal 2.00.
agg_row = next((ln for ln in sec5.split("\n")
                if ln.startswith("| `InpMaxAggregateRiskPercent` |")), "")
check(agg_row.startswith("| `InpMaxAggregateRiskPercent` | `0.00`"),
      "D16 section 5's table row gives InpMaxAggregateRiskPercent a 0.00 floor")
check("HardMaxAggregateRiskPercent()" in agg_row,
      "D16 that row states the ceiling by naming the function that supplies it, "
      "not by copying 2.00")
check("| `InpRequireProfileMatch` |" in sec5 and "bool" in sec5,
      "D16 section 5 still explains why the bool has no range to fail")
check("no attach-time validation" not in sec5 and "| none |" not in sec5,
      "D16 section 5 no longer claims these inputs are unchecked at attach")

check(":4506-4512" in ea_doc and "InpRiskPercent<0.0" in ea_lines[4505]
      and "INIT_PARAMETERS_INCORRECT" in ea_lines[4510],
      "D14 the :4506-4512 citation still lands on the risk-input rejection")
check(":4523-4540" in ea_doc and "AUD-06" in ea_lines[4522]
      and "INIT_PARAMETERS_INCORRECT" in ea_lines[4538],
      "D14 the :4523-4540 citation still lands on the AUD-06 session check")

# ---------------------------------------------------------------- D15
# The sizing inputs are now refused at attach instead of being clamped at use.
# The point of this block is not "a check exists" - it is that the check asks
# for the SAME numbers the enforcement applies. A validation that invented its
# own bound would be worse than none, because "accepted at attach" and "clamped
# at use" would disagree in a way the operator could not predict.
oninit_src = "\n".join(ea_lines[oninit_start - 1:oninit_end])
check("HardMaxAggregateRiskPercent()" in oninit_src,
      "D15 the aggregate bound is asked of HardMaxAggregateRiskPercent(), not "
      "restated as a literal that can drift from the enforcement")
check(re.search(r"InpMaxAggregateRiskPercent>HardMaxAggregateRiskPercent\(\)",
                oninit_src) is not None,
      "D15 InpMaxAggregateRiskPercent is refused above the HARD aggregate bound")
for name in ("InpWeakRiskMultiplier", "InpModerateRiskMultiplier",
             "InpStrongRiskMultiplier"):
    check(re.search(re.escape(name) + r"<0\.0", oninit_src) is not None
          and re.search(re.escape(name) + r">1\.0", oninit_src) is not None,
          "D15 %s is refused outside 0.00..1.00" % name)

# The other side of the same contract: CalcLots() still caps a class multiplier
# at 1.0, and 1.0 is the same number the attach now refuses to exceed.
calc_start = 0
for n, ln in enumerate(ea_lines, 1):
    if ln.startswith("double CalcLots("):
        calc_start = n
        break
calc_src = "\n".join(ea_lines[calc_start - 1:calc_start + 30]) if calc_start else ""
check("if(class_mult>1.0) class_mult=1.0;" in calc_src,
      "D15 CalcLots() still caps a class multiplier at 1.0 - the same bound the "
      "attach now enforces, so nothing is silently resized any more")
check("if(class_mult<=0.0)" in calc_src,
      "D15 a 0.00 multiplier still means that class is not executed, which is "
      "why 0.00 stays legal at attach")
check("if(v > HardMaxAggregateRiskPercent()) v = HardMaxAggregateRiskPercent();"
      in "\n".join(ea_lines),
      "D15 EffectiveAggregateRiskPct() still caps at the same HARD bound")

# The refusal has to say what was wrong and name the values it was given, or the
# operator sees INIT_PARAMETERS_INCORRECT with no cause - the AUD-06 lesson.
siz_block = oninit_src[oninit_src.find("sizing inputs out of range"):]
siz_block = siz_block[:siz_block.find("INIT_PARAMETERS_INCORRECT")]
check("sizing inputs out of range" in oninit_src,
      "D15 the refusal names the problem, not just the verdict")
check(all(("DoubleToString(%s,2)" % n) in siz_block for n in FOUR_NUMERIC),
      "D15 the refusal prints every value it was given")
check("0.00 stays legal" in siz_block,
      "D15 the refusal says that zero is still allowed, so it does not read as "
      "a new restriction on the OFF settings")

# The message is worthless unless the branch actually refuses. Scoped to the
# brace-matched block: a document-wide search finds INIT_PARAMETERS_INCORRECT in
# the neighbouring checks and passes even when this one returns INIT_SUCCEEDED.
siz_start = next((n for n in range(oninit_start, oninit_end + 1)
                  if ea_lines[n - 1].strip().startswith("if(InpWeakRiskMultiplier<0.0")), 0)
siz_end, depth, seen = 0, 0, False
if siz_start:
    for n in range(siz_start, oninit_end + 1):
        depth += ea_lines[n - 1].count("{") - ea_lines[n - 1].count("}")
        if "{" in ea_lines[n - 1]:
            seen = True
        if seen and depth <= 0:
            siz_end = n
            break
siz_src = "\n".join(ea_lines[siz_start - 1:siz_end]) if siz_start else ""
check(siz_start > 0 and siz_end > siz_start,
      "D15 the sizing check located as one brace-matched block (:4564-4582 "
      "shape) rather than found by text")
check("return INIT_PARAMETERS_INCORRECT;" in siz_src,
      "D15 that block ends by refusing the attach, not by printing and carrying "
      "on")
check("INIT_SUCCEEDED" not in siz_src,
      "D15 and it never answers the bad input with INIT_SUCCEEDED")

print("=" * 60)
TOTAL = ea.count("\n")
print("AUDIT-EX1 execution-safety checks: %d checks, failures: %d" % (CHECKS[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  failed: " + f)
    raise SystemExit(1)
print("All execution-safety contracts hold. This is a source contract: it does not")
print("prove MetaEditor compiles the file, and it is not a backtest. Press F7.")
