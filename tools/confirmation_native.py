#!/usr/bin/env python3
"""Build/run QSMC_ConfirmationEngine.mq5 against the typed native shim.

This is an offline evidence harness, NOT MetaEditor F7, NOT Strategy Tester and
NOT a live MT5 demo. It reuses qats_native.py's mechanical MQL5->C++ rewrite and
strict C++17 warning set, but supplies a confirmation-engine translation unit:
the CE shim overlay, the real EA source, and the CE unit/replay driver.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import qats_native as qn  # noqa: E402

EA_SOURCE = os.path.join(ROOT, "MQL5", "Experts", "QSMC_ConfirmationEngine.mq5")
SIM_DIR = os.path.join(ROOT, "tools", "qats_sim")
CE_SHIM = os.path.join(SIM_DIR, "qsmc_ce_shim.h")
CE_DRIVER = os.path.join(SIM_DIR, "qsmc_ce_driver.inc")
OUT_DIR = os.path.join(ROOT, "out", "confirmation_native")
TAG = "ce"


def configure() -> None:
    """Point qats_native's translation-unit writer at the CE harness."""
    qn.SHIM = CE_SHIM
    qn.DRIVER = CE_DRIVER
    qn.OUT_DIR = OUT_DIR
    os.makedirs(OUT_DIR, exist_ok=True)


def lint_engine():
    with open(EA_SOURCE, "r", encoding="utf-8") as fh:
        return qn.mql5_lint(fh.read())


def build_engine(strict: bool = True, sanitize: bool = False):
    configure()
    return qn.build(EA_SOURCE, TAG, "-O2", strict, sanitize, OUT_DIR)


def run_engine(exe: str, args=None, timeout: int = 120):
    cmd = [exe] + (args or [])
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, timeout=timeout)


def run_json_mode(mode: str):
    """Build the CE translation unit, run `mode`, and return parsed JSON.

    This is the shared entry point for the replay/backtest writers. It is still
    an offline host harness: NOT MetaEditor, NOT Strategy Tester, NOT a live
    MT5 demo run. It raises on a lint/build/mode failure; a missing C++17
    compiler returns a SKIP payload with qats_native.SKIP_EXIT.
    """
    configure()
    lint = lint_engine()
    if lint:
        raise RuntimeError("confirmation-native MQL5 lint: " + "; ".join(lint[:3]))
    exe, rc, diag = build_engine(True, False)
    if rc == qn.SKIP_EXIT:
        return {"status": "SKIP", "reason": diag}, qn.SKIP_EXIT
    if rc != 0 or not exe:
        raise RuntimeError("confirmation-native build failed (rc=%d): %s" % (rc, diag[-2000:]))
    proc = run_engine(exe, [mode])
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise RuntimeError("confirmation-native %s produced no JSON: %s" % (mode, proc.stdout[-1000:]))
    data = json.loads(lines[-1])
    if proc.returncode != 0 or data.get("status") != "PASS":
        raise RuntimeError("confirmation-native %s failed (rc=%d): %s" %
                           (mode, proc.returncode, data.get("status")))
    return data, proc.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit-only", action="store_true", help="write translation unit, do not compile")
    ap.add_argument("--no-strict", action="store_true", help="disable -Werror warning classes")
    ap.add_argument("--sanitize", action="store_true", help="ASan/UBSan build")
    ap.add_argument("--no-run", action="store_true", help="build but do not run selftest")
    args = ap.parse_args(argv)

    configure()
    lint = lint_engine()
    for problem in lint:
        print("LINT  " + problem)

    if args.emit_only:
        main_cpp, ea_inc = qn.write_translation_unit(EA_SOURCE, OUT_DIR, TAG)
        print(main_cpp)
        print(ea_inc)
        return 0

    exe, rc, diag = build_engine(not args.no_strict, args.sanitize)
    if rc == qn.SKIP_EXIT:
        print("SKIP  confirmation-native: " + diag)
        return qn.SKIP_EXIT
    if diag.strip():
        print(diag.rstrip())
    if rc != 0 or lint:
        print("confirmation-native: FAILED (host build rc=%d, lint problems=%d)" % (rc, len(lint)))
        return 1
    print("confirmation-native: host build OK -> %s" % exe)
    print("This is NOT MetaEditor. F7 remains the compile gate.")
    if args.no_run:
        return 0
    proc = run_engine(exe, ["selftest"])
    if proc.stdout.strip():
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        print("confirmation-native: selftest FAILED (rc=%d)" % proc.returncode)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
