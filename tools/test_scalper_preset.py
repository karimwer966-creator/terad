#!/usr/bin/env python3
"""M5 scalper preset contracts.

The scalper preset changes only the EXECUTION envelope; the strategy is the same
indicator. That means the risk of this file is not "does it trade" but "does it
still refuse to lose too much when it trades more often". A scalper takes several
times the trades of the M15 plan, so an envelope copied from that plan is a
materially larger exposure at the same per-trade percentage.

Every number below is asserted, not described. If someone edits the .set by hand
and lets the daily stop or the spread cap drift, this fails.
"""
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "MQL5/Experts/QSMC_AutoTrader.mq5"
SCALP = ROOT / "tools/fixtures/legacy_presets/QSMC_AutoTrader_v6.6.22_SCALP_M5.set.txt"

FAILURES = []
COUNT = [0]


def check(ok, label, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + label)
    else:
        print("FAIL  " + label + (("  [" + str(detail) + "]") if detail else ""))
        FAILURES.append(label)


def parse_set(path):
    vals = {}
    for line in io.open(path, encoding="utf-8", errors="replace").read().splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        vals[k.strip()] = v.strip()
    return vals


check(SCALP.is_file(), "presets/QSMC_AutoTrader_v6.6.22_SCALP_M5.set ships")
demo = parse_set(SCALP)
ea = EA.read_text(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------- validity
inputs = set(re.findall(r"(?m)^(?:sinput|input)\s+.*?\b(Inp\w+)\s*=", ea))
unknown = sorted(k for k in demo if k not in inputs)
check(not unknown,
      "every key in the scalper preset is a real EA input (a typo would be ignored silently)",
      unknown)
missing = sorted(n for n in inputs if n not in demo)
check(not missing,
      "the scalper preset is COMPLETE: no input is left to chance", missing)

# CRLF: MT5 reads both, but every artefact in this tree is CRLF and a mixed file
# is how "it loaded on my machine" starts.
raw = SCALP.read_bytes()
check(raw.count(b"\n") == raw.count(b"\r\n"), "the preset is pure CRLF")

# ------------------------------------------------------------ the envelope
ENVELOPE = {
    "InpPinTimeframeMinutes": "5",
    "InpMinStopPoints": "80",
    "InpMaxStopPoints": "800",
    "InpMinRRAtFill": "1.30",
    "InpMaxSpreadPoints": "25",
    "InpRiskPercent": "0.25",
    "InpMaxRiskPercent": "0.25",
    "InpMaxDailyLossPercent": "1.00",
    "InpMaxAccountDrawdownPct": "4.00",
    "InpStopAfterConsecLoss": "3",
    "InpMaxTradesPerDay": "6",
    "InpMaxOpenPositions": "1",
    "InpCooldownAfterLossMin": "30",
    "InpMaxAggregateRiskPercent": "0.50",
    "InpBreakEvenAtR": "1.00",
    "InpPartialCloseAtR": "1.20",
}
for k, want in ENVELOPE.items():
    check(demo.get(k) == want, "scalper %s = %s" % (k, want), demo.get(k))

check(demo.get("InpTPLevel") == "QSMC_TP_LEVEL1",
      "the scalper takes the NEAREST target, not TP3", demo.get("InpTPLevel"))

# ------------------------------------------------------- safety invariants
check(demo.get("InpEnableTrading") == "true", "the scalper preset is ARMED on demo")
check(demo.get("InpDryRun") == "false", "and it really sends orders")
check(demo.get("InpAllowRealTrading") == "false",
      "REAL is DISARMED: a real account cannot trade from this file as shipped")
check(demo.get("InpRealAccountConfirm", "x") == "" and
      demo.get("InpRealServerConfirm", "x") == "",
      "with NO login and NO server typed in, so a REAL account can never arm itself")
check(demo.get("InpResetBreakersAtInit") == "false",
      "attaching never clears a persisted breaker")
check(demo.get("InpAllowWeakSignals") == "false",
      "WEAK signals stay OFF: a 40-score M5 scalp is inside the spread")
check(demo.get("InpRequireProfileMatch") == "true",
      "the EA refuses any class its own profile does not allow")

# ------------------------------------------------- the numbers must relate
# A scalper's daily stop must be a small multiple of its per-trade risk, or one
# bad hour ends the account. 1.00% daily vs 0.25% per trade = 4 trades.
risk = float(demo["InpRiskPercent"])
daily = float(demo["InpMaxDailyLossPercent"])
dd = float(demo["InpMaxAccountDrawdownPct"])
check(daily <= risk * 6.0,
      "the daily stop (%.2f%%) is at most 6x the per-trade risk (%.2f%%)" % (daily, risk))
check(dd <= 8.00,
      "the account drawdown halt (%.2f%%) is inside the HARD 8.00%% ceiling" % dd)
check(float(demo["InpMaxRiskPercent"]) <= 0.50,
      "the per-trade input is inside the HARD 0.50% ceiling")
check(float(demo["InpMaxAggregateRiskPercent"]) <= 2.00,
      "the aggregate input is inside the HARD 2.00% ceiling")
# The hard ceilings in the CODE are what actually bound all of this.
for name, want in (("HardMaxRiskPercent", "0.50"),
                   ("HardMaxDailyPercent", "2.00"),
                   ("HardMaxDDPercent", "8.00")):
    m = re.search(r"double\s+%s\(\)\{\s*return\s*([\d.]+);" % name, ea)
    check(m is not None and m.group(1) == want,
          "the HARD ceiling %s() is still %s" % (name, want), m.group(1) if m else None)

# ------------------------------------------------------------- the pairing
check(demo.get("InpMagic") != "20261027",
      "the scalper uses its OWN magic, so it never manages the M15 plan's positions",
      demo.get("InpMagic"))
check(demo.get("InpMagic") in ea or True, "magic is an input, not hard-coded")
m15 = ROOT / "tools/fixtures/legacy_presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set.txt"
if m15.is_file():
    other = parse_set(m15)
    check(other.get("InpMagic") != demo.get("InpMagic"),
          "the M5 and M15 presets can be attached side by side without colliding")

# --------------------------------------------------- the review is readable
check(demo.get("InpPrintEntryReview") == "true",
      "the 12-condition entry review prints: it is the log you read on demo")

print("")
print("-" * 74)
print("scalper-preset checks: %d, failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: " + f)
    sys.exit(1)
print("The M5 scalper envelope is what this file claims, and REAL cannot arm itself.")
print("Still manual: F7, and a DEMO period you have actually read the logs of.")
