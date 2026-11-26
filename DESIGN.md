# Confirmation-Score Engine — Phase 2 Design

**Status:** implemented as a new, optional, dry-run-by-default EA. The existing production `MQL5/Experts/QSMC_AutoTrader.mq5`, `nadir2.mq5`, the 34-header include layer, presets and REAL authorization are **not modified**. This design is intentionally additive: the old rigid path remains available for A/B comparison, while the new engine owns zone identity, scoring, observability and (only after explicit operator opt-in) its own orders.

## 1. Non-trivial decisions and why

1. **Additive EA, not a patch to the CORE-buffer EA.** `AUDIT.md` §1 shows the visible QSVP zone / `Z|...` id is not the AutoTrader execution input. Rewiring AutoTrader would silently change a production order boundary. The new `MQL5/Experts/QSMC_ConfirmationEngine.mq5` reads chart objects and tooltips directly, scores them, logs them, and stays disarmed by default.
2. **Root documents.** `AUDIT.md`, `DESIGN.md` and `CHANGELOG.md` are at the repository root because the user named those exact deliverables. `tools/check_repo_layout.py` L1 was amended to allow exactly these three additional root files; every other new document lives under `docs/` and is indexed in `docs/INDEX.md`.
3. **One reviewed trade-API exception.** `tools/check_release_gate.py` G4 names the additive confirmation EA as a third exclusion and **G9 now enforces its whole-file contract**: dry-run ON, live orders OFF, REAL/CONTEST refused at `OnInit`, position management short-circuited before any mutating trade API, per-order REAL/permission re-check, kill switch, daily-loss lock, max concurrent positions, capped risk, no `WebRequest`, no martingale, no grid and no averaging down. The exclusion is printed in the gate output; it is not a silent bypass. `tools/mql5_rules.py` also lints the new EA as its own translation unit. `tools/static_check.py` intentionally keeps the legacy one-unit class model: the CE EA has its own `CZoneRegistry` and is verified by the native strict C++17 build instead of being spliced into the 34-header model.
4. **Single UTC clock.** All scoring/session comparisons use `datetime` seconds in UTC. `TimeCurrent()` / object anchor times are broker-server times and are converted with configurable `InpBrokerUtcOffsetWinterMinutes` / `InpBrokerUtcOffsetSummerMinutes` and an EU-DST rule. Algeria (UTC+1, no DST) and the operator-facing kill zones are derived from UTC. EU and US DST helpers are unit-tested at spring/fall edges.
5. **Sessions affect scoring and entry permission, never zone existence.** A zone born in Asia is registered, persisted and scored. `InpRequireSessionPermission` can refuse an Asia/off-peak entry with `SESSION_PERMISSION`, but the zone remains in `ZoneRegistry` for a later London/NY retest.
6. **State, not a boolean.** `DETECTED -> VALIDATED -> TESTED(MITIGATED) -> TRIGGERED -> EXPIRED/INVALIDATED` is a validated transition table. MITIGATED is `TESTED`, not a rejection. Age moves a zone to `EXPIRED`; it never deletes it or marks it done because one filter failed.
7. **Hash-map registry with persistence.** `CZoneRegistry` is a fixed-capacity open-hash table keyed by canonical zone id. `CE_SerializeZone` / `CE_DeserializeZone` produce a tab-delimited snapshot written to `InpRegistryFile` in the terminal common folder. A reload restores identity, state, touches and last decision.
8. **Dedicated `ZoneParser`.** `Z|BUY|<epoch>` / `Z|SELL|<epoch>` and the current `QSVP_ZN_B<n>` / `QSVP_ZN_S<n>` object names are both accepted. Tooltip text from `MQL5/Include/QSMC/QSMC_SvpChart.mqh:1142-1148` is parsed in one class, not by scattered `StringFind` calls. The canonical id is taken from the tooltip's `Z|...` token; if it is missing, a stable `Z|BUY|<anchor_utc>` / `Z|SELL|<anchor_utc>` id is generated from the object's direction and anchor time.
9. **Score, not veto.** Eight weighted components sum to a 0–100 normalized score. HTF bias adds or subtracts points and reduces size for counter-trend setups; it vetoes only when the HTF component itself is below `InpMinHtfPoints`. The AI opinion is at most 5 of 100 points and is never required: on timeout, malformed JSON, stale `as_of`, or `InpUseAIAgent=false`, the other 95 points are renormalized.
10. **Strategy-pattern entry modes.** Three mode evaluators share one `Evaluate(facts, entry, why)` signature and are selected by `InpEntryMode`: Retest (edge / 50% after a confirmed close), Momentum (closed beyond zone + micro-BOS or first pullback, capped by ATR chase), Reversal-after-mitigation (sweep + M1 CHoCH + second reaction). The dispatcher is explicit rather than virtual because MQL5 class pointers and dynamic allocation add risk without benefit here.
11. **Dry-run is the shipping default.** `InpDryRun=true`, `InpAllowLiveOrders=false`, `InpAllowRealTrading=false`. `InpMasterEnable=true` lets the engine evaluate and log without orders. A REAL account is refused unconditionally; no REAL confirmations are shipped. `InpKillSwitch` and a persisted daily-loss latch can stop entries. No code doubles lots, widens stops, adds to losers or places a grid.
12. **Structured observability.** Every evaluated zone produces one `CE|key=value` log line and one CSV row with all eight component scores, raw/available points, total, tier, decision, reject code and reject values. A `Comment()` panel shows the top three zones, their breakdowns and the last decision. Files are rewritten as bounded snapshots from terminal-local buffers; no `WebRequest` is made by this EA.
13. **Offline verification only.** The native harness compiles the real MQL5 text against the existing typed shim and executes pure logic. It is not MetaEditor F7, not Strategy Tester and not a live MT5 demo. The backtest report is a deterministic synthetic surrogate with a written Strategy Tester plan; no broker tick data or MT5 terminal exists in this sandbox.

## 2. Architecture

```
chart objects / tooltips (QSVP_ZN_* or Z|...)
        -> CZoneParser::ZP_ParseZoneObject()
        -> CZoneRegistry (hash map by id, transition table, snapshot)
        -> CE_BuildFacts()  [M1 ATR, M5/M15 structure, H1/H4 bias,
                             volume profile, UTC session, spread, AI file]
        -> CE_EvaluateZone() [CE_ScoreComponents -> CE_ApplyDecision -> CE_BuildPlan]
        -> CE_FormatLogLine() + CE_FormatCsvRow() + CE_UpdatePanel()
        -> CE_PlaceOrder() only if explicitly armed and account is DEMO
        -> CE_ManagePositions() [breakeven after 1R, partial TP at nearest liquidity]
```

`CE_LoadAIOpinion()` reads a small JSON file written by an external companion (not shipped). Schema:

```json
{"direction":-1,"confidence":0.72,"reasons":"sweep; choch; h4 aligned","invalidation":"close above 3570","as_of":1732482900}
```

`direction` must be `1` or `-1`; `confidence` is 0..1; `reasons` and `invalidation` are non-empty strings without commas/braces; `as_of` is a UTC epoch. Missing, stale, malformed, disabled or timed-out opinions set `ai_used=false` with a reason code and remove the AI component from the denominator. The opinion is never the sole authority and never loosens account/session/RR gates.

## 3. Score components (0–100 normalized)

| Component | Max | Inputs / evidence |
|---|---:|---|
| Zone quality | 20 | OB+FVG > OB > FVG; DETECTED/VALIDATED/TESTED; size vs ATR; freshness; first vs repeated touch |
| Liquidity | 15 | Asia/London H/L sweeps, BSL/SSL, EQH/EQL, sweep before reaction |
| Structure | 20 | M1 CHoCH, M5 BOS, confirmation candle **close**, second reaction |
| HTF | 15 | H4/H1 alignment points; counter H4 is a penalty and size reduction, not a directional veto |
| Volume / value | 10 | POC reaction, VAH/VAL reaction, M1 volume expansion |
| Session | 10 | London +10, NY +8, Asia +2, off-peak +0 (UTC-derived Algeria windows) |
| Execution quality | 10 | spread, ATR percentile, room to opposing liquidity for RR >= `InpMinRRAtFill` |
| AI opinion (optional) | 5 | structured JSON only; absent => denominator is 95, not 100 |

Tiers: `score >= InpTierA` => A / full risk; `InpTierB <= score < InpTierA` => B / `InpTierBRiskScale`; `< InpTierB` => C / no trade but a logged near miss. `InpMinHtfPoints` is the only HTF veto and applies to the HTF component, not to direction.

## 4. Time contract

* `CE_ServerToUtc(server, winter, summer, use_dst)` resolves the two possible broker offsets against `CE_IsEuDst(utc)`. Spring-forward gap maps to the summer candidate; fall-back ambiguity deterministically maps to the later (winter) UTC. Both edges are tested.
* `CE_IsEuDst`: last Sunday March 01:00 UTC -> last Sunday October 01:00 UTC.
* `CE_IsUsDst`: second Sunday March 07:00 UTC -> first Sunday November 06:00 UTC. Tested for informational use; Algeria kill zones do not shift with US/EU DST.
* Algeria local = UTC+1. Default kill zones in Algeria local: Asia 00:00–08:00, London 09:00–12:00, NY 15:30–19:00. In UTC: Asia 23:00–07:00, London 08:00–11:00, NY 14:30–18:00. Windows are half-open.

## 5. Risk and execution

* Lots = `equity * InpRiskPercent/100 * risk_scale / (stop_distance/point * tick_value)`, floored to `InpLotStep` and clamped to `InpMinLots..InpMaxLots`. No multiplier is applied after a loss.
* SL is beyond both the zone boundary and invalidation, plus `InpAtrBuffer * ATR`, then widened to broker stops/freeze and `InpMinStopPoints`. It is always snapped **away** from entry.
* TP1 / partial TP is the nearest opposing liquidity that still pays `>= InpMinRRAtFill`; final TP is `InpTpRRMultiple * R`. After `InpBreakEvenAtR`, SL trails to a spread-aware breakeven.
* Hard gates: master switch, kill switch, REAL/CONTEST refusal at `OnInit` and again on the account/permission path, persisted daily-loss lock, `InpMaxConcurrentTrades`, `InpMaxTradesPerDay`, cooldown after any entry, account/terminal permissions, spread, RR at fill, retcodes. `CE_ManagePositions()` returns before `PositionModify`/`PositionClosePartial` while `InpDryRun=true` or `InpAllowLiveOrders=false`; managing an existing same-magic position is a mutating action and is not allowed in the shipping default. Transient retcodes are retried at most `InpMaxOrderRetries` times with unchanged size; permanent retcodes mark the evaluation `BLOCKED` but leave the zone alive.
* Duplicate protection is by zone id + state, not by "seen" bar identity. A refused plan never burns the zone; only `TRIGGERED` after a confirmed order consumes the entry.

## 6. Verification plan

* `tools/confirmation_native.py` builds the real EA text as a strict C++17 host translation unit with `tools/qats_sim/qsmc_ce_shim.h`, `tools/qats_sim/qsmc_ce_driver.inc` and `tools/qats_sim/qsmc_ce_replay.inc`. Its `selftest` mode executes the parser, state machine, registry round-trip, UTC/DST, scoring tiers, AI timeout, entry modes, account gates, risk scaling, CSV/log schema, panel, collection and partial-close paths. `tools/test_confirmation_engine.py` additionally asserts the 55 input surface and the G9/MQL5 dialect contracts.
* `tools/confirmation_replay.py` and `tools/test_confirmation_replay.py` replay both 2026-11-25 setups across Asia/London/NY and a UTC day boundary; they generate and verify `docs/CONFIRMATION_ENGINE_REPLAY_2026-11-25.md` plus the 42-column `docs/confirmation_replay_2026-11-25.csv`.
* `tools/confirmation_backtest.py` and `tools/test_confirmation_backtest.py` generate and verify `docs/CONFIRMATION_ENGINE_TEST_BACKTEST_2026-11-25.md`: a deterministic 92-day/132,480-M1-bar synthetic surrogate, chronological walk-forward split and parameter sensitivity. The report explicitly says this is not Strategy Tester, not broker ticks and not evidence of an edge.
* `.github/workflows/qsmc-verify.yml` runs the four new offline contracts; the curated production job runs the release gate with G9. Operator steps that remain outside this sandbox: F7 in MetaEditor, XAUUSD M1 every-tick variable-spread Strategy Tester for at least three months using broker ticks, and a 24-hour MT5 demo paper run. The reports say so explicitly.

## 7. Assumptions carried to the PR

1. Arena fixes the branch to `arena/13d1250e-terad`; the requested `feature/confirmation-engine` cannot be created here. Commits stay on the fixed branch and the PR discloses this.
2. "Chart time" is broker-server time; broker winter offset is ambiguous between configured UTC+2 and the owner-observed UTC+1. Both are configurable; default is UTC+2 winter / UTC+3 EU-DST summer.
3. No AI endpoint, API key or schema sample was supplied; the optional opinion is file-based JSON with a max-age timeout.
4. No Experts log, `.set`, tick data or exact account type was supplied. Replay uses source-derived facts and the two user-described zone geometries; exact 2026-11-25 runtime blockers remain unknown.
5. `Z|...` is currently a tooltip/setup id, not the chart object name. Backward compatibility means parsing both forms, not renaming shipped objects.
