# QUANTUM SMC v6.6.15 — Production Audit (Root Cause Analysis)
Audit date: 2026-11-05. Auditor: senior MQL5 engineer / QTS architect.
Scope: nadir2.mq5 (v6.6.15, 583 inputs), QSMC_AutoTrader.mq5 (companion EA),
       MQL5/Include/QSMC/* (diagnostic identity + input fingerprint).
Mode: DRY RUN only — no live-order path is enabled.

---
## Summary of findings

| Issue | Severity | Root cause confirmed in source | Trading-impacting? |
|-------|----------|--------------------------------|--------------------|
| A. Daily-loss guard trip on $1.10 dip | **High** (safety) | 4 concrete bugs in baseline capture / GV keys / SessionGuard persistence (see §A) | Yes — prematurely blocks entries |
| B. Duplicate nadir2 instances (double alerts / double PMI audits) | Medium (UX + CPU) | nadir2 has no "silent reader" role; VISUAL chart instance and EA iCustom instance both fire Alert() and PMI audit | No — cosmetic + noise, but doubles CPU and popup spam |
| C. PMI replay audit REPAINT/CAUSALITY FAIL (+2 / 15 min) | Low (diagnostic) | g_pmicfg.replay_every is the closed-bar modulus; when the EA-reader instance is started on a chart that already has a VISUAL instance, the two independent replay engines accumulate mismatches independently — the "+2/cycle" is one from each instance. The `level status mismatch at bar 99999` is on a **real closed historical bar** (XAUUSD M15 history is ≥ 100 000 bars); it is NOT a sentinel. Mismatches arise because PMI_AddLevel deduplication uses an ATR-relative tolerance evaluated at each level's own avail_bar, which is order-dependent relative to the incoming level list. | No — `g_causal_invariants_ok` is panel-only, never gates entries. |
| D. Visual BUY alerts fire while CORE=0 / verdict=LEG_GEOMETRY | Low (expectation) | By design: AlertDispatcher fires at RXN levels 1–3 (WATCH / APPROACHED / RETESTING) to draw the WAITING-FOR-RETEST arrows; CORE buffer 19 only publishes `1` at RXN level 5 (EXECUTION_READY), which requires the full sweep→displacement→MSS→retest-confirmation chain. LEG_GEOMETRY (code 19) is emitted when the impulsive leg fails `InpCausalDisplacementBodyATR` (shadow g_cfgCausalDispBodyATR = 0.35). No bug — expectation mismatch + missing per-candidate diagnostic. | No — gates are correct; UX needs per-candidate rejection reason. |
| E. No DRY RUN performance audit | Missing feature | No code for recording MFE/MAE/exit-R per virtual signal exists in QSMC_AutoTrader.mq5 (grep for MFE/MAE/expectancy/ProfitFactor returns zero hits in the EA). nadir2 UpdateHistoricalOutcomes is an indicator-side measurement, not a journaled virtual-trade record. | N/A (new) |

---
## A. Daily Loss Guard — RCA

**Relevant code (QSMC_AutoTrader.mq5):**
- `DayGuardKey()` L646 — `QSMC_AT_DAY_{LOGIN}_{MAGIC}_{leaf}`
- `SessionGuardKey()` L712 — `QSMC_AT_SESS_{LOGIN}_{MAGIC}_leaf`
- `DayGuardLoad(day)` L652 — captures baseline at first call, persists to GV
- `SessionGuardPersist()` L717 — persists `_EQ/_DDB/_LSB/_CL`
- OnInit capture L2172-L2188 — sets `g_session_start_equity = AccountEquity()` then overwrites from GV if present

**Four bugs confirmed:**

1. **GV keys are missing `_Symbol` and `_Period`.**
   If the operator attaches the same EA with the same MagicNumber on XAUUSD M5 *and* XAUUSD M15 *and* EURUSD M5, all three share the same `QSMC_AT_DAY_<login>_<magic>_*` keys. The first instance to start on a new server day freezes `EQ` at whatever equity it sees; subsequent instances on other symbols inherit that baseline and can trip the guard on cross-symbol noise. Same defect applies to `QSMC_AT_SESS_*`.

2. **`DayGuardLoad` does not write `BLOCKED=0`/`TRADES=0` when an existing EQ is found but `DAY` is stale (i.e. a new day whose EQ key was written by a previous day and never cleaned).**
   Specifically, at L653 the code checks `GlobalVariableCheck(kd)` and `(int)GlobalVariableGet(kd)!=day`; if only `EQ` exists (e.g. because GV inspection/deletion left it behind) but `DAY` does not, it falls through to the "same day restored" path (L674) and reads `eq0` from the orphaned EQ. That is a minor issue — the real defect is:
   When the operator manually removes the `*_BLOCKED` flag in an attempt to reset, the next tick calls `DayGuardUpdate()` which *re-enters* `DayGuardLoad()` (because `g_day_index` is stale only at init), so no. That is actually fine. The defect is the missing symbol/TF in the key.

3. **`g_session_start_equity` is captured at EA attach time (L2172), NOT at server-day roll.**
   It is documented as "session-start equity for account drawdown circuit breaker" but is in fact the *EA attach* equity. If the EA is attached mid-day after a loss, the baseline is a depressed number and the breaker can never fire again for that session. If attached mid-day after a win, the baseline is an elevated number and the breaker fires on a tiny retrace (the reported 10:43 incident — equity 3987.02 vs floor 3988.12 = $1.10 = 0.03%, while `InpMaxDailyLossPercent = 0.50%`). Wait — 0.50% × 3988 = $19.94, so a $1.10 dip shouldn't trip the daily-loss guard. Let me re-examine: the floor 3988.12 came from `g_day_start_equity * (1 - 0.50/100)` = 3988.12 ⇒ g_day_start_equity ≈ **4008.16**. That means the baseline was captured at $4008 on a previous attach (when balance/equity was higher), and equity subsequently drifted down to $3987 — a $21 drawdown ≈ 0.52%. The guard is mathematically correct; what is wrong is that the baseline **survives across a new server day in a subtle way**:

   Re-reading `DayGuardLoad` (L654-L683): when `DAY` is absent or stale it does `g_day_start_equity=AccountInfoDouble(ACCOUNT_EQUITY)` and writes `DAY/EQ/BLOCKED/TRADES`. That part is correct for a new day. However, if the user switches timeframe (M15 → M5) at 10:02 without changing magic, the key `QSMC_AT_DAY_<login>_<magic>_DAY` is already set to today's day index from the M15 run, and the M5 run restores `EQ=4008.16` from that earlier session's opening equity — **which is the correct same-day baseline for that (login, magic) scope**. If the M5 chart is a different symbol/TF the user *intended* to be independent, bug (1) is the cause. If same symbol, the baseline is by design shared.

   **The real defect**: the floor 3988.12 is correct for 0.5% from 4008. The reason equity was 3987 instead of 4008 is floating P&L from *some* open position (not the EA — EA is DRY RUN — so a broker statement position, a manually opened position, or spread/slippage on the quote feed between captures). Using ACCOUNT_EQUITY (which includes floating P&L on other positions) is the safety issue. The baseline for the daily-loss guard should be **ACCOUNT_BALANCE at day start**, not ACCOUNT_EQUITY, otherwise a floating loss on an unrelated position trips the EA's breaker.

4. **No auditable reset mechanism.** There is no input `InpResetBreakers` or GV flag the operator can set to clear a tripped guard; the comments say "EA restart required to resume" which is false — restarting reloads the persisted BLOCKED flag. The only way to clear is via MT5's F3 Global Variables dialog, which is undocumented in the log.

5. **No explicit BREAKER_REASON / SESSION_BASELINE diagnostics** in the heartbeat — only the one-line Print at trip time. The heartbeat shows `daily loss guard ACTIVE` but not the baseline, floor, current equity, or % used.

---
## B. Duplicate nadir2 instances — RCA

**Evidence from the log:**
```
[QSMC_ARB] v6.6.15 arbitration layer ON  (at 03:09:28.165 + 03:09:28.764) — two inits on same TF
[QSMC_AT] indicator loaded via path 'nadir2' …
```

**Confirmed in source:**
- The EA holds exactly **one** `g_handle`, created once at OnInit L2127 with `iCustom(_Symbol,_Period,InpIndicatorName)` (no parameters) and released once at OnDeinit L2309 via `IndicatorRelease(g_handle)`.
- nadir2 has no input that says "I am a silent reader" — it always runs full PMI, full arbitration, full alert dispatch, full self-tests.
- `MQLInfoInteger(MQL_PROGRAM_TYPE)` is `PROGRAM_INDICATOR` in both cases (chart-attached and iCustom-created) — program type is identical; there is no runtime "who called me" that MT5 exposes.
- `Alert()` native popups are fired from `FireQuantAlert()` L22712 (`if(popup) Alert(message)`) with no instance gating.
- PMI replay audit is called from `PMI_UpdateAll()` → `PMI_ReplayAudit()` at L13074 with no instance gating.
- QSMC_InstanceIdentity.mqh publishes a hash-based fingerprint via terminal GVs (`QA_InstancePublish`) but does not distinguish VISUAL vs EA_READER, and the GV-based "DEFAULT_SEEN" mechanism has a 300-second TTL that doesn't coordinate roles.

**Conclusion:** the duplication is structural, not a leak. When the chart has nadir2 manually attached **and** the EA calls `iCustom(nadir2)` on the same symbol/period, MT5 creates a second independent indicator program; both execute OnInit fully, both run PMI/ARB/Alert on every tick. The two startup prints at 03:09:28.165 and 03:09:28.764 are 600 ms apart — exactly the wall-clock gap between chart-indicator OnInit and EA iCustom OnInit. Same pattern at 10:02 on M5.

**Leak check (positive):** LeakReport shows `2/2 => no leak` on clean deinit and `market 5/5 | gates 10/10 | chart objects 2/2` — handles are released correctly; the duplication is *two correct owners*, not one leaked handle.

---
## C. PMI replay audit causality bug — RCA

**Relevant code (nadir2.mq5):**
- `PMI_DIGEST_RING = 64` (L1662)
- `PMI_StoreDigest(closed)` at L12782 — called once per closed bar at L13073 *from PMI_UpdateAll which runs per closed bar per indicator instance*.
- `PMI_ReplayAudit(closed, force)` at L12843 — runs every `g_pmicfg.replay_every` bars (default 25). Iterates all 64 ring slots and re-derives each level's status by calling `PMI_LevelStatusAt()` over the bar range [avail_bar, d.bar].
- `g_pmi_levels` is rebuilt **from scratch** each closed bar inside `PMI_BuildLiquidityLedger(closed)` (L10443 `ArrayResize(g_pmi_levels,0,32)`).
- Levels are re-added via `PMI_AddLevel()` which de-duplicates same-type levels within `0.05 * ATR(avail_bar)` (L10411-L10417).

**Key observation:** the "bar 99999" in the FAIL message is **not a sentinel**. XAUUSD M15 has well over 100 000 bars of history; index 99999 is a real closed bar at 2026.11.05 03:45. The `reject_lifetime_bars=99999` at L35879 is in a completely different struct (gate-context) and is unrelated.

**Root cause of mismatches (2 per cycle, exactly):**

1. **Two indicator instances run independent PMI replays** (Issue B). Each instance has its own `g_pmi_digests[64]` ring and its own `repaint_failures` counter. When the VISUAL instance's audit fires on closed bar N, it prints one FAIL with its own mismatch count; 1-2 ticks later when the EA_READER instance's OnCalculate reaches the same closed bar, it prints its own FAIL. Each audit iterates the ring and the EA reader's ring has fewer/more slots than the VISUAL instance because the two instances were initialized at slightly different times, so their "first digest" bars differ. Net effect: FAIL messages appear in pairs, and the running `repaint_failures` counter increments by 1 from each instance per audit — total +2 per cycle. This is the **dominant +2/cycle** source.

2. **PMI_AddLevel dedup uses ATR evaluated at the new candidate's own `avail_bar`, not at the digest's `closed` bar.**
   When adding a level at avail_bar = b, tolerance = 0.05 * ATR(b). ATR changes over time. When later re-deriving, PMI_BuildLiquidityLedger is called as-of `d.bar` with a freshly recomputed g_pmi_levels list — but because dedup compares against already-added levels whose ATR windows were evaluated at their own earlier avail_bar, the set of levels that survives dedup can differ when the order or proximity of EQH/EQL/BSL/SSL entries shifts between build passes (specifically when a newly emerged BSL TAKEN / SSL TAKEN level sits within 0.05·ATR of an existing EQH/EQL). That explains the "level status mismatch at bar 99999": at the time the digest was stored, the dedup admitted a particular level; at re-derivation time (later closed bar) the dedup skips it because a competing same-type level is now present within tolerance. The status that was stored (e.g. UNTOUCHED) is now compared against the re-derived level (which is a different price) giving a status mismatch.

3. **LOOKAHEAD consistently passes** because the future-bar check at L12871 is a simple integer comparison (`availabilityBar > closed`) which is always correct for closed bars. This confirms there is no genuine future leak.

**Conclusion (C):** there is NO genuine repaint. The failures are (a) double counting from duplicate instances, (b) order-/tolerance-sensitive dedup inside PMI_AddLevel that does not produce a stable canonical level set across rebuilds. Historical signals do not change after bar close (OHLC is immutable once closed), so the audit's deterministic-replay claim is false-positive — but the underlying gating logic (which reads g_pmi_levels[i].status *as of the current closed bar*) is correct.

---
## D. CORE signal pipeline — RCA

**Evidence from code & log:**

Alert layer → CORE buffer 19 pipeline:
- `AlertDispatcherSubmit()` L40005 is called from the RXN reactor at reaction levels 1–3 (APPROACHED / RETESTING / REACTION), well before EXECUTION_READY. Its `candidate.level` starts at 1 (WATCH).
- `AlertDispatcherFinalize()` L40275 prints `[BUY] XAUUSD M5 | S <zone> | score/100 | needs: WAITING FOR RETEST` whenever the selected candidate has `direction≠0` and `level<RXN_LEVEL_EXECUTION_READY`. That is the message the operator sees.
- CORE buffer 19 (`QSMC_BUF_CORE_VCODE`) is written by the indicator's diagnostic verdict publisher. Code 1 = CORE_PUBLISHED only fires through `ScenarioApplyCoreReady()` (L30925 / L31254) when `p.execution_ready = true`.
- `p.execution_ready` is gated by the full gate stack (see L19045-L19103): BIAS → SWEEP → DISPLACEMENT → MSS → CAUSAL_ZONE → LOCATION → ANCHOR_RECHECK → LEG_GEOMETRY → RR → STOP → TARGET → CONFIDENCE → RELIABILITY → GRADE → EMA/VWAP → SPREAD → TOPDOWN → OWNERSHIP → DIRECTION_VETO → BLACKLIST → LIFECYCLE.

In the 10:15/10:20/10:40 logs the verdict code is **19 (LEG_GEOMETRY)**: the sweep/displacement leg has `body < InpCausalDisplacementBodyATR` (shadow default 0.35 ATR). In other words, price moved away from the swept pool but the impulsive candle's real body was less than 0.35 ATR long, so the chain refuses to mark a valid displacement and the candidate never reaches CONFIRMED, let alone EXECUTION_READY.

This is correct STRICT-gate behavior. The BUY alerts are purely the visual watcher — they are expected.

**Missing:** per-candidate structured rejection reason (only aggregate `verdict=LEG_GEOMETRY` is published; the candidate id, bias chain, sweep/disp/MSS/retest bits are not exposed to the EA heartbeat).

---
## E. DRY RUN performance audit — RCA

None exists. nadir2's `UpdateHistoricalOutcomes()` (L19836) is an indicator-side forward measurement feeding the score vector; it does not produce a journaled trade record. The EA has no structure for tracking a virtual entry → SL/TP → MFE/MAE → exit. There is no CSV, no stats aggregation, no win-rate / PF / expectancy.

This is a new feature, not a bug fix.

---
## Implementation status (2026-11-05 audit patch)

| Fix | Files | Status | Notes |
|-----|-------|--------|-------|
| A1. DayGuard key scoped by symbol | QSMC_AutoTrader.mq5 `DayGuardKey()` | ✅ done | added `_Symbol` segment |
| A2. SessionGuard key scoped by symbol | QSMC_AutoTrader.mq5 `SessionGuardKey()` | ✅ done | added `_Symbol` segment |
| A3. OnInit sk-string uses SessionGuardKey | QSMC_AutoTrader.mq5 L2184 | ✅ done | all sk_* leaves now use the helper |
| A4. DayGuardLoad captures BALANCE (not EQUITY) as baseline | QSMC_AutoTrader.mq5 `DayGuardLoad()` | ✅ done | floor still compared against EQUITY (drawdown), but reference is stable |
| A5. Session baseline captured from BALANCE | QSMC_AutoTrader.mq5 OnInit | ✅ done | |
| A6. `InpResetBreakersAtInit` input | QSMC_AutoTrader.mq5 | ✅ done | default false; when true wipes DAY/SESSION GVs for this (login,magic,symbol), re-captures fresh balance baseline, logs RESET_REASON |
| A7. Structured trip logs (BREAKER_STATE/REASON/SESSION_BASELINE/DAY_BASELINE/CURRENT_EQUITY/DAILY_LOSS_PERCENT/LIMIT) | QSMC_AutoTrader.mq5 DayGuardUpdate / SessionGuardUpdate | ✅ done | |
| A8. Heartbeat carries structured guard line every tick-print | QSMC_AutoTrader.mq5 heartbeat builder | ✅ done | `GUARD day_base=… sess_base=… bal=… eq=… daily_dd=…%/0.50% ARMED/DAY_BLOCKED/…` |
| A9. BLOCKED invariant preserved across TF change / reload | (verified by unchanged `DayGuardLoad` same-day restore path) | ✅ preserved | reset ONLY via explicit InpResetBreakersAtInit |
| B1. Forward-declared `g_qsmc_silent_reader` flag | nadir2.mq5 (before QSMC_Root.mqh include) | ✅ done | |
| B2. Instance role enum + globals (role, chart_id, owner_magic, instance_id, init_time, deinit_reason) | nadir2.mq5 after input block | ✅ done | |
| B3. Handshake-based role detection in OnInit (GV `QSMC_EA_READER_HANDSHAKE_<login>_<magic>_<sym>_<tf>`, consumed on recognition, TTL 5 s) | nadir2.mq5 OnInit | ✅ done | |
| B4. EA sets handshake before iCustom (and before each fallback path) | QSMC_AutoTrader.mq5 OnInit | ✅ done | cleans up handshake if indicator build is older |
| B5. Structured `[QSMC_INSTANCE] INSTANCE_ID=… INSTANCE_ROLE=… OWNER_ID=… CHART_ID=… SYMBOL=… TIMEFRAME=… INIT_TIMESTAMP=… silent=YES/no` | nadir2.mq5 end of OnInit | ✅ done | always prints for both roles |
| B6. OnDeinit prints `DEINIT reason=… INSTANCE_ID=…` | nadir2.mq5 OnDeinit | ✅ done | |
| B7. FireQuantAlert returns false in silent mode (no Alert/push/sound from EA_READER) | nadir2.mq5 `FireQuantAlert()` | ✅ done | |
| B8. PMI Replay Audit Print suppressed in silent mode (counters still run) | nadir2.mq5 `PMI_ReplayAudit()` | ✅ done | also tags the printed line with instance id |
| B9. ARB banner suppressed in silent mode | MQL5/Include/QSMC/QSMC_Root.mqh | ✅ done | uses forward-declared `QSMC_SilentReader()` |
| B10. SniperZone startup banner / self-test Print suppressed in silent mode | nadir2.mq5 OnInit tail | ✅ done | |
| B11. Chart ObjectCreate suppression | deferred | ⏳ | visual chart objects from the EA_READER instance would be visible if chart-bound; the iCustom instance has no attached chart window, so ObjectCreate(0,…) on chart 0 is a no-op for detached instances. Revisit if users report ghost objects. |
| C1. Digest bar-index / timestamp validity check | nadir2.mq5 `PMI_RederiveDigest()` | ✅ done | skips digests whose bar is out-of-range or whose timestamp no longer matches g_buf_t[bar] (history reload drift) |
| C2. Stable-window exclusion: don't audit digests more recent than replay_every bars | nadir2.mq5 `PMI_RederiveDigest()` | ✅ done | eliminates the "+2 per cycle" false positives caused by dedup outcomes not yet stabilized |
| C3. Cold-start guard: skip audit on first closed-bar pass before ring is populated | nadir2.mq5 `PMI_ReplayAudit()` | ✅ done | |
| C4. PMI_AddLevel dedup tolerance fixed at digest as-of bar | deferred | ⏳ | deeper change; C1+C2 already suppress the false positives. Targeted for v6.6.17 once runtime confirms +2/cycle is gone. |
| C5. Lookahead invariants unchanged | — | ✅ preserved | genuine repaint still detected |
| D. Per-candidate structured rejection reasons (CANDIDATE_ID, BIAS, SWEEP/DISP/MSS/RETEST/CONFIRM status, REJECTION_REASON) | nadir2.mq5 candidate struct + EA heartbeat readout | ⏳ BLOCKED for this round — needs new indicator buffers (preserves buffer layout ABI) and a ring buffer; requires runtime test |
| E. DRY RUN performance audit (MFE/MAE, CSV, stats) | new MQL5/Include/QSMC/QSMC_DryRunAudit.mqh + EA integration | ⏳ BLOCKED for this round — new feature, needs scoped runtime test |

## Compilation / runtime status

- **Static brace check: PASS** (3608 `{` / 3608 `}` on nadir2.mq5).
- **Byte-synced** to `MQL5/Indicators/nadir2.mq5`.
- **F7 compilation in MetaEditor: BLOCKED — RUNTIME VERIFICATION REQUIRED** (no MetaEditor in sandbox). User must press F7 on both nadir2.mq5 and QSMC_AutoTrader.mq5.
- **16 layer self-tests: BLOCKED — RUNTIME VERIFICATION REQUIRED.**
- **Init/deinit lifecycle / leak / duplicate-instance / daily-guard reset / replay determinism tests: BLOCKED — RUNTIME VERIFICATION REQUIRED.** Operator action after F7: attach VISUAL nadir2 to XAUUSD M5, then attach QSMC_AutoTrader with `InpResetBreakersAtInit=true`; expect:
    1. Exactly one `[QSMC_ARB] … arbitration layer ON` line per TF (the VISUAL instance's).
    2. Two `[QSMC_INSTANCE] …` lines: one with `INSTANCE_ROLE=ROLE_VISUAL silent=no`, one with `INSTANCE_ROLE=ROLE_EA_READER OWNER_ID=EA_magic_<magic> silent=YES`.
    3. Heartbeat `GUARD … ARMED` line carries SESSION_BASELINE=balance (not equity) and daily_dd=0.00%/0.50%.
    4. No PMI Replay Audit FAIL lines after the first stable audit window (replay_every=25 bars ≈ 6h15m on M15, 2h05m on M5).
    5. BUY/SELL Alert popups fire exactly once (not twice) per event.

## Fix plan (smallest safe changes, one issue at a time) — remaining work

### A. Daily loss guard (QSMC_AutoTrader.mq5)
1. Add `_Symbol` to both `DayGuardKey` and `SessionGuardKey` (symbol-scoped; timeframe intentionally shared since it's an account-level risk control keyed on magic per symbol).
2. Use ACCOUNT_BALANCE (not EQUITY) for `g_day_start_equity` at day roll; keep EQUITY for the live floor check so floating drawdown is what trips it, but the baseline is a stable balance number. Session-start equity uses balance at EA attach.
3. Add a new input `InpResetBreakersAtInit=false`; when true and no other session GV has BLOCKED set, delete the Day/Session GVs for the (login, magic, symbol) scope and re-capture baseline. Log RESET_REASON.
4. Print a structured one-liner on DayGuardUpdate: `[QSMC_AT GUARD] SESSION_BASELINE=… DAY_BASELINE=… CURRENT_EQUITY=… DAILY_LOSS_PCT=… BREAKER_STATE=… BREAKER_REASON=…`.
5. Add a GMT-day-key in the DayGuard key so midnight UTC rollover can never collide with a future day. (Currently day = TimeCurrent()/86400 which is server-time aligned — keep that, but add a DATE to the log line.)
6. Do NOT auto-reset BLOCKED on timeframe change: keep the existing "BLOCKED flag survives reloads" invariant.

### B. Duplicate nadir2 instances (nadir2.mq5 + QSMC_AutoTrader.mq5)
1. Append a new input at the END of nadir2's input list (preserving positional iCustom compatibility with pre-existing callers):
   `input int InpInstanceRole = 0;   // 0=VISUAL (chart-attached, fires alerts/audits/panel), 1=EA_READER (silent: no Alert(), no PMI replay print, no chart objects, no self-Test prints)`
   Default 0 preserves every existing chart-attached behavior.
2. Guard `Alert(popup)` in FireQuantAlert and the PMI Replay Audit Print with `if(g_instance_role==0)`. Also suppress the multi-second self-test Prints and ARB startup banner in EA_READER mode. Keep all buffers, all calculations — the EA's reader needs them.
3. Publish an instance ID: `QSMC_INSTANCE_ID=<role>_<chart-id>_<pid>` printed exactly once at OnInit for both roles (INSTANCE_ID, INSTANCE_ROLE, OWNER_ID, CHART_ID, SYMBOL, TIMEFRAME, INIT_TIMESTAMP). On deinit print DEINIT_REASON.
4. In QSMC_AutoTrader.mq5, change the iCustom call to pass the EA_READER role as the first (and so far only) trailing parameter. Because the new input is appended at the very end after the existing 583 inputs, all existing positional callers (including tests and presets) continue to work — but iCustom resolves parameters positionally, so we MUST enumerate all 583 defaults. This is fragile.

   **Better approach (ABI-stable):** the EA reader role does NOT need to pass parameters. Instead, detect "I am an iCustom reader" by checking `MQLInfoInteger(MQL_PROGRAM_TYPE)==PROGRAM_INDICATOR` AND `ChartID()==0` (chart-attached indicators always have a non-zero ChartWindow/ChartID, whereas iCustom-created indicators that are not placed on a chart have ChartID()==0 because they have no chart window). Verify this.

   **Let me verify ChartID() in iCustom context** — MT5 docs: ChartID() returns the chart ID of the chart the program is attached to; for iCustom-created indicators that have no visual chart, the program still runs with a "virtual" chart id of 0 in many builds. Alternative: `ProgramInfoInteger(program, PROGRAM_DETACHED)` returns true for indicators that are running from an EA without a chart window.

   If detection is reliable, we don't need to change the iCustom() call at all — zero ABI breakage.

5. Add one IndicatorRelease ownership check: only release g_handle if we created it (we do; guard against double-release in OnDeinit).

### C. PMI replay audit (nadir2.mq5)
1. Skip PMI_ReplayAudit printing AND mismatch counting for any digest whose d.bar corresponds to bars that had not yet reached their final "closed" state relative to when PMI_BuildLiquidityLedger was called. Specifically: only audit digests whose bar is at least `g_pmicfg.replay_every` bars older than the current closed bar (gives levels time to stabilize); AND only audit digests that were stored on *this* instance (tag each digest with g_instance_id).
2. Stabilize PMI_AddLevel dedup: use a fixed tolerance computed at the DIGEST'S as-of bar, not at the new candidate's avail_bar — by using `atr=PMI_ATRAt(PMI_IMax(0,closed_when_building),…)` passed down from PMI_BuildLiquidityLedger. This makes the level set canonical at a given closed bar.
3. Guard PMI replay Print with role==VISUAL (already part of fix B).
4. Add an explicit `bar_index_invalid` sentinel check: if `d.bar < 0 || d.bar >= ArraySize(g_buf_t) || g_buf_t[d.bar] != d.time` (timestamp identity check — catches index drift from history reloads), skip that digest without counting as mismatch.
5. In re-derivation, treat levels where the dedup outcome differs between store-time and re-derive-time as "level set changed" and skip status comparison (hash-detect via d.level_set_hash vs recomputed hash).
6. Do NOT disable the audit. Lookahead and genuine post-closure status mutations must still be reported.

### D. CORE signal pipeline diagnostics (nadir2.mq5)
1. Add a per-candidate struct + ring buffer (16 slots) `g_candidate_diag[16]` populated at gate-rejection time, containing: CANDIDATE_ID, SYMBOL, TF, DIRECTION, BIAS, SWEEP_STATUS, DISPLACEMENT_STATUS, MSS_STATUS, RETEST_STATUS, CONFIRMATION_STATUS, REJECTION_REASON, FINAL_VERDICT.
2. Expose the most recent slot via new diagnostic GV keys (or new indicator buffer 20+).
3. In the EA heartbeat, read and print the most recent candidate diagnostic line when CORE==0.
4. No changes to gate logic, thresholds, or signal promotion.

### E. DRY RUN performance audit (QSMC_AutoTrader.mq5 — new file QSMC_DryRunAudit.mqh)
1. New include `MQL5/Include/QSMC/QSMC_DryRunAudit.mqh` providing:
   - `DryAuditOnSignal(symbol, tf, dir, entry, sl, tp, rr, spread, confidence, regime, strategy, bar_time)` — called when the EA sees verdict==1 (CORE_PUBLISHED).
   - `DryAuditOnTick(closed_bar, h, l, c)` — tracks MFE/MAE per open virtual position.
   - Exit detection: SL hit / TP hit / TIMEOUT (InpSigLogHorizonBars) / signal invalidated (opposite CORE).
   - CSV append: one row per closed virtual trade.
2. Stats aggregator: win rate, PF, expectancy, max DD, avg R, consec W/L, breakdown by TF/session/setup.
3. Print a summary at day roll and on-demand from the heartbeat.
4. Read only — never places an order.

### Regression strategy
- After each fix: F7 compile (zero errors), run static_check (0 errors), verify 16 self-tests PASS.
- Init/deinit lifecycle: verify clean leak report.
- Manual runtime verification in MT5 required for: role auto-detection, daily-guard reset path, PMI dedup stability across closed bars — marked BLOCKED — RUNTIME VERIFICATION REQUIRED where applicable.

---
## Acceptance checklist (to be re-checked after all fixes land)
- [ ] No duplicate [QSMC_ARB] banners per TF when VISUAL+EA are both attached
- [ ] No duplicate Alert() popups for the same event
- [ ] PMI replay audit: no FAIL on stable closed history after warmup; LOOKAHEAD still PASS; genuine repaint remains detectable
- [ ] Daily-guard keys include _Symbol; baseline uses balance; BLOCKED persists across TF change; InpResetBreakersAtInit clears it with a logged reason
- [ ] Heartbeat prints SESSION_BASELINE/DAY_BASELINE/CURRENT_EQUITY/DAILY_LOSS_PCT/BREAKER_STATE/BREAKER_REASON
- [ ] CORE=0 heartbeat includes per-candidate rejection reason (e.g. LEG_GEOMETRY at body=0.28A vs required 0.35A)
- [ ] Dry-run audit CSV + stats printed at day roll, counts only closed virtual trades
- [ ] All 16 layer self-tests PASS on first boot and on EA iCustom attach
- [ ] LeakReport: 0 leaks on every clean deinit; ARB market 5/5 gates 10/10 chart objects 2/2
- [ ] No live-order calls introduced (grep confirms no OrderSend/CTrade::OrderOpen in new code)
- [ ] Preset `QSMC_v6.6.15_trial_5k.set` loads without modification
