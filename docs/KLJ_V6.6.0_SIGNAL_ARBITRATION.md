# Quantum SMC Intelligence Engine — v6.6.0 SIGNAL ARBITRATION
### Static review + gated redesign of the tactical MTF-entry alert path

**Date:** 2026-10-19
**Reviewed file:** `nadir2.mq5` — 39,655 lines / 1,793,740 bytes, header `v6.5.5 ALERT ARBITRATION / CLOSED-BAR CLARITY PASS`, `#property version "6.55"`.

> **FILE NAME.** The brief calls the indicator `KLJ.mq5`. The repository checkout contains exactly one MQL5 file, `nadir2.mq5`, and its own comments refer to `docs/KLJ_V6.5.4_REACTION_CONFLICT_FIX.md` and `QuantumSMC_AI_Pro_v6.5.3_SystemReview.mq5`. I treated `nadir2.mq5` as the authoritative source, exactly as instructed ("Treat it as the only authoritative source"). Every line number below refers to the **original v6.5.5 file** unless it says "patched".
> The patched file grew by 95 lines before line 13710 and by 184 lines before line 36529; where I cite a patched location I say so.

> **COMPILATION.** **No MetaEditor is available in this environment. Nothing here has been compiled.** Every claim is from reading the source. Static review only — **you must press F7.**

---

## 1. EXECUTIVE SUMMARY (root causes ranked by impact)

| # | Root cause | Line(s) | Effect |
|---|---|---|---|
| **1** | The tactical path **fires `Alert()` itself**, from inside `UpdateMTFExecutionEntry()`, completely outside `AlertDispatcherFinalize()` — the "one closed-bar arbiter" that every other path uses. | `5389` call → `21869` `Alert()` | It bypasses the entire gate chain, the per-bar arbitration, the ranking, and the shared dedupe. |
| **2** | That path **reads no zone at all**. It reads only `g_early_break_*`, `g_active_setup`, `g_htf_bias`, `g_structures` and execution-TF OHLC. | `5286-5348` | A SELL can be published while price sits inside a strong SUPPORT and a BUY into RESISTANCE. This is symptom 2, verbatim. |
| **3** | Its **dedupe key contains `g_mtf_sig_time`**, and `g_mtf_sig_time` is reset to `0` on every PREVIEW bar (`5345`) and by `ClearMTFExecutionEntry()` (`5279`). | `5377`, `5342-5346` | The key alternates between `id\|CONFIRMED` and `id\|CONFIRMED\|<t>` each time the signal re-arms, so the *same* signal re-fires. This is the "1 per minute, different price" storm. |
| **4** | It runs at `14718`, i.e. **before `ZRE_Update()` (`14796`) and `RXN_Update()` (`14807`)**. | `14718` vs `14796` | Even if it wanted to read the zone list, the list it would read is one bar stale and it never looks. |
| **5** | It **steals the one-alert-per-bar claim** from the authoritative engine: `FireQuantAlert` → `QSMC_ClaimDirectionalAlert` claims the chart bar at `21863`, and `AlertDispatcherFinalize` then returns early at `36461`. | `21863`, `36461` | A non-authoritative tactical alert silences the CORE/ZRE/RXN alert for that bar. |
| **6** | It prints the word **CONFIRMED** for a signal that passed no gate, while calling itself "NON-AUTHORITATIVE" in the same line. | `5389` | Terminology defect (R7). |
| **7** | The one-per-bar claim is keyed on the **chart** bar, while the state machine runs on the **execution** bar. On an M1 chart they coincide, so the ceiling is exactly **1 alert per minute per chart**. | `21861-21863` | Explains "often 1 per minute" on XAUUSD M1. |
| **8** | `g_early_break_structure_idx` is used as a flag with no bounds check against `ArraySize(g_structures)` after `EnforceArrayLimits()` shifts the master array. | `5287`, `14503` | Stale-index defect (low impact, no crash). |

**Net effect after the fix:** the tactical path no longer alerts on its own. It records a *fact*; `CSignalArbiter` decides once per closed bar whether that fact is a signal, and `CAlertManager` is the only class that may call `Alert()`.

---

## 2. PHASE 0 — INVENTORY

### 2a. Every site that can raise an alert or draw an entry mark

Only **two** places in the whole 39,655-line file call `Alert()`. Both are sinks; none of the drawing code alerts.

| # | Site (orig. line) | Kind | Trigger condition | Gates it checks | Gates it bypasses |
|---|---|---|---|---|---|
| A1 | `21869` in `FireQuantAlert()` | `Alert()` + `SendNotification()` + `PlaySound()` | caller passes a non-empty `event_id` not already in an 8-slot ring (`21851-21852`); channels from `InpPrimaryAlertPopup/Push/Sound` (`21857-21859`) | 8-slot exact-id ring; for "directional" messages (text contains `BUY` or `SELL`, `36114-36118`) the one-per-chart-bar claim `QSMC_ClaimDirectionalAlert` (`21863`) | **zone, reaction, room/RR, HTF bias, volatility, data quality, cooldown, distance, flip-flop** — all of them |
| A2 | `36520-36522` in `AlertDispatcherFinalize()` | `Alert()` + `SendNotification()` + `PlaySound()` | a candidate survived `alert_eligible`, `AlertWithinMaxDistance`, `AlertChannelsFor`, `AlertCooldownAllows`, and (if directional) the same claim (`36476-36514`) | distance (`36479`), channel (`36481`), dedupe+cooldown (`36482`), per-bar claim (`36485`, `36514`) | none — this is the intended arbiter |

**`FireQuantAlert()` callers (all of which bypass the dispatcher):**

| Line | Caller | Text contains BUY/SELL? | Claimed per chart bar? |
|---|---|---|---|
| `5389` | `UpdateMTFExecutionEntry()` — **the reported defect** | YES (`MTF %s ENTRY %s`) | YES |
| `20045` | setup `\|READY` | YES | YES |
| `20110` | setup terminal state | YES | YES |
| `21790-21810` | TP1/TP2/TP3/S1/S2/BE (analytical) | NO | no |
| `28905` | `TopDown_Update()` verdict flip | YES | YES |

**Entry-mark drawing sites (no alert):**

| Line | Object / buffer | Owner | Condition |
|---|---|---|---|
| `6237-6238` | `BufEntryBuy0/Sell0` (confirmed), `BufPrevBuy0/Sell0` (preview) | `EntryMarkWriteAt()` | index found from bar time; tactical (`src==2`) explicitly skipped (`6234`) |
| `6272-6273` | same four buffers, last bar only | `EntryMarkTactical()` | `InpShowTacticalEntries` (`6271`), `InpDisplayMode != MINIMAL` (`6260`) |
| `6281` | `OBJ_ARROW` `PFX+"MTF_MARK_{BUY,SELL}_{C,P}"` | `EntryMarkTactical()` | as above |
| `6325` | `OBJ_ARROW` `PFX+"EMARK_{CORE,ZRE}_{BUY,SELL}_{C_<time>,P}"` | `EntryMarkObject()` | `InpShowEntries` / `InpShowEntryPreviewMarks`, visual distance |
| `5353` | `OBJ_HLINE` `PFX+"MTF_ENTRY"` | `UpdateMTFExecutionEntry()` | `InpShowMTFExecutionEntry` (`5349`) |
| `5361` | text `PFX+"MTF_ENTRY_TX"` | `UpdateMTFExecutionEntry()` | as above |
| `14760` | `OBJ_HLINE` `PFX+"ENTRY_PREVIEW"` | `OnCalculate` | `InpShowEntryPreview && InpUseRetestLifecycle && state==PREVIEW` |
| `36371` | `OBJ_ARROW` `PFX+"PRIMARY_<bar>_ARROW"` | `AlertDispatcherDrawPrimary()` | `scenario_candidate && direction!=0` |
| `23592`, `23610` | text `PFX+"EARLYBREAK"` | `UpdateEarlyBreakPreview()` | `InpShowEarlyBreakPreview` |

### 2b. Exact provenance of the reported string

```
nadir2.mq5:5389
FireQuantAlert(key, StringFormat("%s %s | TACTICAL / NON-AUTHORITATIVE | MTF %s ENTRY %s @ %.2f | execution %s | institutional confirmation separate",
               _Symbol, TFName((ENUM_TIMEFRAMES)_Period), bull?"BUY":"SELL", state, ep, TFName(etf)));
```

**Full call chain from `OnCalculate`:**

```
OnCalculate                                (14235)
 ├─ guard: if(!is_new_bar && prev_calculated>0 && !InpUpdateEveryTick) return   (14286)
 │     InpUpdateEveryTick defaults to TRUE (1013) => the body below runs EVERY TICK
 ├─ ... detection, lifecycle, CalculateAITradeSetup ...
 ├─ UpdateEarlyBreakPreview(rates_total, g_buf_t, g_buf_h, g_buf_l, g_buf_c)     (14717)
 │     writes g_early_break_price / _bull / _status="LIVE_PREVIEW"
 │     >>> reads the FORMING bar: h[forming], c[forming] where forming = total-1  (23566, 23577-23579)
 ├─ UpdateMTFExecutionEntry()                                                    (14718)   <-- REPORTED DEFECT
 │     ├─ direction source 1: g_early_break_*  (LIVE_PREVIEW)                    (5287-5289)
 │     ├─ direction source 2: g_active_setup                                     (5290-5291)
 │     ├─ direction source 3: g_htf_bias + last matching structure               (5292-5298)  <-- NO ZONE
 │     ├─ if(InpUseHTFBias && g_htf_bias!=(bull?1:-1)) return                    (5299)       <-- only HTF filter
 │     ├─ lh/ll/lo/lc = iHigh/iLow/iOpen/iClose(etf, 0)   // FORMING exec bar     (5302)
 │     ├─ ch/cl/co/cc = iHigh/iLow/iOpen/iClose(etf, 1)   // CLOSED exec bar      (5303)
 │     ├─ live_cross    = bull ? (lh>=trigger && lc>=lo) : (ll<=trigger && lc<=lo)(5321)      <-- forming bar
 │     ├─ closed_confirm= bull ? (ch>=trigger && cc>co && cc>=trigger) : ...      (5325-5326)  <-- closed bar (OK)
 │     ├─ state = closed_confirm ? "CONFIRMED" : "PREVIEW"                        (5331)
 │     ├─ ep   = closed_confirm ? cc : lc                                         (5332)      <-- "different price each time"
 │     ├─ id   = "SYM|etf|trigger_time|B|S|trigger"                               (5333)
 │     ├─ if(state=="PREVIEW" && g_last_mtf_entry_key==id+"|CONFIRMED") return    (5337)
 │     ├─ g_mtf_sig_time = (live_cross ? iTime(etf,1) : iTime(etf,0))             (5344)
 │     │     only when (g_mtf_sig_time==0 || g_last_mtf_entry_key != id+"|CONFIRMED")
 │     ├─ else if(!closed_confirm) g_mtf_sig_time = 0                             (5345)      <-- KEY RESET
 │     ├─ draw HLINE + label + EntryMarkTactical()                                (5349-5373)
 │     └─ FireQuantAlert(...)                                                     (5389)      <-- ALERT, NO GATE
 │            └─ QSMC_IsDirectionalAlertMessage -> true (text has BUY/SELL)        (21853)
 │            └─ QSMC_ClaimDirectionalAlert(g_buf_t[closed], event_id)            (21863)
 │                  claims the CHART bar  =>  <= 1 tactical alert per chart bar
 │            └─ Alert(message)                                                    (21869)
 ├─ FireSetupAlert(g_buf_t[closed])                                              (14779)
 │     └─ AlertDispatcherSubmit(a)  [source=3 CORE]                               (20440)
 ├─ ZRE_Update(...)                                                              (14796)
 ├─ RXN_Update(...)                                                              (14807)
 └─ AlertDispatcherFinalize(rates_total)                                         (14809)
       ├─ if(g_directional_alert_bar_time==bar_time) return                       (36461)  <-- tactical already claimed it
       └─ ... rank ZRE/RXN candidates ... Alert(message)                          (36520)
```

**Two consequences that follow directly from this ordering:**

1. `UpdateMTFExecutionEntry` (`14718`) runs **before** `ZRE_Update` (`14796`). At the moment it decides, `g_zre_zones` / `g_zre_status` hold the state produced at the end of the **previous** bar. It never reads them anyway.
2. `AlertDispatcherFinalize` (`14809`) runs **after** and returns early at `36461` if the tactical path already claimed the bar. **A non-authoritative tactical alert suppresses the authoritative CORE/ZRE/RXN alert for that bar.**

### 2c. GATE MATRIX — BEFORE (v6.5.5)

Rows = signal paths. Columns = gates. Cells: **P** = pass-enforced, **B** = bypassed, **n/a** = not applicable, **(P)** = enforced elsewhere.

| Gate → | closed bar | zone location | HTF bias | room / RR | cooldown | dedupe | volatility | spread / data quality |
|---|---|---|---|---|---|---|---|---|
| **CORE** (`CalculateAITradeSetup` → `ManageSetupLifecycle` → `FireSetupAlert` → dispatcher) | **P** `20407` | n/a (CORE brings its own zone) | **P** `20425-20427` (alignment only, reported not enforced) | **P** in CORE (`InpMinRR1`, `InpMaxStopATR`) | **P** `36482` | **P** `36482`, `20405` | n/a | **P** `36479` distance + `14379` data |
| **ZRE** (Zone Reaction Engine) | **P** `ZRE_ClassifyState` `31612` | **P** `GetSignalDirection` `31585-31610` | **P** `ZRE_ScoreSignal` HTF/D1 | **P** `ZRE_FinalizeGeometry` `31775` | **P** `36482` | **P** `36482` | **P** `ZRE_EffectivePenetrationATR` (extreme-vol only) | **P** `36479` |
| **RXN** (Reaction Signal Layer) | **P** (`RXN_LevelEx` closed-bar) | **P** (`RXN_ApplyOpposition`) | **P** `InpRXNCountertrendMargin` | **P** `InpRXNMinRoomATR` | **P** `36482` | **P** `36482` | **P** extreme-vol branches | **P** `36479` |
| **MTF-TACTICAL** (`UpdateMTFExecutionEntry` → `FireQuantAlert`) | **P** for the exec bar only (`5325-5326`) — but the *label* flips on the forming bar (`5321`) | **B** — never reads `g_zre_zones` | **P** direction only (`5299`): `g_htf_bias` **decides the trade**, it does not filter one | **B** — no RR, no SL, no TP, no barrier | **B** | **B** (key mutates, see §3) | **B** | **B** — `CopyBuffer`/`iHigh` returns never checked at `5302-5304` |
| **PREVIEW** (`UpdateEarlyBreakPreview`) | n/a — uses the forming bar by design (`23566`), displays only | **B** (display only, no alert) | n/a | n/a | n/a | n/a | n/a | n/a |

**Read the tactical row.** It is the only alerting path with **five B's**.

### 2d. GATE MATRIX — AFTER (v6.6.0)

| Gate → | closed bar | zone location | HTF bias | room / RR | cooldown | dedupe | volatility | spread / data quality |
|---|---|---|---|---|---|---|---|---|
| **CORE** | **P** `CClosedBarGate` (opt-in, `InpArbGateCore=false` keeps v6.5.5 behaviour) | **P** if gated | **P** `CBiasGate` | **P** `CRoomGate` | **P** `CCooldownGate` | **P** `CAlertManager` ring | **P** `CVolatilityGate` | **P** `CDataQualityGate` |
| **ZRE** | **P** | **P** | **P** | **P** | **P** | **P** | **P** | **P** |
| **RXN** | **P** | **P** | **P** | **P** | **P** | **P** | **P** | **P** |
| **MTF-TACTICAL** | **P** `CClosedBarGate` — a forming-bar fact is demoted to `PREVIEW` and never alerted | **P** `CLocationGate` — direction now comes from the zone role + a closed-bar reaction/acceptance fact, never from bias | **P** `CBiasGate` — bias is now a filter; opposed ⇒ `COUNTER-TREND / SCALP ONLY` or refuse | **P** `CRoomGate` — stop ≤ `max_stop_atr`, RR ≥ `min_rr`, barrier must leave the room | **P** `CCooldownGate` | **P** `CAlertManager` (exact key + distance + flip-flop + cross-chart GlobalVariable) | **P** `CVolatilityGate` | **P** `CDataQualityGate` + `CBarSeries::Ready()` (partial copy = retry, never success) |
| **PREVIEW** | n/a — still formed from the forming bar, but it can no longer reach any alert sink | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

---

## 3. PHASE 1 — ROOT-CAUSE ANALYSIS (with code evidence)

### Symptom 1 — "~30+ alerts in ~5 hours, often 1 per minute, different price each time"

**Root cause: the dedupe key is not a function of the signal.**

```mq5
5333:  string id=StringFormat("%s|%d|%I64d|%s|%.5f",_Symbol,(int)etf,(long)trigger_time,bull?"B":"S",trigger);
5342:  if(closed_confirm && InpAlertOnSignalBar &&
5343:     (g_mtf_sig_time==0 || g_last_mtf_entry_key!=id+"|CONFIRMED"))
5344:     g_mtf_sig_time=(live_cross ? iTime(_Symbol,etf,1) : iTime(_Symbol,etf,0));
5345:  else if(!closed_confirm) g_mtf_sig_time=0;
5346:  if(g_mtf_sig_time<=0 || g_mtf_sig_time>et) g_mtf_sig_time=et;
...
5377:  string key=id+"|"+state+((g_mtf_sig_time>0 && g_mtf_sig_time!=et) ? "|"+IntegerToString((long)g_mtf_sig_time) : "");
5380:  if(key!=g_last_mtf_entry_id)
5384:     bool fire=(state=="CONFIRMED");
5385:     g_last_mtf_entry_id=key;
```

The key **conditionally appends `g_mtf_sig_time`**, and `g_mtf_sig_time` is:
* set to `iTime(etf,1)` **only** while `g_mtf_sig_time==0` or the stored key differs (`5342-5344`);
* **reset to `0` on every PREVIEW bar** (`5345`);
* **reset to `0` by `ClearMTFExecutionEntry()`** (`5279`), which runs whenever the trigger disappears, the HTF bias flips, or the trigger goes stale (`5285`, `5299`, `5309`, `5319`, `5330`, `5337`, `5374`).

So the key oscillates between two spellings:

```
…|CONFIRMED            (when g_mtf_sig_time == et, i.e. on the anchor bar)
…|CONFIRMED|<t_anchor> (on every later bar, because g_mtf_sig_time is frozen)
```

**Minimal reproduction** (XAUUSD M1, execution TF = M1, trigger fixed at 3300.00, HTF bias bullish):

| Bar | `closed_confirm` | `g_mtf_sig_time` before | key | alert? |
|---|---|---|---|---|
| T+0 | true | 0 → set to T+0 (= et) | `…\|CONFIRMED` | **YES (1)** |
| T+1 | true | frozen at T+0, ≠ et | `…\|CONFIRMED\|T+0` | **YES (2)** |
| T+2 | true | frozen at T+0 | `…\|CONFIRMED\|T+0` | no (same key) |
| T+3 | false, `live_cross` true → PREVIEW | **reset to 0** (`5345`) | `…\|PREVIEW` | no (PREVIEW never fires) |
| T+4 | true | 0 → set to T+4 (= et) | `…\|CONFIRMED` | **YES (3)** |
| T+5 | true | frozen at T+4 | `…\|CONFIRMED\|T+4` | **YES (4)** |

In a market where `live_cross` is true on most bars (bull: `lh>=trigger && lc>=lo` — true for nearly every up-bar once price is above the trigger) and `closed_confirm` intermittently fails, this cycle repeats and yields **~1 alert per bar**.

`ep = cc` (`5332`) is the close of the most recent closed M1 bar, which is why **every alert carries a different price**.

**Why dedupe by zone/signal cannot work:** the tactical path has no zone and no signal id. Its identity is `(symbol, execTF, trigger_time, direction, trigger)`, and `trigger` / `trigger_time` are re-derived from `g_structures[ns-1]` on every detection update (`5292-5298`), so a new swing produces a new identity even when the level is economically the same.

**Second amplifier — the per-bar claim is on the CHART timeframe.**
```mq5
21861:  int closed=ArraySize(g_buf_t)-2;
21863:  if(closed<0 || closed>=ArraySize(g_buf_t) || !QSMC_ClaimDirectionalAlert(g_buf_t[closed],event_id)) return false;
```
`g_buf_t` is the chart series. On `XAUUSD M1` (chart TF == execution TF) the claim therefore resets **every minute** → ceiling = **1 alert/minute/chart**. On `BTCUSD M5` the ceiling is 1/5 min but the sampling is coarse (the M1 closed bar is only read at M5 boundaries, `14718`).

**Third amplifier — `InpUpdateEveryTick = true` by default** (`1013`), so the whole body including `UpdateMTFExecutionEntry()` runs on every tick, not only on new bars.

### Symptom 2 — wrong LOCATION (SELL at support, BUY at resistance)

**Root cause: the direction is taken from the HTF bias, and no zone is read.**

```mq5
5292:  else if(g_htf_bias==1 || g_htf_bias==-1)
5293:  {
5294:     have_dir=true; bull=(g_htf_bias>0);
5295:     for(int i=ArraySize(g_structures)-1;i>=0;i--)
5296:     { if(g_structures[i].type=="INIT" || g_structures[i].bullish!=bull) continue;
5297:       trigger=g_structures[i].price; trigger_time=g_structures[i].time; break; }
5298:  }
5299:  if(InpUseHTFBias && g_htf_bias!=(bull?1:-1)){ ClearMTFExecutionEntry(); return; }
```

There is **no reference to `g_zre_zones`, `g_zre_status`, `ZRE_*`, `RXN_*` or `GetSignalDirection()` anywhere in `UpdateMTFExecutionEntry()` (5283-5393)**. The only filter is `5299`, which checks that the bias agrees with the direction the bias itself produced — a tautology.

**Minimal reproduction** (XAUUSD M5, ATR = 2.00):

| Bar | O | H | L | C | Context |
|---|---|---|---|---|---|
| N-1 | 3305.00 | 3306.00 | 3300.20 | 3305.50 | leaving the support |
| N | 3305.50 | 3306.20 | 3299.40 | 3300.80 | price **inside** the support band 3300.00-3302.00 (strength 80) |
| N+1 (M1 exec bars) | … | … | … | closes above `trigger`=3299.00 with `cc>co` | `closed_confirm = true`, `bull = (g_htf_bias>0) = false` |

With `g_htf_bias = -1` the path emits **SELL at 3300.xx, inside a strong SUPPORT**. With `g_htf_bias = +1` and price inside RESISTANCE it emits **BUY into RESISTANCE**. Both are exactly the reported behaviour. The rejection/acceptance machinery that would have prevented this already exists in the file (`GetSignalDirection`, `31585-31610`) and is simply not called.

### Symptom 3 — the tactical path is independent of ZRE / RXN / the core engine

**Confirmed by construction and by ordering.**

* Independence: the function body (`5283-5393`) reads no zone state and calls no ZRE, RXN or CORE function.
* Ordering: it is invoked at `14718`, i.e. **78 lines before `ZRE_Update` (`14796`) and 89 lines before `RXN_Update` (`14807`)**.
* It does not go through `AlertDispatcherSubmit()` (`36201`) at all. The comment at `14808` says *"One closed-bar arbiter for Core/ZRE/RXN directional alerts; no live-preview alert path"* — the tactical path is not in that list.
* Misleading word: `5389` prints `ENTRY CONFIRMED` while the same string says `NON-AUTHORITATIVE`. `CONFIRMED` is produced by a closed execution bar satisfying `ch>=trigger && cc>co && cc>=trigger` (`5325`) — an execution fact, not a trade signal.

**Additional damage:** because the tactical alert claims the chart bar (`21863`), `AlertDispatcherFinalize` returns at `36461` and the authoritative ZRE/RXN/CORE alert for the same bar is **silently dropped**.

### Symptom 4 — the user cannot tell why a signal appeared

The alert text is built inline at `5389` from six fields: symbol, TF, direction, state word, price, execution TF. It contains **no zone, no zone strength, no evidence, no stop, no target, no RR, no reason**. Contrast with the dispatcher's own text builder `AlertCompactLine()` (`36273-36286`), which does carry zone range, score, `needs` and invalidation — the tactical path never uses it.

### 3.1 Suspected bug classes — verdicts

| Suspected class | Verdict | Evidence |
|---|---|---|
| Zone role / direction inversion (support treated as resistance, sign errors, wrong "nearest") | **REFUTED in ZRE/RXN. CONFIRMED as an omission in the tactical path.** | `GetSignalDirection` (`31585-31610`) is correct and role-aware; `ZRE_ClassifyState` (`31612`) is role-aware for `BROKEN`. The tactical path never calls either (`5283-5393`). |
| Zone strength computed but never used as a gate | **CONFIRMED** | `SZREZone.strength` is computed (`ZRE_ScoreZone`, `31165`) and used to *keep* zones (`InpZREMinZoneScore`) and to score signals, but the tactical alert (`5389`) has no strength term at all. |
| Lower-TF (M1) execution signal overriding chart-TF context | **CONFIRMED** | `SelectExecutionTF()` (`5257-5264`) picks M1 for any chart ≤ M5. The tactical state machine runs entirely on that M1 bar (`5302-5306`) while the alert is claimed against the **chart** bar (`21861-21863`). On an M5 chart the M1 bar is only sampled at M5 boundaries (`14718`). |
| State / dedupe stored in globals that reset on `OnInit` / TF switch / symbol change | **CONFIRMED (partially)** | `g_last_mtf_entry_id`, `g_last_mtf_entry_key`, `g_mtf_sig_time`, `g_entry_keys[]` are plain globals (`1844-1857`). `g_directional_alert_bar_time` is reset in `AlertDispatcherClear()` (`36034`) which is called **only from `OnInit`** (`13680`) — so it is **not** reset on TF switch or symbol change, which is why the claim can also suppress across a symbol change within one attach. `InpArbUseGlobalVars` + `CAlertManager::CleanupGlobalVars()` now bound the cross-chart case. |
| Look-ahead / repaint (shift 0, forming bar, future HTF candle) | **CONFIRMED for the label, REFUTED for the confirmation** | `closed_confirm` correctly uses exec bar 1 (`5303`, `5325`). But `live_cross` (`5321`) reads bar 0 and flips the displayed state between PREVIEW and CONFIRMED within a bar, and `UpdateEarlyBreakPreview` reads `h[forming]`/`c[forming]` (`23566`, `23577-23579`) to set the tactical trigger. No future HTF candle is read (`ComputeClosedStructureBias` is closed-bar). |
| Multiple chart instances sending duplicate alerts | **CONFIRMED as a risk, UNVERIFIABLE on one terminal** | Nothing in v6.5.5 coordinates charts: the claim (`36121-36128`) is per-instance. Two charts of `BTCUSD` at M5 and M1 both evaluate the same zone and both alert. v6.6.0 adds a terminal `GlobalVariable` claim (`CAlertManager::Publish`, `QSMC_GV_PREFIX`); whether two live charts actually interleave correctly **must be verified on the user's terminal** (see §8). |
| Integer/double price comparison, `NormalizeDouble`, tick size (BTC vs XAU) | **CONFIRMED as a latent defect** | The tactical path compares prices with raw `>=`/`<=` against a trigger stored at `%.5f` precision (`5333`) and uses `InpEarlyBreakBufferPoints*_Point` (`23576`). `%.5f` is wrong for XAUUSD quoted with 3 digits and for BTCUSD at ~100000.00 (2 digits, 5 decimals of a 6-figure number). No `NormalizeDouble` and no tick alignment anywhere in the path. v6.6.0 introduces an explicit ATR-scaled epsilon (`CReactionDetector`, `eps=MathMax(_Point, atr*0.0005)`) and tick-rounds SL/TP (`QSMC_BuildGeometry`). |
| Array bounds, uninitialised buffers, partial `CopyBuffer` | **CONFIRMED (bounds) / REFUTED (CopyBuffer, fixed in v6.5.2)** | `g_early_break_structure_idx` is used as a flag at `5287` with **no** bounds check against `ArraySize(g_structures)`, while `EnforceArrayLimits()` (`14503`) truncates and left-shifts the master array — a stale index survives. `EMPTY_VALUE` handling in the entry buffers is correct (`6247-6250`, `6296-6299`). `CopyBuffer` partial copies **are** handled (`14373-14400`, v6.5.2 AUDIT-01) — but the tactical path's `iHigh/iLow/iClose/iTime` calls at `5302-5304` **check no return value at all**. |

---

## 4. PHASE 2 — OOP DESIGN (as built)

```
                         ┌──────────────────────────────────────────────┐
                         │  CQuantumRoot  (THE one global, g_qsmc_root) │
                         │  owns every member below; Init/Deinit/RAII   │
                         └────────────────────┬─────────────────────────┘
                                              │
   ┌──────────────┬───────────────┬───────────┼────────────┬──────────────┬─────────────┐
   │              │               │           │            │              │             │
   v              v               v           v            v              v             v
CMarketData   CZoneRegistry  CReaction-   CBias-      CPreset-       CSignal-      CStatsLogger
   │          (SQZone[])     Detector     Provider    Manager        Arbiter            │
   │                                                                    │              │
   │  CBarSeries x5 (chart / exec / D1 / H4 / H1)                       │         CSV journal
   │  - chronological, index 0 = oldest                                 │         + MFE/MAE
   │  - Ready() == complete copy only                                   │           (no look-ahead)
   │  - WarmATR / ATRAt / MeanTrueRange                                 │
   │                                                                    v
   │                                            ┌───────────────────────────────────────┐
   │                                            │  IGate  (MQL5 interface)              │
   │                                            │  Evaluate(cand,ctx,cfg,zones)->       │
   │                                            │     PASS / FAIL / DOWNGRADE + reason  │
   │                                            └───┬───────────────────────────────────┘
   │                                                │
   │        ┌───────────┬───────────┬───────────┬───┴────┬──────────┬──────────┬──────────┐
   │        v           v           v           v        v          v          v          v
   │  CClosedBar-  CDataQuality- CLocation-  CBias-  CRoom-     CVolatility- CCooldown- CFlipFlop-
   │    Gate         Gate        Gate        Gate    Gate          Gate        Gate        Gate
   │                                                                                     CDistance-
   │                                                                                     Gate
   │                                                                                     CSession-
   │                                                                                       Gate
   │                                                    │
   │                                                    v
   │                                    ┌───────────────────────────────────┐
   │                                    │ CAlertManager : IAlertHistory     │
   │                                    │  - THE ONLY Alert/PlaySound/      │
   │                                    │    SendNotification caller        │
   │                                    │  - exact-key ring (R5.1)          │
   │                                    │  - cooldown bars      (R5.2)      │
   │                                    │  - ATR price distance (R5.3)      │
   │                                    │  - flip-flop guard    (R5.4)      │
   │                                    │  - GlobalVariable cross-chart     │
   │                                    │  - BuildMessage() = the ONE text  │
   │                                    └───────────────────────────────────┘
   v
CChartRenderer  (PFX "QSMC_ARB_"; creates, moves and deletes only its own objects)
```

| Class | Responsibility | Complexity | Notes |
|---|---|---|---|
| `CBarSeries` | One timeframe of cached OHLCV; chronological; `Ready()` ⇔ complete copy; Wilder ATR; median volume; mean true range | `Refresh()` O(n) first call, O(1) fast path; `ATRAt` O(period·4) | Contract documented at the top of the file. Index `n-1` is always the forming bar and is never used for confirmed logic. |
| `CMarketData` | Owns the 5 series; one `RefreshAll()` per closed bar | O(Σ series) | `RefreshAll()` returns false unless chart **and** exec series are complete **and** ATR > 0. |
| `SQZone` + `CZoneRegistry` | Zone identity, role (causal birth role + confirmed flip), strength, merge by ATR tolerance, nearest/opposing lookup | `Rebuild` O(N log N); `Nearest` O(log N + k), N ≤ 64 | **`SQZone` is a struct, not a class**: MQL5 does not permit arrays of class objects. This is the one justified deviation from the proposed model — behaviour is identical. |
| `CReactionDetector` | Closed-bar rejection / acceptance + 6 independent evidence groups; retest detection; evidence score | O(1) per bar; O(lookback) for LTF-MSS and retest | Candle geometry mirrors the host's `SCandleIntel` thresholds so the two layers agree. |
| `CBiasProvider` | D1 50 / H4 30 / H1 20 weighted consensus, HTF-wins tie-break, closed pivots only | O(lookback) once per closed bar | An **unknown** timeframe is removed from the weight sum — never counted as agreement. |
| `CPresetManager` | SCALPER (M1-M5) / INTRADAY (M15-H1) / SWING (H4-D1) / CUSTOM | O(1) | Non-default input ⇒ user override wins (same convention as the host's `QSMC_PresetDouble`). |
| `IGate` + 10 gates | One rule per gate; `PASS` / `FAIL` / `DOWNGRADE` + mandatory reason | O(1) each; location/room O(log N + k) | Downgrade ⇒ **not alerted** (R5: alerts only for signals that survived every gate). |
| `CSignalArbiter` | One dispatcher; ranks; two-pass priority (authoritative > tactical); emits ≤ 1 per bar | O(C·G·(log N + k)), C ≤ 32, G = 10 | `Shutdown()` releases the gates before the leak report. |
| `CAlertManager` | The only terminal-alert caller; 5 locks; the one message builder | O(ring), ring ≤ 4096 | Implements `IAlertHistory` so the gates can query it without a circular include. |
| `CChartRenderer` | Owns every `QSMC_ARB_*` object | O(1) draw, O(objects) clear | Never deletes an object it did not create. |
| `CStatsLogger` | CSV journal + MFE/MAE/bars-to-result | O(1) log; O(open rows) advance | No rate is printed below `InpArbMinSample`; a count is never presented as a probability. |
| `CQuantumRoot` | The single root: owns all of the above, drives the per-bar pipeline | — | `AllocCalls() == FreeCalls()` printed on Deinit. |

**Encapsulation / RAII:** the only new global mutable state is `CQuantumRoot *g_qsmc_root` (`QSMC_Root.mqh`). Every `new` inside the subsystem is released by a destructor or by `Shutdown()`; the Deinit log prints the alloc/free counters.

---

## 5. PHASE 3 — SOURCE FILES

Install into the MT5 data folder (the include path is exactly `<data folder>/MQL5/Include/QSMC/`):

| File | Bytes | Lines | Role |
|---|---|---|---|
| `QSMC_AlertManager.mqh` | 15,081 | 370 |
| `QSMC_Arbiter.mqh` | 15,356 | 401 |
| `QSMC_Bias.mqh` | 8,247 | 205 |
| `QSMC_Gates.mqh` | 20,760 | 471 |
| `QSMC_MarketData.mqh` | 21,229 | 508 |
| `QSMC_Preset.mqh` | 14,543 | 275 |
| `QSMC_Reaction.mqh` | 16,024 | 367 |
| `QSMC_Renderer.mqh` | 7,382 | 167 |
| `QSMC_Root.mqh` | 28,038 | 684 |
| `QSMC_Selftest.mqh` | 30,674 | 708 |
| `QSMC_Stats.mqh` | 11,038 | 275 |
| `QSMC_Types.mqh` | 15,598 | 416 |
| `QSMC_Zones.mqh` | 16,241 | 412 |
| `MQL5/Scripts/QSMC_ArbiterTest.mq5` | 3,636 | 68 |
| `nadir2.mq5` | 1,799,730 | 39,782 |
| `tools/apply_qsmc_arb_patch.py` | 12,354 | 300 |
| `tools/static_check.py` | 14,708 | 325 |
| `tools/check_scenario_geometry.py` |
| `tools/test_arbiter.py` | 33,212 | 830 |
| `docs/KLJ_V6.6.0_SIGNAL_ARBITRATION.md` | 61,754 | 658 |

### 5.1 The seven surgical edits to `nadir2.mq5`

| # | Location (patched line) | Edit |
|---|---|---|
| 1 | `631` | `#include <QSMC/QSMC_Root.mqh>` after the `#property` block, plus the `QSMC_ARB_PATCH_MARKER` guard |
| 2 | `13710-13793` | new host function `QSMC_ArbiterFeedAndFinalize()` — converts `g_zre_zones`+`g_zre_status` into `SQZone[]`, publishes the host's own bias, then calls `FinalizeBar()` |
| 3 | `13798` | `QSMC_RootCreate(SelectExecutionTF(),300,InpATRPeriod);` in `OnInit`, right after `AlertDispatcherClear()` (`13797`) |
| 4 | `14245` | `QSMC_RootDestroy();` as the first statement of `OnDeinit` |
| 5 | `5359-5385` | the tactical path **records** a `STacticalFact` instead of alerting |
| 6 | `5398-5406` | label wording: `TACTICAL / CONFIRMED` → `TACTICAL-INFO (exec bar closed)` + ` \| gated by ARB` |
| 7 | `5418-5424` | the old `if(InpAlertOnMTFExecutionEntry){…FireQuantAlert…}` block is **deleted** |
| 8 | `36529` | `QSMC_ArbiterFeedAndFinalize(rates_total,closed,g_alert_candidate_count>0);` inside `AlertDispatcherFinalize`, placed **after** the once-per-bar guard |

Everything else in the 39,655 lines is byte-identical. `git diff` on `nadir2.mq5` shows only these hunks.

**Escape hatch:** set `InpArbEnabled=false` and the subsystem is inert (the root is never created, `FinalizeBar` is a no-op, no object is drawn, no alert is suppressed). The indicator then behaves as v6.5.5.

### 5.2 MQL5 conformance (Phase 3 rules)

* MQL5 only. **No** STL, lambdas, exceptions, multiple inheritance, operator overloading, `dynamic_cast`, `template`. Verified mechanically by `tools/static_check.py` (rule 2).
* Every `CopyRates` return is compared against the requested count; a short copy sets `Ready()=false` and the bar is **not** consumed (`CBarSeries::Refresh`).
* Every array access is bounds-guarded; every division is guarded (`atr>0.0`, `risk>0.0`, `range>0.0`).
* Series orientation is set explicitly and documented per array: `ArraySetAsSeries(m_o,false)` … — index 0 = oldest. `CopyRates` results are re-written into that orientation at the boundary.
* **No shift-0 logic reaches a CONFIRMED decision.** `CClosedBarGate` refuses `bar_index<1`; `CReactionDetector::Evaluate` returns false for `bar_index<1 || bar_index>ClosedIndex()`.
* All user-visible strings are built in exactly two places: `CAlertManager::BuildMessage()` and `CChartRenderer`.
* No `OrderSend`, no trade function, no position/order API anywhere in the subsystem.
* Recursion: none. Every loop has a hard bound (`QSMC_ZONE_MAX`, `QSMC_ARB_MAX_CANDIDATES`, `QSMC_TACTICAL_MAX_FACTS`, `QSMC_STATS_MAX_ROWS`, bounded outward scan in `CZoneRegistry::Nearest`).
* No per-tick recomputation: the whole pipeline runs inside `AlertDispatcherFinalize` after the host's own `g_alert_finalized_bar_time==bar_time` once-per-bar guard.

### 5.3 Manual "compiler pass"

`tools/static_check.py` performs the parts of a compiler pass that can be done by reading:

```
$ python3 tools/static_check.py
  WARN  QSMC_Arbiter.mqh: 10 new site(s), 3 delete site(s); balance is verified at runtime by AllocCalls()/FreeCalls()
  WARN  QSMC_MarketData.mqh: 5 new site(s), 1 delete site(s); balance is verified at runtime by AllocCalls()/FreeCalls()
  WARN  QSMC_Root.mqh: 1 new site(s), 1 delete site(s); balance is verified at runtime by AllocCalls()/FreeCalls()
  no errors, 3 warning(s)
```

The three warnings are expected: the `delete` sites sit in loops/destructors, and the runtime `AllocCalls()/FreeCalls()` counters are the real check (printed on Deinit).

**Identifier ledger — every identifier this release introduces, and where it is declared:**

| Kind | Identifiers | Declared in |
|---|---|---|
| Enums | `ENUM_ZR_ROLE`, `ENUM_ZR_LOC`, `ENUM_ZR_STATE`, `ENUM_SIG_STATE`, `ENUM_SIG_SOURCE`, `ENUM_GATE_RESULT`, `ENUM_VOL_REGIME` | `QSMC_Types.mqh` |
| Enum | `ENUM_QSMC_PRESET` | `QSMC_Preset.mqh` |
| Structs | `SQZone`, `SQZoneHit`, `SReactionFacts`, `SGateCtx`, `SSignalCandidate`, `SGateResult`, `SQsmcArbConfig` | `QSMC_Types.mqh` |
| Structs | `SArbiterReport`, `STacticalFact` | `QSMC_Arbiter.mqh`, `QSMC_Root.mqh` |
| Struct | `SSigRow` | `QSMC_Stats.mqh` |
| Interfaces | `IAlertHistory`, `IGate` | `QSMC_Gates.mqh` |
| Classes | `CBarSeries`, `CMarketData` | `QSMC_MarketData.mqh` |
| Classes | `CZoneRegistry` | `QSMC_Zones.mqh` |
| Classes | `CReactionDetector` | `QSMC_Reaction.mqh` |
| Classes | `CBiasProvider` | `QSMC_Bias.mqh` |
| Classes | `CPresetManager` | `QSMC_Preset.mqh` |
| Classes | `CClosedBarGate`, `CDataQualityGate`, `CLocationGate`, `CBiasGate`, `CRoomGate`, `CVolatilityGate`, `CCooldownGate`, `CFlipFlopGate`, `CDistanceGate`, `CSessionGate` | `QSMC_Gates.mqh` |
| Classes | `CAlertManager` | `QSMC_AlertManager.mqh` |
| Classes | `CSignalArbiter` | `QSMC_Arbiter.mqh` |
| Classes | `CStatsLogger` | `QSMC_Stats.mqh` |
| Classes | `CChartRenderer` | `QSMC_Renderer.mqh` |
| Classes | `CQuantumRoot`, `CArbSelfTest` | `QSMC_Root.mqh`, `QSMC_Selftest.mqh` |
| Free functions | `QSMC_TFName`, `QSMC_RoleName`, `QSMC_StateName`, `QSMC_SourceName`, `QSMC_LocName`, `QSMC_EvidenceName`, `QSMC_EvidenceList`, `QSMC_EvidenceCount`, `QSMC_MissingEvidence` | `QSMC_Types.mqh` |
| Free function | `QSMC_BuildGeometry` | `QSMC_Zones.mqh` |
| Free functions | `QSMC_RootCreate`, `QSMC_RootDestroy`, `QSMC_Root` | `QSMC_Root.mqh` |
| Free function | `QSMC_RunSelfTest` | `QSMC_Selftest.mqh` |
| Global variable | `CQuantumRoot *g_qsmc_root` | `QSMC_Root.mqh` (the **only** new global mutable state) |
| Inputs (32) | `InpArbEnabled`, `InpArbPreset`, `InpArbGateTactical`, `InpArbTacticalMayConfirm`, `InpArbGateCore`, `InpArbPopup`, `InpArbPush`, `InpArbSound`, `InpArbVerboseLog`, `InpArbCSVLog`, `InpArbZoneReachATR`, `InpArbMergeTolATR`, `InpArbMaxPenetrationATR`, `InpArbBreakATR`, `InpArbMinZoneStrength`, `InpArbMinEvidence`, `InpArbRetestLookback`, `InpArbMinWickRatio`, `InpArbVolumeMult`, `InpArbDispATR`, `InpArbBiasW_D1`, `InpArbBiasW_H4`, `InpArbBiasW_H1`, `InpArbAllowCounterTrend`, `InpArbCounterTrendMinScore`, `InpArbCounterTrendExtraEv`, `InpArbMinRR`, `InpArbMaxStopATR`, `InpArbSLBufferATR`, `InpArbCooldownBars`, `InpArbMinAlertDistanceATR`, `InpArbFlipFlopBars`, `InpArbUseGlobalVars`, `InpArbDedupeRing`, `InpArbMinATRPoints`, `InpArbMaxSpreadPoints`, `InpArbMinBars`, `InpArbSessionStartHour`, `InpArbSessionEndHour`, `InpArbMinSample` | `QSMC_Preset.mqh` |

**Checks performed:**
1. Every `#include` resolves — `<QSMC/QSMC_Types.mqh>`, `<QSMC/QSMC_MarketData.mqh>`, `<QSMC/QSMC_Zones.mqh>`, `<QSMC/QSMC_Reaction.mqh>`, `<QSMC/QSMC_Bias.mqh>`, `<QSMC/QSMC_Preset.mqh>`, `<QSMC/QSMC_Gates.mqh>`, `<QSMC/QSMC_AlertManager.mqh>`, `<QSMC/QSMC_Arbiter.mqh>`, `<QSMC/QSMC_Stats.mqh>`, `<QSMC/QSMC_Renderer.mqh>`, `<QSMC/QSMC_Root.mqh>`, `<QSMC/QSMC_Selftest.mqh>`. Order is acyclic (Types → MarketData → Zones → Reaction/Bias → Gates → AlertManager → Arbiter → Stats/Renderer → Root → Selftest).
2. Every interface method is implemented: `IAlertHistory` (3 methods) by `CAlertManager`; `IGate` (2 methods) by all 10 gates.
3. Every struct member referenced with `.` exists on that struct (type-inferred).
4. Brace/paren/bracket balance per file.
5. **No name collision with the host file.** The host already declares `struct SZone` (`nadir2.mq5:3196`) and `SZone g_zones[]` (`3500`); the new zone record was renamed `SQZone` for this reason. A 60-identifier collision scan against `nadir2.mq5` returned only that one hit.
6. Every input name used in code is declared in `QSMC_Preset.mqh`; `InpArbCSVLog`, `InpArbMinSample`, `InpArbTacticalMayConfirm`, `InpArbGateCore` are read in `QSMC_RootCreate()`; `InpArbEnabled`, `InpArbGateTactical`, `InpAlertOnMTFExecutionEntry` (host input) are read in the patched `UpdateMTFExecutionEntry`.

**What this pass cannot do:** it is not a type checker. It cannot catch a wrong argument order, an implicit conversion the compiler rejects, a missing `const`, or an MQL5-specific restriction on returning a class by value. **Press F7.**

---

## 6. PHASE 6 — CHANGELOG (every behavioural change)

### 6a. Behavioural changes

| # | Area | Old (v6.5.5) | New (v6.6.0) | Reason |
|---|---|---|---|---|
| B1 | Tactical alert emission | `UpdateMTFExecutionEntry` called `FireQuantAlert()` directly (`5389`) | The path records a `STacticalFact`; `CSignalArbiter` decides once per closed bar; `CAlertManager` emits | Symptoms 1-4; R5, R7 |
| B2 | Tactical direction | from `g_early_break_*` / `g_active_setup` / **`g_htf_bias` + last matching structure** (`5287-5298`) | from the nearest zone's **role** + a closed-bar reaction/acceptance fact (`CQuantumRoot::BuildTacticalCandidate`) | Symptom 2; R1 |
| B3 | Tactical location gate | none | `CLocationGate`: between-zones refusal, role check, strength floor, broken-not-retested refusal, penetration bound, evidence floor | R1 |
| B4 | Tactical room / RR | none | `CRoomGate`: stop ≤ `InpArbMaxStopATR`, RR ≥ `InpArbMinRR`, barrier must leave `(RR+1)·risk` | R4 |
| B5 | Tactical HTF filter | `g_htf_bias!=(bull?1:-1)` → clear (`5299`) | `CBiasGate`: neutral/unknown never licences; opposed ⇒ `COUNTER-TREND / SCALP ONLY` or refusal | R2 |
| B6 | Tactical closed-bar rule | `state=closed_confirm?"CONFIRMED":"PREVIEW"` (`5331`) and the label flipped on `live_cross` | `CClosedBarGate` demotes a forming-bar fact to `PREVIEW`; `PREVIEW` is never alerted | R3 |
| B7 | Tactical state cap | could print `CONFIRMED` | capped at `TACTICAL-INFO` unless `InpArbTacticalMayConfirm=true` | R7 |
| B8 | Tactical dedupe | `id\|state[\|sig_time]` ring of 1 (`5380`) | exact-key ring (`InpArbDedupeRing`, default 256) + cooldown + ATR distance + flip-flop + cross-chart GlobalVariable | Symptom 1; R5 |
| B9 | Tactical alert text | 6 fields, no zone/evidence/SL/TP/RR/reason (`5389`) | `CAlertManager::BuildMessage()` — symbol, TF, direction, state, zone id, zone range, strength, evidence list + count, entry, SL, TP1, RR, room, bar + closed flag, source, score, reason, blocked-by | R6 |
| B10 | Tactical label | `TACTICAL / CONFIRMED` | `TACTICAL-INFO (exec bar closed)` + ` \| gated by ARB` | R7 |
| B11 | Bar-slot priority | a tactical alert claimed the chart bar and `AlertDispatcherFinalize` then returned early (`21863`, `36461`) | `FinalizeBar(authoritative_pending)`: if ZRE/RXN/CORE submitted anything for the bar, the tactical path is suppressed | Priority inversion |
| B12 | Zone consumption | tactical path read no zone | fed from `g_zre_zones` + `g_zre_status`, resolved **after** `ZRE_Update`/`RXN_Update` (`36529`) | Symptoms 2, 3 |
| B13 | Retest rule | n/a | `CReactionDetector::DetectRetest` + `CQuantumRoot::SetZones` mark a broken zone `retested` only after a closed-bar retest holds | R1 |
| B14 | Data quality | `iHigh/iLow/iClose/iTime` return values unchecked (`5302-5304`) | `CBarSeries::Ready()` ⇔ complete copy; partial = retry, bar not consumed; `CDataQualityGate` adds an ATR floor, a spread cap and a bar-count floor | AUDIT-01 discipline applied to the tactical path |
| B15 | Price comparison | raw `>=`/`<=` against a `%.5f` trigger | ATR-scaled epsilon `MathMax(_Point, atr*0.0005)`; SL/TP tick-rounded; TP1 rounded **away** from entry | BTC/XAU tick-size defect |
| B16 | Chart objects | — | `CChartRenderer` owns `QSMC_ARB_*`: primary arrow + "what" + "why" labels + a "no signal because…" line | R6; "understand why" |
| B17 | Journal | — | optional CSV `MQL5/Files/QSMC_ARB_<SYM>_<TF>_<YYYYMMDD>.csv` (`InpArbCSVLog=false` by default) | Auditability |
| B18 | Leak report | — | `AllocCalls()/FreeCalls()` printed on Deinit | RAII verification |

### 6b. Inputs — **no existing input was renamed, removed or re-defaulted**

`InpUseMTFExecutionEntry`, `InpAutoExecutionTF`, `InpExecutionTF`, `InpMTFEntryMaxDistanceATR`, `InpAlertOnMTFExecutionEntry`, `InpShowMTFExecutionEntry`, `InpShowTacticalEntries`, `InpChaseFilter`, `InpChaseMaxATR`, `InpAlertOnSignalBar` are all **unchanged** and all still honoured.

`InpAlertOnMTFExecutionEntry=true` still means "the tactical path may alert" — but now only through the gates. `InpAlertOnSignalBar` still anchors the label/arrow at the signal bar; it no longer influences any key.

**New inputs (all default to the behaviour described):**

| Input | Default | Meaning |
|---|---|---|
| `InpArbEnabled` | `true` | master switch; `false` = v6.5.5 behaviour |
| `InpArbPreset` | `AUTO` | SCALPER / INTRADAY / SWING / CUSTOM |
| `InpArbGateTactical` | `true` | route the tactical path through every gate |
| `InpArbTacticalMayConfirm` | `false` | `true` would let the tactical path publish `CONFIRMED` (not recommended) |
| `InpArbGateCore` | `false` | `true` also gates the CORE path (off by default: CORE keeps its own validated gates) |
| `InpArbPopup` / `InpArbPush` / `InpArbSound` | `true` / `false` / `false` | channels |
| `InpArbVerboseLog` | `false` | print every gate verdict per closed bar |
| `InpArbCSVLog` | `false` | write the signal CSV |
| `InpArbZoneReachATR` | `1.50` | beyond this ⇒ BETWEEN ZONES / NO TRADE |
| `InpArbMergeTolATR` | `0.50` | zone merge tolerance |
| `InpArbMaxPenetrationATR` | `0.35` | bounded penetration for a rejection |
| `InpArbBreakATR` | `0.30` | closed bar beyond the role edge = acceptance |
| `InpArbMinZoneStrength` | `60` | strength floor |
| `InpArbMinEvidence` | `2` | independent evidence groups of 6 |
| `InpArbRetestLookback` | `24` | bars a broken zone has to retest within |
| `InpArbMinWickRatio` | `0.50` | rejection wick / range |
| `InpArbVolumeMult` | `1.60` | volume / 20-bar median |
| `InpArbDispATR` | `0.50` | displacement away from the level |
| `InpArbBiasW_D1` / `_H4` / `_H1` | `50` / `30` / `20` | documented v6.5.3 D7 weights |
| `InpArbAllowCounterTrend` | `true` | `false` = refuse every counter-trend signal |
| `InpArbCounterTrendMinScore` | `70` | evidence score needed against the bias |
| `InpArbCounterTrendExtraEv` | `1` | extra evidence group needed against the bias |
| `InpArbMinRR` | `1.50` | RR floor to TP1 |
| `InpArbMaxStopATR` | `4.00` | stop ceiling |
| `InpArbSLBufferATR` | `0.20` | invalidation buffer beyond the zone edge |
| `InpArbCooldownBars` | `10` | bars between two alerts of the same (symbol, zone, dir, state) |
| `InpArbMinAlertDistanceATR` | `0.50` | min price move from the previous alert on that zone+direction |
| `InpArbFlipFlopBars` | `10` | suppress the opposite direction on the same zone |
| `InpArbUseGlobalVars` | `true` | cross-chart claim |
| `InpArbDedupeRing` | `256` | exact keys retained |
| `InpArbMinATRPoints` | `0.0` | dead-market floor (0 = one tick) |
| `InpArbMaxSpreadPoints` | `0` | 0 = no spread gate |
| `InpArbMinBars` | `120` | minimum closed bars |
| `InpArbSessionStartHour` / `InpArbSessionEndHour` | `-1` / `-1` | -1 = no session filter |
| `InpArbMinSample` | `30` | below this n, no rate is printed |

**Preset values** (applied only while the corresponding input still equals its documented default — any non-default value is treated as an explicit override, so saved `.set` files keep working):

| Parameter | SCALPER (M1-M5) | INTRADAY (M15-H1) | SWING (H4-D1) |
|---|---|---|---|
| `zone_reach_atr` | 1.20 | 1.50 | 2.00 |
| `merge_tol_atr` | 0.40 | 0.50 | 0.75 |
| `max_penetration_atr` | 0.25 | 0.35 | 0.50 |
| `break_atr` | 0.20 | 0.30 | 0.40 |
| `min_zone_strength` | 55 | 60 | 65 |
| `min_evidence` | 2 | 2 | 3 |
| `retest_lookback` | 16 | 24 | 40 |
| `min_wick_ratio` | 0.45 | 0.50 | 0.55 |
| `volume_mult` | 1.40 | 1.60 | 1.80 |
| `displacement_atr` | 0.40 | 0.50 | 0.60 |
| `min_rr` | 1.20 | 1.50 | 2.00 |
| `max_stop_atr` | 3.00 | 4.00 | 6.00 |
| `sl_buffer_atr` | 0.15 | 0.20 | 0.30 |
| `cooldown_bars` | 20 | 10 | 3 |
| `min_alert_distance_atr` | 0.35 | 0.50 | 1.00 |
| `flipflop_bars` | 20 | 10 | 3 |

**Thresholds/weights deliberately NOT changed:** every ZRE weight (`ZRE_W_*`, `3602-3609`), every ZRE signal weight (`ZRE_P_*`, `3677-3684`), `InpZREMinZoneScore`, `InpZREMinEvidence`, `InpRXNMin*Score`, `InpRXNCountertrendMargin`, `InpRXNMinRoomATR`, `InpMinRR1`, `InpMaxStopATR`, `InpSLBufferATR`, `InpProximityFilter`/`InpProximityMaxATR`, `InpChaseFilter`/`InpChaseMaxATR`, `InpTopDownMinRR`, and the v6.5.3 D7 bias weights (the new layer *reuses* 50/30/20 rather than re-tuning them).

### 6c. Deleted code

Only one block was deleted: the 18-line `if(InpAlertOnMTFExecutionEntry){…}` alert block at v6.5.5 `5375-5392`. It is replaced by a comment explaining what it used to do. Nothing else was removed; no public input was removed.

---

## 7. PHASE 4 — TEST SCENARIOS, HARNESS, VALIDATION PROTOCOL

### 7a. The ten deterministic scenarios

ATR is **2.00 in every scenario, in both harnesses** (`QST_ATR` in `QSMC_Selftest.mqh`, asserted by **T00**); `_Point` = 0.01; zones `R 108.00-109.00 strength 80` and `S 90.00-91.00 strength 78`; INTRADAY preset unless stated; `n = 40` bars (39 = last closed, 40 = forming).

| # | Setup | Expected decision | Expected reason | MQL5 assertion | Python assertion |
|---|---|---|---|---|---|
| 1 | Price rises into `R`; the **closed** bar `O 106.80 H 109.40 L 106.70 C 107.10 V 2000` | **SELL CONFIRMED once**, then **no repeat for 20 bars** | `rejection at RESISTANCE`, evidence `wick+candle+volume+displacement+sweep` (5/6), score 84 | T01a-d | T01a-d |
| 2 | `O 108.40 H 110.10 L 108.20 C 110.00` — closes 1.00 (0.50 ATR) above `R.hi` | **BUY continuation**; **no SELL** | `acceptance at RESISTANCE` | T02a-c | T02a-c |
| 3 | Price **inside** `S 90.00-91.00`, `C 90.40`, the tactical path wants to SELL | **Blocked by CLocationGate** | `SELL at SUPPORT … without a closed-bar breakout (forbidden by R1)` **or** `the execution bar did not reject or accept …` | T03a-b | T03a-b |
| 4 | Price at 100.80, nearest zone 3.60 ATR away | **NO TRADE** | `BETWEEN ZONES - nearest zone is 3.60 ATR away, limit is 1.50 ATR` | T04a-b | T04a-c |
| 5 | The fact cites the **forming** bar (index 39) | **PREVIEW at most**; never `CONFIRMED`; no alert named `CONFIRMED` | `forming bar - CONFIRMED requires a closed bar (R3)` | T05a-c | T05a |
| 6 | 30 consecutive M1 bars each genuinely rejecting the same `R` | **exactly 1 alert** | first suppression = `cooldown 1/10` (then distance) | T06 | T06a-b (`published=1 suppressed=29`) |
| 7 | SELL published at `R`, then one bar later a genuine BUY acceptance above the same `R` | **Suppressed** | `flip-flop guard 1/10` | T07 | T07a-c |
| 8 | Two roots (simulating two charts) evaluate the same bar and zone | **1 alert** | second: `already published by another chart of this symbol` | T08 | T08 |
| 9 | Weak rejection with a **bullish** HTF consensus (`+1/+1/+1`), candidate SELL | downgraded or refused; **never** `CONFIRMED` | `COUNTER-TREND: only N evidence groups, 3 required` | T09a-b | T09a-b |
| 10 | No series loaded | **No signal** | `data not ready: chart series not ready` | T10a-b | T10 |

Both harnesses print one line per assertion and a final count.

**A defect the cross-check exposed, and how it is now guarded.** The MQL5
scenario bars were originally written assuming ATR = 2.00, but the harness's
own `Flat(QST_BARS, base, 0.30, ...)` generates bars with a true range of
`2 x 0.30`, so the Wilder ATR converged to **0.60**, not 2.00. Because every
distance in every scenario is expressed in ATR units, that single unit error
silently invalidated the geometry:

| Scenario | Intended | Actual at ATR = 0.60 |
|---|---|---|
| T01 | bounded rejection, penetration 0.20 ATR | penetration **0.67 ATR** vs a 0.35 cap → no rejection → **T01a would FAIL** |
| T07 | SELL then a genuine BUY acceptance | the first bar also over-penetrates; the second bar's close 109.10 did not clear 109.00 + 0.30x0.60, so it was neither an acceptance nor a rejection → **T07 untestable** |
| T06 | 30 bars each rejecting the zone | only k >= 23 reached the band; 7 of 30 valid → passed, but could not detect a removed anti-spam lock |
| T08 | two charts, one symbol | same bar as T01 → no publication at all → passed trivially |

Fixed by driving `Flat()` from a single `QST_ATR` constant (`QST_HALF = QST_ATR/2`),
rewriting the T06 and T07 bars, and adding **T00**, which measures the
synthetic ATR and fails if it drifts more than 5 % from `QST_ATR` — so a unit
mismatch of this class can no longer pass silently. `tools/check_scenario_geometry.py`
ports `Flat()`, `ComputeWilderATR()` and the touch/penetration/acceptance/closed-back
decision and predicts every scenario's arithmetic offline.

### 7b. Harness 1 — MQL5 Script (runs in the terminal)

`MQL5/Scripts/QSMC_ArbiterTest.mq5`

```
1. Copy MQL5/Include/QSMC/*.mqh  -> <data folder>/MQL5/Include/QSMC/
2. Copy MQL5/Scripts/QSMC_ArbiterTest.mq5 -> <data folder>/MQL5/Scripts/
3. MetaEditor: F7 (compile)
4. Navigator -> Scripts -> QSMC_ArbiterTest -> drag onto any chart
5. Read the Experts tab
```

It drives the **production** code path (`CQuantumRoot` → `CReactionDetector` → gates → `CSignalArbiter` → `CAlertManager`) with synthetic bars via the documented test seams `CBarSeries::LoadSynthetic()` and `CQuantumRoot::LoadSynthetic()`. It opens no file, draws no object and places no order.

### 7c. Harness 2 — Python reference (runs anywhere)

```
$ python3 tools/test_arbiter.py -v
...
RESULT: 22 passed, 0 failed
```

An independent re-implementation of R1-R7. **If the two harnesses ever disagree, one of them contains a defect** — that is why both exist. It is not a backtest and produces no win rate.

### 7d. Manual validation protocol (the user's terminal)

**Preparation.** Back up the current build. Install the `QSMC` include folder. Compile `nadir2.mq5` (F7) — **fix any compiler error before going further**. Load it twice: once with `InpArbEnabled=false` (baseline) and once with `InpArbEnabled=true`.

**Step 1 — baseline (before).** Strategy Tester → Visual mode, `BTCUSD M5`, 10 trading days, "Every tick based on real ticks". Enable `InpAlertOnMTFExecutionEntry=true`, `InpArbEnabled=false`, `InpArbCSVLog=false`. Count `Alert()` lines in the Journal. Record **alerts/day** and, for each, whether the direction agrees with the nearest zone's role.

**Step 2 — after.** Same symbol, same dates, same ticks; `InpArbEnabled=true`, `InpArbCSVLog=true`. Record the same two numbers.

**Step 3 — repeat for `XAUUSD M1`** (the worst case: chart TF == execution TF, so the v6.5.5 ceiling is 1/minute).

**Step 4 — acceptance criteria.**

| Metric | Target |
|---|---|
| Alert count per day, BTCUSD M5 | **≥ 90 % reduction** vs Step 1 |
| Alert count per day, XAUUSD M1 | **≥ 90 % reduction** vs Step 1 |
| Alerts whose direction contradicts the nearest zone's role (R1) | **0** |
| Alerts whose text lacks a zone id, an SL, a TP1, an RR or a reason (R6) | **0** |
| Two alerts for the same `(symbol, zone, direction, state)` inside `InpArbCooldownBars` | **0** |
| `alloc/free` line on Deinit | **no leak** |

**Step 5 — two-chart test (the one thing the offline harness cannot prove).** Open `BTCUSD M5` and `BTCUSD M1` **in the same terminal**, both with the indicator. Wait for a reaction at a zone. Expected: **one** alert, not two. If you see two, set `InpArbUseGlobalVars=false` on both and re-test — if the duplicate persists, the GlobalVariable path is the cause and I need the Journal excerpt to fix it.

**CSV log format** (`MQL5/Files/QSMC_ARB_<SYMBOL>_<TF>_<YYYYMMDD>.csv`, one row per candidate evaluated):

| Column | Meaning |
|---|---|
| `seq` | monotonic row id |
| `signal_time` | open time of the decision bar |
| `symbol`, `tf` | instrument, chart timeframe |
| `source` | `CORE` / `ZRE` / `RXN` / `MTF-TACTICAL` |
| `state` | `NO TRADE` / `WATCH` / `PREVIEW` / `TACTICAL-INFO` / `COUNTER-TREND / SCALP ONLY` / `LIMITED ROOM` / `CONFIRMED` |
| `dir` | `+1` buy, `-1` sell, `0` non-directional |
| `zone_id` | deterministic `Z\|{S,R}\|lo\|hi` on the BIRTH role |
| `zone_lo`, `zone_hi`, `zone_role`, `zone_strength` | the zone that owned the decision |
| `evidence`, `evidence_count` | `+`-joined group names, count of 6 |
| `entry`, `sl`, `tp1`, `rr`, `room_atr`, `distance_atr` | geometry |
| `score` | evidence quality 0-100 (**not** a win rate) |
| `published` | `1` only if the alert actually reached `Alert()` |
| `reason` | why the state is what it is |
| `blocked_by` | `; `-joined `GATE: reason` list |

Audit query you can run on it: `SELECT count(*) WHERE published=1 GROUP BY day` for the reduction, and `SELECT count(*) WHERE dir>0 AND zone_role='RESISTANCE' AND published=1` for the R1 violation count (target 0 — note an *acceptance* BUY at resistance is legitimate, so also check `evidence`/`reason`).

---

## 8. KNOWN LIMITATIONS AND UNVERIFIED ITEMS

**Nothing below has been compiled or executed on a terminal.**

| # | Item | Status | What would prove it |
|---|---|---|---|
| 1 | **Compilation** | **UNVERIFIED** | Press F7 in MetaEditor. I have no compiler. |
| 2 | Actual alert-count reduction | **UNVERIFIED — no number is claimed** | Run §7d steps 1-4. The ≥ 90 % figure in the brief is a **target**, not a measurement. |
| 3 | Cross-chart dedupe via terminal GlobalVariables (scenario 8) | **WEAKLY VERIFIED** — the logic is exercised by two roots in one process, which is **not** the same as two charts in one terminal | §7d step 5 on the user's terminal |
| 4 | `CZoneRegistry::Nearest` worst-case complexity | claimed `O(log N + k)`, worst case `O(N)` with `N ≤ 64` | true by construction of the early-exit; not measured |
| 5 | `CReactionDetector` LTF-MSS group on real data | the rule is deterministic (a closed bar through the opposite side of the swing) but its **usefulness** is unmeasured | compare alert quality with and without `QEV_MSS` |
| 6 | Bias mapping: the host tracks one HTF bias (`g_htf_bias`), so H1 is declared **unknown** and removed from the weight sum | the consensus scale is therefore `±(D1·50 + HTF·30)/80` | if the user wants a true H1 term, `CBiasProvider` already computes it from the H1 series — drop the `SetExternalBias` call in `QSMC_ArbiterFeedAndFinalize` |
| 7 | `g_early_break_structure_idx` stale-index defect (§3.1) | **still present in the untouched host code** | now harmless: the tactical path no longer decides; a follow-up should bounds-check it at `5287` |
| 8 | The CORE path is **not** gated by default (`InpArbGateCore=false`) | intentional — CORE has its own validated gates and re-gating it risks suppressing valid signals | set `InpArbGateCore=true` and compare before adopting |
| 9 | Zone feed completeness | the subsystem sees only `g_zre_zones` (capped by `InpZREMaxZones`) **plus** nothing else — the recovered "tail" zones that RXN uses (`g_rxn_extra_zones`) are **not** fed | if a blocking zone is invisible to the arbiter, a signal can pass that RXN would have capped; feeding `g_rxn_extra_zones` too is a small follow-up |
| 10 | `InpArbMinEvidence` semantics | a **breakout/acceptance** cannot earn `QEV_WICK` or a reversal candle (by design: it has none) — it earns `QEV_CANDLE` only from displacement | with `min_evidence=3` (SWING) an acceptance may therefore never reach `CONFIRMED`; this is a deliberate conservative bias, but it may be too strict |
| 11 | Volatility regime thresholds (0.35 / 0.70 / 1.40 / 2.20 on short/long mean-true-range) | undocumented in v6.5.5 because no such gate existed; these are new and **untuned** | compare against the host's `InpATRLowRatio`/`InpATRHighRatio` if a disagreement shows up |
| 12 | `CStatsLogger` outcome rows | they are tracked, but **no rate is printed** below `InpArbMinSample` (30) by design | accumulate ≥ 30 closed rows before reading anything |
| 13 | Dead code | I found none I could safely delete beyond the one alert block; `g_last_mtf_entry_key`, `g_mtf_entry_state`, `g_mtf_sig_time` are retained because the **display path** still reads them (`5337`, `5343`, `5366`) | a follow-up cleanup once the user confirms the display still looks right |
| 14 | `docs/KLJ_V6.5.4_REACTION_CONFLICT_FIX.md` and the other `docs/*.md` files referenced by the source comments | **absent from this checkout** | I could not read them; if they contain thresholds that contradict anything above, they win |

**Deliberate non-changes:** no `OrderSend`; no probability, no win-rate and no "score as a probability" anywhere; no threshold silently retuned (§6b); no public input renamed; the 39,655-line engine is untouched except at the 8 documented seams.

---

## 9. HOW TO ROLL BACK

1. Set `InpArbEnabled=false` — the subsystem becomes inert, the indicator behaves as v6.5.5. (Keep the include folder installed.)
2. Or revert `nadir2.mq5` to the pre-patch file; `git diff` isolates the change.
3. Or delete the `MQL5/Include/QSMC` folder **and** revert — but the include is now required by the patched file, so do both together or the compile fails.
