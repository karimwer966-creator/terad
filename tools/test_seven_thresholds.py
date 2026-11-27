#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEVEN THRESHOLDS - the 2026-11-27 relaxation table cannot drift from the source.

WHY THIS FILE EXISTS
--------------------
Seven `input` values in `nadir2.mq5` are implicated in the 2026-11-27 XAUUSD
missed trade, and each carries a `// was X` comment claiming the value it
replaced. Those comments are the only record of the change: `nadir2.mq5` enters
this repository at `8172522` (2026-11-03) as a whole-file add with all seven
*already* at their current values, so git cannot corroborate a single one.

That makes the table in `docs/SEVEN_THRESHOLDS_2026-11-27.md` load-bearing and
fragile at the same time. If someone edits a default and not the table, the only
written record of the relaxation stops describing the shipped build, and there
is no history to fall back on.

This suite parses the source and the document and fails on any disagreement.
It also pins the two interactions the table calls out as dangerous, so they
cannot be refactored away in silence:

  * `InpRequireMSSAfterSweep=true` makes `CorePathTryBuildContinuation()` return
    before it sets a `why`, so the whole v6.6.25 CONTINUATION feature switches
    off with no log line.
  * `EffMaxStopATR()` raises the CORE stop ceiling to 6.0 ATR under
    `QSMC_GATE_PRACTICAL` while ZRE keeps reading the raw value.

WHAT IT CHECKS
--------------
  T1  all seven inputs exist, at the value the table's "Now" column states.
  T2  each `// was X` comment in the source matches the table's "was" column.
  T3  the table's "Declared" line number is the real declaration line.
  T4  the shipped mirror declares the same seven values.
  T5  the two shadow globals are still assigned from their inputs in OnInit.
  T6  the CONTINUATION / MSS interaction is still present.
  T7  the QSMC_GATE_PRACTICAL stop asymmetry is still present.
  T8  the document says the measurement has NOT been done, so nobody reads the
      table as evidence.

Source contract only. Not a MetaEditor compile, not a backtest, and emphatically
not a signal count - this repository contains no bar data to count over.
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NADIR = os.path.join(ROOT, "nadir2.mq5")
MIRROR = os.path.join(ROOT, "MQL5", "Indicators", "nadir2.mq5")
DOC = os.path.join(ROOT, "docs", "SEVEN_THRESHOLDS_2026-11-27.md")

SEVEN = [
    "InpDisplacementATR",
    "InpFVGMinSizeATR",
    "InpRetestTimeoutBars",
    "InpRetestMaxDistanceATR",
    "InpRequireMSSAfterSweep",
    "InpMaxStopATR",
    "InpCausalDisplacementBodyATR",
]

CHECKS = [0]
FAILURES = []


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("PASS  " + label)
    else:
        print("FAIL  " + label)
        FAILURES.append(label)


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


src = read(NADIR)
doc = read(DOC)
lines = src.split("\n")


def decl(name, text=None):
    """(1-based line, value literal, trailing comment) of `input ... name = V;`."""
    t = (text if text is not None else src).split("\n")
    for i, l in enumerate(t, 1):
        m = re.match(r"^input\s+\S+\s+" + re.escape(name) + r"\s*=\s*([^;]+);(.*)$", l)
        if m:
            return i, m.group(1).strip(), m.group(2)
    return None, None, None


def norm(v):
    """Compare 4.0 and 4.00 and true/True as equal."""
    v = v.strip().lower()
    if v in ("true", "false"):
        return v
    try:
        return "%.6f" % float(v)
    except ValueError:
        return v


# ---- the document's table -------------------------------------------------
rows = {}
for line in doc.split("\n"):
    if not line.startswith("| "):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 7:
        continue
    name = cells[1].strip("`")
    if name not in SEVEN:
        continue
    rows[name] = {"now": cells[2].strip("*` "), "was": cells[3].strip("` "),
                  "decl": cells[4].strip("`"), "sites": cells[5]}

check(len(rows) == len(SEVEN),
      "T1 the table has exactly one row for each of the seven inputs (found %d)" % len(rows))

for name in SEVEN:
    ln, val, comment = decl(name)
    check(ln is not None, "T1 %s is declared as an input" % name)
    if ln is None:
        continue
    row = rows.get(name)
    check(row is not None, "T1 %s has a table row" % name)
    if row:
        check(norm(row["now"]) == norm(val),
              "T1 %s: table 'Now' %s equals the source default %s"
              % (name, row["now"], val))
        m = re.search(r"was\s+([0-9.]+|true|false)", comment or "")
        if m:
            check(norm(row["was"]) == norm(m.group(1)),
                  "T2 %s: table 'was' %s equals the source comment 'was %s'"
                  % (name, row["was"], m.group(1)))
        else:
            check(False, "T2 %s: the source comment still records the value it replaced" % name)
        m2 = re.fullmatch(r":(\d+)", row["decl"])
        check(m2 is not None and int(m2.group(1)) == ln,
              "T3 %s: table cites the real declaration line (table %s, source L%d)"
              % (name, row["decl"], ln))
        m3 = re.match(r"(\d+)", row["sites"])
        check(m3 is not None and int(m3.group(1)) >= 1,
              "T3 %s: the table states how many code sites read it (%s)" % (name, row["sites"]))

# ---- T4 mirror ------------------------------------------------------------
if os.path.isfile(MIRROR):
    mtext = read(MIRROR)
    drift = []
    for name in SEVEN:
        _, a, _ = decl(name, src)
        _, b, _ = decl(name, mtext)
        if norm(a or "") != norm(b or ""):
            drift.append("%s: %s vs %s" % (name, a, b))
    check(not drift,
          "T4 the shipped mirror declares the same seven values (%s)"
          % ("; ".join(drift) if drift else "all seven agree"))
else:
    check(False, "T4 the shipped mirror MQL5/Indicators/nadir2.mq5 exists")

# ---- T5 the shadow globals ------------------------------------------------
for inp, shadow in (("InpMaxStopATR", "g_cfgMaxStopATR"),
                    ("InpCausalDisplacementBodyATR", "g_cfgCausalDispBodyATR")):
    check(re.search(re.escape(shadow) + r"\s*=\s*" + re.escape(inp) + r"\s*;", src) is not None,
          "T5 %s is still copied into %s in OnInit" % (inp, shadow))

# ---- T6 the silent CONTINUATION kill-switch -------------------------------
cont = re.search(r"CorePathTryBuildContinuation\s*\(", src)
check(cont is not None, "T6 CorePathTryBuildContinuation() exists")
if cont:
    k = src.find("{", cont.end())
    depth = 0
    body = ""
    for p in range(k, len(src)):
        if src[p] == "{":
            depth += 1
        elif src[p] == "}":
            depth -= 1
            if depth == 0:
                body = src[k:p + 1]
                break
    check("InpRequireMSSAfterSweep" in body,
          "T6 the CONTINUATION path still tests InpRequireMSSAfterSweep")
    pre = body[:body.find("InpRequireMSSAfterSweep")] if "InpRequireMSSAfterSweep" in body else ""
    check("InpRequireMSSAfterSweep" in body and not re.search(r"\bwhy\s*=", pre),
          "T6 it refuses BEFORE any reason is set - the silent kill-switch the table "
          "warns about is still silent")

# ---- T7 the stop-ceiling asymmetry ----------------------------------------
eff = re.search(r"double\s+EffMaxStopATR\s*\(\s*\)\s*\{", src)
check(eff is not None, "T7 EffMaxStopATR() exists")
if eff:
    k = src.find("{", eff.start())
    depth = 0
    body = ""
    for p in range(k, len(src)):
        if src[p] == "{":
            depth += 1
        elif src[p] == "}":
            depth -= 1
            if depth == 0:
                body = src[k:p + 1]
                break
    check("QSMC_GATE_PRACTICAL" in body and "g_cfgMaxStopATR" in body,
          "T7 EffMaxStopATR() still raises the CORE ceiling under QSMC_GATE_PRACTICAL "
          "while ZRE reads the raw value")

# ---- T8 the honesty clause ------------------------------------------------
flat = re.sub(r"\s+", " ", doc.replace("*", ""))
check("no before/after signal count exists" in flat,
      "T8 the document states plainly that no before/after measurement exists")
check("predates this repository's history" in flat,
      "T8 the document states the 'was' values predate this repository's history")
check("source-contract ready" in flat,
      "T8 the document carries the source-contract status line, not a validation claim")
check("nothing in this file is a measurement" in flat.lower(),
      "T8 the document says outright that nothing in it is a measurement")

print("=" * 60)
print("seven-threshold checks: %d checks, failures: %d" % (CHECKS[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  failed: " + f)
    raise SystemExit(1)
print("docs/SEVEN_THRESHOLDS_2026-11-27.md and nadir2.mq5 agree on all seven values.")
print("Source contract only: NOT a compile, NOT a backtest, NOT a signal count.")
