#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every active `tools/...` reference must resolve to a shipped file.

WHY THIS EXISTS
---------------
The shipped analytical host carried six comments naming harnesses that are NOT
in this checkout, including two claims that incremental/full replay equivalence
was "machine-verified by tools/replay_equiv_test.py (700+ randomized trials)".
An operator reading the source would reasonably believe a verification suite
exists and has been run. It does not exist in this repository, so the claim is
unverifiable here. The historical docs are frozen snapshots; the ACTIVE source
is not allowed to point at absent checks or assert their results.

This gate scans the tracked corpus (not scratch/out logs), finds every literal
reference to a file under tools/, and fails when the referenced path is not a
regular file. It is a documentation/reference integrity check, not an MQL5
compile, not a replay test and not a trading-behaviour change.

Usage:
  python3 tools/test_tool_reference_integrity.py [--verbose]
"""
from __future__ import print_function

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Any extension, not just .py: presets, generated .json and native sources are
# also referenced as tools/<path>. The negative lookbehind keeps a URL suffix
# such as ".../tools/check.py" from being counted as a repository-relative ref.
REF = re.compile(r"(?<![\w/.-])tools/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+")
SELF = "tools/test_tool_reference_integrity.py"


def tracked_files():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=str(ROOT))
    for token in raw.split(b"\0"):
        if not token:
            continue
        rel = token.decode("utf-8", "surrogateescape")
        p = ROOT / rel
        if not p.is_file() or rel == SELF:
            continue
        # Skip binary assets. A NUL in the first 8 KiB is enough in this repo.
        with p.open("rb") as fh:
            if b"\0" in fh.read(8192):
                continue
        yield rel, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="print every resolved reference")
    args = ap.parse_args()

    missing = []
    resolved = 0
    files = 0
    for rel, p in tracked_files():
        files += 1
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in REF.finditer(text):
            target = m.group(0)
            if (ROOT / target).is_file():
                resolved += 1
                if args.verbose:
                    print("PASS  %s -> %s" % (rel, target))
            else:
                missing.append((rel, target, text.count("\n", 0, m.start()) + 1))

    if missing:
        for rel, target, line in sorted(missing):
            print("FAIL  %s:%d references missing %s" % (rel, line, target))
        print("-" * 74)
        print("tool-reference integrity: %d resolved, %d missing, %d files scanned"
              % (resolved, len(missing), files))
        print("A source comment may describe a historical harness, but it must not")
        print("name an absent tools/ path as a current verification asset.")
        return 1

    print("-" * 74)
    print("tool-reference integrity: %d resolved, 0 missing, %d files scanned"
          % (resolved, files))
    print("All active tools/ references resolve. NOT an MQL5 compile or replay test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
