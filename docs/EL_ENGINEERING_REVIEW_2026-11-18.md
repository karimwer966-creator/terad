# Engineered Liquidity / QSMC — engineering audit

Date: 2026-11-18 UTC. Branch: `arena/868e405a-terad`. Base: `4e1ef71`.

## Executive finding and scope

**Release verdict: NOT READY.** Confirmed data-integrity and identity defects have small, tested corrections, but mandatory MTF/provenance requirements are not yet satisfied. This is not a profitability assessment or MT5 certification. The full acceptance criteria in the request are **not met**; in particular this report must not be read as a completed behavioral proof of every signal path.

The checked-out product calls itself QSMC, not EL. This audit maps the requested EL concepts onto that existing implementation; no new product or parallel signal engine was created. `QuantumAutonomousTradingSystem.mq5` (QATS) is a separate experimental product. It is inventoried and its existing curated checks were executed, but its trading strategy did not receive an exhaustive independent audit here.

Evidence levels used below:
- **Source-confirmed:** direct control flow/arithmetic in this tree.
- **Host-executed:** shipped function bodies compiled as C++ with explicitly simulated terminal APIs. Not a MetaEditor compile.
- **Unverified:** behavior needing MT5, broker history, deployment configuration, or a larger causal replay study.

## A. System architecture and inventory

[Complete file inventory, direct include dependency map, tool/configuration list and host function locator](EL_SOURCE_INVENTORY_2026-11-18.md).

There are **43 MQL source files**: **10 `.mq5` paths** (including the canonical/mirrored host pair) and **33 `.mqh` headers**. `nadir2.mq5` is canonical; `MQL5/Indicators/nadir2.mq5` must be byte-identical. This duplication is intentional packaging, not a second independent implementation. Neither copy should be edited independently.

### Program boundaries

| Program | Responsibility / consumers |
|---|---|
| `nadir2.mq5`, mirror | Main analysis, causal graph, candidate/lifecycle authority, journal, signal buffers, dashboard, drawings, alert dispatcher |
| `QSMC_AutoTrader.mq5` | `iCustom` consumer of CORE buffers 7–12 and execution metadata; independent account/risk/entry review before orders |
| `KLJ_DataFeeder.mq5` | External observational feed writer; not a signal confirmer |
| `QuantumAutonomousTradingSystem.mq5` | Separate QATS strategy and execution path; not the CORE companion |
| `QSMC_SmcVpEngine.mq5` | Separate modular SMC/volume-profile analytical host; not interchangeable with main CORE ABI |
| `QSMC_ScannerProbe.mq5` | Scanner/diagnostic host |
| `QSMC_ArbiterTest.mq5` | Terminal-side test script |
| `QSMC_BufferDump.mq5` | Buffer capture for terminal validation |
| `QSMC_ResetGuards.mq5` | Explicit operational guard reset; not a signal generator |

Paths in this table without directories are under their corresponding `MQL5/Experts`, `Indicators`, or `Scripts` directories (see inventory).

### Header ownership (all 33)

| Headers (prefix `QSMC_`, suffix `.mqh`) | Responsibility |
|---|---|
| Types, Preset, InputFingerprint, InstanceIdentity | Shared contracts, configuration, input identity and instance isolation |
| MarketData, Structure, EarlyBreakDetector | Chronological OHLC series, per-index ATR, causal closed-bar structure and early observations |
| Zones, ZoneScorer, Reaction, Bias | Zone registry, zone ranking, reactions, directional context |
| Gates, Arbiter, Root | Arbitration gates, candidate arbitration and subsystem ownership/orchestration |
| AlertManager, Renderer, ChartLayers | Arbitration delivery locks, rendering, visual-layer policy |
| SignalRegistry, UnifiedDecision | Signal families/episodes, optional unified CORE authority, merging and diagnostic deduplication |
| ExecutionRules | Pure companion execution arithmetic; no terminal API |
| IncidentSafety, LiquidityValue | Host-context safety/diagnostics and liquidity-value observations |
| CandlePatterns, Stats, Selftest | Candle taxonomy, observational/statistical reporting, deterministic checks |
| DataProvider, Scanners | File-backed observational datasets and time-budgeted scanning |
| SvpCore, SvpLiquidity, SvpZones, SvpVolumeProfile, SvpDecision, SvpChart | Separate modular SMC/VP contracts, liquidity, zones, volume profile, decisions and chart |

### Functional dependency map

```text
Terminal OHLC + ATR/ADX/RSI handles
  -> OnCalculate chronological g_buf_* and indicator arrays
  -> DetectLiquidity / DetectStructure / DetectOrderBlocks / DetectFVG
  -> BuildCausalEventGraph (pool -> sweep -> displacement -> structure -> zone)
  -> SelectBestStructureAnchor -> CalculateAITradeSetup
  -> fixed entry / structural stop / barrier-bound targets / scoring / quality gates
  -> ManageSetupLifecycle or non-retest confirmation path
  -> AppendConfirmedSignalJournal (immutable confirmation fact)
  -> SigLog_CollectCore -> CORE buffers 7..12 + metadata
  -> QSMC_AutoTrader::ProcessSignals -> HandleSignal -> entry/account/risk review

ZRE + RXN + CORE candidate submissions
  -> AlertDispatcherFinalize -> optional UnifiedDecision current-bar gate
  -> ranking + delivery/cooldown -> primary chart representation / alert
  -> SignalRegistry tracks visual episodes (not a trade authorization substitute)

CQuantumRoot -> MarketData + Structure + Zones + Reaction + Bias
  -> Gates -> Arbiter -> AlertManager + Renderer + Stats
  (host arbitration integration; advisory facts do not replace CORE confirmation)

QSMC_SmcVpEngine -> SvpCore/Liquidity/Zones/VolumeProfile/Decision -> SvpChart
KLJ_DataFeeder -> file -> DataProvider -> observational panels/scanners
```

The include checker verified a resolved acyclic graph and no orphan headers. Reachability is **not** proof that every method is used. No supposedly dead modules were deleted. Main-host structure, Root structure and Svp structure are genuinely different implementations with different semantics; consolidating them without a migration specification is unsafe. Visual primary, optional unified verdict, top-down chain and CORE execution are also different authority domains, not interchangeable signals.

Build/deploy: `tools/package_production.py`, preset generators/checkers, static/dialect/include/release gates, native harnesses and four GitHub workflow files are listed in the inventory. There is no demonstrated MetaEditor installation in this environment.

## B. Ranked findings

Line references below refer to the resulting tree and canonical host unless noted; the mirror has the same host lines. Function names are supplied because other edits can move coordinates.

### HIGH — fixed

**H1. Mandatory indicator copy exhaustion consumed an unready bar.**
- `nadir2.mq5:15911–15936`, `OnCalculate`.
- Root cause: after the retry counter exceeded its budget, execution continued, substituted zero for incomplete ATR/ADX/RSI slots and later committed `g_last_bar_time`. Retry exhaustion changed data validity.
- Impact: missing/altered evidence, missed bar retry, decisions reaching downstream modules with unavailable mandatory inputs.
- Correction: every incomplete copy returns `prev_calculated` before committing bar identity. Budget only limits repeated diagnostics. Recovery resets both retry count and warning latch.
- Side effect: persistent missing history pauses analysis rather than fabricating availability. Existing chart objects may remain visible while this gate waits; a global DATA_NOT_READY overlay/retirement policy is still needed.
- Regression: real extracted gate, each of ATR/ADX/RSI failing independently, negative/zero/partial return counts, repeated beyond exhaustion, then complete recovery.

**H2. Sniper partial history was accepted after exhaustion.**
- `nadir2.mq5:43133`, `MTF_SniperCopyRatesBounded`; `:43196`, `MTF_SniperCopyBufferBounded` (use function locator if shifted).
- Root cause: explicit branches accepted partial closed rates/buffers after the retry budget. Different suffix lengths can refer to different chronological bar positions when paired by index.
- Impact: incomplete volatility/structure evidence, potential misaligned historical rates versus ATR.
- Correction: exhausted incomplete copies clear their output and return zero; complete recovery still works. `ResetLastError` precedes copies so diagnostics describe the current call.
- Side effect: short broker histories no longer acquire an artificial READY state after waiting. Callers can still elect to skip unavailable timeframes: see H5.
- Regression: seven timeframe slots, partial histories over ten attempts (budget three in harness), invalid slot index, full recovery; buffer negative/zero/short returns and invalid handle/BarsCalculated.

**H3. Invalid indicator samples became apparently valid zero observations.**
- `nadir2.mq5`, `MTF_SniperCopyBufferBounded`, numeric-validation loop near `43260`.
- Root cause: `EMPTY_VALUE`, NaN, infinity and negative values were rewritten to zero, yet returned as a usable count.
- Correction: reject the entire snapshot and clear it; state-latched `DATA_INVALID` diagnostic. `DATA_READY` is emitted only after numeric validation succeeds. Legitimate zero RSI/ADX is not prohibited.
- Side effect: more explicit unavailability during warm-up; the caller must still distinguish zero ATR from usable positive ATR.
- Regression: exact sentinel, NaN, infinity and negative injected sample, then recovery, under ASan/UBSan.

**H4. Registry component sanitization was not injective.**
- `MQL5/Include/QSMC/QSMC_SignalRegistry.mqh:166`, `QSR_Clean` / `QSR_Family`.
- Root cause: replacing `|` with `/` distinguished separator placement but merged raw `A|B` with raw `A/B`.
- Impact: unrelated identities can share episodes/cooldowns and suppress or relabel a scenario.
- Correction: escape `%` first as `%25`, then `|` as `%7C`; plain existing identifiers remain unchanged.
- Side effect: identities containing special characters change across upgrade; reload should be treated as a fresh in-memory registry session. This does not introduce durable registry persistence.
- Regression: `QSR_SelfTest` case 20 covers slash and literal-escape collisions; existing host-compiled chart/registry suite executes it.

### HIGH — unresolved release blockers

**H5. Sniper MTF readiness — risk substitutions fixed; broader MTF contract still unresolved.**
- Original defects: H1 ATR was only overwritten after success, missing H1 ADX fell back to chart `g_adx`, and trade management substituted chart/synthetic ATR for missing H1/M15 ATR.
- Continuation correction: `MTF_SniperInvalidateSnapshot` clears cached H1 values, raw/merged/active outputs and previous drawings before a fresh decision. `MTF_SniperZone_Update` requires positive finite chart/H1/M15 ATR, complete H1 ADX and M15 structure data; M5 charts additionally require M5 execution data rather than silently switching to M15. Missing input returns without committing a bar. Scoring returns zero when the Sniper snapshot is unavailable.
- Rates and ATR counts must match before zone collection; missing optional zone ATR does not discard measured OHLC macro votes or hide actual macro opposition. The copied closed-rate suffix must match the TF's closed-bar timestamp, unchanged across the ATR read. H1/M15 fingerprints must remain unchanged across the full collection/ADX transaction.
- Direct trade-management calls independently reject invalid ATR/insufficient M15 data and clear derived prices/lot/trailing outputs. No synthetic timeframe substitution remains in this risk function.
- Complete decisions remain frozen for their chart closed bar; subsequent H1/M15 rolls cannot rewrite that decision. A new chart closed bar always clears old cached risk evidence and revalidates. Failed attempts retry on the same chart bar.
- Side effects: Sniper scoring/drawings are unavailable until the required risk data recover. Optional zone-source timeframes were **not** arbitrarily turned into seven new hard prerequisites; lookback lengths and quality thresholds remain unchanged. Missing optional sources can still reduce macro/zone evidence and must not be called complete MTF alignment.
- Remaining: define mandatory macro/confirmation TFs, distinguish missing optional RSI/micro-MSS from measured negative evidence, and implement historical as-of selection for late attach/retry. Current timestamp checks catch suffix/rollover mismatch, not every stale calculated indicator or future-data hazard. No claim that H5 as a whole is closed.
- Regression: `tools/test_el_sniper_readiness.py` executes the actual update, invalidation, status, score and risk bodies. Terminal reads, zone detection and entry-evidence rules are explicitly stubbed; the test is not an MT5 scheduler or strategy proof.

**H6. Immutable confirmation facts lack the requested full price provenance.**
- `nadir2.mq5:2769`, `SConfirmedSignalJournalEntry`; `:3548`, `STradeSetup`; `AppendConfirmedSignalJournal` near `20922`.
- Journal retains prices, event ancestry and times, but not an immutable ATR value/TF/timestamp or exact pre-buffer structural stop reference.
- Consequently later logs cannot reliably reconstruct which volatility snapshot justified a wide structural stop. Recovering a value from a later mutable ATR buffer is not equivalent evidence.
- Next correction: snapshot provenance at creation, carry it through retest without re-anchoring, validate it at confirmation, then derive chart/CSV/alerts from the same immutable fact. Needs compatibility and replay tests; not guessed in this patch.

**H7. Historical liquidity classification depends on latest volatility.**
- `nadir2.mq5`, `DetectLiquidity` near `24929–24940`: one ATR from `closed` determines clustering tolerance for the historical fractal loop; the same ATR is passed into sweep strength checks on older `b`.
- Consequence: full rebuilds under changed volatility can change historical clusters/priority. Per-index ATR in the modular MarketData engine does not fix this host implementation.
- Next correction requires causal fixtures specifying pool formation/merge availability and per-event tolerance. Simply replacing one variable does not prove cluster history remains causal. Historical no-repaint acceptance remains unverified.

### HIGH — additional confirmed geometry defect fixed in continuation

**H8. Sniper stop sign and target ordering could authorize invalid geometry.**
- File/function: `nadir2.mq5`, `MTF_SniperComputeTradeManagement` (final locations in the inventory and continuation locator table).
- Root cause: risk used `MathAbs(entry-sl)`, hiding wrong-side stops from direct/stale calls. TP1 could come from a distant opposing zone while TP2/TP3 fell back to 2R/3R closer to entry; no final target-order check existed.
- Example BUY: entry 100, structural SL 97.4, opposing TP1 110, projected TP2 105.2 and TP3 107.8. SELL mirror: entry 100, SL 102.6, TP1 90, TP2 94.8, TP3 92.2. Both ladders are crossed even though individual rewards are positive.
- Correction: signed directional risk with finite/positive entry-stop validation (`SKIP_STOP_GEOMETRY`); finite positive and strictly ordered target validation using the existing `ValidateTargetGeometry` (`SKIP_TARGET_GEOMETRY`). Clear invalid targets and prevent entry authorization; preserve the structural stop. Do not invent a replacement closer objective.
- Side effect: formerly crossed target ladders are rejected. Valid normal mirrored ladders, the existing H1 stop ceiling and structural stop formula remain unchanged.
- Regression: actual risk function for BUY and SELL, valid baseline, wrong-side entry/stop, distant opposing-zone target crossing, unchanged structural stop, and unavailable derived outputs after rejection.

### MEDIUM — unresolved / constrained behavior

**M1. Required diagnostic schema and rejection taxonomy are not universal.** `CalculateAITradeSetup` has silent early returns (`total<50`, ATR unavailable); existing GateAudit/TopDown/CSV messages use several vocabularies. The five requested DATA states are not implemented as one cross-module contract. This patch adds only targeted incomplete/invalid/recovery diagnostics, not universal logging compliance.

**M2. Registry lifecycle is deliberately smaller than the requested lifecycle.** `QSR_TransitionAllowed:142` supports DETECTED -> CONFIRMED -> ACTIVE -> terminal (and terminal exits), not every requested candidate/armed/pending/published state. CORE retest state lives separately. Do not add dummy transitions merely to match names. Cross-registry persistence/reload identity still requires terminal tests.

**M3. Target-collapse fallback cannot succeed.** `CalculateAITradeSetup` near `21730` assigns `tp2=tp1; tp3=tp1` after failed geometry, then rechecks `ValidateTargetGeometry`, which requires strict TP ordering (`18724`). The second check must fail for finite values. This is fail-safe, but the comment promising a single-objective fallback is false and the branch does not provide one. Safest default is preserve rejection; supporting single-target signals requires an explicit ABI/consumer decision.

**M4. Main copy gate validates copy counts, not all numeric/timestamp properties.** A complete copy is not proof of finite positive closed ATR, synchronized timestamps or fresh HTF handles. The Sniper numeric correction is not a universal indicator validator. Add closed-sample checks without rejecting legitimate indicator warm-up sentinels in irrelevant historical slots.

### LOW — fixed test reliability issue

**L1. Chart-hygiene suite treated a host's exact line count as behavior.** `tools/test_qsmc_chart_hygiene.py:130`. Legitimate fixes made the suite fail before native-skip checks, causing misleading secondary native-toolchain failures. Removed only the exact 45,002-line pin; pure CRLF, mirror, buffer/input/object contracts and executed chart/registry tests remain. Initial failed runs are disclosed in section G.

No claim that all possible CRITICAL defects have been excluded: whole-terminal execution and several acceptance requirements remain unverified.

## C. Signal pipeline and strategy definitions

### Main authoritative CORE

1. `OnInit` creates handles/buffers; `OnCalculate` mirrors chart data into chronological arrays. Latest closed index is `rates_total-2`. Patched mandatory-copy gate returns before new-bar identity on incomplete input.
2. `DetectStructure`: confirm fractal at `f=b-n` with `n` closed bars on either side; earlier equal extremes are allowed but later equals disqualify. Close above confirmed high/below confirmed low is a break. With-trend break = BOS; reversal with body >= per-bar ATR * `InpDisplacementATR` = MSS, otherwise CHoCH. INIT seeds trend and cannot authorize an anchor.
3. `DetectLiquidity`: fractal highs/lows become EQH/EQL records even before a second pivot. Nearby same-side levels merge by averaging. This is **not** identical to `CStructureEngine`, whose documented pool definition requires equal-pivot pairs. Sweep requires high > pool with close < pool (SELL) or low < pool with close > pool (BUY). Touch-only closes do not qualify; one sweep child consumes its exact pool.
4. `BuildCausalEventGraph` near `17226`: pool -> exact-parent sweep -> validated displacement -> BOS/CHoCH/MSS -> exact displacement/structure-bound OB/FVG. Sweep availability must precede displacement occurrence; displacement strictly follows sweep and precedes structure. Invalid paths do not become valid anchors merely because chart objects exist.
5. `SelectBestStructureAnchor` and `CalculateAITradeSetup` near `21351` evaluate both directions. HTF bias orders candidates and, with explicit opposing bias, the other side is diagnostic-only. This is an intentional strategy asymmetry, not a reversed SELL sign. Neutral tie-break prefers BUY first; no market outcome symmetry is promised.
6. Zone blacklisting, spread, optional institutional veto, structural stop distance, barrier/target geometry, RR, scoring/confidence/reliability and lifecycle/candle gates remain. No threshold was relaxed by this patch.
7. With retest lifecycle, an active immutable setup owns execution until confirmation/invalidation/timeout. Opposite observations can remain visible through RXN; observation does not equal execution authority.
8. `AppendConfirmedSignalJournal` validates later confirmation/availability metadata and exact replay consistency. `SigLog_CollectCore:14687` writes the journal tuple to CORE buffers at the bar closing at availability. Buffers 7–12 are direction, entry, SL, TP1, TP2, TP3; companion independently validates/expires signals.
9. `AlertDispatcherFinalize:41645` ranks CORE/ZRE/RXN scenario candidates separately. Optional unified mode updates the closed-bar snapshot before checking authorization. Primary reaction drawings can be explicitly non-authoritative; not every BUY/SELL annotation is an executable CORE signal.

### Other engines and evidence definitions

- `CStructureEngine` requires strict local extrema (plateaus excluded), a closed close past break buffer for BOS/CHoCH, equal-pivot pools, wick penetration and close-back for sweeps. It is not proof of the legacy host's pool behavior.
- `SvpLiquidity` maps M15 BSL/SSL, equal pivots and previous complete day/week levels. Its sweep lifecycle distinguishes detected rejection from displacement+structure-confirmed sweep. `SvpZones` and `SvpDecision` combine zones and volume-profile conditions; these are separate analytical semantics.
- PDH/PDL, PWH/PWL, sessions, internal/external labels and Sniper clustering exist in additional host/Svp paths. This audit does **not** certify all expiration/merge/invalidation formulas across these implementations. No unsupported claim that one common definition applies to every module.
- OB/FVG validation, mitigation, expiry, premium/discount and range rules have existing dedicated suites, but those suites are not a full causal proof of every host branch. An invalidated zone must remain excluded at the point of use, not just hidden on chart.

### Rejection interpretation

Quality rejection (spread/RR/confidence/HTF opposition), data unavailable, not-yet-confirmed, and expired/invalidated are distinct concepts. Existing diagnostics cover many gates, but not every early exit or every advisory path. A unified reason enum and per-candidate trace remain necessary. Increasing signal count is not evidence of correction.

## D. XAUUSD price geometry and stop policy

Prices are absolute quote units, not pips. The host uses tick-normalization (`NormalizePriceToTick`); broker point, tick size, digits, stops-level and fill geometry must still be captured in terminal evidence. Do not infer these from a symbol name or assume every XAUUSD broker uses the same tick.

`DirectionalRR` uses BUY risk `entry-sl`, reward `target-entry`; SELL risk `sl-entry`, reward `entry-target`. It returns -1 for risk <= point or nonpositive reward. `ValidateTargetGeometry` requires correctly sided stop and strict ordered TP1/TP2/TP3. Host tests execute both functions, not merely Python copies.

| Example | Risk | Reward TP1 | RR | Interpretation |
|---|---:|---:|---:|---|
| BUY E=3952.86, SL=3942.86, TPs=3972.86/3982.86/3992.86 | 10 | 20 | 2 | Correct directional geometry only |
| SELL E=3952.86, SL=3962.86, TPs=3932.86/3922.86/3912.86 | 10 | 20 | 2 | Mirrored valid geometry only |
| BUY E=100, SL=101 | negative | — | invalid | Wrong side stop |
| SELL E=100, SL=99 | negative | — | invalid | Wrong side stop |
| BUY TP below entry / SELL TP above entry | positive if stop correct | negative | invalid | Wrong side reward |
| E=SL / E=TP | zero risk / zero reward | — | invalid | Must not trade |
| Supplied SELL E=3952.86, SL=4170.84, TP=3516.91 | **217.98** | **435.95** | **1.999954** | Geometry is correct; market justification UNKNOWN |

For the supplied SELL, no originating timestamp, TF, broker rates, ATR snapshot, zone/sweep references or journal record was supplied. It is impossible to attribute it honestly to a particular wrong swing, ATR bug, or even a particular engine. Its stop is approximately 5.51% of entry, not automatically invalid. At hypothetical ATR=20 it is 10.899 ATR; at ATR=60 it is 3.633 ATR. These ATRs are illustrations, not measured market data.

### Existing configurable policy (preserved, not duplicated)

Main CORE entry is zone top for BUY / zone bottom for SELL. Structural stop is opposite zone edge, or farther sweep extreme when `InpSLBeyondSweep`, plus signed `InpSLBufferATR * chart closed ATR`. Entry/stop are tick-normalized. `CalculateAITradeSetup` rejects risk <= point or > ATR * `EffMaxStopATR`; it does not silently tighten the stop.

`InpMaxStopATR` default = 4; strict mode uses configured cap; practical profile raises effective ceiling to at least 6 via `EffMaxStopATR:19587`, with an existing init banner. Thus the example needs ATR >=54.495 at a 4-ATR ceiling, or >=36.33 at 6 ATR, before this distance gate alone passes. Passing distance does not prove a valid setup.

Other plans differ: advisory risk-model `InpRMSLMaxATR` defaults 2; Sniper hard maximum is 2 H1 ATR; the continuation removes its chart/synthetic ATR fallback and clears cached risk values before refresh (H5). The wider macro/as-of readiness contract remains unresolved. Do not label all three as the same policy.

Required diagnostics status: symbol/TF/direction/prices/times and event ids are available across existing outputs; risk/reward/RR are calculated in places. **Every signal does not yet expose the entire requested single record** (especially ATR TF/time, structural pre-buffer reference, immutable entry source and SL/ATR). H6 blocks acceptance. No fabricated diagnostics fields were filled with later/current values.

## E. MTF and data-readiness review

| Path | Timeframe/readiness behavior | Remaining issue |
|---|---|---|
| Main host | Chart ATR/ADX/RSI; chronological tail/full copies; complete mandatory count now required | Full counts do not prove all numeric/freshness properties |
| TopDown | D1/H4/H1/M30/M15/M5 closed-data chain, fingerprints of closed/current TF opens and chart bar | Missing-data WAIT is only a hard CORE veto when institutional confirmation is required; optional overlay must not be misrepresented as mandatory evidence |
| EMA alignment | Five configurable TF handles, shift-1 close vs shift-1 EMA; unknown rows excluded | Percentage denominator is known rows, not proof all six TFs are present; no complete timestamp transaction across handles |
| Sniper | W1/D1/H4/H1/M30/M15/M5; helpers start at shift 1; risk gate now requires measured H1/M15 data and matched suffixes | Optional rows still skipped; macro completeness, late-attach as-of alignment and calculated-buffer freshness remain H5 |
| CMarketData | Requires requested rates count; previous snapshot retained but Ready=false after short copy; newest/closed times tracked | Terminal freshness/history reload still needs validation |
| Historical ATRAt | External current ATR only for latest closed index; historical Wilder calculation per index | Does not repair all legacy host historical ATR fallbacks or liquidity tolerance |

D1, H4, H1, M30, M15 and M5 all have explicit TopDown selections in source. The new stub test iterates seven Sniper slots; it is **not** six actual broker-history replay tests. No terminal evidence proves synchronization at TF boundaries, weekend gaps, history reload or broker clock changes. Correct next design: each mandatory evidence snapshot carries symbol, TF, event/availability time, source-bar fingerprint, and DATA status; aggregate authorization fails closed if any mandatory snapshot is loading/incomplete/stale/invalid. Do not impose this on intentionally optional observational rows without documenting authority.

## F. Implemented changes

1. `nadir2.mq5` and byte-identical deployment mirror: mandatory copy gate fail-closed after exhaustion; Sniper partial-copy rejection; reject invalid numeric Sniper arrays; reset copy error; state-latched invalid/recovery diagnostics. No new inputs, buffer layout changes, risk threshold changes or signal fabrication.
2. `MQL5/Include/QSMC/QSMC_SignalRegistry.mqh`: collision-free component escaping and self-test case 20.
3. `tools/test_el_data_integrity.py`: extract and host-execute actual shipped data gates and geometry functions with deterministic API stubs and ASan/UBSan; missing compiler exits 77.
4. `tools/check_production_ready.py`: add new regression to curated gate.
5. `tools/test_qsmc_chart_hygiene.py`: replace exact line-count assertion with CRLF invariant; retain behavioral/mirror/ABI checks.
6. Continuation in the host/mirror: Sniper risk-data snapshot invalidation, observable unavailable/recovery state, stale-score/drawing retirement, closed-bar cache preservation, mandatory risk-TF checks and stop/target geometry rejection.
7. `tools/test_el_sniper_readiness.py`: host-compiled actual-body regression for these continuation fixes; added to the curated gate.
8. This report, refreshed full inventory document and `docs/INDEX.md` registration.

Possible operational consequences: loading/short histories can wait indefinitely instead of failing open; no retry budget can make unavailable mandatory data valid. A legitimate setup may be observed later after recovery, and publication of the correct original closed bar requires MT5 replay verification. Special-character registry identities change once on upgrade. No broad architecture rewrite or dead-code deletion was performed.

## G. Testing and evidence

### Executed results

| Category | Actual result |
|---|---|
| Static source audit | Inventory/include topology PASS; dialect check 0 errors/0 warnings; static checker 0 errors/**5 allocation-lifecycle warnings** (not leak proofs) |
| Automated checks | Continuation curated invocation completed: **70 PASS, 0 FAIL, 0 SKIP**. The earlier 68/69 run and corrected docs-index failure are retained below as historical evidence. |
| Host-compiled tests | Actual-body data/geometry and Sniper readiness/geometry harnesses PASS with ASan/UBSan; chart/registry harness **56/56 PASS**; curated native resolver, unified decision, liquidity-value, QATS and SMC+VP checks PASS |
| Post-edit focused reruns | Data/geometry PASS; layout 8/8 PASS; dialect PASS; static 0 errors/5 warnings; comment integrity 19/19 PASS; CRLF-aware diff whitespace PASS |
| MQL5 compilation | **NOT RUN** |
| Strategy Tester | **NOT RUN** |
| Live MT5 Demo | **NOT RUN** |

The initial 69-suite invocation ran before final documentation registration and is retained as evidence, not retroactively relabeled OFFLINE GO. The continuation invocation exited 0 with 70/70 PASS. The final closed-bar-cache and optional macro-OHLC preservation refinements landed while that long invocation was running; their final exact function bodies were separately rerun in the Sniper sanitizer harness, with focused final dialect/static/comment, performance, diagnostics, risk-model, layout and whitespace checks. This is not represented as an atomic full-suite run after every final edit. All counts describe suites/checks, not a count of proven market scenarios. Native stubs cannot reproduce the MT5 asynchronous scheduler, `iCustom` ABI deployment, broker ticks or chart UI.

Initial audit-suite attempts were not clean baseline runs: the first command could not open a missing scratch directory; a later scratch directory at repository root caused the strict layout gate to fail. Moving scratch artifacts under ignored `out/` removed that environmental cause. The changed host also exposed the obsolete 45,002-line chart-test pin; that failure cascaded into native-skip tests. The pin correction is described in L1. No initial failing run is presented as an unchanged-base measurement.

Required but **NOT RUN**: MetaEditor F7, MQL5 script tests, Strategy Tester XAUUSD D1/H4/H1/M30/M15/M5 runs, live MT5 Demo, reload/timeframe-switch duplicate verification, broker-specific tick/stops constraints, end-to-end chart/alert/buffer price equality, complete candidate matrix for missing sweep/displacement/MSS/invalid zones through all host entry paths. Existing source contracts and native subset tests do not substitute for those runs.

Reproducible commands:

```sh
python3 tools/test_el_data_integrity.py
python3 tools/test_qsmc_chart_hygiene.py
python3 tools/check_production_ready.py --require-native
git -c core.whitespace=cr-at-eol diff --check
```

The whitespace override acknowledges the host's deliberately preserved CRLF; plain `git diff --check` flags CR line endings in this environment.

## Recent-change verification

The repository is a **shallow checkout**. The visible base log contains `4e1ef71` (merge PR #77). `git show` could not resolve any of the three supplied hashes:
`96a1584e36327e3f1e0a9278e98bfebd83b99ac9`, `b5acb216d7750f4c46bec4ee5beb6e2e76c07a4d`, `ef602bfcaab297529bd703dd02cc625cf14bb4d9`.
This means absent from the locally available object history, **not** proof they never existed upstream. No attribution to those commits is invented.

Current code does contain the relevant protections: `QSR_AgeSeconds` clamps backwards time; `QSR_Episode` expires all idle family records; named alert-source ids avoid mixing the dispatcher and enum id spaces; `UD_Update` derives current-bar authority from confirmation availability; `UD_AlertAllows` requires exact bar identity when enabled; `UD_LogAllows` releases old/future timestamps and recycles a saturated table; `UD_ValidSigIndex` guards path lookups; confirmation journal duplicate comparison preserves immutable facts. These protections were retained. The identity escaping fix repairs a residual collision rather than reverting family-key protection.

## H. Remaining risks and next release gates

1. Resolve H5–H7 with isolated causal fixtures; snapshot immutable price provenance rather than logging mutable approximations.
2. Specify mandatory TFs per signal engine/quality class and optional evidence separately. Add explicit DATA_STALE and full timestamp-transaction tests.
3. Add end-to-end real-host fixtures for BUY/SELL confirmation, invalid/missing evidence, expired/invalidated setups, chart reload and duplicate publication. The new tests cover copy gates and geometry only.
4. Require complete diagnostics schema and explicit rejection reasons across silent exits and all publication paths, with transition-only logging.
5. Review nonfinite prices, all ArrayResize failure handling, lifetime/handle cleanup across init failures, cross-instance rendering namespaces, journal retention growth and notification failures in actual MT5. Existing bounded registries and incremental-copy patterns are positive evidence, not whole-system guarantees.
6. Run MetaEditor then Strategy Tester then demo; capture broker history, inputs, build identity, signal journal, exported buffers and screenshots/alerts. Never use a REAL account for this audit.
7. Supplied wide SELL cannot be root-caused without original market data and provenance. Do not force a narrower stop to make it look acceptable.

## I. Final release verdict

**NOT READY**

The targeted repairs, including the Sniper continuation, are suitable for review, but outstanding data provenance/readiness defects and unexecuted terminal tests prevent declaring the requested audit acceptance complete. Offline green is not production readiness.

## Appendix — initial curated invocation outcome (historical)

This is the captured invocation outcome **before** fixing docs index registration. The layout failure was `L7 document(s) absent from docs/INDEX.md: EL_SOURCE_INVENTORY_2026-11-18.md`; the subsequent layout check passed all eight invariants after registering both new documents.

```text
QSMC v6.6.24 curated offline production-readiness summary
checks=69 passed=68 failed=1 skipped=0
PASS rc=0 0.3s python-parse
FAIL rc=1 0.1s repo-layout
PASS rc=0 0.4s preset-binding
PASS rc=0 2.8s include-graph
PASS rc=0 3.1s include-graph-contracts
PASS rc=0 9.3s mql5-rules
PASS rc=0 11.1s static-check
PASS rc=0 0.7s comment-integrity
PASS rc=0 0.7s tick-performance
PASS rc=0 0.8s runtime-diagnostics
PASS rc=0 0.9s el-data-integrity
PASS rc=0 0.2s ux1-master-switch
PASS rc=0 0.0s display-authority
PASS rc=0 0.0s price-provenance
PASS rc=0 0.5s instance-identity
PASS rc=0 2.4s input-fingerprint-parser
PASS rc=0 0.4s input-fingerprint-manifest
PASS rc=0 0.4s set-presets
PASS rc=0 0.3s autotrader-contract
PASS rc=0 0.1s execution-safety
PASS rc=0 0.7s execution-rules
PASS rc=0 0.5s candle-patterns
PASS rc=0 0.7s demo-preflight
PASS rc=0 0.1s diag-bridge
PASS rc=0 0.0s historical-atr
PASS rc=0 0.5s volatility-window
PASS rc=0 0.0s early-break
PASS rc=0 0.0s arbiter-parity
PASS rc=0 0.0s scanner-arithmetic
PASS rc=0 0.0s quant-stats
PASS rc=0 0.6s wfa-robustness
PASS rc=0 0.0s why-no-trades
PASS rc=0 0.0s structure-events
PASS rc=0 0.0s zone-scoring
PASS rc=0 0.0s edgebook
PASS rc=0 1.1s liquidity-value-runtime
PASS rc=0 0.1s dashboard-clarity
PASS rc=0 0.1s incident-compact
PASS rc=0 0.1s orderblock-lifecycle
PASS rc=0 1.0s causal-chain-regressions
PASS rc=0 0.1s zre-signal-role
PASS rc=0 0.1s unified-decision-contract
PASS rc=0 1.6s unified-decision-runtime
PASS rc=0 0.8s resolver-runtime
PASS rc=0 0.0s scanner-snapshot
PASS rc=0 0.1s phase2-modules
PASS rc=0 0.1s phase3-wyckoff
PASS rc=0 0.4s phase4-priceaction
PASS rc=0 0.5s phase6-confluence
PASS rc=0 0.6s phase7-riskmodel
PASS rc=0 0.0s scenario-geometry
PASS rc=0 0.0s host-patch-idempotent
PASS rc=0 11.4s native-toolchain
PASS rc=0 0.1s defaults-match-preset
PASS rc=0 0.1s signal-execution-profiles
PASS rc=0 0.7s compile-errors
PASS rc=0 0.0s scalper-preset
PASS rc=0 0.1s at-risk-audit
PASS rc=0 0.1s quantum-ea-verify
PASS rc=0 111.1s qats-native-build
PASS rc=0 163.3s qats-dual-direction
PASS rc=0 23.7s qats-journal-report
PASS rc=0 0.7s compile-regressions
PASS rc=0 0.9s xau-execution-policy
PASS rc=0 0.4s quantum-account-policy
PASS rc=0 0.1s qats-limit-entry
PASS rc=0 10.5s qsmc-chart-hygiene
PASS rc=0 93.8s qsmc-smcvp-engine
PASS rc=0 1.9s release-gate

Manual gates still required: MetaEditor F7 (0 errors), banner v6.6.24,
EA handshake OK, demo/paper observation, and the go-live runbook before real money.
```

## Continuation — Sniper readiness and geometry

The continuation does not declare the full audit complete. H5 risk-timeframe substitutions/stale cache are addressed; H6 immutable CORE provenance, H7 causal historical liquidity tolerance, and the remaining H5 mandatory-macro/as-of contract are still release blockers.

### Exact final code locators

| File | Function / purpose | Line |
|---|---|---:|
| `nadir2.mq5` (and mirror) | `MTF_SniperComputeTradeManagement` | 44446 |
| `nadir2.mq5` (and mirror) | `MTF_SniperScoreForDirection` | 44697 |
| `nadir2.mq5` (and mirror) | `MTF_SniperInvalidateSnapshot` | 44733 |
| `nadir2.mq5` (and mirror) | `MTF_SniperDataStatus` | 44749 |
| `nadir2.mq5` (and mirror) | `MTF_SniperZone_Update` | 44758 |

Direct body tests cover: loss of H1 ATR/H1 ADX/M15 data, partial ATR versus rates, stale rate suffix, risk-TF rollover during collection, chart ATR failure, same-bar recovery, frozen complete decisions, next-chart-bar refresh, M5 execution data loss, optional M30 nonblocking behavior, preservation of W1 macro OHLC when optional zone ATR is missing, chart history shrink, disabling Sniper, invalid/sentinel/NaN/infinite ATR, normal mirrored price geometry, unchanged wide-stop rejection, wrong-side stops and crossed target ladders. These are deterministic stubbed-I/O tests, not a six-TF broker-data replay.

A complete decision is cached for its chart closed bar, not recomputed using newer child-TF information; this intentionally preserves the pre-existing closed-bar semantics. A late attach or retry still needs historical as-of loading to prove every cross-TF candle was available at that original boundary.

### Continuation test outcome

- Curated offline invocation: **70/70 PASS**, exit 0, `--require-native`; no skipped suites.
- Final actual-body Sniper sanitizer rerun: **PASS**, including crossed target ladders and signed stop rejection for both directions.
- Original data/geometry sanitizer rerun: **PASS**.
- Phase 7 risk-model contracts: **292 checks, 0 failures**.
- Final dialect: **0 errors, 0 warnings**. Final static consistency: **0 errors, 5 existing allocation-lifecycle warnings**.
- Comment integrity: **19 checks, 0 failures**. Tick-performance and runtime-diagnostics source/native subsets: **0 failures**. Layout: **8/8 PASS**.
- Forced absent-toolchain test: expected **exit 77 / SKIP**, not a falsely reported native pass.
- CRLF-aware `git diff --check`: **PASS**. Indicator mirror byte equality: **PASS**.
- MQL5 compilation / Strategy Tester / Live MT5 Demo: **NOT RUN**.

The command's wording `OFFLINE GO` concerns mechanical checks only. Engineering release verdict remains **NOT READY** because the report's unresolved readiness/provenance/causality blockers are not removed by this result.

```text
QSMC v6.6.24 curated offline production-readiness summary
checks=70 passed=70 failed=0 skipped=0
PASS rc=0 0.2s python-parse
PASS rc=0 0.1s repo-layout
PASS rc=0 0.4s preset-binding
PASS rc=0 2.8s include-graph
PASS rc=0 3.3s include-graph-contracts
PASS rc=0 9.9s mql5-rules
PASS rc=0 11.5s static-check
PASS rc=0 0.7s comment-integrity
PASS rc=0 0.7s tick-performance
PASS rc=0 0.9s runtime-diagnostics
PASS rc=0 1.0s el-data-integrity
PASS rc=0 1.6s el-sniper-readiness
PASS rc=0 0.3s ux1-master-switch
PASS rc=0 0.0s display-authority
PASS rc=0 0.0s price-provenance
PASS rc=0 0.5s instance-identity
PASS rc=0 2.5s input-fingerprint-parser
PASS rc=0 0.5s input-fingerprint-manifest
PASS rc=0 0.4s set-presets
PASS rc=0 0.3s autotrader-contract
PASS rc=0 0.1s execution-safety
PASS rc=0 0.7s execution-rules
PASS rc=0 0.6s candle-patterns
PASS rc=0 0.8s demo-preflight
PASS rc=0 0.1s diag-bridge
PASS rc=0 0.0s historical-atr
PASS rc=0 0.5s volatility-window
PASS rc=0 0.0s early-break
PASS rc=0 0.1s arbiter-parity
PASS rc=0 0.0s scanner-arithmetic
PASS rc=0 0.0s quant-stats
PASS rc=0 0.7s wfa-robustness
PASS rc=0 0.0s why-no-trades
PASS rc=0 0.0s structure-events
PASS rc=0 0.0s zone-scoring
PASS rc=0 0.0s edgebook
PASS rc=0 1.1s liquidity-value-runtime
PASS rc=0 0.1s dashboard-clarity
PASS rc=0 0.0s incident-compact
PASS rc=0 0.1s orderblock-lifecycle
PASS rc=0 0.6s causal-chain-regressions
PASS rc=0 0.0s zre-signal-role
PASS rc=0 0.1s unified-decision-contract
PASS rc=0 1.5s unified-decision-runtime
PASS rc=0 0.8s resolver-runtime
PASS rc=0 0.0s scanner-snapshot
PASS rc=0 0.1s phase2-modules
PASS rc=0 0.1s phase3-wyckoff
PASS rc=0 0.4s phase4-priceaction
PASS rc=0 0.5s phase6-confluence
PASS rc=0 0.6s phase7-riskmodel
PASS rc=0 0.0s scenario-geometry
PASS rc=0 0.0s host-patch-idempotent
PASS rc=0 10.6s native-toolchain
PASS rc=0 0.1s defaults-match-preset
PASS rc=0 0.1s signal-execution-profiles
PASS rc=0 0.8s compile-errors
PASS rc=0 0.0s scalper-preset
PASS rc=0 0.1s at-risk-audit
PASS rc=0 0.1s quantum-ea-verify
PASS rc=0 94.1s qats-native-build
PASS rc=0 129.1s qats-dual-direction
PASS rc=0 26.3s qats-journal-report
PASS rc=0 0.9s compile-regressions
PASS rc=0 0.9s xau-execution-policy
PASS rc=0 0.4s quantum-account-policy
PASS rc=0 0.1s qats-limit-entry
PASS rc=0 10.0s qsmc-chart-hygiene
PASS rc=0 86.9s qsmc-smcvp-engine
PASS rc=0 2.0s release-gate

Manual gates still required: MetaEditor F7 (0 errors), banner v6.6.24,
EA handshake OK, demo/paper observation, and the go-live runbook before real money.
```
