#!/usr/bin/env python3
"""Verify the deterministic 2026-11-25 replay report and CSV.

NOT MetaEditor F7, NOT Strategy Tester, NOT broker ticks and NOT a live demo.
Exit 77 means no C++17 host compiler was available.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "CONFIRMATION_ENGINE_REPLAY_2026-11-25.md"
CSV = ROOT / "docs" / "confirmation_replay_2026-11-25.csv"
FAILS = []
COUNT = [0]


def check(ok, label, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + label)
    else:
        print("FAIL  " + label + (("  [" + detail + "]") if detail else ""))
        FAILS.append(label)


def main() -> int:
    proc = subprocess.run([sys.executable, "tools/confirmation_replay.py", "--check"],
                          cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode == 77:
        print("SKIP  confirmation replay: no usable C++17 host compiler")
        return 77
    check(proc.returncode == 0, "replay artefacts are deterministic and current", proc.stdout[-400:])
    check(REPORT.is_file(), "replay report ships")
    check(CSV.is_file(), "replay CSV ships")

    text = REPORT.read_text(encoding="utf-8") if REPORT.is_file() else ""
    lowered = text.lower().replace("**", "")
    for needle in ("Verdict: PASS", "not MetaEditor F7", "not Strategy Tester",
                   "SESSION_PERMISSION", "ENTER_DRY_RUN", "MITIGATED", "AI_TIMEOUT",
                   "AI_DIRECTION_MISSING", "KILL_SWITCH", "No live trading"):
        check(needle.lower() in lowered, "report records " + needle)

    rows = []
    if CSV.is_file():
        with CSV.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
    check(len(rows) == 10, "CSV has one 42-column header and nine evaluation rows", str(len(rows)))
    check(bool(rows) and len(rows[0]) == 42, "CSV header has 42 columns",
          str(len(rows[0]) if rows else 0))
    check(all(len(row) == 42 for row in rows[1:]), "every CSV row has 42 columns")
    check(bool(rows) and "zone" in rows[0] and "reject" in rows[0],
          "CSV header exposes zone and reject fields")
    check(any(len(row) > 21 and row[21] == "SESSION_PERMISSION" for row in rows[1:]),
          "CSV records session-permission near misses")
    check(any(len(row) > 20 and row[20] == "ENTER_DRY_RUN" for row in rows[1:]),
          "CSV records dry-run entries without sending orders")

    print("-" * 74)
    print("confirmation replay checks: %d  failures: %d" % (COUNT[0], len(FAILS)))
    print("This validates generated replay artefacts, NOT F7 and NOT a live MT5 demo.")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
