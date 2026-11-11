#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NATIVE-SKIP - the difference between "verified", "wrong" and "cannot run".

WHY THIS EXISTS
---------------
Seven suites compile and run the real MQL5 method bodies with a host g++. On a
Windows desktop without g++ they used to raise

    FileNotFoundError: [WinError 2] The system cannot find the file specified

and the curated gate printed OFFLINE NO-GO - a healthy tree condemned because
the machine lacked a compiler. The fix is a third status, and a third status is
only trustworthy if it is pinned:

  * a suite that cannot run exits 77 and says which toolchain it wanted;
  * it never prints PASS for something it did not run, and never turns a real
    failure into a skip;
  * the gate renders PARTIAL, names the skipped checks, and refuses to pretend
    the GO covers them;
  * --require-native makes a skip fatal, which is what CI uses so a runner
    without a compiler cannot go green quietly.

These tests are machine-independent: the skip path is forced with
QSMC_NO_NATIVE=1 rather than by uninstalling anything.
"""
from __future__ import print_function

import contextlib
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import native_toolchain as NT  # noqa: E402
import check_production_ready as G  # noqa: E402

FAILS = []
COUNT = [0]

# (curated name, filename, also checks source without a compiler)
NATIVE_SUITES = [
    ("tick-performance", "test_tick_performance.py", True),
    ("runtime-diagnostics", "test_runtime_diagnostics.py", True),
    ("input-fingerprint-parser", "test_input_fingerprint_parser.py", True),
    ("volatility-window", "test_volatility_window.py", False),
    ("liquidity-value-runtime", "test_liquidity_value_runtime.py", False),
    ("unified-decision-runtime", "test_unified_decision_runtime.py", False),
    ("resolver-runtime", "test_resolver_runtime.py", False),
]

# QATS v1.20: three more suites that need the host compiler and follow the same
# skip contract. The curated gate itself runs them for real (two take about a
# minute each), so only the compiler-less half of the contract is repeated here.
QATS_NATIVE_SUITES = [
    ("qats-native-build", "test_qats_native_build.py", False),
    ("qats-dual-direction", "test_qats_dual_direction.py", False),
    ("qats-journal-report", "test_qats_journal_report.py", True),
]

# v6.6.22: the chart-hygiene suite and the SMC + Volume Profile engine suite.
# Both check the source first (always) and execute it second (compiler needed),
# so both must exit 77 - with their source checks still reported - when the
# compiler is absent. The gate runs them for real.
SMCVP_NATIVE_SUITES = [
    ("qsmc-chart-hygiene", "test_qsmc_chart_hygiene.py", True),
    ("qsmc-smcvp-engine", "test_qsmc_smcvp.py", True),
]


def check(ok, name, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s%s" % (name, ("  [%s]" % detail) if detail else ""))
        FAILS.append(name)


def run_suite(filename, force_no_native):
    env = dict(os.environ)
    env.pop(NT.FORCE_ENV, None)
    if force_no_native:
        env[NT.FORCE_ENV] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, os.path.join(HERE, filename)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          env=env, timeout=900)
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 1. the helper's contract
# ---------------------------------------------------------------------------
check(NT.SKIP_EXIT == 77, "the skip exit code is 77 (autotools convention)")
check(NT.FORCE_ENV == "QSMC_NO_NATIVE", "the forced-skip variable is documented by name")

saved_env = os.environ.pop(NT.FORCE_ENV, None)
NT._CACHE.clear()
try:
    here = NT.compiler()
    here_san = NT.compiler(sanitizers=True)
finally:
    if saved_env is not None:
        os.environ[NT.FORCE_ENV] = saved_env

os.environ[NT.FORCE_ENV] = "1"
NT._CACHE.clear()
forced = NT.compiler()
forced_san = NT.compiler(sanitizers=True)
os.environ.pop(NT.FORCE_ENV, None)
NT._CACHE.clear()

check(forced is None, "QSMC_NO_NATIVE=1 makes compiler() return None")
check(forced_san is None, "QSMC_NO_NATIVE=1 also disables the sanitizer probe")
check(here is None or os.path.exists(here), "a discovered compiler is a real path", here)
check(here_san is None or os.path.exists(here_san), "the sanitizer-capable compiler is real too",
      here_san)
check(not (here_san and not here), "a sanitizer-capable compiler also satisfies the plain probe")
if here is None:
    print("NOTE  no C++ compiler on this host: the suites below can still be tested for the "
          "skip path, but their real run is unverified here.")

# ---------------------------------------------------------------------------
# 2. skip() prints an honest line and records it
# ---------------------------------------------------------------------------
saved_skips = list(NT.SKIPS)
NT.SKIPS[:] = []
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = NT.skip("native subset: example")
text = buf.getvalue()
check(rc == NT.SKIP_EXIT, "skip() returns the skip code")
check(text.splitlines()[0].startswith("SKIP  native subset: example:"),
      "the skip line names the check and then the reason", text.splitlines()[0][:100])
check("C++17 compiler" in text and "g++" in text,
      "the skip line names the toolchain it wanted", text.splitlines()[0][:120])
check("NOT verified here" in text, "the skip line refuses to imply verification")
check(len(NT.SKIPS) == 1, "the skip is recorded once")

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    NT.skip("native subset: example")
check(len(NT.SKIPS) == 1, "the same skip is not recorded twice", len(NT.SKIPS))

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    NT.skip("native subset: sanitized example", sanitizers=True)
check("AddressSanitizer" in buf.getvalue(),
      "a sanitizer skip explains that it is the sanitizer that is missing")
check(len(NT.SKIPS) == 2, "a different skip is a second record")

check(NT.exit_code([]) == NT.SKIP_EXIT,
      "with skips recorded, a clean suite still exits 77 (not 0)")
NT.SKIPS[:] = []
check(NT.exit_code([]) == 0, "with no skips and no failures, a suite exits 0")
check(NT.exit_code(["a failure"]) == 1, "a failure beats a skip: exit 1")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    NT.skip("native subset: example")
check(NT.exit_code(["a failure"]) == 1, "a failure still beats a skip when both are present")
NT.SKIPS[:] = saved_skips

# ---------------------------------------------------------------------------
# 3. the seven native suites: 77 when they cannot run, 0 when they can
# ---------------------------------------------------------------------------
for name, filename, has_source in NATIVE_SUITES + QATS_NATIVE_SUITES + SMCVP_NATIVE_SUITES:
    rc, text = run_suite(filename, force_no_native=True)
    check(rc == NT.SKIP_EXIT,
          "%s exits 77 when the toolchain is absent" % name, "rc=%s" % rc)
    check(any(l.startswith("SKIP") for l in text.splitlines()),
          "%s says SKIP instead of dying on FileNotFoundError" % name)
    check(not any(l.startswith("FAIL") for l in text.splitlines()),
          "%s reports no failure when nothing was run" % name)
    if has_source:
        check("PASS" in text,
              "%s still reports the source-only checks it could run" % name)
    else:
        # A purely native suite must NOT print PASS when it ran nothing.
        check("PASS" not in [l[:4] for l in text.splitlines()],
              "%s prints no PASS at all when it ran nothing native" % name,
              [l for l in text.splitlines() if l.startswith("PASS")][:2])

for name, filename, _ in NATIVE_SUITES:
    rc, text = run_suite(filename, force_no_native=False)
    if here is None:
        check(rc == NT.SKIP_EXIT,
              "%s exits 77 on this compiler-less host" % name, "rc=%s" % rc)
    else:
        check(rc == 0, "%s still passes for real where g++ exists" % name,
              "rc=%s :: %s" % (rc, text.splitlines()[-1] if text.splitlines() else ""))

# ---------------------------------------------------------------------------
# 4. the gate's classification
# ---------------------------------------------------------------------------
check(G.classify("some-check", 0, "") == "PASS", "rc=0 is PASS")
check(G.classify("some-check", 77, "") == "SKIP", "rc=77 is SKIP, never PASS")
check(G.classify("some-check", 1, "") == "FAIL", "rc=1 is FAIL")
check(G.classify("release-gate", 0, "  GO (with 0 warning(s))") == "PASS",
      "the release gate passes on GO")
check(G.classify("release-gate", 0, "  NO-GO - invariants broken") == "FAIL",
      "the release gate fails on NO-GO even with rc=0")
check(G.classify("release-gate", 77, "SKIP nothing") == "SKIP",
      "a skipped release gate is a skip, not a pass")

check(G.skip_reason("PASS a\nSKIP  native subset: no compiler here\n") ==
      "native subset: no compiler here", "skip_reason lifts the reason without the marker",
      G.skip_reason("SKIP  native subset: no compiler here"))
check(G.skip_reason("PASS only") == "skipped (no reason printed)",
      "skip_reason admits when no reason was printed")

# ---------------------------------------------------------------------------
# 5. the verdict - the part a human reads
# ---------------------------------------------------------------------------
def rows(*statuses):
    out = []
    for i, status in enumerate(statuses):
        rc = {"PASS": 0, "SKIP": 77, "FAIL": 1}[status]
        out.append(("check-%d" % i, status, rc, 0.1, "/dev/null"))
    return out


code, lines = G.verdict(rows("PASS", "PASS"))
joined = "\n".join(lines)
check(code == 0 and "OFFLINE GO:" in joined and "PARTIAL" not in joined,
      "all PASS is a clean GO", joined)
check("2/2" in joined, "the clean GO counts the checks", joined)

code, lines = G.verdict(rows("PASS", "SKIP", "PASS"))
joined = "\n".join(lines)
check(code == 0, "a skip is not a NO-GO on a desktop without a compiler")
check("OFFLINE GO (PARTIAL)" in joined, "a skip downgrades the verdict to PARTIAL", joined)
check("2/3 verified" in joined and "1 SKIPPED" in joined,
      "PARTIAL states exactly how much was verified", joined)
check("check-1" in joined, "PARTIAL names the skipped check", joined)
check("did NOT run here" in joined, "PARTIAL says the skipped checks did not run", joined)
check("--require-native" in joined, "PARTIAL points at the strict mode", joined)

code, lines = G.verdict(rows("PASS", "SKIP", "PASS"), require_native=True)
joined = "\n".join(lines)
check(code == 1, "--require-native turns a skip into a NO-GO", code)
check("OFFLINE NO-GO" in joined, "--require-native prints NO-GO", joined)
check("check-1" in joined, "--require-native names the check that could not run", joined)
check("by request, not a defect" in joined,
      "--require-native says the NO-GO is a policy choice, not a fault", joined)

code, lines = G.verdict(rows("PASS", "FAIL", "SKIP"))
joined = "\n".join(lines)
check(code == 1 and "OFFLINE NO-GO" in joined and "check-1" in joined,
      "a real failure is a NO-GO even when another check merely skipped", joined)
check("PARTIAL" not in joined, "a failure is never softened into PARTIAL", joined)

code, lines = G.verdict(rows("FAIL", "SKIP"), require_native=True)
check(code == 1 and "check-0" in "\n".join(lines),
      "with both, the failing check is still named first")

# ---------------------------------------------------------------------------
# 6. the curated list itself
# ---------------------------------------------------------------------------
names = [name for name, _ in G.CHECKS]
check(len(names) == len(set(names)), "no curated check is listed twice")
check("native-toolchain" in names, "this suite is part of the curated gate")
curated_native = [n for n, _, _ in NATIVE_SUITES if n in names]
check(len(curated_native) == len(NATIVE_SUITES),
      "all seven native suites are still in the curated gate", curated_native)
curated_qats = [n for n, _, _ in QATS_NATIVE_SUITES if n in names]
check(len(curated_qats) == len(QATS_NATIVE_SUITES),
      "the three QATS native suites are in the curated gate", curated_qats)
curated_smcvp = [n for n, _, _ in SMCVP_NATIVE_SUITES if n in names]
check(len(curated_smcvp) == len(SMCVP_NATIVE_SUITES),
      "the chart-hygiene and SMC+VP engine suites are in the curated gate", curated_smcvp)
check(all(isinstance(cmd, list) and all(isinstance(a, str) for a in cmd)
          for _, cmd in G.CHECKS), "every curated command is a list of strings")
print("NOTE  curated checks: %d" % len(names))

if FAILS:
    print("%d of %d native-skip test(s) failed" % (len(FAILS), COUNT[0]))
    raise SystemExit(1)
print("%d native-skip checks passed; a skip is visible, never a pass." % COUNT[0])
