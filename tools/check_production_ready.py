#!/usr/bin/env python3
"""One-command curated OFFLINE production-readiness gate for QSMC v6.6.20.

This is deliberately not a MetaEditor compile, not a backtest, and not a proof
of profitability. It runs the mechanical/release/safety checks that can be
proven in this repository and prints OFFLINE GO / OFFLINE NO-GO.

The historical line-number audit suites (docs freshness, declutter, resolver,
scalping, weighted gates, decision journal, tactical line pins, zone provenance,
gate profile, phase-5 enum pin) are not part of this curated gate because they
were already stale against the shipped source layout. The release gate, static
checker, execution-safety contracts and the runtime/native subsets below are.

Usage:
  python3 tools/check_production_ready.py
  python3 tools/check_production_ready.py --timeout 240
"""
from __future__ import print_function

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "production")

CHECKS = [
    ("python-parse", [sys.executable, "-m", "py_compile"] +
     [os.path.join("tools", f) for f in sorted(os.listdir(os.path.join(ROOT, "tools")))
      if f.endswith(".py")]),
    ("mql5-rules", [sys.executable, "tools/mql5_rules.py", "--quiet"]),
    ("static-check", [sys.executable, "tools/static_check.py"]),
    ("comment-integrity", [sys.executable, "tools/test_comment_integrity.py"]),
    ("tick-performance", [sys.executable, "tools/test_tick_performance.py"]),
    ("runtime-diagnostics", [sys.executable, "tools/test_runtime_diagnostics.py"]),
    ("ux1-master-switch", [sys.executable, "tools/test_ux1_master_switch.py"]),
    ("display-authority", [sys.executable, "tools/test_display_authority.py"]),
    ("price-provenance", [sys.executable, "tools/test_price_provenance.py"]),
    ("instance-identity", [sys.executable, "tools/test_instance_identity.py"]),
    ("input-fingerprint-parser", [sys.executable, "tools/test_input_fingerprint_parser.py"]),
    ("input-fingerprint-manifest", [sys.executable, "tools/generate_input_fingerprint.py", "--check"]),
    # A .set is an input surface an operator loads with one click: it must never
    # drift from the source (the 2026-11-06 practical preset was truncated).
    ("set-presets", [sys.executable, "tools/generate_set_presets.py", "--check"]),
    ("autotrader-contract", [sys.executable, "tools/test_autotrader_contract.py"]),
    ("execution-safety", [sys.executable, "tools/test_execution_safety.py"]),
    ("diag-bridge", [sys.executable, "tools/test_diag_bridge.py"]),
    ("historical-atr", [sys.executable, "tools/test_historical_atr_contract.py"]),
    ("volatility-window", [sys.executable, "tools/test_volatility_window.py"]),
    ("early-break", [sys.executable, "tools/test_early_break.py"]),
    ("arbiter-parity", [sys.executable, "tools/test_arbiter.py"]),
    ("scanner-arithmetic", [sys.executable, "tools/test_scanners.py"]),
    ("quant-stats", [sys.executable, "tools/test_quant_stats.py"]),
    ("structure-events", [sys.executable, "tools/test_structure.py"]),
    ("zone-scoring", [sys.executable, "tools/test_zone_scoring.py"]),
    ("edgebook", [sys.executable, "tools/test_edgebook_contract.py"]),
    ("liquidity-value-runtime", [sys.executable, "tools/test_liquidity_value_runtime.py"]),
    ("dashboard-clarity", [sys.executable, "tools/test_dashboard_clarity.py"]),
    ("incident-compact", [sys.executable, "tools/test_incident_compact.py"]),
    ("orderblock-lifecycle", [sys.executable, "tools/test_orderblock_lifecycle.py"]),
    ("causal-chain-regressions", [sys.executable, "tools/test_causal_chain_regressions.py"]),
    ("zre-signal-role", [sys.executable, "tools/test_zre_signal_role.py"]),
    ("unified-decision-contract", [sys.executable, "tools/test_unified_decision_contract.py"]),
    ("unified-decision-runtime", [sys.executable, "tools/test_unified_decision_runtime.py"]),
    ("resolver-runtime", [sys.executable, "tools/test_resolver_runtime.py"]),
    ("scanner-snapshot", [sys.executable, "tools/test_scanner_snapshot.py"]),
    ("phase2-modules", [sys.executable, "tools/test_phase2_modules.py"]),
    ("phase3-wyckoff", [sys.executable, "tools/test_phase3_wyckoff.py"]),
    ("phase4-priceaction", [sys.executable, "tools/test_phase4_priceaction.py"]),
    ("phase6-confluence", [sys.executable, "tools/test_phase6_confluence.py"]),
    ("phase7-riskmodel", [sys.executable, "tools/test_phase7_riskmodel.py"]),
    ("scenario-geometry", [sys.executable, "tools/check_scenario_geometry.py"]),
    ("host-patch-idempotent", [sys.executable, "tools/apply_qsmc_arb_patch.py", "--check"]),
    ("release-gate", [sys.executable, "tools/check_release_gate.py"]),
]


def tail(text, n=4):
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.chdir(ROOT)
    results = []
    print("=" * 76)
    print(" QSMC v6.6.20 - curated OFFLINE production-readiness gate")
    print(" NOT a compile, NOT a backtest, NOT a broker-latency measurement")
    print("=" * 76)
    for name, cmd in CHECKS:
        log = os.path.join(OUT, name + ".log")
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=args.timeout)
            text = proc.stdout.decode("utf-8", errors="replace")
            rc = proc.returncode
        except subprocess.TimeoutExpired as exc:
            text = (exc.stdout or b"").decode("utf-8", errors="replace")
            text += "\nTIMEOUT after %ss\n" % args.timeout
            rc = 124
        with open(log, "w", encoding="utf-8") as f:
            f.write(text)
        ok = (rc == 0)
        if name == "release-gate":
            ok = ok and "GO (with" in text and "NO-GO" not in text
        results.append((name, ok, rc, time.time() - t0, log))
        print("%-28s %s  rc=%s  %.1fs" % (name, "PASS" if ok else "FAIL", rc, time.time() - t0))
        if not ok:
            print(tail(text))
    failed = [r for r in results if not r[1]]
    summary = os.path.join(OUT, "SUMMARY.txt")
    with open(summary, "w", encoding="utf-8") as f:
        f.write("QSMC v6.6.20 curated offline production-readiness summary\n")
        f.write("checks=%d failed=%d\n" % (len(results), len(failed)))
        for name, ok, rc, dt, log in results:
            f.write("%s rc=%s %.1fs %s\n" % ("PASS" if ok else "FAIL", rc, dt, name))
        f.write("\nManual gates still required: MetaEditor F7 (0 errors), banner v6.6.20,\n")
        f.write("EA handshake OK, demo/paper observation, and the go-live runbook before real money.\n")
    print("-" * 76)
    if failed:
        print("OFFLINE NO-GO: %d/%d checks failed. See %s" % (len(failed), len(results), OUT))
        return 1
    print("OFFLINE GO: %d/%d curated checks passed." % (len(results), len(results)))
    print("Summary: %s" % summary)
    print("Still manual: F7 in MetaEditor, v6.6.20 banner, EA iCustom handshake, demo/paper run.")
    print("Real money only after docs/QSMC_GO_LIVE_RUNBOOK.md; the EA ships inert + dry-run + demo-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
