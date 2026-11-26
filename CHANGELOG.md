# Changelog — Confirmation Engine Phase 2

**Date:** 2026-11-25<br>
**Branch:** `arena/13d1250e-terad` (Arena fixed the branch name; the requested `feature/confirmation-engine` is disclosed as a deviation in the PR).<br>
**Base:** `ea298c9` after the committed Phase 1 audit `8f51623`.<br>
**Version:** additive on QSMC v6.6.24; no host indicator, production EA, preset, include-layer, input-fingerprint, or REAL-authorization version is changed.

## 1. What changed

- Added `AUDIT.md` (Phase 1, committed) and this `DESIGN.md` / `CHANGELOG.md` pair. Root documentation is limited to these three files; reports live under `docs/` and are indexed in `docs/INDEX.md`.
- Added the optional additive EA `MQL5/Experts/QSMC_ConfirmationEngine.mq5`. It reads chart objects/tooltips directly, keeps a canonical zone registry, scores eight components, logs `CE|key=value` lines and a 42-column CSV, renders a top-three `Comment()` panel and computes a plan. `MQL5/Experts/QSMC_AutoTrader.mq5`, `nadir2.mq5`, the 34-header include layer, presets and REAL authorization are unchanged.
- Added host-only native verification: `tools/confirmation_native.py`, `tools/qats_sim/qsmc_ce_shim.h`, `tools/qats_sim/qsmc_ce_driver.inc`, `tools/qats_sim/qsmc_ce_replay.inc` and M1/partial-close support in `tools/qats_sim/mql5_shim.h`. The strict C++17 build and selftest are **not** MetaEditor F7, **not** Strategy Tester and **not** a live demo.
- Added replay/backtest deliverables: `tools/confirmation_replay.py`, `tools/test_confirmation_replay.py`, `docs/CONFIRMATION_ENGINE_REPLAY_2026-11-25.md`, `docs/confirmation_replay_2026-11-25.csv`, `tools/confirmation_backtest.py`, `tools/test_confirmation_backtest.py` and `docs/CONFIRMATION_ENGINE_TEST_BACKTEST_2026-11-25.md`.
- Added `tools/test_confirmation_engine.py`, a named G4 by-name exception plus **G9** in `tools/check_release_gate.py`, a separate CE unit in `tools/mql5_rules.py`, and the four new offline contracts in `.github/workflows/qsmc-verify.yml`.
- Tightened the new EA after review: `OnInit()` refuses REAL and CONTEST accounts, and `CE_ManagePositions()` short-circuits before any `PositionModify` / `PositionClosePartial` while dry-run is ON or live orders are OFF. No shipped setting enables live trading.

## 2. Shipping safety defaults

| Switch | Default | Contract |
|---|---|---|
| `InpDryRun` | `true` | demo/dry-run is ON; `CE_PlaceOrder()` returns `DRY_RUN` without an order |
| `InpAllowLiveOrders` | `false` | explicit executor arming switch stays OFF |
| `InpAllowRealTrading` | `false` | REAL is always refused; no REAL confirmation is shipped |
| `InpMasterEnable` | `true` | evaluation/logging can run while the executor is disarmed |
| `InpKillSwitch` | `false` | operator can stop entries without deleting zones |
| `InpUseAIAgent` | `false` | optional local-file opinion is off by default |
| `InpRiskPercent` | `0.25` | below the documented 0.50% risk ceiling |
| `InpMaxDailyLossPercent` | `0.50` | below the documented 2.00% daily-loss ceiling |

G9 pins these defaults, the REAL/CONTEST init refusal, the account/per-order REAL re-check, the early dry-run guard for position management, bounded risk, no `WebRequest`, no martingale and the named G4 exception. A REAL account is not a supported runtime for this engine.

## 3. New input surface (55 inputs)

The table is derived from the `input` declarations in `MQL5/Experts/QSMC_ConfirmationEngine.mq5`; the source remains the authority.

| Input | Type | Default | Purpose |
|---|---|---|---|
| `InpMasterEnable` | `bool` | `true` | master evaluation switch |
| `InpDryRun` | `bool` | `true` | demo/dry-run default ON |
| `InpAllowLiveOrders` | `bool` | `false` | explicit opt-in for orders |
| `InpAllowRealTrading` | `bool` | `false` | REAL is always refused |
| `InpKillSwitch` | `bool` | `false` | operator kill switch |
| `InpMagic` | `int` | `20261125` | order magic |
| `InpDeviationPoints` | `int` | `20` | CTrade deviation |
| `InpTradeComment` | `string` | `"CE"` | order comment |
| `InpMaxOrderRetries` | `int` | `2` | transient retcode retries |
| `InpUseLimitOrders` | `bool` | `true` | retest uses limit orders |
| `InpBrokerUtcOffsetWinterMinutes` | `int` | `120` | server = UTC + winter |
| `InpBrokerUtcOffsetSummerMinutes` | `int` | `180` | server = UTC + summer |
| `InpBrokerUsesEuDst` | `bool` | `true` | EU DST broker offset |
| `InpRequireSessionPermission` | `bool` | `true` | session entry permission |
| `InpAllowAsiaEntries` | `bool` | `false` | Asia entries |
| `InpAllowOffPeakEntries` | `bool` | `false` | off-peak entries |
| `InpTierA` | `int` | `75` | full risk at or above |
| `InpTierB` | `int` | `55` | reduced risk at or above |
| `InpMinHtfPoints` | `int` | `3` | HTF component floor |
| `InpTierBRiskScale` | `double` | `0.50` | B-tier risk scale |
| `InpHtfCounterRiskScale` | `double` | `0.60` | counter-H4 risk scale |
| `InpRiskPercent` | `double` | `0.25` | equity risk per trade |
| `InpMinLots` | `double` | `0.01` | minimum lots |
| `InpMaxLots` | `double` | `1.00` | maximum lots |
| `InpLotStep` | `double` | `0.01` | lot step |
| `InpMinStopPoints` | `int` | `20` | minimum stop points |
| `InpAtrBuffer` | `double` | `0.30` | SL ATR buffer |
| `InpInvalidationATR` | `double` | `1.00` | invalidation beyond zone |
| `InpTpRRMultiple` | `double` | `2.00` | final TP in R |
| `InpPartialTpFraction` | `double` | `0.50` | partial close fraction |
| `InpBreakEvenAtR` | `double` | `1.00` | trail to BE after 1R |
| `InpMinRRAtFill` | `double` | `1.20` | minimum RR at fill |
| `InpMaxSpreadPoints` | `double` | `60.0` | maximum spread points |
| `InpAtrPercentileLow` | `double` | `20.0` | ATR percentile low |
| `InpAtrPercentileHigh` | `double` | `80.0` | ATR percentile high |
| `InpAtrPeriod` | `int` | `14` | ATR period |
| `InpAtrPercentileLookback` | `int` | `100` | ATR percentile window |
| `InpHtfLookbackBars` | `int` | `50` | H1/H4 bias lookback |
| `InpLiquidityLookbackBars` | `int` | `50` | opposing liquidity lookback |
| `InpProfileLookbackBars` | `int` | `50` | volume profile lookback |
| `InpMaxZoneAgeHours` | `int` | `48` | zone lifecycle TTL |
| `InpEntryMode` | `int` | `0` | 0 retest, 1 momentum, 2 reversal |
| `InpRetestEntryPercent` | `double` | `50.0` | 0 edge, 50 midpoint |
| `InpMaxChaseATR` | `double` | `1.50` | momentum max chase |
| `InpUseAIAgent` | `bool` | `false` | optional opinion component |
| `InpAIFile` | `string` | `"QSMC\\ai_opinion.json"` | opinion JSON |
| `InpAITimeoutMs` | `int` | `250` | file-read deadline |
| `InpAIMaxAgeSec` | `int` | `60` | opinion max age |
| `InpMaxDailyLossPercent` | `double` | `0.50` | hard daily loss lock |
| `InpMaxConcurrentTrades` | `int` | `1` | hard max positions |
| `InpMaxTradesPerDay` | `int` | `3` | hard daily trade cap |
| `InpCooldownMinutes` | `int` | `60` | minutes after any entry |
| `InpCsvLog` | `bool` | `true` | structured CSV |
| `InpCsvFile` | `string` | `"QSMC\\confirmation_evaluations.csv"` | — |
| `InpRegistryFile` | `string` | `"QSMC\\confirmation_registry.txt"` | — |

## 4. Behavioural contract

- Parses both user-described `Z|BUY|<epoch>` / `Z|SELL|<epoch>` object names and current `QSVP_ZN_B*/S*` chart objects with `Z|...` tooltip/setup IDs.
- Keeps zones alive across Asia, London, New York, off-peak and UTC day boundaries. Sessions affect score and entry permission, not existence.
- `TESTED_MITIGATED` is a second-reaction state, not a rejection; `EXPIRED`/`INVALIDATED` are terminal states.
- H1/H4 bias contributes score and reduces size for counter-H4 plans; it is not a rigid directional veto. The only HTF floor is `InpMinHtfPoints` on the HTF component itself.
- Optional AI opinion requires `direction`, `confidence`, `reasons`, `invalidation`, `as_of`; disabled, missing, timed-out, malformed, stale and direction-mismatch cases fall back. A valid opinion adds at most 5 of 100 points and never loosens account/session/RR gates.
- Score, state, parser, UTC/DST and risk layers are replayable from the native harness. Every evaluation emits a structured log line, a 42-column CSV row and a panel update.
- Transient order retcodes can be retried with unchanged size only after explicit operator arming; a refused plan never burns a zone.

## 5. Verification and limits

Offline: `tools/confirmation_native.py` (strict host build + selftest), `tools/test_confirmation_engine.py`, `tools/confirmation_replay.py --check`, `tools/test_confirmation_replay.py`, `tools/confirmation_backtest.py --check`, `tools/test_confirmation_backtest.py`, `tools/check_release_gate.py` (G9), `tools/mql5_rules.py`, `tools/static_check.py`, layout, preset, include-graph and QATS/QSVP native regression suites.

Not performed here: MetaEditor/MT5/wine are unavailable, so there is no F7 compile, no Strategy Tester result, no broker-latency measurement and no live or demo MT5 run. The 3-month report is a deterministic synthetic M1 surrogate with a written operator plan; it is not broker tick data and not evidence of profitability.

## 6. Assumptions carried to the PR

- Broker winter offset is ambiguous: configured UTC+2 vs owner-observed UTC+1; both are configurable and the replay uses the shipped UTC+2 / EU-DST UTC+3 default.
- No runtime Experts log, trial CSV, `.set`, exact account type, broker symbol suffix or tick data was supplied.
- No AI endpoint, API key or structured opinion schema sample was supplied; the optional opinion is a bounded local JSON file.
- `Z|...` is currently a tooltip/setup ID, not the chart object name; the engine parses both forms rather than renaming shipped objects.
- No AutoTrader consumption of QSVP objects existed before this additive engine; the legacy CORE-buffer execution path is deliberately untouched.
- No approval was inferred for AUD-03/AUD-04/AUD-05 or other behaviour-changing patches to production execution logic.
