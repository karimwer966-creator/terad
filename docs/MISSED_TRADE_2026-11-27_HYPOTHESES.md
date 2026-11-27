# Missed trade 2026-11-27 (XAUUSD M15, Asia) — hypotheses verified in code

**Build investigated:** v6.6.24 at `4bba08e` (all line numbers below are in that commit).
**Fix release:** v6.6.25 on branch `arena/b7726771-terad` (Arena fixes the branch name; the
requested `fix/structure-rearm-continuation` could not be used).
**Method:** code reading only. MetaEditor (F7), the Strategy Tester and the broker's bar
history were **not available** here, so nothing below is a replay of the real 2026-11-27 bars.

## 1. The incident in one paragraph

Price ranged 3562–3570, then rallied vertically to ~3684 (+114 points, ~10R). Five tactical
BUY alerts fired near 3570 (zone 3561–3577, score 50–57, evidence 2–3/6, RR 1.20–1.50); none
became a CORE signal. The overlay showed `STRUCT none`, `CHAIN SWP- > DISP-`, *"no causally valid structure
anchor"*, CORE WAIT / NO_SETUP; the GateAudit top blocker was *"chain: structure event
missing/invalidated in the graph"*; top-down WAIT; the AutoTrader processed 0 / sent 0.

## 2. Verdicts

| # | Hypothesis | Where (v6.6.24) | Verdict | Evidence |
|---|---|---|---|---|
| H1 | After a break the swing reference is zeroed and only a new N=3 fractal re-arms it | `nadir2.mq5` `DetectStructure` L24571; zeroing L24652 (`g_struct_last_high=0.0; // consumed; next confirmed fractal re-arms`); re-arm only via fractal registration L24605 | **CONFIRMED** | A fractal at `f` needs `n` closed bars right of it with strictly lower highs. A vertical leg prints none, so after the first break no later close can be a BOS. `STRUCT … bull` lines print only with `InpLogLifecycleTransitions=true` (L1394, default `false`), so their absence in the journal is not evidence either way. The panel's `SWING SH 3586.49 (H1)` is `GroupedDashSwingText` (L33528) reading the PMI H1 swing list, not the structure state. |
| H2 | The chain needs a confirmed same-side sweep ≤ `InpSweepToStructureMaxBars` (8) bars before the break, available before the displacement candle — reversal-only | `BuildCausalEventGraph` L17392: age window L17466, availability L17473, structure added **invalidated** when no sweep qualifies L17509; `ResolveCausalPath` L18255 rejects it at L18268; `CalculateAITradeSetup` L21634 *"no causally valid structure anchor"*; `DetectOrderBlocks` skips sweep-less breaks L24748; invariants demand pool→sweep ancestry (L17924) | **CONFIRMED** | Exactly the GateAudit top blocker and the overlay text. Corroborated by the panel (`SWEEP none`, *"EVENTS WAITING FOR SWEEP"*, L11137). `TopDown_Sequence15` (L34619) also requires a sweep, so the top-down M15 step is reversal-only too. |
| H3a | `InpTopDownHardGateForWeak` vetoes WEAK signals | `QSMC_ClassifySignal` L19957 (switch L1999, default `true`) | **PARTIAL** | The veto is real and fires on any top-down WAIT, but WEAK exists only with `PERMISSIVE` + `InpAllowWeakSignals=true` (L1987, default `false`). With the shipped defaults it was not the operative gate. |
| H3b | `InpTopDownMinRR`=2.0 conflicts with a nearest-barrier TP1 | `TopDown_Evaluate` L34718; nearest of {M15 swing liquidity, H1 VAH/VAL, H1 POC, H1 dealing extreme, PDH/PDL} (L34889–34903) and the floor (L34905–34913), message L34912 | **CONFIRMED (for top-down only)** | TP1 is the *nearest* candidate; if it pays < 2.0 the whole chain fails with *"R:R x below required 2.00 (nearest target …)"* → WAIT. That WAIT does **not** veto CORE by default (`TopDown_VetoesDirection` L35020 needs `InpRequireInstitutionalConfirm=true`; `TopDown_GatingModeLine` L35049 reports *GRADE ONLY*). |
| H3c | CORE TP1 conflicts with the RR floor | `FindInstitutionalTarget` L18958 | **REFUTED** | CORE already skips candidates below `g_cfgMinRR1` (1.5) and falls back to ATR 1.5/2.5/4.0 capped at the opposing barrier. |
| H3d | `InpRMUseRRFloor` blocks signals | L1021; only consumer `RM_Verdict` call L28451 | **REFUTED** | `g_rm_*` state is read only by a lifecycle log line and a dashboard tooltip (L33978). It never gates CORE. |
| H4 | Cold-start `ADX_H1` not ready blocks silently | `MTF_SniperCopyBufferBounded` L43767 prints *"[SniperDataHealth] … not ready (BarsCalculated -1 < 5)"* (L43796); `MTF_SniperZone_Update` L45324 → `DATA_INCOMPLETE reason=H1_ADX` (L45410) and retries | **PARTIAL** | It is logged, not silent, and it blocks only the Sniper engine. CORE never reads `g_sniper_data_ready`, but the quality class still says `NO_SETUP` (L23683) while the data is warming up, which hides the real state. |
| H5a | AutoTrader `TIMEFRAME PIN REFUSED` | `QSMC_AutoTrader.mq5` `InpPinTimeframeMinutes`=15 (L364); `OnInit` refusal L4501–4505 → `INIT_PARAMETERS_INCORRECT` | **CONFIRMED** | MT5 removes an EA whose `OnInit` fails, so after a switch to M5/H4 the chart has **no** EA, even after switching back. `OnTick`/`OnTimer` return silently on a mismatch. |
| H5b | QSMC magic 53000001 re-initialised 83× (reason=3), `mode=ANALYSIS`, `APP: stopped`, `QSMC CLOCK offset=120` | — | **NOT ATTRIBUTABLE** | A repository-wide search finds no producer of magic 53000001, `TRADE_EVENT`, `APP: stopped`, `QSMC CLOCK` or `mode=ANALYSIS`. This repo's EAs use 20261027 (`QSMC_AutoTrader.mq5` L270) and 20261125 (`QSMC_ConfirmationEngine.mq5` L41). reason=3 is `REASON_CHARTCHANGE`. |
| H5c | `TRADE_EVENT` deals 02:05–05:17, 11:34/11:55 (retcode 10009) | — | **NOT ATTRIBUTABLE** | Same as H5b; direction and owner cannot be recovered from those lines. v6.6.25 adds an attributable alternative (F(c)). |
| — | Tactical alerts never become signals | `QSMC_Arbiter.mqh` L303–312 (R7 source cap) | **BY DESIGN** | `SRC_TACTICAL` is capped at TACTICAL-INFO. Its TP1 is entry + risk × min_rr capped at the nearest opposing zone, which is why RR was 1.20–1.50. |

## 3. Most likely failure chain (needs the bars to confirm)

1. The first close above the range high creates a BOS/CHoCH/MSS, but no same-side sweep of
   the range lows qualified within 8 bars before the displacement → the structure event is
   added invalidated (H2) → *no causally valid structure anchor*.
2. That break zeroed `g_struct_last_high`; the vertical leg printed no new fractal → no further
   break for the rest of the rally (H1), so no later anchor could exist either.
3. Top-down stayed WAIT (M15 step needs a sweep; nearest target paid < 2.0 — H3b). Not a CORE
   veto by default, but it is what the panel showed.
4. Tactical alerts are informational by design. The AutoTrader saw no published CORE signal;
   if the chart had been switched off M15 it had also been removed (H5a).

**What is needed to prove it:** XAUUSD M1/M5/M15/H1/H4/D1 history from ICMarketsSC-Demo for
2026-11-24 → 2026-11-27 (warm-up), replayed in the Strategy Tester (visual, every tick based on
real ticks) with `InpLogLifecycleTransitions=true` and `InpLogCompactBarLine=true`, once with
all v6.6.25 switches OFF and once per switch. Without those bars nobody can state whether the
entry near 3570 now produces a BUY.

## 4. What v6.6.25 changes (every switch defaults OFF)

| Fix | Switch(es) | Effect when ON |
|---|---|---|
| B | `InpRearmStructureAfterBreak`, `InpRearmStructureBars`=5 | K closed bars after a break, the consumed reference becomes the extreme of exactly bars B+1..B+K (provisional); a confirmed fractal replaces it. Classification unchanged. |
| C | `InpAllowContinuationChain`, `InpSweepToStructureMaxBarsContinuation`=12 | A with-trend BOS with **no** qualifying sweep may form a CONTINUATION chain: leg origin in [BOS−12, BOS−2], net leg move **and** one impulse body ≥ `InpDisplacementATR` × ATR (0.90; the reversal leg asks only 0.35 × ATR of body, `InpCausalDisplacementBodyATR`), unmitigated OB / unfilled FVG bound to that impulse, H1 closed-structure bias **as of the BOS close** agrees. Tagged `CONTINUATION` in `[CONTINUATION]` log lines, a `[GateAudit]` line, the dashboard path, the SigLog CSV (`causal_chain=P(CONTINUATION)`) and buffer 26 (0 none/OFF, 1 REVERSAL, 2 CONTINUATION). SL goes beyond the zone (there is no sweep). |
| D | `InpTargetLiquidityAware` | Top-down TP1 = nearest liquidity pool / swing / half-ATR15 multiple (≤ 8) that **pays** `InpTopDownMinRR`; skipped levels are named. WEAK only with H1 bias agreeing AND Asia/London AND RR1 ≥ `InpWeakSignalMinRR`; each failed condition is named. No RR floor is lowered. |
| E | `InpWarmupWaitHTFData` | While the Sniper HTF buffers are not DATA_READY, CORE evaluation is deferred, logged `[WARMUP]`, quality class `WARMUP`; the same closed bar is re-evaluated once ready. |
| F | `InpPinIdleOnMismatch`, `InpKeepStateOnChartChange`, `InpLogTradeEvents` (AutoTrader) | (a) stay attached but idle on a non-pinned TF with one 300-s rate-limited warning naming the required TF; (b) keep seen-keys/ladder memory on deinit reason 3; (c) one `TRADE_EVENT` line per account deal (any magic) and per own request with BUY/SELL, symbol, volume, price, SL, TP, comment, magic, owner, retcode. |
| G | `InpLogCompactBarLine` | One `[BAR]` line per closed bar: structure refs (FRACTAL/PROV/consumed) + last break, chain hops + kind, top-down verdict, RR1, first failing gate, funnel leader. |

**Flags-OFF identity.** Every new path is behind its switch; the reversal path keeps its exact
expressions (e.g. `leg_bar` equals the sweep bar whenever a sweep exists); new state is reset
on full passes and folded into the causal fingerprint only while ON; buffers 0–25, the CSV and
the journal are unchanged while OFF; buffer 26 stays all-zero. The input-fingerprint manifest
changes because seven inputs were added (its value is an identity of the input set, not a
signal). `tools/test_missed_trade_fixes_native.py` proves `DetectStructure` OFF ≡ the frozen
v6.6.24 body bar by bar (structures, state, log text) and ON incremental ≡ full rebuild; this is
host C++, **not** MetaEditor.

## 5. Strategy Tester plan (not run here)

| Setting | Value |
|---|---|
| Expert | `QSMC_AutoTrader` (pinned M15), `InpIndicatorName` = the indicator build under test |
| Symbol / period | XAUUSD, M15 |
| Range | 2026-08-31 → 2026-11-27 (≈ 64 trading days; ≥ 60 required) |
| Model | Every tick based on real ticks |
| Deposit / leverage | the demo account's own values — identical across all runs |
| Execution | default AutoTrader risk (`InpRiskPercent`, daily-loss, DD halt, spread/slippage, max positions, consecutive-loss breaker, news — all unchanged) |

Because the AutoTrader reads `nadir2` with its **compiled defaults** (`InpPinIndicatorDefaults`),
each variant is a copy of `nadir2.mq5` compiled under its own name with the switch defaults
edited, selected through `InpIndicatorName`:

| Run | Indicator build | Switches ON |
|---|---|---|
| R0 | `nadir2` | none (baseline = v6.6.24 behaviour) |
| R1 | `nadir2_B` | B |
| R2 | `nadir2_C` | C |
| R3 | `nadir2_BC` | B + C |
| R4 | `nadir2_BCD` | B + C + D |
| R5 | `nadir2_BCDE` | B + C + D + E (+ G for the log) |

Compare per run: CORE signals published (and per week), trades, win rate, profit factor, max
equity DD (money and %), average realised R, expectancy, and the REVERSAL/CONTINUATION split
(buffer 26 or the CSV tag). **Reject** a switch if, against R0, max DD grows by more than 20 %,
PF drops by more than 0.10, or published signals more than double (flood). Then replay
2026-11-25 → 2026-11-27 in visual mode with R5 and read the `[BAR]` / `[CONTINUATION]` lines
around the 3570 area: only that replay can say whether a BUY appears and with which tag
(REVERSAL or CONTINUATION). No numbers are reported here because none were measured.

## 6. Risks

- C trades with the trend without a liquidity event: expect more signals and a lower hit rate
  per signal than the reversal chain; that is what the R2/R3 comparison must measure.
- B adds structure events on every K-bar extension of a trend; with C ON that can create
  several anchors in one leg (proximity, location and the retest lifecycle still apply).
- D can choose a farther target past nearer liquidity; the skipped levels are logged.
- The H1 bias for C/D is `H1StructureBiasAsOf(boundary)` → `ComputeClosedStructureBias(PERIOD_H1, …,
  boundary)` (closed H1 bars only, as of the decision boundary); if H1 history is not loaded it
  returns neutral and the chain / WEAK signal is refused with the reason logged.
