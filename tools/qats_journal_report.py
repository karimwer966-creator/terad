#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QATS-JOURNAL - turn an MT5 Experts journal into a BUY-vs-SELL report.

WHY THIS EXISTS
---------------
"Is the EA seeing both directions?" used to be answered by scrolling a journal.
v1.20 prints a traceable life cycle for every signal:

    [QATS][BUY][DETECTED] / [QATS][SELL][DETECTED]   a setup's core confirmation passed
    [QATS][SIGNAL][SCORED]                            both scores + the outcome, every bar
    [QATS][BLOCK][REASON]                             a risk guard vetoed an eligible signal
    [QATS][EXECUTION][REJECTED]                       the plan / sizing / broker refused it
    [QATS][EXECUTION][APPROVED] / [FILLED]            the order was sent / accepted
    [QATS][GUARD] position ... closed WIN|LOSS|NEUTRAL  the result, from deal history

This tool reads those lines from a real terminal log (Experts tab export, or the
terminal's own logs/YYYYMMDD.log, UTF-16 or UTF-8) or from a simulator log, and
reports - separately for BUY and SELL - signals, executions, every rejection with
its exact reason, win rate, profit factor, expectancy, average planned R:R, the
drawdown seen by the heartbeats, and execution failures. It is the evidence
format for the DEMO forward test: run it on the journal, attach the output.

v1.11 journals (one direction per bar) are recognised too, so an old log can be
quantified with the same tool.

Usage:
    python3 tools/qats_journal_report.py <log> [<log> ...] [--json]

It reports what the journal says. It cannot see orders the journal does not
mention, and it is not proof of profitability.
"""
from __future__ import print_function

import argparse
import collections
import json
import re
import sys

SIDES = ("BUY", "SELL")


def read_lines(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", "replace")
    elif raw[:3] == b"\xef\xbb\xbf":
        text = raw[3:].decode("utf-8", "replace")
    elif len(raw) > 3 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00":
        text = raw.decode("utf-16-le", "replace")
    else:
        text = raw.decode("utf-8", "replace")
    return text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&").splitlines()


def field(s, key, default=""):
    m = re.search(r"(?:^|[\s\[(|])" + re.escape(key) + r"=(\S+)", s)
    return m.group(1) if m else default


def money(text):
    try:
        return float(text.replace("+", ""))
    except ValueError:
        return 0.0


def new_side():
    return {
        "score_sum": 0, "score_max": 0, "bars_score_ge_min": 0, "bars_core_pass": 0,
        "setups_detected": 0, "bars_candidate": 0, "bars_eligible": 0,
        "outcomes": collections.Counter(), "blocked_bar_reasons": collections.Counter(),
        "block_events": collections.Counter(), "rejections": collections.Counter(),
        "approved": 0, "filled": 0, "planned_rr_sum": 0.0,
        "wins": 0, "losses": 0, "neutral": 0, "gross_profit": 0.0, "gross_loss": 0.0, "net": 0.0,
        "entries_v111": 0,
    }


def analyse(lines):
    rep = {
        "versions": [], "symbols": [], "first_time": "", "last_time": "", "qats_lines": 0,
        "bars_scored": 0, "minimum": None, "profile": None, "format": None,
        "sides": {s: new_side() for s in SIDES}, "none_bars": 0, "conflicts": 0,
        "cooldown": [], "exec_fail_lines": 0, "critical_lines": 0, "retries": 0,
        "equity": [], "max_dd_pct_seen": 0.0, "guard_lines": collections.Counter(),
        "deals_v111": [], "longest_run": {"side": "", "bars": 0},
    }
    run_side, run_len = "", 0
    for line in lines:
        i = line.find("[QATS]")
        if i < 0:
            continue
        rep["qats_lines"] += 1
        s = line[i:]
        tm = re.search(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}", line[:i]) or re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}", line[:i])
        if tm:
            if not rep["first_time"]:
                rep["first_time"] = tm.group(0)
            rep["last_time"] = tm.group(0)
        m = re.match(r"\[QATS\] QuantumAutonomousTradingSystem v(\S+) attaching to (\S+)", s)
        if m:
            if m.group(1) not in rep["versions"]:
                rep["versions"].append(m.group(1))
            if m.group(2) not in rep["symbols"]:
                rep["symbols"].append(m.group(2))
            continue
        if s.startswith("[QATS][SIGNAL][SCORED]"):
            rep["format"] = "v1.20 (both directions per bar)"
            rep["bars_scored"] += 1
            rep["minimum"] = int(field(s, "minimum", "0") or 0)
            rep["profile"] = field(s, "profile")
            cand, outcome, reason = field(s, "candidate"), field(s, "outcome"), field(s, "reason")
            for side in SIDES:
                sc = int((field(s, side, "0/100").split("/")[0]) or 0)
                d = rep["sides"][side]
                d["score_sum"] += sc
                d["score_max"] = max(d["score_max"], sc)
                if sc >= rep["minimum"]:
                    d["bars_score_ge_min"] += 1
                if (side + " core=PASS") in s:
                    d["bars_core_pass"] += 1
            if cand in SIDES:
                d = rep["sides"][cand]
                d["bars_candidate"] += 1
                d["outcomes"][outcome] += 1
                if field(s, "eligible") == "yes":
                    d["bars_eligible"] += 1
                if outcome in ("BLOCKED", "REJECTED", "VETOED", "CONFLICT"):
                    d["blocked_bar_reasons"][outcome + ":" + reason] += 1
            else:
                rep["none_bars"] += 1
            side_now = cand if cand in SIDES else ""
            if side_now and side_now == run_side:
                run_len += 1
            else:
                run_side, run_len = side_now, (1 if side_now else 0)
            if run_len > rep["longest_run"]["bars"]:
                rep["longest_run"] = {"side": run_side, "bars": run_len}
            continue
        if s.startswith("[QATS][SIGNAL][CONFLICT]"):
            rep["conflicts"] += 1
            continue
        if s.startswith("[QATS][SIGNAL]"):
            # v1.11: one direction per bar
            rep["format"] = rep["format"] or "v1.11 (ONE direction per bar - the other side was never scored)"
            rep["bars_scored"] += 1
            rep["minimum"] = int(field(s, "minimum", "0") or 0)
            side = field(s, "direction")
            result = field(s, "result")
            if side in SIDES:
                d = rep["sides"][side]
                sc = int(field(s, "score", "0") or 0)
                d["bars_candidate"] += 1
                d["score_sum"] += sc
                d["score_max"] = max(d["score_max"], sc)
                if sc >= rep["minimum"]:
                    d["bars_score_ge_min"] += 1
                d["outcomes"][result] += 1
                if field(s, "eligible") == "yes":
                    d["bars_eligible"] += 1
                    if result != "ACCEPTED":
                        rm = re.search(r"reason=(.*?)(?: \| |$)", s)
                        d["blocked_bar_reasons"][re.sub(r"[\d.]+", "#", rm.group(1) if rm else "?")] += 1
            else:
                rep["none_bars"] += 1
            side_now = side if side in SIDES else ""
            if side_now and side_now == run_side:
                run_len += 1
            else:
                run_side, run_len = side_now, (1 if side_now else 0)
            if run_len > rep["longest_run"]["bars"]:
                rep["longest_run"] = {"side": run_side, "bars": run_len}
            continue
        m = re.match(r"\[QATS\]\[(BUY|SELL)\]\[DETECTED\]", s)
        if m:
            rep["sides"][m.group(1)]["setups_detected"] += 1
            continue
        if s.startswith("[QATS][BLOCK][REASON]"):
            side = field(s, "direction")
            if side in SIDES:
                for code in field(s, "reasons").split(","):
                    if code:
                        rep["sides"][side]["block_events"][code] += 1
            continue
        if s.startswith("[QATS][EXECUTION][REJECTED]"):
            side = field(s, "direction")
            if side in SIDES:
                rm = re.search(r"reason=(.*)$", s)
                rep["sides"][side]["rejections"]["%s: %s" % (field(s, "stage"), re.sub(r"[\d.]+", "#", rm.group(1) if rm else "?"))] += 1
            continue
        if s.startswith("[QATS][EXECUTION][APPROVED]"):
            side = field(s, "direction")
            if side in SIDES:
                rep["sides"][side]["approved"] += 1
                rep["sides"][side]["planned_rr_sum"] += money(field(s, "rr", "0"))
            continue
        if s.startswith("[QATS][EXECUTION][FILLED]"):
            side = field(s, "direction")
            if side in SIDES:
                rep["sides"][side]["filled"] += 1
            continue
        m = re.match(r"\[QATS\]\[GUARD\] position (\d+) (BUY|SELL|NONE) closed (WIN|LOSS|NEUTRAL) net=([-+\d.]+)", s)
        if m:
            side, outcome, net = m.group(2), m.group(3), money(m.group(4))
            if side in SIDES:
                d = rep["sides"][side]
                d["net"] += net
                if outcome == "WIN":
                    d["wins"] += 1
                    d["gross_profit"] += net
                elif outcome == "LOSS":
                    d["losses"] += 1
                    d["gross_loss"] += -net
                else:
                    d["neutral"] += 1
            continue
        if s.startswith("[QATS][COOLDOWN]"):
            rep["cooldown"].append((rep["last_time"], s[len("[QATS][COOLDOWN] "):][:160]))
            continue
        if s.startswith("[QATS][GUARD]"):
            if "consecutive losing closes" in s:
                rep["guard_lines"]["consecutive-loss stand-down started"] += 1
            elif "DAILY LOSS LIMIT HIT" in s:
                rep["guard_lines"]["daily loss limit hit"] += 1
            elif "DRAWDOWN HALT:" in s:
                rep["guard_lines"]["account drawdown halt"] += 1
            continue
        if s.startswith("[QATS][EXEC][FAIL]"):
            rep["exec_fail_lines"] += 1
            continue
        if s.startswith("[QATS][VERIFY][CRITICAL]"):
            rep["critical_lines"] += 1
            continue
        if s.startswith("[QATS][RETRY]"):
            rep["retries"] += 1
            continue
        if s.startswith("[QATS][HB]"):
            try:
                eq = float(field(s, "equity"))
                rep["equity"].append(eq)
            except ValueError:
                pass
            dd = re.search(r"DD=([\d.]+)%", s)
            if dd:
                rep["max_dd_pct_seen"] = max(rep["max_dd_pct_seen"], float(dd.group(1)))
            continue
        m = re.match(r"\[QATS\]\[DEAL\] ticket=(\d+) entry=(\d+) symbol=\S+ type=(\d+) volume=([\d.]+) price=([\d.]+) profit=([-\d.]+)", s)
        if m:
            entry, dtype, profit = int(m.group(2)), int(m.group(3)), float(m.group(6))
            rep["deals_v111"].append((m.group(1), entry, dtype, profit))
            continue
    # v1.11 has no per-position result line: rebuild trades from the deal lines
    if rep["format"] and rep["format"].startswith("v1.11"):
        seen = set()
        open_side = None
        for ticket, entry, dtype, profit in rep["deals_v111"]:
            if ticket in seen:
                continue                                  # the terminal can deliver one deal twice
            seen.add(ticket)
            if entry == 0:
                open_side = "BUY" if dtype == 0 else "SELL"
                rep["sides"][open_side]["entries_v111"] += 1
                rep["sides"][open_side]["filled"] += 1
            elif open_side:
                d = rep["sides"][open_side]
                d["net"] += profit
                if profit > 0:
                    d["wins"] += 1
                    d["gross_profit"] += profit
                elif profit < 0:
                    d["losses"] += 1
                    d["gross_loss"] += -profit
                else:
                    d["neutral"] += 1
    # equity drawdown as seen by the heartbeats
    peak, dd = 0.0, 0.0
    for eq in rep["equity"]:
        peak = max(peak, eq)
        if peak > 0:
            dd = max(dd, (peak - eq) / peak * 100.0)
    rep["heartbeat_equity_dd_pct"] = dd
    return rep


def side_summary(d, bars):
    closed = d["wins"] + d["losses"] + d["neutral"]
    return {
        "mean_score": (d["score_sum"] / float(bars)) if bars else 0.0,
        "max_score": d["score_max"],
        "bars_score_ge_min": d["bars_score_ge_min"],
        "bars_core_pass": d["bars_core_pass"],
        "setups_detected": d["setups_detected"],
        "bars_candidate": d["bars_candidate"],
        "bars_eligible": d["bars_eligible"],
        "approved": d["approved"], "filled": d["filled"],
        "closed": closed, "wins": d["wins"], "losses": d["losses"], "neutral": d["neutral"],
        "win_rate": (d["wins"] / float(closed)) if closed else 0.0,
        "profit_factor": (d["gross_profit"] / d["gross_loss"]) if d["gross_loss"] > 0 else (float("inf") if d["gross_profit"] > 0 else 0.0),
        "net": d["net"],
        "expectancy_money": (d["net"] / closed) if closed else 0.0,
        "avg_planned_rr": (d["planned_rr_sum"] / d["approved"]) if d["approved"] else 0.0,
        "outcomes": dict(d["outcomes"]),
        "blocked_bar_reasons": dict(d["blocked_bar_reasons"]),
        "block_events": dict(d["block_events"]),
        "rejections": dict(d["rejections"]),
    }


def to_summary(rep):
    out = {k: rep[k] for k in ("versions", "symbols", "first_time", "last_time", "qats_lines", "bars_scored", "minimum",
                               "profile", "format", "none_bars", "conflicts", "exec_fail_lines", "critical_lines",
                               "retries", "max_dd_pct_seen", "heartbeat_equity_dd_pct", "longest_run")}
    out["guards"] = dict(rep["guard_lines"])
    out["cooldown_events"] = rep["cooldown"]
    out["BUY"] = side_summary(rep["sides"]["BUY"], rep["bars_scored"])
    out["SELL"] = side_summary(rep["sides"]["SELL"], rep["bars_scored"])
    findings = []
    b, s = out["BUY"], out["SELL"]
    if rep["bars_scored"] == 0:
        findings.append("No scored bar found: this is not a QATS journal, or the EA never analysed a bar.")
    if rep["format"] and rep["format"].startswith("v1.11") and rep["bars_scored"]:
        findings.append("v1.11 journal: each bar names ONE direction. %d bars were BUY, %d SELL, %d none; the other "
                        "side was not scored on those bars. Longest single-direction run: %d bars %s."
                        % (b["bars_candidate"], s["bars_candidate"], rep["none_bars"], rep["longest_run"]["bars"], rep["longest_run"]["side"]))
    if rep["format"] and rep["format"].startswith("v1.20") and rep["bars_scored"]:
        for name, d in (("BUY", b), ("SELL", s)):
            if d["setups_detected"] == 0:
                findings.append("%s: no setup passed the core confirmation in %d bars (max score %d). Read the "
                                "'%s core=FAIL(...)' text of the scored records for the missing event."
                                % (name, rep["bars_scored"], d["max_score"], name))
            elif d["filled"] == 0:
                findings.append("%s: %d setup(s) detected, none executed - see the blocks and rejections below." % (name, d["setups_detected"]))
    if rep["critical_lines"]:
        findings.append("%d [QATS][VERIFY][CRITICAL] line(s): an order was accepted but no position was found. Inspect the account." % rep["critical_lines"])
    out["findings"] = findings
    return out


def render(summary):
    L = []
    w = L.append
    w("# QATS journal report")
    w("")
    w("- EA version(s): %s | symbol(s): %s" % (", ".join(summary["versions"]) or "not in this excerpt", ", ".join(summary["symbols"]) or "n/a"))
    w("- journal format: %s" % (summary["format"] or "no scored bars"))
    w("- period: %s .. %s | [QATS] lines: %d | bars scored: %d | minimum score: %s | profile: %s"
      % (summary["first_time"] or "?", summary["last_time"] or "?", summary["qats_lines"], summary["bars_scored"],
         summary["minimum"], summary["profile"] or "n/a"))
    w("")
    w("## Signals and executions by direction")
    w("")
    w("| | BUY | SELL |")
    w("|---|---|---|")
    b, s = summary["BUY"], summary["SELL"]
    rows = [
        ("bars where this side was the candidate", "bars_candidate", "%d"),
        ("mean score over all scored bars", "mean_score", "%.1f"),
        ("highest score seen", "max_score", "%d"),
        ("bars with score >= minimum", "bars_score_ge_min", "%d"),
        ("bars with core confirmation PASS", "bars_core_pass", "%d"),
        ("setups detected ([DETECTED])", "setups_detected", "%d"),
        ("bars eligible (core + score)", "bars_eligible", "%d"),
        ("orders approved", "approved", "%d"),
        ("orders filled", "filled", "%d"),
        ("positions closed", "closed", "%d"),
        ("wins / losses / neutral", None, None),
        ("win rate", "win_rate", "pct"),
        ("profit factor", "profit_factor", "%.2f"),
        ("net result", "net", "%+.2f"),
        ("expectancy per trade (money)", "expectancy_money", "%+.2f"),
        ("average planned R:R", "avg_planned_rr", "%.2f"),
    ]
    for label, key, fmt in rows:
        if key is None:
            w("| %s | %d / %d / %d | %d / %d / %d |" % (label, b["wins"], b["losses"], b["neutral"], s["wins"], s["losses"], s["neutral"]))
        elif fmt == "pct":
            w("| %s | %.1f%% | %.1f%% |" % (label, 100 * b[key], 100 * s[key]))
        else:
            w(("| %s | " + fmt + " | " + fmt + " |") % (label, b[key], s[key]))
    w("")
    w("Bars with no candidate: %d | conflicts (both sides eligible): %d | longest single-direction run: %d bars %s"
      % (summary["none_bars"], summary["conflicts"], summary["longest_run"]["bars"], summary["longest_run"]["side"]))
    w("")
    w("## Outcome of every bar, by candidate direction")
    w("")
    w("| direction | outcome | bars |")
    w("|---|---|---|")
    for name in SIDES:
        for k, v in sorted(summary[name]["outcomes"].items(), key=lambda kv: -kv[1]):
            w("| %s | %s | %d |" % (name, k, v))
    w("")
    w("## Why eligible signals were not executed")
    w("")
    w("| direction | kind | reason | count |")
    w("|---|---|---|---|")
    any_row = False
    for name in SIDES:
        for k, v in sorted(summary[name]["block_events"].items(), key=lambda kv: -kv[1]):
            w("| %s | risk guard ([BLOCK][REASON] events) | %s | %d |" % (name, k, v))
            any_row = True
        for k, v in sorted(summary[name]["rejections"].items(), key=lambda kv: -kv[1]):
            w("| %s | execution ([EXECUTION][REJECTED]) | %s | %d |" % (name, k.replace("|", "/"), v))
            any_row = True
        for k, v in sorted(summary[name]["blocked_bar_reasons"].items(), key=lambda kv: -kv[1])[:8]:
            w("| %s | bars | %s | %d |" % (name, k.replace("|", "/"), v))
            any_row = True
    if not any_row:
        w("| - | - | none recorded | 0 |")
    w("")
    w("## Protection and execution health")
    w("")
    w("- guards tripped: %s" % (", ".join("%s x%d" % kv for kv in sorted(summary["guards"].items())) or "none"))
    w("- largest drawdown printed by a heartbeat (from the equity high-water mark): %.2f%%" % summary["max_dd_pct_seen"])
    w("- drawdown of the heartbeat equity series inside this journal: %.2f%%" % summary["heartbeat_equity_dd_pct"])
    w("- broker refusals ([QATS][EXEC][FAIL]): %d | retries: %d | accepted-but-unverified positions: %d"
      % (summary["exec_fail_lines"], summary["retries"], summary["critical_lines"]))
    if summary["cooldown_events"]:
        w("- cooldown timeline:")
        for t, text in summary["cooldown_events"][:20]:
            w("  - %s %s" % (t, text))
    w("")
    if summary["findings"]:
        w("## Findings")
        w("")
        for f in summary["findings"]:
            w("- " + f)
        w("")
    w("This report restates the journal. It is not a compile result, not a backtest, and not evidence of profitability.")
    return "\n".join(L) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description="BUY-vs-SELL report from a QATS Experts journal")
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    lines = []
    for path in args.logs:
        lines += read_lines(path)
    summary = to_summary(analyse(lines))
    if args.json:
        json.dump(summary, sys.stdout, indent=1, sort_keys=True, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
