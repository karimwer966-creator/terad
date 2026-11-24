# QSMC v6.6.24 — audit cycle 2026-11-24 (owner-reported MT5 evidence)

**Date:** 2026-11-24 · **Branch:** `arena/d8d5fce7-terad` · **Base:** `fea3ee3` (merge of PR #81, itself on top of v6.6.24)
**Trigger:** owner's MT5 journals (XAUUSD, 2026-11-23/24) showing a "strong SELL" on the chart that does not appear in `QSMC_AutoTrader` logs, plus contradictory diagnostics and guard readouts.
**Scope discipline:** this is an AUDIT document. No entry threshold, risk limit, session window, gate or entry-authority rule was changed in producing it. The fixes proposed are ordered so that every *behaviour-affecting* item carries `[needs owner approval]` and ships separately from pure bug fixes.

**No profitability claim is made anywhere in this document.** Nothing here is a backtest, a win rate or a forecast.

### Prior audit

The 2026-11-16 audit cycle lived at this same path. It has been archived, unchanged, at
**`docs/AUDIT_v6.6.24_2026-11-16.md`** (renamed via `git mv` — history preserved). Everything
in it still stands, including the R1–R5 demo-trial deliverables, the Class A fixes (F-001…F-011)
and the explicit "not compiled, F7 required" caveat. The present document is the **new** cycle and
does not re-litigate those fixes; §8 reconciles the two.

---

## 0. What this audit could and could not do

| | |
|---|---|
| **MetaEditor compile** | **NOT DONE.** The host is Linux and has no MQL5 compiler. `F7` remains the first real compile check for any code change that follows. Every "verified" below is a source-level statement or a Python/native-C++ execution of extracted shipped code — never an MQL5 build. |
| **Backtest / replay in Strategy Tester** | **NOT DONE** for the fixes proposed here. The P0-5 replay harness is a *deliverable*, not a result. |
| **Runtime in a terminal** | **NOT DONE.** `QSMC_RunSelfTest()` was not executed. |
| **Python suites** | **DONE.** Seven of the suites covering the subsystems below were run on this branch and pass (see §7). They are source-contract/native-harness checks, not MT5 runs. |
| **Owner's MT5 journals** | Read as primary evidence. The "strong SELL" the owner saw was **not** observed by this auditor and is treated strictly via the log lines quoted below. |

**Not read line-by-line:** `nadir2.mq5` (45,176 lines) is a 2.1 MB single file; this audit read the
regions cited below and searched the rest. The five `QSMC_Svp*` modules, `QSMC_Renderer.mqh`, the QATS
product and the UI internals were not audited line by line. Findings outside the cited regions are
therefore *not* claimed.

---

## 1. Architecture map — what computes, what publishes, what reads, what executes

Two roles of the same indicator binary exist at once (`nadir2.mq5`):

```
VISUAL instance (operator's chart, ROLE_VISUAL, OWNER_ID="VISUAL")     EA_READER instance (private iCustom child of the EA)
  computes everything                                                     computes everything (PERMISSION: same code path)
  publishes: chart objects, GVs (diagnostic)                              publishes: NO chart objects (silent reader)
  signs GVs with role tag H<role>_<hash>                                 same
  buffers filled; EA does NOT read chart instance's buffers
                                                                         ▲
                                                              iCustom() by QSMC_AutoTrader (no inputs passed → compiled defaults)
```

Decision chain (closed bars only, forming bar never consumed):

```
OnCalculate (nadir2.mq5)
  └─ copy rates/buffers bounded (MTF_SniperCopyRatesBounded/MTF_SniperCopyBufferBounded)
  │    not-ready ⇒ print, return 0, publish NOTHING for that handle
  └─ closed-bar engines → QSMC_UnifiedDecision / gates / arbiter (QSMC_Root)
       │
       ├─ BufSigCoreVerdict (buffer 19, nadir2.mq5:15213/15235)
       │    1 = published on this closed bar | 2 = active setup | 3 = conf pending
       │    else  DiagBlockerCode(GateAuditTopReason())   (nadir2.mq5:20318–20345)
       ├─ CORE export buffers 7..12 (CORE_DIR/ENTRY/SL/TP1..3, :15201–15206)
       ├─ class/score/reliability/rr1/risk-mult buffers 21+ (:15218…)
       └─ SigLog_Update → confirmed-signal journal (ring, in-memory + optional CSV)
                                     │
QSMC_AutoTrader (OnTick/OnTimer)     ▼
  ProcessSignals (QSMC_AutoTrader.mq5:3278)
    ├─ ReadClassification / SeenBefore (dedupe)
    ├─ HandleSignal:
    │    re-checks (spread/stops/session/positions) → CalcLots (class mult → cap → HARD ceiling)
    │    → ClaimExecutionLane (cross-EA) → RunEntryReview (12 conditions)
    │    → TradeEnvBlock → CTrade::Buy/Sell
    │    → verify from the ACCOUNT: retcode class → position exists → server-side SL/TP side
    │      → only then g_sent++ ; missing protection → repair → else close / emergency lockout
    └─ nothing between buffer and order is re-derived from the market; every refusal prints
```

Data-readiness authority (the P0-2 story in one box):

```
MTF_SniperZone_Update (nadir2.mq5:44766)
  gates DATA_READY on: chart ATR, H1 ATR, H1 ADX, M15 structure-ATR, M5 execution-ATR (chart M5 only),
                       H1/M15 iTime stamps stable (RISK_TIMEFRAME_CHANGED)
  does NOT gate: W1/D1/H4/M30 ATR or rates (optional macro zone sources), RSI_M15 (C3 confirm leg)
  missing → MTF_SniperInvalidateSnapshot() → status DATA_INCOMPLETE/<reason> → return, no verdict
  all present → g_sniper_data_ready=true → DATA_READY/RISK_INPUTS_ALIGNED (:44937–44940)
```

Signal publication authority: buffers 7..12 and buffer 19 are written **once per closed bar** on the
closed index. `DiagPublishCoreState` (:20324) deduplicates on `g_diag_core_bar` and marks `code=1` only
when the confirmed-signal journal's last record became `availability_time == this closed bar's open`.

---

## 2. Findings table

Status legend: **CONFIRMED** = proven from source/logs in this audit · **REFUTED** = the suspected
defect does not exist (with evidence) · **NEEDS-DATA** = cannot be settled without the owner's logs.
"Owner appr." = needs `[needs owner approval]`; PRx = proposed PR sequence (§9).

| ID | Sev | Status | Location (line @ HEAD) | Root cause | Proposed fix | Owner appr. |
|---|---|---|---|---|---|---|
| **P0-1** | S1 | CONFIRMED (rejection path) / NEEDS-DATA (trigger) | `nadir2.mq5:17405–17418` (CE_HTF_STRUCTURE creation), `:17635–17654` (ValidateHTFAvailability), `:17824–17845` (invariant CE_HTF), `:18076–18092` (RunCausalGraphChecks), `:16236` (replay arm, `useIncremental` only), `:1195/1197` (HTF TF=H4 default, fractal N=3) | HTF event is created from `g_htf_*` timestamps and then the causal graph is validated; the graph was rolled back because the HTF availability invariant failed. Creation and mapping use consistent arithmetic `availability_bar = ChartEventBarAtTime(availability-1)`, so a *freshly built* event cannot violate the two mapping conditions — the failing case must have been either (a) a bar-index boundary (event mapped onto the forming/last loaded bar), or (b) a stale index after history reload at `OnInit`/re-init, or (c) an HTF availability stamp that is **not** the exact `iTime(tf, shift)` boundary the validator demands. Availability is assigned as `confirmed_at` (close of the Nth right candle — see `ComputeClosedStructureBias` :25246–25249) and `ValidateHTFAvailability` *requires* `availability == confirmation_close`, so availability-before-HTF-close **cannot pass the validator**; the fail happened, the setup was rolled back and never traded. Which of (a)/(b)/(c) fired is not determinable from the logs the owner pasted (the exact `[CausalInvariant] FAIL` line and broker UTC offset are missing). | Keep the invariant exactly as is (it is the only thing standing between a repaint and an order). Add: (i) a pinned unit/native test for `ValidateHTFAvailability` (D1/W1, DST and non-DST weeks) asserting the boundary conditions; (ii) on FAIL, print the three epochs (`event/confirmation/availability`) unconditionally — today the reason string contains the id but the raw times only appear in the `[HTFEvent] mapping failed` path; (iii) never reuse the CE_HTF event across re-init. If the owner's FAIL recurs with the new print, the root cause is then provable from one log line. | **No** for (i)–(iii); **the trade-blocking semantics stay unchanged**. Any relaxation of the invariant would be a separate, approval-gated PR. |
| **P0-2** | S1 | (a) CONFIRMED (limited scope) · (b) REFUTED (not an off-by-one) · (c) CONFIRMED · (d) PARTIALLY CONFIRMED — see §3.2 | `nadir2.mq5:43221–43299` (MTF_SniperCopyBufferBounded), `:44766–44942` (MTF_SniperZone_Update), `:44830–44852` (missing-gate), `:44752–44760` (status latch) | (a) `DATA_READY` is only proof that the *mandatory risk inputs* aligned. A not-ready **optional** handle (RSI_M15 → C3 leg, W1/D1/H4/M30 ATR) coexists with `DATA_READY/RISK_INPUTS_ALIGNED` by construction — confirmed. The mandatory handles DO block. (b) `BarsCalculated < count+1` is **correct** for a shift=1 copy of `count` bars (indices 1..count must exist ⇒ calc ≥ count+1); the READY line prints `copied/count` (200/200) while the not-ready line prints `calc < count+1` (-1 < 201). Same condition, two different units — confusing, not wrong. (c) the not-ready branch never increments `retry_counter` (only the ready path does), so `DATA_READY … after 0 waiting attempts` follows a not-ready warned_flag with zero retries — the number is accurate and the label is misleading. (d) Signal publication is **not** currently gated on `g_sniper_data_ready` outside the sniper engine; the core engine publishes independently. Whether `RISK_INPUTS_ALIGNED` should also require RSI_M15 is an owner decision (it feeds one of five confirm conditions). | 1. Ready-line prints both unknowns explicitly: `DATA_READY 200/200 (copied/requested) after %d retries and %d not-ready waits`. 2. Count not-ready waits in a separate counter so the READY line can never read "0 waiting attempts" after a not-ready event. 3. When `!(g_sniper_data_ready)`, the core publish path writes `code=0/blocker=DATA_INCOMPLETE/<reason>` into buffer 19 (verdict currently comes only from core journal state — see §3.2, fix is additive, one line). 4. Test: native harness with `BarsCalculated=-1` asserting (i) no `DATA_READY`, (ii) no buffer-19 code ≠ 0/blocker, (iii) `missing=` reason string matches the failed handle. | **No** for 1, 2, 4. **Yes** for 3 if "buffer 19 blocker on DATA_INCOMPLETE" is considered an entry-authority change (recommend: ship as part of P0-2 with explicit owner sign-off). RSI_M15/W1/D1/H4/M30 required-ness = **owner decision**. |
| **P0-3** | S1 | CONFIRMED (zero-comparison PASS; phantom "test 5"; replay unarmed on cold start) | `nadir2.mq5:13108–13115` (replay early-return), `:13198–13221` (PASS text hardcodes "Tests 1-4, 6"), `:16236` (armed only when `useIncremental && closed % InpReplayAuditEveryBars == 0`), `:18076–18092`, `PMI replay state reset (:8833) seeds `last_report="not run"`; `QSMC_Root.mqh:457/481` (outcomes print gated on `!QSMC_SilentReader() && (bars>0 || ready)`); `analyze_trial.py` (~:152) already has the PASS/FAIL/INCONCLUSIVE + min_sample pattern | The PMI replay audit compares nothing on the first closed-bar passes — but the self-test prints PASS anyway, and the PASS text names a test 5 that does not exist anywhere in the suite. "replay: not run" is the correct cold-start state and is never escalated. | 1. In `PMI_ReplayAudit`/self-test summary, `compared == 0` ⇒ verdict **INCONCLUSIVE**, never PASS; print the reason (`no digests yet` / `not armed (non-incremental)`). 2. Delete the phantom test 5 from the PASS text or add the missing test — decide by reading the suite; restoring a *real* test 5 is preferred, but if none was ever implemented, print "Tests 1-4, 6" **only together with** "compared=N" and treat N==0 as INCONCLUSIVE. 3. "replay: not run" at cold start must be printed once per init as WARN level, and the log line must state the arming condition (incremental tree + `closed % every == 0`). 4. Self-tests (`QSMC_Selftest.mqh`): new assertion that a zero-comparison audit **fails the suite** if it claims PASS. | **No.** |
| **P0-4** | S1 | CONFIRMED (EA cannot know the indicator build; INPUTS mismatch is structural; effective-threshold drift chart-vs-EA) | EA: `QSMC_AutoTrader.mq5:3413–3442` (`IndicatorIdentityLine` — `INDICATOR_BUILD=UNVERIFIED`, `INDICATOR_INPUTS=COMPILED DEFAULTS`), `:4027` (heartbeat identity print), `:4715` (init print), `:4556–4680` (iCustom + handshake; **EA passes no inputs by design**; `test_autotrader_contract` enforces the verbatim call form); indicator: `QA_InstancePublish` (`QSMC_InstanceIdentity.mqh:58–85`) prints `input_hash`/`EA_DEFAULT_hash` at init only, `QA_InstanceMismatch()` role-scoped, 300 s TTL; chart profile `PRACTICAL` relaxes 5 numeric thresholds (`nadir2.mq5:19570–19612`): confidence→60, reliability→60, RR1→1.20, stop→6.0 ATR, anchor→120 (lines :19573–19611); EA reads compiled defaults (`STRICT`: 75/80/1.5/4.0/60) | Two instances of the same code, two input sets, one direction of information flow. The EA cannot hash the chart instance's inputs (they are invisible to it); the handshake GV proves only "an EA_READER came up", not what it computes with. `INDICATOR_BUILD=UNVERIFIED` is therefore *honest* — but nothing enforces any consequence for it, and the mismatch the operator needs to see (chart PRACTICAL vs EA STRICT) is printed once at init, never at heartbeat, and never blocks. | 1. Heartbeat prints, beside the existing identity line, the pair `input_hash` vs `EA_DEFAULT_hash` published by the EA_READER instance (the EA **can** read GVs the reader writes) + a single `EFFECTIVE_THRESHOLDS` line (profile, conf/rel/RR1/stop/anchor actually in force on the reading instance) — this is a log-only change. 2. If they differ from compiled defaults **and** the EA was expected to run defaults, print `INPUTS MISMATCH — EA trades compiled defaults, chart shows its own tuning` (log-only). 3. `INDICATOR_BUILD` verification: prompt the operator for the indicator's `COMPILED_AT` (already printed by `[QSMC_INSTANCE]` at init) and refuse to trade (block, loudly) when it is absent/stale. Requires a new GV published by the reader each init — **[needs owner approval]** scope: gate change. 4. Fingerprint comparison at **start and at every heartbeat** — implementable now, log-only or block-on-mismatch; if block-on-mismatch is approved, that is an entry-authority change and ships separately. | **Yes** for 3 and for block-vs-log in 4. **No** for log-only 1, 2, 4. No threshold moves without approval. |
| **P0-5** | S1 | NEEDS-DATA (the missed SELL) — instrumentation decided | Chart side: `nadir2.mq5:16445` (`DiagPublishCoreState(closed)`, once per closed bar), `:20318–20345` (buffer 19 codes), GateAudit histogram `:19431–19600` (aggregate, `EA_READER bars==1` or every `InpGateAuditLogEveryBars`); funnel: `QSMC_OpportunityFunnel.mqh` (13 stages, FNV-1a ids, ring 1024, **print-only, not wired**); EA side: `QSMC_AutoTrader.mq5:3300–3470` (INVALID_DIR/expired → permanent/expired reject, NaN refusal, `JournalSignal(signal_seen)`); `:4556–4680` (iCustom) | A chart "strong SELL" that never reached the EA can come from exactly three classes: (i) the signal was never published (core chain blocked it — or buffer 19 said blocked), (ii) it was published but the EA marked it seen/expired/invalid before execution, (iii) EA and chart read **different configs** (P0-4 — chart PRACTICAL vs EA compiled defaults: the chart can print "strong" for a setup that fails STRICT reliability/RR1/stop ceilings and is therefore invisible to the EA). Only (ii)/(iii-part) leave a trace in EA logs; (i) leaves none in EA logs *by construction*, because the EA never sees buffers it wasn't handed. | **P0-5 deliverable (diagnostics only):** (a) extend `QSMC_OpportunityFunnel.mqh` with a per-closed-bar compact line, written to MQL5/Files **and** surviving re-init (versioned append-only, like EdgeBook): bar time, data-ready state/reason, structure state, causal-chain state, location, score, reliability, RR1, top-down verdict, session, blacklist, arbiter ownership, gate-audit top-3 blockers, buffer-19 code. One line per closed bar, not per candidate. (b) Replay harness (Strategy Tester, offline): XAUUSD 2026-11-23…24, M15 and M5, two input sets — (1) the owner's chart PRACTICAL set, (2) compiled defaults — printing the per-bar funnel for both. This settles (i) vs (iii): either both funnels block the SELL (then the chart label was not a published signal) or PRACTICAL publishes and STRICT does not (P0-4 territory). (c) Prove publication is closed-bar only (buffer 19 written only at `closed` index; journal availability == bar open) — partially proven in §1; replay closes the rest. If after (a)+(b) the harness shows the SELL existed in PRACTICAL and nothing was readable by the EA, that is a **config divergence finding**, not a code defect — the fix is P0-4 (or an owner decision to pin the EA to the chart inputs). | **No** for (a) diagnostics and (b) replay (both print/measure only). Any change to what the EA executes as a result = **owner approval**, separate PR. |
| **P1-1** | S2 | CONFIRMED (mixed reference paths exist) / PARTIAL (the "opened 2026.11.19" case) | Canonical ref: `nadir2.mq5:8840–9056` (`QSMC_PriorDayRef`/`SPriorPeriodRef`, chart-boundary definition, shift-1 only as `CopyRates` fallback), consumers: pivots/CAM `:29020–29075`, `:29260`; legacy remnants still on the shift-1 path: `:29014–29018`, `:18917/18919–18921` (target engine), `:34338`; `QSMC_SvpLiquidity.mqh` pools; PDH/M1 case: canonical ref time = prior **closed D1** candle | The daily/weekly reference was unified in v6.5.3 onto one boundary-based definition — but not everywhere: at least four call sites still read `iBarShift(PERIOD_D1,1)`-style shift-1 candles, and the SVP pool path never migrated. Shift-1 and chart-boundary disagree exactly when the new D1/W1 bar has not opened yet in the loaded history (weekend gap, holiday, W1 boundary) — which is when a Monday 2026-11-24 attach can see "prior daily candle opened 2026.11.19" (Thursday) while the M1 panel still shows the canonical ref (matching PDH≈3689.54 vs PIV R2≈3758.7 split). | Single `SPriorPeriodRef` everywhere: migrate the four legacy sites and the SVP pool read onto the canonical ref; the shift-1 fallback stays but must print `ref_via_shift1=true` (already tracked in `g_d1_ref_via_shift1`) so a fallback is never silent. Tests: weekend-gap + DST-week replay asserting one identical ref for PDH/PDL/PWH/PWL/pivots/CAM in both cases; then the target engine. | **No** — same definition, one implementation. (If the owner wants PDH re-pinned to a *different* definition than boundary-based, that's approval-gated, but no new definition is proposed.) |
| **P1-2** | S2 | CONFIRMED (no upper-size sanity reject in FVG path) | `nadir2.mq5:24756` (AdvanceFVGStatesTo), `:24792` (AddOrMergeFVG), `:24832` (TryDetectFVGAt), `:24880` (DetectFVG); no size/range gate anywhere in the FVG pipeline; history high cited by owner: 5598.38 vs XAUUSD ~3556–3637 (2026-11) | An FVG of `3829.21 → 4693.81` (864 points, on a symbol trading 3556–3637) is not a market structure fact; it is bad data or a scale/unit bug (e.g., an unadjusted feed window, a point/tick unit error, or a stale cache on a different instrument with the same symbol name — XAUUSD exists on multiple brokers with different price scales). The detector has no upper-bound check at all, so anything the copy gates accept is eligible. | Add a **data-sanity gate** at the FVG/OB ingest boundary (not inside the detector): reject/flag any zone whose (hi-lo) > `InpMaxZoneATR`-style bound (default derived from N × ATR of its own TF) and any level outside the symbol's loaded closed-history high/low; emit `[DATA_SANITY] rejected FVG lo=… hi=… reason=…`. Add the symmetric rule for pivots (`PIV S2 outside symbol closed history range`). Flag = do not use the zone for entries **nor** for targets; keep it visible for the operator. Test: synthetic bad-history replay + unit check that an out-of-range zone never reaches the arbiter. | **Yes** — it changes which zones exist at all (entry authority, however narrowly). Propose with default **ON for flagging, OFF for blocking** if the owner prefers; blocking is the useful mode, hence approval. |
| **P1-3** | S2 | NEEDS-DATA (per-TF ATR correctness) / behaviour change gated | `QSMC_Types.mqh:438–468` (QSMC_ZoneRangeReason — rejects only when gap > `max_distance_atr*atr` **and** age outside (0,lifetime)); `QSMC_IncidentSafety.mqh:9–58` (QA_FilterCandidates, EMPTY_VALUE fail-closed); `nadir2.mq5` — distance measured against **chart-TF ATR** (`g_atr`); InpZoneMaxDistanceATR=12.0, InpZoneLifetimeBars=120 | An HTF level (W1/D1) several hundred chart-ATRs away is rejected on a 1-minute chart ("expired distant zone") but survives on M5 — the age test is in chart bars, so "lifetime 120 bars" means 120 minutes on M1 vs 10 hours on M5. There is no evidence this is a *bug* — it may be an accepted design (chart-relative relevance); the defect class is that the rule silently means different things on different TFs and says so nowhere. | **Proposal only (default OFF):** an opt-in `InpZoneDistanceOwnTF` that measures HTF-level distance in the level's own TF ATR; change age accounting for HTF zones to HTF bars; print `distance_owntf=… atr_tf=…` in the zone line. Do **not** implement in this cycle. On M5 twelve RXN zones were alive — the current rule is not broken everywhere; the M1 starve-out needs the replay harness (P0-5b) to quantify before anyone approves a change. | **Yes** — explicitly. |
| **P1-4** | S2 | CONFIRMED (disagreements exist and are documented below); report-only | EA: `QSMC_AutoTrader.mq5:393–394` (10:00–18:00 **server**, half-open via `QER_SessionInside` :1998–2017, inclusive-open/exclusive-close), `:3625–3629`, `:5066`; indicator: `nadir2.mq5:824–833` (Asia 9–18 **Tokyo local**, London 8–16 **London local**, NY 8–16 **NY local**, Kill zones 7–10 London / 7–10 NY), conversion `SessionLocalTime` (:~22700) via `ServerToUTC`/`BrokerUTCOffsetSecondsAt` (:24258–24290) honouring `InpBrokerUTCOffsetWinterMinutes=120`, `InpBrokerDSTRule=BROKER_DST_EU` (:859), `InpUseDSTSessions=true`; PMI print: `nadir2.mq5:13458` claims fixed "internal UTC (Asia 00-09, London 07-16, overlap 12-16, NY 12-21); panel shows Algeria UTC+1"; panel: Algeria UTC+1; `QSMC_Preset.mqh:88` `InpArbSessionStartHour=-1` (off); QATS: off | Three independent session models coexist: (1) a broker-server half-open window in the EA (10–18), (2) DST-aware local-market sessions in the indicator, (3) a **fixed, non-DST "UTC" banner in PMI** that matches none of the above (London 07–16 UTC ≠ London local 8–16 in winter = 08–16 UTC; NY 12–21 ≠ 12–20 summer / 13–21 winter). Algeria (UTC+1, no DST) is an operator-facing convenience, uncoupled from both. If the broker's winter offset really is UTC+1 (owner's observation) while `InpBrokerUTCOffsetWinterMinutes=120` (UTC+2) is configured, `ServerToUTC` is wrong by one hour **every winter day**, shifting every session/anchor/VWAP-London boundary computed through it — that is a configuration fault, and it is verifiable at a glance from one heartbeat line printing all four clocks. | Report-only (no window changes): (i) heartbeat prints one block: server hour, computed UTC, London local, NY local, Algeria, and the configured vs detected broker offset if determinable (`TimeGMT` vs `TimeCurrent`); (ii) PMI banner line 13458 replaced by the same computed line (it is a lie today — "fixed UTC" is not what the code does); (iii) document the EA window's UTC reading in `docs/` (it is London + first half of NY, by design or by accident — owner decides); (iv) if owner confirms broker winter = UTC+1, set `InpBrokerUTCOffsetWinterMinutes=60` in the preset — that is a **configuration change needing approval**, listed here, not made. | **Yes** for (iv) and for any window edit. **No** for (i)–(iii). |
| **P1-2-adjacent note** | — | CONFIRMED | `nadir2.mq5:24880` | See P1-2 — no size gate exists at all in FVG detection; the gate belongs at ingest. | (folded into P1-2) | (folded) |
| **P2-1** | S3 | CONFIRMED (duplication exists) / document-only | Indicator trade management: `MTF_SniperComputeTradeManagement` (:calls `:44904`) — scaling 40/30/30, TP exits 25/30/45 (sniper/zone engine); EA: partial 50% @1.50R (`QSMC_AutoTrader.mq5` position-management section); core engine has its own TP logic (`17900–17950` region) | A live trade is potentially managed twice (chart indicator and EA) with incompatible plans. In practice the EA is the only order manager; the indicator's plan is advisory for the chart viewer. Nobody should "fix" this by making the indicator manage orders. | Document which layer manages a live trade (EA only; indicator = advisory display) in `docs/`; add one comment at `MTF_SniperComputeTradeManagement` pointing at the EA. **No code path changes.** | **No.** |
| **P2-2** | S3 | CONFIRMED (mechanics) / limits unchanged | `QSMC_AutoTrader.mq5:4726` (`g_session_start_equity` = **equity at attach**, frozen), persisted `SessionGuardKey("_EQ")` symbol-scoped, restore if >0 (`:4778–4781`); `InpResetBreakersAtInit` wipes keys incl. `_HWM`, re-captures baseline (`:4740–4775`); HWM restore `max(stored, baseline, eq)` (`:4800–4806`); drawdown breaker (F4) references `g_equity_hwm` via `dd_ref` (`:1944`) — **sess_base does NOT feed the drawdown breaker**; `GUARD … sess_base=` printed `:4033` | Owner reads `sess_base=4720.62` against `bal=6703.96` (−29.6%) and fears a hidden floor. There is none: the 0.50 % daily limit (≈ 33.52 USD) is keyed off `g_day_start_equity` (per-day roll), and the account-drawdown breaker off `g_equity_hwm`. `sess_base` is informational (and a fallback `dd_ref` when the HWM key is absent). The number being far below balance is an artefact of an old attach/re-init, not of a risk rule. | Document: (i) `sess_base` semantics + that it never enters a stop computation; (ii) recommend (not make) `InpResetBreakersAtInit` usage at attach after long detach periods; (iii) one doc paragraph on what each of day_base/sess_base/HWM/bal/eq means. If the owner wants sess_base to actually *be* a session floor, that's `[needs owner approval]` and NOT proposed. Per-trade risk % vs the 0.5 % day stop: report only. | **No** (docs). **Yes** if a real session floor is ever requested. |
| **P2-3** | S2 | CONFIRMED (memory-only outcomes; `VISUAL_VISUAL_` prefix) / PARTIAL (DEINIT reason=3 + truncation) | `QSMC_Root.mqh:457/481` (`m_stats.Open`/`Deinit` print gated `!QSMC_SilentReader()`), `QSMC_Stats.mqh:~997` (ctor m_open=false), `:~1010` (`csv_enabled=false` ⇒ return **before** `m_edgebook.Open` ⇒ outcomes are memory-only); preset `InpArbCSVLog=false` default (`QSMC_Preset.mqh:48`), `InpArbMinSample=30` (:90); EdgeBook `QSMC_EDGE_V1_<sym>_<tf>.csv` exists and works when armed (`QSMC_Stats.mqh`); `g_instance_id` built `:14966–14971` as `<ROLE>_<owner_magic>_…` with `owner_magic="VISUAL"` ⇒ `VISUAL_VISUAL_XAUUSD_…` confirmed by construction; OnDeinit `:15677–15680` prints `DEINIT reason=` with full id | DEINIT reason=3 (terminal shutdown/profile switch) on a TF change destroys the in-memory EdgeBook/funnel/outcomes; the next attach starts from n=0 — the operator cannot tell "no evidence yet" from "evidence lost". The duplicated `VISUAL_VISUAL_` prefix and the truncated `InpRequireInstitutio…` fragment are both string-assembly defects (prefix applied twice; a clipped/`StringSubstr`-pasted banner). | 1. Persist outcomes/funnel counters automatically when `InpArbCSVLog=true` is **not** set? No — persistence is currently opt-in by design (privacy/size). Proposal: when outcome tracking runs (it does, even with CSV off — see `test_edgebook_contract.py` assertion), write a minimal `QSMC_ARB_STATE_<sym>_<tf>.csv` (counts only: wins/losses/ambiguous, not per-trade) OR simply print `outcomes n=%d (memory only)` at deinit so an n=0 is never misread as "no history existed". 2. Default stays off; **owner chooses**: (a) keep opt-in, add the deinit print (no approval), or (b) auto-arm a counts-only ledger (approval: new file in MQL5/Files). 3. Fix `VISUAL_VISUAL_`: role prefix already includes the role; drop the `owner_magic=="VISUAL"` duplication. 4. Find and fix the clipped `InpRequireInstitutiohistory=…` concatenation (search for missing `
`/`" "` around that banner) — pure log fix. | **No** for 1(a), 3, 4. **Yes** for 1(b). |
| **P2-4** | S2 | CONFIRMED (label contradictions; no single effective-threshold line) | `nadir2.mq5:19825–19846` (`SIGNAL EXECUTION PROFILE: PERMISSIVE` banner followed immediately by `EFFECTIVE SET: STRONG only` when weak/moderate are off — the second line is the true one, the first is the profile's *name*), `:19844` top-down mandatory line vs `InpTopDownHardGateForWeak`; heartbeat (`QSMC_AutoTrader.mq5:4020–4060`) prints `GUARD …` but **no** consolidated effective-threshold line; `TopDown gate=ON minRR=2.00` (chart) vs PRACTICAL `RR1 1.20` floor (`:19586`) — two different "RR" numbers for two different questions (entry-review checklist RR vs execution floor), never printed together | The banner names the *profile* ("PERMISSIVE") while the effective set line states the *operative* restriction (STRONG only). An operator skimming the first line concludes the chart is permissive; the EA (compiled defaults, STRICT) is stricter still. "minRR=2.00" vs "RR1 1.20" are different gates (entry-review geometry check vs PRACTICAL floor) — both correct, neither labelled. | One `EFFECTIVE THRESHOLDS` line per heartbeat (EA) and one per init (indicator), listing: gate profile, emitted verdict classes allowed, conf/rel/RR1/stop/anchor in force, top-down veto on/off and for which classes, session window (UTC+server+Algeria), risk % (EA), InpDryRun. If any two printed values disagree with their binding gate, print `CONTRADICTION: <a> vs <b>` on the same line. Pure log fix; the numbers themselves are not touched. | **No.** |

**Reading the owner's log against this table:** P0-4 (chart PRACTICAL vs EA STRICT — `input_hash=1763998980 config=CUSTOM` at chart vs EA defaults, `INDICATOR_BUILD=UNVERIFIED`) is the single most probable reason a chart-visible "strong SELL" produced **zero** EA-side trace without a single error line — and P0-5's replay harness is what will prove it. Nothing in this audit claims the SELL was real, filled, or missed; the instrumentation in P0-5 exists precisely to make that answerable next time.

---

## 3. Detail on the four P0 items

### 3.1 P0-1 — CE_HTF id and availability (what the log shows vs what the code does)

Owner's failing id decodes as (UTC):

| field | epoch | UTC |
|---|---|---|
| `CE_HTF_XAUUSD_1795190400_1795449600_S` event | 1795190400 | 2026-11-20 16:00 (Friday) |
| availability | 1795449600 | 2026-11-23 16:00 (Monday) = event + exactly 72 h = 3 × 86400 |

Two observations:

1. The 3-day gap with identical seconds fields (`16:00:00`) is a **TF boundary pattern**, not an
   intraday accident. A D1/W1 candle at a 16:00 UTC wall-clock means the stored bar stamps cross a
   UTC+8 boundary (D1 open = 16:00 UTC). The log headers reading `00:00` are consistent with an
   operator broker whose XAUUSD day opens at 00:00 **server** while the stored epoch is interpreted
   as 16:00 UTC — i.e. **server = UTC+8**, or the log prints a different clock than the raw epoch.
   Neither matches the configured `InpBrokerUTCOffsetWinterMinutes=120` (UTC+2) nor the owner's
   stated "server was UTC+1". This arithmetic cannot be closed from inside the repo:
   **NEEDS-DATA** — the owner's broker UTC offset (and whether bar stamps are server-true), plus
   the exact `[CausalInvariant] FAIL` line.
2. Whatever the clock, the **invariant did its job**: `ValidateCausalGraphInvariants` flagged the
   event, `RunCausalGraphChecks` printed `[CausalInvariant] FAIL … mapping mismatch: <id>`, the
   setup branch was rolled back (`[CausalBranch] ROLLBACK … setup event rejected`) and the signal
   was **not used**. The "strong SELL" question is downstream of this line. Definition-of-done for
   P0-1: invariant passes on XAUUSD D1/W1 in replay, **or** the failing event is proven correctly
   rejected and never consumed — the second half of that sentence is already evidenced by the code
   path above; the first half needs the P0-5 replay.

Note on the "00:00" headers: `MTF_SniperDataStatus`, `[EL][DATA]` and most banners print
`TimeToString(..., TIME_DATE|TIME_MINUTES)` of raw stored stamps. If the owner's chart shows
`2026.11.23 00:00` while the epoch maps to `16:00 UTC`, the chart window is UTC+8 — again pointing at
the broker being on UTC+8, **not** UTC+1/UTC+2. One more reason to demand the broker offset rather
than assume it (P1-4).

### 3.2 P0-2 — can DATA_READY lie? (the exact code path)

```
MTF_SniperCopyBufferBounded(handle,count,buf,retries,warned,tag)      nadir2.mq5:43221
  calc = BarsCalculated(handle)
  if(calc < count+1) { if(!warned){warned=true; Print("… not ready (BarsCalculated ",calc," < ",count+1,") …");} return 0; }
  → ATR_H1:   -1 < 201   (i.e. calc≥201 required for a 200-bar shift=1 copy: indices 1..200)
  → RSI_M15:  -1 < 17    (16+1; same rule)
  CopyBuffer(…,shift=1,count,…) → full_ok ? advance : (retry_counter≤3 ⇒ retry, else warn+return 0)
  not-ready path does NOT touch retry_counter  ⇒ "after 0 waiting attempts" is the RE-READY line
                                                after a not-ready episode (warned_flag stays true)
```

`MTF_SniperZone_Update` (:44766) then enforces the **mandatory** set before publishing
`DATA_READY/RISK_INPUTS_ALIGNED` (:44830–44852):

| Input | Mandatory? | Failure ⇒ status |
|---|---|---|
| chart `g_atr` valid | yes | `CHART_ATR` |
| H1 ATR (`g_sniper_h1_atr`) | yes | `H1_ATR` |
| H1 ADX (`nadx==4`) | yes | `H1_ADX` |
| M15 ATR (`n_m15` + `m15_atr_last`) | yes | `M15_STRUCTURE_ATR` |
| M5 ATR (chart M5 only) | yes | `M5_EXECUTION_ATR` |
| H1/M15 stamps vs `iTime` | yes | `RISK_TIMEFRAME_CHANGED` |
| W1/D1/H4/M30 rates/ATR | **no** (optional macro zone sources) | none |
| RSI_M15 | **no** (C3 of five confirm conditions, `conds_met` counting) | none |

So the owner's sequence is real but not contradictory: `RSI_M15 not ready (-1 < 17)` can coexist
with a later `DATA_READY/RISK_INPUTS_ALIGNED` — the readiness word is scoped to the risk inputs the
stops and the H1 ADX validation gate need, and the log never qualified it. The mandatory handles
**cannot** be bypassed (that path returns early and invalidates the snapshot). The one true cosmetic
deception is the `after 0 waiting attempts` ready-line (P0-2c).

**Honest limit of this finding:** whether the M1 "SELL" ever depended on RSI_M15's C3 leg is not
visible here; the class of failure (optional-input-not-ready + published DATA_READY) is confirmed,
the occurrence on this trade is not.

### 3.3 P0-3 — zero comparisons can print PASS

Two separate zeros:

1. **The PMI self-test prints PASS with nothing compared.** `PMI_AuditDigestAsOf` increments
   `compared` only for levels with `lv_avail[i] ≥ 0 && ≤ d.bar && lv_type[i] != 0`
   (:13100–13105); inside the loop `compared_out++` fires only when a level survives those
   filters. `digests_stored < 2` short-circuits the whole replay (:13108–13115). Meanwhile
   `PMI_RunSelfTests` reports "Tests 1-4, 6" as PASS regardless of `compared`. A first build with a
   cold ring therefore prints PASS while having verified nothing — rule 5 of this audit (never a
   PASS on zero comparisons) is violated today.
2. **"test 5" does not exist.** There is no fifth test anywhere; the PASS text names one because
   it was copied from a document template. The honest line is `tests run: N, compared: M`.

`analyze_trial.py` (~:152) already implements the right shape:
`PASS / FAIL / INCONCLUSIVE` keyed off `min_sample_for_conclusion`. P0-3 adopts exactly that
contract for the PMI replay audit and the self-test summary.

### 3.4 P0-4 — why the EA cannot see the chart's config, and what can be fixed safely

Information flow today:

```
chart .set → VISUAL instance (PRACTICAL, input_hash=1763998980, config=CUSTOM)
EA iCustom(sym,tf,"nadir2")  —— passes NO inputs ——▶ EA_READER instance (compiled defaults, STRICT)
                                                    input_hash = EA_DEFAULT_hash = 602903429
                                                    INDICATOR_BUILD=UNVERIFIED (deliberate)
```

Observable facts: `INDICATOR_INPUTS=COMPILED DEFAULTS (no input list passed; a chart .set cannot
reach this instance)` — printed by design; `INDICATOR_BUILD=UNVERIFIED` — because the EA has no
channel to learn the reader's `__DATETIME__` or its inputs. The GV handshake proves an EA_READER
*started* (30 s TTL, role-scoped `H<role>_<hash>` publication, 300 s mismatch scan), nothing more.

**Safely fixable now (no approval):** the EA can read the same GVs the reader publishes — including
`input_hash`, `DEFAULT_HASH`, `DEFAULT_SEEN` — and print them at heartbeat with a computed
`config=CUSTOM/DEFAULT-equivalent` word (mirroring `QA_InstancePublish`'s own logic, EA-side, read-only).

**Not fixable without new channels or approval:** proving *which build* produced the buffers (needs a
per-init build GV → approval), and making the EA's effective thresholds identical to the chart's
(needs either an input list on the iCustom call — forbidden today by the trade/order flow design and by
`test_autotrader_contract`, which pins the verbatim call form — or a hard block on mismatch, which is
an entry-authority change → approval).

Until then, the truth line the operator must rely on is: **the EA trades compiled defaults, full stop.**
The chart may look permissive; the executor is STRICT. Any PR that changes this coupling is out of
scope for a pure-fix release.

---

## 4. P1-4 — session clock inventory (report-only)

All definitions found in source, mapped to UTC assuming **broker winter = UTC+1 (owner)** /
**configured = UTC+2 (`InpBrokerUTCOffsetWinterMinutes=120`, `BROKER_DST_EU`)**:

| Definition | Where | Clock used | Winter (owner / configured) | Summer (EU DST) |
|---|---|---|---|---|
| EA trade filter `InpSessionStartHour=10..InpSessionEndHour=18` | EA:393, `QER_SessionInside` :1998–2017 | broker server hour, half-open [10,18) | 09:00–17 / 08:00–16 | 09:00–17 / 08:00–16 |
| Indicator Asia session `InpAsianStart=9, InpAsianEnd=18` | nadir2:824 | **Tokyo local** via SessionLocalTime (UTC+9) | 00:00–09:00 UTC | 00:00–09:00 UTC |
| Indicator London session `8..16` | nadir2:825 | **London local** (DST-aware) | 08:00–16:00 | 07:00–15:00 |
| Indicator NY session `8..16` | nadir2:826 | **NY local** (DST-aware) | 13:00–21:00 | 12:00–20:00 |
| London kill zone `7..10` | nadir2:832 | London local | 07–10 / 07–10 | 06–09 / 06–09 |
| NY kill zone `7..10` | nadir2:833 | NY local | 12–15 | 11–14 |
| PMI banner "internal UTC … Algeria UTC+1" | nadir2:13458 | **fixed, non-DST** — matches nothing above | Asia 00–09 ✓iso, London 07–16 ✗, NY 12–21 ✗ | ✗ |
| Panel "Algeria UTC+1" | renderer banner | fixed +1, no DST | +1 | +1 |
| `InpArbSessionStartHour=-1` | QSMC_Preset:88 | off | — | — |
| QATS `0..0` | QATS:190 | off | — | — |

**Disagreements flagged:** (1) PMI banner vs indicator reality (banner must go). (2) EA 10–18 server
covers London cash + the NY open but **misses NY afternoon** — the owner's journal line
"outside the session window 10:00-18:00 server" firing on a mid-NY bar is this exact arithmetic, on
top of the winter offset question. (3) The configured winter offset (UTC+2), the owner's observation
(UTC+1) and the UTC+8 reading of the CE_HTF epochs (§3.1) are three different numbers — unverified
until the owner states the broker's real offset; if the broker is UTC+1 winter,
`InpBrokerUTCOffsetWinterMinutes=120` shifts **every** DST-derived session/anchor/VWAP boundary by
+1 h all winter. **No window, offset or rule is changed in this audit.** Each change above is tagged
with its approval status in the table.

---

## 5. Reconciliation with the 2026-11-16 audit (`docs/AUDIT_v6.6.24_2026-11-16.md`)

| 2026-11-16 item | State after this cycle |
|---|---|
| Class A fixes F-001…F-011 | **Unaffected.** This cycle touched nothing those fixes rely on. |
| Class B F-008/F-009 (`[needs owner approval]`) | Still pending owner decision; not re-opened here. |
| R1–R4 demo-trial deliverables (journal, analyze_trial, preflight, buffer diff) | Unchanged; R2's PASS/FAIL/INCONCLUSIVE contract is the design P0-3 adopts. |
| "Not read line-by-line: nadir2.mq5" | **Narrowed**, not eliminated: this cycle read the decision/publication/identity regions cited above; the file remains 45k lines and most rendering internals are still unaudited. |
| Definition-of-done of that cycle (demo attach) | Still open; F7 remains required. |

Nothing in this document supersedes the safety doctrine of the prior cycle; it extends it to the
misses that surfaced in the owner's 2026-11-23/24 journals.

---

## 6. Definition-of-done checklist (from the work order) vs this audit

| Done criterion | Status |
|---|---|
| No PASS on zero comparisons | **Defect confirmed** (P0-3); fix designed, not yet implemented. |
| DATA_READY never with a not-ready handle | Holds for **mandatory** handles; confirmed open for optional ones (P0-2); fix designed. |
| CausalInvariant passes on XAUUSD D1/W1, or failing event proven correctly rejected & never used | Event proven **rejected and never used** (code path §3.1); replay proof pending (P0-5b). |
| EA and indicator use identical effective thresholds or EA blocks loudly | **Neither is true today** (P0-4). Log additions designed; blocking = owner decision. |
| Single DailyRef feeds all daily/weekly levels | Mostly unified; **legacy shift-1 remnants + SVP pool path confirmed still divergent** (P1-1). |
| One log line per closed bar explaining the (non-)entry | Does not exist; P0-5a designs it. |
| Zero lookahead/repaint | No violation found in the regions read; the HTF chain is availability-stamped by construction (§3.1); P1-2 shows the *ingest* boundary has no sanity floor at all (data quality, not causality). |
| Zero leaks | No new leak found; instance-id `VISUAL_VISUAL_` prefix duplication confirmed (cosmetic, P2-3). |

---

## 7. What was run on this branch (evidence for the claims above)

```
python3 tools/test_el_sniper_readiness.py     PASS (native harness; copy gates, exhaustion, RSI_M15 shape)
python3 tools/test_el_data_integrity.py       PASS (native harness; not-ready/partial/recovery paths)
python3 tools/test_opportunity_funnel.py      PASS (native harness)
python3 tools/test_instance_identity.py       PASS (599-input fingerprint manifest)
python3 tools/test_why_no_trades.py           PASS
python3 tools/test_causal_chain_regressions.py PASS
python3 tools/test_compile_errors.py          PASS
python3 tools/test_edgebook_contract.py      (inspected; source-contract checks, not executed in this cycle)
```

None of these is an MQL5 compile. `F7` in MetaEditor on v6.6.24 + all dependents remains mandatory
before any fix PR merges. All seven suites were executed on this branch at `fea3ee3`; the branch is
otherwise untouched by this document.

## 8. PR sequence (each: description, tests, before/after log excerpt, "does not change entry thresholds" or approval tag)

1. **PR-1 · P0-3** — zero-comparison ⇒ INCONCLUSIVE; phantom test 5; replay-unarmed WARN. (No approval.)
2. **PR-2 · P0-2** — dual-unit ready line; not-ready wait counter; buffer-19 DATA_INCOMPLETE blocker
   (note: blocker emission = owner sign-off or log-only at owner's choice); native test `BarsCalculated=-1`.
3. **PR-3 · P0-1** — invariant FAIL prints raw epochs unconditionally; D1/W1 DST + non-DST native test;
   CE_HTF event never reused across re-init. (No approval.)
4. **PR-4 · P0-4** — heartbeat identity: `input_hash`/`EA_DEFAULT_hash` + `EFFECTIVE_THRESHOLDS` line +
   `INPUTS MISMATCH` word (log-only). (Approval only for the block-vs-log decision; default log-only.)
5. **PR-5 · P1-1** — legacy shift-1 call sites + SVP pool read onto `SPriorPeriodRef`; weekend/DST test.
6. **PR-6 · P1-2** — data-sanity gate at FVG/OB ingest (flag default, block behind approval).
7. **PR-7 · P0-5** — funnel instrumentation + files persistence + replay harness (diagnostics only).
8. **PR-8 · P2 items** — deinit outcomes line; `VISUAL_VISUAL_` prefix; clipped banner; one
   `EFFECTIVE THRESHOLDS` line folds into PR-4/PR-8; effective-threshold contradictions flagged.
9. **PR-9 · P1-4 docs** — clock inventory into `docs/`, PMI banner corrected to the computed line.
10. **Not in this sequence** (approval-gated, separate): P1-3 own-TF zone filter; P1-2 blocking mode;
    P0-4 hard-block on build/inputs mismatch; P1-4 offset/window changes; P2-2 session floor; any
    Class-B items from the 2026-11-16 cycle.

## 9. Owner decisions required (explicit list)

1. P0-2: are RSI_M15 / W1 / D1 / H4 / M30 **required** for DATA_READY? (Recommend: no change today;
   measure with P0-5 replay first.)
2. P0-2: buffer-19 blocker on DATA_INCOMPLETE — ship, or log-only this release?
3. P0-4: log-only mismatch warning at heartbeat (recommended), or hard block? Hard block is
   entry-authority → approval.
4. P0-4/P2-4: is the EA supposed to run compiled defaults, or should the owner attach a `.set` and
   pass an input list? (Today: compiled defaults, by design, enforced by contract test.)
5. P1-2: flag-only or block mode for out-of-history zones?
6. P1-3: after P0-5 replay quantifies the M1 starve-out, approve (or reject) the own-TF distance filter.
7. P1-4: the broker's real winter UTC offset (UTC+1? UTC+2? UTC+8?) and whether the EA window
   10–18 server should stay, become UTC-anchored, or follow London/NY locals.
8. P2-3: opt-in already exists — keep it, or auto-arm the counts-only ledger?
9. P0-1/P0-4: show `[needs owner approval]` before any change to what gets published or traded as a
   result of the replay's verdict on the missed SELL.

## 10. Appendix — epoch quick reference (this audit)

```
1795190400 = 2026-11-20 16:00:00 UTC (Friday)
1795449600 = 2026-11-23 16:00:00 UTC (Monday, = event+3·86400)
1795507200 = 2026-11-24 08:00:00 UTC (Tuesday, seen as a diagram epoch elsewhere)
D1/W1 boundaries at a 16:00 UTC wall clock imply a UTC+8 day-open server.
Configured winter offset = 120 min (UTC+2); owner observation = UTC+1; CE_HTF epochs ⇒ UTC+8.
```

*This document is the deliverable for STEP 0 (audit). No code, threshold, window, limit or gate has
been changed by this document. Every claim above is either labelled in the table or explicitly out
of scope.*
