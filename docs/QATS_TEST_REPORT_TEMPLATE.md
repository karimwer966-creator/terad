# QATS — Strategy Tester test report template

> Copy to `docs/QATS_TEST_REPORT_<UTC-date>.md` (or `out/tester/<run>/notes.md`).
> Complete every field. A report with TODO markers is not a report.
> **No profitability claim is made or implied by completing this template.**

## 0. No profit claim

This report measures what happened in the MT5 Strategy Tester under the configuration
in `QATS_STRATEGY_TESTER_CONFIG.md`. It is evidence about that window, on that feed,
with that fill model. It is **not** a forecast, a validation, or an endorsement of
live trading. The 2026-11-11 simulation study recorded **no demonstrated edge**.
If the numbers below do not show one out-of-sample, the verdict is **no edge**.

## 1. Identity

| Field | Value |
|---|---|
| Run ID / date-time (UTC) | |
| Tester host / OS | |
| MT5 terminal build (About banner) | |
| EA file SHA-256 (`sha256sum MQL5/Experts/QuantumAutonomousTradingSystem.mq5`) | |
| Preset file SHA-256 (`presets/Quantum_XAUUSD_PRODUCTION.set`) | |
| `QATS_VERSION` string in source | 1.23 |
| Symbol / digits / contract size | |
| Modeling / spread mode | |
| Deposit / leverage / currency | |
| Window from / to (UTC) | |
| Forward-segment start (split date) | |
| Run IDs covered (R1..R6, grid cells, §7 scenarios) | |

## 2. Build gate

| Check | Result (errors/warnings) |
|---|---|
| MetaEditor F7 on the exact source above | |
| Journal first lines (protection/policy banners) match a DEMO account | |

## 3. Summary table (primary runs)

| Run | Config change | Trades | Win % | PF | EV/trade (R) | Net | Max DD (%) | Recovery | Avg realized R:R |
|---|---|---|---|---|---|---|---|---|---|
| R1 | preset as committed | | | | | | | | |
| R2 | limit entry OFF | | | | | | | | |
| R3 | profile CONSERVATIVE | | | | | | | | |
| R4 | profile ACTIVE | | | | | | | | |
| R5 | news filter ON | | | | | | | | |
| R6 | M15 displacement OFF | | | | | | | | |

## 4. Sensitivity grid (9 cells, full window)

| Cell | MinScore 55/60/65 | DisplaceATR 1.2/1.5/2.0 | SetupWindow 12/24/48 | Trades | PF (OOS) | EV/trade (OOS) | Max DD (OOS) |
|---|---|---|---|---|---|---|---|
| G1 | 60 | 0.8 | 6 | | | | |
| G2 | 65 | 0.8 | 6 | | | | |
| G3 | 55 | 1.2 | 6 | | | | |
| G4 | 55 | 1.5 | 6 | | | | |
| G5 | 55 | 2.0 | 6 | | | | |
| G6 | 55 | 0.8 | 12 | | | | |
| G7 | 55 | 0.8 | 24 | | | | |
| G8 | 55 | 0.8 | 48 | | | | |
| R1 | 55 | 0.8 | 6 | | | | |

Pre-declared decision rule (from the config §4): preset kept as-is unless a
neighbouring cell beats it on OOS expectancy with PF > 1.05 and DD ≤ preset.

- Knife-edge cells found (yes/no; which):
- Neighbour beating the preset under the pre-declared rule (yes/no; which):
- If yes: **STOP — operator review required, nothing adopted silently.**

## 5. Walk-forward (quarterly)

| Quarter | R1 trades | R1 win % | R1 PF | R1 EV/trade | R1 net | R2 delta | Notes |
|---|---|---|---|---|---|---|---|
| 2024Q1 | | | | | | | |
| 2024Q2 | | | | | | | |
| 2024Q3 | | | | | | | |
| 2024Q4 | | | | | | | |
| 2025Q1 | | | | | | | |
| 2025Q2 | | | | | | | |
| 2025Q3 | | | | | | | |
| 2025Q4 | | | | | | | |
| 2026Q1 | | | | | | | |
| 2026Q2 | | | | | | | |
| 2026Q3 | | | | | | | |

Forward segment (split date → end of window) isolated:

| Segment | Trades | Win % | PF | EV/trade | Net | Max DD |
|---|---|---|---|---|---|---|
| In-sample (2024-01-01 → split) | | | | | | |
| Forward (split → 2026-10-31) | | | | | | |

## 6. Decomposition (R1; zero-trade classes stated explicitly)

| Slice | Trades | Win % | PF | EV/trade | Net |
|---|---|---|---|---|---|
| BUY side | | | | | |
| SELL side | | | | | |
| Asia session (broker server-time) | | | | | |
| London session | | | | | |
| New-York session | | | | | |
| Regime TREND_BULL | | | | | |
| Regime TREND_BEAR | | | | | |
| Regime RANGE | | | | | |
| Regime HIGH_VOL | | | | | |
| Regime LOW_VOL / UNCLEAR | | | | | |
| P/D premium bucket | | | | | |
| P/D discount bucket | | | | | |
| P/D equilibrium bucket | | | | | |
| Entry via LIMIT | | | | | |
| Entry via market (R2) | | | | | |
| Displacement on H1 | | | | | |
| Displacement on M15 (fallback) | | | | | |

## 7. Phase-9 journal diagnostics (R1)

| Item | Count |
|---|---|
| `[QATS][ANALYSIS]` records emitted | |
| — of which `EXECUTION_STATUS=EXECUTED` | |
| — of which `BLOCKED` / `REJECTED` / `NOT_PLACED` | |
| `[QATS][FINAL]` `DECISION=BLOCKED` | |
| `[QATS][GUARD]` high-score rejections (score ≥ InpMinScore) | |
| Top-3 `REJECTED AT=.. REASON=..` pairs (with counts) | |
| `[QATS][BLOCK][REASON]` vs FINAL mismatch count | |
| Worst-loss day: `[QATS][HB]` / `[QATS][RISK]` tail snapshot | |

`qats_journal_report.py` output (BUY vs SELL) attached: yes/no — path:

## 8. Spread scenario runs (§7 of the config)

| Fixed spread | Trades | PF | EV/trade | Net | Verdict vs R1 |
|---|---|---|---|---|---|
| 20 pts | | | | | |
| 30 pts | | | | | |
| 50 pts | | | | | |

## 9. Verdict (exactly one)

- [ ] **NO EDGE** — out-of-sample PF < 1.0 or OOS EV ≤ 0 (expected prior per the 2026-11-11 study)
- [ ] **INSUFFICIENT EVIDENCE** — too few trades / window not available / tick data missing
- [ ] **EDGE PRESENT — UNCONFIRMED** — OOS positive, consistent across ≥ 2 of 3 forms (primary + grid + quarterly), and insensitive to ±1 parameter step; still requires ≥ 4 weeks DEMO forward test
- [ ] **EDGE PRESENT — CONFIRMED ON DEMO** — the above plus ≥ 4 weeks forward test on DEMO with metrics within 20% of the tester split; only this opens a REAL discussion via `QSMC_GO_LIVE_RUNBOOK.md`

Reviewer name / date / signature line:

## 10. What this report changes

- EA source: unchanged / changed (files, hashes, and the operator authorization for the change)
- Preset: unchanged / changed (exact keys and values; re-verify checklist re-run)
- Docs updated: CHANGELOG / audit addendum / this file cross-linked
- REAL trading: remains disarmed (`InpAllowRealTrading=false`) — always, regardless of §9

## Appendix — exact tester settings used (paste the tester's own dump)

```
(paste)
```
