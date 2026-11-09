#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WHY-NO-TRADES - read an MT5 journal and name the blocker, in order.

WHY THIS EXISTS
---------------
"No trades" has (at least) eleven distinct causes in this system, and they look
identical from the chart: a flat equity line. Operator diagnosis therefore
becomes guesswork - and the most common reaction to guesswork is to loosen a
gate, which is the one action that makes a silent system dangerous instead of
merely quiet.

Two independent questions have to be answered, in this order:

  1. COULD it trade?   The EA ships inert and carries three breakers. An account
     that is down 2.6% can be perfectly healthy code that is refusing by design.
     Resetting those breakers to "get some trades" is the worst possible reading
     of "it does not open trades".
  2. DID it have anything to trade?   The indicator publishes nothing until its
     gate chain produces a CORE setup. Data that is not loaded (terminal error
     4806 on a higher timeframe) starves the eighth pillar before any gate is
     consulted.

So the tool reports BLOCKERS (it cannot send) separately from CAUSES (it had
nothing to send) and from NOISE (events that look alarming and are not). It
never edits anything, never recommends lowering a threshold, and never says
"all good" when it simply did not recognise the log.

WHAT IT IS NOT
--------------
  * Not a compiler and not a terminal. It parses text that MT5 wrote.
  * Not a substitute for the panel's NEEDS row: when the journal names no cause,
    the indicator's own audit (`InpGateAuditLogEveryBars>0`) is the next step.
  * Not financial advice.

USAGE
  python3 tools/why_no_trades.py --log "/path/to/Experts.log"
  python3 tools/why_no_trades.py --log journal.txt --json out/diagnosis.json

Exit codes: 0 = at least one finding, 3 = nothing recognised (not "fine"),
2 = bad input.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

# MT5's HTML export escapes these; a pasted journal carries them through.
ENTITIES = (("&gt;", ">"), ("&lt;", "<"), ("&quot;", '"'), ("&#39;", "'"),
            ("&amp;", "&"))

SEVERITY_ORDER = {"BLOCKER": 0, "CAUSE": 1, "WARNING": 2, "NOISE": 3}

NUM = r"(-?\d+(?:[.,]\d+)?)"


def unescape(text: str) -> str:
    for src, dst in ENTITIES:
        text = text.replace(src, dst)
    return text


def to_f(value):
    """MT5 prints money with a dot; locale exports use space groups or commas.

    "1 234.56", "1\u00a0234,56" and "1234.56" are all the same number. A value
    that cannot be read returns None: quoting a silent 0.0 as evidence would be
    worse than admitting the field was not understood.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for space in (" ", "\u00a0", "\u202f", "'"):
        text = text.replace(space, "")
    if "," in text and "." in text:
        text = text.replace(",", "")          # 1,234.56 -> 1234.56
    elif "," in text:
        text = text.replace(",", ".")         # 58,11    -> 58.11
    try:
        return float(text)
    except ValueError:
        return None


def read_log(path: str) -> list:
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        raw = fh.read()
    lines = [unescape(l.rstrip("\r\n")) for l in raw.splitlines()]
    return [l for l in lines if l.strip()]


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

EVIDENCE_MAX = 240


def finding(fid, severity, title, evidence, detail, action):
    """One finding. The evidence is one readable line, never a 600-char dump."""
    text = (evidence or "(no line)").strip().replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    if len(text) > EVIDENCE_MAX:
        text = text[:EVIDENCE_MAX - 1] + "\u2026"
    return {"id": fid, "severity": severity, "title": title,
            "evidence": text, "detail": detail, "action": action}


def first_line(lines, pattern):
    rx = re.compile(pattern)
    for line in lines:
        m = rx.search(line)
        if m:
            return line.strip(), m
    return None, None


GUARD_SNIPPET = re.compile(r"(?:GUARD|day guard RESTORED|BREAKER_STATE)[^|]*")


def snippet(line, pattern=None, width=190):
    """A readable slice of a log line, never the whole 600-character heartbeat.

    The heartbeat carries five things in one line; quoting all of it as
    'evidence' makes a report nobody scans.
    """
    if line is None:
        return "(no line)"
    if pattern is not None:
        m = re.search(pattern, line)
        if m:
            text = m.group(0)
            return text if len(text) <= width else text[:width - 1] + "\u2026"
    return line.strip() if len(line) <= width else line.strip()[:width - 1] + "\u2026"


def parse_guard(line):
    """Pull the numbers out of one heartbeat GUARD segment."""
    out = {}
    for key in ("day_base", "sess_base", "bal", "eq", "floor"):
        m = re.search(r"\b%s=%s" % (key, NUM), line)
        if m:
            out[key] = to_f(m.group(1))
    m = re.search(r"daily_dd=%s%%/(%s|money|DISABLED)%%?" % (NUM, NUM), line)
    if m:
        out["daily_dd_pct"] = to_f(m.group(1))
        out["daily_cap"] = m.group(2)
    m = re.search(r"loss_money=%s/%s" % (NUM, NUM), line)
    if m:
        out["loss_money"] = to_f(m.group(1))
        out["money_cap"] = to_f(m.group(2))
    for flag in ("DAY_BLOCKED", "SESSION_DRAWDOWN_BLOCKED", "CONSEC_LOSS_BLOCKED"):
        if flag in line:
            out[flag] = True
    if " ARMED" in line and not out:
        out["ARMED"] = True
    return out


def diagnose(lines) -> dict:
    findings = []
    seen = set()

    def add(*args):
        f = finding(*args)
        if f["id"] in seen:
            return
        seen.add(f["id"])
        findings.append(f)

    text = "\n".join(lines)

    # ---- 0. is the companion even running? ---------------------------------
    attach = [l for l in lines if "[QSMC_AT]" in l]
    if not attach:
        add("ea-absent", "BLOCKER",
            "There is no [QSMC_AT] line at all: the companion EA is not running",
            lines[0] if lines else "(empty log)",
            "The indicator never executes anything. Without QSMC_AutoTrader "
            "attached and compiled, a flat account is the expected state, not a "
            "strategy result.",
            "Attach QSMC_AutoTrader.ex5 to the SAME chart as nadir2, and press F7 "
            "on both in MetaEditor first.")
        return {"findings": findings, "lines": len(lines), "recognised": bool(findings)}

    # ---- 1. arming state ----------------------------------------------------
    hb, _ = first_line(lines, r"\[QSMC_AT\] heartbeat: ")
    arm, _ = first_line(lines, r"\[QSMC_AT\] (?:state [A-Z ]+|QSMC v6\.\d+ execution companion ON)")
    on_line, _ = first_line(lines, r"execution companion ON")
    if on_line:
        m = re.search(r"\| ([^|]*?) \|", on_line)
        mode = (m.group(1).strip() if m else "")
        if "INERT" in on_line:
            add("armed-off", "BLOCKER",
                "The EA is INERT: InpEnableTrading=false",
                on_line,
                "Shipping default. It will classify signals and send nothing.",
                "Only set InpEnableTrading=true after the dry-run stage in "
                "docs/QSMC_GO_LIVE_RUNBOOK.md. Never as a first step.")
        elif "DRY RUN" in on_line:
            add("dry-run", "WARNING",
                "The EA is in DRY RUN: orders are printed, never sent",
                on_line,
                "This is the intended state for Stage 1. 'DRY RUN' lines in the "
                "journal are the trade plan it would have executed.",
                "If you expected real demo orders, set InpDryRun=false — after "
                "reading the DRY RUN lines and confirming SL/TP/RR are sane.")

    # ---- 2. breakers (COULD it trade) --------------------------------------
    guard_line, _ = first_line(lines, r"GUARD day_base=")
    guard = parse_guard(guard_line) if guard_line else {}
    if guard.get("DAY_BLOCKED"):
        used = guard.get("loss_money")
        cap = guard.get("money_cap")
        detail = "Daily loss budget is exhausted"
        if used is not None and cap:
            detail += (" — %.2f lost against a %.2f USD cap (%.2f%% of the day "
                       "baseline, cap %s%%)" % (used, cap,
                                                guard.get("daily_dd_pct") or 0.0,
                                                guard.get("daily_cap")))
        detail += (". The baseline and the BLOCKED flag are persisted per server "
                   "day on purpose: a reload, a timeframe change or a fresh "
                   "attach does NOT clear them, and clearing them would be a "
                   "decision to trade through the limit.")
        restored, _ = first_line(lines, r"day guard RESTORED")
        add("day-blocked", "BLOCKER",
            "DAY_BLOCKED: today's loss limit has tripped",
            snippet(restored or guard_line, r"(?:GUARD|day guard RESTORED)[^|]*"), detail,
            "Nothing to reset: the day guard clears itself when the server date "
            "rolls. If you believe the baseline is stale (see the 2026-11-01 "
            "incident), run MQL5/Scripts/QSMC_ResetGuards.mq5 in dry-run, read "
            "the list, then apply — never mid-day to 'get trades'.")

    if guard.get("SESSION_DRAWDOWN_BLOCKED"):
        base = guard.get("sess_base")
        eq = guard.get("eq")
        detail = ("The account-drawdown breaker tripped earlier and stayed "
                  "tripped: it is persisted and requires a conscious reset.")
        if base and eq:
            detail += (" Session baseline %.2f, equity %.2f (%.2f%% down)."
                       % (base, eq, 100.0 * (base - eq) / base))
        add("session-blocked", "BLOCKER",
            "SESSION_DRAWDOWN_BLOCKED: the account drawdown breaker is latched",
            snippet(guard_line, r"GUARD[^|]*"), detail,
            "Review the account first: two breakers are telling you the same "
            "thing. If you accept the reset after review, use "
            "QSMC_ResetGuards.mq5 (dry-run → apply) or one attach with "
            "InpResetBreakersAtInit=true, then set it back to false.")
    if guard.get("CONSEC_LOSS_BLOCKED"):
        add("streak-blocked", "BLOCKER",
            "CONSEC_LOSS_BLOCKED: the consecutive-loss breaker is latched",
            snippet(guard_line, r"GUARD[^|]*"),
            "InpStopAfterConsecLoss losing closes in a row; it persists across "
            "reloads by design.",
            "Same reset path as the session breaker, and the same question: has "
            "something about the market or the settings changed since the streak?")

    # ---- 3. signal starvation (DID it have anything to trade) -------------
    zero, m_zero = first_line(lines, r"CORE signals in last %s closed bars: 0" % NUM)
    verdict_line, m_verdict = first_line(lines, r"indicator verdict: ([A-Z_]+)")
    verdict = m_verdict.group(1) if m_verdict else None
    look = int(to_f(m_zero.group(1))) if m_zero else None

    health = {}
    visual_lines = set()
    rx_health = re.compile(r"\[SniperDataHealth\](?: role=(ROLE_[A-Z_]+))?"
                           r"[^|]*?([A-Za-z0-9_]+) not ready \(copied "
                           + NUM + "/" + NUM + r", terminal_error (\d+)\)")
    for line in lines:
        m = rx_health.search(line)
        if not m:
            continue
        role = m.group(1) or "ROLE_VISUAL"
        tag = m.group(2)
        if role != "ROLE_EA_READER":
            visual_lines.add(tag)
        if health.get(tag) != "ROLE_EA_READER":
            health[tag] = role
    if health:
        starving = sorted(t for t, r in health.items() if r == "ROLE_EA_READER")
        visual = sorted(t for t in visual_lines if health.get(t) != "ROLE_EA_READER")
        detail = ("terminal_error 4806 means the requested history was not found "
                  "on the server. While an EA-reader feed is missing, the MTF "
                  "Sniper pillar (25%% of the confluence weight) cannot vote, so "
                  "the gate chain cannot complete and no signal reaches the EA - "
                  "regardless of its inputs. %d EA-reader feed(s) down, %d "
                  "visual-only feed(s) down." % (len(starving), len(visual)))
        if not starving:
            detail += (" Only panel feeds are down here: the chart looks poorer "
                       "than it is, but this is NOT why there is no trade.")
        title = "MTF data missing: " + (", ".join(starving[:4]) or ", ".join(visual[:4]))
        extra = max(len(starving), len(visual)) - 4
        if extra > 0:
            title += " (+%d more)" % extra
        ev = snippet(next(l for l in lines if "not ready (copied" in l),
                     None, width=200)
        add("mtf-history", "CAUSE", title, ev, detail,
            "Open the missing timeframes on this symbol (W1, D1, H4, H1, M30, "
            "M5) and scroll/Home until their history downloads; raise "
            "Tools -> Options -> Charts -> 'Max bars in chart'; confirm the "
            "terminal is connected. Wait for '[SniperDataHealth] ... READY' or "
            "for the 'still incomplete' WARNING, then watch the funnel move. "
            "Do NOT touch a gate before this is resolved.")

    if zero:
        detail = ("The indicator published no CORE setup in the last %s closed "
                  "bars. The EA is healthy and has nothing to execute — this is "
                  "the transport saying so." % (look if look else "200"))
        if verdict and verdict not in ("CORE_PUBLISHED",):
            detail += (" Last blocker reported by the indicator: %s." % verdict)
        add("no-signal", "CAUSE",
            "Zero CORE signals%s" % ((" — indicator verdict %s" % verdict)
                                     if verdict else ""),
            snippet(zero, r"CORE signals[^|]*"), detail,
            "Read the chart panel's NEEDS row (it names the same blocker), or "
            "set InpGateAuditLogEveryBars>0 in nadir2 for the literal reason. "
            "Remember: a .set loaded on the chart does NOT change what the EA "
            "sees — the EA reads the indicator's COMPILED defaults.")

    # ---- 4. profile divergence --------------------------------------------
    prof, m_prof = first_line(lines, r"GATE PROFILE: (\w+) \| .* confidence (\d+) \| "
                                     r"reliability (\d+) \| RR1 ([0-9.]+)")
    if prof and "vs" in text:
        add("profile-divergence", "WARNING",
            "The EA reads COMPILED indicator defaults, not the chart preset",
            snippet(prof, r"GATE PROFILE[^\n]*"), 
            "The attach line lists inputs whose divergence changes what the EA "
            "can ever receive, e.g. InpGateProfile (compiled STRICT 75/80/1.50R "
            "vs PRACTICAL 60/60/1.20R). Tuning the visible panel produces a "
            "different system from the one being executed.",
            "Either run the indicator with its defaults, or change the DEFAULTS "
            "in nadir2.mq5 and recompile (docs/DEMO_SETUP_AR_FULL.md §4).")

    # ---- 5. execution refusals (should be rare) ---------------------------
    refused, m_ref = first_line(lines, r"\[QSMC_AT\] REFUSED to send .*: (.+)$")
    if refused:
        add("env-refused", "CAUSE",
            "The EA refused to send: %s" % (m_ref.group(1).strip() if m_ref else "?"),
            refused,
            "This is the environment gate (Algo Trading off, symbol close-only, "
            "real account with InpDemoOnly=true, or InpRealAccountConfirm not "
            "matching the login).",
            "Fix the named condition. Do not disable the gate.")

    failed, m_fail = first_line(lines, r"ORDER FAILED .* retcode=%s" % NUM)
    if failed:
        rc = int(to_f(m_fail.group(1)) or 0)
        add("order-failed", "CAUSE",
            "An order reached the server and was rejected (retcode %d)" % rc,
            failed,
            "Permanent retcodes abandon the signal; transient ones are retried "
            "on the next poll and then abandoned after InpOrderRetryMax.",
            "Read the retcode text on the same line. 10016 = invalid stops "
            "(broker stops/freeze level), 10018 = market closed, 10019 = no "
            "money, 10027 = Algo Trading disabled on the server side.")

    # ---- 6. wiring --------------------------------------------------------
    mism, _ = first_line(lines, r"INSTANCE MISMATCH")
    if mism:
        add("instance-mismatch", "BLOCKER",
            "INSTANCE MISMATCH: two active instances disagree for the same scope",
            mism,
            "The diagnostic bridge keys on account/symbol/timeframe/input-hash. "
            "A mismatch means the EA and the panel are not looking at the same "
            "indicator build or inputs.",
            "Re-attach both from the same compiled build; verify the "
            "[QSMC_INSTANCE] input_hash lines match.")
    nodiag, _ = first_line(lines, r"no diagnostic record")
    if nodiag:
        add("no-diag", "WARNING",
            "The EA has no diagnostic record for this symbol/timeframe",
            nodiag,
            "Usually a symbol/timeframe/instance mismatch, or an older indicator "
            "build without ABI v2.",
            "Confirm both programs are on the same chart, symbol and timeframe, "
            "and that nadir2 was compiled from this source tree.")

    # ---- 7. noise (real, expected, worth naming so it stops worrying) -----
    rejects = [l for l in lines if "[QSMC_ZONE_REJECT]" in l]
    if rejects:
        add("zone-reject", "NOISE",
            "%d zone rejection(s) — normal hygiene, not the blocker" % len(rejects),
            rejects[0],
            "Zones expire by age and distance. A rejected FVG cannot produce a "
            "signal, but its rejection is the filter working, not failing.",
            "Nothing. Look at the last one's reason to confirm it says "
            "'expired distant zone'.")

    started, _ = first_line(lines, r"Quantum SMC .* v[\d.]+ (?:PRODUCTION BUILD|Stopped)")
    if started:
        add("banner", "NOISE",
            "Build banner seen: the indicator is loaded and initialising", started,
            "Self-tests print PASS lines; any 'self-test: FAIL' would be a real "
            "finding (this tool looks for it separately).", "Nothing.")
    selftest, _ = first_line(lines, r"self-?test[: ]+FAIL")
    if selftest:
        add("selftest-fail", "BLOCKER",
            "An indicator self-test reported FAIL", selftest,
            "A failing self-test means the internal contracts are broken in this "
            "build; signals from it are not trustworthy.",
            "Do not trade this build. Capture the full self-test block and "
            "re-compile from a known-good source.")

    findings = [f for _, f in sorted(
        enumerate(findings),
        key=lambda pair: (SEVERITY_ORDER.get(pair[1]["severity"], 9), pair[0]))]
    return {"findings": findings, "lines": len(lines),
            "recognised": bool(findings),
            "guard": guard, "verdict": verdict,
            "mtf_missing": sorted(health)}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(result) -> str:
    out = []
    findings = result["findings"]
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    out.append("QSMC 'why no trades' — %d finding(s): %s"
               % (len(findings), ", ".join("%d %s" % (v, k.lower())
                                           for k, v in sorted(
                                               counts.items(),
                                               key=lambda kv: SEVERITY_ORDER[kv[0]]))
               or "none"))
    out.append("")
    if not findings:
        out.append("NOTHING RECOGNISED. This is not the same as 'healthy': the log")
        out.append("may be truncated, from another build, or from a run that never")
        out.append("started. Capture the Experts tab from the moment of attach.")
        return "\n".join(out)

    blockers = [f for f in findings if f["severity"] == "BLOCKER"]
    causes = [f for f in findings if f["severity"] == "CAUSE"]
    if blockers and causes:
        out.append("TWO INDEPENDENT PROBLEMS. Fixing one will not produce a trade:")
        out.append("  * the EA cannot send (%d blocker(s)), and" % len(blockers))
        out.append("  * it has nothing to send (%d cause(s))." % len(causes))
        out.append("")

    for i, f in enumerate(findings, 1):
        out.append("[%d] %-7s %s" % (i, f["severity"], f["title"]))
        out.append("    evidence: %s" % f["evidence"].strip()[:EVIDENCE_MAX])
        for j, wrap in enumerate(_wrap(f["detail"], 74)):
            out.append(("    why:      " if j == 0 else "              ") + wrap)
        for j, wrap in enumerate(_wrap(f["action"], 74)):
            out.append(("    action:   " if j == 0 else "              ") + wrap)
        out.append("")
    if blockers and causes:
        out.append("Order of work: fix the CAUSE (why there is no signal) while the")
        out.append("BLOCKERs stand. The day guard clears itself at the next server date;")
        out.append("the session breaker needs a deliberate reset AFTER review. Resetting")
        out.append("them first would remove the limit that protects an account which")
        out.append("still has nothing to trade.")
    return "\n".join(out)


def _wrap(text, width):
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Classify an MT5 journal into blockers / causes / noise.")
    ap.add_argument("--log", required=True, help="Experts or Journal log file")
    ap.add_argument("--json", default=None, help="write the result as JSON here")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.log):
        print("ERROR: no such file: %s" % args.log, file=sys.stderr)
        return 2
    try:
        result = diagnose(read_log(args.log))
    except (OSError, ValueError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    print(render(result))
    if args.json:
        with io.open(args.json, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("\njson: %s" % args.json)
    return 0 if result["recognised"] else 3


if __name__ == "__main__":
    sys.exit(main())
