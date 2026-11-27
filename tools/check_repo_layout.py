#!/usr/bin/env python3
"""Repository layout gate: the tree an operator clones must be the tree the docs describe.

WHY THIS EXISTS
---------------
Every defect this file checks was found by hand, one at a time, and each of them
was invisible to compilation:

  * `presets/` shipped ONE file while 21 preset paths were named in runbooks, so
    "load preset X" was an instruction nobody could follow and the packaging
    script could not copy the files it promised;
  * `presets/Quantum_XAUUSD_PRODUCTION.set` is a QATS preset and had nothing to
    do with QSMC, yet sat unlabelled next to the QSMC presets until this gate
    forced every preset to declare `; source:`;
  * six release reports lived at the repository root while every other document
    lived in `docs/`, so the first screen of a fresh checkout was history rather
    than the product;
  * shipped `.mq5` files declared versions two to eight releases behind the host
    (`6.614`, `6.615`, `v6.6.0`), which is exactly how an operator identifies a
    stale build by its banner;
  * `tools/fixtures/legacy_presets/` survived as the "real" preset surface after
    the presets moved into `presets/`, so tests validated files nobody loads.

The checks are deliberately cheap (no compilers, no MT5) so they can run in the
first seconds of CI and in `check_production_ready.py` before the long suites.

Usage:
  python3 tools/check_repo_layout.py            # gate (exit 1 on any FAIL)
  python3 tools/check_repo_layout.py --verbose  # print every PASS line too
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAILS: list[str] = []
PASSES: list[str] = []


def ok(msg: str) -> None:
    PASSES.append(msg)


def fail(msg: str) -> None:
    FAILS.append(msg)


# --------------------------------------------------------------------------- #
# L1 - the root is an index, not a pile
# --------------------------------------------------------------------------- #
# Directories that are part of the product, and the only files allowed to sit at
# the root. A release report, a scratch note or a compiled binary belongs
# somewhere else; adding a new root file is a decision, not an accident.
ROOT_DIRS = {"docs", "MQL5", "presets", "tools", "out", ".git", ".github"}
ROOT_FILES = {
    "README.md",        # the index: what ships, how to verify it
    "INSTALL_AR.md",    # the install guide, in Arabic
    "nadir2.mq5",       # canonical host, mirrored into MQL5/Indicators
    "AUDIT.md",         # confirmation-engine Phase 1 source audit
    "DESIGN.md",        # confirmation-engine architecture and decisions
    "CHANGELOG.md",     # new inputs and defaults for the confirmation engine
    ".gitignore",
    ".gitattributes",
    "LICENSE",
}


def check_root() -> None:
    extra = []
    for entry in sorted(os.listdir(ROOT)):
        if entry in ROOT_DIRS or entry in ROOT_FILES:
            continue
        extra.append(entry)
    if extra:
        fail("L1 unexpected entries at the repository root: %s" % ", ".join(extra))
    else:
        ok("L1 root holds only %d index files and %d product directories"
           % (len(ROOT_FILES & set(os.listdir(ROOT))), len(ROOT_DIRS & set(os.listdir(ROOT)))))


# --------------------------------------------------------------------------- #
# L2 - one preset surface, not two
# --------------------------------------------------------------------------- #
DEAD_DIRS = ["tools/fixtures/legacy_presets"]


def check_dead_dirs() -> None:
    alive = [d for d in DEAD_DIRS if (ROOT / d).exists()]
    if alive:
        fail("L2 dead preset surface still present: %s (presets/ is the single source)"
             % ", ".join(alive))
    else:
        ok("L2 no duplicate preset surface (presets/ is canonical)")


# --------------------------------------------------------------------------- #
# L3 - the two copies of the host are one file
# --------------------------------------------------------------------------- #
def check_mirror() -> None:
    a = ROOT / "nadir2.mq5"
    b = ROOT / "MQL5" / "Indicators" / "nadir2.mq5"
    if not a.is_file() or not b.is_file():
        fail("L3 nadir2.mq5 is missing (root or MQL5/Indicators)")
        return
    if a.read_bytes() != b.read_bytes():
        fail("L3 root nadir2.mq5 and MQL5/Indicators/nadir2.mq5 differ "
             "(38 tools read the root copy; packaging refuses to ship a split tree)")
    else:
        ok("L3 root nadir2.mq5 is byte-identical to MQL5/Indicators/nadir2.mq5")


# --------------------------------------------------------------------------- #
# L4 - every preset is bound, formatted and referenced
# --------------------------------------------------------------------------- #
def check_presets() -> None:
    presets = sorted(p for p in (ROOT / "presets").glob("*.set"))
    if not presets:
        fail("L4 presets/ is empty")
        return
    corpus = []
    for pattern in ("docs/**/*.md", "*.md", "tools/*.py", ".github/workflows/*.yml"):
        for p in ROOT.glob(pattern):
            if p.is_file():
                corpus.append(io.open(p, encoding="utf-8", errors="replace").read())
    corpus_text = "\n".join(corpus)

    unbound, unreferenced, unformatted = [], [], []
    for p in presets:
        raw = p.read_bytes()
        text = raw.decode("utf-8", "replace")
        if "\r\n" not in text:
            unformatted.append(p.name)
        if not re.search(r"^;\s*source:\s*\S+", text, re.M):
            unbound.append(p.name)
        if p.name not in corpus_text:
            unreferenced.append(p.name)

    if unbound:
        fail("L4 preset(s) without a '; source:' line: %s" % ", ".join(unbound))
    if unformatted:
        fail("L4 preset(s) not CRLF (MetaTrader writes CRLF): %s" % ", ".join(unformatted))
    if unreferenced:
        fail("L4 preset(s) shipped but named in no document, tool or workflow: %s"
             % ", ".join(unreferenced))
    if not (unbound or unformatted or unreferenced):
        ok("L4 %d presets: all CRLF, all bound to a source, all referenced" % len(presets))


# --------------------------------------------------------------------------- #
# L5 - a path named in a document must exist
# --------------------------------------------------------------------------- #
# References that are correct to leave unresolved, with the reason. Each one is a
# historical audit describing where a file USED to be, or a runtime path that only
# exists on the operator's machine.
PATH_ALLOWLIST = {
    "MQL5/Experts/rollback/": "gitignored local rollback snapshots (audit history)",
    "MQL5/Include/QSMC/QSMC_DryRunAudit.mqh": "removed in v6.6.16; cited by its own RCA",
    "MQL5/Logs/": "runtime: the terminal writes these, not the repository",
    "presets/QSMC_v6.6.15_trial_5k.set": "historical $5k trial, frozen in docs/history/",
    "presets/QSMC_v6.6.16_trial_5k.set": "historical $5k trial, frozen in docs/history/",
}
PATH_RE = re.compile(r"(?<![\w/.-])((?:docs|presets|tools|MQL5|\.github)/[\w./-]+\.\w+)")


def check_paths() -> None:
    missing: dict[str, set[str]] = {}
    for p in sorted(ROOT.glob("**/*.md")):
        rel_parts = p.relative_to(ROOT).parts
        if rel_parts[0] in {".git", "out"}:
            continue
        text = io.open(p, encoding="utf-8", errors="replace").read()
        for m in PATH_RE.finditer(text):
            ref = m.group(1)
            if (ROOT / ref).exists():
                continue
            if any(ref.startswith(k) or ref == k for k in PATH_ALLOWLIST):
                continue
            missing.setdefault(ref, set()).add(str(p))
    if missing:
        for ref in sorted(missing):
            fail("L5 %s does not exist (named in %s)"
                 % (ref, ", ".join(sorted(missing[ref])[:3])))
    else:
        ok("L5 every repository path named in a document exists "
           "(%d documented exceptions)" % len(PATH_ALLOWLIST))


# --------------------------------------------------------------------------- #
# L6 - no shipped program declares itself older than the host
# --------------------------------------------------------------------------- #
# Files with their own release line. QATS is a separate product (v1.x) and the
# SMC+VP engine versions itself; both are shipped as-is and documented as such.
OWN_VERSION = {
    "MQL5/Experts/QuantumAutonomousTradingSystem.mq5": "separate product, v1.x line",
    "MQL5/Indicators/QSMC_SmcVpEngine.mq5": "separate engine, own version line",
}
PROP_RE = re.compile(r'#property\s+version\s+"([0-9.]+)"')


def _triple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.strip('"').split("."))


def check_versions() -> None:
    host_file = ROOT / "MQL5" / "Indicators" / "nadir2.mq5"
    m = PROP_RE.search(io.open(host_file, encoding="utf-8", errors="replace").read())
    if not m:
        fail("L6 the host declares no #property version")
        return
    host = m.group(1)
    stale, ahead = [], []
    seen = 0
    for sub in ("MQL5/Experts", "MQL5/Indicators", "MQL5/Scripts", "MQL5/Include"):
        for p in sorted((ROOT / sub).glob("**/*.mq5")) + sorted((ROOT / sub).glob("**/*.mqh")):
            rel = str(p.relative_to(ROOT))
            if rel in OWN_VERSION:
                continue
            for v in PROP_RE.findall(io.open(p, encoding="utf-8", errors="replace").read()):
                seen += 1
                if _triple(v) < _triple(host):
                    stale.append("%s declares %s (host %s)" % (rel, v, host))
                elif _triple(v) > _triple(host):
                    ahead.append("%s declares %s (host %s)" % (rel, v, host))
    if stale:
        for s in stale:
            fail("L6 stale build claim: " + s)
    if ahead:
        for s in ahead:
            fail("L6 build claim ahead of the host: " + s)
    if not (stale or ahead):
        ok("L6 all %d shipped #property version lines agree with the host (%s), "
           "%d separate-product exceptions" % (seen, host, len(OWN_VERSION)))

    # The companion's startup banner is the string the runbook tells the operator
    # to look for; it said v6.620 while the EA declared 6.622.
    ea = ROOT / "MQL5" / "Experts" / "QSMC_AutoTrader.mq5"
    banner = re.search(r'\[QSMC_AT\]\s+QSMC\s+(v[0-9.]+)\s+execution companion ON',
                       io.open(ea, encoding="utf-8", errors="replace").read())
    if banner:
        digits = host.replace(".", "")            # "6.622" -> "6622"
        if banner.group(1).lstrip("v").replace(".", "") != digits:
            fail("L6 %s start-up banner says %s but the host version is %s"
                 % (ea.name, banner.group(1), host))
        else:
            ok("L6 the companion's start-up banner matches the host (%s)" % banner.group(1))


# --------------------------------------------------------------------------- #
# L7 - one document, one home: docs/INDEX.md is the catalogue
# --------------------------------------------------------------------------- #
def check_index() -> None:
    docs = sorted(p for p in (ROOT / "docs").glob("*.md"))
    index = ROOT / "docs" / "INDEX.md"
    if not index.is_file():
        fail("L7 docs/INDEX.md is missing: %d documents with no catalogue"
             % (len(docs) - 1))
        return
    text = io.open(index, encoding="utf-8", errors="replace").read()
    orphans = [p.name for p in docs if p.name != "INDEX.md" and p.name not in text]
    if orphans:
        fail("L7 document(s) absent from docs/INDEX.md: %s" % ", ".join(orphans))
    else:
        ok("L7 all %d documents in docs/ appear in docs/INDEX.md" % (len(docs) - 1))

    # L8 - the count INDEX.md states in its own opening sentence. It said "97
    # documents" while the tree held 105, and nothing compared the two: the
    # number is prose, so no test read it. Now it is computed.
    m = re.search(r"(\d+)\s+documents\b", text)
    actual = len(docs) - 1
    if not m:
        fail("L8 docs/INDEX.md states no document count in its opening sentence")
    elif int(m.group(1)) != actual:
        fail("L8 docs/INDEX.md says %s documents, the tree holds %d - update the sentence"
             % (m.group(1), actual))
    else:
        ok("L8 the document count INDEX.md states (%s) equals the tree (%d)"
           % (m.group(1), actual))


# --------------------------------------------------------------------------- #
# L9 - an audit marker in shipped source is a promise the release note keeps
# --------------------------------------------------------------------------- #
def check_audit_markers() -> None:
    # AUD-06 and AUD-07 shipped in the EA, the root header and the host with the
    # marker written into the source comments, while CHANGELOG.md - the document
    # an operator reads to learn what a release changed - never mentioned either
    # one. Nothing compared the two, because the marker is a comment and the
    # release note is prose: no compiler reads either. A fix that changes
    # behaviour and never reaches the release note is a fix the operator cannot
    # find, and the note's own "behave exactly as the previous version" claim
    # goes quietly false on the same day.
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        fail("L9 CHANGELOG.md is missing, so no audit marker can be recorded")
        return
    note = io.open(changelog, encoding="utf-8", errors="replace").read()

    markers: dict[str, list[str]] = {}
    for sub in ("MQL5/Experts", "MQL5/Indicators", "MQL5/Scripts", "MQL5/Include"):
        for p in sorted((ROOT / sub).glob("**/*.mq5")) + sorted((ROOT / sub).glob("**/*.mqh")):
            text = io.open(p, encoding="utf-8", errors="replace").read()
            for marker in re.findall(r"\bAUD-[0-9]+\b", text):
                markers.setdefault(marker, []).append(str(p.relative_to(ROOT)))
    host = io.open(ROOT / "nadir2.mq5", encoding="utf-8", errors="replace").read()
    for marker in re.findall(r"\bAUD-[0-9]+\b", host):
        markers.setdefault(marker, []).append("nadir2.mq5")

    if not markers:
        fail("L9 no AUD-xx marker found in shipped source - the scan is broken, "
             "not the release note")
        return
    missing = sorted(m for m in markers if m not in note)
    for marker in missing:
        fail("L9 %s is marked in shipped source (%s) but CHANGELOG.md never "
             "records it - an operator reading the release note cannot find the "
             "behaviour change" % (marker, ", ".join(sorted(set(markers[marker])))))
    if not missing:
        ok("L9 all %d audit markers in shipped source are recorded in "
           "CHANGELOG.md (%s)" % (len(markers), ", ".join(sorted(markers))))


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    check_root()
    check_dead_dirs()
    check_mirror()
    check_presets()
    check_paths()
    check_versions()
    check_index()
    check_audit_markers()

    if verbose:
        for line in PASSES:
            print("PASS " + line)
    for line in FAILS:
        print("FAIL " + line)
    print("\nlayout: %d checks passed, %d failed" % (len(PASSES), len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
