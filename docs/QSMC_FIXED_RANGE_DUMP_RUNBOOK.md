# QSMC_FixedRangeDump — compiled/runbook and CSV evidence guide

Status: **COMPILATION NOT VERIFIED — RUNTIME NOT VERIFIED — CSV NOT VERIFIED.**
No MetaEditor/MT5 was run in the authoring environment. Every step below is
written for Windows + MetaTrader 5. Nothing in this document is evidence that
the script compiles, runs, or that any CORE signal is or is not present.

Purpose: an **isolated, diagnostic-only** dump of `nadir2` buffers 0..25 for a
fixed, closed-bar-only range. It is **not** a change to the baseline system
(see `docs/QSMC_BASELINE_HASHES.md`, tag `pre-refactor-v6.6.24`).

## 1. What it does / what it deliberately does not do

- Creates ONE nadir2 handle via `iCustom(symbol, PERIOD_M15, InpIndicatorName)`
  with **no input arguments** — the same call form the EA uses
  (`QSMC_AutoTrader` → `iCustom(_Symbol,_Period,InpIndicatorName)`), so
  compiled defaults apply. Documented difference: equivalence holds only if the
  EA chart symbol equals `InpSymbol` and the EA chart period is M15. This tool
  forces M15; it cannot reason about H1/H4 charts or about the EA on another TF.
- Accepts explicit `InpStart` / `InpEnd` as **exact M15 bar-open times in
  broker/server time**, inclusive. Endpoints that are not exact bar-open times
  are rejected (`iBarShift(...,exact=true)` + timestamp re-verification).
- Exports **closed bars only** — shift ≥ 1. If `InpEnd` resolves to shift 0
  (the forming bar) it is clamped to shift 1 and the log says so.
- Each CSV row carries `bar_time_server`, `shift_at_read`, `bar_status`,
  `bars_calculated`, then 26 raw cells; buffer **21 = `buffer_21_SCORE`**,
  buffer **22 = `buffer_22_CLASS`**.
- Cells distinguish: `READ_FAIL` (that buffer's `CopyBuffer` ≠ 1 for that bar),
  `EMPTY_VALUE` (genuine sentinel), `INVALID_NUMBER` (NaN/Inf), else raw
  double with 16 decimals. `bar_status` is `OK`, `COPY_SHORT`, `MISSING_BAR`,
  optionally suffixed `|BAR_CHANGED`.
- Detection/reporting: short `CopyBuffer` reads (per-cell `READ_FAIL` + log),
  missing bars (`MISSING_BAR`), invalid handles (fatal, before any output),
  bars changed while collecting (second pass re-resolves the same timestamp
  and compares full OHLC + tick volume + real volume + spread; `BAR_CHANGED`).
- Logs: symbol, timeframe, requested/actual range, row count, bar count of
  history, terminal build (`TERMINAL_BUILD`), indicator readiness
  (`BarsCalculated` vs required), synchronization flag. **No login, account,
  server, broker name, or credential is read or printed.**
- Creates **no orders, no GlobalVariables by the script itself**, no chart
  objects by the script itself, no trading state; never writes to indicator
  buffers; indicator outputs are not modified.

### 1.1 Mandatory side-effect limitation (do not skip)

The *script* is inert, but the *target indicator* is not. nadir2, when created
without the EA's GV handshake, will in its own `OnInit`:

- scan `GlobalVariablesTotal()/GlobalVariableName()` for
  `QSMC_EA_READER_HANDSHAKE_*` and **delete** fresh matches
  (`MQL5/Indicators/nadir2.mq5` ~14900–14955),
- take the **VISUAL** role and draw/delete `PFX`-prefixed chart objects on the
  host chart (same function, ~14900–14990),
- publish `GlobalVariableSet(p+"CORE"/"PROFILE"/"BARS"/"ARMED"/"CONF"/"TIME")`
  once per closed bar (`DiagPublishCoreState`, `nadir2.mq5` 20324–20354,
  called from `16445`).

The script cannot stop those without editing nadir2 (forbidden this step) or
creating the forbidden handshake GV. Therefore: run it ONLY in a **separate,
disposable, portable MT5 installation** on an **empty chart**, never on the
production terminal/chart. Isolation contains the side effects; it does not
remove them.

## 2. Buffer index map (INDICATOR_CALCULATIONS unless noted)

| Idx | Buffer | Idx | Buffer |
|-----|--------|-----|--------|
| 0 | BufEmaFast (DATA) | 13 | BufSigZREDir |
| 1 | BufEmaSlow (DATA) | 14 | BufSigZREEntry |
| 2 | BufVWAP (DATA) | 15 | BufSigZRESL |
| 3 | BufEntryBuy0 (DATA) | 16 | BufSigZRETP1 |
| 4 | BufEntrySell0 (DATA) | 17 | BufSigZRETP2 |
| 5 | BufPrevBuy0 (DATA) | 18 | BufSigZRETP3 |
| 6 | BufPrevSell0 (DATA) | 19 | BufSigCoreVerdict |
| 7 | BufSigCoreDir | 20 | BufSigZREVerdict |
| 8 | BufSigCoreEntry | **21** | **BufSigCoreScore — SCORE** |
| 9 | BufSigCoreSL | **22** | **BufSigCoreClass — CLASS** |
| 10 | BufSigCoreTP1 | 23 | BufSigCoreReliability |
| 11 | BufSigCoreTP2 | 24 | BufSigCoreRR1 |
| 12 | BufSigCoreTP3 | 25 | BufSigCoreRiskMult |

(`SetIndexBuffer` calls: `nadir2.mq5` 15157–15222.)

## 3. Windows runbook (MetaTrader 5)

### 3.0 Prerequisites

1. Windows + MT5 (any recent build; record `TERMINAL_BUILD` from the log).
2. A **disposable portable** copy of the terminal, e.g. `C:\MT5_PORTABLE_DIAG\`
   with `C:\MT5_PORTABLE_DIAG\terminal64.exe` and a `portable` folder next to
   it. Do NOT use the production terminal/chart/profile.
3. The broker symbol's M15 history downloaded (open the symbol, switch to
   M15, scroll back to the range start, enable "Download"/"Go into the past"
   until the range is present). Broker/server time is whatever the terminal
   charts show (`Market Watch → Symbols` → check chart times).
4. This repository at the tagged baseline, PLUS the one new file
   `MQL5/Scripts/QSMC_FixedRangeDump.mq5`.
5. `nadir2.mq5` and its `Include/QSMC/*.mqh` sources present (they already
   are, in this repo).

### 3.1 Install / copy (portable terminal)

```
set SRC=C:\path\to\terad
set PORT=C:\MT5_PORTABLE_DIAG\portable
copy "%SRC%\MQL5\Scripts\QSMC_FixedRangeDump.mq5" "%PORT%\MQL5\Scripts\"
xcopy "%SRC%\MQL5\Indicators\nadir2.mq5"          "%PORT%\MQL5\Indicators\" /Y
xcopy "%SRC%\MQL5\Include\QSMC\*.mqh"             "%PORT%\MQL5\Include\QSMC\" /Y
```

Do not copy a prebuilt `nadir2.ex5` from anywhere else; build it fresh.

### 3.2 Compile (MetaEditor)

1. Launch the portable terminal once (creates the folder layout), then close it.
2. Open **MetaEditor** from the portable terminal (`Tools → MetaQuotes Language
   Editor`, or `MetaEditor64.exe /portable` with the portable data folder).
3. `File → Open` → `MQL5\Indicators\nadir2.mq5` → press **F7** (Compile).
   - Expect **0 error(s)**. Warnings are acceptable only if you record them.
   - Record the full compile log tail (`nadir2.ex5` path, "0 errors").
4. `File → Open` → `MQL5\Scripts\QSMC_FixedRangeDump.mq5` → **F7**.
   - Expect **0 error(s)**. Record the log.
5. If either step fails: **STOP**. Do not patch production sources to fix a
   diagnostic script. Report the exact compiler output; equivalence stays
   NOT VERIFIED and nothing ships.

### 3.3 Run

1. Start the portable terminal, log in with any account you like (the tool
   prints no account data; a demo login is fine).
2. Open a **blank** chart: `File → New Chart → <symbol>`, period **M15**.
   No indicators, no EA, nothing else on the chart.
3. `Navigator → Scripts → QSMC_FixedRangeDump` → drag onto the chart.
4. In the inputs dialog set:
   - `InpSymbol` = the symbol (or blank for the chart symbol),
   - `InpIndicatorName` = `nadir2` (as installed),
   - `InpStart` / `InpEnd` = **exact M15 bar-open timestamps** in broker/server
     time (e.g. dates as shown on the chart axis), inclusive, both closed bars,
   - `InpOutFile` = e.g. `QSMC_fixed_range_XAUUSD_M15.csv`,
   - `InpReadyWaitSeconds` = 30 (raise only if history is huge),
   - `InpConfirmedIsolatedPortableTerminal` = **true** (checkbox/typing `true`).
     With `false` the script refuses to run — by design.
5. OK. Watch **Experts** / **Journal** tabs. The script finishes in seconds.

### 3.4 Output location

Portable mode:
`C:\MT5_PORTABLE_DIAG\portable\MQL5\Files\QSMC_fixed_range_XAUUSD_M15.csv`
(Live terminal: `%APPDATA%\MetaQuotes\Terminal\<instance-id>\MQL5\Files\…`.)
The CSV is UTF-8/ANSI text with CRLF line endings.

### 3.5 CSV checks to perform (in this order)

1. **Header** must be exactly:
   `bar_time_server,shift_at_read,symbol,timeframe_minutes,bar_status,bars_calculated,buffer_0,…,buffer_20,buffer_21_SCORE,buffer_22_CLASS,buffer_23,…,buffer_25`
2. **Time column** strictly increasing; every value an exact 15-minute grid
   point; all within `[InpStart, InpEnd]`; none equal to the forming bar at
   run time. Grid: `:00,:15,:30,:45`.
3. **Row count** = expected number of closed M15 bars between start and end
   inclusive (count minutes/15). If `InpEnd` was the forming bar, the log and
   row count must reflect the clamp to shift 1.
4. **`bar_status`**: all `OK` is the success condition. `COPY_SHORT`,
   `MISSING_BAR`, `OUT_OF_REQUESTED_RANGE`, `BAR_CHANGED` (possibly with `|`)
   each invalidate that row; the tool also prints counts. A run with any
   non-OK status is NOT usable as a baseline artifact — re-download history
   and re-run; do not "fix" by editing the CSV.
5. **`bars_calculated`** in every row must be ≥ (rows_back_from_current) for
   the oldest row, i.e. the indicator had computed at least that far back;
   and ≥ `start_shift+1` for the range to be covered. If readiness was "NO",
   the oldest cells are untrusted regardless of what they show.
6. **21/22 labels**: `buffer_21_SCORE`, `buffer_22_CLASS` present. Score is a
   0–100-style "evidence quality" (not a forecast/win-rate); CLASS is the
   integer class (e.g. 1=WEAK_VALID, 2=MODERATE_VALID, 3=STRONG_VALID per the
   enum in `nadir2.mq5` ~1887–1896).
7. **EMPTY_VALUE** appears only as the literal token `EMPTY_VALUE`; **READ_FAIL**
   appears only when that cell's CopyBuffer failed; the two must not be
   conflated when counting signal samples.
8. **No account data**: grep the Experts log for `login`, `account`,
   `broker`, `server` — none should come from this tool. (`terminal build=`
   is expected and allowed.)
9. Cross-check two or three timestamps against the chart's OHLC for those
   bars (open/high/low/close) — they must match exactly, proving the row↔bar
   association.

Keep the CSV, the compile logs, and the run logs together; they are the
(still **NOT VERIFIED**) evidence bundle for the baseline gate review.

## 4. Interpretation rules (hard)

- A freshly attached handle re-runs OnCalculate from scratch, but there is **no
  evidence in the source that historical CORE publications are backfilled into
  buffers 7–25 or the journal** (see §5). Therefore an all-zero dump for
  history is **not** proof of "no historical signal", and **not** proof of
  equivalence either. It is a *non-event*.
- To get real historical samples you need either a **forward replay** in the
  Strategy Tester (the EA/indicator run through the period, observing the
  buffers live per closed bar) — plan 1/plan 2 docs — or a separate,
  explicitly-scoped backfill feature, which is **out of scope** here.
- `BAR_CHANGED` or `COPY_SHORT` rows: discard the whole run for gating
  purposes; diagnose data sync first.
- The tool does not prove anything about fills, slippage, execution, or risk.

## 5. Does nadir2 backfill historical CORE exports on a fresh attach?

**NOT VERIFIED — and the source strongly indicates it does NOT.**

Evidence:

- `OnInit` (`nadir2.mq5` 15318) does `ArrayResize(g_confirmed_signal_journal,0,32)`
  — the confirmed-signal journal starts EMPTY on every attach.
- Buffer cells 7–25 are written by the confirmation/publication path at the
  time a setup confirms on a closed bar (e.g. via `SigLog_BufWrite*`; same
  "once per closed bar" discipline as `DiagPublishCoreState`). A new historical
  pass does not re-publish historical confirmations into those buffers.
- `DiagPublishCoreState` (20324–20354) publishes only the *current* closed bar;
  it reads `g_confirmed_signal_journal` for the fact that "became available
  exactly when this bar closed" — it cannot retroactively populate the past.
- By contrast, `QSMC_SmcVpEngine.mq5` DOES implement an explicit
  `InpSveBackfillBars = 96` replay at start (`QSMC_SmcVpEngine.mq5` 116, 255–256,
  ~395–403) — that is the separate QSVP display engine, NOT CORE in nadir2.
- `nadir2.mq5` does contain a full causal rebuild on attach
  (`prev_calculated==0` → `full_detection=true` → detection over the whole
  `rates_total`), which rebuilds *detection artefacts* (events/graphs/state).
  That is not the same as writing historical CORE signal buffers/journal.

Consequences:

- Historical CORE equivalence via this CSV dump: **NOT VERIFIED**.
- Do not present an all-zero (or all-EMPTY_VALUE) historical CSV as evidence of
  equivalence, parity, absence of regressions, or safety.
- Proposed method instead: Strategy Tester forward replay — see
  `docs/QSMC_TESTER_PLAN_1_OBSERVATION.md` (diagnostics) and
  `docs/QSMC_TESTER_PLAN_2_EXECUTION.md` (execution characterization). In a
  replay, every closed bar is processed in order and the buffers are observed
  as they are produced — the only way to see a genuine historical sample of
  CORE publications.
- Representative period requirement: find a period with actual CORE
  publications (journal prints of published CORE events / non-zero buffer
  7/19/21/22 during replay). If none exists in available broker history,
  report that limitation and do NOT lower gates to force trades.

## 6. Gate status

Creating this script, compiling it, and producing a CSV **does not** satisfy
the baseline gate. The gate needs user-returned logs, a clean CSV
(`bar_status=OK` throughout), and review. Until then: **NOT VERIFIED**, no
production file is moved, no strategy behavior is changed.
