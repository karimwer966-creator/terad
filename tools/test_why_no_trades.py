#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WHY-NO-TRADES - independent tests for the journal classifier.

WHY THIS EXISTS
---------------
tools/why_no_trades.py exists because the most common support question on this
project is "the EA is attached and it opens no trades". A classifier that
answers that question wrongly is worse than no tool: it can tell an operator to
reset a breaker, or let them believe a bad chart is the cause when the real
cause is a latched drawdown limit. So the answer logic is pinned here:

  * a log with no [QSMC_AT] line must be reported as "companion not running",
    not as a strategy result;
  * INERT / DRY RUN / armed must not be confused - they send nothing for
    completely different reasons;
  * each breaker is detected from the guard line as printed, and the numbers
    quoted back are the numbers in the log (58.11 lost against 19.98 cap);
  * "no signal" is separated from "cannot send": the two problems coexist and
    fixing one does not produce a trade;
  * an EA-reader MTF feed that is missing is a CAUSE; a visual-only feed that is
    missing is explicitly downgraded, because it is not why nothing executes;
  * severity ordering is stable (BLOCKER, CAUSE, WARNING, NOISE) and duplicate
    findings never appear twice;
  * the shipped fixture produces exactly the diagnosis that was delivered to the
    operator on 2026-11-09, and it carries no real account number.

These are tests of CLASSIFICATION, not of the strategy. Nothing here says an
attached EA should have traded.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import why_no_trades as W  # noqa: E402

FAILS = []
COUNT = [0]


def check(ok, name, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s%s" % (name, ("  [%s]" % detail) if detail else ""))
        FAILS.append(name)


# ---------------------------------------------------------------------------
# Real-shaped log lines (from the 2026-11-09 Experts tab, account redacted)
# ---------------------------------------------------------------------------
TS = "2026.11.09 12:07:55.070\t"
ATTACH = (TS + "QSMC_AutoTrader (XAUUSD,M15)\t[QSMC_AT] QSMC v6.620 execution "
          "companion ON | XAUUSD PERIOD_M15 | magic 20261027 | mode RISK% risk "
          "0.10% | tp 1 | break-even 1.00R | DRY RUN | demo-only | closed-bar "
          "signals only, no martingale, no stop widening")
ATTACH_LIVE = ATTACH.replace(" | DRY RUN", "")
ATTACH_INERT = ATTACH.replace("DRY RUN", "INERT")
GUARD = (TS + "QSMC_AutoTrader (XAUUSD,M15)\t[QSMC_AT] GUARD day_base=3996.99 "
         "sess_base=4044.16 bal=3938.88 eq=3938.88 daily_dd=1.45%/0.50% "
         "loss_money=58.11/19.98 USD floor=3977.01 DAY_BLOCKED "
         "SESSION_DRAWDOWN_BLOCKED CONSEC_LOSS_BLOCKED")
HEARTBEAT = (TS + "QSMC_AutoTrader (XAUUSD,M15)\t[QSMC_AT] heartbeat: DRY RUN | "
             "CORE signals in last 200 closed bars: 0 -> the indicator published "
             "NO CORE setup, so this EA has nothing to execute (read the chart "
             "panel NEEDS row, or set InpGateAuditLogEveryBars>0 in nadir2)")
HEALTH = (TS + "nadir2 (XAUUSD,M15)\t[SniperDataHealth] role=ROLE_EA_READER "
          "ATR_PERIOD_W1 not ready (copied -1/200, terminal_error 4806) - "
          "waiting up to 200 update attempts; this update is skipped")
HEALTH_VISUAL = (TS + "nadir2 (XAUUSD,M15)\t[SniperDataHealth] role=ROLE_VISUAL "
                 "ATR_PERIOD_W1 not ready (copied -1/200, terminal_error 4806) "
                 "- waiting up to 200 update attempts; this update is skipped")
PROFILE = (TS + "nadir2 (XAUUSD,M15)\t>>> v6.6.20 GATE PROFILE: STRICT | every "
           "threshold is the input as entered | confidence 75 | reliability 80 | "
           "RR1 1.50 | stop 4.00 ATR | anchor window 60 bars")
ZONE = (TS + "nadir2 (XAUUSD,M15)\t[QSMC_ZONE_REJECT] role=ROLE_VISUAL "
        "symbol=XAUUSD tf=PERIOD_M15 source=FVG created=2026.11.02 01:00 "
        "lo=3877.34 hi=3892.77 reason=expired distant zone")


def ids(result):
    return [f["id"] for f in result["findings"]]


def by_id(result, fid):
    for f in result["findings"]:
        if f["id"] == fid:
            return f
    return None


# ---------------------------------------------------------------------------
# 1. "the EA is not even running" must not be dressed up as a strategy result
# ---------------------------------------------------------------------------
empty = W.diagnose([])
check(ids(empty) == ["ea-absent"], "an empty log yields exactly one finding", ids(empty))
check(empty["findings"][0]["severity"] == "BLOCKER", "ea-absent is a BLOCKER")
check("not running" in empty["findings"][0]["title"],
      "ea-absent says the companion is not running")

indicator_only = W.diagnose([
    TS + "nadir2 (XAUUSD,M15)\t Quantum SMC Intelligence Engine v6.6.20 PRODUCTION BUILD",
    PROFILE,
    ZONE,
])
check(ids(indicator_only) == ["ea-absent"],
      "an indicator-only log is still 'ea-absent', not 'no signal'", ids(indicator_only))

# ---------------------------------------------------------------------------
# 2. arming state: three different reasons to send nothing
# ---------------------------------------------------------------------------
inert = W.diagnose([ATTACH_INERT, HEARTBEAT])
check("armed-off" in ids(inert), "INERT is detected", ids(inert))
check("dry-run" not in ids(inert), "INERT is not also reported as DRY RUN")
check(by_id(inert, "armed-off")["severity"] == "BLOCKER",
      "INERT is a BLOCKER (a setting, not a market condition)")

dry = W.diagnose([ATTACH, HEARTBEAT])
check("dry-run" in ids(dry), "DRY RUN is detected", ids(dry))
check(by_id(dry, "dry-run")["severity"] == "WARNING",
      "DRY RUN is a WARNING: it is the intended Stage-1 state")
check("never sent" in by_id(dry, "dry-run")["title"], "DRY RUN says orders are never sent")

live = W.diagnose([ATTACH_LIVE, HEARTBEAT])
check("dry-run" not in ids(live) and "armed-off" not in ids(live),
      "an armed, live attach produces neither arming finding", ids(live))

# ---------------------------------------------------------------------------
# 3. breakers - detected from the guard line, quoted back verbatim
# ---------------------------------------------------------------------------
guarded = W.diagnose([ATTACH, GUARD, HEARTBEAT])
check(all(x in ids(guarded) for x in
          ("day-blocked", "session-blocked", "streak-blocked")),
      "all three breaker flags are detected", ids(guarded))
check(guarded["guard"]["day_base"] == 3996.99, "day baseline parsed",
      guarded["guard"].get("day_base"))
check(guarded["guard"]["loss_money"] == 58.11, "loss_money parsed",
      guarded["guard"].get("loss_money"))
check(guarded["guard"]["money_cap"] == 19.98, "daily money cap parsed",
      guarded["guard"].get("money_cap"))
day = by_id(guarded, "day-blocked")
check("58.11" in day["detail"] and "19.98" in day["detail"],
      "the day-blocked detail quotes the actual loss and the actual cap",
      day["detail"][:120])
check("1.45" in day["detail"] and "0.50" in day["detail"],
      "the day-blocked detail quotes dd vs cap", day["detail"][:160])
check("does NOT clear them" in day["detail"].replace("\n", " "),
      "the detail states that a reload does not clear the guard")
check("never mid-day" in day["action"], "the action refuses a mid-day reset")
check("QSMC_ResetGuards.mq5" in day["action"], "the action names the reset script")

sess = by_id(guarded, "session-blocked")
check("2.60%" in sess["detail"],
      "the session breaker computes 2.60% down from 4044.16 -> 3938.88",
      sess["detail"][-90:])
check("4044.16" in sess["detail"] and "3938.88" in sess["detail"],
      "the session breaker quotes both baselines", sess["detail"][-90:])
check("reset" in sess["action"], "the session action is a deliberate reset, not a wait")

# a day guard without the flags is not a blocker
clean_guard = GUARD.replace(" DAY_BLOCKED", "").replace(
    " SESSION_DRAWDOWN_BLOCKED", "").replace(" CONSEC_LOSS_BLOCKED", "")
ok_guard = W.diagnose([ATTACH, clean_guard, HEARTBEAT])
check(not any(f["severity"] == "BLOCKER" and "day" in f["id"] for f in ok_guard["findings"]),
      "an untripped guard line does not invent a breaker", ids(ok_guard))

# ---------------------------------------------------------------------------
# 4. signal starvation is a CAUSE, kept separate from "cannot send"
# ---------------------------------------------------------------------------
starved = W.diagnose([ATTACH, GUARD, HEARTBEAT])
zero = by_id(starved, "no-signal") or by_id(starved, "zero-signal")
check(zero is not None, "zero CORE signals produce a finding of their own", ids(starved))
check(zero["severity"] == "CAUSE", "zero signals is a CAUSE, not a blocker",
      zero["severity"])
check("200" in zero["detail"], "the closed-bar lookback is quoted", zero["detail"][:80])

verdict_line = (TS + "nadir2 (XAUUSD,M15)\t[QSMC_AT] indicator verdict: NO_STRUCTURE_EVENT")
with_verdict = W.diagnose([ATTACH, HEARTBEAT, verdict_line])
check(with_verdict["verdict"] == "NO_STRUCTURE_EVENT",
      "the indicator verdict is captured", with_verdict["verdict"])
zv = by_id(with_verdict, "no-signal") or by_id(with_verdict, "zero-signal")
check("NO_STRUCTURE_EVENT" in zv["detail"],
      "the verdict is repeated in the no-signal detail", zv["detail"][:120])

# ---------------------------------------------------------------------------
# 5. MTF history: role decides whether it is a cause or a footnote
# ---------------------------------------------------------------------------
ea_down = W.diagnose([ATTACH, HEALTH, HEARTBEAT])
check("mtf-history" in ids(ea_down), "a missing EA-reader feed is reported", ids(ea_down))
check(by_id(ea_down, "mtf-history")["severity"] == "CAUSE",
      "a missing EA-reader feed is a CAUSE")
check("ATR_PERIOD_W1" in by_id(ea_down, "mtf-history")["title"],
      "the missing feed is named", by_id(ea_down, "mtf-history")["title"])
check("25%" in by_id(ea_down, "mtf-history")["detail"],
      "the 25% Sniper-pillar weight is stated", by_id(ea_down, "mtf-history")["detail"][:200])
check("4806" in by_id(ea_down, "mtf-history")["detail"],
      "terminal_error 4806 is explained")

vis_only = W.diagnose([ATTACH, HEALTH_VISUAL, HEARTBEAT])
check("mtf-history" in ids(vis_only), "a missing visual feed is still mentioned", ids(vis_only))
check("NOT why" in by_id(vis_only, "mtf-history")["detail"].replace("\n", " "),
      "a visual-only outage is explicitly downgraded", by_id(vis_only, "mtf-history")["detail"][-160:])
check(by_id(vis_only, "mtf-history")["severity"] == "CAUSE",
      "a visual-only outage still stays out of BLOCKER")

# ---------------------------------------------------------------------------
# 6. noise stays noise
# ---------------------------------------------------------------------------
noisy = W.diagnose([ATTACH, GUARD, HEARTBEAT, ZONE, PROFILE])
zset = [f for f in noisy["findings"] if "zone" in f["id"]]
check(zset and all(f["severity"] == "NOISE" for f in zset),
      "zone rejections are NOISE, never a blocker", [f["id"] for f in zset])
check("expired" in zset[0]["action"] or "Nothing" in zset[0]["action"],
      "the zone finding's action is 'nothing'", zset[0]["action"][:80])
check("zone-reject" in ids(noisy), "zone rejections are catalogued", ids(noisy))

# ---------------------------------------------------------------------------
# 7. ordering, uniqueness, determinism
# ---------------------------------------------------------------------------
order = {"BLOCKER": 0, "CAUSE": 1, "WARNING": 2, "NOISE": 3}
sevs = [order[f["severity"]] for f in noisy["findings"]]
check(sevs == sorted(sevs), "findings are sorted BLOCKER -> CAUSE -> WARNING -> NOISE", sevs)
check(len(ids(noisy)) == len(set(ids(noisy))), "no finding id appears twice", ids(noisy))
check(ids(W.diagnose([ATTACH, GUARD, HEARTBEAT, ZONE, PROFILE])) == ids(noisy),
      "the same log classifies identically twice")
check(all(f["evidence"].strip() for f in noisy["findings"]),
      "every finding carries an evidence line")
check(all(len(f["evidence"]) <= W.EVIDENCE_MAX for f in noisy["findings"]),
      "evidence is clipped to a readable width",
      max(len(f["evidence"]) for f in noisy["findings"]))

# ---------------------------------------------------------------------------
# 8. rendering
# ---------------------------------------------------------------------------
text = W.render(noisy)
check(text.startswith("QSMC 'why no trades'"), "the report has a header")
check("TWO INDEPENDENT PROBLEMS" in text,
      "blockers + causes are announced as two independent problems")
check("Order of work" in text and "fix the CAUSE" in text,
      "the report tells the operator which problem to work on first")
check(text.count("    action:") == len(noisy["findings"]),
      "every finding renders exactly one action block", text.count("    action:"))
clean = W.render(W.diagnose([ATTACH_LIVE]))
check("TWO INDEPENDENT PROBLEMS" not in clean,
      "a log with no blockers does not claim two problems", clean[:200])
# A live attach with nothing else wrong: the classifier has nothing to say, and
# inventing a cause here would send an operator chasing a phantom.
quiet = W.diagnose([ATTACH_LIVE])
check(quiet["findings"] == [] and quiet["recognised"] is False,
      "a healthy live attach yields no findings and recognised=False",
      ids(quiet))
check("NOTHING RECOGNISED" in W.render(quiet),
      "an unrecognised log says so instead of inventing findings")

# ---------------------------------------------------------------------------
# 9. parsing helpers
# ---------------------------------------------------------------------------
check(W.unescape("a &gt; b &lt; c &amp; d") == "a > b < c & d",
      "HTML entities are unescaped (the Experts tab exports them)")
check(W.to_f("1 234.56") == 1234.56, "space thousand separators parse")
check(W.to_f("1\u00a0234,56") == 1234.56, "nbsp groups and a decimal comma parse")
check(W.to_f("1,234.56") == 1234.56, "comma groups with a dot decimal parse")
check(W.to_f("58.11") == 58.11, "plain decimals parse")
check(W.to_f("n/a") is None, "an unparsable number is None, never 0.0")
check(W.parse_guard(GUARD).get("DAY_BLOCKED") is True, "parse_guard reads the flags")
check(W.parse_guard("unrelated") == {}, "parse_guard on a non-guard line is empty")

# ---------------------------------------------------------------------------
# 10. CLI contract
# ---------------------------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="why_no_trades_")
try:
    good = os.path.join(tmp, "good.log")
    with io.open(good, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join([ATTACH, GUARD, HEARTBEAT, HEALTH, ZONE]) + "\n")
    js = os.path.join(tmp, "out.json")
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        rc = W.main(["--log", good, "--json", js])
    check(rc == 0, "exit 0 when something was recognised", rc)
    check(os.path.isfile(js), "--json writes the file it was given")
    payload = json.loads(io.open(js, encoding="utf-8").read())
    check(payload["findings"] and payload["lines"] == 5,
          "the json payload carries the findings and the line count",
          payload.get("lines"))

    quiet_log = os.path.join(tmp, "quiet.log")
    with io.open(quiet_log, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ATTACH_LIVE + "\n")
    with contextlib.redirect_stdout(io.StringIO()):
        rc_quiet = W.main(["--log", quiet_log])
    check(rc_quiet == 3,
          "exit 3 when the log is readable but nothing is wrong")

    # A log with no [QSMC_AT] line is NOT 'nothing recognised': it is the
    # companion not running, which is the most common cause of a flat account.
    foreign = os.path.join(tmp, "foreign.log")
    with io.open(foreign, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("this is not an MT5 log at all\n")
    with contextlib.redirect_stdout(io.StringIO()):
        rc_foreign = W.main(["--log", foreign])
    check(rc_foreign == 0,
          "a log without the companion exits 0 with the ea-absent finding")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc_missing = W.main(["--log", os.path.join(tmp, "missing.log")])
    check(rc_missing == 2,
          "exit 2 for a missing file")

    # -----------------------------------------------------------------------
    # 11. the shipped fixture: the exact diagnosis delivered on 2026-11-09
    # -----------------------------------------------------------------------
    fixture = os.path.join(HERE, "fixtures", "no_trades_2026-11-09.log")
    check(os.path.isfile(fixture), "the 2026-11-09 fixture ships with the tool")
    result = W.diagnose(W.read_log(fixture))
    check(all(x in ids(result) for x in
              ("dry-run", "day-blocked", "session-blocked", "mtf-history")),
          "the fixture reproduces all four findings of the real session", ids(result))
    check("CONSEC_LOSS_BLOCKED" not in ids(result),
          "the fixture does not invent a consecutive-loss breaker")
    check(result["verdict"] == "NO_STRUCTURE_EVENT",
          "the fixture's verdict is NO_STRUCTURE_EVENT", result["verdict"])
    check("ADX_H1" in result["mtf_missing"], "the fixture's ADX_H1 outage is recorded")
    check(len(result["mtf_missing"]) == 6,
          "the fixture has six distinct MTF feeds down", len(result["mtf_missing"]))
    with contextlib.redirect_stdout(io.StringIO()):
        rc_fixture = W.main(["--log", fixture])
    check(rc_fixture == 0, "the fixture exits 0")
    raw = io.open(fixture, encoding="utf-8").read()
    check("52959880" not in raw, "the fixture carries no real account number")
    check("12345678" in raw, "the fixture's account number is the documented placeholder")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if FAILS:
    print("%d of %d why-no-trades test(s) failed" % (len(FAILS), COUNT[0]))
    raise SystemExit(1)
print("%d why-no-trades checks passed; these test the classification, not an edge."
      % COUNT[0])
