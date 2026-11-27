#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PREFLIGHT FOR A DEMO TRIAL - the mechanical half of "is this build safe to attach?".

WHY THIS EXISTS
The demo trial of v6.6.24 must start from ONE known build: one version string,
presets that still bind to the sources they were generated from, no order API
reachable from the indicator layer, one magic per executor, an account-mode gate
that cannot arm itself on a REAL account, the HARD ceilings intact, and the
shipping risk defaults at 0.10 % / 0.50 % / 3 % / 1 position / M15.

Every one of those is a fact about the FILES, so it can be checked before the
terminal is even open. R3 is this check, and it runs in CI.

WHAT A PASS MEANS
That the tree is internally consistent and that none of the safety invariants
this project pins have been edited away. It does NOT mean the code compiles
(MetaEditor F7 is still the only judge), it is NOT a backtest, and it says
nothing about profitability.

USAGE
    python3 tools/preflight_demo.py            # prints PASS/FAIL lines
    python3 tools/preflight_demo.py --quiet    # failures only
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECT_VERSION_TEXT = "v6.6.25"
EXPECT_PROPERTY = "6.625"

# Programs exempt from the shared version property. These two carry their own
# version scheme by design (see tools/check_repo_layout.py OWN_VERSION).
OWN_VERSION = {"QuantumAutonomousTradingSystem.mq5", "QSMC_SmcVpEngine.mq5"}

# The magic the QME instance owns. A QSMC executor that reuses it would share
# the ownership lane and the seen-key namespace with a different engine.
QME_MAGIC = "20261110"

HARD_CEILINGS = {"HardMaxRiskPercent": "0.50",
                 "HardMaxDailyPercent": "2.00",
                 "HardMaxDDPercent": "8.00"}

SHIPPING_DEFAULTS = {
    "InpRiskPercent": "0.10",
    "InpMaxRiskPercent": "0.10",
    "InpMaxDailyLossPercent": "0.50",
    "InpMaxAccountDrawdownPct": "3.00",
    "InpMaxOpenPositions": "1",
    "InpPinTimeframeMinutes": "15",
}

TRADE_API = ("OrderSend(", "OrderSendAsync(", "PositionClose(", "PositionOpen(",
             "PositionModify(", "CTrade", "#include <Trade/")

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), label, detail))


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


# Runtime announcements: the strings an operator reads in the Journal, which
# must name the release that is shipping. Each entry is a regex with ONE version
# capture group plus the version it must carry. Unlike the stale-window regex in
# main(), these are compared with the release constant, so a bump moves them.
ANNOUNCEMENTS = (
    (re.compile(r"\[QSMC_ARB\]\s+(v\d\.\d\.\d+)\b"), EXPECT_VERSION_TEXT),
    (re.compile(r"QSMC_ArbiterTest - (v\d\.\d\.\d+)\b"), EXPECT_VERSION_TEXT),
)


def scan_announcements(sources: "list[tuple[str, str]]") -> list[str]:
    """Return "where: announces vX, want vY" for every stale announcement."""
    bad: list[str] = []
    for where, src in sources:
        for rx, want in ANNOUNCEMENTS:
            for got in rx.findall(src):
                if got != want:
                    bad.append("%s: announces %s, want %s" % (where, got, want))
    return bad


def mql_sources(subdirs=("Include", "Indicators", "Scripts", "Experts")) -> list[str]:
    out = []
    for sub in subdirs:
        base_dir = os.path.join(ROOT, "MQL5", sub)
        if not os.path.isdir(base_dir):
            continue
        for base, _dirs, files in os.walk(base_dir):
            for f in files:
                if f.endswith((".mq5", ".mqh")):
                    out.append(os.path.join(base, f))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    ea_path = os.path.join(ROOT, "MQL5", "Experts", "QSMC_AutoTrader.mq5")
    ea = read(ea_path)
    indicators = sorted(os.listdir(os.path.join(ROOT, "MQL5", "Indicators")))

    # ---------------------------------------------------------------- 1 version
    ind = read(os.path.join(ROOT, "nadir2.mq5"))
    m = re.search(r'#define\s+QSMC_VERSION_TEXT\s+"(v[\d.]+)"', ind)
    check(m and m.group(1) == EXPECT_VERSION_TEXT,
          "the indicator announces %s" % EXPECT_VERSION_TEXT,
          m.group(1) if m else "missing QSMC_VERSION_TEXT")

    bad_prop = []
    for path in mql_sources():
        name = os.path.basename(path)
        if name in OWN_VERSION:
            continue
        src = read(path)
        for prop in re.findall(r'#property\s+version\s+"([^"]+)"', src):
            if prop != EXPECT_PROPERTY:
                bad_prop.append("%s:%s" % (name, prop))
    check(not bad_prop, "every shipped program declares #property version %s" % EXPECT_PROPERTY,
          ", ".join(bad_prop))

    #--- Identity statements only. A comment that says "v6.6.23 T3" is history
    #--- and is supposed to stay (it is how a reader learns why a line exists);
    #--- what must never survive is a program ANNOUNCING an old release.
    stale = []
    identity = re.compile(r'(#property\s+version\s+"6\.62[0-3])'
                          r'|(QSMC_VERSION_TEXT\s+"v6\.6\.2[0-3]")'
                          r'|(QSMC v6\.62[0-3]\b)'
                          r'|(\[QSMC_ARB\] v6\.6\.2[0-3]\b)'
                          r'|(QSMC_ArbiterTest - v6\.6\.2[0-3]\b)'
                          r'|(CHART PROFILE / VISUAL LAYERS[^\n]*v6\.6\.2[0-3])')
    for path in mql_sources():
        src = read(path)
        if identity.search(src):
            stale.append(os.path.relpath(path, ROOT))
    check(not stale, "no shipped program ANNOUNCES v6.6.20..v6.6.23 "
                     "(historical comments are kept on purpose)", ", ".join(stale))

    #--- The window above is hardcoded, so it is one release behind by
    #--- construction: v6.6.25 shipped with QSMC_ArbiterTest still PRINTING
    #--- "v6.6.24 signal arbitration harness" because v6.6.24 sat outside
    #--- v6.6.2[0-3] and nothing else compared the banner with the build. The
    #--- Journal lines are compared with EXPECT_VERSION_TEXT instead, so bumping
    #--- the release constant moves this check with it. Header prose is NOT in
    #--- scope: "QSMC v6.6.24 (2026-11-16)" and "R4 of the v6.6.24 audit" date
    #--- the work a file was written for and are supposed to stay.
    stale_announce = scan_announcements(
        [(os.path.relpath(p, ROOT), read(p)) for p in mql_sources()])
    check(not stale_announce,
          "every runtime announcement ([QSMC_ARB], QSMC_ArbiterTest) names %s"
          % EXPECT_VERSION_TEXT, ", ".join(stale_announce))
    #--- Mutation self-test: a scan that cannot flag the defect it was written
    #--- for is a tautology. Both announcement forms must be caught here.
    mutant = scan_announcements([("<mutant>",
                                  'Print(" QSMC_ArbiterTest - v6.6.24 signal arbitration harness");\n'
                                  'Print("[QSMC_ARB] v6.6.20 arbitration layer ON");')])
    mutant_txt = ", ".join(mutant)
    check(len(mutant) == 2 and "v6.6.24" in mutant_txt and "v6.6.20" in mutant_txt,
          "the announcement scan catches a stale harness banner AND a stale ARB banner",
          mutant_txt or "nothing flagged")

    # ---------------------------------------------------------------- 2 presets
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_presets.py")],
                        cwd=ROOT, capture_output=True, text=True)
    check(rc.returncode == 0, "every preset still binds to its source (check_presets.py)",
          (rc.stdout or "").strip().splitlines()[-1] if rc.stdout else "")

    # ------------------------------------------------- 3 no trade API outside EA
    offenders = []
    #--- Gate G4 is about the LAYER: nothing the indicator compiles may be able
    #--- to send an order. MQL5/Experts is where trading is supposed to live, so
    #--- it is out of scope here (each executor is audited on its own).
    for path in mql_sources(subdirs=("Include", "Indicators", "Scripts")):
        rel = os.path.relpath(path, ROOT)
        if rel.endswith("QSMC_AutoTrader.mq5"):
            continue
        src = read(path)
        for token in TRADE_API:
            if token in src:
                offenders.append("%s: %s" % (rel, token))
    check(not offenders,
          "no trade API in the indicator / QSMC include layer (gate G4)",
          "; ".join(offenders[:6]))

    # ------------------------------------------------------------- 4 magic lane
    magics = set()
    for path in mql_sources(subdirs=("Experts", "Scripts", "Indicators")):
        if not path.endswith(".mq5"):
            continue
        if "QSMC" not in os.path.basename(path):
            continue   # the QME family carries its own magic by design
        for val in re.findall(r"input\s+long\s+InpMagic\s*=\s*(\d+)", read(path)):
            magics.add(val)
    check(len(magics) == 1, "every QSMC program that declares InpMagic uses ONE value",
          ", ".join(sorted(magics)) or "none declared")
    check(QME_MAGIC not in magics,
          "the QSMC executor does not reuse the QME magic %s" % QME_MAGIC,
          ", ".join(sorted(magics)))

    # --------------------------------------------------- 5 account-mode gating
    for token, label in (
            ("bool AccountModeKnown(long &mode)", "the account mode is resolved, not assumed"),
            ("ACCOUNT_TRADE_MODE", "the mode comes from the account, not from an input"),
            ("bool RealAuthorized(string &why)", "REAL needs explicit authorization"),
            ("InpAllowRealTrading", "the REAL arming switch exists"),
            ("InpRealAccountConfirm", "REAL is bound to the EXACT login of this account"),
            ("InpRealServerConfirm", "REAL is bound to the EXACT broker server"),
            ("g_emergency_lockout", "an identity change / protection failure latches a lockout")):
        check(token in ea, label, "missing: %s" % token)

    # --------------------------------------------------------------- 6 ceilings
    for fn, want in HARD_CEILINGS.items():
        m2 = re.search(r"double\s+%s\(\)\s*\{\s*return\s+([\d.]+);" % fn, ea)
        check(m2 and m2.group(1) == want, "%s is %s" % (fn, want),
              m2.group(1) if m2 else "not found")

    # -------------------------------------------------------------- 7 defaults
    for name, want in SHIPPING_DEFAULTS.items():
        m3 = re.search(r"input\s+\w+\s+%s\s*=\s*([\d.]+)" % name, ea)
        check(m3 and m3.group(1) == want, "%s ships at %s" % (name, want),
              m3.group(1) if m3 else "not found")

    # ------------------------------------------------- 8 the trial journal is on
    m4 = re.search(r"input\s+bool\s+InpEnableTrialJournal\s*=\s*(true|false)", ea)
    check(m4 and m4.group(1) == "true",
          "the trial journal ships ON (it is how the trial is judged)",
          m4.group(1) if m4 else "not declared")

    # ------------------------------------------------------------- report
    fails = [r for r in RESULTS if not r[0]]
    if not args.quiet:
        for ok, label, detail in RESULTS:
            print(("PASS  " if ok else "FAIL  ") + label + (("  [%s]" % detail) if detail and not ok else ""))
    else:
        for ok, label, detail in fails:
            print("FAIL  " + label + (("  [%s]" % detail) if detail else ""))
    print("-" * 78)
    print("DEMO PREFLIGHT: %d checks, %d failed" % (len(RESULTS), len(fails)))
    print("Indicators present: %s" % ", ".join(indicators))
    if fails:
        print("NO-GO: fix the failures above before attaching anything to a demo account.")
    else:
        print("GO for a DEMO attach. This is not a MetaEditor compile (press F7),")
        print("not a backtest, and not a claim about profitability.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
