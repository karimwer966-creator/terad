#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every active `tools/...` and `docs/...` reference must resolve to a shipped file.

WHY THIS EXISTS
---------------
The shipped analytical host carried six comments naming harnesses that are NOT
in this checkout, including two claims that incremental/full replay equivalence
was "machine-verified by tools/replay_equiv_test.py (700+ randomized trials)".
An operator reading the source would reasonably believe a verification suite
exists and has been run. It does not exist in this repository, so the claim is
unverifiable here. The historical docs are frozen snapshots; the ACTIVE source
is not allowed to point at absent checks or assert their results.

The same defect class exists for documents. Seven `// was X` input comments in
nadir2.mq5 cited docs/SIGNAL_VISIBILITY_DIAGNOSIS.md as the record of seven
relaxed thresholds, and that file did not exist in this repository - so the only
record of the change was the comment claiming a record existed. Nine further
dangling docs/ citations were found at the same time and are named in
KNOWN_DANGLING_DOCS; a tenth citation now fails the build.

This gate scans the tracked corpus (not scratch/out logs), finds every literal
reference to a file under tools/ or docs/, and fails when the referenced path is
not a regular file (paths wrapped across two lines by a fixed-width comment box
are re-joined first). It is a documentation/reference integrity check, not an
MQL5 compile, not a replay test and not a trading-behaviour change.

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
DOC_REF = re.compile(r"(?<![\w/.-])docs/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+")
SELF = "tools/test_tool_reference_integrity.py"

# docs/ paths cited by shipped files that are ABSENT from this checkout. Each
# entry was verified on 2026-11-27: no file of that name exists in docs/ or
# docs/history/, and no renamed successor could be identified. They survive as
# historical citations - the comment around each explains why a line exists -
# and this set is the ONLY place a dangling docs/ path may live: the gate fails
# on any new one, so the set can shrink but cannot grow silently.
# docs/SIGNAL_VISIBILITY_DIAGNOSIS.md belonged here until v6.6.25 wrote it: seven
# `// was X` input comments in nadir2.mq5 cited it and it did not exist, so the
# only record of seven relaxed thresholds was the comment itself. That is the
# defect this half of the gate exists to stop repeating.
KNOWN_DANGLING_DOCS = frozenset({
    "docs/ARCHITECTURE.md",
    "docs/KLJ_V6.5.0_REACTION_LAYER_AUDIT.md",
    "docs/KLJ_V6.5.0_REACTION_LAYER_REPORT.md",
    "docs/KLJ_V6.5.1_FORENSIC_AUDIT.md",
    "docs/KLJ_V6.5.2_FILE_AUDIT.md",
    "docs/KLJ_V6.5.4_REACTION_CONFLICT_FIX.md",
    "docs/PART_A_REPAIR_HANDOFF.md",
    "docs/PREDICTIVE_ENGINE_AUDIT.md",
    "docs/QSMC_UNIFIED_DEMO_REAL_2026-11-09.md",
})


def docs_ref_resolves(text, m):
    """(exists, target) for one docs/ reference match.

    Fixed-width comment boxes wrap a long path across two lines:
    "docs/KLJ_V6.6.0_SIGNAL_" on one line, "ARBITRATION.md" on the next. The
    regex can only match up to the last dot on the first line, so it reports
    "docs/KLJ_V6.6.0". When the match is cut mid-token the remainder of the line
    and the first token of the next one are re-joined before the reference is
    called dangling - without that, a correct citation reads as a defect.
    """
    target = m.group(0)
    if (ROOT / target).is_file():
        return True, target
    rest = text[m.end():]
    if rest[:1] == "_" or rest[:1].isalnum():
        lines = rest.split("\n")
        same_line = re.match(r"[A-Za-z0-9_.\-]*", rest).group(0)
        if len(lines) > 1:
            tok = re.match(r"[A-Za-z0-9_.]+", lines[1].lstrip("/|*# \t"))
            if tok:
                joined = target + same_line + tok.group(0)
                if (ROOT / joined).is_file():
                    return True, joined
    return False, target


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
    doc_missing = []
    doc_known = []
    doc_resolved = 0
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
        for m in DOC_REF.finditer(text):
            exists, target = docs_ref_resolves(text, m)
            if exists:
                doc_resolved += 1
                if args.verbose:
                    print("PASS  %s -> %s" % (rel, target))
            elif target in KNOWN_DANGLING_DOCS:
                doc_known.append((rel, target, text.count("\n", 0, m.start()) + 1))
            else:
                doc_missing.append((rel, target, text.count("\n", 0, m.start()) + 1))

    # The docs/ half must be able to fail, or it is a tautology: the scan is run
    # against a path nobody has written and has to report it.
    probe_text = "see docs/THIS_PATH_IS_NOT_IN_THE_REPOSITORY.md for the proof"
    probe_m = DOC_REF.search(probe_text)
    probe_caught = bool(probe_m) and not docs_ref_resolves(probe_text, probe_m)[0]
    if not probe_caught:
        print("FAIL  the docs/ scan cannot flag a dangling path (the check is a tautology)")

    if missing or doc_missing or not probe_caught:
        for rel, target, line in sorted(missing):
            print("FAIL  %s:%d references missing %s" % (rel, line, target))
        for rel, target, line in sorted(doc_missing):
            print("FAIL  %s:%d references missing %s" % (rel, line, target))
        print("-" * 74)
        print("tool-reference integrity: %d resolved, %d missing, %d files scanned"
              % (resolved, len(missing), files))
        print("doc-reference integrity:    %d resolved, %d missing, %d known-dangling"
              % (doc_resolved, len(doc_missing), len(set(t for _r, t, _l in doc_known))))
        print("A source comment may describe a historical harness, but it must not")
        print("name an absent tools/ path as a current verification asset, and it")
        print("must not cite a docs/ file that is not in the checkout.")
        return 1

    print("-" * 74)
    print("tool-reference integrity: %d resolved, 0 missing, %d files scanned"
          % (resolved, files))
    print("doc-reference integrity:    %d resolved, 0 missing, %d known-dangling (%s)"
          % (doc_resolved, len(set(t for _r, t, _l in doc_known)),
             ", ".join(sorted(set(t for _r, t, _l in doc_known))) or "none"))
    print("All active tools/ and docs/ references resolve, except the known-dangling")
    print("historical citations named in KNOWN_DANGLING_DOCS. NOT an MQL5 compile.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
