# QATS v1.20 — why the EA only bought, what was changed, and what is proven
### `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` · v1.11 → v1.20 · 2026-11-11 · branch `arena/67f13fdd-terad`

Status key: **PASS** = verified here · **FAIL** = verified broken · **NOT RUN** = could not be done in this
environment (blocker named) · no claim is made about anything marked NOT RUN.

Arabic operator guide: [`QATS_DUAL_DIRECTION_AR.md`](QATS_DUAL_DIRECTION_AR.md) ·
full backtest tables: [`QATS_BACKTEST_STUDY_2026-11-11.md`](QATS_BACKTEST_STUDY_2026-11-11.md)

---

## 0. The answer on one screen

| question | answer | status |
|---|---|---|
| Why did v1.11 open only BUY trades on 2026-11-11? | The direction was chosen **before** scoring, from an exclusive "sweep" flag; only that one side was ever scored. A stale bullish sweep held the flag for about 9.5 hours, so SELL was not evaluated at all — on a day whose D1 bias was bearish. Section 2. | root cause reproduced in simulation |
| Is BUY/SELL treatment equal now? | Yes. One function builds the evidence for both sides on every closed M5 bar; a price-mirrored market produces the exact mirror trades. Section 5. | **PASS** (offline) |
| Is the journal traceable now? | Yes: `[QATS][BUY\|SELL][DETECTED]`, `[QATS][SIGNAL][SCORED]`, `[QATS][SIGNAL][CONFLICT]`, `[QATS][BLOCK][REASON]`, `[QATS][EXECUTION][APPROVED\|REJECTED\|FILLED]`, `[QATS][COOLDOWN]`, `[QATS][STATS]`. Section 4. | **PASS** (offline) |
| Was "consecLosses=0 cooldown=YES" a bug? | A legitimate running timer with a misleading display — plus four real defects in how losses were counted. Section 2.5. | fixed, **PASS** (offline) |
| MetaEditor compile, 0 errors / 0 warnings? | **NOT RUN.** There is no MetaEditor on this Linux host. The whole file does build with a strict host C++ compiler against a typed MQL5 shim (0 errors, 0 warnings, 57 gate checks) — that is evidence, not proof. Section 7.1. | **NOT RUN** |
| MT5 Strategy Tester? | **NOT RUN.** No MT5 terminal here. An offline replay of the real source on 9.6 years of M1 data was run instead. Section 6. | **NOT RUN** |
| DEMO forward test of v1.20? | **NOT RUN.** The only broker evidence is the operator's v1.11 journal: 3 BUY fills, 0 SELL fills. Section 7.3 is the procedure. | **NOT RUN** |
| Is the strategy profitable? | **Not demonstrated, and the simulation says no.** In-sample expectancy is negative for v1.11 **and** for v1.20, in every year, in both directions. Section 6. | **FAIL** (simulation) |
| Production-ready? | **No.** Section 8. | — |

The direction bias, the missing transparency and the cooldown accounting were engineering defects, and they are
repaired and tested. Whether the strategy makes money is a different question; nothing in this work shows that it
does, and no filter was added to make a backtest look better.

---

## 1. What the DEMO journal of 2026-11-11 shows (v1.11, XAUUSD)

Facts read from the operator's Experts journal (terminal clock = broker clock − 1 h; times below are broker time).

- Symbol: 2 digits, point 0.01, contract 100, lot step 0.01, stops level 0, filling mode IOC only.
  Inputs: compiled defaults (risk 0.5 %, daily loss 2 %, drawdown halt 8 %, 4 trades/day, 1 position,
  3 losses → 60 min stand-down, minimum score 55).
- **02:30 – 11:55: every single bar says `direction=BUY`.** One score per bar. The context on those bars was
  `D1=-1 H4=+0` with `sweep=BULL_SWEEP` — the same sweep, bar after bar, for about 9.5 hours.
- 02:30 – 07:55: BUY rejected, "score N below minimum 55" (N between 30 and 50).
- **Three BUY orders were filled** (retcode 10009, server-side SL/TP verified). All three were against the D1 bias,
  in the premium half of the range, with `M15=no M5=no` and a target about 90 USD away (planned R:R 15.7 – 18.5):

  | broker time | volume @ price | result | counted as |
  |---|---|---|---|
  | 06:59:59 | 0.05 @ 4058.44 | break-even scratch, −1.15 | loss 1 |
  | 09:05:00 | 0.06 @ 4058.65 | stop, −29.34 | loss 2 |
  | 10:15:00 | 0.06 @ 4053.88 — **36 s after the previous stop-out, on the same setup** | stop, −30.60 | loss 3 |

- 10:25: stand-down for 60 minutes; the heartbeat then prints `consecLosses=0 … cooldown=YES`.
  The daily cap (4/4) was reached as well, but only one reason was ever logged.
- **12:00: the first SELL line of the day** — score 55 with `disp=no M15=no M5=no` — blocked by the cooldown.
- **Zero SELL executions.**
- Equity moved by about ±100 USD while the EA had no position: other positions on the account feed the
  equity-based guards (daily loss, drawdown).

What this journal proves about the broker: a BUY market order with SL/TP is accepted and protected server-side.
It proves nothing about SELL execution — none was ever sent.

---

## 2. Root causes in v1.11

Every item was verified in the v1.11 source (commit `34156cc9`) and, where it has runtime behaviour, reproduced by
executing that source in the simulator (`tools/qats_backtest.py --baseline`, `qats_<tag> repro …`).

### 2.1 The direction was decided before anything was scored (the BUY-only cause)

```mql5
// v1.11 AnalyzeMarket()
int dir = 0;
if(sweepBull && !sweepBear)      dir = +1;      // <- an exclusive flag picks the side
else if(sweepBear && !sweepBull) dir = -1;
else if(a.h1Struct != 0 && a.h4Bias != 0 && ((a.h1Struct > 0) == (a.h4Bias > 0))) dir = a.h1Struct;
else if(a.d1Bias != 0)           dir = a.d1Bias;
else if(a.h4Bias != 0)           dir = a.h4Bias;
...
if(dir != 0) { /* score THIS side only */ }
```

Only the chosen side received a score. While `sweepBull` was true and `sweepBear` was false, a SELL could not be
detected, scored, logged or traded, whatever the rest of the market said.

### 2.2 The sweep flag went stale

`DetectSweep()` accepted **any** older swing low that one of the last four H1 bars dipped under and closed back
above. It never asked whether that level had already been taken, and it never expired a sweep whose rejection had
failed. In a drifting market each new H1 bar re-qualifies against some other old low, so the flag — and with it
the direction — stays put for hours.

### 2.3 A sweep plus free points reached the threshold without any confirmation

v1.11 weights: D1 20, H4 15, H1 20 — **or 10 points for free when H1 was undecided** —, sweep 15, displacement 10,
zone 10/5, premium/discount 5, volume 5, VWAP 5, M15 5, M5 5. A sweep, the free H1 points and a few minor items
reach 55 with **no displacement and no break of structure**. That is how three counter-D1 BUYs with
`M15=no M5=no` were taken.

### 2.4 The trade plan

- The target was the extreme of the last 120 H1 bars: about 90 USD away, R:R near 15. It is almost never reached,
  so the position lives or dies on the break-even stop.
- The SELL stop ignored the spread: a SELL is closed on the ASK, so its stop triggered one spread earlier than
  the BUY mirror image would.
- The duplicate guard was keyed by the M5 bar only. A new bar was a new "signal", so the same stale setup was
  re-entered 36 seconds after it had just been stopped out.

### 2.5 Loss streak and cooldown

| # | v1.11 behaviour | consequence |
|---|---|---|
| a | The streak counter is zeroed at the moment the stand-down starts. | `consecLosses=0 cooldown=YES` is a correct timer shown in a misleading way: nothing says when it started, what triggered it or when it ends. |
| b | Losses are counted per **deal**, on `DEAL_PROFIT` alone. | Commission and swap are ignored; a partial close and the final close of one position are two "results". |
| c | A deal is only considered when it carries the EA's magic. | A stop-out or a manual close carries magic 0 in some paths and is skipped. |
| d | Counting happens on a new M5 bar only. | A stop-out is noticed up to five minutes late; an entry on the very next bar can slip in first. |
| e | `EntriesAllowed()` returns at the first block. | Cooldown and daily cap were both active on 2026-11-11; the journal named one. |
| f | The drawdown halt latches without a journal line. | The EA goes silent and nothing says why. |

### 2.6 Execution paths that only fail in rare situations

| # | defect | reproduction (v1.11 → v1.20) |
|---|---|---|
| g | `ConfigureTrade()` ran only inside the first entry. After a restart with a position open, a management close was sent with magic 0 and the default deviation. | `repro restart`: closing deal magic **0**, no `[QATS][DEAL]` line → magic **26011091**, one line |
| h | On a non-XAUUSD symbol a queued retry was re-submitted with `score=0`, classed REJECTED, and the pending flag was never cleared. | `repro retry`, one requote: **339** `[QATS][RETRY]` lines, entries blocked for **16** bars by "order retry pending", **2** positions opened → **1** retry line, 0 blocked bars, 1 position |
| i | Live re-validation of the quote and the stop geometry ran for XAUUSD only. | now for every symbol |
| j | The `[QATS][DEAL]` line was printed twice per deal. | once |

### 2.7 The engine was not direction-symmetric

Replaying 2019 on an integer price grid, once as recorded and once price-mirrored: v1.11 takes 533 BUY / 357 SELL
on the original feed and 398 BUY / 495 SELL on the mirrored one, and ends on different balances. A symmetric
engine must swap the two counts exactly.

---

## 3. v1.20 — the dual-direction engine

### 3.1 Four classes of filter, named in the source

| class | what | can it be switched off? |
|---|---|---|
| **MANDATORY RISK PROTECTION** | account authorization, master switch, daily loss lock, drawdown halt, loss cooldown, daily trade cap, session, stale tick, spread, position cap, opposite position, one entry per setup, stop/target geometry, sizing, margin | inputs within the code hard caps (2 % risk, 5 % daily, 15 % drawdown) |
| **CORE STRATEGY CONFIRMATION** | liquidity sweep, displacement, BOS/CHoCH — as demanded by `InpStrategyProfile` | choose the profile; "none" is not an option |
| **OPTIONAL CONFLUENCE** | D1 bias, H4 bias, order block / FVG, premium–discount, VWAP, volume, M15, M5 | they only add score |
| **INFORMATIONAL ONLY** | breakout acceptance of a pool, signal class, the XAUUSD EMA / counter-D1 "vetoes" | never gate an XAUUSD entry |

### 3.2 Core gate — `InpStrategyProfile`

| value | profile | a setup needs | a sweep alone |
|---|---|---|---|
| 0 | CONSERVATIVE | sweep **and** displacement **and** BOS/CHoCH **and** (M15 or M5) | no trade |
| 1 | **BALANCED** (default) | displacement **and** BOS/CHoCH; sweep and M15/M5 add score | no trade |
| 2 | ACTIVE | any two of sweep / displacement / BOS-CHoCH | no trade |

The score is only consulted after the core gate has passed. A liquidity sweep on its own passes no profile.

### 3.3 Weights — one table for both sides, sum exactly 100, absent evidence scores 0

| D1 bias | H4 bias | structure | sweep | displacement | zone touched (or merely present) | location | VWAP | volume | M15 | M5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 17 | 13 | 17 | 13 | 9 | 9 (4) | 4 | 4 | 4 | 5 | 5 |

The "10 free points when H1 is undecided" are gone. Every `[QATS][SIGNAL][SCORED]` line lists each weight with the
points it earned; the listed points always add up to the printed score (checked on every bar of every replay).

### 3.4 One function, called twice

`EvaluateSide(+1 …)` and `EvaluateSide(-1 …)` are the same code; a single `bull` flag flips every comparison.
Each call returns the full evidence of its side: bias, structure, sweep, displacement, zones, location, VWAP,
volume, M15, M5, score, core verdict, setup identity. There is no default side and no shared "direction" variable
that one side could occupy.

**Direction policy** (`QATS_ResolveDirection`), deterministic and symmetric:

1. only one side eligible → that side;
2. both eligible → the higher score, if it leads by `InpConflictMargin` (10) points;
3. else the H1 structure trend; 4. else the D1 bias; 5. else the H4 bias;
6. else **stand aside** (`CONFLICT_UNRESOLVED`).

The EA never holds both sides: an open opposite position either is closed by an eligible opposite setup
(`InpCloseOnOpposite`) or blocks the entry (`OPPOSITE_POSITION`).

### 3.5 Structure and liquidity

- `BuildStructure()` walks the closed H1 bars causally. A close beyond the last confirmed swing is a break: with
  the trend a **BOS**, against it a **CHoCH**. A swing is consumed by the break that crosses it.
- `BuildLiquidityMap()` classifies every pool — swing highs/lows, equal highs/lows, prior day and prior week
  extremes — on both sides:

  | state | meaning | used as |
  |---|---|---|
  | INTACT | never traded through | take-profit target |
  | SWEPT | run, then closed back inside within the window, and the extreme has held | reversal evidence |
  | ACCEPTED | run, two closes beyond | breakout — informational, not a sweep |
  | SPENT | run earlier, or the rejection failed later | nothing |

  A sweep therefore **expires** (`InpSetupWindowBars`, 6 H1 bars) and **dies** when price closes beyond its
  extreme. That is the repair for 2.2.
- Displacement is only counted at or after the sweep it is supposed to confirm.

### 3.6 One entry per setup

A setup's identity is the H1 bar of its structural event (the BOS/CHoCH bar, else the sweep rejection bar), per
direction. The identity of the last setup that became a position is persisted; the same setup cannot open a second
position (`DUPLICATE_SETUP`). That is the repair for the 36-second re-entry.

### 3.7 Trade plan

- Stop: the wider of 1.5 × ATR(M5) and the 3-bar M5 extreme, plus the broker stops level. A SELL stop sits one
  spread above the chart level, because a SELL is closed on the ASK.
- Target: the **nearest INTACT opposing pool that pays at least `InpMinRR`**; otherwise `InpRewardRisk` × stop.
  Average planned R:R in the study is about 3.5 instead of about 14.
- Stops are snapped away from the entry, liquidity targets toward it, to the broker tick size.

### 3.8 Loss streak and cooldown

- Results are counted per **position**, from the deal history: all deals of a position are netted
  (profit + swap + commission + fee), and a position belongs to the EA when its **entry** deal carries the magic,
  whoever closed it. A partially closed position is counted once, when it is flat.
- Counting runs in `OnTradeTransaction`, at the closing deal, and again on every new bar before the analysis.
- The state is explicit and persisted: `cooldown_start`, `cooldown_until`, `cooldown_trigger`. Every transition is
  journalled: `[QATS][COOLDOWN] state=STARTED|EXPIRED|REPAIRED|CLEARED …`. A persisted state that cannot be
  legitimate (expiry further away than one full stand-down, start after expiry, negative streak) is repaired and
  the repair is printed.
- The heartbeat now prints `cooldown=YES(trigger=3 losses,start=…,until=…,remaining=…s)`.
- `InpNeutralCloseR` (default **0.0**): a close within ± this fraction of 1R is neutral for the streak.
  At 0.0 every net loss counts — including a break-even scratch that lost the slippage, like the −1.15 trade of
  2026-11-11. Raising it (0.10, say) makes such a scratch neutral. It is an operator decision and the default
  deliberately does not relax a protection.

### 3.9 Guards name every active block

`GuardBlocks()` evaluates the whole chain on every pass. `[QATS][BLOCK][REASON] … reasons=LOSS_COOLDOWN,DAILY_TRADE_CAP`
lists all of them. The drawdown halt and its release are journalled.

### 3.10 New inputs (50 inputs in total; the preset carries all of them)

| input | default | meaning |
|---|---|---|
| `InpStrategyProfile` | `QATS_PROFILE_BALANCED` (1) | core confirmation a setup needs |
| `InpSetupWindowBars` | 6 | H1 bars a sweep / displacement / break stays valid |
| `InpConflictMargin` | 10 | score lead needed when both sides are eligible |
| `InpNeutralCloseR` | 0.0 | neutral band of the loss streak, in R |

Hardening that changes no behaviour: the symbol specification is read into a scratch copy and published only when
valid (a failed reading can no longer zero the point size the guards divide by); the two terminal-permission
checks cast to `bool` explicitly.

---

## 4. The journal — one traceable life cycle per signal

Lines produced by executing the v1.20 source on real 2019 data (simulator; the EA text is what MetaEditor compiles).

```
[QATS][BUY][DETECTED] symbol=XAUUSD bar=2019.01.02 07:00 setup=B-20190102-0600 score=69/100 minimum=55 eligible=yes profile=BALANCED core=PASS 2/3 | sweep=none displacement=bar 2019.01.02 06:00 structure=BOS@1282.75(bar 2019.01.02 06:00) zone=OB | D1=+1 H4=+1 H1trend=+1 M15=yes M5=no
[QATS][SELL][DETECTED] symbol=XAUUSD bar=2019.01.02 21:00 setup=S-20190102-2000 score=43/100 minimum=55 eligible=no profile=BALANCED core=PASS 2/3 | sweep=none displacement=bar 2019.01.02 20:00 structure=CHOCH@1281.88(bar 2019.01.02 20:00) zone=OB | D1=+1 H4=+1 H1trend=-1 M15=yes M5=no
[QATS][SIGNAL][SCORED] symbol=XAUUSD bar=2019.01.02 21:00 BUY=47/100 SELL=43/100 minimum=55 profile=BALANCED candidate=SELL eligible=no outcome=BELOW_MINIMUM reason=SCORE_BELOW_MINIMUM setup=S-20190102-2000 | D1=+1 H4=+1 H1trend=-1 P/D=0.68 VWAP=1284.59091 | BUY core=FAIL(sweep alone: no displacement and no BOS/CHoCH) 1/3 [D1:17 H4:13 STRUCT:0 SWEEP:13(SSL:SWING) DISP:0 ZONE:4 PD:0 VWAP:0 VOL:0 M15:0 M5:0] | SELL core=PASS 2/3 [D1:0 H4:0 STRUCT:17(CHOCH) SWEEP:0 DISP:9 ZONE:4 PD:4 VWAP:4 VOL:0 M15:5 M5:0]
[QATS][EXECUTION][REJECTED] symbol=XAUUSD bar=2019.01.02 07:00 direction=BUY setup=B-20190102-0600 score=69 stage=SPREAD_VS_STOP reason=spread 17.00 pts exceeds 20.00% of stop distance
[QATS][EXECUTION][APPROVED] symbol=XAUUSD bar=2019.01.02 07:20 direction=BUY setup=B-20190102-0600 score=69 class=MODERATE_VALID entry=1285.18 sl=1283.73 tp=1288.08 tpSource=RR rr=2.00 lots=34.48 risk=4999.60 USD (0.50%)
[QATS][EXECUTION][FILLED] symbol=XAUUSD direction=BUY setup=B-20190102-0600 retcode=10009 deal=1000002 order=1000003 price=1285.18 volume=34.48 position=verified ticket=1000001
[QATS][BLOCK][REASON] symbol=XAUUSD bar=2019.01.02 07:25 direction=BUY setup=B-20190102-0600 score=68 reasons=MAX_POSITIONS,DUPLICATE_SETUP detail=max open positions reached (1); setup B-20190102-0600 was already traded; waiting for new core evidence
[QATS][GUARD] position 1000001 BUY closed LOSS net=-172.40 USD (neutral band 0.00) -> lossStreak=1/3
[QATS][COOLDOWN] state=STARTED trigger=3 losses start=2019.01.15 04:12:30 until=2019.01.15 05:12:30 remaining=3600s lossStreak restarts at 0
[QATS][COOLDOWN] state=EXPIRED trigger=3 losses start=2019.01.15 04:12:30 until=2019.01.15 05:12:30 - entries re-enabled, lossStreak=0
[QATS][STATS] scope=session-to-20190102 BUY detected=1 eligibleBars=72 approved=1 executed=1 blockedBars=67 rejected=4 closed=W0/L1/N0 net=-172.40 | SELL detected=1 eligibleBars=0 approved=0 executed=0 blockedBars=0 rejected=0 closed=W0/L0/N0 net=+0.00 | conflicts=0
```

| tag | when | per |
|---|---|---|
| `[QATS][BUY][DETECTED]` / `[QATS][SELL][DETECTED]` | a side's core confirmation passes for a new setup, whether or not the score then qualifies | setup |
| `[QATS][SIGNAL][SCORED]` | every analysis: both scores, the candidate, the outcome, its reason code, both evidence lists | closed M5 bar (`InpVerbose=false`: only when the outcome changes) |
| `[QATS][SIGNAL][CONFLICT]` | both sides eligible: scores, margin, the rule that decided, the decision | pair of setups |
| `[QATS][BLOCK][REASON]` | a risk guard vetoed an eligible signal; **all** active codes | setup + reason set |
| `[QATS][EXECUTION][REJECTED]` | plan / sizing / spread-vs-stop / reservation / broker refused it, with the stage | setup + reason (every broker refusal) |
| `[QATS][EXECUTION][APPROVED]` | every check passed, the order is being sent: entry, SL, TP, target source, R:R, lots, risk | order |
| `[QATS][EXECUTION][FILLED]` | the server accepted and the position was found | order |
| `[QATS][GUARD] position … closed WIN\|LOSS\|NEUTRAL` | a position finished; net result and the streak | position |
| `[QATS][COOLDOWN] state=…` | STARTED, EXPIRED, REPAIRED, CLEARED, and the state at attach | transition |
| `[QATS][STATS]` | per-direction counters | server day, and at deinit |

Outcome codes of a SCORED line: `EXECUTED`, `BLOCKED`, `REJECTED`, `BELOW_MINIMUM`, `NO_SETUP`, `VETOED`
(non-XAUUSD only), `CONFLICT`, `DRY_RUN`, `NO_DATA`. Every bar ends in exactly one.

`python3 tools/qats_journal_report.py <journal>` turns a terminal log (UTF-16 or UTF-8, v1.20 or v1.11 format)
into a BUY-vs-SELL table: candidate bars, detected setups, eligible bars, approved, filled, closed, win rate,
profit factor, expectancy, planned R:R, every rejection reason with its count, the cooldown timeline, broker
refusals. It is the evidence format for the DEMO test (7.3).

---

## 5. What was verified offline

The EA source is rewritten **mechanically** into C++ (`tools/qats_native.py`: `#property` blanked, `input` made a
variable, arrays mapped to a bounds-checked type, forward declarations generated, `#line` keeps the .mq5 line
numbers) and built against `tools/qats_sim/mql5_shim.h`, a typed model of the MQL5 API with a single-symbol broker
simulator behind it (bars on six timeframes, EMA/ATR handles, terminal global variables, a hedging account,
server-side SL/TP, deals and history, `CTrade`, checked `PrintFormat`). No function body is rewritten: the logic
that runs is the text MetaEditor compiles.

| suite | result | what it establishes |
|---|---|---|
| `tools/test_qats_native_build.py` | **57 / 57 PASS** | The whole file builds with 17 strict flags as errors: **0 errors, 0 warnings**. 14 injected defects (lossy conversions, wrong property getter, shadowing, unused variable, string + number, undeclared name, missing return, wrong arity, unknown member, struct by value, assignment to an input, static function) are each rejected at the right .mq5 line. All 100 `PrintFormat`/`StringFormat` calls carry exactly as many arguments as conversions. **743 boolean operands** (every `if`, `while`, `for`, `?:`, `&&`, `\|\|`, `!`) are type-checked to be `bool` — MetaEditor's "expression not boolean" — and 8 injected integer conditions are rejected. |
| `tools/test_qats_dual_direction.py` | **73 / 73 PASS** (71 when this audit was first published; section 4b, the file-seam replay, was added with the loader fix) | 235 unit checks (each bullish case beside its bearish mirror); 45 integration scenarios with 575 checks, each replayed tick by tick through `OnInit` / `OnTick` / `OnTradeTransaction`; 11 mirrored scenario pairs; a 14,040-bar symmetry replay with **0** mismatching bars; all of it again under AddressSanitizer + UBSan with poisoned locals and a zero-divide trap, with identical results. |
| `tools/test_qats_journal_report.py` | **33 / 33 PASS** | The report counts what the journal says, for v1.11 and v1.20 formats, in UTF-16 / UTF-8 / CRLF. |
| `tools/verify_quantum_ea.py`, `test_xau_execution_policy.py`, `test_quantum_account_policy.py`, `test_quantum_compile_regressions.py`, `test_signal_execution_profiles.py` | PASS | The pre-existing structural, authorization and execution-policy contracts still hold; the verifier gained checks for the direction policy, the life-cycle tags and the weights summing to 100, and fails v1.11 on 17 of them. |
| `tools/check_production_ready.py` | **OFFLINE GO 57 / 57** (55 when first published; the two QSMC suites were added later) | The repository's curated gate, with the three QATS suites in it. |

Scenario coverage (`qats_<tag> selftest --list`): strong BUY and strong SELL from detection to a closed position
in each profile; sweep-only and BOS-only in each profile and direction; counter-trend on XAUUSD and on another
symbol; rejection by spread, master switch, session, permission, drawdown, daily loss, daily cap + cooldown, dry
run, volume, margin (and margin shrink-to-fit), broker refusal, timeout; the cooldown state machine; loss counting
with commission, partial closes and manual closes; opposite position blocked / closed then opened; restart with a
position open; retry success and retry exhaustion; journal invariants.

**Direction symmetry on real data** (`tools/qats_backtest.py mirror`, 2019, integer price grid):

| build | exact mirror | BUY / SELL trades | BUY / SELL, mirrored feed | end balance | mirrored | bars compared | bars that differ |
|---|---|---|---|---|---|---|---|
| v1.20 | **YES** | 191 / 123 | 123 / 191 | 776,525.58 | 776,525.58 | 70,859 | **0** |
| v1.11 | **NO** | 533 / 357 | 398 / 495 | 452,450.62 | 472,751.26 | n/a | n/a |

On every one of 70,859 bars the BUY score of the first replay equals the SELL score of the mirrored replay, with
mirrored evidence and the same outcome; every trade has its twin with the same volume and the same profit.
If the EA takes more BUYs than SELLs in a given month, the market did that — the code cannot.

**Additional replays under the sanitizers** (ASan + UBSan + float zero-divide, poisoned locals): all of 2019
(340 trades — byte-identical trade list to the normal build) and 2025-09 → 2026-09 on the raw feed spread with
default inputs (189 trades): no runtime error, no API misuse, no format error.

**Behaviour-neutral hardening, proven neutral**: the three source edits made after the study (3.10) leave the
complete 2019 journal — 76,369 lines, 41.6 MB — the trade list and the summary byte-identical, and the whole study
was re-run on the final source with identical numbers.

**Regenerated after a loader fix.** The yearly files of the dataset overlap at their seams (8,127 one-minute rows)
and the loader of the first publication fed them twice. The loader now skips a row that does not move time forward
(section 4b of `tools/test_qats_dual_direction.py`), and the study, the mirror proof and the two sanitizer replays
above were run again: the figures in this document are those of the re-run. No conclusion changed; the note at the
top of [`QATS_BACKTEST_STUDY_2026-11-11.md`](QATS_BACKTEST_STUDY_2026-11-11.md) lists what moved.

What this does **not** establish: that MetaEditor accepts the file (MQL5 and C++ are different languages), that
MT5 behaves like the simulator, or that a broker fills like the fill model.

---

## 6. Simulation study — BUY versus SELL, v1.11 versus v1.20

**A simulation, not the MT5 Strategy Tester.** Real source, real M1 bid/ask history (public dataset
`Dypoi/XAUUSD_Dataset`, 2016-09 → 2026-09, pinned by commit and SHA-256, not redistributed here), four quotes per
M1 bar, stops filled at their level with 5 points of adverse slippage, **no commission, no swap**. The feed's
median spread is 26 – 67 points on a 2-digit symbol, above `InpMaxSpreadPoints=50` in recent years, so the
headline rows use half the recorded spread; a raw-spread row is included. In-sample 2017-02 → 2023-09,
out-of-sample 2023-09 → 2026-09. The out-of-sample window was not used while the engine was designed.

"Signal study" rows switch off only the two breakers that end a run (drawdown halt, daily loss lock) and use a
1,000,000 balance so the minimum lot never decides. Every other guard is on.

### In-sample, 2017-02-01 → 2023-09-01

| configuration | dir | setups detected | eligible bars | executed | win rate | profit factor | expectancy (R) |
|---|---|---|---|---|---|---|---|
| v1.11 | BUY | n/a | 169,952 | 3,484 | 16.0 % | 0.79 | −0.104 |
| | SELL | n/a | 128,891 | 3,023 | 15.3 % | 0.71 | −0.148 |
| | **both** | | | **6,507** | **15.6 %** | **0.76** | **−0.124** |
| v1.20 BALANCED (default) | BUY | 1,645 | 49,114 | 1,151 | 19.5 % | 0.79 | −0.111 |
| | SELL | 1,556 | 35,613 | 989 | 19.2 % | 0.78 | −0.146 |
| | **both** | | | **2,140** | **19.4 %** | **0.79** | **−0.127** |
| v1.20 CONSERVATIVE | BUY | 417 | 9,164 | 409 | 19.1 % | 0.79 | −0.105 |
| | SELL | 387 | 7,791 | 381 | 21.0 % | 0.83 | −0.088 |
| | **both** | | | **790** | **20.0 %** | **0.81** | **−0.097** |
| v1.20 ACTIVE | **both** | | | **2,752** | **18.8 %** | **0.77** | **−0.138** |

Every in-sample calendar year is negative for v1.20 BALANCED (2017 … 2023). Maximum drawdown of the signal-study
equity: 78.0 % (v1.20 BALANCED), 98.7 % (v1.11).

### Out-of-sample, 2023-09-01 → 2026-09-01

| configuration | dir | setups detected | eligible bars | executed | win rate | profit factor | expectancy (R) |
|---|---|---|---|---|---|---|---|
| v1.11 | BUY | n/a | 99,967 | 1,884 | 17.4 % | 0.95 | −0.016 |
| | SELL | n/a | 38,700 | 1,080 | 15.8 % | 0.64 | −0.156 |
| | **both** | | | **2,964** | **16.8 %** | **0.83** | **−0.067** |
| v1.20 BALANCED (default) | BUY | 784 | 29,544 | 606 | 23.9 % | 1.16 | +0.090 |
| | SELL | 662 | 10,985 | 358 | 17.0 % | 0.76 | −0.136 |
| | **both** | | | **964** | **21.4 %** | **1.00** | **+0.006** |
| v1.20 BALANCED, raw feed spread | **both** | | | **828** | **19.4 %** | **0.92** | **−0.034** |
| v1.20 CONSERVATIVE | **both** | | | **349** | **18.3 %** | **0.87** | **−0.072** |

By year (v1.20 BALANCED): 2023 −, 2024 −, **2025 +**, 2026 −. Over this window gold went from 1,940 to 4,324 in
the dataset, and by 65 % in 2025 alone. The out-of-sample "break-even" is that one year carrying the BUY side; the
SELL side loses in every window, and with the recorded spread the total is negative again. This is a market
regime, not an edge — the mirror test proves the code treats both sides alike, so the difference between the two
columns is the market's.

### With every guard on, on a 10,000 account

The drawdown halt is a latch: once equity is the configured percentage below its high-water mark the EA sends
nothing until an operator resets it (`InpResetBreakersAtInit=true`, once). With the compiled defaults (0.5 % risk,
8 % halt) the last in-sample entry of v1.20 is on 2017-06-01 — 114 trades, balance 9,985 — and the halt then
refuses 2,583 further setups; out-of-sample the last entry is on 2023-09-27, after 23 trades. v1.11 stops after 38
and 30 trades.

With the **shipped preset** (`presets/Quantum_XAUUSD_PRODUCTION.set`: 0.10 % risk, 3 % drawdown halt, 0.5 % daily
loss, 3 trades a day) the same replay gives:

| window | closed trades (BUY / SELL) | last entry | end balance | max DD | profit factor | expectancy | what stopped it |
|---|---|---|---|---|---|---|---|
| in-sample 2017-02 → 2023-09 | 273 (142 / 131) | 2017-11-16 | 9,853.98 | 3.1 % | 0.90 | −0.045 R | the 3 % halt latched after 9.5 months and refused 2,406 further setups for the remaining 5.8 years |
| out-of-sample 2023-09 → 2026-09 | 945 (606 / 339) | 2026-08-31 | 10,126.46 | 2.9 % | 1.03 | +0.029 R | nothing: the halt was never reached (+1.3 % in three years, before commission and swap) |

Read together: the preset bounds the damage exactly as designed — and a strategy whose expectancy is not positive
reaches that bound. The out-of-sample +1.3 % in three years is smaller than one month of realistic commission on
945 round trips; it is not evidence of an edge.

### Why eligible signals were not executed (v1.20 BALANCED, in-sample; journal records)

| reason | BUY | SELL |
|---|---|---|
| `DUPLICATE_SETUP` (the setup already produced a position) | 2,510 | 1,835 |
| `MAX_POSITIONS` | 1,197 | 887 |
| `SPREAD` | 236 | 39 |
| `LOSS_COOLDOWN` | 229 | 190 |
| `SPREAD_VS_STOP` (execution stage) | 165 | 143 |
| `DAILY_TRADE_CAP` | 14 | 9 |

Entry orders sent / accepted / failed: 2,141 / 2,141 / 0. Format errors 0, API misuse 0, critical errors 0.

### Reading

- v1.20 trades a third as often as v1.11, wins more often, plans a reachable target, and treats both directions
  alike. Its expectancy per unit of risk is about the same as v1.11's in-sample (−0.127 R against −0.124 R) and better
  out-of-sample (+0.006 R against −0.067 R). **That is not profitability.**
- The 2,780 in-sample trades of an intermediate build were broken down by every feature the EA scores — D1/H4
  alignment, sweep present, BOS versus CHoCH, zone touched, premium/discount, VWAP side, M15/M5, score bucket, hour
  of day, planned R:R. No subset showed a stable positive expectancy. No filter was added on the strength of that
  search: one found that way would be a description of the past.
- Full tables, both windows, all eleven configurations, spread sensitivity, zone-touch and session variants, and
  the reproduction commands: [`QATS_BACKTEST_STUDY_2026-11-11.md`](QATS_BACKTEST_STUDY_2026-11-11.md),
  machine-readable in `qats_backtest_study_2026-11-11.json`.

---

## 7. What was NOT verified — and exactly how to verify it

### 7.1 MetaEditor compile — NOT RUN

1. MT5 → **File → Open Data Folder** → `MQL5\Experts\` → copy `QuantumAutonomousTradingSystem.mq5` there
   (replace the v1.11 file).
2. Open it in MetaEditor (F4) and press **F7**. Required result in the *Errors* tab: **0 errors, 0 warnings**.
3. If anything is reported, copy the lines of the *Errors* tab verbatim (file, line, column, text). The host build
   keeps .mq5 line numbers, so a report can be matched and repaired exactly. Do not attach an `.ex5` produced with
   warnings without reading them.

Why the host build is not enough: MQL5 is not C++. The shim reproduces the API signatures and the warning classes
this repository has met, and the lint covers constructs C++ accepts and MQL5 does not (struct parameters by value,
reference variables, local types, member initialisers, reserved words, assignment to an input) — but only
MetaEditor decides.

### 7.2 MT5 Strategy Tester — NOT RUN

1. Log in to the **DEMO** account first. The EA refuses any account it cannot identify as DEMO; the attach
   banner in the tester Journal says which mode it saw.
2. `Ctrl+R` → Expert `QuantumAutonomousTradingSystem`, symbol: the broker's XAUUSD, any timeframe (the EA reads
   D1/H4/H1/M15/M5 itself), modelling **"Every tick based on real ticks"** (a first pass on "1 minute OHLC" is
   faster), deposit 10,000, at least 12 months.
3. *Inputs* → right-click → **Load** → `presets/Quantum_XAUUSD_PRODUCTION.set`.
4. In the tester *Journal* the first lines must include `v1.20 attaching`, `[QATS][POLICY] direction: BUY and SELL
   are scored independently …`, `[QATS][PROTECTION] PASS: DEMO account authorized`.
5. After the run: tester *Journal* → right-click → **Open** → take the agent's `logs\YYYYMMDD.log`, then
   `python3 tools/qats_journal_report.py <that file>` and keep the output next to the tester report.
6. To measure the signal over the whole period rather than until the first halt, run a second pass with
   `InpMaxAccountDrawdownPct=0` and `InpMaxDailyLossPercent=0` — in the tester only.

Compare with section 6. The tester has real ticks and the broker's contract, commission and swap; where it
disagrees with the simulation, the tester is right.

### 7.3 DEMO forward test — NOT RUN for v1.20

1. Compile (7.1). Attach to the XAUUSD chart of the DEMO account, load the preset, enable Algo Trading.
   If guard state from the v1.11 session is still stored (a cooldown, the equity high-water mark), v1.20 validates
   and journals it; to start clean set `InpResetBreakersAtInit=true` for one attach, then back to `false`.
2. Read the attach banner:
   `[QATS] QuantumAutonomousTradingSystem v1.20 attaching to XAUUSD` ·
   `[QATS][POLICY] direction: … profile=BALANCED …` · `[QATS][POLICY] weights: … (sum 100 …)` ·
   `[QATS][PROTECTION] PASS: DEMO account authorized` · `[QATS][COOLDOWN] state=IDLE at attach` ·
   no `[QATS][CONFIG] current spread … above InpMaxSpreadPoints` (if present, entries stay blocked by `SPREAD`).
3. Let it run for at least ten trading days, or until 30 positions have closed, whichever is later.
4. Each day: *Experts* tab → right-click → **Open** → `MQL5\Logs\YYYYMMDD.log`. Then
   `python3 tools/qats_journal_report.py MQL5/Logs/2026111*.log > demo_report.md`.
5. Acceptance — each line is a number in that report:

   | # | criterion | where |
   |---|---|---|
   | 1 | `journal format: v1.20 (both directions per bar)` | header |
   | 2 | both columns non-zero in "bars where this side was the candidate" and "setups detected" | table 1 |
   | 3 | at least one `direction=BUY` **and one `direction=SELL`** `[QATS][EXECUTION][FILLED] … position=verified`, each followed by `[QATS][VERIFY] server-side SL=… TP=…` | journal |
   | 4 | "orders approved" = "orders filled" + broker/reservation rejections; "accepted-but-unverified positions: 0" | tables 1, 3; health |
   | 5 | every eligible bar that did not trade appears under "Why eligible signals were not executed" with a reason | table 3 |
   | 6 | every cooldown `STARTED` is followed by `EXPIRED` after `InpCooldownAfterLossMin`, with no `FILLED` between them | cooldown timeline |
   | 7 | no second `FILLED` for the same `setup=` id | journal |
   | 8 | no `[CRITICAL]` line; no "zero divide" or "array out of range" in the Experts tab; the EA is still attached | journal |

   Criterion 2 depends on the market: in a one-way week most candidates are on one side. That is legitimate —
   what must never appear is an eligible SELL that neither traded nor was given a reason.
6. Keep `demo_report.md` and the raw logs. They are the evidence; a screenshot is not.

---

## 8. Production-readiness verdict

**Not production-ready. Do not run it on a REAL account.**

| gate | state |
|---|---|
| Direction symmetry, transparency, cooldown accounting, execution paths | repaired; **PASS** offline |
| MetaEditor compile with 0 errors and 0 warnings | **NOT RUN** |
| MT5 Strategy Tester on the broker's symbol | **NOT RUN** |
| DEMO forward test with fills in both directions | **NOT RUN** (v1.11: 3 BUY fills, 0 SELL) |
| Positive expectancy after costs, out-of-sample | **not demonstrated**; negative in-sample in simulation, about zero out-of-sample before commission and swap |

The first four are engineering and can be closed by the procedures in section 7. The fifth is the strategy: a
correct, symmetric, well-logged implementation of rules that lose money still loses money. Closing that gap is
research — a hypothesis about where these setups have an edge, tested out-of-sample — and it is not something a
code audit can supply.

---

## 9. Known limitations

- **Simulation fill model**: four quotes per M1 bar. A stop and a target inside the same minute are resolved by
  the bar's path, not by ticks; break-even moves happen at M1 resolution. No commission, no swap, no requotes
  beyond the injected ones, no partial fills, hedging account only.
- **Dataset**: one public source with no licence statement; its spread is wider than the operator's broker's.
  Results under a different feed will differ.
- **Equity guards read the account**, not the EA: other positions on the same account move the daily-loss and
  drawdown guards (observed on 2026-11-11). The attach banner now says so. Use a dedicated account for the test.
- **The drawdown halt is a latch.** With no position open, equity cannot recover on its own; an operator reset is
  the only way out. This is deliberate and is journalled.
- **`InpMaxSpreadPoints=50` is in points.** On a symbol quoted with an extra digit it must be scaled by ten; the
  attach banner warns when the current spread already exceeds it.
- **More than one EA position on the symbol** (`InpMaxOpenPositions > 1`) is supported but the scenarios
  concentrate on the shipped value 1.
- **`tools/qats_backtest.py --baseline`** reads v1.11 from git history and needs a full clone.
- **One terminal, one chart per symbol and magic.** Reservation keys do not coordinate separate terminals.

---

## 10. Files

| path | what |
|---|---|
| `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` | the EA, v1.20 — the only deployment file |
| `presets/Quantum_XAUUSD_PRODUCTION.set` | the preset, with the four new inputs |
| `tools/qats_native.py` | .mq5 → C++ rewrite, strict build, MQL5 lint, boolean-context audit |
| `tools/qats_sim/` | typed MQL5 shim + broker simulator, driver, unit tests, 45 scenarios, synthetic market |
| `tools/qats_backtest.py` | `fetch`, `run`, `study`, `mirror`, `report` |
| `tools/qats_journal_report.py` | BUY-vs-SELL report from an MT5 journal |
| `tools/test_qats_native_build.py`, `test_qats_dual_direction.py`, `test_qats_journal_report.py` | the three new suites (exit 77 without a host compiler) |
| `tools/verify_quantum_ea.py`, `tools/test_xau_execution_policy.py` | updated for v1.20 |
| `.github/workflows/quantum-verify.yml`, `tools/check_production_ready.py`, `tools/test_native_toolchain.py` | the suites wired into CI and the curated gate |

```
python3 tools/test_qats_native_build.py          # ~1 min
python3 tools/test_qats_dual_direction.py        # ~1.5 min
python3 tools/test_qats_journal_report.py
python3 tools/check_production_ready.py          # the whole curated gate

python3 tools/qats_backtest.py fetch  --dest /path/to/xau_m1
python3 tools/qats_backtest.py study  --data /path/to/xau_m1 --out out/qats_backtest
python3 tools/qats_backtest.py mirror --data /path/to/xau_m1 --from 2019-01-01 --to 2020-01-01 --baseline --out out/qats_backtest
python3 tools/qats_journal_report.py  <MQL5/Logs/YYYYMMDD.log> [...]
```
