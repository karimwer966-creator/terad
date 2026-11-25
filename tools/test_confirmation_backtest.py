#!/usr/bin/env python3
"""Verify the deterministic 3-month surrogate backtest report.

NOT MetaEditor F7, NOT Strategy Tester, NOT broker ticks and NOT evidence of a
trading edge. Exit 77 means no C++17 host compiler was available.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "CONFIRMATION_ENGINE_TEST_BACKTEST_2026-11-25.md"
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
    proc = subprocess.run([sys.executable, "tools/confirmation_backtest.py", "--check"],
                          cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode == 77:
        print("SKIP  confirmation backtest: no usable C++17 host compiler")
        return 77
    check(proc.returncode == 0, "backtest report is deterministic and current", proc.stdout[-400:])
    check(REPORT.is_file(), "backtest report ships")

    text = REPORT.read_text(encoding="utf-8") if REPORT.is_file() else ""
    lowered = text.lower().replace("**", "")
    for needle in ("Verdict: PASS", "92 days", "132480", "184 setups",
                   "0 orders sent", "not MetaTrader Strategy Tester",
                   "not evidence of profitability or an edge",
                   "Walk-forward split", "Parameter sensitivity",
                   "strict-A", "tight-spread", "SPREAD_INVALID",
                   "No live trading"):
        check(needle.lower() in lowered, "report records " + needle)
    digest = re.search(r"Canonical result SHA-256.*?`([0-9a-f]{64})`", text, re.S)
    check(digest is not None, "report pins a canonical SHA-256 digest")
    check("orders_sent=0" in text or "0 orders sent" in text,
          "report states the executor sent no orders")

    print("-" * 74)
    print("confirmation backtest checks: %d  failures: %d" % (COUNT[0], len(FAILS)))
    print("This validates a deterministic synthetic surrogate, NOT F7 or Strategy Tester.")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
