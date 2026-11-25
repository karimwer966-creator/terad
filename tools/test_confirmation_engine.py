#!/usr/bin/env python3
"""Confirmation-engine native selftest + disarmed shipping contract.

NOT MetaEditor F7, NOT Strategy Tester and NOT a live MT5 demo. Exit 77 means
the host has no C++17 compiler; the curators classify that as SKIP.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import confirmation_native as cn  # noqa: E402

EA = ROOT / "MQL5" / "Experts" / "QSMC_ConfirmationEngine.mq5"
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
    data, rc = cn.run_json_mode("selftest")
    if data.get("status") == "SKIP":
        print("SKIP  confirmation-engine: no usable C++17 host compiler")
        return rc
    check(data.get("status") == "PASS", "native selftest status is PASS", str(data.get("status")))
    check(data.get("failed") == 0, "native selftest reports zero failures", str(data.get("failed")))
    check(int(data.get("checks", 0)) >= 331, "native selftest covers at least 331 checks",
          str(data.get("checks")))

    src = EA.read_text(encoding="utf-8")
    inputs = re.findall(r"^input\s+(?:bool|int|double|string)\s+(Inp\w+)\s*=", src, re.M)
    check(len(inputs) == 55, "the additive EA declares 55 inputs", str(len(inputs)))
    check(len(set(inputs)) == 55, "every confirmation-engine input name is unique")
    required = {
        "InpDryRun": "true", "InpAllowLiveOrders": "false",
        "InpAllowRealTrading": "false", "InpMasterEnable": "true",
        "InpKillSwitch": "false", "InpUseAIAgent": "false",
    }
    for name, want in required.items():
        m = re.search(r"^input\s+bool\s+" + name + r"\s*=\s*(true|false)\s*;", src, re.M)
        check(m is not None and m.group(1) == want, "%s ships as %s" % (name, want),
              m.group(1) if m else "missing")
    check("INIT REFUSED: REAL or CONTEST account detected" in src,
          "OnInit refuses REAL and CONTEST before the first tick")
    check("if(InpDryRun || InpAllowLiveOrders==false)" in src,
          "CE_ManagePositions has the disarmed early-return guard")
    check("WebRequest(" not in src, "the CE EA makes no WebRequest call")
    check("g_trade.PositionClosePartial" in src and "g_trade.PositionModify" in src,
          "the new G9 exception is exercised by a real mutating trade path")

    gate = subprocess.run([sys.executable, "tools/check_release_gate.py"], cwd=str(ROOT),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    check(gate.returncode == 0, "release gate is GO with G9 active", "rc=%d" % gate.returncode)
    check("G9 confirmation engine ships DISARMED" in gate.stdout,
          "release gate names the G9 disarmed contract")

    rules = subprocess.run([sys.executable, "tools/mql5_rules.py"], cwd=str(ROOT),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    check(rules.returncode == 0, "MQL5 dialect rules include the new EA", "rc=%d" % rules.returncode)
    check("QSMC_ConfirmationEngine.mq5 (confirmation)" in rules.stdout,
          "the new EA is linted as its own translation unit")

    print("-" * 74)
    print("confirmation-engine checks: %d  failures: %d" % (COUNT[0], len(FAILS)))
    print("This is a strict host build/selftest, NOT MetaEditor F7 and NOT a live MT5 demo.")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
