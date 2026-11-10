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
    # The over-optimisation defence. Offline arithmetic + MT5 config emission;
    # both decide whether a study may proceed, so both are in the curated gate.
    ("wfa-robustness", [sys.executable, "tools/test_wfa_robustness.py"]),
    ("why-no-trades", [sys.executable, "tools/test_why_no_trades.py"]),
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
    ("native-toolchain", [sys.executable, "tools/test_native_toolchain.py"]),
    ("defaults-match-preset", [sys.executable, "tools/test_defaults_match_preset.py"]),
    # v6.6.21: one classifier, one risk scale, one entry review - pinned end to end.
    ("signal-execution-profiles", [sys.executable, "tools/test_signal_execution_profiles.py"]),
    # v6.6.21 closed two holes this gate did not cover: the risk/limit audit that
    # pinned the un-scaled fixed-lot guard, and the QATS structural verifier that
    # caught a used-but-undeclared input. Both run in CI; they run here now too.
    # v6.6.22: F7 shipped 15 errors no suite in this tree looked for. These two
    # check the error CLASSES (const-reference writes, unknown struct members)
    # and the scalper envelope, at the gate rather than only in CI.
    ("compile-errors", [sys.executable, "tools/test_compile_errors.py"]),
    ("scalper-preset", [sys.executable, "tools/test_scalper_preset.py"]),
    ("at-risk-audit", [sys.executable, "tools/test_at_risk_audit.py"]),
    ("quantum-ea-verify", [sys.executable, "tools/verify_quantum_ea.py"]),
    ("release-gate", [sys.executable, "tools/check_release_gate.py"]),
]


SKIP_RC = 77


def classify(name, rc, text):
    """PASS / FAIL / SKIP from an exit code, with the release gate's own rule.

    77 is the autotools convention for "skipped: prerequisite unavailable". It
    is deliberately not PASS: several suites here compile and run the real MQL5
    method bodies with a host g++, and a Windows desktop without one cannot
    verify them. Reporting that as PASS would be a lie; reporting it as FAIL
    (which is what happened before) turns a healthy tree into a false NO-GO.
    """
    if rc == SKIP_RC:
        return "SKIP"
    ok = (rc == 0)
    if name == "release-gate":
        ok = ok and "GO (with" in text and "NO-GO" not in text
    return "PASS" if ok else "FAIL"


def skip_reason(text):
    for line in text.splitlines():
        if line.startswith("SKIP"):
            return line[4:].strip()
    return "skipped (no reason printed)"


def verdict(results, require_native=False):
    """(exit code, report lines) from [(name, status, rc, seconds, log)]."""
    failed = [r for r in results if r[1] == "FAIL"]
    skipped = [r for r in results if r[1] == "SKIP"]
    if require_native and skipped:
        failed = failed + skipped
    out = ["-" * 76]
    if failed:
        names = ", ".join(r[0] for r in failed)
        out.append("OFFLINE NO-GO: %d/%d checks failed (%s)."
                   % (len(failed), len(results), names))
        if require_native and skipped:
            out.append("--require-native was given and %d check(s) could not run "
                       "here: that is a NO-GO by request, not a defect." % len(skipped))
        return 1, out
    if skipped:
        out.append("OFFLINE GO (PARTIAL): %d/%d verified, %d SKIPPED - no usable "
                   "C++ toolchain on this host." % (len(results) - len(skipped),
                                                    len(results), len(skipped)))
        out.append("  skipped: %s" % ", ".join(r[0] for r in skipped))
        out.append("  Those checks did NOT run here. A GO on this host does not cover")
        out.append("  them: install MSYS2/MinGW-w64 (g++ with AddressSanitizer) or read")
        out.append("  the Linux CI result, and re-run with --require-native to make a")
        out.append("  missing toolchain fatal instead of visible.")
        return 0, out
    out.append("OFFLINE GO: %d/%d curated checks passed." % (len(results), len(results)))
    return 0, out


def tail(text, n=4):
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--require-native", action="store_true",
                    help="treat skipped (no C++ toolchain) checks as failures; "
                         "use this in CI so a missing compiler cannot pass quietly")
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
        status = classify(name, rc, text)
        results.append((name, status, rc, time.time() - t0, log))
        print("%-28s %s  rc=%s  %.1fs" % (name, status, rc, time.time() - t0))
        if status == "FAIL":
            print(tail(text))
        elif status == "SKIP":
            print("                             " + skip_reason(text)[:100])
    failed = [r for r in results if r[1] == "FAIL"]
    skipped = [r for r in results if r[1] == "SKIP"]
    summary = os.path.join(OUT, "SUMMARY.txt")
    with open(summary, "w", encoding="utf-8") as f:
        f.write("QSMC v6.6.20 curated offline production-readiness summary\n")
        f.write("checks=%d passed=%d failed=%d skipped=%d\n"
                % (len(results), len(results) - len(failed) - len(skipped),
                   len(failed), len(skipped)))
        for name, status, rc, dt, log in results:
            f.write("%s rc=%s %.1fs %s\n" % (status, rc, dt, name))
        if skipped:
            f.write("\nSkipped checks were NOT verified on this host "
                    "(no usable C++17 compiler / AddressSanitizer).\n")
        f.write("\nManual gates still required: MetaEditor F7 (0 errors), banner v6.6.20,\n")
        f.write("EA handshake OK, demo/paper observation, and the go-live runbook before real money.\n")
    code, lines = verdict(results, require_native=args.require_native)
    for line in lines:
        print(line)
    print("Summary: %s" % summary)
    if code == 0:
        print("Still manual: F7 in MetaEditor, v6.6.20 banner, EA iCustom handshake, demo/paper run.")
        print("Real money only after docs/QSMC_GO_LIVE_RUNBOOK.md; the EA ships ARMED ON DEMO "
              "(EXECUTION_DEMO) with REAL disarmed (InpAllowRealTrading=false, empty login/server "
              "confirmations) and refuses an unauthorized REAL account at init and at every order.")
    else:
        print("See %s for per-check logs." % OUT)
    return code


if __name__ == "__main__":
    sys.exit(main())
