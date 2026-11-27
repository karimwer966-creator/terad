#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INCIDENT EVIDENCE MAP - keeps docs/incident-20261101/README.md honest.

WHY THIS EXISTS
---------------
`docs/incident-20261101/` holds 113 frozen files in two subtrees that share 47
filenames, and nothing in the repository said which subtree is authoritative.
`evidence/` and `fingerprint-fix/` both contain a `summary.txt`, a
`static_check.log` and a `test_decision_journal.log`, and two of those three
disagree with each other. A reader cannot tell a superseded log from a
contradicting one, and "which log do I believe?" has a wrong answer that looks
like a right one.

docs/incident-20261101/README.md answers it. This suite is the reason the answer
stays true: the README's counts are checked against the files, and the files are
checked against each other. The folder is frozen, so any change here is either a
correction that must be reflected in the README or a corruption of an evidence
record, and both are failures worth stopping on.

WHAT IT CHECKS
--------------
  E1  the folder's shape: REPORT.md, README.md and exactly two log subtrees.
  E2  the file counts the README states (62 / 50).
  E3  the overlap: 47 shared names, 44 byte-identical, and the 3 that differ are
      exactly the 3 the README names - no fourth difference may appear.
  E4  each of those 3 differences is the one the README explains, verbatim.
  E5  only evidence/ holds the per-defect before-logs REPORT.md cites; only
      fingerprint-fix/ holds the parser suite and the NOTE.
  E6  the README's staleness table is true: today's tree really does exceed the
      frozen counts, so a reader cannot mistake the logs for the current state.
  E7  the README still says the post-fix F7 is open. Nothing here may imply it
      was ever returned.

This is a file-and-text contract over a frozen evidence record. It is not a
compile, not a backtest, and it makes no claim about trading behaviour.
"""

import hashlib
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "docs", "incident-20261101")
EVID = os.path.join(BASE, "evidence")
FIX = os.path.join(BASE, "fingerprint-fix")
README = os.path.join(BASE, "README.md")

COUNT = [0]
FAILURES = []


def check(cond, label, detail=""):
    COUNT[0] += 1
    if cond:
        print("PASS %s" % label)
    else:
        print("FAIL %s%s" % (label, ("  -> " + detail) if detail else ""))
        FAILURES.append(label)


def names(d):
    return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def doc(*rel):
    return read(os.path.join(BASE, *rel))


# ---------------------------------------------------------------- E1 shape
check(os.path.isdir(EVID), "E1 evidence/ exists")
check(os.path.isdir(FIX), "E1 fingerprint-fix/ exists")
check(os.path.isfile(os.path.join(BASE, "REPORT.md")), "E1 REPORT.md exists")
check(os.path.isfile(README), "E1 README.md exists")

subs = sorted(e for e in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, e)))
check(subs == ["evidence", "fingerprint-fix"],
      "E1 exactly two log subtrees", "%s" % subs)

e_names = names(EVID)
f_names = names(FIX)

# ---------------------------------------------------------------- E2 counts
check(len(e_names) == 62, "E2 evidence/ holds 62 files", "%d" % len(e_names))
check(len(f_names) == 50, "E2 fingerprint-fix/ holds 50 files", "%d" % len(f_names))
check("62 files in `evidence/`" in read(README),
      "E2 the README states the 62 count")
check("50 in `fingerprint-fix/`" in read(README),
      "E2 the README states the 50 count")

# ---------------------------------------------------------------- E3 overlap
shared = sorted(set(e_names) & set(f_names))
identical = [n for n in shared if md5(os.path.join(EVID, n)) == md5(os.path.join(FIX, n))]
differing = [n for n in shared if n not in identical]

check(len(shared) == 47, "E3 47 filenames are shared", "%d" % len(shared))
check(len(identical) == 44, "E3 44 of them are byte-identical", "%d" % len(identical))
check("47 filenames are shared" in read(README), "E3 the README states the 47")
check("**44 of those 47 are byte-identical**" in read(README),
      "E3 the README states the 44")

EXPECTED_DIFF = ["static_check.log", "summary.txt", "test_instance_identity.log"]
check(differing == EXPECTED_DIFF,
      "E3 the only differing shared files are the three named ones",
      "%s" % differing)

# ------------------------------------------------------- E4 the three diffs
sum_e = doc("evidence", "summary.txt").strip()
sum_f = doc("fingerprint-fix", "summary.txt").strip()
check(sum_e == "46 checks; failures: []", "E4 evidence/summary.txt is the 46-check run",
      repr(sum_e))
check(sum_f == "47 checks; failures: []",
      "E4 fingerprint-fix/summary.txt is the 47-check run", repr(sum_f))
check("`46 checks; failures: []`" in read(README), "E4 the README quotes the 46")
check("`47 checks; failures: []`" in read(README), "E4 the README quotes the 47")

sc_e = doc("evidence", "static_check.log")
sc_f = doc("fingerprint-fix", "static_check.log")
check("QSMC_InputFingerprint.mqh   97707 bytes" in sc_e,
      "E4 the older static_check.log records 97707 bytes")
check("QSMC_InputFingerprint.mqh   98805 bytes" in sc_f,
      "E4 the newer static_check.log records 98805 bytes")
check("97707 bytes" in read(README) and "98805 bytes" in read(README),
      "E4 the README quotes both header sizes")

ii_e = doc("evidence", "test_instance_identity.log")
ii_f = doc("fingerprint-fix", "test_instance_identity.log")
check("input fingerprint manifest: 568 inputs" in ii_e,
      "E4 the older identity log records a 568-input manifest")
check("input fingerprint manifest: 576 inputs" in ii_f,
      "E4 the newer identity log records a 576-input manifest")
check("568 inputs" in read(README) and "576 inputs" in read(README),
      "E4 the README quotes both manifest counts")

# the three differences must be the ONLY content differences, line for line
for n in EXPECTED_DIFF:
    a = doc("evidence", n).splitlines()
    b = doc("fingerprint-fix", n).splitlines()
    delta = [i for i in range(max(len(a), len(b)))
             if (a[i] if i < len(a) else None) != (b[i] if i < len(b) else None)]
    check(len(delta) <= 1,
          "E4 %s differs on at most one line" % n,
          "lines %s" % delta)

# --------------------------------------------------------- E5 who holds what
e_only = sorted(set(e_names) - set(f_names))
f_only = sorted(set(f_names) - set(e_names))

BEFORE_LOGS = ["atr-before.log", "authority-before.log", "compact-before.log",
               "instance-before.log", "price-before.log", "scanner-before.log",
               "zone-before.log"]
check(all(n in e_only for n in BEFORE_LOGS),
      "E5 the seven per-defect before-logs live only in evidence/",
      "%s" % [n for n in BEFORE_LOGS if n not in e_only])
integ = [n for n in e_only if n.startswith("integration-before-")]
check(len(integ) == 8, "E5 evidence/ holds eight integration-before logs",
      "%d" % len(integ))
check(not [n for n in f_names if re.match(r"^(integration-)?.*-before\.log$", n)
           and n != "before.log"],
      "E5 fingerprint-fix/ holds none of those before-logs")

check("test_input_fingerprint_parser.log" in f_only,
      "E5 only fingerprint-fix/ has the parser suite's log")
check("test_input_fingerprint_parser.log" not in e_names,
      "E5 evidence/ predates the parser suite")
check("NOTE.md" in f_only, "E5 only fingerprint-fix/ has NOTE.md")
check("before.log" in f_only, "E5 only fingerprint-fix/ has before.log")
check("evidence/" in doc("REPORT.md"),
      "E5 REPORT.md cites the evidence/ before-logs by path")

# --------------------------------------------------- E6 the staleness claim
tools = os.path.join(ROOT, "tools")
n_test = len([f for f in os.listdir(tools) if f.startswith("test_") and f.endswith(".py")])
n_check = len([f for f in os.listdir(tools) if f.startswith("check_") and f.endswith(".py")])
check(n_test > 43,
      "E6 the frozen '43 files tools/test_*.py' is stale today (%d)" % n_test,
      "%d" % n_test)
check(n_check > 0, "E6 the tree also holds %d check_*.py suites" % n_check)

hdr = os.path.join(ROOT, "MQL5", "Include", "QSMC", "QSMC_InputFingerprint.mqh")
size = os.path.getsize(hdr)
check(size > 98805,
      "E6 the frozen 98805-byte header is stale today (%d bytes)" % size,
      "%d" % size)

# the manifest count is the one number a reader could act on, so it is read
# from the suite that owns it rather than re-parsed here.
import subprocess
out = subprocess.run([sys.executable, os.path.join(tools, "test_instance_identity.py")],
                     capture_output=True, text=True, cwd=ROOT)
m = re.search(r"input fingerprint manifest: (\d+) inputs", out.stdout)
check(bool(m), "E6 test_instance_identity.py reports a manifest count",
      "rc=%d" % out.returncode)
if m:
    live = int(m.group(1))
    check(live > 576,
          "E6 the frozen 576-input manifest is stale today (%d)" % live,
          "%d" % live)
    check(("**%d**" % live) in read(README),
          "E6 the README states the live manifest count (%d)" % live,
          "README does not mention %d" % live)
check(str(n_test) in read(README),
      "E6 the README states today's test_*.py count (%d)" % n_test)

# ------------------------------------------------------- E7 still not closed
check("never\nreturned" in read(README) or "never returned" in read(README),
      "E7 the README says the post-fix F7 log was never returned")
check("still open" in read(README), "E7 the README says that item is still open")

print("")
print("=" * 74)
print("INCIDENT EVIDENCE MAP checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    print("")
    print("A frozen evidence record changed, or README.md drifted from it. Fix")
    print("README.md unless the folder itself was corrupted - if a log was")
    print("edited, that is the failure, not the test.")
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("This is a file-and-text contract over a frozen folder. It is not a")
print("MetaEditor compile, not a backtest, and it makes no trading claim.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
