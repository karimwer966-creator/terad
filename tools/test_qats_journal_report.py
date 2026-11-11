#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QATS-JOURNAL-TEST - the journal report must count what the journal says.

tools/qats_journal_report.py is the evidence format for the DEMO forward test:
an operator runs it on the Experts journal and reads BUY vs SELL. A report that
miscounts would send them hunting a defect that is not there (or hide one that
is), so the counts are pinned three ways:

  A. a committed v1.11 journal (one direction per bar) - the tool must recognise
     the old format, count each side, and say that the other side was not scored;
  B. a v1.20 journal produced HERE by replaying the real EA source in the
     simulator - the report's numbers must equal what the scenario itself
     measured (fills per direction, scored bars, closed positions);
  C. the same journal re-encoded the way the terminal stores it (UTF-16 with a
     byte-order mark) and the way a browser copy mangles it (CRLF, HTML entities)
     must produce the identical report.

Section B needs a host C++ compiler. Without one the suite still verifies A and
the encodings, prints SKIP for B, and exits 77 - "not fully verified here" - so a
gate can tell that apart from both a pass and a failure.
"""
from __future__ import print_function

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import qats_journal_report as JR  # noqa: E402
import qats_native as Q  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "qats_v111_journal_sample.log")
FAILURES = []
COUNT = [0]


def check(ok, label, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + label)
    else:
        print("FAIL  " + label + (("  [" + str(detail) + "]") if detail else ""))
        FAILURES.append(label)


def summarise(path):
    return JR.to_summary(JR.analyse(JR.read_lines(path)))


def main():
    # ----------------------------------------------------- A. v1.11 journal
    s = summarise(FIXTURE)
    check(s["versions"] == ["1.11"], "A1 the EA version is read from the attach banner", s["versions"])
    check(s["format"].startswith("v1.11"), "A2 a one-direction-per-bar journal is recognised as v1.11", s["format"])
    check(s["bars_scored"] == 254, "A3 every [QATS][SIGNAL] record is one scored bar (254)", s["bars_scored"])
    check(s["BUY"]["bars_candidate"] == 192 and s["SELL"]["bars_candidate"] == 62,
          "A4 bars per direction: 192 BUY, 62 SELL", (s["BUY"]["bars_candidate"], s["SELL"]["bars_candidate"]))
    check(s["BUY"]["bars_candidate"] + s["SELL"]["bars_candidate"] + s["none_bars"] == s["bars_scored"],
          "A5 BUY + SELL + none adds up to the scored bars (each bar named exactly one direction)")
    check(s["longest_run"] == {"side": "BUY", "bars": 180}, "A6 the longest single-direction run is 180 BUY bars (15 hours)", s["longest_run"])
    check(s["BUY"]["filled"] == 4 and s["SELL"]["filled"] == 0, "A7 entries rebuilt from [QATS][DEAL]: 4 BUY, 0 SELL",
          (s["BUY"]["filled"], s["SELL"]["filled"]))
    check(s["BUY"]["losses"] == 4 and s["BUY"]["wins"] == 0 and abs(s["BUY"]["net"] + 79.29) < 0.005,
          "A8 closed BUY trades: 4 losses, net -79.29", (s["BUY"]["wins"], s["BUY"]["losses"], s["BUY"]["net"]))
    reasons = s["BUY"]["blocked_bar_reasons"]
    check(reasons.get("daily trade cap reached (#/#)") == 86 and reasons.get("CONSECUTIVE-LOSS cooldown active") == 11 and
          reasons.get("max open positions reached (#)") == 44,
          "A9 rejection reasons are bucketed with their counts (numbers folded)", reasons)
    check(s["guards"].get("consecutive-loss stand-down started") == 1, "A10 the consecutive-loss stand-down is counted", s["guards"])
    check(any("ONE direction" in f and "180 bars BUY" in f for f in s["findings"]),
          "A11 the report states that the other side was not scored", s["findings"])
    text = JR.render(s)
    check("| bars where this side was the candidate | 192 | 62 |" in text, "A12 the rendered table carries the same numbers")
    check("not evidence of profitability" in text, "A13 the report states its own limits")

    # --------------------------------------------- C. encodings (on fixture)
    work = os.path.join(Q.OUT_DIR, "journal")
    os.makedirs(work, exist_ok=True)
    raw = open(FIXTURE, "rb").read().decode("utf-8")
    u16 = os.path.join(work, "utf16.log")
    with open(u16, "wb") as fh:
        fh.write(b"\xff\xfe" + raw.encode("utf-16-le"))
    crlf = os.path.join(work, "crlf.log")
    with open(crlf, "wb") as fh:
        fh.write(raw.replace("\n", "\r\n").replace(">", "&gt;").encode("utf-8"))
    bom8 = os.path.join(work, "bom8.log")
    with open(bom8, "wb") as fh:
        fh.write(b"\xef\xbb\xbf" + raw.encode("utf-8"))
    base = json.dumps(s, sort_keys=True, default=str)
    check(json.dumps(summarise(u16), sort_keys=True, default=str) == base, "C1 a UTF-16 terminal log gives the identical report")
    check(json.dumps(summarise(crlf), sort_keys=True, default=str) == base, "C2 CRLF line ends and HTML-escaped '>' give the identical report")
    check(json.dumps(summarise(bom8), sort_keys=True, default=str) == base, "C3 a UTF-8 byte-order mark gives the identical report")
    proc = subprocess.run([sys.executable, os.path.join(HERE, "qats_journal_report.py"), FIXTURE, "--json"],
                          stdout=subprocess.PIPE, universal_newlines=True)
    check(proc.returncode == 0 and json.loads(proc.stdout)["BUY"]["bars_candidate"] == 192, "C4 the command line prints the same summary as JSON")

    # ------------------------------------------------ B. v1.20 journal, live
    skipped = False
    if not Q.find_compiler():
        skipped = True
        print("SKIP  qats-journal-report section B: this host has no usable C++17 compiler (g++, c++, clang++)")
        print("      The v1.20 journal could not be generated here. NOT verified here; the Linux CI run has one.")
    else:
        exe, rc, diag = Q.build(Q.EA_SOURCE, "journal")
        check(rc == 0 and exe is not None, "B0 the EA builds for the journal replay", diag.strip()[:200])
        if exe:
            log = os.path.join(work, "two_sided.log")
            proc = subprocess.run([exe, "selftest", "journal_invariants", "--log", log], stdout=subprocess.PIPE, universal_newlines=True)
            result = {}
            for line in proc.stdout.splitlines():
                if line.startswith("RESULT "):
                    result = dict(t.split("=", 1) for t in line.split()[1:])
            check(proc.returncode == 0 and result, "B1 the two-sided scenario ran and reported its own counts", proc.stdout[-200:])
            v = summarise(log)
            # the SCORED record format is unchanged since v1.20 (both directions per
            # bar); only the version string in the attach banner moved.
            check(len(v["versions"]) == 1 and v["versions"][0] in ("1.20", "1.21", "1.22")
                  and v["format"].startswith("v1.20"),
                  "B2 the journal is recognised as v1.20+", (v["versions"], v["format"]))
            check(v["bars_scored"] == int(result.get("scored", -1)), "B3 scored bars equal the scenario's own count (%s)" % result.get("scored"), v["bars_scored"])
            check(v["BUY"]["filled"] == int(result.get("buyFills", -1)) and v["SELL"]["filled"] == int(result.get("sellFills", -1)),
                  "B4 fills per direction equal the scenario's own counts (BUY %s, SELL %s)" % (result.get("buyFills"), result.get("sellFills")),
                  (v["BUY"]["filled"], v["SELL"]["filled"]))
            check(v["BUY"]["setups_detected"] >= 1 and v["SELL"]["setups_detected"] >= 1, "B5 both directions have detected setups")
            check(v["BUY"]["approved"] == v["BUY"]["filled"] and v["SELL"]["approved"] == v["SELL"]["filled"],
                  "B6 every approved order is a filled order in this journal")
            check(v["BUY"]["closed"] == 1 and v["SELL"]["closed"] == 1 and v["BUY"]["wins"] == 1 and v["SELL"]["wins"] == 1,
                  "B7 closed positions are attributed to their direction from the deal history lines")
            check(v["BUY"]["block_events"].get("DUPLICATE_SETUP", 0) >= 1 and v["SELL"]["block_events"].get("DUPLICATE_SETUP", 0) >= 1,
                  "B8 block reasons are counted per direction", (v["BUY"]["block_events"], v["SELL"]["block_events"]))
            check(v["BUY"]["avg_planned_rr"] >= 1.5 and v["SELL"]["avg_planned_rr"] >= 1.5, "B9 the planned R:R is read from the APPROVED records")
            check(not v["findings"], "B10 a journal with both sides detected and executed raises no finding", v["findings"])
            total_bars = sum(sum(v[side]["outcomes"].values()) for side in ("BUY", "SELL")) + v["none_bars"]
            check(total_bars == v["bars_scored"], "B11 every scored bar has exactly one outcome in the report")
            # the cooldown scenario: losses in both directions, one stand-down, one expiry
            clog = os.path.join(work, "cooldown.log")
            proc = subprocess.run([exe, "selftest", "cooldown", "--log", clog], stdout=subprocess.PIPE, universal_newlines=True)
            c = summarise(clog)
            check(proc.returncode == 0, "B12 the cooldown scenario ran")
            check(c["BUY"]["losses"] == 3 and c["SELL"]["losses"] == 2 and c["SELL"]["wins"] == 1,
                  "B13 losses and wins from the deal history are split by direction (BUY 3 L, SELL 2 L / 1 W)",
                  (c["BUY"]["wins"], c["BUY"]["losses"], c["SELL"]["wins"], c["SELL"]["losses"]))
            check(c["guards"].get("consecutive-loss stand-down started") == 1, "B14 one stand-down was started")
            states = [text.split()[0] for _, text in c["cooldown_events"]]
            check("state=STARTED" in states and "state=EXPIRED" in states and states.index("state=STARTED") < states.index("state=EXPIRED"),
                  "B15 the cooldown timeline shows STARTED then EXPIRED", states)

    print("")
    print("-" * 74)
    print("qats-journal-report: %d checked, %d failed" % (COUNT[0], len(FAILURES)))
    if FAILURES:
        for f in FAILURES:
            print("  FAILED: " + f)
        return 1
    if skipped:
        print("Sections A and C verified; section B (live v1.20 journal) was skipped.")
        return Q.SKIP_EXIT
    print("The journal report counts what the journal says, in every encoding the terminal produces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
