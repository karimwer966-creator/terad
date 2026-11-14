# QATS Master Engineering Audit — QuantumAutonomousTradingSystem.mq5

**Date:** 2026-11-13 | **File:** `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` | **Version:** v1.23 (`QATS_VERSION "1.23"`) | **Size:** 4,053 lines | **Branch:** `arena/8397a41f-terad` (from `main` @ `db025e9`)
**Method:** complete manual read of every section (1–25), every function listed in §2, every input. No source file was modified by this audit. The offline g++ shim suites (`tools/`) were NOT re-run for this report; no MQL5 compiler was run — nothing in this document claims a MetaEditor compile.
**Verdict class:** AUDITED (Phase 1 complete). Not modified yet; not compile-verified; not backtested; not production-ready.

---

## 1. Executive summary

The EA is a coherent, conservative, guard-first SMC/liquidity research system for XAUUSD: D1/H4 EMA context → H1 confirmed-swing structure (BOS/CHoCH) → H1 liquidity map (BSL/SSL, equal highs/lows, PDH/PDL/PWH/PWL) with INTACT/SWEPT/ACCEPTED/SPENT lifecycle → H1-first (M15 fallback) displacement → OB/FVG zones → M15/M5 confirmation → deterministic confluence scoring → layered persistent guards → market or OB/FVG-limit execution, with partial bank, break-even, daily-loss lock, drawdown halt, consecutive-loss cooldown and full journal audit trail.

The architecture is sound and much of it is genuinely good: closed-bar discipline everywhere, account binding, DEMO-first authorization with an explicit REAL opt-in, persisted breakers with repair logic, one-reservation-per-setup, and structured logging. **Preserve it.**

It is not, however, the system the mission requires yet. The headline gaps:

1. **Premium/Discount protection is single-range and duplicated** — two copies of "highest high minus lowest low over `InpSwingLookback` (120) H1 bars, midpoint = equilibrium" (`DealingRangePosition`, `LimitPriceInPD`). No long/short/swing-range comparison, no freshness validation, no logging of the EQ values, and the data-failure fallback silently degrades to neutral/0.5.
2. **The market-order path has NO premium/discount hard protection at all.** `InpLimitNeedPD` (default `true`) gates only LIMIT entries (SELL premium / BUY discount). On the market path, PD exists only as a 10-point location score; a BUY in deep premium with score ≥ 55 is still sent.
3. **News filter: absent entirely.** There is no economic-calendar handling anywhere in the EA.
4. **Per-bar redundant recomputation** — swings and the liquidity map are rebuilt two or three times per new M5 bar (AnalyzeMarket → BuildTradePlan / BuildLimitPlan), all through uncached `iHigh/iLow/iClose` calls.
5. **Execution-guard asymmetry** — XAUUSD gets duplicate-order reservation (`GlobalVariableSetOnCondition`); every other symbol gets none.
6. **`ZoneStillValid` fails OPEN on missing history** (closes beyond available bars read as 0.0 and never invalidate a zone).
7. **Missing required diagnostics contract** — no `[QATS][PD]`, `[QATS][SCALPING]`, `[QATS][RISK]`, `[QATS][FINAL]`, `CORE_STATUS/STRUCTURE_STATUS/...` single-record output; High-score-but-rejected setups are not explained as one record.

None of these is a license to relax anything. Every fix in the plan below keeps risk controls intact or tightens them.

---

## 2. Function / component inventory (complete)

Inputs: 6 groups — (1) master/risk/guards L145–176, (2) D1/H4/H1/M15 structure & swings L178–186, (3) scoring/profile/conflict L176–203, (4) displacement/zone L~186–205, (5) limit entry L206–214, (6) maintenance L214+.
Enums: `ENUM_QATS_STRATEGY_PROFILE`, `QSMC_CLASS_*`, `SIGNAL_PROFILE_*`, `ENUM_SIGNAL_EXECUTION_PROFILE`.
Structs: `SSwing`, `SLiquidityPool`, `SZone`, `SReading`, `SSide`, `SStructure`, `SAnalysis`, `SClosedPos`.
Globals: persisted-GV key helpers (`GVKey/GVGet/GVSet/GVDel`, `TodayKey`, `ResetBreakers`), indicator handles ×10, guard state, statistics, signal/dedup keys, `CTrade g_trade`.

| § | Lines | Contents (functions) |
|---|-------|----------------------|
| 1–6 | 1–175 | Header/history, inputs, enums/weights `QATS_W_*`, version `QATS_VERSION` |
| 7 | 392–473 | PERSISTED GUARD STATE (`GVKey`, `GVGet/GVSet/GVDel`, `TodayKey`, `ResetBreakers`) |
| 8 | 496–561 | SYMBOL SPEC (`LoadSymbolSpec`, `PrintSymbolSpec`) |
| 9 | 563–642 | ACCOUNT GUARD (`VerifyAccountProtection`, `EffectiveRiskPercent`, `EffectiveDailyLossPercent`, `EffectiveDrawdownPercent`, `BufValue`) |
| 10 | 654–722 | INDICATOR SNAPSHOT (`SmaVolume`, `SessionVWAP`, `LoadReading`, `BiasFrom`) |
| 11 | 723–851 | MARKET STRUCTURE (`IsFractal`, `FindSwings`, `BuildStructure`, `HighestHigh`, `LowestLow`, `DealingRangePosition`) |
| 12 | 851–1010 | LIQUIDITY (`FirstPierceShift`, `FirstPierceSince`, `EvaluatePool`, `AddPool`, `BuildLiquidityMap`, `PoolRank`, `SweepForDirection`, `NearestLiquidityTarget`) |
| 13 | 1069–1202 | TIME/DISPLACEMENT/OB/FVG (`ShiftOfTime`, `DetectDisplacement`, `FindOrderBlock`, `FindFVG`, `PriceNearZone`, `ZoneStillValid`) |
| 14 | 1204–1256 | M15/M5 (`M15Confirms`, `M5Trigger`, `IsXAUUSD`, `QATS_DirectionVeto`, `QATS_ScoreEligible`, `QATS_StopsValid`, `QATS_SnapToTick`, `QATS_ScoreSide`, `QATS_CoreGate`, `QATS_ResolveDirection`, `QATS_Candidate`, `QATS_ClassifyClose`, `QATS_StrategyProfileName`, `SideIndex`, `SideName`, `VetoName`, `SetupId`, `PriceText`, `BarText`, `H1BarText`) |
| 15 | 1447–1605 | SIDE EVAL (`ResetSide`, `ResetAnalysis`, `EvaluateSide`) |
| 16 | 1605–1700 | LOGGING (`SideTrace`, `ChainText`, `LogSignal`, `AnnounceSide`) |
| 17 | 1698–1744 | SIGNAL RESERVATION (`InitSignalKeys`, `ReserveSignal`, `SetupAlreadyTraded`, `MarkSetupTraded`) |
| 18 | 1744–2160 | ANALYSIS & PLAN (`AnalyzeMarket` L1744, `BuildTradePlan` L1807, `CalcPositionVolume` L1920, `AddBlock`, `CooldownText`, `GuardBlocks` L2043, `EntriesAllowed` L2102, `CountMyPositions` L2109, `OppositePositionOpen` L2124, `CollectEntryBlocks` L2140) |
| 19 | 2158–2440 | EXECUTION (`ConfigureTrade`, `VerifyPositionOpened`, `QATS_ClassName/ProfileName/Classify/ProfileAllows/Audit`, `ExecuteSignal` L2246, `ProcessPendingRetry` L2410) |
| 20 | 2445–2588 | POSITION MANAGEMENT (`ManagePositions` L2445, `IsStopValid`, `PartialClose`, `ClosePositionOnOpposite`) |
| 20b | 2588–3306 | LIMIT ENTRY v1.21 (`LimitMoneyPerPriceUnit` **dead**, `CountMyPending` L2630, `ZoneUnmitigated`, `ZoneOverlaps`, `LimitEntryPrice`, `PickEntryZone`, **`LimitPriceInPD` L2738**, `BuildLimitPlan` L2767, `IsInvalidFillRetcode/IsPlacedOrDone`, `PlaceLimitOrder` L2965, `CancelReasonName`, `PendingOrderSetupTime`, `DeletePendingOrder`, `ManagePendingOrders` L3207) |
| 21 | 3306–3624 | DAILY GUARDS (`BoundAccountActive`, `NeutralBandMoney`, `ClearCooldownState`, `StartCooldown`, `UpdateCooldownState`, `PrintStats`, `UpdateDailyGuards`, `PositionStillOpen`, `FindClosedPos`, `ProcessClosedDeals`, `InitDealWatermark`) |
| 22 | 3647–3677 | HEARTBEAT/PANEL (`Heartbeat`, `DrawPanel`) |
| 23 | 3679–3818 | LIFECYCLE (`OnInit`, `ReleaseHandles`, `OnDeinit`) |
| 24 | 3827–4001 | TICK/SIGNAL LIFECYCLE (`LogBlock`, `LogRejected`, `ProcessSignal`, `OnTick`) |
| 25 | 3999–4053 | TRANSACTION LOG (`OnTradeTransaction`) |

---

## 3. What is correct — do not touch

- Closed-bar discipline in ALL decision paths (shift ≥ 1); swings need k closed wings (`IsFractal` bounds `s-k>=1`, `s+k<bars`); BOS/CHoCH from closed closes only; same-bar double-break credits neither side (`BuildStructure`).
- Displacement: H1 first, M15 fallback (v1.23) — M15 uses **M15 ATR**, M15 bar indices never enter H1 zone logic (`impulse` is mapped via `ShiftOfTime`), M15 rejection-bar anchor prevents counting impulses that precede the sweep.
- Liquidity lifecycle INTACT/SWEPT/ACCEPTED/SPENT with per-pool event bars (`FirstPierceShift/Since`); consumed levels; both-sides mirror with shared loop.
- Limit entry path (v1.21): zone must be unmitigated on closed H1 bars; entry snapped **into** the zone; stop beyond the far edge (never tightened); min/max stop, freeze/stops level, already-passed and distance guards; expiry; cancel reasons with broker re-authorization (`VerifyAccountProtection` before delete); setup marked spent at FILL not placement; daily cap counts fills only.
- Sizing identity: risk % of equity → money → OrderCalcProfit against the broker spec; margin-shrink loop; tick-size snapping; hard caps `QATS_HARD_CAP_*`; **no martingale/grid/loss-chasing anywhere**.
- Account guard: bound login/server/mode; DEMO-first (`InpDemoOnly=true` default); REAL requires the explicit triple opt-in; `OnTick` management re-verifies; `OnInit` fails to `INIT_FAILED` without a valid symbol spec or XAUUSD signal-key init.
- Persisted breakers with self-repair (`UpdateCooldownState` resets/clamps invalid GVs); loss streak from deal history net of fees/commission/swap, ownership from the ENTRY deal's magic; watermark prevents recounting ancient deals.
- One-reservation-per-setup (XAUUSD): `GlobalVariableSetOnCondition` mutex; `SetupAlreadyTraded` blocks re-trading; duplicate-bar guard; `ProcessPendingRetry` clears the pending flag BEFORE re-attempting so a retry can never deadlock entries.
- Every order sends SL; positions losing their SL get one rebuilt from ATR; break-even never widens; partial bank once per position (persisted `pc_<ticket>`).
- `OnTradeTransaction` dedups repeated delivery, logs deals, updates streak/cooldown immediately on closing deals.
- `InpDisplaceM15=false` remains the rollback freeze for v1.23 behavior.

## 4. Critical findings (CR) — Phase 2/3 scope

**CR-1 — Premium/Discount is single-range, duplicated, unlogged.** `DealingRangePosition` (L836) and `LimitPriceInPD` (L2738) each compute one range (`InpSwingLookback`=120 closed H1 bars, highest-high/lowest-low, midpoint equilibrium) and duplicate the math. There is no long-term (A) / short-term (B) / confirmed-swing (C) range, no swing-freshness/age validation, no detection of stale extremes dominating the range, no hysteresis or predictable selection, no logging of the three equilibriums and the selected range. `DealingRangePosition` also silently returns 0.5 on any data failure — the journal then shows a plausible-looking `P/D=0.50` that means "no data", which is exactly the kind of silent bypass the PD mandate forbids. → Phase 3 (`QATS_PD_ADAPTIVE`).

**CR-2 — Market entries have no PD protection; PD only as a 10-point score on the market path.** `InpLimitNeedPD` is consulted only in `BuildLimitPlan`. A score-55 BUY in premium is sent by `ExecuteSignal` with no premium/discount check. The mission mandates PD protection as a risk boundary (SELL premium / BUY discount) and forbids relaxing it to raise frequency. Options are set out in the plan (§8, Phase 3); nothing will be relaxed. → Phase 3.

**CR-3 — Duplicate-order reservation exists only for XAUUSD.** `ReserveSignal` is called under `IsXAUUSD()` in both `ExecuteSignal` and `PlaceLimitOrder`; on any other symbol there is no atomic signal reservation — only `SetupAlreadyTraded` (non-atomic across instances) and the daily caps. For a production-grade generic EA this is an execution-integrity gap. → Phase 8.

**CR-4 — One refused modification disarms break-even for ALL positions.** `ManagePositions` uses one global `g_lastManageFail`; a single refused BE modify suppresses BE moves for every position for 10 s. → Phase 8 (per-ticket throttle).

**CR-5 — `ProcessClosedDeals` rescans 30 days of history every M5 bar** (and on every closing deal). On a busy account this is an avoidable O(history) cost inside the management path; the watermark already exists and should bound the scan. → Phase 8/15.

**CR-6 — News/event risk filter ABSENT.** The EA has no economic-calendar integration of any kind. The mandate allows two honest outcomes only: (a) a configurable calendar-based filter whose failure mode is explicit (calendar empty/unavailable → log once, never invent events), or (b) an explicit, documented limitation. MQL5 does expose `CalendarValueHistory`, but it is populated by MetaQuotes and is empty on many terminals; it must be treated as best-effort and verified on THIS terminal before any claim. → Phase 7 (implementation + explicit verification note, or a documented limitation — never fabricated events).

**CR-7 — `ZoneStillValid` fails open on missing bars.** `for(t=fromShift; t>=1; t--)` with unvalidated `fromShift`; `iClose` beyond available history returns 0.0, which never satisfies `c < bottom`/`c > top`, so an out-of-history zone is reported "valid". Same class of bug: any shift derived from data that is not yet downloaded (cold start on M15 fallback path) is trusted. → Phase 2/5 (clamp to `iBars`, fail closed, journal once).

**CR-8 — Score/PD duplication drift risk:** `dealPos` feeds scoring; `LimitPriceInPD` re-derives the range independently with different data (highest-high over 120 bars). Two implementations of the same protection will drift. → Phase 3 (single adaptive engine feeds both score and gate).

## 5. Non-critical findings (NC)

- **NC-1** `DealingRangePosition` 0.5-on-failure silent fallback (see CR-1) — emit explicit `PD_STATUS=NO_DATA`.
- **NC-2** `BuildTradePlan` (L1807) and `BuildLimitPlan` (L2767) each **recompute** `FindSwings` + `BuildLiquidityMap` after `AnalyzeMarket` already built them — 2–3× uncached series work per new M5 bar. → Phase 8/15 (per-bar memoized context).
- **NC-3** `ZoneUnmitigated` loops closed H1 bars with `iHigh/iLow` per call; fine correctness-wise, worth folding into the same cache.
- **NC-4** Scoring weights give correlated evidence independent points (sweep 15 + displacement 20 both derive from the same post-sweep impulse; structure 20 + trend bias D1/H4 15 both read the same EMA chain). No double-count guard exists. The core gate is the compensating control — keep it. A "structural vs indicator evidence" separation and per-point explanations are mandated. → Phase 9/12 (diagnostics); any weight retune only after out-of-sample evidence.  [Addendum: per-point explanations are live in the `[QATS][SIGNAL][SCORED]` record (`BUY core=.. [D1:.. H4:.. STRUCT:.. SWEEP:.. DISP:.. ZONE:.. PD:.. VWAP:.. VOL:.. M15:.. M5:..]`, mirrored for SELL); no weight retune performed — that requires out-of-sample evidence (Phase 10+).]
- **NC-5** `LimitMoneyPerPriceUnit()` is dead code (defined L2623, never called) — sizing correctly uses `OrderCalcProfit`. → Phase 2 removal or journal-only use.
- **NC-6** `DrawPanel` renders via `Comment()` only — cleared by any chart change; no fallback. Cosmetic. → Phase 9.
- **NC-7** Structure same-bar double-break sets `breakBar=-1` (documented conservative neutralisation) — not journalled when it happens; invisible to the operator. → Phase 9 log-once.
- **NC-8** Daily guards and sessions are **broker-server-time based** (`TimeTradeServer`), and `TodayKey()` rolls the daily baseline at broker midnight — not UTC. That is correct for broker-time sessions but must be documented as such (DST shifts the NY/London windows in server time). → Phase 7 (configurable windows + DST note), docs.
- **NC-9** `IsXAUUSD()` gates the XAUUSD-only veto/diagnostic policy and the reservation; on other symbols `QATS_DirectionVeto` still applies EMA-veto/counter-bias logic from inputs — acceptable but inconsistent documentation. → Phase 8/docs.
- **NC-10** `g_statBlockedBars/Rejected/...` counters are per-session only; nothing aggregates across restarts. Fine.
- **NC-11** No trailing stop (BE + partial bank only) — intentional; document as known limitation.
- **NC-12** `Heartbeat` fires on ticks only; an illiquid symbol with no ticks reports nothing (no `OnTimer`). → Phase 15 note; low priority for XAUUSD.
- **NC-13** `SessionVWAP` includes only bars since server midnight and falls back to `iClose(...,1)` when volume is 0 — correct but undocumented in one place; minor.
- **NC-14** Reserved GV namespace `sig_buy/sig_sell` uses M5 `signalBar` as identity; combined with `SetupAlreadyTraded`, semantics are right, but the two keys are not documented in one place. → docs.
- **NC-15** `EvaluatePool` marks a failed rejection as SPENT even if price later reverses — acceptable definition (state is per-window), documented in code; keep, but journal pool transitions in Phase 4/9.
- **NC-16** `OnDeinit` does not reset `Comment("")` on all paths? It does (`Comment("")`), plus chart has no persistent objects. OK — nothing to do.

## 6. Repaint / look-ahead verdict

**No look-ahead or repainting detected in the decision path.** Verified point by point: all structure/sweep/displacement/zone reads use shift ≥ 1; `IsFractal` requires both wings closed; `BuildStructure` is causal (oldest→newest), levels consumed by the crossing break, same-bar both-branch break credits neither; `PDH/PDL/PWH/PWL` read shift 1 of D1/W1 (closed); `SessionVWAP` walks newest closed M5 bar backward and stops at the day boundary; `FindSwings`/`BuildStructure` consume bars only after their right wing closes; OB/FVG require a qualifying closed impulse; displacement scans closed bars only. `a.signalBar = iTime(PERIOD_M5, 0)` labels the *decision bar* (forming bar) but never feeds a price decision — the identity reservation keys off it, which is safe.
One memory-type note: `BuildStructure` is O(lookback·k) and runs twice per M5 bar (via `AnalyzeMarket`) — see NC-2.

## 7. Timeframe integrity

H1 is the decision clock; M15 confirms; M5 triggers; D1/H4 contextual. `ShiftOfTime` converts an M15 event bar back to the containing closed H1 bar (never index-reuse). `e.dispTF` carries the confirming TF and is logged. `ZoneStillValid` iterates the zone's own TF. No M15 index is passed to H1 functions. The one TF-mixing pattern left is **performance-driven recompute of H1 maths from M5 ticks** (NC-2), not a correctness bug.

## 8. Proposed phased implementation plan (no code until this is approved)

Rollback copy of the EA is taken before every phase: `MQL5/Experts/rollback/QuantumAutonomousTradingSystem_pre_phase<N>.mq5`. After each phase: modified-function list, side effects, unresolved issues, and a report — presented, then closed only when you accept it.

**Phase 2 — Critical bug fixes (small, surgical).** CR-7 (`ZoneStillValid` clamp/fail-closed), CR-4 (per-ticket BE throttle), NC-5 (dead code), NC-7 (log structure double-break once), NC-1 journaling hook for PD-no-data. No behavior relaxation; suite re-run.
**Phase 3 — Adaptive Premium/Discount (`QATS_PD_ADAPTIVE`, CR-1/CR-2/CR-8).** New engine: three H1 dealing ranges — A long-term (120 closed H1 bars), B short-term (48 closed H1 bars), C confirmed swing range (most recent confirmed swing high/low, with age/relevance validation: max age in H1 bars, range vs ATR sanity, equal-extreme rejection). Validate completeness (enough bars), reject stale extremes dominating (range A extremity older than N bars while price sits outside it), and select deterministically (e.g., swing range when fresh+valid, else the tighter of A/B by ATR-normalised width, with hysteresis: no switching while the previously selected EQ is within ε). SELL→premium, BUY→discount on **both** paths; market path gains the same hard PD gate behind a new input `InpPDEnforceMarket` (default **true** — protection is added, never removed; setting it false is an explicit operator decision, journalled). Journal required line: `[QATS][PD] LONG_EQ=.. SHORT_EQ=.. SWING_EQ=.. SELECTED=A|B|C STATUS=OK|REJECTED reason=..`; `PD_STATUS` exposed for Phase 9. `InpLimitNeedPD` unchanged in default. EQ of each range exposed for scoring; `DealingRangePosition` re-implemented on top of the adaptive engine (score uses SELECTED EQ — no second implementation).
**Phase 4 — Liquidity engine.** Pool-state transition journal (INTACT→SWEPT→ACCEPTED/SPENT with bar+level), no double counting (assert one terminal state per pool per window), sweep-vs-breakout acceptance rules kept (2 closes beyond), consume-on-target verification in limit TP path, PDH/PDL/PWH/PWL retained, equal highs/lows tolerance from ATR kept. Structural tests extended.
**Phase 5 — Displacement / OB / FVG.** Body vs ATR, body/range, direction consistency kept; per-event TF+shift stored (extend `e.dispTF/dispBar` to liquidity sweep events so the journal can say "sweep at H1 bar N rejected at shift M"). FVG must be displacement-validated (it already is via anchor impulse) and mitigated-zone reuse rejected (unchanged); `ZoneStillValid` gets the CR-7 fix scoped here if not done in Phase 2.
**Phase 6 — M5/M1 scalping research (READINESS, not authority).** M1 trigger module stays OPT-IN, never overrides HTF protection, evaluated only behind `InpUseM1Trigger=false` default. Compare M1 vs M5 triggers historically (walk-forward); accept M1 only if out-of-sample evidence shows an edge — otherwise document "no edge, disabled". Nothing about M1 changes entries by default.
**Phase 7 — Regime & session filters.** Market regime module (trending/ranging/high-vol/low-vol/unclear) from ATR percentile vs its own 100-bar median, EMA20/50/200 structure, range-expansion ratio; per-regime rules are REPORT-ONLY first (journal `REGIME=`), gating only if evidence justifies it — no excessive filtering. Sessions: keep server-time windows but add explicit broker→UTC offset input + DST handling note; windows remain configurable. News filter (CR-6): implement optional `CalendarValueHistory`-based guard (currencies=XAU/USD, importance=high, configurable minutes before/after); failure = log `[QATS][NEWS] CALENDAR_UNAVAILABLE — no events assumed, entries NOT blocked by unverifiable data` once per session, never fabricated. Explicit terminal verification required before any production claim.
**Phase 8 — Execution & risk.** CR-3 (extend atomic reservation to all symbols: `GVKey("sig_buy_<symbol>")`-style namespaced keys, XAUUSD keys keep legacy names for compatibility), CR-5 (bounded 30-day scan → watermark-bounded), NC-2 (per-bar memoization of swings/pool map shared by analysis, plan and limit-plan), partial-fill accounting (log `ResultVolume` vs requested; treat `DONE_PARTIAL` as filled-with-report), limit-order re-validation on the final send attempt, verify GV flush on reserve. Risk: no changes to caps; add `RISK_STATUS` exposure map (equity, day P/L, HWM/DD, streak, cap usage) for Phase 9 journaling.
**Phase 9 — Diagnostics & journal.** Required single-record format per evaluated setup:
`[QATS][ANALYSIS] bar=.. side=.. BUY_SCORE=.. SELL_SCORE=.. CORE_STATUS=.. STRUCTURE_STATUS=.. LIQUIDITY_STATUS=.. DISPLACEMENT_STATUS=TF=.. STATUS=.. PD_STATUS=.. EXECUTION_STATUS=.. FINAL_DECISION=.. REASON=..` plus `[QATS][FINAL] DECISION=.. REASON=..`. Dedup unchanged (once per setup per outcome). Every rejection explains itself, including "why a high-scoring setup was rejected" (`SCORE=78 REJECTED AT=RISK_GUARD REASON=DAILY_LOSS_LOCK`).
**Phase 10 — Compile & test.** Real MetaEditor/F7 compile IF available in this environment (otherwise stated plainly); offline `tools/` suites re-run (`verify_quantum_ea`, `test_qats_native_build`, `test_qats_dual_direction`, `test_qats_limit_entry`, `check_production_ready`); Strategy Tester configuration document (spread fixed=current, modeling=Every tick based on real ticks, date range ≥ 2 years incl. 2024 stress, deposit/leverage as broker, forward-test split); test report template; parameters sensitivity plan; explicit "NO profitability claim" statement.

**Deliverables mapping:** (1) this audit, (2) §4/§5 bug lists, (3) updated `.mq5` per phase, (4) changelog `docs/QATS_CHANGELOG.md`, (5) module notes in `docs/`, (6) real compile log if performed, (7) `docs/QATS_STRATEGY_TESTER_CONFIG.md`, (8) test report, (9) known limitations (§10 below), (10) readiness classification — this document lifts the EA from NOT AUDITED to **AUDITED** only.

## 9. Strategy Tester configuration (draft — finalised in Phase 10)

- Terminal: MetaTrader 5, symbol `XAUUSDm`/`XAUUSD` as on the trading server; Period M5; **Modeling: Every tick based on real ticks**; Spread: **current** (never lower); Deposit 10,000; Leverage as broker; Optimization off for first pass.
- Inputs: production preset `presets/Quantum_XAUUSD_PRODUCTION.set` (DEMO), `InpDisplaceM15=true`, `InpUseLimitEntry=true` (test both), `InpDryRun=false`, `InpEnableTrading=true`, `InpDemoOnly=true`.
- Windows: ≥ 24 months including 2024 volatility; forward-test split last 20–25%; walk-forward by quarter; sensitivity on `InpMinScore ∈ {55,60,65}`, `InpDisplaceATR ∈ {1.2,1.5,2.0}`, `InpSetupWindowBars ∈ {12,24,48}`.
- Metrics: trades, win rate, profit factor, EV/trade, max DD %, recovery factor, avg RR, spread/slippage sensitivity, expectancy by session/regime/side/TF; reject overlays after the fact; no cherry-picked windows.
- Demo forward test ≥ 4 weeks before any REAL discussion; REAL stays `InpDemoOnly=true` until you explicitly authorize otherwise.

## 10. Known limitations (honest, standing)

- Offline shim suites ≠ MetaEditor F7; nothing here is compile-verified yet.
- Calendar reliability on this terminal is unverified (CR-6).
- Broker-midnight daily reset & server-time sessions (DST shifts windows) — documented behavior, not UTC.
- Day baseline starts at first sight of the day: attaching mid-day after losses understates earlier damage.
- Loss streak is per symbol+magic; other strategies on the account are not counted.
- No trailing stop; BE + partial bank only.
- PD engine pre-Phase-3 is single-range (CR-1) — do not rely on it yet.
- XAUUSD-only duplicate reservation (CR-3).
- Performance: unmemoized series reads (NC-2).
- No news filter (CR-6) — considered HIGH priority, not done yet.
- `InpEnableTrading=true` + `InpDryRun=false` is the LIVE configuration; on DEMO this is fine; REAL requires the explicit triple opt-in and stays off by default.

## 11. Readiness classification

**v1.23 (current tree): AUDITED — NOT MODIFIED, NOT COMPILE-VERIFIED, NOT BACKTESTED, NOT PRODUCTION-READY.**
Path to PRODUCTION CANDIDATE: Phase 2 → 3 → … → 10, each closed with a report, ending in real compile + Strategy Tester evidence + demo forward test.

---

## Addendum — implementation phases 2..10 (2026-11-14, appended after the audit)

This audit froze the pre-implementation state. Phases 2–10 have since landed on
`arena/8397a41f-terad`; the authoritative per-phase records are
`QATS_CHANGELOG.md` and the module notes (`QATS_ADAPTIVE_PD_V124.md`,
`QATS_LIQUIDITY_V124.md`, `QATS_DISPLACEMENT_FVG_V124.md`,
`QATS_M5_M1_SCALPING_V124.md`, `QATS_REGIME_SESSION_NEWS_V124.md`,
`QATS_EXECUTION_RISK_V124.md`, `QATS_DIAGNOSTICS_JOURNAL_V124.md`,
`QATS_COMPILE_TEST_V124.md`, with the deliverables
`QATS_STRATEGY_TESTER_CONFIG.md` and `QATS_TEST_REPORT_TEMPLATE.md`). Status
summary against this document's findings:

- CR-1 / CR-2 / CR-8 (adaptive PD) — implemented; market path PD gate ships in
  the production preset, offline-gated, fail-closed.
- CR-4, CR-7, NC-5, NC-7, NC-1 — fixed (Phase 2).
- CR-6 (news) — **implemented, OPT-IN default off, fail-open for trading**
  (`NEWS_BLACKOUT`, `CALENDAR_UNAVAILABLE` once per attach, never fabricated).
  Terminal calendar liveness remains unverified until Phase 10.
- NC-8 (server-time sessions / broker midnight / DST) — partially addressed:
  windows unchanged (correct broker-time behavior); advisory
  `InpBrokerUtcOffsetMinutes` input + DST caveat at attach. A future phase may
  enforce UTC windows only with verified broker DST evidence.
- Regime module (§8 Phase 7) — implemented REPORT-ONLY; never a veto.
- CR-3, CR-5, NC-2 (reservation/scan/memoization) — Phase 8 landed: reservation
  on every symbol with GV-flush verification (fail closed), watermark-bounded
  deal scan, per-bar memoized liquidity context; partial-fill accounting and
  the RISK_STATUS exposure map added. Offline gate 57/57.
- Operator F7 attempt #1 (2026-11-14, on `d3df3f6`, the PR-#68 merge):
  **1 error — `undeclared identifier 'importance'`** (the EA read importance
  off `MqlCalendarValue`; that struct carries only time + event_id). Fixed to
  the event-join pattern proven by nadir2 (History NULL/NULL → CalendarEventById
  → ev.importance) plus `CalendarEventByCurrency` for the watched-currency
  filter (name flagged as unverifiable offline; documented fallback = block on
  any high-importance event + explicit journal). F7 attempt #2 pending.
  Offline: build clean, unit 558/558, news scenarios 12/12, news_blackout
  pair green.
- Phase 10 — Compile & test — documentation scope closed offline, honestly:
  F7 compile NOT available on this environment (probe 2026-11-14: no
  MetaEditor/terminal/Wine; offline suites ≠ compile); offline battery re-run
  green (57/57 OFFLINE GO); Strategy Tester configuration (`docs/QATS_STRATEGY_TESTER_CONFIG.md`)
  and test report template (`docs/QATS_TEST_REPORT_TEMPLATE.md`) delivered;
  sensitivity plan + pre-declared decision rule + kill criteria included;
  explicit NO profitability claim. Readiness unchanged (MODIFIED).
- Diagnostics contract — Phase 9 landed: `[QATS][ANALYSIS]` single record per
  evaluated setup (mandated field order), `[QATS][FINAL]` decision record,
  high-score rejection explanation (`SCORE=.. REJECTED AT=RISK_GUARD
  REASON=..`), RISK_STATUS folded into the record. NC-6 resolved as a
  documented cosmetic limitation; NC-7 implemented as log-once since the
  structure work (`g_loggedDoubleBreak`, `[QATS][STRUCTURE] same closed bar …
  contradictory data`) — audit box ticked; NC-11 remains intentional.
  Offline gate 57/57.
- Known limitations standing today (add to §10, do not delete the originals):
  no trailing stop; unverified terminal calendar; broker-midnight baseline;
  per-session counters; pre-Phase-3 text in this file describes the old single
  range and is superseded by the adaptive engine; the heartbeat now also
  carries `[QATS][RISK]` (Phase 8); per-setup records carry RISK and the
  full decision contract (Phase 9); DrawPanel remains Comment()-only by
  documented, intentional cosmetic limitation (re-draws every tick).
- Readiness classification is unchanged: **NOT COMPILE-VERIFIED, NOT
  BACKTESTED, NOT PRODUCTION-READY**. Phase order to PRODUCTION CANDIDATE
  stands — and it CANNOT close in this environment: it requires a human F7,
the Strategy Tester matrix (config doc), and a ≥ 4-week DEMO forward test. QATS_VERSION remains 1.23.
