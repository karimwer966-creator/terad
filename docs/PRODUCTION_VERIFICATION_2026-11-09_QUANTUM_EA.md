# INDEPENDENT ENGINEERING VERIFICATION — QuantumAutonomousTradingSystem
### Phases 1–7 · v1.10 · 2026-11-09 · branch `arena/f83fc236-terad` · PR #56

Status key: **PASS** = verified here · **FAIL** = verified broken · **BLOCKED** = cannot be done in this
environment (blocker named) · **NOT TESTED** = no claim.
**Acceptance condition (compile + attach + verified BUY/SELL on MT5 DEMO) is NOT MET and is not claimed.**

> **Superseded in part by v1.20 (2026-11-11).** Three rows of section 1B were judgements from reading the source
> and were wrong once the source was executed: "BUY/SELL symmetry — PASS" (the direction was picked before
> scoring; only one side was scored; a mirrored market did not produce mirrored trades), "Liquidity sweep"
> (a sweep never expired and could be re-detected against any older level) and "Duplicate signals" (the same
> setup was re-entered on the next M5 bar). Fix 3 of section 1A (losses counted per deal on `DEAL_PROFIT`) was
> itself replaced by per-position netting. The DEMO journal of 2026-11-11 — three BUY fills, no SELL ever
> scored for 9.5 hours — is the field evidence. See
> [`QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md`](QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md). The acceptance condition
> above is still NOT MET.

---

## PHASE 1 — SOURCE CODE AUDIT

### 1A. Logic bugs found and FIXED in v1.10

| # | Severity | Location | Bug | Fix |
|---|---|---|---|---|
| 1 | **Critical** | `UpdateDailyGuards()` | Equity high-water mark was never persisted on first sight. `GVGet(hwmKey, equity)` re-initialised to *current* equity every tick ⇒ DD measured from now ⇒ **account-drawdown halt could never engage**. | `if(!GlobalVariableCheck(hwmKey)) GVSet(hwmKey, equity);` then read/compare — HWM now persists across ticks and reloads. |
| 2 | **High** | `PartialClose()` | Raw `TRADE_ACTION_DEAL` with `position=ticket` is hedging-specific. On **netting** accounts (all positions of a symbol netted) the position field is not used — sending it risks retcode refusal of the partial bank. | `position` is now set **only** when `ACCOUNT_MARGIN_MODE == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`; netting/exchange omit it (opposite deal reduces the net position, per MQL5 semantics). |
| 3 | **High** | `ProcessClosedDeals()` | Any `OUT` deal with `PROFIT+SWAP+COMMISSION < 0` counted as a "losing close". **Breakeven/commission-only deals therefore armed the consecutive-loss breaker** and could stand the EA down while the strategy was flat. | A deal is a loss **iff `DEAL_PROFIT < 0`**; `DEAL_PROFIT == 0` is explicitly NEUTRAL and never increments the breaker. Also: stale partial-bank markers (`pc_<ticket>`) are now deleted when their position closes (`DEAL_POSITION_ID`). |
| 4 | Medium | `IsStopValid()` (break-even guard) | Validated the re-targeted SL against `SYMBOL_TRADE_STOPS_LEVEL` only. Brokers may freeze modifications whose distance is inside **`SYMBOL_TRADE_FREEZE_LEVEL`**, which can exceed the stops level — the protective break-even move could be rejected server-side. | Uses `MathMax(stopsLevel, freezeLevel)` (same standard as the plan validator). |
| 5 | Low | `OnInit()` fatal path | If any `iMA/iATR` handle failed, previously created handles were leaked (terminal keeps indicator instances until deinit). | New `ReleaseHandles()` (also used by `OnDeinit`) is called on the failure path. |
| 6 | Low | `DetectSweep()` | `levelOut` parameter was written but never read (dead output parameter). | Parameter removed; signature simplified; callers updated. |
| 7 | Low | `VerifyPositionOpened()` | A confirmed position logged the ticket but not the **server-side** SL/TP — impossible to see from the journal whether the broker actually applied protection. | Confirmation now also prints `[QATS][VERIFY] server-side SL=… TP=… openPrice=… volume=…`. |
| 8 | Low | `SessionVWAP()` | The loop included the **forming** M5 bar — inconsistent with the closed-candle doctrine. | Forming bar (shift 0) excluded (loop `i >= 1`). |
| 9 | Medium (dead feature) | Scoring engine | `r.vwap` was computed on every analysis and **never used** — dead computation. | Session VWAP is now a symmetric confluence component (+5 when price agrees with direction) and printed in the reason line. |
| 10 | Cosmetic | `BuildTradePlan()` | Stale placeholder comment ("below opposite OB origin…") with no code behind it. | Removed. |
| 11 | Medium (perf) | `SessionVWAP()` | The loop started at the **oldest** loaded bar and walked all history until the day boundary — O(history) `iTime` reads on every new M5 bar. | Iterates newest→oldest closed bars, stopping at the day boundary (≤ ~288 iterations). |

### 1B. Audited-and-correct components (no change needed)

| Area | Verdict | Evidence |
|---|---|---|
| Closed-candle enforcement | **PASS** (all decision reads use shift ≥ 1; `iTime(…,0)` used only for new-bar detection) | grep + manual trace |
| Look-ahead bias | **None found** — D1/W1 references use shift-1 closed periods; swings require right-side closed bars | `FindSwings`, `BuildLiquidityPools`, `iHigh(D1,1)` |
| Bar-time repaint | **None** — no objects anchored to shift 0 on the signal path; everything shifts with closed bars | manual |
| BOS/MSS detection | Correct closed-break semantics; both sides symmetric | `AnalyzeMarket` §11 |
| Swing confirmation | Newest usable swing at shift `k+1` (3 for k=2); never touches shift 0/1 for structure | `FindSwings` |
| Liquidity sweep | Requires a **closed** bar piercing the pool then closing back inside; bull/bear tracked independently | `DetectSweep` |
| OB/FVG validity | OB = last opposite closed candle before the impulse; FVG = 3-candle closed-bar imbalance; zone bounds are candle extremes | `FindOrderBlock`, `FindFVG` |
| Premium/Discount | Dealing range from last `InpSwingLookback` **closed** H1 bars; buys favour discount, sells premium | `DealingRangePosition` |
| Candle confirmation (M15/M5) | Closed bars only; symmetric engulfing/pin/marubozu | `M15Confirms`, `M5Trigger` |
| BUY/SELL symmetry | Bull and bear paths are parallel; scoring mirrored (`dir>0 ? … : …`); SL/TP mirrored; BE move mirrored; flip close symmetric | full pass |
| Duplicate signals | One decision per new closed M5 bar + one-position cap (magic+symbol) + pending-retry serialization + per-day trade cap | `OnTick`, `EntriesAllowed`, GVs |
| D1/H4/H1/M15/M5 sync | Independent per-TF closed reads from `TimeTradeServer()` state; no mixed timeframes arrays; no caching across ticks | `LoadReading` |
| Netting/Heding partial close & position identification | Netting-aware after fix #2; identification is magic+symbol scan everywhere | `CountMyPositions`, `VerifyPositionOpened`, `ManagePositions` |
| Internal consistency | 42 inputs / 34 globals / 54 functions — every reference resolves; zero duplicate definitions; zero format-string mismatches (rescanned post-fix) | `tools/verify_quantum_ea.py` |

---

## PHASE 2 — RISK ENGINE VALIDATION (calculation-verified offline; runtime NOT TESTED)

The EA's exact algorithm (`EffectiveRiskPercent` + `CalcPositionVolume` incl. step-floor, clamps and the
margin shrink-loop) was re-implemented in a reference simulator and executed against a broker-spec matrix.
Tick economics drive the math (`(StopDist ÷ TickSize) × TickValue`), so the numbers are contract-size
independent by construction (`SYMBOL_TRADE_CONTRACT_SIZE` is loaded and printed, never assumed).

**Specs used** (typical broker conditions, all values from the broker at runtime in the EA):

XAUUSD: tickSize 0.01, tickValue $1.00, step 0.01, min 0.01, contract 100, 1:100 ·
EURUSD: tickSize 1e-5, tickValue $1.00, step 0.01, min 0.01, contract 100,000, 1:30 ·
US30: tickSize 1.0, tickValue $1.00, step 1.0, min 1.0, contract 1, 1:20 ·
GBPJPY: tickSize 1e-3, tickValue **$0.66** (profit ccy JPY — see note), step 0.01, min 0.01, contract 100,000, 1:30

| Case | Equity | Risk input | Stop | Applied rp | Volume | Actual risk | Verdict |
|---|---|---|---|---|---|---|---|
| XAUUSD | 500 | 0.50% | $20 | 0.50% | — | — | **REFUSED** (below broker min 0.01 lot) |
| XAUUSD | 2,000 | 0.50% | $20 | 0.50% | — | — | **REFUSED** (below min) |
| XAUUSD | 5,000 | 0.50% | $20 | 0.50% | 0.01 | $20.00 (0.40%) | OK |
| XAUUSD | 10,000 | 0.50% | $20 | 0.50% | 0.02 | $40.00 (0.40%) | OK |
| XAUUSD | 50,000 | 0.50% | $20 | 0.50% | 0.12 | $240.00 (0.48%) | OK |
| XAUUSD | 5,000 | 0.50% | $50 | 0.50% | — | — | **REFUSED** (below min) |
| XAUUSD | 5,000 | 0.50% | $100 | 0.50% | — | — | **REFUSED** (below min) |
| EURUSD | 500 | 1.00% | 80 pips | 1.00% | — | — | **REFUSED** (below min) |
| EURUSD | 1,000 | 1.00% | 80 pips | 1.00% | 0.01 | $8.00 (0.80%) | OK |
| EURUSD | 5,000 | 1.00% | 80 pips | 1.00% | 0.06 | $48.00 (0.96%) | OK |
| EURUSD | 10,000 | 1.00% | 80 pips | 1.00% | 0.12 | $96.00 (0.96%) | OK |
| EURUSD | 100,000 | 1.00% | 80 pips | 1.00% | 1.25 | $1,000.00 (1.00%) | OK |
| US30 | 5,000 | 1.00% | 250 pts | 1.00% | — | — | **REFUSED** (min 1.0 lot) |
| US30 | 10,000 | 1.00% | 250 pts | 1.00% | — | — | **REFUSED** (margin/risk mismatch: 0.4 lots < min 1) |
| US30 | 50,000 | 1.00% | 250 pts | 1.00% | 2.00 | $500.00 (1.00%) | OK |
| GBPJPY | 10,000 | 1.00% | 150 pips | 1.00% | 0.01 | $9.90 (0.10%) | OK — **margin-capped**, see below |
| HARDCAP probe | 10,000 | 5.00% in / 5.00% ceiling | 80 pips | **2.00%** | 0.20 | $200.00 (2.00%) | Hard cap binds ✓ |
| EffectiveRiskPercent resolution | — | (0.5,1.0)→0.50 · (2.5,1.0)→1.00 · (5,5)→**2.00** · (5,1)→1.00 · (0,1)→0.01 · (−1,1)→0.01 | | | | | |

**Margin shrink-to-fit (proof with real numbers):**

| Case | Risk-calc volume | Margin needed | Cap (90% × free) | Shrunk to | Final margin | Result |
|---|---|---|---|---|---|---|
| EURUSD, eq $100k, **1:1 leverage** | 1.25 lots | $137,500 | $90,000 | **0.81 lots** | $89,100 | risk $648 (0.65%) — fits |
| GBPJPY, eq $10k, 1:30 | 0.10 lots | $65,000 | $9,000 | **0.01 lots** | $6,500 | risk $9.90 (0.10%) — fits |

Loop invariant verified: strictly decreasing by exactly one volume step per iteration ⇒ terminates;
if even `volMin` does not fit, the trade is REFUSED with a logged reason.

**Account currency conversion:** risk P/L is taken from `SYMBOL_TRADE_TICK_VALUE`, which MT5 reports in the
account deposit currency — the conversion happens broker-side and is currency-agnostic in the formula; margin
affordability is delegated to `OrderCalcMargin` (server-side, cross-currency aware). Margin-vs-profit currency
divergence is therefore handled without special cases. This is the *intended* MT5 mechanism (verified by MT5 API
semantics, not by a live fill).

**Netting vs Hedging:** identification of positions is magic+symbol everywhere (`PositionGetTicket` scan) —
works in both modes. Partial close is netting-aware after fix #3. In netting mode one symbol = one net
position, so `InpMaxOpenPositions=1` yields the same observable cap; in hedging mode the cap enforces one
independent position per magic+symbol. CTrade `PositionClose` is mode-aware natively.

**Over-risk rejection:** any computed loss-per-stop above the effective risk is *impossible* by construction
(vol is derived from it); refusal happens at broker-min volume, at the margin shrink floor, at `InpMinRR`,
at spread/stop fraction, or at any guard in Phase 4. **Risk is never elevated to recover losses** — no input
or code path scales risk up after a loss; the only loss-driven paths lower activity (stand-down/lock).

**Verdict Phase 2:** calculation **PASS (offline reference)**. Runtime behavior on a live DEMO: **NOT TESTED**.

---

## PHASE 3 — EXECUTION ENGINE

| Requirement | Implementation | Status |
|---|---|---|
| BUY / SELL market execution | `CTrade::Buy/Sell` with explicit sl/tp, deviation, magic, comment | **Implemented** (runtime NOT TESTED) |
| Server-side SL / TP | SL & TP passed on every `Buy/Sell`; verified server copy in `[QATS][VERIFY]` (fix #7) | **Implemented** |
| Retcode classification | transient `{10004,10012,10020,10021,10024,10031}` → ≤3 retries, ≥5 s apart, budget-persisted; permanent → signal abandoned; nothing else is "success" | **Implemented** |
| Actual deal confirmation | success = `TRADE_RETCODE_DONE/DONE_PARTIAL` **and** a fresh magic+symbol matching position found within 120 s; else `[CRITICAL]` | **Implemented** |
| Duplicate prevention | one position cap + retry serialization + new-bar gate + per-day cap + pending-order arena | **Implemented** |
| Slippage | `InpDeviationPoints` on open, close, partial close, retry | **Implemented** |
| Spread | absolute cap + fraction-of-stop cap; re-checked inside `ExecuteSignal` before send | **Implemented** |
| Market closure / broker restrictions | `SYMBOL_TRADE_MODE_FULL` required; refusal if the symbol/server is not full-trade; `MARKET_CLOSED` retcode lands in the permanent class → abandoned + logged | **Implemented** |
| Position verification (not "sent = filled") | `VerifyPositionOpened()` gate above | **Implemented** |
| Fill-price slippage honesty | entry price taken live from ASK/BID at decision time; SL/TP absolute — broker-enforced at server | **Implemented** |
| Partial fill | `DONE_PARTIAL` accepted, logged with actual volume; BE/partial logic works on the remaining volume | **Implemented** |

**Verdict Phase 3:** engineering **PASS by construction + review**; live server behavior (fills, retcodes,
freeze/stop adjustments by the broker) **NOT TESTED**.

---

## PHASE 4 — CAPITAL PROTECTION

| Control | Mechanism | Restart persistence | Status |
|---|---|---|---|
| Daily loss | equity baseline keyed `daybase_<yyyymmdd>`; lock when loss ≥ 2% (or money stop) | Persisted (GV) | PASS (design) |
| Account drawdown | equity high-water mark `…_hwm`; entries halt at 8% off peak — **fixed in v1.10 (was dead)** | Persisted | PASS (design) |
| Consecutive losses | watermark ticket `last_deal` + counter `consec_losses`; ≥3 losing `DEAL_PROFIT<0` → `cooldown_until` (+60 min); a win resets | Persisted | PASS (design) |
| Daily trade cap | counter `trades_<yyyymmdd>` ≤ 4 | Persisted | PASS (design) |
| Emergency stop | every position carries SL; SL-missing position detected each tick → ATR-based SL rebuilt immediately; failure logged `[CRITICAL]` | Per-tick | PASS (design) |
| Restart persistence | all guards (lock/HWM/consec/cooldown/trades/watermark) in date- or account-keyed terminal globals; chart reload cannot re-base them | Persisted | PASS (design) |
| Risk escalation after losses | **impossible by construction**: no path scales risk up; EffectiveRisk is clamped; loss only lowers activity | n/a | PASS |
| Max simultaneous exposure | `InpMaxOpenPositions` = 1 (magic+symbol); one chart per symbol | n/a | PASS |
| No fixed balance anywhere | all risk scales with live equity | n/a | PASS |

**Verdict Phase 4:** design **PASS**; live tripping of any guard **NOT TESTED**.

---

## PHASE 5 — COMPILATION — **BLOCKED**

MetaEditor does not exist in this environment (Linux sandbox, 2026-11-09), and cannot be obtained:

```
$ which wine wine64                 → (empty)
$ curl -sI https://download.mql5.com/...mt5setup.exe  → HTTP 000 (exit 35, SSL connect error)
$ curl -sI https://www.metatrader5.com/en/terminal/download → HTTP 000 (exit 35)
$ pip index versions MetaTrader5    → No matching distribution found (Windows-only bridge)
```

Substitutes performed (none is a compiler): structural verifier (PASS), format-string audit (0 mismatches),
full manual line-by-line review of all 1,809+ lines including the v1.10 delta.

**The EA has NOT been compiled. No `.ex5` exists. No "compiles cleanly" claim is made.**
v1.10 must be compiled with F7 and the output captured before any production claim.

## PHASE 6 — DEMO FORWARD EXECUTION — **BLOCKED**

No MT5 terminal, no broker connection, no DEMO credentials are available. No ticks were received,
no order was sent, no ticket/deal exists. No trade was forced, no result fabricated.

## PHASE 7 — FINAL REPORT

### Bugs fixed in v1.10 (this verification round)
10 functional fixes (incl. one performance defect) + 1 audit-dead-code removal — see Phase 1 table (HWM persistence, netting partial close,
breakeven-deal classification, freeze-level BE guard, handle-leak on failed init, dead parameter, server SL/TP
logging, VWAP forming-bar exclusion, VWAP made a scored confluence, stale comment).

### Risk calculation test cases
18-case matrix + 3 margin shrink proofs + effective-risk resolution matrix — Phase 2 table.
Calculation **PASS (offline)**; runtime **NOT TESTED**.

### Compilation evidence — **BLOCKED** (see Phase 5)
### DEMO execution evidence — **BLOCKED** (see Phase 6)
### BUY / SELL ticket & deal — **NOT AVAILABLE (none; none fabricated)**
### SL/TP confirmation — **NOT TESTED** (server print exists in code; never ran against a broker)

### Remaining blockers (exact)
1. Windows machine with MetaEditor (or Wine + MT5 installer).
2. F7 compile of `MQL5/Experts/QuantumAutonomousTradingSystem.mq5`; capture the 0/0 output; save the `.ex5`.
3. MT5 logged into a DEMO account; Algo Trading enabled.
4. Attach; confirm attach banner (`PROTECTION: PASS`, `data pipeline OK`).
5. Wait for a real setup; confirm `[QATS][VERIFY] POSITION CONFIRMED` for a BUY and a SELL;
   record tickets/deals + server SL/TP; confirm BE/partial behaviour live.
6. If the market prints no qualifying closed-bar confluence (score ≥ 65), the EA stays flat and logs the exact
   missing component — this is designed behaviour, not a failure.

### Exact final deployment file
`MQL5/Experts/QuantumAutonomousTradingSystem.mq5` (v1.10) — compile to `QuantumAutonomousTradingSystem.ex5`.

### Acceptance condition status
"Compiles + attaches + verified BUY and SELL executions on MT5 DEMO" — **NOT SATISFIED / NOT CLAIMED.**
The engineering is as complete as this environment permits; the remaining gates are mechanical and are listed above.

### Honest one-liner
A reviewed, hardened, self-contained DEMO-only EA — **not yet a proven trading system**. The next proof is F7,
then a live DEMO chart; until both exist, this code owes you evidence, not confidence.
