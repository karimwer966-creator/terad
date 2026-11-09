#!/usr/bin/env python3
"""Generate complete MT5 .set files for nadir2 and QSMC_AutoTrader.

WHY THIS FILE EXISTS
--------------------
`presets/nadir2_PRACTICAL_XAUUSD.set` was genuinely corrupted, not merely
stale: every line had lost its tail. `InpEMAFast` was 5 instead of 50,
`InpEMASlow` was 2 instead of 200, `InpATRPeriod` was 1 instead of 14,
`InpZoneLookback` was 1 instead of 150, `InpLiqToleranceATR` was 0.00 instead
of 0.15, and the `"======group` header lines were cut to `"======E`. A preset
is an input surface the operator loads with one click, so a truncated number is
a silent strategy change - exactly the class of defect that produced the
2026-11-06 "no CORE signal" journal.

The fix is not to patch a mangled file. This generator parses the INPUT
DECLARATIONS out of the source, emits every input with its compiled default,
and applies a small, explicit table of overrides with a comment stating why each
one differs. Nothing is typed by hand twice, so the file cannot drift from the
code, and `--check` fails in CI the moment it does.

Usage:
  python3 tools/generate_set_presets.py           # write the .set files
  python3 tools/generate_set_presets.py --check    # fail on drift (CI)
"""
from __future__ import print_function

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NL = "\r\n"

# --------------------------------------------------------------------------
# nadir2 (indicator). Base = the compiled defaults, then these overrides.
# Every override is a deliberate decision for XAUUSD intraday; the reasons are
# the same ones docs/QSMC_WHY_NO_TRADES.md documents.
# --------------------------------------------------------------------------
NADIR2_OVERRIDES = {
    # --- gates: PRACTICAL profile is what makes a 60/100 candidate publish ---
    # The indicator ships STRICT (75 conf / 80 rel) and that is a *product*
    # decision, so the profile is switched here, in the profile input, instead
    # of by faking the thresholds. EffMin*() then apply the documented floors.
    "InpGateProfile": "QSMC_GATE_PRACTICAL",

    # --- the causal chain the EA consumes must be fully wired ---
    # v6.6.21 audit: the causal invariant / replay audit was OFF in the old
    # preset, which is why a broken binding could hide behind [GateAudit]
    # instead of failing loudly. These are the checks that caught it.
    "InpEnableCausalInvariantChecks": "true",
    "InpPMIRunReplayAudit": "true",
    "InpInstitutionalSequence": "true",

    # --- all seven advisory modules on, through the ONE master switch ---
    # AUDIT-UX1: InpEnableAllModules turns on PowerOf3, SilverBullet, Wyckoff,
    # PriceAction, MeanReversion, Confluence and RiskModel plus their tooltip
    # output. It deliberately does NOT turn on the chart-object opt-ins (entry
    # zone box, range box, OB labels) - boxes are clutter, and the modules are
    # display-only observers that never gate the entry.
    "InpEnableAllModules": "true",

    # --- execution companion layer must be fully observable ---
    # The EA reads CORE signals; the reaction layer (ZRE/RXN) and the sniper
    # zones are what make a CORE setup reachable on gold. These are observation
    # layers: they cannot loosen a gate.
    "InpUseZRE": "true",
    "InpUseRXN": "true",
    "InpUseSniperZoneEngine": "true",
    "InpUseQuantEngine": "true",
    "InpUseMasterVolumeProfile": "true",
    "InpUseHistoricalAnalysis": "true",
    "InpUseCandleIntelligence": "true",
    "InpUseInstitutionalBehavior": "true",
    "InpUseDirectionalScenarioEngine": "true",
    "InpUsePredictiveEngine": "true",

    # --- diagnostics ON: this is what makes "no signal" answerable ---
    "InpShowGateAudit": "true",
    "InpGateAuditLogEveryBars": "20",     # ~1 block per 20 closed bars
    "InpLogSignalDetails": "true",
    "InpSigLogCore": "true",
    "InpSigLogZRE": "true",
    "InpSigLogRunSelfTest": "true",
    "InpPMIRunSelfTestOnInit": "true",
    "InpZRERunSelfTest": "true",
    "InpRXNRunSelfTest": "true",
    "InpSniperRunSelfTest": "true",
    "InpRuntimeNoLookaheadAudit": "true",

    # --- incremental detection: the live path the EA actually runs ---
    "InpUseIncrementalDetection": "true",
    "InpUpdateEveryTick": "false",        # closed-bar decisions only
    "InpRedrawTradeBoxOnNewBarOnly": "true",

    # --- visual context (the panel is the operator's instrument) ---
    "InpDisplayMode": "QSMC_MODE_FULL",
    "InpShowMTFPanel": "true",
    "InpShowAIDashboard": "true",
    "InpShowTopDownPanel": "true",
    "InpShowEntries": "true",
    "InpShowSLTP": "true",
    "InpShowSniperZones": "true",
    "InpShowKillZones": "true",
    "InpShowSessionHL": "true",
    "InpShowPDHPDL": "true",
    "InpShowConfluentSR": "true",
    "InpShowPremiumDiscount": "true",
    "InpShowOTE": "true",
    "InpShowPivots": "true",
    "InpShowCamarilla": "true",
    "InpShowBreakers": "true",
    "InpResolveLabelCollisions": "true",
    "InpSmartObjectManagement": "true",

    # --- chart clutter: deliberately OFF ---
    # The master switch excludes these on purpose; enabling them here would
    # contradict AUDIT-UX1 and bury the chart the EA is read from.
    "InpUltraCleanMode": "false",
    "InpShowBattleAnnotations": "false",
    "InpShowEarlyBreakPreview": "false",
    "InpShowEntryPreviewMarks": "false",
    "InpShowZREEntryMarks": "false",
    "InpShowFibonacci": "false",
    "InpShowDebugAlerts": "false",
    "InpDebugLog": "false",

    # --- alerts: popups are fine on a demo chart, push/sound are not ---
    "InpAlertOnSetup": "true",
    "InpAlertOnConfirmed": "true",
    "InpAlertPushOnConfirmed": "false",
    "InpPrimaryAlertPopup": "true",
    "InpPrimaryAlertPush": "false",
    "InpPrimaryAlertSound": "false",
    "InpZREAlertPopup": "true",
    "InpZREAlertPush": "false",
    "InpZREAlertSound": "false",
    "InpRXNAlerts": "false",
    "InpTopDownAlerts": "false",
    "InpAlertDispatcherLog": "false",

    # --- keep the deliberately-off definitions visible in the file ---
    # These four are OFF on purpose and are NOT defects:
    #   InpUseRetestLifecycle : seeds a setup and waits for a later closed-bar
    #       confirmation. OFF = enter on the published closed bar, which is what
    #       InpMaxSignalAgeBars=2 assumes in the EA. Turning it on makes the
    #       EA's 2-bar window occasionally too tight; leave off for the trial.
    #   InpRequireMSSAfterSweep : a stricter structural filter; OFF = a CHoCH or
    #       BOS may anchor, which is what the PRACTICAL profile documents.
    #   InpBlockEquilibriumEntries : a location filter on top of the profile.
    #   InpUseEMAVWAPConfluence : an extra confluence requirement.
    # They are set explicitly so a future reader cannot mistake "off by default"
    # for "forgotten by the preset".
    "InpUseRetestLifecycle": "false",
    "InpRequireMSSAfterSweep": "false",
    "InpBlockEquilibriumEntries": "false",
    "InpUseEMAVWAPConfluence": "false",
}

# One line per override, written above the key in the generated file. The point
# is that the operator can read WHY a number differs from the compiled default
# without opening the source.
NADIR2_REASONS = {
    "InpGateProfile": "PRACTICAL profile = documented floors 60 conf / 60 rel / 1.20R / 6 ATR / 120 bars search (a 64/100 candidate can publish)",
    "InpEnableCausalInvariantChecks": "the audit that exposed the 2026-11-06 OB binding rollback; OFF would hide the next one",
    "InpPMIRunReplayAudit": "incremental-vs-full replay comparison; the tripwire for a repainting graph",
    "InpInstitutionalSequence": "require sweep -> displacement -> structure ancestry before any publish",
    "InpEnableAllModules": "one switch for the seven advisory modules (PowerOf3, SilverBullet, Wyckoff, PriceAction, MeanReversion, Confluence, RiskModel) + their tooltips",
    "InpUseZRE": "zone reaction engine: the observation layer that makes a CORE setup reachable on gold",
    "InpUseRXN": "reaction signal layer: confirms/suppresses a zone reaction; observation only, never loosens a gate",
    "InpUseSniperZoneEngine": "sniper zones feed the EA's target logic and the panel",
    "InpUseQuantEngine": "volatility/regime context for scoring (does not gate)",
    "InpUseMasterVolumeProfile": "value area / POC context on the panel",
    "InpUseHistoricalAnalysis": "empirical hit-rate context per setup class",
    "InpUseCandleIntelligence": "candle anatomy scoring factor",
    "InpUseInstitutionalBehavior": "institutional footprint scoring factor",
    "InpUseDirectionalScenarioEngine": "scenario plans on the panel",
    "InpUsePredictiveEngine": "predictive panel; display only",
    "InpShowGateAudit": "PRINT the gate audit - without it 'no signal' is unanswerable",
    "InpGateAuditLogEveryBars": "one GateAudit block every 20 closed bars (no log flood, still visible)",
    "InpLogSignalDetails": "one line per published signal with its chain",
    "InpSigLogCore": "write the CORE signal log the EA evidence trail reads",
    "InpSigLogZRE": "also log the reaction-layer signals (shadow comparison)",
    "InpSigLogRunSelfTest": "verify the log writer at init instead of discovering it broken later",
    "InpPMIRunSelfTestOnInit": "PMI self-test at init",
    "InpZRERunSelfTest": "ZRE self-test at init",
    "InpRXNRunSelfTest": "RXN self-test at init",
    "InpSniperRunSelfTest": "sniper self-test at init",
    "InpRuntimeNoLookaheadAudit": "assert no published level references a future bar",
    "InpUseIncrementalDetection": "the live path: closed-bar deltas, not a full rebuild each tick",
    "InpUpdateEveryTick": "OFF: decisions are made on CLOSED bars only (the EA assumes this)",
    "InpRedrawTradeBoxOnNewBarOnly": "stop per-tick chart object churn; values are closed-bar state",
    "InpDisplayMode": "FULL panel: the dashboard is the operator's instrument",
    "InpShowMTFPanel": "multi-timeframe alignment row",
    "InpShowAIDashboard": "main dashboard",
    "InpShowTopDownPanel": "HTF bias / gating mode row",
    "InpShowEntries": "entry marks on the chart",
    "InpShowSLTP": "SL/TP levels for the published setup",
    "InpShowSniperZones": "sniper zone boxes",
    "InpShowKillZones": "session kill-zone bands",
    "InpShowSessionHL": "session high/low lines",
    "InpShowPDHPDL": "previous day high/low",
    "InpShowConfluentSR": "confluent support/resistance",
    "InpShowPremiumDiscount": "premium/discount ranges",
    "InpShowOTE": "optimal trade entry zone",
    "InpShowPivots": "pivot levels",
    "InpShowCamarilla": "camarilla levels",
    "InpShowBreakers": "breaker blocks",
    "InpResolveLabelCollisions": "labels never stack on top of each other",
    "InpSmartObjectManagement": "charts objects are recycled instead of leaking",
    "InpUltraCleanMode": "OFF: cleaning the chart would hide the panel being read",
    "InpShowBattleAnnotations": "OFF: clutter, no decision value",
    "InpShowEarlyBreakPreview": "OFF: preview-only marks; the EA acts on closed bars",
    "InpShowEntryPreviewMarks": "OFF: preview-only",
    "InpShowZREEntryMarks": "OFF: preview-only",
    "InpShowFibonacci": "OFF: clutter on top of OTE/premium-discount",
    "InpShowDebugAlerts": "OFF: development output",
    "InpDebugLog": "OFF: development output",
    "InpAlertOnSetup": "popup when a setup is armed (demo chart)",
    "InpAlertOnConfirmed": "popup when the setup is confirmed",
    "InpAlertPushOnConfirmed": "OFF: no push notifications on a demo trial",
    "InpPrimaryAlertPopup": "popup channel for the primary alert",
    "InpPrimaryAlertPush": "OFF: no push",
    "InpPrimaryAlertSound": "OFF: no sound on a headless/VPS chart",
    "InpZREAlertPopup": "popup on a zone reaction",
    "InpZREAlertPush": "OFF: no push",
    "InpZREAlertSound": "OFF: no sound",
    "InpRXNAlerts": "OFF: RXN is an observation layer; its alerts duplicate ZRE's",
    "InpTopDownAlerts": "OFF: noise on every HTF flip",
    "InpAlertDispatcherLog": "OFF: the signal log already records the alerts",
    "InpUseRetestLifecycle": "OFF on purpose: enter on the published closed bar, which is what the EA's InpMaxSignalAgeBars=2 assumes",
    "InpRequireMSSAfterSweep": "OFF on purpose: a CHoCH or BOS may anchor (documented in the PRACTICAL profile)",
    "InpBlockEquilibriumEntries": "OFF on purpose: the profile already handles location",
    "InpUseEMAVWAPConfluence": "OFF on purpose: an extra confluence leg would re-tighten the profile",
}

EA_REASONS = {
    "InpEnableTrading": "ARMED: no order can be sent with this false",
    "InpDryRun": "false = orders are really sent (demo)",
    "InpAllowRealTrading": "OFF: REAL never arms itself - this is a demo preset",
    "InpRealAccountConfirm": "empty: the exact login would be required to arm REAL, and it is never typed into a shipped preset",
    "InpRealServerConfirm": "empty: the exact broker server would be required to arm REAL, and it is never typed into a shipped preset",
    "InpResetBreakersAtInit": "clears a stale day_base on load; SET IT BACK TO false after the first attach",
    "InpPinTimeframeMinutes": "pin M15: refuse to run on any other chart timeframe (the 2026-11-06 log cycled M1..H4)",
    "InpMagic": "the documented magic for this setup",
    "InpIndicatorName": "iCustom target (no quotes, no path)",
    "InpTradeComment": "tag on every order so the journal is greppable",
    "InpLotMode": "FIXED volume: 0.10 lots per trade",
    "InpRiskPercent": "inert in FIXED mode; kept at the trial value for the RISK% fallback",
    "InpMaxRiskPercent": "inert in FIXED mode; the historical ceiling is preserved",
    "InpFixedLots": "0.10 lots - the requested size",
    "InpFixedLotsMaxRiskPercent": "refuse a fixed lot whose STOP would cost more than 6% of equity (logged FIXED_LOT_TOO_BIG)",
    "InpTPLevel": "exit at the indicator's TP2 with the R1 break-even behind it",
    "InpBreakEvenAtR": "move the stop to entry at +1R",
    "InpPartialCloseAtR": "0 = the R-based partial is off: ONE exit manager owns the position",
    "InpUseTPPips": "false: use the indicator's levels, not a fixed pip ladder",
    "InpMoveSLToBEAtTP1": "off: the pip ladder is disabled, so its rung logic must be too",
    "InpMoveSLToTP1AtTP2": "off: same reason",
    "InpMaxDailyLossPercent": "fallback only - the money stop below wins when it is non-zero",
    "InpMaxDailyLossMoney": "200 in the ACCOUNT CURRENCY - the requested daily loss limit",
    "InpMaxAccountDrawdownPct": "second, independent brake: -6% of the session-start equity",
    "InpStopAfterConsecLoss": "stop after 2 losing closes in a row",
    "InpMaxOpenPositions": "one position at a time",
    "InpMaxTradesPerDay": "3 entries per server day",
    "InpMaxSpreadPoints": "gold spreads are wide; 60 points is still under a normal tick",
    "InpDeviationPoints": "slippage allowance for a market fill",
    "InpMinRRAtFill": "re-check RR at the price actually paid, not the planned zone edge",
    "InpMaxSignalAgeBars": "a 2-bar-old signal is stale on M15",
    "InpSessionStartHour": "session start, SERVER clock (10:00 as configured)",
    "InpSessionEndHour": "session end, SERVER clock (18:00 as configured)",
    "InpCooldownAfterLossMin": "60 minutes of silence after a loss",
    "InpHeartbeatSeconds": "one heartbeat every 5 minutes",
}

NADIR2_HEADER = [
    ";====================================================================",
    "; nadir2 - FULL PRODUCTION preset for XAUUSD (M15 / M30)",
    "; GENERATED by tools/generate_set_presets.py - do not hand-edit.",
    ";",
    "; Every input is present, so MT5 shows no stale value from a previous",
    "; preset. Values are the compiled defaults EXCEPT the commented",
    "; overrides below.",
    ";",
    "; WHAT IS ON",
    ";   gate profile      PRACTICAL (60 conf / 60 rel / 1.20R floors)",
    ";   causal chain      institutional sequence + invariant + replay audit",
    ";   modules           all seven advisory modules via InpEnableAllModules",
    ";   observation       ZRE, RXN, sniper zones, quant, MVP, PMI, scenarios",
    ";   diagnostics       GateAudit every 20 bars, signal log, self-tests",
    ";",
    "; WHAT IS OFF ON PURPOSE (not a defect - see the comments in the file)",
    ";   retest lifecycle, MSS-after-sweep, equilibrium block, EMA/VWAP",
    ";   confluence, chart-object clutter, push/sound alerts",
    ";",
    "; The EA reads this indicator with iCustom DEFAULTS unless the EA is told",
    "; otherwise - see docs/DEMO_SETUP_AR_FULL.md.",
    ";====================================================================",
]

# --------------------------------------------------------------------------
# QSMC_AutoTrader (execution). The numbers are the operator's plan:
# 0.10 lots fixed, a 200 money daily stop, demo only.
# --------------------------------------------------------------------------
EA_OVERRIDES = {
    "InpEnableTrading": "true",
    "InpDryRun": "false",
    "InpAllowRealTrading": "false",
    "InpRealAccountConfirm": "",
    "InpRealServerConfirm": "",
    "InpResetBreakersAtInit": "true",
    "InpPinTimeframeMinutes": "15",
    "InpMagic": "20261027",
    "InpIndicatorName": "nadir2",
    "InpTradeComment": "QSMC-DEMO-0.10",
    "InpLotMode": "QSMC_LOT_FIXED",
    "InpFixedLots": "0.10",
    "InpFixedLotsMaxRiskPercent": "6.00",
    "InpRiskPercent": "0.10",
    "InpMaxRiskPercent": "0.10",
    "InpTPLevel": "QSMC_TP_LEVEL2",
    "InpBreakEvenAtR": "1.00",
    "InpPartialCloseAtR": "0.00",
    "InpUseTPPips": "false",
    "InpMoveSLToBEAtTP1": "false",
    "InpMoveSLToTP1AtTP2": "false",
    "InpMaxDailyLossPercent": "2.00",
    "InpMaxDailyLossMoney": "200.00",
    "InpMaxAccountDrawdownPct": "6.00",
    "InpStopAfterConsecLoss": "2",
    "InpMaxOpenPositions": "1",
    "InpMaxTradesPerDay": "3",
    "InpMaxSpreadPoints": "60",
    "InpDeviationPoints": "30",
    "InpMinRRAtFill": "1.20",
    "InpMaxSignalAgeBars": "2",
    "InpSessionStartHour": "10",
    "InpSessionEndHour": "18",
    "InpCooldownAfterLossMin": "60",
    "InpHeartbeatSeconds": "300",
}

EA_HEADER = [
    ";====================================================================",
    "; QSMC_AutoTrader - DEMO PRODUCTION (0.10 lots / 200 daily stop)",
    "; GENERATED by tools/generate_set_presets.py - do not hand-edit.",
    ";",
    "; ARMED: InpEnableTrading=true + InpDryRun=false",
    "; DEMO ONLY: REAL is disabled - arming needs InpAllowRealTrading=true + exact login + exact server",
    ";",
    ";   0.10 lots fixed   InpLotMode=FIXED, InpFixedLots=0.10",
    ";   daily stop 200    InpMaxDailyLossMoney=200 in the account currency",
    ";                     (wins over the 2.00% stop; capped by HARD 10%)",
    ";   3 entries/day, 1 open, session 10:00-18:00, M15 pinned",
    ";",
    "; READ THE ATTACH BANNER before trusting it:",
    ";   [QSMC_AT] ARMED PLAN | currency ... | lot FIXED 0.10 ...",
    ";   [QSMC_AT] ARMED PLAN | daily stop: money stop 200.00 USD",
    ";   [QSMC_AT] LOT CHECK: 0.10 lots is tradable on XAUUSD ...",
    "; See docs/DEMO_SETUP_AR_FULL.md for the install order.",
    ";====================================================================",
]

DECL = re.compile(r"^\s*(?:sinput|input)\s+([\w]+)\s+([\w]+)\s*=\s*([^;]+);", re.M)


def parse(source):
    """[(name, type, default)] in declaration order."""
    out = []
    seen = set()
    for m in DECL.finditer(source):
        typ, name, default = m.group(1), m.group(2), m.group(3).strip()
        if name in seen:          # a shared header may re-declare nothing; guard
            continue
        seen.add(name)
        out.append((name, typ, default))
    return out


def clean_default(typ, raw):
    raw = raw.strip()
    if typ == "string":
        return raw if raw.startswith('"') else '"%s"' % raw
    if typ == "bool":
        low = raw.lower()
        return "true" if low in ("true", "1") else "false"
    if typ == "double":
        try:
            return repr(float(raw))
        except ValueError:
            return raw
    if typ in ("int", "long", "uint", "ulong", "short", "char"):
        try:
            return str(int(float(raw)))
        except ValueError:
            return raw
    return raw          # enums, colors, timeframes: the enumerator NAME


def render(entries, overrides, header, reasons):
    """Render the .set text.

    MT5 .set semantics: a line starting with ';' is a comment, and there is NO
    inline comment support - 'InpX=true  ; why' would set the string
    "true  ; why". Every rationale therefore goes on its OWN commented line
    directly above the key it explains.
    """
    missing = [k for k in overrides if k not in {n for n, _, _ in entries}]
    if missing:
        raise SystemExit("override names not declared in the source: %s"
                         % ", ".join(sorted(missing)))
    lines = list(header) + [""]
    for name, typ, default in entries:
        if name in overrides:
            value = overrides[name]
            why = reasons.get(name, "preset override for the demo/production plan")
            lines.append("; %s: %s" % (name, why))
        else:
            value = clean_default(typ, default)
        lines.append("%s=%s" % (name, value))
    return NL.join(lines) + NL


def main(argv):
    nadir_src = (ROOT / "nadir2.mq5").read_text(encoding="utf-8", errors="replace")
    ea_src = (ROOT / "MQL5" / "Experts" / "QSMC_AutoTrader.mq5").read_text(
        encoding="utf-8", errors="replace")

    targets = [
        (ROOT / "presets" / "nadir2_PRODUCTION_XAUUSD.set",
         parse(nadir_src), NADIR2_OVERRIDES, NADIR2_REASONS, NADIR2_HEADER),
        (ROOT / "presets" / "QSMC_AutoTrader_DEMO_0.10_200.set",
         parse(ea_src), EA_OVERRIDES, EA_REASONS, EA_HEADER),
    ]

    check = "--check" in argv
    drift = 0
    for path, entries, overrides, reasons, header in targets:
        rendered = render(entries, overrides, header, reasons)
        if check:
            # compare BYTES: read_text() applies universal-newline translation,
            # which would report drift on a file that is byte-identical.
            if not path.is_file() or path.read_bytes() != rendered.encode("utf-8"):
                print("FAIL %s is stale - run tools/generate_set_presets.py" % path.name)
                drift += 1
            else:
                print("PASS %s (%d inputs, %d overrides)"
                      % (path.name, len(entries), len(overrides)))
        else:
            path.write_text(rendered, encoding="utf-8", newline="")
            print("WROTE %s (%d inputs, %d overrides)"
                  % (path.name, len(entries), len(overrides)))
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
