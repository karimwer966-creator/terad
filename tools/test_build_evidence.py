#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BUILD-EVIDENCE contract: the F7 matrix cannot drift from the logs on disk.

WHY THIS EXISTS
---------------
Every other tool in this repository says, in its own words, "this is not a compile".
That is honest, and it left a hole: the ONE claim the operator actually needs --
"does it build in MetaEditor?" -- had no artifact at all. It lived in chat messages,
which is exactly where a claim goes to be forgotten.

docs/build-evidence/ now holds pasted MetaEditor output. This test makes the folder
truthful:

  A  every row of the F7 matrix either has a log or says PENDING, never both, and a
     PASS row's log really contains `0 errors`;
  B  a log cannot be filed against a program it does not belong to: the basenames
     listed inside the log must equal that program's real TRANSITIVE include chain,
     resolved from the repository (so a log pasted from a different file, or an
     include renamed after the log was taken, is caught);
  C  a log that reports errors is not allowed to sit under a PASS row;
  D  the table cannot grow a program that does not exist in the repository;
  E  the standing caveat is still stated, because the folder is read as a claim.

WHAT THIS IS NOT
----------------
It does not compile anything, and it cannot verify that a pasted log is authentic --
only that it is consistent with the tree and internally coherent. It also does not
grade warnings: a warning is printed, never silently dropped.

Exit code 1 on any failure.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BE = os.path.join(ROOT, "docs", "build-evidence")
README = os.path.join(BE, "README.md")

FAILS = []
CHECKS = [0]


def check(ok, label, detail=""):
    CHECKS[0] += 1
    print(("PASS  " if ok else "FAIL  ") + label + (("  | " + detail) if detail and not ok else ""))
    if not ok:
        FAILS.append(label)


def read(p):
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ------------------------------------------------------------------ include graph
INC_DIRS = [
    os.path.join(ROOT, "MQL5", "Include"),
    os.path.join(ROOT, "MQL5", "Include", "QSMC"),
]


def resolve_include(name):
    """`<QSMC/X.mqh>` -> path, or None for a terminal-shipped include."""
    rel = name.replace("\\", "/")
    for d in INC_DIRS:
        p = os.path.join(d, rel.replace("QSMC/", "", 1) if d.endswith("QSMC") else rel)
        if os.path.isfile(p):
            return p
    return None


INC_RX = re.compile(r'^\s*#include\s+[<"]([^>"]+)[>"]', re.M)

# Includes that ship with MetaTrader, not with this repository. They cannot be
# resolved from the tree, so they are recognised by name instead: the Standard
# Library headers pulled in by <Trade/Trade.mqh>. A log is allowed to list these
# and nothing else beyond the repository's own chain - any other unknown basename
# is a file this repository does not contain, which means the log came from a
# different source tree.
TRADE_STDLIB = {
    "Trade.mqh", "Object.mqh", "StdLibErr.mqh", "OrderInfo.mqh",
    "HistoryOrderInfo.mqh", "PositionInfo.mqh", "DealInfo.mqh", "SymbolInfo.mqh",
}


def chain(start, seen=None):
    """Transitive include chain of `start`, as basenames, definition order."""
    if seen is None:
        seen = []
    text = read(start)
    base = os.path.basename(start)
    if base not in seen:
        seen.append(base)
    for name in INC_RX.findall(text):
        p = resolve_include(name)
        if p is None:
            continue                      # terminal library: not ours to compile
        if os.path.basename(p) in seen:
            continue
        chain(p, seen)
    return seen


# ------------------------------------------------------------------------ matrix
rows = []          # (program, status, evidence)
for line in read(README).split("\n"):
    if not line.startswith("| `"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 5:
        continue
    program = cells[0].strip("`").strip()
    status = cells[2].replace("*", "").strip()
    evidence = cells[4].strip("`").strip()
    rows.append((program, status, evidence))

check(len(rows) >= 4, "the F7 matrix lists every program that has to build (%d rows)" % len(rows),
      str(rows))

for program, status, evidence in rows:
    label = os.path.basename(program)
    path = os.path.join(ROOT, program.replace("/", os.sep))
    check(os.path.isfile(path), "A %s exists in the repository" % label)

    if status.upper() == "PENDING":
        check(evidence in ("—", "-", "", "—"), "A %s is PENDING and cites no log" % label, evidence)
        continue

    log_path = os.path.join(BE, evidence)
    check(os.path.isfile(log_path), "A %s cites a log that exists (%s)" % (label, evidence))
    if not os.path.isfile(log_path):
        continue

    log = read(log_path)
    errs = re.findall(r"(\d+)\s+errors?\s*,\s*(\d+)\s+warnings?", log)
    check(bool(errs), "A %s log states an '<n> errors, <n> warnings' verdict" % label)

    if errs:
        n_err, n_warn = int(errs[-1][0]), int(errs[-1][1])
        check(("PASS" in status.upper()) == (n_err == 0),
              "A %s PASS row and its log agree about errors (%d)" % (label, n_err))
        if n_warn:
            print("      note: %s reports %d warning(s) - kept, not hidden" % (label, n_warn))

    # B: the log's own file list must be this program's real include chain, plus
    # (only) the terminal Standard Library headers it is documented to pull in.
    listed = set(re.findall(r"^([A-Za-z0-9_]+\.mq[5h])\s*$", log, re.M))
    expected = set(chain(path))
    src = read(path)
    terminal = set()
    if re.search(r'#include\s+[<"]Trade/Trade\.mqh[>"]', src):
        terminal |= TRADE_STDLIB
    missing = expected - listed
    extra = listed - expected - terminal
    check(not missing and not extra,
          "B %s log lists exactly that program's include chain" % label,
          "missing=%s extra=%s" % (sorted(missing), sorted(extra)))
    if terminal:
        check("Trade.mqh" in listed,
              "B %s includes <Trade/Trade.mqh>, so its log must list Trade.mqh" % label)

# C: no PASS row may hide a failing log anywhere in the folder.
for name in sorted(os.listdir(BE)):
    if not name.endswith(".log"):
        continue
    log = read(os.path.join(BE, name))
    m = re.findall(r"(\d+)\s+errors?", log)
    if not m:
        continue
    cited = any(name == ev for _, _, ev in rows)
    check(int(m[-1]) == 0 or not cited,
          "C %s: a log with errors is not cited by any PASS row" % name, m[-1])

# D: the matrix cannot name a program that does not exist.
for program, _, _ in rows:
    check(os.path.isfile(os.path.join(ROOT, program.replace("/", os.sep))),
          "D %s is a real path in this repository" % program)

# E: the caveat that stops this folder reading as a profitability claim.
flat = re.sub(r"\s+", " ", read(README))
check("not a compile" in flat.lower() and "profitable" in flat.lower(),
      "E the folder still states that source checks are not a compile and a build is not an edge")

print("-" * 70)
print("BUILD-EVIDENCE: %d checks, %d failure(s)" % (CHECKS[0], len(FAILS)))
if FAILS:
    for f in FAILS:
        print("  failed: " + f)
    raise SystemExit(1)
print("The F7 matrix matches the logs on disk. This is still not a compiler:")
print("it cannot prove a log is authentic, only that it is consistent. Press F7.")
