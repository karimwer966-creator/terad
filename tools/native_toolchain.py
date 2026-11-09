#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NATIVE-TOOLCHAIN - is this host able to build the C++ subset harnesses?

WHY THIS EXISTS
---------------
Seven suites in this repository do not only read source: they compile a small
C++ subset (the real MQL5 method bodies, with the terminal API stubbed out) and
run it, because a percentile routine or a state machine can be wrong in ways
grep cannot see. That verification needs a host C++ compiler.

On a Linux CI runner `g++` is there. On an operator's Windows desktop it usually
is not, and the suites used to die with

    FileNotFoundError: [WinError 2] The system cannot find the file specified

which reads like a broken repository rather than "this machine cannot run this
check". Worse, the curated gate then reported those checks as failures, so a
perfectly healthy tree looked like a NO-GO on Windows.

The rule this module implements:

  * a suite that CANNOT run says so, with the toolchain it looked for;
  * it exits 77 ("skipped: prerequisite unavailable", the autotools convention)
    so the gate can tell "not verified here" apart from "verified and wrong";
  * it never reports PASS for something it did not run.

The distinction matters because the two outcomes need different actions:

    rc=0   verified on this host
    rc=77  NOT verified on this host - run it where a compiler exists (CI), and
           do not read the gate's GO as covering it
    rc!=0  verified and failed - a real defect

Set QSMC_NO_NATIVE=1 to force the skip path. That exists so the skip handling
itself can be tested on a machine that does have g++; it is not a switch for
turning red checks green, because a skip changes the verdict, never hides it.
"""
from __future__ import print_function

import os
import shutil
import subprocess
import tempfile

SKIP_EXIT = 77
FORCE_ENV = "QSMC_NO_NATIVE"
CANDIDATES = ("g++", "c++", "clang++")

SKIPS = []
_CACHE = {}


def _probe(cxx, flags):
    """Can this compiler build and link with `flags`? Cheap, cached, never raises."""
    with tempfile.TemporaryDirectory(prefix="qsmc-probe-") as d:
        src = os.path.join(d, "probe.cpp")
        exe = os.path.join(d, "probe")
        with open(src, "w") as fh:
            fh.write("int main(){return 0;}\n")
        try:
            proc = subprocess.run([cxx, "-std=c++17"] + list(flags) + [src, "-o", exe],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  timeout=180)
        except (OSError, subprocess.SubprocessError):
            return False
        return proc.returncode == 0


def compiler(sanitizers=False, refresh=False):
    """Path to a usable C++ compiler, or None when this host has none.

    sanitizers=True additionally requires AddressSanitizer/UndefinedBehavior
    support, because several harnesses link with -fsanitize=address,undefined.
    MinGW-w64 builds - the usual way to get g++ on Windows - do not provide it,
    so the check has to be made by building something, not by checking a name.
    """
    if os.environ.get(FORCE_ENV):
        return None
    key = bool(sanitizers)
    if key in _CACHE and not refresh:
        return _CACHE[key]
    flags = ["-fsanitize=address,undefined"] if sanitizers else []
    found = None
    for name in CANDIDATES:
        path = shutil.which(name)
        if not path:
            continue
        if flags and not _probe(path, flags):
            continue
        found = path
        break
    _CACHE[key] = found
    return found


def skip(label, sanitizers=False):
    """Record and print a skip. Never raises: the suite decides how to finish."""
    if sanitizers:
        what = ("g++/clang++ with AddressSanitizer support (MinGW builds "
                "usually lack it)")
    else:
        what = "C++17 compiler (%s)" % ", ".join(CANDIDATES)
    msg = "SKIP  %s: this host has no usable %s" % (label, what)
    if msg not in SKIPS:
        SKIPS.append(msg)
    print(msg)
    print("      NOT verified here. This suite needs that toolchain; the Linux")
    print("      CI run on every push has it, or install MSYS2/MinGW-w64.")
    return SKIP_EXIT


def exit_code(failures):
    """0 verified, 1 verified-and-failed, 77 ran nothing native."""
    if failures:
        return 1
    return SKIP_EXIT if SKIPS else 0
