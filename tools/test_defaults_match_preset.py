#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DEFAULTS-MATCH-PRESET - the compiled EA and the shipped .set are one object.

WHY THIS EXISTS
---------------
The 2026-11-09 delivery moved the production preset INTO the compiled defaults,
so that a first attach on a demo account trades the intended configuration with
no .set file and no Inputs editing. That promise has exactly one failure mode
that matters: the two drift apart. A default changes in the code, the .set is not
updated, and from then on "attach and go" and "load the preset" are two different
strategies - with the operator reading the .set and the account running the code.

This suite is the guard against that. It reads both artefacts as data:

  * every key in presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set must exist as an
    input in QSMC_AutoTrader.mq5 (a key that matches nothing is silently ignored
    by MT5 - that is how "npMaxAccountDrawdownPct=3.00" left the 3% account-DD
    halt unapplied for the whole of v6.6.20);
  * every value must equal the compiled default, compared in the same textual
    form the EA prints at attach, so a 0.1 vs 0.10 difference cannot hide;
  * the safety switches are asserted explicitly, because "the file and the code
    agree" is worthless if both agree to arm real money.

The old INERT preset is checked too, for the same reason: it is still shipped,
still the first-install document, and it must stay a valid file even though it is
no longer the default.
"""
from __future__ import print_function

import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

EA = os.path.join(ROOT, "MQL5", "Experts", "QSMC_AutoTrader.mq5")
DEMO = os.path.join(ROOT, "presets", "QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set")
INERT = os.path.join(ROOT, "presets", "QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set")

FAILS = []
COUNT = [0]


def check(ok, name, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s%s" % (name, ("  [%s]" % detail) if detail else ""))
        FAILS.append(name)


def parse_inputs(text):
    out = {}
    for m in re.finditer(r"^input\s+([A-Za-z_][\w]*)\s+([A-Za-z_]\w*)\s*=\s*([^;]+);",
                         text, re.M):
        out[m.group(2)] = (m.group(1), m.group(3).strip())
    return out


def same(typ, preset_value, code_value):
    """Compare in the unit that matters: numbers numerically, everything else text."""
    if typ in ("double", "int", "long"):
        try:
            return abs(float(preset_value) - float(code_value)) < 1e-9
        except ValueError:
            return False
    return preset_value == code_value


def as_set_value(typ, default):
    """The form the EA's own attach table prints, so both sides compare cleanly."""
    if typ == "bool" or typ in ("int", "long"):
        return default
    if typ == "double":
        return "%.2f" % float(default)
    if typ == "string":
        return default.strip('"')
    return default


def parse_set(path):
    vals = {}
    for line in io.open(path, encoding="utf-8", errors="replace").read().split("\n"):
        s = line.rstrip("\r").strip()
        if not s or s.startswith(";") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        vals[k.strip()] = v.strip()
    return vals


ea_text = io.open(EA, encoding="utf-8", errors="replace").read()
inputs = parse_inputs(ea_text)
check(len(inputs) == 59, "the companion declares 59 inputs", len(inputs))

# ---------------------------------------------------------------------------
# 1. the demo preset exists and is a complete picture of the compiled defaults
# ---------------------------------------------------------------------------
check(os.path.isfile(DEMO), "presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set ships")
demo = parse_set(DEMO)

unknown = sorted(k for k in demo if k not in inputs)
check(not unknown,
      "every key in the demo preset is a real input (no key is silently ignored)",
      unknown)
missing = sorted(n for n in inputs if n not in demo)
check(not missing,
      "the demo preset is complete: no input is left to chance", missing)

drift = []
for name, (typ, default) in sorted(inputs.items()):
    want = as_set_value(typ, default)
    got = demo.get(name, "")
    if not same(typ, got, want):
        drift.append("%s: preset=%r code=%r" % (name, got, want))
check(not drift,
      "every compiled default equals the demo preset value",
      "; ".join(drift[:6]))

# ---------------------------------------------------------------------------
# 2. the safety switches, asserted by name - agreement alone proves nothing
# ---------------------------------------------------------------------------
check(demo.get("InpEnableTrading") == "true", "the demo preset is ARMED", demo.get("InpEnableTrading"))
check(demo.get("InpDryRun") == "false", "and it really sends orders", demo.get("InpDryRun"))
check(demo.get("InpAllowRealTrading") == "false",
      "REAL is disarmed by default (the single arming switch ships OFF)")
check(demo.get("InpRealAccountConfirm", "x") == "" and demo.get("InpRealServerConfirm", "x") == "",
      "with no login and no server typed in, so a REAL account can never trade")
check(demo.get("InpPinTimeframeMinutes") == "15",
      "pinned to M15, the QSMC profile timeframe", demo.get("InpPinTimeframeMinutes"))
check(demo.get("InpResetBreakersAtInit") == "false",
      "and it never resets a breaker on attach", demo.get("InpResetBreakersAtInit"))

# the risk envelope the delivery promises, in one place
envelope = {
    "InpRiskPercent": "0.10",
    "InpMaxRiskPercent": "0.10",
    "InpMaxDailyLossPercent": "0.50",
    "InpMaxAccountDrawdownPct": "3.00",
    "InpStopAfterConsecLoss": "2",
    "InpMaxTradesPerDay": "3",
    "InpMaxSpreadPoints": "60",
    "InpDeviationPoints": "30",
    "InpMinRRAtFill": "1.20",
    "InpSessionStartHour": "10",
    "InpSessionEndHour": "18",
    "InpCooldownAfterLossMin": "60",
    "InpPartialCloseAtR": "1.50",
    "InpBreakEvenAtR": "1.00",
    "InpMinStopPoints": "20",
    "InpMaxStopPoints": "5000",
    "InpMaxOpenPositions": "1",
    "InpMaxSignalAgeBars": "2",
    "InpMaxDataAgeSeconds": "30",
}
for name, want in sorted(envelope.items()):
    check(inputs.get(name, ("", ""))[1] == want or
          as_set_value(*inputs.get(name, ("", ""))) == want,
          "compiled default %s = %s" % (name, want),
          inputs.get(name, ("", "missing")))

# ---------------------------------------------------------------------------
# 3. the HARD ceilings are what the preset table and the gate claim
# ---------------------------------------------------------------------------
hard = {}
for key, rx in (("risk", r"double\s+HardMaxRiskPercent\(\)\{\s*return\s*([\d.]+);"),
                ("daily", r"double\s+HardMaxDailyPercent\(\)\{\s*return\s*([\d.]+);"),
                ("dd", r"double\s+HardMaxDDPercent\(\)\{\s*return\s*([\d.]+);")):
    m = re.search(rx, ea_text)
    hard[key] = m.group(1) if m else None
check(hard == {"risk": "0.50", "daily": "2.00", "dd": "8.00"},
      "the HARD ceilings are 0.50 / 2.00 / 8.00", hard)
for name, key in (("InpMaxRiskPercent", "risk"), ("InpMaxDailyLossPercent", "daily"),
                  ("InpMaxAccountDrawdownPct", "dd")):
    value = float(as_set_value(*inputs[name]))
    limit = float(hard[key])
    check(value <= limit,
          "%s (%s) sits at or below its HARD ceiling (%s)" % (name, value, limit))

# ---------------------------------------------------------------------------
# 4. the attach table must reference this file, or it is describing something else
# ---------------------------------------------------------------------------
check("QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set" in ea_text,
      "the EA's PRESET CHECK line names the file it compares itself against")
check("PrintEffectiveVsPreset();" in ea_text,
      "and the table is actually printed at attach")
for name in ("InpEnableTrading", "InpRiskPercent", "InpMaxAccountDrawdownPct",
             "InpPinTimeframeMinutes"):
    check('PresetDelta(rows,"%s"' % name in ea_text,
          "the attach table covers %s" % name)

# ---------------------------------------------------------------------------
# 5. the INERT preset is still a valid, unarmed document (and no longer broken)
# ---------------------------------------------------------------------------
inert = parse_set(INERT)
bad = sorted(k for k in inert if k not in inputs)
check(not bad,
      "the INERT preset has no key that MT5 would silently ignore", bad)
check(inert.get("InpEnableTrading") == "false" and inert.get("InpDryRun") == "true",
      "the INERT preset still does not arm anything")
# ... and it differs from the compiled defaults in exactly those two switches.
inert_drift = []
for name, (typ, default) in sorted(inputs.items()):
    if name in ("InpEnableTrading", "InpDryRun"):
        continue
    want = as_set_value(typ, default)
    got = inert.get(name, "")
    if not same(typ, got, want):
        inert_drift.append("%s: preset=%r code=%r" % (name, got, want))
check(not inert_drift,
      "the INERT preset is the same configuration as the compiled defaults "
      "apart from the two arming switches",
      "; ".join(inert_drift[:6]))
for name in ("InpMaxAccountDrawdownPct", "InpMaxDailyLossMoney"):
    check(name in inert,
          "the v6.6.20 typo that dropped %s is fixed" % name,
          sorted(k for k in inert if k.endswith(name)))

if FAILS:
    print("%d of %d defaults-vs-preset check(s) failed" % (len(FAILS), COUNT[0]))
    raise SystemExit(1)
print("%d defaults-vs-preset checks passed; the compiled EA and the .set are one object."
      % COUNT[0])
