# QSMC full-repository audit & signal-intelligence repair — v6.6.10 AUDIT-TAC

Status: **four confirmed defects, all in the non-authoritative display path, fixed
at the root.** No entry gate was weakened, no threshold was lowered, no default was
changed, no module/input/buffer/dashboard element was removed, and no trade API was
added. **Nothing was compiled** — there is no MetaEditor in this environment, so
F7 remains the final judgement (see §8).

Branch: `arena/d4369e1f-terad`, forked from `main` @ `70dea7a`.

---

## 1. Repository architecture and dependency map

Verified by reading the tree, not assumed. `git status` was clean at the start;
there were no uncommitted user changes to preserve.

### 1.1 Layout

```
nadir2.mq5                     40 407 -> 40 848 lines   THE indicator (host, one translation unit)
MQL5/Include/QSMC/*.mqh        18 headers, 7 993 lines  the v6.6.0 arbitration subsystem
MQL5/Indicators/QSMC_ScannerProbe.mq5   310 lines       Phase-7 host for QSMC_Scanners.mqh
MQL5/Scripts/QSMC_ArbiterTest.mq5        68 lines       self-test harness
MQL5/Experts/KLJ_DataFeeder.mq5         524 lines       optional data feeder (inert by default)
MQL5/Experts/QSMC_AutoTrader.mq5      1 164 lines       execution companion (the ONLY file allowed
                                                        to reach the trade API; ships inert)
tools/*.py                     18 scripts, 4 861 lines  offline verification (no terminal needed)
docs/*.md                      15 documents
.github/workflows/qsmc-verify.yml                       CI: static + dialect + contract parity
```

`nadir2.mq5` is the **actual main indicator entry point** and it is the file that
carries every signal engine. `MQL5/Include/QSMC/QSMC_Root.mqh` **is present** and is
the root module: `CQuantumRoot`, the single global mutable object the subsystem adds
(`g_qsmc_root`), included once by the host at `nadir2.mq5:639`.

### 1.2 Subsystem include graph (verified by parsing every `#include`)

```
QSMC_Types.mqh  (0 includes — the shared vocabulary: SQZone, SSignalCandidate,
                 SGateCtx, SArbiterReport, ENUM_SIG_STATE, ENUM_ZR_ROLE …)
   ↑
   ├─ QSMC_MarketData.mqh   CBarSeries, CMarketData      (+ QSMC_Structure, QSMC_Reaction,
   ├─ QSMC_Zones.mqh        CZoneRegistry                  QSMC_Stats, QSMC_Scanners)
   ├─ QSMC_ZoneScorer.mqh   CZoneScorer
   ├─ QSMC_Preset.mqh       CPresetManager  ← the 40 documented inputs
   ├─ QSMC_Renderer.mqh     CChartRenderer  (owns every QSMC_ARB_* object)
   ├─ QSMC_Gates.mqh        CClosedBarGate, CDataQualityGate, CLocationGate, CBiasGate,
   │                        CRoomGate, CVolatilityGate, CCooldownGate, CFlipFlopGate,
   │                        CDistanceGate, CSessionGate            (+ QSMC_Zones)
   ├─ QSMC_AlertManager.mqh CAlertManager  ← the ONLY Alert/push/sound site  (+ QSMC_Gates)
   ├─ QSMC_Arbiter.mqh      CSignalArbiter (+ Gates, Zones, Reaction, AlertManager)
   ├─ QSMC_Bias.mqh         CBiasProvider  (+ MarketData)
   ├─ QSMC_Stats.mqh        CEWStatistics, CCUSUM, CVolumeProfile, CEdgeBook, CStatsLogger
   ├─ QSMC_EarlyBreakDetector.mqh CEarlyBreakDetector (+ Stats, Structure)
   ├─ QSMC_DataProvider.mqh CFileDataProvider  (not included by Root; used by the probe)
   └─ QSMC_Scanners.mqh     CAssetScanner, CTopSetupsScanner, CMomentumHeatmap,
                            CVolatilityHeatmap, CSeasonalityScanner
QSMC_Root.mqh   CQuantumRoot  ← includes 14 of the above
QSMC_Selftest.mqh CArbSelfTest ← includes Root (T1…T15)
```

### 1.3 Host-side engines inside `nadir2.mq5` (verified by counting definitions)

| family | defs | what it owns | per-bar entry point |
| --- | --- | --- | --- |
| `PMI_*` | 258 | Predictive Market Intelligence: paths, no-trade reasons, MTF leg mirror | `PMI_Update()` / `PMI_UpdateAll()` |
| `ZRE_*` | 199 | Zone Reaction Engine: the canonical closed-bar S/R zone registry, rejection, break/flip, entry+SL geometry, verdict | `ZRE_Update()` |
| `RXN_*` | 180 | Reaction Signal Layer: liquidity → displacement → structure phases and levels per zone | `RXN_Update()` |
| `MTF_*` | 84 | MTF SniperZone engine (W1→M5 confluence, 8-pillar strength) **and** the tactical MTF execution entry | `MTF_SniperZone_Update()`, `UpdateMTFExecutionEntry()` |
| `MVP_*` | 57 | Master Volume Profile: POC, value area, coverage | `MVP_Update()` |
| `QSMC_*` | 40 | the host↔subsystem bridge | `QSMC_ArbiterFeedAndFinalize()` |
| `Scenario*` / `SCN_*` | — | **Directional Scenario Engine (DSE)** — the module that prints `BUY PLAN — CONDITIONAL — <state>` | `ScenarioUpdate()` |
| `TopDown_*` / `g_td` | — | closed-bar D1→M5 top-down chain | `TopDown_Update()` |

### 1.4 Where each responsibility in the brief actually lives

| responsibility | verified location |
| --- | --- |
| D1/H4 directional bias | `ScenarioLoadTF(PERIOD_D1/H4/H1,…)` → `SScenarioContext.d1/h4/h1`, weighted consensus `bias_net_dir`/`bias_net_score` (D1 50 / H4 30 / H1 20, HTF-wins tie-break) built in `ScenarioBuildContext()`; separately `g_htf_bias`, `g_d1_structure_state`, and `CBiasProvider` for the arbiter |
| H1 market structure | `CStructureEngine` (`QSMC_Structure.mqh`) for the arbiter; `g_structures[]` (`SStructureBreak`, MSS/BOS/CHoCH) + `DetectStructure()` for the host; `g_scn_ctx.h1` for the DSE |
| M30/M15/M5 confirmation | `ScenarioEvaluateM30M15()` (M30 rejection + displacement, M15 structure), `ScenarioM5RetestScan()` (closed-M5 two-candle retest), `ScenarioChainMirror()` (`g_td` legs) |
| liquidity pools & sweeps | `g_liquidity[]`, `CE_LIQ_SWEEP` causal events, `SRxnLiquidity`, `RXN_PtsLiquidity()` |
| BOS / MSS-CHoCH / displacement | `DetectStructure()`, `g_causal_events[]` (`CE_FVG`, `CE_LIQ_SWEEP`, …), `RXN_ScanDisplacement()`, `InpCausalDisplacementBodyATR` |
| Order Blocks & FVG | `DetectOrderBlocks()`, `DetectFVG()`, `AddBreakerBlock()`, `g_orderblocks[]`, `g_fvgs[]`, `MTF_SniperOverlapsNativeOBorFVG()` |
| Premium/Discount & OTE | `g_scn_ctx.dealing_high/low/eq`, `daily_location`, `ScenarioMarkLocation()`, `DrawPremiumDiscount()`, `FibDPValue()`, `InpShowOTE` |
| S/R and session levels | ZRE registry (`g_zre_zones[]`, `g_zre_status[]`), `BuildConfluentSRLevels()`, `DrawPDHPDL()`, `DrawPivotPoints()`, `DrawCamarilla()`, `DrawSessionHighLow()`, `IsInKillZone()` |
| POC / volume profile | `CVolumeProfile` (`QSMC_Stats.mqh`) + `MVP_Update()`; explicitly tick-volume, not exchange volume |
| BUY/SELL scenario generation | `ScenarioDiscover()` → `ScenarioBuildPlan()` → `ScenarioClassifyPlan()` → `ScenarioBuildVerdict()` |
| setup scoring & conflict resolution | `ScenarioRankScore()`, `ScenarioPlanBetter()` (Priority A→D total order), `ScenarioPlanLeadKey()`, `ZRE_ScoreSignal()`, `RXN_Score()`, `CZoneScorer::Score()`, `CSignalArbiter::Finalize()` |
| entry / SL / TP / invalidation | `ZRE_ComputeEntrySL()`, `ZRE_FinalizeGeometry()`, `QSMC_BuildGeometry()`, `ScenarioEvaluateGeometry()`, `structural_invalidation`, `LifecycleInvalidateActive()` |
| MTF tactical previews | `UpdateMTFExecutionEntry()` (nadir2.mq5:5382) — **the defect site** |
| freshness / expiration / dashboard text | `InpZREFreshBars`, `InpZREExpireBars`, `InpRetestTimeoutBars`, `InpBlacklistExpiryBars`, `ScenarioMarkLate()`, `ScenarioDashCompact/Full()`, `DrawQuantumDashboard()` |

### 1.5 Verified per-bar execution order inside `OnCalculate` (nadir2.mq5:14519)

```
14907  TopDown_Update()                 closed-bar D1 -> M5 chain
14915  ConfirmPendingDirectSetup()      (retest-lifecycle off)
14929  ManageSetupLifecycle()           Core lifecycle owns the newly closed bar first
14932  PMI_Update(); MTF_SniperZone_Update()
14934  CalculateAITradeSetup()          seeds a Core setup when nothing owns the chart
15001  UpdateEarlyBreakPreview()        forming-bar preview (visual only)
15002  UpdateMTFExecutionEntry()   <<<  tactical preview: draws its label, feeds the arbiter
15080  ZRE_Update()                     canonical closed-bar zone registry
15091  RXN_Update()
15093  AlertDispatcherFinalize()   ->   QSMC_ArbiterFeedAndFinalize() -> CQuantumRoot::FinalizeBar()
15097  ScenarioUpdate()            <<<  DSE publishes BUY PLAN / SELL PLAN and the verdict
15101  SigLog_Update(); DiagPublishCoreState(); GateProfilePublish()
15110  DrawQuantumDashboard()           the card, drawn last, reads everything above
```

**This ordering is itself part of the diagnosis** (§3, defect 2).

---

## 2. Confirmed defects

Every row below is backed by source, and each was reproduced offline before it was
called a defect. Severity: **1** = contradictory output the operator sees; **2** =
dead safety logic; **3** = misleading wording/visual; **4** = documentation drift.

| # | file : function | class | wrong behaviour | evidence | fix | test |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | `nadir2.mq5:5382` `UpdateMTFExecutionEntry()` | **1** | The tactical preview drew `TACTICAL / PREVIEW MTF BUY ENTRY PREVIEW @…` **without reading any authoritative module**. Its direction could come from `g_htf_bias` alone plus *any* past `g_structures[]` event of the same side. So an INVALIDATED BUY plan and a live BUY entry preview were on the chart at the same moment | the whole function body contained **zero** references to `g_scn_*`, `g_active_setup.state`, the ZRE/RXN registries, or `QSMC_Root()`'s report — verified by grep over the function region | one authoritative-state gate, `TacticalAuthorityGate()` (nadir2.mq5:27396), called at `:5424` **before** anything is drawn, marked, or handed to the arbiter | `tools/test_tactical_authority.py` A1-A3, A6, A10, B2, B3; MQL5 `TacticalAuthoritySelfTest` TAC-1…TAC-7 |
| **2** | `nadir2.mq5:5477` + `:5500` vs `tools/apply_qsmc_arb_patch.py:259` | **2** | `g_last_mtf_entry_key` had **two readers and no writer**. `apply_qsmc_arb_patch.py` EDIT 6 deleted the alert block that contained the only assignment and left both readers. The v6.4.1 guard *"a signal that already fired CONFIRMED never re-alerts as a PREVIEW when the condition lapses and re-arms"* was therefore permanently dead, and the `g_mtf_sig_time` re-anchor condition was permanently true | `grep -rn g_last_mtf_entry_key` before the fix: 1 declaration, 2 reads, 0 writes in `nadir2.mq5`; the only write in the whole repository was inside the patch script's *removed* block | `if(closed_confirm) g_last_mtf_entry_key=id+"|CONFIRMED";` at `:5491`, restoring the documented v6.4.1 semantics. Alerts stay owned by the arbitration layer | `test_tactical_authority.py` A12 (including an explicit reproduction of the pre-fix behaviour) and B1 |
| **3** | `nadir2.mq5:28492` `ScenarioDrawOne()` + `:28544` `ScenarioDraw()` | **3** | A plan killed by `plan_dead` (a closed M5 candle beyond the structural invalidation) reaches `SCN_INVALIDATED` **without** setting `invalidated`. `ScenarioDrawOne` guarded only on `p.invalidated`, so that plan was still drawn as a tinted *conditional retest area* and tagged **`BUY PLAN — CONDITIONAL — INVALIDATED`** — a live-looking zone whose own tag said it was dead. That exact string is what the chart showed | `ScenarioClassifyPlan()` (`:27819`): `if(p.invalidated){…}` then a *separate* `if(p.plan_dead){ p.state=SCN_INVALIDATED; …}` at `:27838`; `ScenarioM5RetestScan()` sets `plan_dead` and `dead_note` only | one `terminal` predicate covering both invalidation paths; terminal plans are drawn in the terminal colour, the tag never says CONDITIONAL, and the tooltip says RETIRED PLAN. `ScenarioDraw()`'s `expect_buy/expect_sell` now match the guard exactly | `test_tactical_authority.py` A3 (`plan_dead` reaches `SCN_INVALIDATED` without setting `invalidated`), B8 (six contracts) |
| **4** | `nadir2.mq5` `#define QSMC_VERSION_TEXT "v6.6.9"` vs five `v6.6.10` markers | **4** | The build already carried internal `v6.6.10` markers (the diagnostic bridge at `:2264`, `:5169`, `:15101`) while the release triple still said v6.6.9. `check_release_gate.py` G1 only compares the triple across host/`QSMC_Root.mqh` banner/runbook, so this drift is invisible to CI — and `docs/QSMC_DASHBOARD_CLARITY.md` tells the operator to identify a stale compiled copy *by its version string* | `grep -n "v6\.6\.10" nadir2.mq5` returned 3 hits at v6.6.9; G1 passed | **reported, not changed.** Bumping the release triple touches `#property version`, `QSMC_VERSION_TEXT`, the `[QSMC_ARB]` banner, the runbook title, the CI echo line and every doc header. That is a release decision, not a defect repair, and doing it silently inside this pass would have made the change harder to revert. This pass is tagged `v6.6.10 AUDIT-TAC` in-code to match the existing forward-tagged markers | none needed; recorded as a prioritised next step (§9) |

### Checked and cleared — **not** defects

These were the other plausible suspects. Each was read and found correct, and each is
now pinned by a test so it cannot rot silently:

* **Wick vs close on a level break.** `ZRE_IsBrokenNow()` (`:32622`) compares
  `prev_close`/`close_px` against the edge ± `break_atr*ATR`; `ZRE_IsFlipped()`
  (`:32162`) scans `[closed-lookback … closed-1]` **closes only**;
  `RXN_BrokenNow()` and `MTF_SniperEvaluateTouchesAndBreaches()` breach tests both use
  `bc` (the close). A wick through a level is a *touch*, never a break. → A5.
* **`ZRE_EffectiveSide()`** reads both closed-bar facts through one resolver
  (the v6.6.9 fix) and `GetSignalDirection()` never lets HTF bias flip a direction. → A6.
* **`ScenarioPlanBetter()`** (`:28015`) is a correct total order: Priority A validity
  first, then `invalidated`, then `plan_dead`, then alignment, then evidence score.
  A `rank_score` of 100 cannot outrank a failed validity gate. → A7.
* **`ScenarioM5RetestScan()`** requires two *distinct* closed M5 candles (touch, then a
  later close beyond the protected edge), refuses non-chronological/duplicate
  timestamps, refuses bars before the zone's proven origin, and returns
  `INVALIDATED_BEFORE_RETEST` on a breach. A candle can never confirm its own retest. → A6, A9.
* **MTF data causality.** `MTF_SniperCopyRatesBounded()` uses `CopyRates(_Symbol,tf,1,count,…)`
  — shift 1, so closed bars only — verifies ascending timestamps and positive OHLC, and
  the swing loop `for(i=5;i<=bars-1-5;i++)` requires five right bars. No forming bar and
  no unconfirmed swing enters the sniper engine.
* **The arbiter's own tactical path** (`QSMC_Root.mqh:778` `BuildTacticalCandidate`)
  already enforces *LOCATION FIRST*: "Direction comes from the zone, never from the HTF
  bias alone", and refuses with "the MTF trigger alone is not a location fact".
  **The alert authority was right; the display was the only reader that disagreed.**
  That documented rule is what defect 1's fix aligns the display to — no new policy.
* **`LifecycleInvalidateActive()`** (`:20702`) validates the transition, blacklists the
  setup, then releases ownership (`active=false`) and deletes the trade objects. The
  `active && state==STATE_INVALIDATED` window between the two statements is already
  defended against at `:21840`, `:25217`, `:25680` and `:33783`.
* **`QSMC_ArbiterFeedAndFinalize()`** runs from `AlertDispatcherFinalize()` at `:15093`,
  i.e. after `ZRE_Update`/`RXN_Update` and behind a once-per-closed-bar guard — the
  alert path's zone snapshot is fresh and cannot double-fire.

---

## 3. Root-cause analysis of the conflicting BUY/SELL signals

The three chart messages the operator reported are produced by **two different modules
reading two different snapshots**, and neither module was required to reconcile:

```
BUY PLAN — CONDITIONAL — INVALIDATED          Directional Scenario Engine
                                              ScenarioDrawOne() -> g_scn_buy
SELL PLAN — CONDITIONAL — LATE — WAIT FOR RETEST   same engine -> g_scn_sell
TACTICAL / PREVIEW MTF BUY ENTRY PREVIEW @4038.62  UpdateMTFExecutionEntry()
                                              -> g_htf_bias + g_structures[]
```

Answers to the ten investigation questions, each with its source reference:

1. **Why can an invalidated BUY plan coexist with an MTF BUY preview?**
   Because `UpdateMTFExecutionEntry()` never read the DSE. Its third direction branch
   (`else if(g_htf_bias==1 || g_htf_bias==-1)`) picks the direction from the
   higher-timeframe bias and then walks `g_structures[]` backwards for the *most recent
   structure event of that same side*, using its price as the trigger. A BUY plan can be
   retired by `ZRE_ST_BROKEN`, by `InpZREExpireBars`, or by a closed M5 candle through
   `structural_invalidation`, and the bias-derived trigger is completely unaffected by
   any of those facts. Defect 1.

2. **Are the BUY plan and the tactical preview using different market states,
   timeframes, or timestamps?** All three.
   *state* — the DSE reads `g_zre_zones`/`g_zre_status`/RXN/Core after `ZRE_Update()`;
   the preview reads `g_htf_bias` and `g_structures[]`.
   *timeframe* — the DSE works on the chart series plus closed D1/H4/H1/M5 snapshots
   bounded by `ModelBoundary`; the preview calls `iHigh/iLow/iOpen/iClose/iTime(_Symbol,
   SelectExecutionTF(), 0|1)` straight from the terminal, where shift 0 is the **forming**
   execution bar.
   *timestamp* — `OnCalculate` runs the preview at `:15002` and `ScenarioUpdate()` at
   `:15097`, so on the first tick of a new chart bar the preview is drawn against the
   previous closed bar's scenario snapshot. That lag is one *tick*, it is strictly causal
   (no future data), and it is now documented in the source where it happens.

3. **Can an outdated scenario remain visible after its invalidation?** Yes, twice over.
   Defect 1 (the bias-only trigger has **no age bound at all** — any structure event still
   retained in `g_structures[]` re-arms a fresh-looking preview whenever price wanders
   back to it) and defect 2 (the CONFIRMED→PREVIEW re-arm dedup was dead, so a preview
   that had already confirmed could keep re-appearing forever).

4. **Does the SELL engine identify rejection, displacement and bearish structure in the
   correct order?** Yes. `ScenarioEvaluateM30M15()` requires the M30 rejection before the
   displacement, `RXN_PhaseAfterStructure()` orders liquidity → displacement → structure,
   and `ScenarioClassifyPlan()` walks `has_retest` → `has_structure` → `has_displacement`
   → `has_reaction` in that order. `ZRE_EvalRejection()` and `RXN_PtsRejection()` are
   direction-symmetric. **No defect found here.** The reported SELL message was correct:
   the plan really was LATE.

5. **Why is a setup classified as LATE?** `ScenarioMarkLate()` (`:27198`): the last
   **closed** chart price is more than `InpChaseMaxATR` (default 1.50) × the closed **H1**
   ATR beyond the zone's far edge — for a SELL, `close < zone_low - chase*ATR`. It uses
   only closed data; a PREVIEW touch never changes it. `validity_pass` requires `!p.late`,
   so a LATE plan is not a qualified candidate, and `ScenarioBuildVerdict()` maps it to
   `SCV_LATE_WAIT_RETEST`. The tactical path has its own separate chase verdict
   (`g_mtf_entry_late`, same inputs) that only affects wording and colour.

6. **Does WAIT FOR RETEST refer to a specific valid retest zone and a still-valid setup?**
   Yes for the DSE: `ScenarioM5RetestScan()` names the exact entry-zone bounds
   (`entry_zone_low/high`), the touch candle time, the reclaim candle time, the reclaim
   close, and the structural invalidation level, and it returns
   `NOT_EVALUATED(no live selected zone)` when the plan is not live. **No for the tactical
   label**: `| LATE (%.1f ATR from close) - wait for retest` named no zone and no
   invalidation level at all. Partially addressed — the label now also carries the
   authoritative reason (`| CONTEXT: …`), and the DSE card names the zone and the
   invalidation. A full "retest zone on the tactical label" is left as a next step (§9),
   because the tactical path has no zone of its own to name — that absence is exactly
   what the arbiter's LOCATION-FIRST rule already refuses to trade on.

7. **Can a bullish higher-timeframe bias incorrectly override a confirmed bearish
   execution structure?** In the *alert* path, no: `BuildTacticalCandidate` takes the
   direction from the zone role plus the closed-bar reaction fact, and the tactical hint
   "is only allowed to agree with it". In the *display* path, yes it could: the
   bias branch `continue`s past every structure event whose `bullish` flag disagrees, so
   a confirmed bearish MSS was not merely outranked — it was never looked at. Fixed by
   rule (4): a bias-only direction with no live scenario on that side is CONTEXT.

8. **Can a bearish lower-timeframe move incorrectly override an intact higher-timeframe
   structure?** No. The mirror of the above: the DSE requires full D1/H4/H1 alignment
   (`alignment_rank==3`) for `candidate_qualified`, and a weighted conflict keeps every
   candidate unqualified *by design* (`MIXED / CONFLICT`, `DECISION: STAND ASIDE`). The
   gate added here is direction-symmetric — A1 and A2 assert both mirrors.

9. **Are S/R zones classified as broken by a candle close or merely a wick?** By a
   **close**, with an ATR buffer, on the role edge only. See "checked and cleared". → A5.

10. **Are any signals repainted or derived from future bars?** No signal is. The forming
    bar is read in exactly two places, both explicitly non-authoritative and both labelled
    as such: `UpdateEarlyBreakPreview()` (`LIVE_PREVIEW`) and the `live_cross` PREVIEW arm
    of `UpdateMTFExecutionEntry()`. `closed_confirm` uses shift 1 only. The one genuine
    repaint risk found was defect 2 — a *lapsed* CONFIRMED re-arming as a PREVIEW — which
    is a re-paint of the display, not of a confirmed signal, and is now closed.

---

## 4. Files changed, and why

| file | change | why |
| --- | --- | --- |
| `nadir2.mq5` | +455 / −14 lines, 40 407 -> 40 848 lines, 14 surgical edits | defects 1-3 |
| `tools/test_tactical_authority.py` | **new**, 963 lines, 135 contracts | the regression suite for the above |
| `.github/workflows/qsmc-verify.yml` | +3 lines | a gate nobody runs is a suggestion |
| `docs/QSMC_V6.6.10_TACTICAL_AUTHORITY.md` | **new**, 643 lines, this file | the audit report |

Nothing else was touched. No header, no input, no default, no buffer, no plot, no gate
order, no gate verdict, no trade API, no other document.

### 4.1 The fourteen edits, in file order

1. `:1902` three new observability globals (`g_mtf_entry_authority`,
   `g_mtf_entry_blocked`, `g_mtf_entry_src`).
2. `:4434` `ENUM_TACTICAL_AUTHORITY { OK, CONTEXT, STALE, BLOCKED }`, placed next to the
   scenario vocabulary it reads.
3. `:5330` forward declarations for the six new symbols (the DSE section is ~22 000 lines
   below the tactical path).
4. `:5378` `ClearMTFExecutionEntry()` clears the new globals with the display they describe.
5. `:5394` direction **source** tracking (`src` 0/1/2) and the trigger's chart bar.
6. `:5424` the authoritative-state gate, called before any drawing, marking or feeding.
7. `:5491` **the restored `g_last_mtf_entry_key` write** (defect 2).
8. `:5493` publish the verdict and its reason for the panel.
9. `:5549` the CONTEXT reason on the label itself.
10. `:5556` the label verb is chosen from the verdict — `ENTRY` only when an authoritative
    module still owns a live scenario on that side; `:5565` a CONTEXT verdict paints no
    entry mark or arrow.
11. `:14343` `TacticalAuthoritySelfTest()` runs from `OnInit` next to `ScenarioMTEESelfTest()`
    and prints `Tactical-authority self-test: PASS (7/7)`.
12. `:27253-27416` the gate itself: `TacticalScenarioTerminal()`, `TacticalScenarioLive()`,
    `TacticalAuthorityName()`, the **pure** `TacticalAuthorityDecide()`, the state-gathering
    `TacticalAuthorityGate()` adapter, and the in-terminal self-test.
13. `:28492` `ScenarioDrawOne()` terminal-plan handling (defect 3).
14. `:28573` `ScenarioDraw()` expectation flags matched to the new guard; `:28712`,
    `:28875` and `:28883` the reconciliation rows on the compact and full decision cards.

---

## 5. The corrected decision pipeline and scenario lifecycle

### 5.1 The hierarchy, as it now stands

```
A  CONTEXT      D1 / H4 / H1 closed structural bias, weighted D1 50 / H4 30 / H1 20 with an
                explicit HTF-wins tie-break; D1 dealing range -> premium / discount / EQ;
                PDH/PDL/PWH/PWL.  A bias is EVIDENCE. It is never an instruction:
                `alignment_rank==3` (full D1/H4/H1 agreement) is a HARD gate for
                candidate_qualified, and a weighted conflict leaves every candidate
                unqualified by design -> `MIXED / CONFLICT`, `DECISION: STAND ASIDE`.
B  STRUCTURE &  Valid swings need N confirmed right bars (5 in the sniper engine, so an
   LIQUIDITY    unconfirmed swing is never treated as known). Buy/sell-side liquidity,
                confirmed sweeps, displacement body vs `InpCausalDisplacementBodyATR`,
                BOS / MSS / CHoCH. A break is a CLOSE beyond the role edge by more than
                break_atr*ATR; a wick is a touch.
C  SETUP        CONTEXT -> LIQUIDITY EVENT -> DISPLACEMENT -> STRUCTURE CONFIRMATION ->
                OB/FVG RETEST -> EXECUTION CONFIRMATION, mapped onto the existing engines
                rather than duplicated: RXN supplies the phase order
                (`RXN_PhaseAfterStructure`), ZRE supplies the zone and its role, the DSE
                mirrors the chain legs. An OB or FVG alone is never sufficient:
                `candidate_qualified` additionally requires location, closed-M5 geometry,
                M5 data and M5 invalidation history reaching the zone's proven origin.
D  EXECUTION    M5 two-candle retest (touch, then a LATER close beyond the protected edge;
                a candle can never confirm its own retest) and only Core may say
                EXECUTION_READY — the DSE mirrors that flag, it never sets it.
E  PLAN         Entry tied to the zone's protected edge, SL at the structural invalidation,
                TP1 at the first opposing barrier, `expected_r` net of the M5 spread.
                When the gates are not satisfied the output is
                NO_QUALIFIED_CANDIDATE / WAIT / STAND ASIDE — never an invented price.
```

Continuation, pullback and reversal are distinguished by `scenario_type`
(`D1/H4 ALIGNED BUY|SELL`, `D1/H4 CONFLICT (weighted …)`, `COUNTERTREND WATCH`,
`DIRECTIONAL CONTEXT UNAVAILABLE`). A countertrend plan stays visible and is labelled as
what it is; it never qualifies.

### 5.2 The lifecycle, and who owns each state

Two state machines already exist and were **left alone** — they were not the defect:

* **Core** (`ENUM_SIGNAL_STATE`): `WATCH → ARMED → [PREVIEW] → CONFIRMATION_PENDING →
  CONFIRMED → TARGET_1/2/3_REACHED → COMPLETED`, or `INVALIDATED / EXPIRED / NO_TRADE`.
  Every transition goes through `TryTransitionSignalState()`, which rejects out-of-order
  bars, refuses to rewind a confirmed setup to ARMED, refuses to replace an active owner,
  and validates the legality matrix `IsLegalSignalStateTransition()`. Terminal states can
  only be left for `WATCH`/`ARMED`/`NO_TRADE`, i.e. a **new** setup with a **new**
  `setup_event_id` — a scenario is never revived in place.
* **DSE** (`ENUM_SCENARIO_STATE`): `UNAVAILABLE → WATCHING_ZONE → ZONE_APPROACHING →
  TOUCHED_PREVIEW → REACTION_CONFIRMED → DISPLACEMENT_CONFIRMED → STRUCTURE_CONFIRMED →
  WAITING_FOR_RETEST → RETEST_CONFIRMED`, with `EXECUTION_READY` mirrored from Core only,
  and `LATE_WAIT_FOR_RETEST / INVALIDATED / EXPIRED / COMPLETED / COUNTERTREND_WATCH` as
  the non-actionable states. This maps onto the requested
  `IDLE → WATCH → CANDIDATE → CONFIRMED → WAIT_RETEST → READY` plus terminals, so no new
  machine was introduced.

**What was missing was the third participant.** The tactical preview had no state at all —
it was a per-tick recomputation from a bias flag and a structure list. It now has a
single authoritative verdict with an explicit total order, and it is the *only* place the
tactical display can get one:

```
                       TacticalAuthorityDecide()   (PURE — reads no global)
                                     │
   ┌─────────────────────────────────┼──────────────────────────────────────┐
   │ (1) DSE holds a TERMINAL plan for this side                             │
   │     (invalidated | plan_dead | SCN_INVALIDATED | SCN_EXPIRED)           │
   │                                                     -> BLOCKED          │
   │ (2) the Core lifecycle blacklisted this SAME side+level idea and the    │
   │     retirement is inside InpBlacklistExpiryBars      -> BLOCKED          │
   │     (the veto CalculateAITradeSetup already applies, at :20110)          │
   │ (3) a bias-only trigger older than InpRetestTimeoutBars closed chart bars│
   │                                                          -> STALE       │
   │ (4) the direction came from the HTF bias alone (src==2) and the DSE has │
   │     no CURRENT plan on that side                     -> CONTEXT         │
   │ otherwise                                              -> OK            │
   └─────────────────────────────────────────────────────────────────────────┘
        BLOCKED / STALE : display cleared, NO entry mark, and the fact is NOT
                          handed to the arbiter. Reason kept for the panel.
        CONTEXT         : the level line stays, the word becomes CONTEXT, no entry
                          mark is painted, and the arbiter STILL receives the fact so
                          its own explained refusal ("the MTF trigger alone is not a
                          location fact") is unchanged.
        OK              : unchanged behaviour.
```

Mandatory behaviour from the brief, and where it is now enforced:

| requirement | enforcement |
| --- | --- |
| an invalidated setup cannot remain eligible for execution | rule (1) + `validity_pass` requiring `!invalidated && !plan_dead`; `ScenarioEntryStatusToken` puts `INVALIDATED` ahead of every later status |
| a stale preview cannot override an invalidated authoritative scenario | rule (1) returns before `DrawTextLabel`, `EntryMarkTactical` and `TacticalObserve` (asserted by source-order contracts B2) |
| a new setup must have its own identity and evidence | `GenerateSetupId()` + `BlacklistSetup()` + `TryTransitionSignalState`'s owner check; unchanged |
| a scenario must not be revived because price returns to the same zone | rule (3): the bias-only trigger is aged out against `InpRetestTimeoutBars` |
| revalidation requires fresh, documented conditions | `ScenarioMarkRelevant()`'s Priority-A set (live, correctly sided, fresh, unchased, inside the closed-H1 horizon) is what `dse_live` reads — the gate does not re-derive it |
| BUY and SELL may coexist, but the card must separate hypotheses from the selection | `ScenarioDashCompact/Full` print BOTH plans and then `PREFERRED SCENARIO` + the single deciding criterion from `ScenarioPlanLeadKey()`; the new `TACTICAL:` row states the third participant's verdict |
| READY means every mandatory condition is satisfied | `execution_ready` is written only by `ScenarioApplyCoreReady()` |
| WAIT_RETEST names the zone and the invalidation | `retest_low/high`, `entry_zone_low/high`, `structural_invalidation`, `retest_note`, and the tooltip's `Stop:` line |
| a LATE setup is not a fresh entry | `validity_pass` requires `!late`; the tactical label for a LATE side now says CONTEXT quoting `LATE - WAIT FOR RETEST` |
| transitions are deterministic and testable | `TacticalAuthorityDecide()` is pure, mirrored 1:1 in Python (A-part) and in MQL5 (`TAC-1…TAC-7`), and A11 asserts idempotence |

### 5.3 Ranking: hard gates stay hard

The separation the brief asks for already existed and was verified rather than rewritten.
`ScenarioPlanBetter()` compares `validity_pass` **before** `alignment_rank` **before**
`rank_score`, and `candidate_qualified` is a conjunction, so a raw score cannot bypass a
failed gate (A7 proves it with `rank_score=100` losing to `rank_score=1`).
`CZoneScorer` keeps hard validity gates separate from a soft 0-100 context rank, and
reaction evidence (65%) and zone context (35%) are scored from disjoint features so a wick,
a sweep and a displacement are not counted twice. Every displayed score is labelled
"evidence quality, not a probability" in the source and on the card, and
`test_quant_stats.py` / `test_zone_scoring.py` / `test_early_break.py` pin that wording.
No probability is claimed anywhere, so nothing needed calibrating.

---

## 6. Tests executed, and exact results

All of this ran in the repository, in this environment, with no terminal.

```
$ python3 -m py_compile tools/*.py                                   OK
$ python3 tools/mql5_rules.py --quiet
  no dialect errors, 0 warning(s) - now press F7 in MetaEditor
$ python3 tools/static_check.py
  no errors, 5 warning(s)          [the 5 pre-existing new/delete balance notes]
$ python3 tools/check_release_gate.py
  GO (with 0 warning(s)) - mechanical invariants hold.
$ python3 tools/check_scenario_geometry.py
  RESULT: all geometry checks passed
$ python3 tools/apply_qsmc_arb_patch.py --check
  already patched (marker present) - nothing to do
```

| suite | result |
| --- | --- |
| `test_arbiter.py` | 27 passed, 0 failed |
| `test_autotrader_contract.py` | passed |
| `test_dashboard_clarity.py` | passed |
| `test_diag_bridge.py` | passed |
| `test_early_break.py` | passed |
| `test_edgebook_contract.py` | passed |
| `test_gate_profile.py` | passed |
| `test_historical_atr_contract.py` | passed |
| `test_quant_stats.py` | passed |
| `test_scanners.py` | passed |
| `test_structure.py` | passed |
| **`test_tactical_authority.py` (new)** | **135 contracts, 0 failed** |
| `test_zone_scoring.py` | passed |
| `test_zre_signal_role.py` | all role/direction contracts hold |

Every suite was run **before** the first edit as well: the baseline was fully green, so
nothing below is a repair of a pre-existing failure.

### 6.1 Coverage of the sixteen required regression cases

| # | case | where |
| --- | --- | --- |
| 1 | bullish HTF context + bearish LTF rejection | **A1** (+ `test_structure.py` MIXED) |
| 2 | bearish HTF context + bullish LTF recovery | **A2** (symmetric, both mirrors) |
| 3 | liquidity sweep without displacement | `test_arbiter.py` evidence-mask gates; `QSMC_Selftest.mqh` T5/T12 |
| 4 | displacement without confirmed structure break | `RXN_PhaseAfterStructure` via `test_arbiter.py`; `CArbSelfTest::T12` |
| 5 | structure break without valid retest | **A6** (`SCN_WAITING_FOR_RETEST`), `ScenarioMTEESelfTest` MTEE-5 |
| 6 | valid retest with a failed execution trigger | `ScenarioMTEESelfTest` MTEE-5 ("conditional retest is not Core authorization") |
| 7 | BUY invalidated while an old BUY preview is cached | **A3 + A12 + B1-B5** — the reported defect |
| 8 | SELL marked LATE after the entry window passed | **A4** (+ MTEE-6 precedence) |
| 9 | support wick penetration, no close-based invalidation | **A5** (both sides) |
| 10 | confirmed support break and failed retest | **A6** (role reversal + terminal plan) |
| 11 | competing BUY and SELL candidates | **A7** (+ `ScenarioPlanLeadKey`) |
| 12 | missing / insufficient timeframe history | **A8** (+ MTEE-7) |
| 13 | MTF candle timestamp misalignment | **A9** |
| 14 | signal expiration and fresh setup creation | **A10** (staleness + bounded blacklist + EXPIRED) |
| 15 | zero-lookahead historical replay | **A11** + B6 purity + B10 ordering; `test_historical_atr_contract.py`; `RunRuntimeDisplayNoLookaheadAudit()` at runtime |
| 16 | spread or risk/reward gate failure | `test_gate_profile.py`, `test_zone_scoring.py`, `CRoomGate`/`CVolatilityGate` in `test_arbiter.py` |

Cases 3, 4, 6 and 16 are deliberately **not** re-implemented here: they are already
covered by an independent reference implementation, and a second transcription would be a
second thing to drift.

### 6.2 What the tests verify

Per the brief, they assert **states and reasons**, not "a non-empty result": every A-part
case checks the returned verdict *and* the reason string (that it names `INVALIDATED`,
that it carries the `4044.00` invalidation level, that it quotes the DSE's own
`LATE - WAIT FOR RETEST` rather than inventing "no scenario"). The B-part checks ordering
in the source: the gate must be called **before** `TacticalObserve`, **before**
`DrawTextLabel`, and **before** `EntryMarkTactical` — a correct rule wired in after the
drawing would be indistinguishable from no rule at all.

### 6.3 Untested cases (honest list)

* **No compilation.** MetaEditor does not exist here.
* **No market data.** No symbol, no broker history, no tick replay. The 4038/4046/4063/4075
  prices from the report were used as *investigation clues only* — they appear in this
  document and in test fixtures, never in strategy logic. No historical price was
  hardcoded into any decision path.
* **No chart.** The reconciliation rows, the RETIRED PLAN tooltip and the CONTEXT label
  wording have not been seen rendered.
* `TacticalScenarioTerminal`/`TacticalScenarioLive` read real DSE globals; only the pure
  order they feed is unit-tested. Their field selection is pinned by source contracts B7.
* The interaction with `InpUseMTFExecutionEntry=false`, `InpUseHTFBias=false` and
  `InpArbEnabled=false` is reasoned about in the code but not executed.

---

## 7. Before / after on reproducible examples

### 7.1 The reported chart

State: D1/H4 bullish bias; a BUY zone broken on a closed bar; the SELL side chased.

| | before | after |
| --- | --- | --- |
| DSE BUY tag | `BUY PLAN — CONDITIONAL — INVALIDATED` over a **tinted conditional retest box** | `BUY PLAN — INVALIDATED — NOT AN ENTRY` over a **dark-gray RETIRED PLAN** box; tooltip says retired, not "a plan to monitor" |
| DSE SELL tag | `SELL PLAN — CONDITIONAL — LATE - WAIT FOR RETEST` | unchanged |
| tactical label | `TACTICAL / PREVIEW MTF BUY ENTRY PREVIEW @ 4038.62 \| exec M5 \| grade C` | **absent.** Nothing drawn, no HLINE, no arrow, no mark, and no fact handed to the arbiter |
| card | BUY INVALIDATED, SELL LATE, and a BUY entry preview — three voices, no reconciliation | `TACTICAL: BLOCKED - the DSE BUY scenario is INVALIDATED (closed M5 candle … below BUY structural invalidation 4044.00) - a retired scenario keeps no preview` |
| verdict | `LATE - WAIT FOR RETEST` (correct) | unchanged |

### 7.2 Bias-only preview with no scenario on that side

| | before | after |
| --- | --- | --- |
| label | `TACTICAL / PREVIEW MTF BUY ENTRY PREVIEW @ …` | `TACTICAL / PREVIEW MTF BUY CONTEXT PREVIEW @ … \| CONTEXT: no DSE BUY scenario - the direction came from the HTF bias alone, which is context, not an entry` |
| entry mark | hollow diamond painted on the bar | not painted (the level line stays) |
| arbiter | received the fact, refused it, explained "the MTF trigger alone is not a location fact" | **identical** — the fact is still fed, so the explanation is preserved |

### 7.3 Ancient trigger, price returns to it

A bullish structure event 180 chart bars back, `InpRetestTimeoutBars=40`, HTF bias still
bullish, price drifts back to the level.

| | before | after |
| --- | --- | --- |
| display | a fresh-looking `MTF BUY ENTRY PREVIEW` at the old level | nothing; `TACTICAL: SUPPRESSED - STALE - the BUY trigger is 180 closed chart bars old (limit InpRetestTimeoutBars 40) - returning to an old level is not a fresh entry` |

### 7.4 CONFIRMED, then the condition lapses and re-arms

| | before | after |
| --- | --- | --- |
| bar N | `TACTICAL-INFO (exec bar closed) MTF BUY ENTRY CONFIRMED @ …` | identical |
| bar N+k, same trigger, live cross only | `TACTICAL / PREVIEW MTF BUY ENTRY PREVIEW @ …` **again** — the dedup key was permanently `""` | suppressed by the restored guard, and `g_mtf_sig_time` is no longer re-anchored on every tick |

### 7.5 What did **not** change

A Core-owned setup (`src==1`) and an early-break live preview (`src==0`) are never
downgraded to CONTEXT and never aged out by rule (3). A side with a **current** DSE plan
keeps the exact wording, colour, arrow and mark it had before. No alert that used to fire
now fires with different content: rules (1) and (3) suppress a fact the arbiter would
almost certainly have refused anyway (it has no zone behind it), and rule (4) leaves the
feed untouched on purpose so the arbiter's own explanation survives.

---

## 8. Compilation and runtime verification status

**NOT COMPILED. NOT RUN ON A CHART.** This is stated plainly rather than implied:

* There is no MetaEditor and no MetaTrader 5 terminal in this environment, and no
  compiler evidence was fabricated.
* What *was* verified mechanically: MQL5 dialect rules D1-D16 clean (this is the rule set
  anchored to the exact errors that broke the v6.6.0 build — no reference returns, no
  integer suffixes, no `->`, no pointers to structs, no comma-chains, no invented
  builtins, no unbraced declarations, `StringFormat` specifiers matched to arguments);
  brace/paren balance; include resolution; struct-member existence; the release gate;
  the scenario-geometry arithmetic; and byte-exact CRLF preservation
  (`nadir2.mq5`: 1 862 910 bytes, 40 848 LF, 40 848 CRLF, **0 bare LF**, as
  `.gitattributes` requires).
* **To finish the verification:** open `nadir2.mq5` in MetaEditor, press **F7**, then
  attach it to a demo chart and confirm the init journal contains
  `[QSMC_ARB] v6.6.9 arbitration layer ON | …` **and** the new line
  `>>> v6.6.9 Tactical-authority self-test: PASS (7/7)`. A `FAIL - TAC-n` there names the
  group that broke. Then review one live session on a demo chart before trusting any of it.

The new code was written to the dialect rules deliberately: `TacticalScenarioTerminal`/
`TacticalScenarioLive` use mirrored halves instead of a struct pointer (D12 forbids
pointers to structs), `TacticalAuthorityDecide` returns an enum by value (D1), every
`if` body that declares a variable is braced (D18), and the one `StringFormat` that
changed gained exactly one `%s` and exactly one argument (D7 — pinned by contract B4).

---

## 9. Remaining limitations and prioritised next steps

1. **Compile it.** F7, then the two init-journal lines in §8. Nothing else matters until
   this is done.
2. **Resolve the version drift (defect 4).** Decide whether `v6.6.10` becomes the release
   triple. If it does, five places must move together or `check_release_gate.py` G1 fails:
   `#property version`, `QSMC_VERSION_TEXT`, the `[QSMC_ARB] vX.Y.Z arbitration layer ON`
   banner in `QSMC_Root.mqh`, the `# QSMC vX.Y.Z` title in `docs/QSMC_BUILD_AND_RUN.md`,
   and the CI `Manual gate` echo. Consider adding a G1 sub-check that no in-code marker
   claims a version ahead of `QSMC_VERSION_TEXT`, so this cannot drift again.
3. **Give the tactical label a real retest zone.** It can currently only say "wait for
   retest" because the tactical path owns no zone. The honest fix is not to invent one:
   either drop the phrase, or have the label name the DSE lead's `entry_zone_low/high` and
   `structural_invalidation` when the DSE has a plan on that side. Both are display-only
   changes; the second is more useful and needs its own contract test.
4. **Fix the RXN recovered-zone role gap** already documented in
   `docs/KLJ_V6.6.9_ONE_ZONE_ROLE.md` §6: zones in `g_rxn_extra_zones` have no
   `g_zre_status` row, so `RXN_EvalZone()` still resolves their **birth** role. Pre-existing,
   not introduced here, and it needs its own test because giving them a status row changes
   the RXN funnel.
5. **The `room` score conservatism** from the same document: `ZRE_TryBuildSignal()` compares
   the traded side against other zones' *birth* side. Score only; it cannot flip a direction.
6. **One-tick display lag at bar open** (§3, question 2). Removing it would mean calling
   the tactical path twice per bar, which would leave a second `TacticalObserve` fact in
   `m_tac[]` after `FinalizeBar` drained it — a real latency bug. Documented instead of
   "fixed". Revisit only if the DSE is ever moved above `UpdateMTFExecutionEntry()`.
7. **Three dead globals.** `g_last_mtf_entry_id`, `g_mtf_last_confirm_bar` and
   `g_last_mtf_preview_bar` have no readers and no writers left after the v6.6.0 patch.
   Left in place deliberately (removing declarations is the kind of unrelated churn this
   pass avoids), but they should be deleted or re-purposed in a cleanup pass — a global
   with no writer is how defect 2 hid.
8. **`MTF_SniperEvaluateTouchesAndBreaches()` grades a touch with up to 5 following
   bars.** That is legitimate for an as-of-now zone-strength grade over a closed-bar
   snapshot, and it is not a per-bar signal, but it means the strength of the *most recent*
   touches is computed from a truncated window. Worth an explicit note in
   `docs/QSMC_ZONE_SCORER.md`.
9. **No probability is published anywhere**, so nothing needs calibrating — keep it that
   way. If a calibrated probability is ever wanted it needs out-of-sample broker data this
   repository does not have, and `CEdgeBook` is the only place with the outcome ledger to
   build it from.

---

## 10. Git references

* Branch: `arena/d4369e1f-terad` (from `main` @ `70dea7af0ddd007ebe94503cb4897af376694c6c`)
* Commits: see `git log` on that branch — one commit for the source repair, one for the
  test + CI + this report, so the behaviour change and its proof can be reverted
  independently.
* No pull request was opened and nothing was merged or closed; that decision is the
  repository owner's.

---

*This document records a static audit and an offline contract suite. It is not a backtest,
it contains no win rate, and no score in this system is a probability of success. Fewer,
clearer, causally valid scenarios — and WAIT when the evidence is insufficient — is the
design goal; nothing here claims to predict a market move.*
