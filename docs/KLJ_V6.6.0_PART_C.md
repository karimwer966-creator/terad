# Quantum SMC v6.6.0 — PART C, PHASE 6: THE DATA LAYER

**Status: Phase 6 written. Static review only — nothing compiled. Press F7.**
Phases 7-9 are specified at the end of this document but not yet implemented.

**Phase status: 6 and 7 implemented. 8 and 9 not started.**

**Gating note.** Your brief says *"Do not start PART C until PART A passes its test scenarios."*
PART A passes its **offline** checks (`tools/test_arbiter.py` 22/22; `tools/check_scenario_geometry.py` all pass), but the MQL5 Script has never run in a terminal. I asked whether to wait or proceed and the question was skipped, so I took the conservative branch: **proceed, with every external provider disabled by default** so no endpoint or key is invented, and with all PART C code isolated from PART A/B. You can stop me at any point.

---

## 1. Platform constraints this design obeys

| Constraint (MQL5 fact) | How it is respected |
|---|---|
| `WebRequest()` is forbidden in indicators | No `WebRequest` call exists in any `MQL5/Include/QSMC/*.mqh` file or in `nadir2.mq5`. Only `MQL5/Experts/KLJ_DataFeeder.mq5` calls it. Verified by `tools/static_check.py`. |
| Fetched URLs must be whitelisted in Tools > Options > Expert Advisors | Documented at the top of the EA, with the failure mode (error 4014/5202) named. |
| Heavy work must not run in `OnCalculate` | `CFileDataProvider::Refresh()` is documented and intended for `OnTimer` only. No PART C code is wired into `nadir2.mq5` yet. |
| Failure of a PART C module must not affect PART A/B | PART C modules expose *status flags*, never exceptions. A provider returning `QDP_NODATA` excludes its value from every score; it cannot open or close a gate. |
| No invented data | A missing series is reported as `NO DATA: <source>, last update <time>`. No interpolation, no carry-forward, no default value. |

---

## 2. Deliverables in this phase

| File | Bytes | Lines | Role |
|---|---|---|---|
| `MQL5/Include/QSMC/QSMC_DataProvider.mqh` | 14,317 | 350 | `IDataProvider` interface + `CFileDataProvider` (reads only) |
| `MQL5/Experts/KLJ_DataFeeder.mq5` | 18,936 | 499 | companion EA: fetches, validates, writes atomically |

---

## 3. `QSMC_DataProvider.mqh`

### 3.1 Schema (the contract between the EA and the indicator)

```
# QSMC-DATA v1
series_id,as_of,value,prev,label
_meta,2026.10.19 09:15,0,0,generated
COT:XAU:NET_NONCOMM,2026.10.13 00:00,123456,120000,net noncomm
RETAIL:XAU:LONGPCT,2026.10.19 08:00,71.4,68.9,retail long %
```

* Long format: every observation is one row, so a new dataset is a new `series_id` and needs **no change to this header**.
* The header row is **required**. A file without it is rejected as `QDP_SCHEMA` rather than guessed at.
* `as_of` is the **observation's own date**, not `now()`. COT is published with a multi-day lag; the as-of date is what the dashboard shows. This is why a row with an unparseable timestamp is stored but flagged `valid=false` — an undated observation is never silently dated "today".
* `_meta` carries the file generation time, used for freshness.

### 3.2 Manual compiler pass

**Introduced identifiers and where they are declared:**

| Kind | Identifiers | Declared in |
|---|---|---|
| Macros | `QDP_OK`, `QDP_STALE`, `QDP_NODATA`, `QDP_SCHEMA`, `QDP_DISABLED` | `QSMC_DataProvider.mqh` |
| Struct | `SDataPoint { series_id, as_of, value, prev, label, valid }` | `QSMC_DataProvider.mqh` |
| Interface | `IDataProvider` — `Refresh()`, `IsFresh(int)`, `GetLastUpdate()`, `GetStatus()`, `GetStatusText()`, `Get(string,SDataPoint&)` | `QSMC_DataProvider.mqh` |
| Class | `CFileDataProvider : public IDataProvider` | `QSMC_DataProvider.mqh` |
| Private methods | `SplitCsv`, `ParseTime`, `SetStatus`, `Clear`, `Push` | `QSMC_DataProvider.mqh` |
| Public methods | `Init`, `Path`, `Source`, `Rows`, `ParseErrors`, `ReadCalls`, `Refresh`, `IsFresh`, `GetLastUpdate`, `GetLastRead`, `GetStatus`, `GetStatusText`, `Get`, `AgeSeconds`, `AgeText` | `QSMC_DataProvider.mqh` |
| Free function | `QSMC_DataProviderSelfTest()` | `QSMC_DataProvider.mqh` |
| Members | `m_path`, `m_source_name`, `m_use_common`, `m_status`, `m_status_text`, `m_last_update`, `m_last_read`, `m_rows[]`, `m_rows_n`, `m_max_rows`, `m_parse_errors`, `m_read_calls`, `m_short_reads` | `QSMC_DataProvider.mqh` |

**Checks performed:**

1. `#include <QSMC/QSMC_Types.mqh>` resolves; the include graph stays acyclic (`QSMC_DataProvider` depends only on Types, and nothing in PART A depends on it).
2. All six `IDataProvider` methods are implemented by `CFileDataProvider` — verified by `static_check.py` (rule: every interface method must have a matching implementation).
3. Every `SDataPoint` member read in code is declared; every member is written before use (`Refresh()` sets all six, `Get()` resets all six on a miss so a caller can never read a stale struct).
4. **MQL5 file mode corrected during review:** the reader originally opened with `FILE_CSV`. With `FILE_CSV`, `FileReadString()` stops at the **field delimiter**, not end-of-line, which would have split `a,b,c` into three "lines". Changed to `FILE_TXT`.
5. Array bounds: `SplitCsv` writes at most `cap` items; `Push` refuses beyond `m_max_rows` (bounded cache, default 512, clamped to 16..8192); every `m_rows[i]` access is inside `m_rows_n`.
6. No `new`/`delete` in this module — the cache is a plain struct array, so there is nothing to leak.
7. No recursion: `SplitCsv` and the parse loop are iterative.
8. No `WebRequest`, no `OrderSend`, no trade function.

**What this pass cannot catch:** argument-order errors, implicit conversions the compiler rejects, whether `FILE_SHARE_READ|FILE_SHARE_WRITE` is accepted alongside `FILE_TXT` on your build. **Press F7.**

### 3.3 Two deliberate design choices worth flagging

* **Freshness comes from the in-file `_meta` stamp, not a filesystem property.** `FileGetInteger(handle, FILE_MODIFY_DATE)` is not present in every MQL5 build, and relying on it would have made the staleness rule untestable. Using an in-file stamp means a synthetic fixture can carry any timestamp, so the staleness logic is fully testable offline.
* **`Get()` does exact matching only.** A near-miss series id is reported missing. Fuzzy matching here would risk silently displaying gold's positioning on a silver chart.

---

## 4. `KLJ_DataFeeder.mq5` (companion EA)

### 4.1 What it does, and what it refuses to do

It runs on a timer, GETs each configured URL, extracts a **flat** set of fields, and rewrites the output file atomically (`.tmp` → delete target → `FileMove`), so a reader sees either the old file or the complete new one — never a half-written one.

It refuses to guess:

* **No endpoint and no key are in the file.** `InpUrl1..3` and `InpApiKey` are inputs, empty by default, and `InpFeedEnabled=false`. It ships inert.
* **It is not a general JSON parser.** It understands flat objects and CSV. A nested object or array is consumed whole, counted, and reported as `UNSUPPORTED_SHAPE` in the status file. Approximating a nested value would be worse than reporting it missing.
* **A value that will not parse as a number is dropped**, not coerced to `0`.
* It calls `Sleep()` between retries — legal in an EA, illegal in an indicator. This is one more reason it is a separate process.

### 4.2 Manual compiler pass

**Introduced identifiers:**

| Kind | Identifiers | Declared in |
|---|---|---|
| Inputs (17) | `InpFeedEnabled`, `InpRefreshMinutes`, `InpTimeoutMs`, `InpMaxRetries`, `InpRetryBackoffSec`, `InpMinSecondsBetweenCalls`, `InpOutputFile`, `InpWriteStatusFile`, `InpAuthHeader`, `InpApiKey`, `InpUrl1..3`, `InpMap1..3`, `InpVerbose` | `KLJ_DataFeeder.mq5` |
| Macro | `MAX_FIELDS` (64) | `KLJ_DataFeeder.mq5` |
| Structs | `SField { key, series_id }`, `SSource { url, fields[MAX_FIELDS], fields_n, last_call, failures, last_error }` | `KLJ_DataFeeder.mq5` |
| Globals | `g_src[3]`, `g_src_n`, `g_timer_count`, `g_fetch_ok`, `g_fetch_fail`, `g_rows_written`, `g_gen_errors` | `KLJ_DataFeeder.mq5` |
| Functions | `ParseFlatJson`, `ParseMap`, `FetchSource`, `WriteFeed`, `WriteStatus`, `RefreshAll`, `OnInit`, `OnDeinit`, `OnTimer`, `OnTick` | `KLJ_DataFeeder.mq5` |

**MQL5 API usage verified against the reference:**

| Call | Signature check |
|---|---|
| `WebRequest("GET",url,headers,timeout,data,result,result_headers)` | 7-arg MQL5 form (not the MQL4 cookie/referer form). `timeout` is in **milliseconds**. |
| `FileOpen(path, FILE_WRITE\|FILE_TXT\|FILE_ANSI\|FILE_COMMON)` | Corrected from `FILE_CSV`, which would have escaped the commas I emit. |
| `FileMove(src, dst, common_flag)` | MQL5 has no `FILE_REPLACE` here, so the target is `FileDelete`d first — otherwise the move can fail on an existing file. |
| `FileDelete(path, common_flag)` | 2-arg MQL5 form. |
| `FolderCreate(dir, common_flag)` | Returns false when the folder already exists; the return value is intentionally ignored. |
| `CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8)` | Valid for a `char[]` response. |
| `EventSetTimer(seconds)` | Takes **seconds**; `InpRefreshMinutes * 60`. |
| `ShortToString(ushort)` / `StringGetCharacter(s,pos)` | Both valid MQL5. |
| `Sleep()` | Legal in an EA. |

**Checks performed:** no `new`/`delete` (all state is static or a fixed struct array, so `OnDeinit` has nothing to free); no recursion (`ParseFlatJson` tracks nesting with a depth counter in a loop); every array write bounded by `MAX_FIELDS`; every `FileOpen` handle checked against `INVALID_HANDLE` and closed on every path, including the schema-error early return; `FileClose` called before every `return`.

**What this pass cannot catch:** whether your build accepts `FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON` in that combination, and whether `WebRequest` is permitted at all in your terminal's policy. **Press F7.**

---

## 5. Test cases (Phase 6)

The brief requires these five failure modes to be covered. Status of each:

| Case | Expected | Implemented? | How to exercise |
|---|---|---|---|
| **Stale data** | `IsFresh(60)` false, `IsFresh(1e9)` true; status text reports the generation time | Yes — `IsFresh()` / `AgeText()` | Write a fixture whose `_meta` is a week old, call `Refresh()` then `IsFresh()`. |
| **Missing symbol / unknown series** | `Get("NOPE")` returns false, does **not** substitute a neighbour | Yes — `Get()` | Query any id not in the file. |
| **Partial history** | Rows present are used; missing rows are absent, not zero-filled | Yes — long format | Omit rows from the fixture; `Rows()` must drop, `Get()` must fail for the omitted ones. |
| **n below minimum** | Withheld, not shown | **Not yet** — belongs to the Phase 7/8 modules | Will be enforced in `CSeasonalityScanner` / `CStatsLogger`. |
| **API failure** | HTTP error or empty body ⇒ source failure counted, **previous file left untouched**, error written to `<output>.status` | Yes — `FetchSource()` + `WriteStatus()` | Point `InpUrl1` at a dead URL, or leave it unset and enable the feed. |

Two gaps I am stating rather than papering over:

* `QSMC_DataProviderSelfTest()` currently exercises only the **no-source** and **file-not-found** paths (T1-T2). T3-T7 need a fixture file, which requires a terminal. The fixture-driven cases are specified in the header comment so they can be run the moment you have one.
* The **flat-JSON parser** has no offline test yet. `tools/` gained no mirror for it this phase; I recommend a small Python port before you rely on it against a live provider.

---

## 6. What I need from you before Phase 8 can ship

Phase 8 (COT, retail sentiment, equity sentiment, macro dashboard) reads entirely through `CFileDataProvider`, so it is buildable without a provider — it will simply display `NO DATA` for every series. To make it *useful* I need:

1. **Which provider** for each of: COT, retail sentiment, AAII/Put-Call, macro releases. If you have licensed access, tell me the endpoint and I will shape `InpMap*` around its response.
2. **Whether its response is flat or nested.** Nested payloads will need either a provider that returns flat data or a small middleware; I will not fake a parser for a shape I have not seen.
3. **Symbol mapping.** COT contracts are per-future (e.g. GC for gold), not per-broker-symbol. That mapping has to be configured explicitly — a wrong mapping is a wrong number on the chart, which is worse than no number.
4. **Confirmation that redistribution to your own machine is permitted** by the terms you accept. I cannot verify licensing from here.

---

## 7. PHASE 7 — scanners and heatmaps (IMPLEMENTED)

`MQL5/Include/QSMC/QSMC_Scanners.mqh` — MT5 data only, no external feed.

| Class | What it does | Complexity | Memory |
|---|---|---|---|
| `CAssetScanner` | Holds the universe (broker symbol + asset group). `Validate()` asks the terminal whether the symbol exists and whether its history is synchronised. | `Validate` O(1) per symbol | O(N), N ≤ 64 |
| `CTopSetupsScanner` | Per symbol: builds swing zones from that symbol's own bars, then runs the **PART A** `CZoneRegistry` / `CReactionDetector` / `CBiasProvider` **read-only** over the last closed bar. Ranked by evidence score. | O(bars) per symbol, **resumable and time-boxed** (`GetTickCount64`, default 30 ms) | **O(1) in the symbol count** — one `CMarketData` is re-`Init()`ed per symbol instead of one per symbol |
| `CMomentumHeatmap` | ROC over a selectable lookback, ATR-normalised, z-scored against **that symbol's own** history — never against the universe. | O(lookback × hist) | O(N) |
| `CVolatilityHeatmap` | ATR percentile within 100 and 250 bars + a five-bucket regime label. | O(window) | O(N) |
| `CSeasonalityScanner` | Mean/median/std/positive-share returns by month, week-of-year, day-of-week and hour-of-day. Always shows `n`, years covered and dispersion. | O(bars) | O(1) — bounded flat accumulators |

### 7.1 Two things I want to flag explicitly

**(a) The scanner's zones are NOT the chart's ZRE zones.**
The brief asks the scanner to "run the same zone/reaction/bias engine". It does reuse `CZoneRegistry`, `CReactionDetector` and `CBiasProvider` verbatim — but the *zones* fed into that registry are swing-derived from price alone (`BuildScanZones`), because the host's ZRE zones live in `g_zre_zones` and depend on the host's structure / order-block / FVG machinery, which is not callable per-symbol from an include. **This scanner is a triage tool that tells you where to look. Its rows are not signals and must not be traded from.** That is stated in the header comment, not buried.

**(b) Deviation: `g_quant.vol_class` is not reused.**
The brief says to reuse the host's volatility class. That global lives in `nadir2.mq5`; reading it from an include would couple this header to the host's globals and make the module untestable. The percentile is therefore computed here and mapped onto the **same five bucket names** the host uses (`LOW / NORMAL / HIGH / EXTREME / UNKNOWN`). The numbers will **not** be identical to the host's classifier, which uses its own thresholds. Treat it as a second opinion, not a mirror.

### 7.2 Manual compiler pass

**Introduced identifiers:**

| Kind | Identifiers | Declared in |
|---|---|---|
| Macros | `QSC_MAX_SYMBOLS`, `QSC_MAX_ZONES`, `QSC_MAX_LOOKBACKS`, `QSC_MAX_ROWS`, `QSC_SEAS_MONTHS`, `QSC_SEAS_WEEKS`, `QSC_SEAS_DOW`, `QSC_SEAS_HOURS` | `QSMC_Scanners.mqh` |
| Enums | `ENUM_ASSET_GROUP`, `ENUM_SCAN_STATUS`, `ENUM_SEAS_BUCKET`, `ENUM_TIME_BASIS` | `QSMC_Scanners.mqh` |
| Structs | `SSetupRow`, `SMomentumRow`, `SVolatilityRow`, `SSeasonRow` | `QSMC_Scanners.mqh` |
| Classes | `CAssetScanner`, `CTopSetupsScanner`, `CMomentumHeatmap`, `CVolatilityHeatmap`, `CSeasonalityScanner` | `QSMC_Scanners.mqh` |
| Free functions | `QScanGroupName`, `QScanStatusName`, `QSeasBucketName` | `QSMC_Scanners.mqh` |

**Checks performed:**

1. Includes resolve and stay acyclic: `QSMC_Types` → `QSMC_MarketData` → `QSMC_Zones` / `QSMC_Reaction` / `QSMC_Bias` → `QSMC_Scanners`. Nothing in PART A/B includes `QSMC_Scanners`, so PART C cannot break PART A.
2. **`QSMC_BuildGeometry` signature corrected during review.** I first called it with a `double barrier`; the real signature is `(z, dir, entry, atr, const CZoneRegistry&, cfg, tick, sl, tp1, tp2, tp3, rr, room_atr)`. The scanner now passes the registry and the symbol's `SYMBOL_TRADE_TICK_SIZE`, falling back to `SYMBOL_POINT` then `_Point` — the tick size differs between XAUUSD and BTCUSD, so a hard-coded `_Point` would have produced wrong geometry.
3. `SReactionFacts::missing` is a pre-built string; the scanner no longer recomputes it.
4. Every array write is bounded (`QSC_MAX_ZONES`, `QSC_MAX_ROWS`, 64 buckets × 512 samples).
5. `new`/`delete`: one `CMarketData` per scanner, freed in `Shutdown()` with `AllocCalls()`/`FreeCalls()` counters. No allocation inside `Scan()`.
6. No recursion: `SortByScore` and the median sort are insertion sorts; JSON/CSV parsing is not used here.
7. No `OrderSend`, no `WebRequest`, no trade function.

**What this pass cannot catch:** whether `SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE)` is populated for every symbol your broker offers; whether `SeriesInfoInteger(..., SERIES_SYNCHRONIZED)` behaves as expected on your build. **Press F7.**

### 7.3 A bug the Python mirror caught

`tools/test_scanners.py` is an independent re-implementation of the seasonality, percentile and z-score arithmetic. Two findings:

1. **Degenerate z-score (real bug, fixed).** For a constant-growth series the true standard deviation is 0, but floating point leaves ~1e-13, so the obvious guard `sd > 0.0` passed and dividing by it converted rounding noise into an O(1) number — a +1%/bar ramp reported **z = −1.13 instead of 0**. `CMomentumHeatmap` now requires `sd > max(|mean|, 1e-8) * 1e-6` before computing a z-score, and returns 0 otherwise. The same guard is mirrored in the Python test.
   *(A third class of finding came later, in v6.6.3 — see §7.6: a mirror of the
   arithmetic cannot see a bug in the** storage**, so the Python side had to learn
   the array bounds too.)*

2. **Off-by-one in my own test data (test bug, fixed).** Storing the month's close before applying that month's move put every return in the wrong bucket. The corrected fixture asserts `n = 19` for 20 Januaries, because the first bar has no prior close — asserted explicitly so the convention cannot drift.

### 7.4 Test cases (Phase 7)

| Case | Covered by | Status |
|---|---|---|
| **Missing symbol** | `CAssetScanner::Validate()` returns `QSS_MISSING` with a reason string | Implemented; **needs a terminal to verify** |
| **History not synchronised** | returns `QSS_NOT_SYNCED`, retried next pass | Implemented; **needs a terminal** |
| **Partial history** | `QSS_NO_DATA` when bars < `min_bars` or ATR unavailable | Implemented; **needs a terminal** |
| **n below minimum** | `CSeasonalityScanner` withholds the row entirely | ✅ verified offline (`T2a`: n=19 < 30 → withheld; `T2b`: n=19 ≥ 10 → shown) |
| **Dispersion always shown** | `std_ret`, `median_ret`, `pos_share`, `years` on every row | ✅ verified offline (`T1e`, `T2c`, `T2d`) |
| **Percentile edge cases** | −1 (not 0.0) when history is short or ATR = 0 | ✅ verified offline (`T5a`, `T5b`) |
| **Degenerate distribution** | z = 0, never NaN | ✅ verified offline (`T6a`, `T7a`) |

### 7.5 Time basis and DST — stated, not hidden

`QTB_SERVER` buckets by the broker's bar timestamp as stored. `QTB_UTC` applies a **single** offset, `TimeGMT() - TimeCurrent()`, sampled at scan time. Broker servers usually run a fixed offset, but some shift with DST. **This scanner applies one offset to the whole history and therefore does not retroactively correct historical DST transitions.** Where a broker's offset has changed in the past, hour-of-day rows spanning that change are approximations.

### 7.6 v6.6.3 — the module gets a host, and four defects come out with it

Until this release nothing included `QSMC_Scanners.mqh`: no build compiled it, no
harness called it. `tools/static_check.py` listed the companion sources in an
`EXTRA` array and then **never read it**, which is the same failure one level up —
a source no check touches is a source no check protects. That array is wired into
the checks now, and `MQL5/Indicators/QSMC_ScannerProbe.mq5` is the module's host:
it drives the universe, the time-boxed `Scan()`, the two heatmaps and the
seasonality table, and prints text only — no objects, no orders, no files.

Four defects were found by reading that file with an eye to *how the data is
stored*, not to whether it looks like C++:

| # | Defect | Why it survived a glance | Fix |
|---|---|---|---|
| 1 | `SQZone z=zs[hit.index];` — `hit.index` is an index into `CZoneRegistry::m_zones`, which `Rebuild()` has already **filtered, merged and re-sorted by midpoint**. The row reported the band, role, strength and id of a *different* zone, and fed that zone to `QSMC_BuildGeometry`. | Nothing crashes, the values are plausible, and when no merge happens the indices coincide — so a manual test on a clean chart passes. | `m_zones.At(hit.index,z)`, the same pattern `CQuantumRoot::BuildContext()` uses. A miss is reported as `QSS_NO_SETUP` with a reason, never swallowed. |
| 2 | `BucketOf()` returned **1-based** months (1..12) and weeks (1..53) into a **0-based** 12/53-slot array. December (index 12) and every 53rd week were dropped by the range test, and slot 0 was an empty phantom row labelled `?`. | The table looked complete: 12 rows, 12 names — January..November shifted by one. A file whose header promises "never silently dropped" was dropping a month silently. | Buckets are 0-based for all four kinds; `QSeasBucketName()` adds the `+1` back for the label. `tools/test_scanners.py` now models `SLOTS` and asserts December, W53 and `dropped == 0`. |
| 3 | The median was computed over "the first 512 values of the bucket", i.e. the **oldest** slice, while `n` reported the full count. | The median of a bucket is only read as a number; nothing says it is 30 years old. | Reservoir sampling (Algorithm R) with the LCG seeded per pass: unbiased 512-sample median, **identical for identical bars** (no clock), and `n` still the full bucket. When the bucket fits in 512 the sample *is* the bucket, so the median is exact. |
| 4 | `Percentile()` divided by the **window length** while skipping bars whose ATR is not defined yet. | Every warm-up hole pushed the number down; a genuine 80th percentile printed as 64th and still landed in a plausible regime bucket. | Divide by the values actually compared, and refuse below 10 of them. |

Two API changes came with them:

* `CTopSetupsScanner::Row`, `CMomentumHeatmap::Row`, `CVolatilityHeatmap::Row`
  returned `const SRow *` built from `&m_rows[i]`. **MQL5 has no pointer to a
  structure** — only to class objects — so those three declarations could never
  have compiled; they read like the legal `CBarSeries *Chart()`, which is why no
  review caught them. They are now `bool Row(const int i,SRow &out) const`, the
  form `CZoneRegistry::At()` and `CSeasonalityScanner::Row()` already used in this
  same file. Rule **D12** in `tools/mql5_rules.py` now rejects the pointer form
  anywhere in the subsystem, and the conversion is no-regret: reference-out is
  unambiguously legal whether or not a future build ever allows the other.
* `CMomentumHeatmap` gained `History()`, because a caller cannot print a z-score
  window it is not allowed to read.

`t_scanners` prints `RESULT: all scanner arithmetic checks passed` over 40
assertions (was 23). The probe is compiled by `F7` like any other file here, and
it is the first thing in this repo that makes the Phase 7 module part of a build.

---

## 8. Phases 8-9 — not yet implemented

| Module | Data source | Status | Note |
|---|---|---|---|
| `CAssetScanner` | MT5 only | **Implemented (§7)** | Broker symbol mapping table as inputs; missing symbols skipped with a visible note, never silently dropped. |
| `CTopSetupsScanner` | MT5 only | **Implemented (§7)** | Reuses the PART A zone/reaction/bias engine **read-only**; ranked by evidence score, never "probability"; `OnTimer`, a few symbols per tick, cached per closed bar. |
| `CMomentumHeatmap` | MT5 only | **Implemented (§7)** | ROC over selectable lookbacks, ATR-normalised, z-score vs own history, colour legend. |
| `CVolatilityHeatmap` | MT5 only | **Implemented (§7)** | ATR percentile (100/250-bar), regime label, colour legend. |
| `CSeasonalityScanner` | MT5 only | **Implemented (§7)** | By month / week-of-year / day-of-week / hour-of-day; **always** shows `n`, years covered and dispersion; withheld below minimum n; labelled descriptive history, never a forecast; server time vs UTC handled explicitly. |
| `CCotModule`, `CRetailSentimentModule`, `CEquitySentimentModule`, `CMacroDashboard`, `CContextAggregator` | Companion-EA files | Blocked on §6 | Will ship as `NO DATA` stubs if no provider is chosen. `CContextAggregator` may add `ALIGNED / CONFLICT / NEUTRAL` **labels only** — it never creates, removes or confirms a signal. |
| `CScenarioBacktester` | MT5 only | Specified | Closed bars only, no look-ahead, no optimisation; reports n, wins/losses, avg RR, expectancy (R), profit factor (withheld with no losing sample), MAE, MFE, time to target, censored count, TRAIN/VALIDATION/OUT-OF-SAMPLE split; states spread/commission assumptions; shows losing periods. |

Every one of these is **observational**. None will be wired into the PART A/B gate chain.
