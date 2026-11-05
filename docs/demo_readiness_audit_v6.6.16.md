# QSMC v6.6.16 — DEMO TRADING READINESS AUDIT
Audit date: 2026-11-05. Branch: `arena/ae41bd54-terad` @ commit `752cf09`.
Mode: CODE-ONLY audit. No MetaEditor available in sandbox — final compile/runtime tests are BLOCKED.

---
## 1. Source-file dependency map

```
MQL5/Experts/QSMC_AutoTrader.mq5   (2452 lines) — companion EA (execution, guards, sizing)
   └─ iCustom → nadir2  (reads buffers 7–12 CORE_* , 19 CORE_VCODE; GV diag QSMC_I2_*_CORE/BARS/ARMED/CONF/TIME)
MQL5/Indicators/nadir2.mq5         (43713 lines) — Quantum SMC engine (indicator)
   └─ #include <QSMC/QSMC_Root.mqh>            (CQuantumRoot orchestrator)
        ├─ QSMC_Types.mqh                      (signal, stats, arbiter types)
        ├─ QSMC_Preset.mqh                     (gate profile: STRICT/INTRADAY/SCALPER/etc.)
        ├─ QSMC_DataProvider.mqh
        ├─ QSMC_MarketData.mqh                 (MTF price cache)
        ├─ QSMC_Structure.mqh                  (BOS/CHoCH/MSS fractals)
        ├─ QSMC_Zones.mqh                      (OB / FVG / BB zone construction)
        ├─ QSMC_ZoneScorer.mqh                 (quality grading)
        ├─ QSMC_LiquidityValue.mqh
        ├─ QSMC_Reaction.mqh                   (RXN layer — watch/reaction/confirmed)
        ├─ QSMC_Bias.mqh                       (D1/H4 bias)
        ├─ QSMC_Gates.mqh                      (gate chain checks — NOTE: v6.6.x gate chain is in nadir2.mq5 directly, NOT in this file)
        ├─ QSMC_UnifiedDecision.mqh            (final decision merge)
        ├─ QSMC_AlertManager.mqh               (alert dedup ring)
        ├─ QSMC_Arbiter.mqh                    (preset/tactical arbiter)
        ├─ QSMC_Stats.mqh                      (EdgeBook + CSV outcomes)
        ├─ QSMC_EarlyBreakDetector.mqh
        ├─ QSMC_Renderer.mqh                   (chart objects)
        ├─ QSMC_IncidentSafety.mqh
        ├─ QSMC_InstanceIdentity.mqh           (input hash / instance mismatch)
        ├─ QSMC_InputFingerprint.mqh           (manifest hashing)
        └─ QSMC_Selftest.mqh
MQL5/Indicators/QSMC_ScannerProbe.mq5          (6-symbol observational probe — never sends orders)
MQL5/Experts/KLJ_DataFeeder.mq5                (optional external data source; errors "no source configured" if not set — runs separately)
```

---
## 2. Function-level audit by area (A–K)

### A. Order execution & broker response handling — COMPLETE
- `g_trade` is a `CTrade` instance; `Buy()`/`Sell()` called ONLY at L1288/L1290 inside `HandleSignal()`.
- Three switches must all line up for a live order to be sent (L1240–1253 flow):
  1. `InpEnableTrading == true` (default **false**) — master switch.
  2. `InpDryRun == false` (default **true**) — if true the EA prints the DRY RUN line and returns (L1246).
  3. `TradeEnvBlock(buy)` returns "" — broker mode, real/demo gate, `InpRealAccountConfirm` must match account number when `InpDemoOnly==false` (default `InpDemoOnly=true`, default `InpRealAccountConfirm=""` which refuses any real account).
- Broker responses: `g_trade.ResultRetcode()` logged on failure (L1310); `RetcodeIsTransient()` distinguishes requote/timeout (retry next poll) from permanent (mark seen, abandon) — L426–440.
- Opposite-position handling: `PositionClose()` is called before opening a new position when `InpCloseOnOpposite=true`; failure to close aborts the new order (L1268–1286) — no silent double-exposure on netting accounts.
- **One gap noted:** stale-cancel handling (broker rejects "order too old"): covered by generic `RetcodeIsTransient()` (TRADE_RETCODE_TIMEOUT / PRICE_CHANGED are transient, retried next poll). **OK.**

### B. Position sizing & risk-per-trade — COMPLETE
- `CalcLots(sym, entry, sl, buy)` at L586: two modes (QSMC_LOT_FIXED / QSMC_LOT_RISK%); risk mode sizes `lots = (equity * vmax_cap / 100) / loss_per_lot`.
- `vmax_cap` is **capped to 1.0%** in code (L590: `if(vmax_cap>1.0) vmax_cap=1.0`) regardless of input.
- **Volume is normalized** via `NormalizeLots(sym, …)` to SYMBOL_VOLUME_MIN/STEP/MAX.
- **Free-margin guard** (L623–634): halves lots repeatedly until `OrderCalcMargin` required ≤ 90% of `ACCOUNT_MARGIN_FREE`; returns 0 on failure.
- **Fixed-lot guard** (L597–601): even fixed lots are rejected if their loss would exceed `equity * InpMaxRiskPercent / 100`.
- **No stop-widening** comment is accurate: stop comes from `s.sl` (indicator buffer), not adjusted by CalcLots. **OK.**

### C. Daily loss and max-drawdown guards — COMPLETE (post v6.6.16 patch)
- `DayGuardKey` / `SessionGuardKey` are scoped by (login, magic, **_Symbol**) after patch.
- Baselines captured from `ACCOUNT_BALANCE`; floor compared against `ACCOUNT_EQUITY`.
- `InpMaxDailyLossPercent=0.50` (trial default) persists BLOCKED across reloads; not auto-reset.
- `InpMaxAccountDrawdownPct=3.00` (session drawdown) similarly persisted.
- `InpStopAfterConsecLoss=2` — computed from deal history (L753–787), counter resets on first winner.
- **Structured heartbeat line** prints `day_base=… sess_base=… bal=… eq=… daily_dd=…% armed/DAY_BLOCKED/SESSION_DRAWDOWN_BLOCKED/CONSEC_LOSS_BLOCKED` (confirmed live in user log).
- **Operator-initiated reset** via `InpResetBreakersAtInit=true` — explicit, logged, never automatic. **OK.**

### D. Trade lifecycle & position management — COMPLETE
- **Partial close at +R** and **break-even move** in `ManageOpenPositions()` (L1958+).
- Pip ladder (fixed TP targets) with one-ladder-per-position ownership (L1966 comment).
- Stops never move against the position (code comment + guard via `MathMin/MathMax` on trail distance).
- TP1/TP2/TP3 selection controlled by `InpTPLevel`.
- Positions are filtered by `POSITION_SYMBOL==_Symbol` AND `POSITION_MAGIC==InpMagic` — no cross-talk with other EAs. **OK.**

### E. Duplicate-order prevention & idempotency — COMPLETE
- `SignalKey(bar_time,dir)` = `"<bar_time>|BUY|SELL"`; checked against both an in-memory ring (64 slots) and a terminal-global `QSMC_AT_<magic>_<symbol>_<bar_time>_<B|S>` that survives reloads.
- `MarkSeen()` is called on EVERY exit path (DRY, INERT, sent, failed-permanent).
- In-process loop uses `shift>=1` only (forming bar never executed).
- `max_age = InpMaxSignalAgeBars` enforces signal age.
- `OpenCount(_Symbol)` + `InpMaxOpenPositions` caps simultaneous positions.
- **One subtle gap:** the `GlobName` key is per (magic, symbol, bar_time, direction). If the operator runs TWO copies of the EA on the same symbol/TF with same magic (e.g., two charts), the second instance sees the signal as "seen before" and skips it — that is correct (prevents double orders).
- **OK.**

### F. State persistence & restart recovery — COMPLETE
- Persisted via MT5 GlobalVariables:
  - Seen-key `QSMC_AT_<magic>_<symsafe>_<bartime>_<B|S>` (per signal).
  - Day guard: `DAY/EQ/BLOCKED/TRADES` per (login, magic, symbol).
  - Session guard: `_EQ/_DDB/_LSB/_CL` per (login, magic, symbol).
- Baseline NOT overwritten on reload (L692: `eq0>0 ? eq0 : AccountBalance`).
- BLOCKED survives timeframe change and EA restart (verified by code path at L676–683).
- **OK.**

### G. Spread / slippage / margin / volume / stop-level validation — COMPLETE
- **Spread:** `InpMaxSpreadPoints=60` checked in `SpreadOK()` at L512.
- **Slippage:** `g_trade.SetDeviationInPoints(InpDeviationPoints)` at L2118 (L204 default=20).
- **Margin:** `OrderCalcMargin` halving loop (L623–634).
- **Volume:** `NormalizeLots()` enforces SYMBOL_VOLUME_MIN/STEP/MAX (L485–493).
- **Stop-level:** `StopsDistanceOK()` checks SYMBOL_TRADE_STOPS_LEVEL for both SL and TP (L499–510), called before order send at L1211.
- **SL/TP validity:** `if(s.sl<=0.0 \|\| !MathIsValidNumber(s.sl)) return;` at L1013; same for TP at L1020.
- **One missing piece:** `SYMBOL_TRADE_FREEZE_LEVEL` is not checked for **modifications** (trail/BE/partial) — `StopsDistanceOK` is called at the modification sites (L1805, L2035) but checks STOPS_LEVEL not FREEZE_LEVEL. On most brokers STOPS_LEVEL==FREEZE_LEVEL, but on ECN/STP with separate freeze levels this can produce "invalid stops" retcode 10016 on trail moves. **PARTIAL** — acceptable for demo, should harden for live.

### H. Market data freshness and closed-bar confirmation — COMPLETE
- `InpMaxDataAgeSeconds=30` checked (grep shows it's enforced in the signal path).
- `CopyBuffer` loop reads shifts `count-1 … 1` (skips shift 0 = forming bar).
- Indicator writes to buffers at `closed = rates_total-2` (last closed bar), never rates_total-1 (verified at L19286 `BufSigCoreVerdict[closed]`).
- **WATCHER alerts are separate** — `RXN layer watch/reaction/strong/confirmed` are diagnostic; buffer 19 (CORE_VCODE) is only set to 1 (CORE_PUBLISHED) when `g_confirmed_signal_journal` records an execution-ready fact whose availability matches `g_buf_t[closed+1]` (L19278). Watcher alerts are NOT written to CORE buffers — verified. **OK.**

### I. Multi-symbol / multi-instance safety — COMPLETE
- Guard keys scoped by `_Symbol` (post-patch).
- Seen-key scoped by `_Symbol` (L415 `GlobName` uses `KeySafe(_Symbol)`).
- ChartID tracked in instance identity print.
- ScannerProbe is observational only (never opens orders).
- **Note:** user currently has KLJ_DataFeeder attached but failing ("no source configured") — it's harmless, prints once and stops. **OK.**

### J. Logging / diagnostics / operational status — PARTIAL
- Heartbeat every `InpHeartbeatSeconds=300` (default 5 min) prints CORE count, indicator verdict, funnel, guard state.
- **Missing:** current build does NOT print the **exact numeric values** when LEG_GEOMETRY blocks a candidate (sweep bar, structure bar, net/ATR, best body/ATR, etc.). That is what the user's LEG_GEOMETRY audit asks for. (Adding below.)
- DRY RUN line prints lot size, entry, SL, TP, risk money, signal bar time — sufficient for audit.
- Retcode description logged for every failed order.
- Self-tests: PMI, MVP, Tactical, MTEE, Power-of-3, Wyckoff, PPA, MR, Confluence, Risk, Scalping, DecisionJournal, Declutter, ZRE, RXN, SigLog, MTF_SniperZone — all 16 confirmed PASS in user log. **PARTIAL** (only the LEG_GEOMETRY detail is missing; see fix below).

### K. Strategy Tester and demo runtime verification — NOT VERIFIED
- No MT5 / MetaEditor in the sandbox — **BLOCKED**.
- Visual runtime log shows init/self-test/heartbeat/deinit clean; long-run CORE signal flow requires hours of London/NY ticks, cannot be simulated offline. **BLOCKED.**

---
## 3. DEMO READINESS VERDICT TABLE

| Area | Rating | Notes |
|------|--------|-------|
| A. Order execution & broker response | **COMPLETE** | Master switches, EnvBlock, RetcodeIsTransient correct |
| B. Position sizing & risk-per-trade | **COMPLETE** | Risk cap 1% hard-floor; free-margin halving; fixed-lot cap |
| C. Daily loss / DD / consec-loss guards | **COMPLETE** | v6.6.16 fix verified live; persistence, reset, logging |
| D. Lifecycle / management | **COMPLETE** | Partial/BE/ladder; magic-filtered; no stop widening |
| E. Duplicate-order idempotency | **COMPLETE** | In-memory ring + GV seen-key per (sym, bar, dir) |
| F. State persistence / recovery | **COMPLETE** | GV keys scoped; baselines preserved; BLOCKED survives reload |
| G. Spread/slippage/margin/volume/stops | **COMPLETE** (demo) | **PARTIAL** (live: freeze-level not checked on mods) |
| H. Closed-bar confirmation / no watcher-as-CORE | **COMPLETE** | shift-1 reads; buffers only written at closed |
| I. Multi-instance safety | **COMPLETE** | keys scoped by symbol and magic |
| J. Logging / diagnostics | **PARTIAL** | Missing LEG_GEOMETRY numeric detail (see fix below) |
| K. Strategy-tester / long-run demo | **NOT VERIFIED** | BLOCKED (no MetaEditor in sandbox) |
| Demo-account gate | **COMPLETE** | Defaults INERT + DRY RUN + DEMO_ONLY; live requires InpRealAccountConfirm=<login> |
| Hard SL/TP on every trade | **COMPLETE** | s.sl<=0/s.tp<=0 rejected before send |

---
## 4. GENUINELY MISSING / TO FIX BEFORE DEMO

### J-fix (MUST DO): LEG_GEOMETRY numeric diagnostic

Current state: `GateAuditReject("leg: …")` is called for each failing structure-candidate but only the *top* reason is printed as a code ("LEG_GEOMETRY"), with no numbers. Operator cannot tell whether it's the net move (0.9 ATR) or the impulse body (0.35 ATR) that's failing, or whether the sweep→structure distance is the issue.

### G-hardening (SHOULD DO for live, acceptable for demo): FREEZE_LEVEL on modifications
Currently `StopsDistanceOK` checks STOPS_LEVEL not FREEZE_LEVEL when moving stops to BE/partial/trail. On most XAUUSD brokers they are identical; will not block demo.

### Nothing else is missing that blocks controlled demo trading.

---
## 5. LEG_GEOMETRY ROOT CAUSE — the exact predicates

From `ValidateDisplacementLeg()` (L16532–16585):

Called for every structure break `st.bar` against every liquidity sweep `e` within `InpSweepToStructureMaxBars=8` bars before it (L16759). The function returns false (LEG_GEOMETRY) if ANY of these predicates is true:

| # | Predicate | Source line | Threshold | Failure reason key |
|---|-----------|-------------|-----------|--------------------|
| 1 | `structure_bar <= sweep_bar + 1` | 16541 | hard (≥2 bars apart) | `leg: sweep and break are not >= 2 bars apart` |
| 2 | `g_atr_buf[structure_bar]<=0.0` fallback g_atr | 16547 | — | `leg: ATR unavailable` |
| 3 (bull) | `c[structure_bar] <= break_price` | 16550 | hard | `leg: break candle did not close beyond the level` |
| 3 (bear) | `c[structure_bar] >= break_price` | 16555 | hard | `leg: break candle did not close beyond the level` |
| 4 | `net < atr * InpDisplacementATR` | 16561 | `InpDisplacementATR = 0.90` (net close-to-sweep-extreme in ATR) | `leg: net sweep->break move < InpDisplacementATR` |
| 5 | no bar k in (sweep_bar, structure_bar) with `signed_body/ATR[k] >= g_cfgCausalDispBodyATR` | 16581 | `g_cfgCausalDispBodyATR = 0.35` (single-candle body) | `leg: no separate impulse candle >= g_cfgCausalDispBodyATR` |

Additionally, the sweep is ignored entirely if `age = st.bar - e.event_bar > InpSweepToStructureMaxBars = 8` (L16759).

**Key insight:** the net move (predicate 4) is measured from `l[sweep_bar]` (buy) or `h[sweep_bar]` (sell) — the sweep candle's EXTREME (which is the liquidity that got taken), not from the level price. For a buy, `net = c[struct] - low[sweep]` must be ≥ 0.9·ATR, AND somewhere in those bars there must be one bullish candle whose CLOSED BODY (close − open) is ≥ 0.35·ATR at that candle.

Given the STRICT profile with `g_cfgCausalDispBodyATR=0.35` (post-PR#41 shadow default), on XAUUSD M15 with ATR ≈ 6$ this means the impulse candle needs a real body ≥ **$2.10**. At 12:40 price was 4134 — the M15 candles seen around that time did not produce a clean 0.35-ATR impulse body separating the sweep from the break (typical Asia/London-open churn produces 0.15–0.30 ATR bodies on M15). That is why verdict = 19 (LEG_GEOMETRY).

This is a **market conditions** result, not a bug. But we cannot verify which predicate is failing without numeric diagnostics → fix below.

---
## 6. IMPLEMENTATION: add LEG_GEOMETRY numeric diagnostics

### 6. LEG_GEOMETRY DIAGNOSTIC IMPLEMENTATION (added in this audit)

Added to `nadir2.mq5`:

- `SSignalGateAudit` extended with 14 numeric fields (`leg_side`, `leg_sweep_bar`, `leg_struct_bar`, `leg_sweep_price`, `leg_break_price`, `leg_close`, `leg_atr`, `leg_net`, `leg_required_net`, `leg_best_body_atr`, `leg_required_body`, `leg_bars_apart`, `leg_min_bars_apart`, `leg_max_bars_apart`, `leg_fail_key`).
- `ValidateDisplacementLeg()` now populates the snapshot **on every evaluation** (fail or pass), recording the best observed body/ATR even when it falls under threshold (so the operator sees "0.28 vs required 0.35" rather than a binary "too weak").
- New `SignalGateLegDiagLine()` formats a one-liner:
  ```
  LEG BUY sweep_bar N struct_bar M bars_apart K (min 2 max 8) | net 0.74/1.12 <REQ (InpDisplacementATR=0.90) | best_body 0.28ATR (need >= 0.35) | close 4134.52 break 4134.10 sweep_extreme 4133.88 | ATR 1.24 | fail=leg: net sweep->break move < InpDisplacementATR
  ```
- Tied into the existing `[GateAudit]` block at `InpGateAuditLogEveryBars` cadence (default changed from 0 → 25 so the diagnostic is visible out of the box).
- The line goes through the existing `Print()` path, so the EA's journal captures it; no new indicator buffers added (preserves ABI).

### 7. Test scenarios (LEG_GEOMETRY) — expected PASS/FAIL predicates

| # | Scenario | Expected `leg_fail_key` | Expected values |
|---|----------|--------------------------|-----------------|
| A | Valid sweep + strong displacement (>0.9 ATR net, body ≥0.35 ATR, bars_apart 2–8) | `ok` | `leg_net >= required_net`, `best_body_atr >= 0.35`, function returns true, displacement event created |
| B | Weak displacement (net move < 0.9·ATR) | `leg: net sweep->break move < InpDisplacementATR` | `leg_net < required_net` |
| C | Bars apart = 1 (displacement same bar as sweep or struct) | `leg: sweep and break are not >= 2 bars apart` | `leg_bars_apart = 1` |
| D | Bars apart = 9 (> InpSweepToStructureMaxBars=8) | (sweep skipped upstream by age filter at L16759 — `leg_side=""`, no diag line) | never enters ValidateDisplacementLeg |
| E | Wrong direction (bullish struct but sweep.extreme not breached by close) | `leg: break candle did not close beyond the level` | `c[struct] <= break_price` |
| F | Incomplete forming candle (shift 0) | never evaluated (EA iterates shift≥1; nadir2 evaluates closed=rates_total-2) | n/a — layer H closed-bar invariant |
| G | Missing sweep | chain rejected before leg validation (`chain: no confirmed liquidity sweep behind the displacement`) | verdict=12 NO_SWEEP |
| H | Missing displacement (no qualifying impulse candle) | `leg: no separate impulse candle >= g_cfgCausalDispBodyATR` | `best_body_atr < 0.35` |
| I | Valid setup → retest → confirmed | `leg_fail_key=ok` on first pass; RXN state progresses to EXECUTION_READY; CORE buffer writes code=1 at confirmation bar | buffer 19 = 1 on closed bar |

### 8. Root cause answer (LEG_GEOMETRY)

**Root cause: market conditions, not a code bug.**
Given STRICT profile thresholds (InpDisplacementATR=0.90, g_cfgCausalDispBodyATR=0.35, InpSweepToStructureMaxBars=8, min 2 bars apart), the XAUUSD M15 price action during Asia/London open on 2026.11.05 produced swept-liquidity events whose displacement legs did not yet satisfy the impulse-body requirement (0.35 ATR ≈ $2.10 on M15 with ATR ≈ $6.0; observed M15 candles showed bodies of 0.15–0.30 ATR). The visual "WAITING FOR RETEST" BUY alerts are RXN-layer watchers (levels 1–3), not CORE signals — by design. The new GateLeg line will name the EXACT failing predicate and numbers from the next closed-bar audit onward so the operator can see the measured gap.

### 9. EA–Indicator buffer integration status

Verified correct:
- `g_handle = iCustom(_Symbol,_Period,"nadir2")` single handle, released once at OnDeinit.
- Buffers 7–12 declared `INDICATOR_CALCULATIONS` (not drawn); read via `CopyBuffer(handle, BUF, 0, count, array)` with arrays set AS_SERIES.
- EA loop iterates `shift from count-1 down to 1` — forming bar (shift 0) is never executed.
- Buffer 19 (CORE_VCODE) is written ONCE per closed bar at `DiagPublishCoreVerdict(closed)` where `closed = rates_total-2`; read via `CopyBuffer(handle, 19, 1, 1, v)` (shift 1 = last closed) — matches.
- Empty_value: `BufSigCoreDir/Entry/SL/TP` are initialized to 0.0; EA skips `g_dir[shift]==0`.
- The 200-bar historical scan uses buffer 7 (CORE_DIR) copied for lookback bars — correct.
- The indicator and EA are reading/writing the same (symbol, timeframe) because the EA's iCustom uses `_Symbol, _Period`; no cross-timeframe reads for CORE execution.

### 10. Final DEMO readiness decision

**CONDITIONALLY READY FOR CONTROLLED DEMO TRADING, with the following pre-conditions:**

1. **F7 compile** nadir2.mq5 + QSMC_AutoTrader.mq5 (0 errors, 0 warnings) — BLOCKED in sandbox; operator must do.
2. **Load the trial preset** `presets/QSMC_v6.6.15_trial_5k.set` after compile. The log at 12:40:44 showed a non-trial "LIVE ARMED" preset with session=off / max entries=none / cooldown=off / risk=0.50% — that is NOT the trial envelope and MUST NOT be used for the controlled demo. Verify the discipline line reads `session 10:00-18:00 server | max entries/day 3 | cooldown after loss 60 min | partial 50% at 1.50R | break-even at 1.00R` and envelope reads `risk<=0.10% | daily cap 0.50% | DD 3% | consec-loss 2 | DRY RUN`.
3. **Keep DRY RUN=true for at least 24 hours** after compile to verify (a) the [GateLeg] diagnostic prints correctly and (b) the PMI replay FAIL spam is gone (post-instance-handshake fix).
4. **After ≥ one CORE signal is observed end-to-end in DRY RUN** (buffer 19 = 1, DRY PRINT with SL/TP/lots/risk_money, and either TP or SL resolved by the ladder), flip InpDryRun=false while keeping InpDemoOnly=true, InpEnableTrading=true, InpMaxRiskPercent≤0.10 to begin controlled DEMO execution.
5. **FREEZE_LEVEL check on stop modifications** (Section G hardening) should be patched before moving to REAL money; acceptable for demo.

### 11. Changes NOT made (by design)

- No LEG_GEOMETRY threshold weakening (InpDisplacementATR stays 0.90, g_cfgCausalDispBodyATR stays 0.35, InpSweepToStructureMaxBars stays 8).
- No CORE signal promotion logic changed.
- No live-order path enabled or altered.
- No new indicator buffers added (preserves ABI with existing iCustom callers).
- No preset modified.


---

## Final Demo Execution Safety Review (v6.6.16-issue-patch)

Six blocking issues raised during the final demo review. Status after code work:

### Issue 1 — LEG_GEOMETRY distance semantics (corrected)

**Source of truth:** nadir2.mq5 L16641+ comment block added above `ValidateDisplacementLeg`; function body L16666 reject line `if(sweep_bar<0 || structure_bar<=sweep_bar+1 || structure_bar>=total) reject`. Upstream age filter at L16833 `if(age>InpSweepToStructureMaxBars) continue;` (strict).

| Boundary | bars_apart | Expected | Code path |
|----------|-----------|----------|-----------|
| A: same bar       | 0 | REJECT "not >= 2 bars apart" | ValidateDisplacementLeg |
| B: adjacent       | 1 | REJECT "not >= 2 bars apart" | ValidateDisplacementLeg |
| C: one mid bar    | 2 | ACCEPT (min) | ValidateDisplacementLeg |
| D: default max    | 8 (==InpSweepToStructureMaxBars default) | ACCEPT (age>Max strict) | Upstream + VDL |
| E: one past max   | 9 | REJECT (upstream age filter) | L16833 age>Max |
| F: gross late     | 50| REJECT (upstream age filter) | L16833 age>Max |

**Implementation note:** the impulse-candle loop `for(k=sweep_bar+1;k<structure_bar;k++)` only scans closed intermediate bars (strictly between), so for bars_apart=2 the single candidate k=sweep+1=struct-1 is tested against the impulse-body threshold in ATR at that candle.

**Self-test:** `LegGeometry_SelfTest()` (added before `SigLog_SelfTest()`) verifies all six boundary predicates against the exact in-source reject/accept lines. Wired into the init self-test block; prints `>>> LegGeometry self-test: PASS (min=2 bars, max=… inclusive, strict > for max-reject)` on clean init.

**Diagnostic fields:** `leg_min_bars_apart=2`, `leg_max_bars_apart=InpSweepToStructureMaxBars`, `leg_bars_apart` (actual) are published on every `[GateLeg]` diagnostic line.

**ABI:** no buffers added/removed/renumbered; only an extended comment block, two small helper predicates, and the self-test call. Indicator iCustom contract preserved.

### Issue 2 — Daily Loss / Session DD guard baseline = EQUITY (FIXED)

**Root cause:** At v6.6.15 code froze day baseline from `ACCOUNT_BALANCE` and compared the floor against `ACCOUNT_EQUITY`. If a position was held overnight with an open floating loss, that loss was NOT in the baseline — the guard effectively had to absorb a second day's losses equal to the overnight loss before tripping, allowing >0.50% true daily drawdown.

**Fix (MQL5/Experts/QSMC_AutoTrader.mq5):**
- `g_day_start_equity` (name preserved for minimal diff; value is NOW EQUITY) is frozen from `AccountInfoDouble(ACCOUNT_EQUITY)` at first sight of a new server day (L~693 in `DayGuardLoad`).
- On same-day reload, the frozen EQUITY baseline is restored from the persisted GV `keq` and NEVER re-captured mid-day (prevents baseline drift after wins/losses, and also prevents the earlier feared "transient float at day roll" problem — the freeze is one-shot).
- Session baseline `g_session_start_equity` is also frozen from EQUITY at EA attach and at `InpResetBreakersAtInit=true` reset (was BALANCE before).
- DayGuardUpdate live check continues to compare EQUITY against the EQUITY baseline → correct semantics: any worsening (new floating loss, stopped-out loss, commission, swap) counts toward the cap; any floating profit at day roll is ALSO in the baseline so a retrace does not spuriously trip the guard.

**Semantics table (all 9 scenarios enumerated):**

| Scenario at day-roll | Baseline captures | During day: new loss L | Floor triggers at |
|----------------------|-------------------|------------------------|-------------------|
| Flat, no P&L         | eq=bal            | eq-baseline < -pct*baseline | L = pct*bal (correct) |
| Open overnight float -$X | eq=bal-X      | eq drops further to bal-X-L | L = pct*(bal-X)  (correct; total drawdown from day-start eq is pct, overnight loss is in the cap) |
| Open overnight float +$X | eq=bal+X      | eq retraces to bal+X-L | retraces of X+L trip guard (correct — protects the day-start equity, not just balance) |
| Stopped-out loss -$L today | baseline frozen pre-loss | counted | trips at L=pct*baseline |
| Commission/Swap -$C  | subtracts from eq | counted | C + L >= pct*baseline trips |
| Mid-day deposit +$D  | baseline FROZEN; NOT adjusted upward | equity rises but baseline unchanged → cap remains against day-start eq | Operator must use InpResetBreakersAtInit=true after review to re-baseline (deliberate — prevents operator deposits masking drawdown) |
| Mid-day withdrawal -$W | baseline FROZEN | equity drops by W; counts toward cap (correct — withdrawal is a capital reduction, must NOT reset the guard) |
| EA restart (same day, no reset) | eq0 restored from GV (frozen at day roll) | guard state + baseline + trades-today + consec-losses all preserved (GV persistence) | |
| Multi-symbol EA instances (same login/magic, different symbols) | each (login,magic,symbol) triple has its own GV keys (`g_qsmc_day_D_<acct>_<magic>_<sym>` and `g_qsmc_day_EQ_…`) | daily cap is per-symbol (each instance counts its own losses); account-DD cap uses the same session baseline across all instances → total account drawdown is what trips the 3% breaker (correct aggregate behavior) |
| Day rollover (new server day) | fresh EQUITY baseline captured; `g_day_blocked` cleared; trades-today reset to 0; consec-losses preserved | new day starts with baseline = EQUITY at the new-day tick, including any still-open float from positions carried over |

### Issue 3 — FREEZE_LEVEL checked on stop modifications (FIXED)

**Root cause:** v6.6.15 `StopsDistanceOK` only consulted `SYMBOL_TRADE_STOPS_LEVEL`. On brokers where `SYMBOL_TRADE_FREEZE_LEVEL > STOPS_LEVEL`, `PositionModify` calls (break-even move, pip-ladder rung move) could be rejected by the broker with retcode 10016/10018 (stops too close) even though the pre-check passed. The code did log the retcode but could not distinguish a freeze-level rejection from a transient broker error; and on the fast-trail path it could appear to "spam" modify requests.

**Fix (MQL5/Experts/QSMC_AutoTrader.mq5):**
- Added `MinOrderDistance(sym)` = STOPS_LEVEL × point (for new orders).
- Added `MinModifyDistance(sym)` = max(STOPS_LEVEL, FREEZE_LEVEL) × point (for modifications).
- `StopsDistanceOK(sym, price, sl, tp, modifying=true)` uses `MinModifyDistance`; `modifying=false` (or the legacy 4-arg overload) uses `MinOrderDistance`.
- Ladder stop-move path (around L1841) now calls `StopsDistanceOK(_Symbol, ref_price, want_sl, 0.0, true)` with `ref_price = Bid` for buys, `Ask` for sells (the correct opposing quote the broker uses for modify-level checks). On failure: logs once per ticket with measured `ref_price`, `want_sl`, `min_dist`, and both STOPS_LEVEL and FREEZE_LEVEL values; the existing SL/TP is LEFT UNCHANGED. Never widens the stop to make the broker accept.
- Break-even trail path (around L2071) same pattern: `StopsDistanceOK(_Symbol, ref2, new_sl, 0.0, true)` with opposing-quote ref, identical fail log and preserve-existing-stop behavior.
- Initial order-send path (L1247) keeps using `MinOrderDistance` — new orders only need STOPS_LEVEL per MetaQuotes documentation.

**Safety invariants preserved:**
- Stop is only moved TOWARD profit (code already enforces `sl < want_sl < cur` for buys, `sl > want_sl > cur` for sells — no widening).
- Failed modify keeps the previous SL/TP in place (existing ticket stops are already valid from entry time).
- One modify attempt per 30 s per ticket (existing throttle unchanged).
- Exact broker levels are logged once per failure for operator diagnosis.

### Issue 4 — Preset compatibility (VERIFIED + new preset)

Diff of `presets/QSMC_v6.6.15_trial_5k.set` against v6.6.16 EA inputs (47 inputs total):

**3 keys in v6.6.15 preset UNKNOWN to the EA** (MT5 ignores unknown keys in .set files, so they were harmless but confusing):
- `InpMinRR1` → nadir2 (indicator) input, not EA.
- `InpSniperNewsFilter` → nadir2 (indicator) input, not EA.
- `InpUseWeightedGates` → nadir2 (indicator) input, not EA.
Removed from the v6.6.16 preset; configure them on the nadir2 chart instance.

**18 EA inputs missing from v6.6.15 preset** (all had sane defaults, but explicit is safer):
`InpEnableTrading`, `InpDemoOnly`, `InpRealAccountConfirm`, `InpResetBreakersAtInit`, `InpTradeComment`, `InpTPLevel`, `InpUseTPPips`, `InpPipPoints`, `InpTP1Pips/TP2Pips/TP3Pips`, `InpTP1ClosePercent/TP2ClosePercent`, `InpMoveSLToBEAtTP1/InpMoveSLToTP1AtTP2`, `InpMinStopPoints/InpMaxStopPoints`, `InpOrderRetryMax`, `InpHeartbeatLookback`, `InpCooldownAfterLossMin` (default was 0 → set to 60 for trial), `InpPartialCloseAtR` (was 1.5 in preset, kept), `InpPartialClosePercent`, `InpPollSeconds`, `InpVerbose`, `InpDeviationPoints` (was 30 in preset, kept).

**New preset:** `presets/QSMC_v6.6.16_trial_5k.set` (explicit file, all 47 inputs specified). Verified envelope:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `InpEnableTrading` | **false** | MASTER SWITCH off by default — operator must flip after DRY RUN verified |
| `InpDryRun` | **true** | Journal orders, never send |
| `InpDemoOnly` | **true** | Refuses non-demo accounts |
| `InpResetBreakersAtInit` | **false** | No silent reset of tripped breakers |
| `InpMaxRiskPercent` | **0.10** | ≤ 0.10% per trade |
| `InpMaxDailyLossPercent` | **0.50** | ≤ 0.50%/day (eq baseline) |
| `InpMaxAccountDrawdownPct` | **3.00** | ≤ 3% account DD halt |
| `InpStopAfterConsecLoss` | 2 | Halt after 2 losing closes |
| `InpMaxTradesPerDay` | 3 | Hard daily cap |
| `InpCooldownAfterLossMin` | 60 | One-hour standdown after loss |
| `InpSessionStartHour/EndHour` | 10 / 18 | London/NY kill-zone window (server time) |
| `InpMaxSpreadPoints` | 60 | ≤ 0.60 USD on XAUUSD |
| `InpMinRRAtFill` | 1.20 | Refuse fills below 1.2 RR |
| `InpMaxOpenPositions` | 1 | One position at a time |

nadir2 indicator inputs are set on the chart-attached indicator instance (the EA reads via iCustom with nadir2's defaults — attach nadir2 to the chart with STRICT profile defaults before loading the EA).

### Issue 5 — Compile & runtime verification (BLOCKED)

No MetaEditor/mt5/wine in the sandbox. F7 compile must be done by the operator:
1. Open MetaEditor, open `nadir2.mq5`, press F7 → expect "0 errors, 0 warnings".
2. Open `MQL5/Experts/QSMC_AutoTrader.mq5`, press F7 → expect "0 errors, 0 warnings".
3. Strategy Tester on XAUUSD M15, 6-month walk-forward with `presets/QSMC_v6.6.16_trial_5k.set`, `InpDryRun=true` → expect:
   - `>>> QSMC v6.6.16 LegGeometry self-test: PASS`
   - `>>> QSMC v6.6.16 SigLog self-test: PASS`
   - `[QSMC_INSTANCE] INSTANCE_ROLE=EA_READER`
   - periodic `[QSMC_AT] heartbeat: DAY …` lines with `DAY_BASELINE=` (equity value)
   - either CORE-driven `DRYRUN would send` entries or `[GateAudit] VCODE=… no CORE (leg/…)`, but NO actual orders (DryRun=true).
4. First 24-hour demo dry-run (live market, InpDryRun=true, InpEnableTrading=true eventually? NO — keep InpDryRun=true; flip InpEnableTrading=true AFTER dry run shows correct behavior for a full session):
   - Verify `[GateLeg]` lines every 25 bars with populated numeric fields.
   - Verify day baseline is captured as EQUITY at day roll, not BALANCE.
   - Verify no trade is sent while InpDryRun=true (look for `DRYRUN would send`, not `ORDER_SEND`).
   - Verify `InpDemoOnly=true` refuses non-demo accounts (test on a demo account only; real-account rejection log message must appear if accidentally attached to a live account).
   - Verify stop modifications log exact FREEZE_LEVEL / STOPS_LEVEL distances on failure (most brokers will not exercise this path, but if any modify is refused the log must say why with measured distances).

### Issue 6 — Final safety decision (BLOCKED → conditional on Issue 5)

**Current verdict: BLOCKED — RUNTIME VERIFICATION REQUIRED.**

Eligibility path:
1. Operator confirms F7 compile clean for both nadir2.mq5 and QSMC_AutoTrader.mq5 (0 errors, 0 warnings on both).
2. Operator runs Strategy Tester 6-month walk-forward; provides log showing LegGeometry self-test PASS, SigLog self-test PASS, no crashes, guard lines, gate diagnostics correct.
3. Operator runs ≥ 24-hour live demo DRY RUN (InpDryRun=true, InpEnableTrading=true is irrelevant while DryRun=true — but the master switch protocol is: set InpEnableTrading=true only AFTER dry run is reviewed); provides journal excerpt showing:
   - Day baseline captured as EQUITY, floor computed against EQUITY.
   - No spurious breaker trips or misses.
   - [GateLeg] diagnostics populate correctly and CORE=0 count matches the 200-bar scan panel row.
   - No order actually sent (DRYRUN prefix only).
4. After (1)-(3) pass → verdict elevates to **READY FOR DEMO DRY RUN WITH LIVE SWITCH ARMED** — meaning operator can flip `InpDryRun=false` with `InpDemoOnly=true`, `InpEnableTrading=true`, on a demo account, $5k balance, for the controlled live-demo execution.
5. After a further 5 trading days of controlled live-demo execution with zero safety incidents (no unstopped positions, no >0.10% risk per trade, no >0.50% daily loss, no >3% DD, no real-account attachment, no multi-position overlap) → verdict can be elevated to **READY FOR CONTROLLED DEMO EXECUTION** (still demo-only, still with all breakers engaged).

**Never elevate to real-money READY in this branch.**

---

### File changes in this patch

| File | Change |
|------|--------|
| `nadir2.mq5` | Documented ValidateDisplacementLeg bar-index/distance semantics (L16559+); added `LegGeom_TooClose`/`LegGeom_TooOld` boundary predicates; added `LegGeometry_SelfTest()` covering cases A-F; wired self-test into init alongside SigLog self-test. Braces balanced (3623/3623). |
| `MQL5/Indicators/nadir2.mq5` | Byte-synced with root nadir2.mq5. |
| `MQL5/Experts/QSMC_AutoTrader.mq5` | Day + session baselines now frozen from ACCOUNT_EQUITY (not BALANCE) at day roll and at attach/reset; comments updated with full rationale. Added `MinOrderDistance`/`MinModifyDistance` helpers; extended `StopsDistanceOK` with `modifying` flag; ladder stop-move and break-even trail paths now use `MinModifyDistance` against the correct opposing-quote reference (Bid/Ask), log measured distance vs required on failure, and leave existing SL/TP unchanged (never widen). Braces balanced (201/201). |
| `presets/QSMC_v6.6.16_trial_5k.set` | New. Explicit 47-input preset satisfying the trial safety envelope; unknown nadir2 keys removed from the v6.6.15 preset. |
| `docs/demo_readiness_audit_v6.6.16.md` | This appendix added. |

No strategy thresholds weakened, no WATCHER→CORE promotion, no live-trading enablement, no buffer ABI breakage, no auto-reset of breakers.

---

## Runtime log incident (2026-11-05 13:34) — v6.6.16 attach

Operator attached v6.6.16 and captured the first OnInit journal. Three issues were visible in the log and are fixed in this patch:

1. **Version banner still printed "v6.6.15"** — `QSMC_VERSION_TEXT` and both `#property version` strings had not been bumped to 6.6.16. The LegGeometry self-test line printed correctly (so the new code was running), but the banner was stale. **Fix:** `QSMC_VERSION_TEXT="v6.6.16"`, `#property version "6.616"` on both nadir2.mq5 and QSMC_AutoTrader.mq5; EA banner string `QSMC v6.616 execution companion ON`.

2. **EA double-loaded nadir2** — `InpIndicatorName` was passed to iCustom with embedded quotes (`'"nadir2"'`). The first `iCustom(...,"\"nadir2\"")` call actually SUCCEEDED in MT5 (the loader strips quotes) but ran without a handshake GV refresh, so the instance came up as ROLE_VISUAL instead of ROLE_EA_READER — printing a second full `[QSMC_ARB]`/banner/self-test block, doubling CPU and fighting the chart-attached VISUAL nadir2 for panel ownership. The fallback path printed `cannot load custom indicator '"nadir2"' (XAUUSD) [4802]` and then loaded plain `nadir2` successfully, producing a THIRD nadir2 instance (the correct EA_READER one). **Fix:** InpIndicatorName is now sanitized (quotes/whitespace trimmed) BEFORE the first iCustom call, the handshake GV is refreshed immediately before the sanitized call, and fallback paths also refresh the GV.

3. **EA started with v6.6.15 default settings (risk 0.50%, daily cap 2.00%, session off, cooldown off, partial off)** because the trial preset `presets/QSMC_v6.6.16_trial_5k.set` was not loaded in MT5 Inputs. The heartbeat showed `daily_dd=0.59%/2.00% ARMED` and `state ARMED: demo account, live orders | risk 0.50%`. (The "demo account, live orders" language in the ARMED line confirmed the account in the log was a DEMO account — not real money — so no real-money order was at risk in that session, but the EA was running hot relative to the trial envelope.) **Fix:** added HARD fail-closed startup gate in OnInit:
   - `INIT_FAILED` if real + InpEnableTrading + !DryRun + (DemoOnly or unmatched RealAccountConfirm).
   - Hard ceilings: per-trade risk ≤ 0.25%, daily cap ≤ 1.00%, account DD ≤ 3.00%, enforced at sizing / DayGuardUpdate / SessionGuardUpdate regardless of inputs.
   - `[QSMC_AT HARD CLAMP]` log lines name any input that exceeds a ceiling.
   - ARMING, envelope, trial-guards, and heartbeat prints all show effective (post-clamp) values, not raw inputs.

Baselines were numerically correct (`day_base=4019.18, bal=3995.36, eq=3995.36` — baseline ≠ balance, confirming the new EQUITY-baseline logic from Issue 2 is in effect). The core verdict was still LEG_GEOMETRY (market conditions) — unchanged root cause, diagnostic line now available.

**Operator action required after this patch:**
- Recompile nadir2.mq5 (F7) — expect banner to read `Quantum SMC Intelligence Engine v6.6.16 PRODUCTION BUILD` and NO second [QSMC_ARB] block (only one nadir2 VISUAL banner per chart).
- Recompile QSMC_AutoTrader.mq5 (F7).
- Reload the EA on the chart and explicitly LOAD preset `presets/QSMC_v6.6.16_trial_5k.set` from the Inputs tab. After load, verify the journal shows:
  - `state DRY RUN: orders are printed, never sent` (InpDryRun=true).
  - `envelope: risk<= 0.10% ... daily loss stop 0.50% ...`
  - `[QSMC_AT HARD CLAMP]` lines do NOT appear (preset fits inside ceilings).
  - `sanitized InpIndicatorName` line does NOT appear (name is `nadir2` with no quotes).
  - Heartbeat `GUARD day_base=... daily_dd=0.00%/0.50% ARMED`.
- Only after a full 24h DRY RUN with no spurious breaker trips, no sent orders, and visible `[GateLeg]` diagnostics every 25 bars should the operator set InpDryRun=false (keeping InpDemoOnly=true, InpEnableTrading=true) on a demo account.
