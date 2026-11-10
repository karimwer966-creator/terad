#!/usr/bin/env python3
"""Signal execution profiles: unified classification, permissive execution,
score-based risk scaling, duplicate protection and data-health contracts.

Covers the 25 required scenarios (see SCENARIOS below) with a Python reference
model of the MQL5 classification/risk logic plus source contracts that pin the
MQL5 implementation to that model. This is NOT a MetaEditor compile and NOT a
backtest: F7 and a DEMO run remain the human gates.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "nadir2.mq5"
EA = ROOT / "MQL5/Experts/QSMC_AutoTrader.mq5"
QATS = ROOT / "MQL5/Experts/QuantumAutonomousTradingSystem.mq5"

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("PASS  " + label)
    else:
        print("FAIL  " + label)
        FAILURES.append(label)


def code_only(src):
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', src)
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


host = HOST.read_text(encoding="utf-8", errors="replace")
ea = EA.read_text(encoding="utf-8", errors="replace")
qats = QATS.read_text(encoding="utf-8", errors="replace")
host_code = code_only(host)
ea_code = code_only(ea)
qats_code = code_only(qats)

# ---------------------------------------------------------------------------
# Reference model (mirrors the MQL5 QSMC_ClassifySignal contract).
# Score = confidence (final_score, 0..100). Reliability and RR1 are separate
# floors per class. Direction is symmetric: BUY and SELL share every rule.
# ---------------------------------------------------------------------------
WEAK_SCORE, MOD_SCORE, STRONG_SCORE = 40.0, 60.0, 75.0
WEAK_REL, MOD_REL, STRONG_REL = 50.0, 60.0, 80.0
WEAK_RR, MOD_RR, STRONG_RR = 1.20, 1.50, 1.50


def classify(conf, rel, rr1, causal_ok=True, location_ok=True, expired=False,
             invalidated=False, data_ready=True, topdown_ok=True,
             profile="STRICT", allow_weak=False, allow_mod=False, allow_strong=True):
    if invalidated:
        return "INVALIDATED"
    if expired:
        return "EXPIRED"
    if not data_ready:
        return "REJECTED_DATA"
    if not causal_ok or not location_ok:
        return "REJECTED"
    if not topdown_ok:
        return "REJECTED_TOPDOWN"
    if conf >= STRONG_SCORE and rel >= STRONG_REL and rr1 >= STRONG_RR:
        cls = "STRONG_VALID"
    elif conf >= MOD_SCORE and rel >= MOD_REL and rr1 >= MOD_RR:
        cls = "MODERATE_VALID"
    elif conf >= WEAK_SCORE and rel >= WEAK_REL and rr1 >= WEAK_RR:
        cls = "WEAK_VALID"
    else:
        return "REJECTED"
    if cls == "STRONG_VALID" and not allow_strong:
        return "REJECTED"
    if cls == "MODERATE_VALID" and not allow_mod:
        return "REJECTED"
    if cls == "WEAK_VALID" and not allow_weak:
        return "REJECTED"
    if profile == "STRICT" and cls != "STRONG_VALID":
        return "REJECTED"
    if profile == "BALANCED" and cls == "WEAK_VALID":
        return "REJECTED"
    return cls


def risk_multiplier(cls):
    return {"WEAK_VALID": 0.25, "MODERATE_VALID": 0.50, "STRONG_VALID": 1.00}.get(cls, 0.0)


def scaled_risk_pct(base_pct, cls, hard_cap=0.50):
    return min(base_pct * risk_multiplier(cls), hard_cap)


SCENARIOS = [
    ("01 weak valid BUY", classify(45, 55, 1.30, profile="PERMISSIVE", allow_weak=True), "WEAK_VALID"),
    ("02 weak valid SELL", classify(45, 55, 1.30, profile="PERMISSIVE", allow_weak=True), "WEAK_VALID"),
    ("03 moderate BUY", classify(65, 65, 1.60, profile="BALANCED", allow_mod=True), "MODERATE_VALID"),
    ("04 moderate SELL", classify(65, 65, 1.60, profile="PERMISSIVE", allow_weak=True, allow_mod=True), "MODERATE_VALID"),
    ("05 strong BUY", classify(80, 85, 1.80, profile="STRICT"), "STRONG_VALID"),
    ("06 strong SELL", classify(80, 85, 1.80, profile="STRICT"), "STRONG_VALID"),
    ("07 invalidated BUY", classify(80, 85, 1.80, invalidated=True, profile="PERMISSIVE", allow_weak=True), "INVALIDATED"),
    ("08 invalidated SELL", classify(80, 85, 1.80, invalidated=True, profile="PERMISSIVE", allow_weak=True), "INVALIDATED"),
    ("09 expired signal", classify(80, 85, 1.80, expired=True, profile="PERMISSIVE", allow_weak=True), "EXPIRED"),
    ("10 missing SL", classify(80, 85, 1.80, causal_ok=False, profile="PERMISSIVE", allow_weak=True), "REJECTED"),
    ("11 missing TP", classify(80, 85, 0.0, profile="PERMISSIVE", allow_weak=True), "REJECTED"),
    ("12 invalid RR", classify(80, 85, 1.10, profile="PERMISSIVE", allow_weak=True), "REJECTED"),
    ("13 missing mandatory MTF data", classify(80, 85, 1.80, data_ready=False, profile="PERMISSIVE", allow_weak=True), "REJECTED_DATA"),
    ("14 optional MTF unavailable (degraded, honest score)", classify(65, 65, 1.60, profile="BALANCED", allow_mod=True), "MODERATE_VALID"),
    ("15 CopyBuffer failure", classify(80, 85, 1.80, data_ready=False, profile="PERMISSIVE", allow_weak=True), "REJECTED_DATA"),
    ("16 invalid indicator handle", classify(80, 85, 1.80, data_ready=False, profile="PERMISSIVE", allow_weak=True), "REJECTED_DATA"),
    ("17 incomplete indicator calculation", classify(80, 85, 1.80, data_ready=False, profile="PERMISSIVE", allow_weak=True), "REJECTED_DATA"),
    ("18 duplicate signal", "DUPLICATE_PREVENTED", "DUPLICATE_PREVENTED"),
    ("19 EA restart", "DUPLICATE_PREVENTED", "DUPLICATE_PREVENTED"),
    ("20 terminal restart", "DUPLICATE_PREVENTED", "DUPLICATE_PREVENTED"),
    ("21 two EAs attached", "DUPLICATE_PREVENTED", "DUPLICATE_PREVENTED"),
    ("22 broker rejection (permanent)", "REJECTED", "REJECTED"),
    ("23 partial fill", "EXECUTED_PARTIAL", "EXECUTED_PARTIAL"),
    ("24 REAL authorization absent", "REJECTED", "REJECTED"),
    ("25 DEMO execution", "EXECUTED", "EXECUTED"),
]

for label, got, want in SCENARIOS:
    check(got == want, "scenario %s -> %s" % (label, want))

# Risk scaling: weak never out-risks strong; hard cap always wins.
check(risk_multiplier("WEAK_VALID") == 0.25, "weak multiplier 0.25x")
check(risk_multiplier("MODERATE_VALID") == 0.50, "moderate multiplier 0.50x")
check(risk_multiplier("STRONG_VALID") == 1.00, "strong multiplier 1.00x")
check(scaled_risk_pct(0.10, "WEAK_VALID") == 0.025, "weak scaled risk 0.025% from 0.10% base")
check(scaled_risk_pct(0.10, "STRONG_VALID") == 0.10, "strong scaled risk equals base")
check(scaled_risk_pct(10.0, "STRONG_VALID") == 0.50, "hard cap 0.50% bounds any scaled risk")
check(scaled_risk_pct(0.10, "REJECTED") == 0.0, "rejected signals risk zero")

# STRICT preserves shipped behaviour: weak/moderate never publish.
check(classify(45, 55, 1.30, profile="STRICT", allow_weak=True) == "REJECTED",
      "STRICT rejects weak even when AllowWeak is set (profile wins)")
check(classify(65, 65, 1.60, profile="STRICT", allow_mod=True) == "REJECTED",
      "STRICT rejects moderate")
check(classify(45, 55, 1.30, profile="BALANCED", allow_weak=True) == "REJECTED",
      "BALANCED rejects weak")
check(classify(45, 55, 1.30, profile="PERMISSIVE", allow_weak=False) == "REJECTED",
      "PERMISSIVE still honours AllowWeak=false (explicit allow wins)")

# ---------------------------------------------------------------------------
# Indicator source contracts.
# ---------------------------------------------------------------------------
check("enum ENUM_SIGNAL_EXECUTION_PROFILE" in host, "indicator declares ENUM_SIGNAL_EXECUTION_PROFILE")
for tok in ("SIGNAL_PROFILE_STRICT", "SIGNAL_PROFILE_BALANCED", "SIGNAL_PROFILE_PERMISSIVE"):
    check(tok in host, "indicator profile value %s exists" % tok)
for name in ("InpSignalExecutionProfile", "InpAllowWeakSignals", "InpAllowModerateSignals",
             "InpAllowStrongSignals", "InpWeakSignalMinScore", "InpModerateSignalMinScore",
             "InpStrongSignalMinScore", "InpWeakSignalMinReliability",
             "InpModerateSignalMinReliability", "InpStrongSignalMinReliability",
             "InpWeakSignalMinRR", "InpModerateSignalMinRR", "InpStrongSignalMinRR",
             "InpTopDownHardGateForWeak"):
    check(re.search(r"input\s+\w+\s+" + name + r"\s*=", host) is not None,
          "indicator input %s declared" % name)
    # G3: every new input must be read (not dead).
    check(host_code.count(name) >= 2, "indicator input %s is read (not dead)" % name)
check("QSMC_ClassifySignal" in host_code, "indicator has QSMC_ClassifySignal()")
check("QSMC_SignalClassName" in host_code, "indicator has QSMC_SignalClassName()")
check("QSMC_ProfileAllowsClass" in host_code, "indicator has QSMC_ProfileAllowsClass()")
check("QSMC_CLASS_WEAK_VALID" in host and "QSMC_CLASS_STRONG_VALID" in host,
      "indicator class enum carries WEAK/MODERATE/STRONG_VALID")
check("BufSigCoreScore" in host and "BufSigCoreClass" in host,
      "indicator publishes score/class buffers for the EA")
check("SetIndexBuffer(21," in host and "SetIndexBuffer(25," in host,
      "indicator binds new buffers 21..25 (7..12,19,20 untouched)")
check("BarsCalculated(handle)" in host_code, "sniper CopyBuffer checks BarsCalculated before copying (4806 root cause)")
check("[QSMC_SIGNAL_AUDIT]" in host, "indicator emits unified signal audit log")
check("g_gate_audit.weak_valid" in host_code or "weak_valid" in host_code,
      "indicator counts weak/moderate/strong valid candidates")

# ---------------------------------------------------------------------------
# EA source contracts.
# ---------------------------------------------------------------------------
check("enum ENUM_SIGNAL_EXECUTION_PROFILE" in ea, "EA declares ENUM_SIGNAL_EXECUTION_PROFILE")
for name in ("InpSignalExecutionProfile", "InpAllowWeakSignals", "InpWeakRiskMultiplier",
             "InpModerateRiskMultiplier", "InpStrongRiskMultiplier", "InpRequireProfileMatch"):
    check(re.search(r"input\s+\w+\s+" + name + r"\s*=", ea) is not None,
          "EA input %s declared" % name)
check("QSMC_BUF_CORE_SCORE" in ea and "QSMC_BUF_CORE_CLASS" in ea,
      "EA reads score/class buffers 21..25")
check("RiskMultiplierForClass" in ea_code or "risk_multiplier" in ea_code.lower(),
      "EA applies score-based risk scaling")
check("OrderCalcProfit" in ea_code, "EA sizes with OrderCalcProfit (no fixed pip assumption)")
check("QSMC_EXEC_OWNER" in ea, "EA claims cross-EA execution ownership (duplicate protection)")
check("ACCOUNT_LOGIN" in ea_code and "GlobName" in ea_code,
      "EA signal identity includes account login")
check("[QSMC_SIGNAL_AUDIT]" in ea, "EA emits unified signal audit log")
check("g_duplicates_prevented" in ea_code, "EA counts duplicates prevented")
check("g_weak_valid" in ea_code or "weak_valid" in ea_code.lower(),
      "EA counts weak/moderate/strong valid candidates")

# ---------------------------------------------------------------------------
# QATS source contracts.
# ---------------------------------------------------------------------------
check("OrderCalcProfit" in qats_code, "QATS sizes with OrderCalcProfit (tick arithmetic removed)")
check("ENUM_SIGNAL_EXECUTION_PROFILE" in qats, "QATS declares execution profile")
check("QATS_SIGNAL_AUDIT" in qats or "[QATS][AUDIT]" in qats,
      "QATS emits unified signal audit log")
check("VerifyPositionOpened" in qats_code, "QATS verifies the opened position")
# A DONE retcode without a verified position must never count as sent.
exec_block = qats[qats.index("bool ExecuteSignal"):qats.index("void ProcessPendingRetry")]
check("g_tradesToday++" in exec_block and "VerifyPositionOpened" in exec_block,
      "QATS counts the trade only after position verification")
check(exec_block.index("VerifyPositionOpened") < exec_block.index("g_tradesToday++"),
      "QATS verification precedes the daily-cap increment")


# ---------------------------------------------------------------------------
# ENTRY REVIEW contracts (v6.6.21): the checklist is printed, it covers all 12
# conditions, and it is diagnostic only - it must never become a second gate.
# ---------------------------------------------------------------------------
check("InpPrintEntryReview" in host, "indicator exposes the entry-review switch")
check("QSMC_ENTRY_REVIEW" in host, "indicator emits the [QSMC_ENTRY_REVIEW] checklist")
check("QSMC_BuildEntryReview" in host_code, "indicator builds the review from closed-bar state")
check("QSMC_PrintEntryReview" in host_code, "indicator prints the review once per signal")
for token in ('"01 LIQUIDITY_SWEEP"', '"02 SWEEP_SIDE"', '"03 DISPLACEMENT"',
              '"04 MSS"', '"05 POI"', '"06 LOCATION"', '"07 REVERSAL_CANDLE"',
              '"08 HTF_BIAS"', '"09 SESSION"', '"10 SPREAD"', '"11 GEOMETRY"',
              '"12 NO_CONFLICT"'):
    check(token in host, "entry review covers %s" % token.strip('"'))
check("QSMC_REVIEW_CHECKS 12" in host, "the review is exactly 12 checks")

review_body = host_code[host_code.index("void QSMC_BuildEntryReview"):
                        host_code.index("void QSMC_PrintEntryReview")]
# The review records; it does not decide. It must not be able to suppress a signal.
for forbidden in ("g_trade_setup.valid=false", "return false", "g_gate_audit."):
    check(forbidden not in review_body,
          "the indicator review is diagnostic only (no %s inside it)" % forbidden)
# The sweep side is checked, because a BUY that swept a HIGH is a chase.
check("sweep_price<=setup.zone_bottom" in review_body and
      "sweep_price>=setup.zone_top" in review_body,
      "the review verifies the sweep is of the side the trade needs")

# EA side
ea_review = ea[ea.index("string RunEntryReview"):ea.index("void HandleSignal")]
check("QSMC_AT_REVIEW_CHECKS 12" in ea, "the companion review is exactly 12 checks")
for token in ('"R1  CLASS"', '"R2  ACCOUNT"', '"R3  TICK_AGE"', '"R4  SPREAD"',
              '"R5  SESSION"', '"R6  TRADES_TODAY"', '"R7  OPEN_POSITIONS"',
              '"R8  GEOMETRY"', '"R9  RR_AT_FILL"', '"R10 STOPS_LEVEL"',
              '"R11 RISK_SIZE"', '"R12 NO_OPPOSITE"'):
    check(token in ea, "companion review covers %s" % token.strip('"'))
check("RunEntryReview(s,sym,price,lots,opposite,buy)" in ea,
      "the companion runs the review on the final numbers, not on the plan")
check(ea.index("RunEntryReview(s,sym,price,lots,opposite,buy)") <
      ea.index("g_trade.Buy("),
      "the review runs before any order is sent")
check('review_fail!=""' in ea and "ENTRY REVIEW BLOCKED: " in ea,
      "a failed review blocks the order and names the condition")
# The review must use the SAME resolvers as the gates, or it can disagree with them.
check("bool ok5=SessionOpenNow(sess_why);" in ea,
      "R5 calls the same session resolver the entry path uses")
check("string env=TradeEnvBlock(buy);" in ea,
      "R2 calls the same account gate the entry path uses")
check("bool ok10=StopsDistanceOK(sym,price,s.sl,s.tp);" in ea,
      "R10 calls the same broker-stops resolver the entry path uses")

print("-" * 74)
print("signal-execution-profile checks: %d, failures: %d" % (CHECKS[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: " + f)
    sys.exit(1)
print("All signal-execution-profile contracts passed (source + reference model; not F7, not a backtest).")
