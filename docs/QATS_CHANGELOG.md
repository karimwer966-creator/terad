# QATS — Engineering Changelog

All changes are made on top of v1.23 (merged to `main` in `db025e9`, 2026-11-13).
Rollback copies live in `MQL5/Experts/rollback/` (gitignored, untracked).
No MetaEditor/F7 compile has been run at any point; "offline" = host C++ transpile
+ g++ shim simulation (`tools/qats_native.py`), which is NOT a MetaEditor compile.
Offline gate: `python3 tools/check_production_ready.py` → 57/57 OFFLINE GO throughout (61/61 since the 2026-11-14 PR-68 close-out, which added the four suites the CI structural job runs but the gate did not).

## 2026-11-13 — Phase 2: critical bug fixes (branch arena/8397a41f-terad)

- **CR-7** `ZoneStillValid()` fails closed: degenerate zone numbers, insufficient
  closed-bar history, or unreadable bars now reject the zone (journalled once);
  previously missing history read as close=0.0 and silently passed.
- **CR-4** per-ticket break-even throttle (`ManageFailRecent/ManageFailRecord`,
  32 slots, oldest evicted) replaces the single global `g_lastManageFail`.
- **NC-5** dead `LimitMoneyPerPriceUnit()` removed (sizing uses `OrderCalcProfit`).
- **NC-7** structure same-bar double-break journalled once per attach.
- **NC-1** PD no-data situations journalled once per attach (no more silent 0.50).
- Offline: dual-direction 85/85 → 87/87 (Phase 3), limit-entry 98/98, gate 57/57.

## 2026-11-13 — Phase 3: adaptive premium / discount `QATS_PD_ADAPTIVE`

- **CR-1/CR-8** `DealingRangePosition()` deleted; ONE engine (`ComputePdAdaptive`)
  builds three H1 ranges and feeds both the score (`location`) and both gates.
- Three ranges: A 120 / B 48 closed H1 bars; C confirmed swing range with age
  (`InpPdSwingMaxAge`) and relevance (`InpPdSwingMinATR`) validation.
- Validity rejects: incomplete history, flat ranges (0.25 x ATR), stale dominating
  extremes (`InpPdStaleBufferATR`), stale swing pairs (C freshness).
- Deterministic selection (C > B > A) + hysteresis (`InpPdHysteresisATR`) keeping
  the previous selection while EQs stay within band; switching journalled.
- **CR-2** NEW hard gate on MARKET entries: `InpPDEnforceMarket=true` (default);
  SELL only in premium / BUY only in discount on the live quote; blocked setups
  are journalled (`[QATS][PD] MARKET_BLOCKED ...`, `outcome=BLOCKED
  reason=PD_MARKET`). The limit path keeps `InpLimitNeedPD` (true).
- **Fail closed** when no range is valid (`QATS_PD_NONE`): both paths refuse,
  `[QATS][PD] ... SELECTED=NONE ... STATUS=REJECTED...` — never a silent bypass.
- Journal: `[QATS][PD] LONG_EQ=.. SHORT_EQ=.. SWING_EQ=.. SELECTED=.. POS=.. STATUS=..`
  printed on every evaluation; reason string now carries the selected letter
  (e.g. `P/D=0.62(C)`).
- `SAnalysis` gains `pdEq/pdLongEq/pdShortEq/pdSwingEq` (0 = invalid),
  `pdLongValid/pdShortValid/pdSwingValid`, `pdSelected`, `pdStatus`.
- Offline fixtures freeze the gate like `InpDisplaceM15=false`
  (`tools/qats_sim/qats_market.inc::setInputs`, `tools/qats_backtest.py::SIGNAL_STUDY`);
  production preset ships it `true`.
- New unit suite `unitAdaptivePD` (22 checks) + new scenarios `pd_gate_buy/sell`
  (mirror pair, blocked=50/50 on the synthetic chain). Unit: 348 checks green.
- NOT compile-verified, NOT backtested, NOT demo-forward-tested. Readiness: MODIFIED.

### Unresolved / deferred
- v1.23 expects zero market PD gate; the market path under enforcement is materially
  more selective in trends (by design). Final default choice rides with the user
  decision recorded in the session (Phase 3 was executed with the recommended
  enforce-by-default).
- MetaEditor F7, Strategy Tester, demo forward test — Phase 10.

## 2026-11-13 — Phase 4: liquidity engine hardening `QATS_LIQUIDITY_ENGINE`

Mandate §4. The liquidity map (build / sweep-vs-acceptance-vs-spent semantics /
pool ranking / nearest-intact TP targeting) was already sound and is preserved
where unchanged. This phase closes its three real gaps:

- **Pool de-duplication** (`BuildLiquidityMap` + `MergeSideDuplicates` +
  `PoolBetter`): same side within tolerance now merges to ONE identity. Winner =
  stronger kind (week > day > equal > swing), tie-break newer formation
  (`shift == 0` = the day/week boundary is newest). Side-local merge (the two
  side blocks are merged independently and recombined — merging in-place on the
  combined array broke mirror replay symmetry; caught by the symmetry replay,
  fixed before delivery). `[QATS][LIQUIDITY] merged N duplicate level(s)` when it
  fires.
- **Consumed levels can never read INTACT** (`PoolStateDecision` +
  `PoolFoldState`): the survivor carries the most decided state of the group
  (ACCEPTED > SWEPT > SPENT > INTACT) with that member's decisive bar, and the
  further reach (higher BSL / lower SSL). A consumed level stays consumed even
  when the runner had the weaker kind.
- **Transition journal** (`JournalLiquidityTransitions`): one line per pool per
  state change, `[QATS][LIQUIDITY] TRANSITION side=.. kind=.. level=..
  state=OLD->NEW bar=<server time> extreme=..`; silent baseline on attach; new
  pool appearances are not transitions.
- **TP provenance**: `tpSource` is now `"LIQUIDITY:<KIND>@<level>"` (e.g.
  `LIQUIDITY:EQH@212164.00`) instead of `"LIQUIDITY:EQH"`; `SAnalysis.tpLevel`
  carries the pool's own level (0 = RR fallback). No selection rule changed
  (nearest INTACT opposing pool paying >= InpMinRR / InpLimitMinRR; SELL anchored
  to level + spread; TP snapped toward the entry).
- Unit coverage: `unitLiquidityDedup`, `unitLiquidityJournal`,
  `unitLiquidityFold` (+3 `poolLevel` provenance checks inside `unitLiquidity`;
  unit suite 348 -> 410).
- **Bug found & fixed inside this phase:** the first in-place merge reordered
  the SSL block via cross-side swap-with-last; the mirror replay exposed it
  (60 -> 12 mismatching bars); the split-by-side merge restored exact mirror
  symmetry (0 mismatches, 14040 bars, trades/P&L identical). Broken intermediate
  never claimed green.
- Verifier extended to recognize `SLiquidityPool` globals (additive, same
  treatment as `SAnalysis`/`SSymbolSpec`).
- NOT compile-verified in MetaEditor, NOT backtested, NOT demo-forward tested.
  Offline: verifier clean; dual-direction 87/87; limit-entry 98/98;
  journal-report 33/33; native-build 62/62; production gate 57/57. Readiness:
  MODIFIED. QATS_VERSION remains 1.23.

### Unresolved / deferred
- Merge tolerance is ATR-derived (`InpLiquidityToleranceATR`); levels further
  apart than that remain separate identities by design.
- Transition journal does not survive an EA restart (silent baseline is
  re-established; the first change after a restart is not journalled).
- MetaEditor F7, Strategy Tester, demo forward test — Phase 10.

## 2026-11-13 — Phase 5: displacement / OB / FVG `QATS_DISPLACEMENT_FVG`

Mandate §5. The displacement engine (body vs ATR `InpDisplaceATR`, body/range vs
`InpDisplaceBodyRatio` with `1.3 x ATR` range floor, directional-candle check,
H1-first with the v1.23 M15 fallback on M15 ATR, rejection-bar anchor, closed
bars only) is PRESERVED unchanged. What this phase closes is the event storage,
the journal that reads it, and the zone-validation semantics:

- **Per-event TF+shift for liquidity sweep events** (`SSweep` gains `tf`,
  `poolShift`, `eventTime`): the sweep rejection event is now stored like
  `e.dispTF/e.dispBar` — the detection timeframe is stored explicitly (never
  re-derived), the pool's formation bar shift is stored (SWING/EQ*: H1 shift of
  the formation bar; PDH/PDL/PWH/PWL: 0 = the day/week boundary), and the
  rejection bar's server time is frozen at detection (never re-read). The chain
  journal now names the event, e.g.
  `sweep=SSL:EQH@1996.00(detected H1 shift 3 @ 2026.11.13 09:00; level formed shift 14; extreme 1992.50)`
- **FVG/OB must be displacement-validated — made literal.** Zones were
  previously searched around a displacement impulse OR, for a sweep with no
  displacement, around the sweep bar (a gap formed before/without any impulse
  was scored as confluence). The sweep-anchor fallback is REMOVED: zones are
  searched only around a real impulse anchor (H1 displacement bar, or the H1
  bar containing the M15 displacement; without the containing bar there is no
  anchor and no zone). A sweep-only or structure-only setup scores `ZONE:0`
  (scenario `sweep_only/*` asserts it on the swept side; the other side of the
  synthetic tape is unconstrained). Zone points were optional confluence only,
  never part of the core gate, so no entry decision changes except the removal
  of unvalidated zone points.
- Mitigated-zone reuse rejection unchanged (`ZoneStillValid` keeps the Phase 2
  CR-7 fail-closed semantics); FVG stays anchored to the impulse triple.
- `TFName()` added (the offline shim has no `TimeframeToString`).
- Unit coverage: `unitSweepEvent` (event TF/shift/time storage, reset contract,
  chain text, TFName) + scenario assertion; unit suite 410 -> 430.
- Bug inside the phase (first cut): the sweep-only assertion was written
  side-blind and failed on the mirror because the OPPOSITE side of the
  synthetic tape has its own impulse and legitimately scores ZONE:9; the check
  was corrected to the swept side. Broken intermediate never claimed green.
- NOT compile-verified in MetaEditor, NOT backtested, NOT demo-forward tested.
  Offline: verifier clean; dual-direction 87/87 (sanitizer clean, 430 unit
  checks); limit-entry 98/98; journal-report 33/33; native-build 62/62;
  symmetry replay 0/14040 bars, 10/10 trades; production gate 57/57.
  Readiness: MODIFIED. QATS_VERSION remains 1.23.

### Unresolved / deferred
- Sweep detection is H1-only by construction; `SSweep.tf` stores PERIOD_H1 and
  is there so the TAPE is auditable per event and a future M15 sweep pass does
  not lie about its timeframe.
- MetaEditor F7, Strategy Tester, demo forward test — Phase 10.

## 2026-11-13 — Phase 6: M5/M1 scalping research `QATS_SCALPING_RESEARCH`

Mandate §6 (READINESS, not authority). Research phase: no EA behaviour change,
no M1 module exists or was added.

- **M1 verdict — no edge, not implemented, not enabled.** No `InpUseM1Trigger`
  input is added (an input for a nonexistent module would be NC-5 class dead
  code). The mandated walk-forward M1-vs-M5 cannot be run here: the public
  dataset (`Dypoi/XAUUSD_Dataset`, ~470 MB M1 bid+ask, 2016..2026, SHA-256s in
  `tools/qats_backtest.py::DATASET`) is not committed and not fetchable in
  this environment; synthetic bars cannot evidence a real-market edge (none
  was fabricated). The 2026-11-11 real-data study already records "no
  demonstrated edge". M1 stays DISABLED; nothing about M1 changes entries.
- **M5 trigger role is now pinned by tests** (`unit.m5_trigger_authority`, 20
  checks): geometry on the sim tape (engulfing/pin/marubozu, bullish and
  mirrored bearish), core-gate authority per profile — CONSERVATIVE requires
  M15 OR M5 (never a sole gate), BALANCED and ACTIVE ignore them for core,
  a lone sweep stays refused even with confirmations present, and
  `QATS_W_M5 == QATS_W_M15 == 5`. M5 remains optional confluence only.
- **Readiness gate for a future M1 module** documented in
  `docs/QATS_M5_M1_SCALPING_V124.md` (opt-in default-false, additive-only,
  real-data IS/OOS walk-forward vs the matched M5 baseline, pre-registered
  acceptance, mirror-feed symmetry, F7 + forward test before any claim).
- Unit suite 430 -> 450 checks.
- NOT compile-verified in MetaEditor, NOT backtested, NOT demo-forward tested.
  Offline: verifier clean; dual-direction 87/87 (sanitizer clean, 450 unit
  checks); limit-entry 98/98; journal-report 33/33; native-build 62/62;
  production gate 57/57. Readiness: MODIFIED. QATS_VERSION remains 1.23.

### Unresolved / deferred
- The M1-vs-M5 walk-forward comparison itself — blocked on the dataset; runs
  only with the data present (see the readiness gate). MetaEditor F7, Strategy
  Tester, demo forward test — Phase 10.

## 2026-11-13 — Phase 7: regime / session / news `QATS_REGIME_SESSION_NEWS`

Mandate §7 (master audit). Behavior with defaults is IDENTICAL to the Phase 6
tree except for one extra journal field; REAL stays disarmed.

- **Regime — REPORT-ONLY** (`ClassifyRegime`/`ComputeRegime`/`RangeRatio`,
  `SRegime`, `SAnalysis.regime*`, new H1 EMA-200 handle
  `g_hH1Slow200`): `volRatio = ATR(H1,shift 1) / median over
  InpRegimeAtrWindow (100)` closed H1 bars; HIGH_VOL >= 1.5x (inclusive),
  LOW_VOL <= 0.5x; else TREND_BULL/TREND_BEAR (close > EMA20 > EMA50 > EMA200
  chain); else RANGE (|EMA20-EMA50| <= 0.5 x ATR); else UNCLEAR. Fail closed
  to UNCLEAR on any unreadable input. `REGIME=<name> volRatio=<x>
  rangeRatio=<y>` is journalled on every `SCORED` line and is never a veto;
  `InpRegimeEnable=true` only turns the computation/journal off.
- **Sessions — UNCHANGED**: broker-server-time windows, `TimeTradeServer()`,
  overnight windows, all-day with 0/0. New advisory input
  `InpBrokerUtcOffsetMinutes=0` (printed at attach with the DST caveat; the
  broker's DST follows its server clock; never used for gating). NC-8 partial.
- **News guard (CR-6) — OPT-IN, default false**:
  `InpNewsFilterEnable`, `InpNewsBlockBefore/AfterMin=30`,
  `InpNewsCurrencies=USD,XAU`, `InpNewsMinImportance=3` (high).
  `CalendarValueHistory` per watched currency; an event >= threshold in
  [now - after, now + before] blocks entries with block code `NEWS_BLACKOUT`
  (journalled via `[QATS][BLOCK][REASON]`). **Fail-OPEN for trading**: if
  EVERY calendar call fails the calendar is unreachable — entries are allowed,
  `[QATS][NEWS] CALENDAR_UNAVAILABLE` is journalled ONCE per attach, no event
  is ever fabricated; partially reachable calendars still enforce their
  reachable currencies. An armed-once line confirms first reachability.
  Terminal calendar liveness is Phase-10-verifiable only; until then the
  filter ships default-off (honest outcome (b) documented in code +
  `docs/QATS_REGIME_SESSION_NEWS_V124.md`).
- Verifier allow-list gained `CalendarValueHistory` (additive). Unit suite
  450 -> 486 (`unit.regime`, `unit.news_filter`). New mirror-pair scenario
  `news_blackout_buy/sell` (12 checks each: armed blocks+names the reason,
  disarmed trades the same tape, unreachable trades the same tape with one
  CALENDAR_UNAVAILABLE line). Scenario geometry: unit 486/486,
  dual-direction 89/89 (mirror replay 0 bar mismatches), limit-entry 98/98
  (preset pins exactly the compiled inputs), journal-report 33/33,
  native-build 62/62, verifier clean, production gate 57/57 OFFLINE GO.
- In-phase bug (fixed before any green claim): the news guard first landed
  inside `GuardBlocks()` (function-definition inside a function body) —
  moved to file scope before SECTION 18.
- NOT compile-verified in MetaEditor, NOT backtested, NOT demo-forward tested.
  Readiness: MODIFIED. QATS_VERSION remains 1.23.

### Unresolved / deferred
- Terminal economic-calendar liveness on the operator's platform (Phase 10);
  regime thresholds are engineering defaults pending out-of-sample evidence;
  regime is never a gate. MetaEditor F7, Strategy Tester, demo forward test —
  Phase 10.

## 2026-11-13 — Phase 8: execution & risk `QATS_EXECUTION_RISK`

Mandate §8 (master audit). Protections added or exposed — never relaxed.
No risk cap, sizing, SL/TP, PD, session, regime or news behavior changed.

- **CR-3 atomic reservation on EVERY symbol** (was XAUUSD-only):
  unguarded `InitSignalKeys()` at attach (INIT_FAILED otherwise), unguarded
  `ReserveSignal()` in market and limit paths. Keys are account+magic+symbol
  namespaced; XAUUSD keys keep legacy names. `ProcessPendingRetry` carries the
  reservation (`ExecuteSignal(plan, reserved=true)`) so a retry is not bricked
  by its own first-attempt reservation. XAUUSD and REAL keep the
  no-automatic-retry policy (unchanged, pinned by the rejection scenario);
  DEMO non-XAUUSD keep their 3-retry budget, now functional.
- **GV flush verification on reserve**: after `GlobalVariablesFlush()` the key
  is re-read and the reservation FAILS CLOSED if the persisted value is below
  the reserved bar; same check added to `InitSignalKeys`. RAM-only reservations
  no longer authorize orders.
- **CR-5 watermark-bounded deal scan**: new persisted `last_deal_time` bounds
  `ProcessClosedDeals` to [lastDealTime-6h, now+1d] (never worse than the old
  fixed 30d); `InitDealWatermark` seeds both watermarks from a single 30d
  lookback once (upgrade-safe). Ticket filter still prevents double counting.
- **NC-2 per-bar memoization**: new `LiquidityContext()` builds swings +
  liquidity pools once per H1 bar (analysis, trade plan, limit plan share it);
  cache keyed on the closed-bar context (bar time, bar count, shift-1 H/L/C);
  outputs are element copies; the offline harness clears the cache on tape
  swaps. `JournalLiquidityTransitions` still runs once per evaluation.
- **Partial-fill accounting (market path)**: `QATS_FillShort(requested,
  filled)` (1e-8 epsilon, unit-pinned) drives a new
  `[QATS][EXECUTION][PARTIAL]` line (requested vs filled, shortfall, retcode);
  the fill is treated as filled-with-report as before (verified, counted,
  setup spent once); `[EXECUTION][FILLED]` now carries `requested=`.
- **RISK_STATUS exposure map** for Phase 9: `BuildRiskStatus` +
  `RiskStatusText` (equity, day P/L money/%, HWM, DD % with effective cap and
  %used, streak with cap, cap usage, day-loss % with cap, dayLocked, ddHalted,
  cooldown state/deadline, margin usage); heartbeat prints one `[QATS][RISK]`
  line. Read-only; the guard chain remains the only enforcer.
- Verifier recognizes `SSwing` globals (additive). Unit suite 486 -> 540
  (`unit.fill_short`, `unit.reservation`, `unit.risk_status`,
  `unit.liquidity_context`). Offline: verifier clean (159 user functions);
  unit 540/540; dual-direction 89/89 (mirror replay 0 bar mismatches with the
  memoized context); limit-entry 98/98; journal-report 33/33; native-build
  62/62; production gate 57/57 OFFLINE GO.
- In-phase bugs fixed before any green claim: struct house style for the
  transpiler's struct discovery; memoization cache key strengthened from bare
  H1 bar time (sim tape swaps reuse identical bar times — harness now clears
  the cache on swap); one unit fixture wrongly assumed g_dayBase == simulated
  equity.
- NOT compile-verified in MetaEditor, NOT backtested, NOT demo-forward tested.
  Readiness: MODIFIED. QATS_VERSION remains 1.23.

### Unresolved / deferred
- End-to-end partial-fill behavior needs a live/simulated terminal (Phase 10);
  limit-fill volume comparison deferred (shim has no order-history API; the
  DEAL line logs filled volume). RISK_STATUS enters the per-setup journal in
  Phase 9. MetaEditor F7, Strategy Tester, demo forward test — Phase 10.

## 2026-11-13 — Phase 9: diagnostics & journal `QATS_DIAGNOSTICS_JOURNAL`

Mandate §9 (master audit). Journal-record contract only; zero decision-path
changes, zero new inputs, preset unchanged, REAL disarmed.

- **[QATS][ANALYSIS] single record** per evaluated setup (a side whose core
  passed), printed once per setup per outcome:
  `bar=.. side=.. BUY_SCORE=.. SELL_SCORE=.. SCORE=.. CORE_STATUS=PASS/FAIL n/3
  STRUCTURE_STATUS=BOS@.. LIQUIDITY_STATUS=sweep=SSL:POOL@LEVEL(shift n)
  DISPLACEMENT_STATUS=TF=H1|M15 shift=n STATUS=OK PD_STATUS=..
  EXECUTION_STATUS=.. FINAL_DECISION=.. REASON=.. | RISK equity=.. dayPnL=..
  DD=.. streak=.. cap=.. dayLocked=.. ddHalted=.. cooldown=..`
  (mandated field order: bar side BUY_SCORE SELL_SCORE CORE_STATUS
  STRUCTURE_STATUS LIQUIDITY_STATUS DISPLACEMENT_STATUS=TF=.. STATUS=..
  PD_STATUS EXECUTION_STATUS FINAL_DECISION REASON).
- **[QATS][FINAL] DECISION=.. REASON=..** paired record (ENTER_MARKET /
  ENTER_LIMIT / NO_ORDER / otherwise the outcome verbatim).
- **Every rejection explains itself**, including high-scoring setups:
  `[QATS][GUARD] SCORE=<n> REJECTED AT=<layer> REASON=<code>` once per setup
  per outcome (AT ∈ RISK_GUARD/PD_GATE/SCORE_GATE/VETO/CONFLICT/DRY_RUN/
  LIMIT_GATE/execution stage; fires only for score >= InpMinScore, never for
  EXECUTED/LIMIT_PLACED).
- **RISK_STATUS folded in**: the Phase 8 exposure map is appended to every
  ANALYSIS record (`| RISK …`); heartbeat keeps its own `[QATS][RISK]` line.
- Dedup unchanged (own per-side `setup|outcome|reason` keys); records reuse the
  single outcome funnel (`LogSignal`) before the SCORED dedup; a bar with no
  core-passed side prints no setup record — journal growth stays bounded by
  setup count. `[QATS][SIGNAL][SCORED]` and the journal-report contract are
  untouched (additive only).
- NC-6 (DrawPanel reliance on Comment()) — RESOLVED as documented cosmetic
  limitation (re-drawn every tick; redundant with the journal; object-based
  panel rejected as unnecessary risk). NC-11 (no trailing stop) — remains a
  documented, intentional limitation.
- Unit suite 540 -> 558 (`unit.diagnostics_record`). New mirror-pair scenario
  `diagnostics_record_buy/sell` (20 checks each: DAILY_LOSS_LOCK named in
  ANALYSIS/FINAL/GUARD, once-per-setup dedup, ENTER_MARKET mapping,
  no-rejection-explanation-on-fill). Offline: verifier clean (166 user
  functions); unit 558/558; dual-direction 91/91 (mirror replay 0 bar
  mismatches); limit-entry 98/98; journal-report 33/33; native-build 62/62;
  verifier clean; production gate 57/57 OFFLINE GO.
- In-phase bugs fixed before any green claim: MQL5 reference-local rejected by
  the dialect lint (value copy instead); scenario daily-loss baseline was keyed
  against the pre-attach clock (moved after the tape clock reaches its day);
  phase-2 assertion narrowed from "zero GUARD lines" to "no rejection
  explanation for the EXECUTED outcome" (post-fill blocked evaluations while
  holding the position legitimately explain themselves).
- NOT compile-verified in MetaEditor, NOT backtested, NOT demo-forward tested.
  Readiness: MODIFIED. QATS_VERSION remains 1.23.

### Unresolved / deferred
- Demo journal consumption of the new records (Phase 10 forward test);
  automated reporting over ANALYSIS records (Phase 10/ops tooling).
  MetaEditor F7, Strategy Tester, demo forward test — Phase 10.

## 2026-11-14 — Phase 10: compile & test `QATS_COMPILE_TEST`

Mandate §10 (master audit). Documentation/test-deliverable phase: zero EA
change, zero new inputs, preset unchanged, REAL disarmed. QATS_VERSION 1.23.

- **MetaEditor F7 NOT performed in this environment** — environment probe on
  2026-11-14 found no MetaEditor/metatester/MT5/Wine binaries, no terminal
  install paths, and no importable client whose role is compilation; offline
  suites are not a compile. Stated plainly in `QATS_COMPILE_TEST_V124.md` §2.
- **`docs/QATS_STRATEGY_TESTER_CONFIG.md`** (deliverable #7): MT5 terminal
  settings (M5, every-tick-real-ticks, current spread, deposit 10,000,
  leverage as broker, optimization off), window 2024-01-01..2026-10-31 (≥ 2 y,
  includes the 2024 gold stress), forward split 20-25%, quarterly
  walk-forward, run matrix R1..R6 (limit-entry OFF, profiles 0/2, news ON,
  M15-displacement OFF), one-factor-at-a-time sensitivity grid
  (`InpMinScore` 55/60/65, `InpDisplaceATR` 1.2/1.5/2.0, `InpSetupWindowBars`
  12/24/48 — 9 cells) with a PRE-DECLARED decision rule (no silent preset
  adoption), mandatory metric decomposition by side/session/regime/P-D
  bucket/displacement TF, Phase-9 `[QATS][GUARD]` journal-diagnostics recipe,
  spread stress scenarios, kill criteria, tick-box checklist, NO
  profitability claim banner.
- **`docs/QATS_TEST_REPORT_TEMPLATE.md`** (deliverable #8): identity/hashes,
  F7 gate line, summary table, sensitivity grid, walk-forward, decomposition,
  Phase-9 GUARD histogram, spread scenarios, exactly-one verdict rubric
  (NO EDGE / INSUFFICIENT EVIDENCE / EDGE UNCONFIRMED / CONFIRMED ON DEMO).
- **Offline suites re-run (all green, same source as the 57/57 close):**
  verifier PASS (166 user functions); native-build 62/62; dual-direction
  91/91 (61 scenarios); limit-entry 98/98; journal-report 33/33;
  **check_production_ready 57/57 OFFLINE GO**.
- **Readiness classification UNCHANGED: MODIFIED.** Not compile-verified, not
  tester-run, not demo-forward-tested, not production-ready. The 2026-11-11
  simulation study remains the honest prior (no demonstrated edge).
- Phase-10 module note: `docs/QATS_COMPILE_TEST_V124.md`; audit addendum
  updated to phases 2..10; README status block extended.

### NO PROFITABILITY CLAIM
Nothing in Phase 10 (or any phase so far) claims the EA is profitable.
The tester run, when executed, may legitimately return NO EDGE; that result
must be reported, not rationalized away.

### Unresolved / deferred (require a human with a terminal)
F7 compile; Strategy Tester matrix; tester journal review; ≥ 4 weeks DEMO
forward test; explicit written REAL authorization. Until all above: MODIFIED,
DEMO-only, REAL disarmed.

## 2026-11-14 — PR #68 close-out: CI failure fixed; offline gate 57 → 61

CI job `verify QuantumAutonomousTradingSystem (offline, NOT a compile)` failed in
8s on PR #68 at step "XAUUSD execution and account authorization harnesses
(offline)". Reproduced locally and fixed at the assertion sites — never loosened:

- `tools/test_xau_execution_policy.py` — the native harness now extracts
  `QATS_FillShort` (added by the Phase 8 partial-fill accounting and already
  called inside `ExecuteSignal`); the XAUUSD-gated reservation expectation was
  pinned to pre-Phase-8 source text. CR-3 made the reservation symbol-agnostic
  deliberately, so the assertion now pins the opposite: the XAUUSD-only gate
  must NOT exist (`assertNotIn 'if(IsXAUUSD() && !ReserveSignal'`) and the
  reservation must be wired into exactly the two send paths (market + LIMIT,
  `count == 2`). The veto/score/stop/duplicate guard matrix in the same suite
  passes unchanged (26 guard/duplicate + 24 score/direction + 8 veto cases).
- Root cause of the CI/gate divergence: the curated gate never ran
  `test_quantum_compile_regressions.py`, `test_xau_execution_policy.py`,
  `test_quantum_account_policy.py` or `test_qats_limit_entry.py` — four suites
  the CI job runs. All four added to `tools/check_production_ready.py`;
  header counts in this changelog updated; dated historical entries unchanged.
- Post-fix: policy suite 2/2 OK; compile-regressions 4/4 OK; account-policy
  16/16 OK; **production gate re-run: 61/61 curated checks passed**.

No EA source touched. QATS_VERSION remains 1.23. Readiness unchanged (MODIFIED).
## 2026-11-14 — F7 attempt #1: one error, fixed (`d3df3f6`, branch arena/7c5c992a-terad)

The operator ran F7 in MetaEditor on the PR-#68 merge (`d3df3f6`). Result:
**1 error, 0 warnings** —
`undeclared identifier 'importance'` — QuantumAutonomousTradingSystem.mq5:2911
(the news guard read importance off `MqlCalendarValue`).

MQL5 ground truth (MqlCalendarValue carries only `time` + `event_id`;
importance lives on `MqlCalendarEvent`). The fix rewrites
`NewsHighImpactInWindow` to the event-join pattern already proven in this repo
(nadir2's `MTF_SniperIsNewsBlackout` compiled it): one unfiltered
`CalendarValueHistory` read, joined to the event library by `event_id`; each
watched currency is matched with `CalendarEventByCurrency` (flagged as the one
unverifiable-offline name; fallback if F7 rejects it = block on any
high-importance event in the window with an explicit `[QATS][NEWS] currency
filter UNVERIFIED …` journal line). Partial reachability semantics preserved:
a currency whose lookup fails is unverifiable for THAT currency only — entries
are never blocked by unverifiable data, never fabricated.

Two names could not be verified offline and are called out for the next F7:
`CalendarEventByCurrency` and `MqlCalendarEvent.id`. If F7 attempt #2 fails on
either, apply the documented fallback (History + CalendarEventById, block on
any high-importance event + explicit journal) — do NOT improvise.

Offline re-verified after the fix: host build clean (0 errors); unit 558/558;
`news_blackout_buy/sell` 12/12; `diagnostics_record_*` unaffected; regression
suite green. The simulator now models the real struct shapes (`MqlCalendarValue
{time, event_id}`, `MqlCalendarEvent {id, importance}`), so a repeat of this
divergence class is caught by the host build, not by the next F7.

Honest status: NOT compile-verified yet — F7 attempt #2 is pending. Readiness
unchanged (MODIFIED). QATS_VERSION remains 1.23. REAL remains disarmed.

