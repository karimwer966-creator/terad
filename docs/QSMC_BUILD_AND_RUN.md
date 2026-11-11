# QSMC v6.6.22 — BUILD, RUN, VERIFY

Operational guide for `nadir2.mq5` + the `MQL5/Include/QSMC` arbitration layer.
Design and root-cause analysis live in `docs/KLJ_V6.6.0_SIGNAL_ARBITRATION.md`;
the v6.6.1 compile fixes are in `docs/QSMC_REVIEW_v6.6.1.md` (its §6.5 covers
v6.6.2: literal hygiene + the CI gate).

---

## 0. العربية — البدء السريع

**ما هو هذا المستودع:** مؤشر `nadir2.mq5` (MetaTrader 5) وطبقة قرار اسمها QSMC
موجودة في `MQL5/Include/QSMC/*.mqh`. الطبقة تجمّع كل مسارات الإشارات في قائمة
واحدة، تمرّرها على 10 بوابات (gates)، وتنشر إشارة واحدة لكل شمعة مغلقة فقط.

**خطوات التشغيل:**

1. افتح MT5 ← `File` ← `Open Data Folder` (ملف البيانات).
2. انسخ الملفات إلى هذه الأماكن داخل ملف البيانات:
   - `MQL5/Include/QSMC/*.mqh` → `<Data Folder>/MQL5/Include/QSMC/`
   - `nadir2.mq5` → `<Data Folder>/MQL5/Indicators/`
   - `MQL5/Scripts/QSMC_ArbiterTest.mq5` → `<Data Folder>/MQL5/Scripts/`
   - `MQL5/Experts/KLJ_DataFeeder.mq5` → `<Data Folder>/MQL5/Experts/`
   - `MQL5/Experts/QSMC_AutoTrader.mq5` → `<Data Folder>/MQL5/Experts/`
     (اختياري: **التنفيذ الآلي** — منفصل عن المؤشر، يصل معطّلاً، راجع
     `docs/QSMC_AUTOTRADER.md`. المؤشر نفسه لا يفتح صفقات أبداً.)
   - `MQL5/Indicators/QSMC_ScannerProbe.mq5` → `<Data Folder>/MQL5/Indicators/`
     (اختياري: مضيف طبقة الماسحات Phase 7 — لا يرسم ولا يتداول، فقط نصّ)
   - `MQL5/Indicators/QSMC_SmcVpEngine.mq5` → `<Data Folder>/MQL5/Indicators/`
     (اختياري، جديد في v6.6.22: محرّك قرار SMC + Volume Profile بلوحة من 16 سطراً
     ومخطط نظيف — عرض فقط، لا يفتح صفقات. الدليل: `docs/QSMC_SMCVP_ENGINE_AR.md`)
   (المجلد `QSMC` داخل `Include` **ضروري**: الملفات تُضمَّن هكذا
   `#include <QSMC/QSMC_Root.mqh>`.)
3. افتح `MetaEditor` (F4 داخل MT5) واضغط **F7** على كل ملف بالترتيب:
   `nadir2.mq5` ثم `QSMC_ArbiterTest.mq5` ثم `KLJ_DataFeeder.mq5`
   ثم `QSMC_ScannerProbe.mq5` إن أردت الماسحات،
   ثم `QSMC_SmcVpEngine.mq5` إن أردت محرّك SMC + Volume Profile،
   ثم `QSMC_AutoTrader.mq5` إن أردت التنفيذ الآلي.
   النتيجة المطلوبة: `0 errors, 0 warnings`.
   ترجمة `QSMC_ScannerProbe.mq5` هي الوحيدة التي تُثبت أن
   `QSMC_Scanners.mqh` يُترجم فعلًا — قبل v6.6.3 لم يكن لهذا الملف أي مضيف.
4. في MT5: `Navigator` ← `Indicators` ← `nadir2` اسحبه على مخطط M5/M15.
5. راجع تبويب `Experts`/`Journal`: السطر الأول يجب أن يكون
   `[QSMC_ARB] v6.6.22 arbitration layer ON | preset …`.
6. للاختبار الذاتي: اسحب `QSMC_ArbiterTest` (Scripts) على أي مخطط —
   النتيجة المطلوبة `RESULT: 45 passed, 0 failed` (includes quant, structure, and zone-scoring assertions).
7. للتحقق بدون MT5 (من الطرفية، داخل المستودع):
   `python3 tools/check_production_ready.py` ثم `python3 tools/check_release_gate.py`.
   النتيجة المتوقعة: `OFFLINE GO` و `GO (with 0 warning(s))`. هذا لا يغني عن F7.
8. **قبل تشغيله على مخطط حقيقي**: `python3 tools/check_production_ready.py` و `python3 tools/check_release_gate.py` —
   يجب أن تُخبِر السطر الأخير `GO` (تتحقق من توحّد الإصدار، اكتمال الملفات،
   توثيق كل مدخلات، أن الطبقة لا تتداول ولا تفتح شبكة، وأنها لا تسجّل كل شمعة).
   التشغيل والأرقام المطلوب مراقبتها في الساعة و24 ساعة الأولى:
   `docs/QSMC_PRODUCTION_CHECKLIST.md` (المربعات في §10 هي قائمة التوقيع).

**الماسح (اختياري):** بعد رفع `QSMC_ScannerProbe` على أي مخطط يجب أن تبدأ
الـ Journal بـ `[QSMC_SCAN] probe ON | … | observational only, no gate is decided
here`، ويظهر جدول `top setups by EVIDENCE SCORE` مع قائمة «not shown, and why»
أسفله. الترتيب هنا للاطلاع فقط ولا يُتّخذ عليه قرار دخول.

**زر الإيقاف:** `InpArbEnabled = false` → الطبقة تصبح معطّلة تمامًا ويتصرف
المؤشر مثل v6.5.5 (بدون إعادة تجميع، بدون تغيير في لوحة العرض).

### v6.6.22 — chart hygiene, and a separate SMC + Volume Profile engine

Two changes, both display-side. Neither moves an exported buffer of `nadir2.mq5`
and neither can place an order. Full report: `docs/QSMC_SMCVP_ENGINE_AUDIT_2026-11-11.md`;
operator guide in Arabic: `docs/QSMC_SMCVP_ENGINE_AR.md`.

* **`nadir2.mq5`: one mark per setup.** `AlertDispatcherDrawPrimary()` named its
  arrow and label after the bar a scenario was *published* on, once per closed
  bar, so a scenario that stayed primary for N bars left N arrows and N copies of
  the same label (bounded only by a 16-slot ring = 32 objects). The mark is now
  named after the setup's originating bar (`QSMC_SignalRegistry.mqh`): a
  re-publication updates the same two objects. A layer policy
  (`QSMC_ChartLayers.mqh`, `InpChartProfile=CLEAN` by default) classifies every
  object family as primary / secondary / volume / volume detail / optional and
  shows the first three; `InpChartProfile=LEGACY` restores the previous behaviour.
  The eight new inputs are at the end of the dialog. Verified by
  `tools/test_qsmc_chart_hygiene.py`, which executes the real function before and
  after (12 publications: 24 objects -> 2).
* **`MQL5/Indicators/QSMC_SmcVpEngine.mq5`: a new, additive indicator.** Ten
  confirmations in a fixed order (H4 bias, H1 structure, M15 liquidity, sweep,
  displacement, BOS/CHoCH, OB/FVG, volume profile, entry, risk/reward), no score:
  BUY SETUP or SELL SETUP only when every step of exactly one side holds on
  closed bars, otherwise WAIT with the step that blocks. A 16-row dashboard, at
  most about 50 objects named `QSVP_*`, five `DRAW_NONE` buffers. It was added
  as its own program instead of being edited into the 45,000-line indicator so
  that the line-pinned audit suites of `nadir2.mq5` stay valid and either
  indicator can be removed without touching the other. Verified by
  `tools/test_qsmc_smcvp.py`.
* **Not verified here:** MetaEditor F7, the Strategy Tester and a live chart. No
  MetaTrader runs in the repository's CI or in the environment this was written
  in. Press F7 on `nadir2.mq5` and on `QSMC_SmcVpEngine.mq5` before trusting either.

### v6.6.20 — runtime-log review and diagnostic truthfulness

This hotfix follows the supplied MT5 startup/shutdown excerpt. It changes
diagnostics and object-cleanup accounting only; the closed-bar signal model,
exported buffers, retry bounds, fallback policy and EA execution contract are
unchanged.

* The startup banner says `LIVE MARKET | ANALYSIS ONLY (no orders)` instead of
  `LIVE TRADING`. The legacy `InpRealTimeZones` input is explicitly marked
  inert; the real calculation cadence is `InpUpdateEveryTick`, while zone and
  signal authority remains closed-bar.
* The EA-reader role is detected before informational banners. Duplicate
  reader PASS/banner/stop text is suppressed, but the deterministic self-tests
  still run and FAIL/handle/input/data warnings remain visible.
* Sniper copy waits now print the actual retry bound, terminal error and
  `BarsCalculated` count where available, identify the instance role, and print
  a `READY` recovery line. The existing bounded retry/partial-data policy is
  not relaxed or tightened by this wording change.
* Routine `[QSMC_ZONE_REJECT]` diagnostics are visual-only; the rejection itself
  still applies to both instances.
* The arbitration leak verdict counts the five owned object names still on the
  chart after cleanup. Lifetime `created/deleted` counters are still printed,
  but no longer infer phantom survivors when the host sweep deleted an object
  first. See `docs/QSMC_RUNTIME_LOG_REVIEW_AR.md`.

### v6.6.19 — tick/UI performance and the Bid-line complaint

This release separates **calculation** from **chart painting**. It does not
change the closed-bar signal model, the exported signal buffers, or the
AutoTrader execution contract.

* The EA-owned `iCustom` reader is detected before the arbitration root is
  created. It no longer wipes the visual chart's `QSMC_` objects, no longer
  enables the arbitration renderer, and no longer draws the liquidity-value
  badge or Core status badge.
* Live preview **state** still updates on every tick. Chart-object writes are
  coalesced to roughly 100 ms between bars; a new bar, rebuild, or explicit
  chart event paints immediately. Panels keep their existing 300 ms cadence.
* Drawing primitives compare properties before writing them, so an unchanged
  closed-bar label/line/zone does not invalidate the chart again.
* ATR/ADX/RSI history is copied in full on attach/rebuild, then only the
  changed tail is copied. EMA/VWAP keep their incremental path.
* `InpShowPerfMeter=true` prints a visual-instance `[QSMC_PERF]` report every
  30 seconds: average/max `OnCalculate` microseconds, max bar-slice
  microseconds, owned object count, and server-clock quote age. It measures
  the indicator body only — **not** broker RTT, terminal paint time, or the
  EA's order path. A delayed Bid line alone is not proof of a network fault.

To compare builds, attach the same symbol/timeframe with the same inputs,
enable `InpShowPerfMeter` on the visual instance, and record several
`[QSMC_PERF]` lines during comparable quote activity. Then press **F7** in
MetaEditor and verify `0 errors, 0 warnings`; the offline checks below are
not a compiler.

**أخطاء الترجمة التي كانت تظهر** (`reference cannot used`, `'0xFF' - invalid number`,
`'IntegerToString' - class type expected`) تم إصلاحها في v6.6.1 — راجع
`docs/QSMC_REVIEW_v6.6.1.md` القسم 2.

---

## 0b. Why is there no trade? (troubleshooting)

The complete, ordered list of everything that can stop a trade — from "the EA is
not attached" to "the broker rejected the stops" — is
`docs/QSMC_WHY_NO_TRADES.md`. It gives the literal Journal line for each cause
(`state INERT`, `state BLOCKED: …`, `[QSMC_AT] skip …`) and the one input to
change. Read it before changing any threshold.

## 1. What has to be where

MetaEditor resolves `#include <QSMC/QSMC_Root.mqh>` **only** under the data
folder's own `MQL5\Include`. There is no per-project include path in MQL5.

```
<Data Folder>\MQL5\
├─ Include\QSMC\QSMC_Types.mqh          <- all 31 headers go here, flat
├─ Include\QSMC\QSMC_MarketData.mqh
├─ Include\QSMC\…  (QSMC_Zones, _Reaction, _Bias, _Preset, _Gates,
│                   _AlertManager, _Arbiter, _Stats, _Renderer, _Root,
│                   _Selftest, _Scanners, _DataProvider, _LiquidityValue, _UnifiedDecision,
│                   v6.6.22: _SignalRegistry, _ChartLayers, _SvpCore, _SvpLiquidity,
│                   _SvpZones, _SvpVolumeProfile, _SvpDecision, _SvpChart)
├─ Indicators\nadir2.mq5                <- the indicator itself (repo root)
├─ Indicators\QSMC_ScannerProbe.mq5      <- PART C Phase 7 scanner host (v6.6.3)
├─ Indicators\QSMC_SmcVpEngine.mq5       <- v6.6.22 SMC + Volume Profile engine (display only, optional)
├─ Scripts\QSMC_ArbiterTest.mq5         <- deterministic self-test harness
├─ Experts\KLJ_DataFeeder.mq5           <- optional CSV data feeder (PART C)
└─ Experts\QSMC_AutoTrader.mq5          <- v6.6.20 execution companion (armed on demo, real account refused)
```

The two `Experts` files are separate programs, and only one of them can trade:
`QSMC_AutoTrader.mq5` is the single file on the release gate's G4 allowlist.
`KLJ_DataFeeder.mq5` still contains no trade API, and the indicators and the
headers still contain none at all — that is what makes the dashboard safe to leave
on a chart.

`tools/apply_qsmc_arb_patch.py --check` prints `already patched (marker
present)` when `nadir2.mq5` already carries the arbitration hook. It is the
command to run after re-downloading a raw host file.

`tools/test_autotrader_contract.py` pins the other half of that boundary: the
execution companion reads only the CORE buffers 7-12, never the forming bar,
never a preview or ZRE buffer, ships **armed on demo** (and refuses a real
account in `Init` without `InpRealAccountConfirm`), sizes from `OrderCalcProfit()`
with HARD ceilings of 0.50% / 2.00% / 8.00%, and its rounding is reproduced
independently (floored volume, no-trade below the broker minimum, wider stop =>
smaller size). `tools/test_defaults_match_preset.py` proves the compiled defaults
and `presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set` are the same object. The operator guide
is `docs/QSMC_AUTOTRADER.md`.

`tools/check_release_gate.py` is the **deployment** gate — a different question
from `static_check.py`. It is what turns §2–§4 of
`docs/QSMC_PRODUCTION_CHECKLIST.md` into a command: one version everywhere, a
complete file layout, every input documented and quiet by default, nothing in the
layer able to trade or reach the network, and no log line on the per-bar path.
`GO` / `NO-GO` is its last line, and its exit code matches.

---

## 2. Compile

1. MetaEditor → `File → Open Data Folder` → copy the files as above.
2. Open `nadir2.mq5`, press **F7**. Then `QSMC_ArbiterTest.mq5`, then
   `KLJ_DataFeeder.mq5`, then — if you want the Phase 7 scanners —
   `QSMC_ScannerProbe.mq5`. Every one of them pulls in the same 23 headers, so
   compiling any of them proves those headers; compiling the probe is the only
   thing that proves `QSMC_Scanners.mqh`.
3. Target: **`0 errors, 0 warnings`** in the Results tab.

| Symptom in the Results tab | Cause | Fix |
|---|---|---|
| `cannot open include file 'QSMC/QSMC_Root.mqh'` | the `QSMC` folder is not under `MQL5\Include` of the **data folder** (it is not enough that it sits in the git checkout) | copy `MQL5/Include/QSMC` into `<Data Folder>/MQL5/Include/` |
| `unknown identifier 'InpArb…'` | an old copy of `QSMC_Preset.mqh` (which owns the 40 `InpArb*` inputs) is shadowing the new one | re-copy **all** `.mqh`, they are one release unit |
| `reference cannot used` | pre-v6.6.1 headers: a getter returned a reference (illegal in MQL5) | use the v6.6.1 headers, see `docs/QSMC_REVIEW_v6.6.1.md` §2 |
| `'IntegerToString' - class type expected` | a Print-style `,` chain inside a declaration | v6.6.1 `LeakReport()` uses `StringFormat()` |
| `'0xFF' - invalid number` + `undeclared identifier 'u'` | integer literal suffix `u` — MQL5 has none | v6.6.1 `CAlertManager::HashHex()` uses plain hex literals |
| `'>' - operand expected` + `'Ready' - undeclared identifier` + `')' - expression expected` on a line containing `p->M()` | MQL5 has no `->`, not even for class-object pointers; the compiler splits it into `-` and `>` and then reports the member as undeclared | dereference with `.`: `p.M()` — this was the v6.6.4 `QSMC_Scanners.mqh` failure, now caught by rule **D13** |
| `undeclared identifier 'dayofyear'` (or `dayofweek`) | the member of `MqlDateTime` is `day_of_year`, not `dayofyear` | use `st.day_of_year` / `st.day_of_week` — rule **D14** now checks every `MqlDateTime` member |
| `undeclared identifier 'StringFindRev'` + `',' - unexpected token` on the same line | MQL5 has no reverse string search; the undeclared name makes the parser lose the argument list, so one bad call yields five errors | scan backwards with `StringGetCharacter()` (see `FindLastSeparator()` in `KLJ_DataFeeder.mq5`) — rule **D15** |
| `wrong parameters count` + `built-in: bool FileMove(const string,int,const string,int)` | `FileMove`/`FileCopy` are 4-argument calls — source, source location, destination, destination flags — and have no defaults | `FileMove(tmp,FILE_COMMON,InpOutputFile,FILE_COMMON\|FILE_REWRITE)` — rule **D16** |

`nadir2.mq5` is CRLF. If you patch it with an editor that rewrites line
endings, `git diff` will show 39,800 changed lines; keep CRLF.

### Pre-flight without MetaEditor

`python3 tools/static_check.py` runs the mechanical part of a compiler pass
(balance, includes, interface coverage, struct members, new/delete) **and** the
MQL5 dialect rules D1–D16 from `tools/mql5_rules.py`, per translation unit
(the indicator, the self-test script, the feeder, the new scanner probe, and
`QSMC_Scanners.mqh` as a synthetic unit too, so the module stays linted even if
its host is ever removed). It is not a type checker: a clean run still needs F7.

---

## 3. Run the indicator

1. MT5 → open a chart (M5 or M15 is the intended lane; `InpArbPreset=AUTO`
   picks SCALPER / INTRADAY / SWING from the chart timeframe).
2. `Navigator → Indicators → nadir2` → drop it on the chart.
3. Journal must show, in this order:

```
[QSMC_ARB] v6.6.22 arbitration layer ON | preset INTRADAY (M15-H1) | gates 10
             | exec TF M15 | tactical may confirm: NO (informational only)
             | on XAUUSD M15
```

`on XAUUSD M15` is what the ATR / point / digits of every gate were
resolved against; if it is not the symbol and timeframe you are looking at, stop
and fix the chart, not the thresholds.

On removal (`OnDeinit`) the layer prints its own audit:

```
[QSMC_ARB] stop | bars 412 | published 3 | suppressed 7
[QSMC_ARB] outcomes: ...                       (session outcomes; EdgeBook persistence only with InpArbCSVLog=true)
[QSMC_ARB] alloc/free: market 5/5 | gates 10/10 | chart objects created/deleted 18/18 => no leak
```

`=> no leak` is the memory assertion of this layer: every `new` is matched by
a `delete`. Anything after `=>` that is not `no leak` is a bug — report the
whole line.

### Inputs that matter on day one

| Input | Default | Set it to |
|---|---|---|
| `InpArbEnabled` | `true` | `false` = inert, the indicator behaves as v6.5.5 |
| `InpArbGateTactical` | `true` | keep `true`; this is the anti-spam path for MTF entries |
| `InpArbTacticalMayConfirm` | `false` | `true` only if you accept a tactical alert labelled CONFIRMED (R7) |
| `InpArbGateCore` | `false` | `true` also re-gates the CORE path |
| `InpArbVerboseLog` | `false` | `true` while validating: one log line per gate verdict per closed bar |
| `InpArbCSVLog` | `false` | `true` to journal signals + outcomes to `MQL5\Files\QSMC_arb_*` |
| `InpArbPopup` | `true` | `false` on a chart you only want to draw on |

### The 10-minute validation protocol

1. `InpArbVerboseLog=true`, 24 h of M5 history on one symbol.
2. Count the published alerts: the old tactical path produced ~30 per 5 h;
   with the gate chain the expected order is 0–3 per 5 h.
3. For every published alert, read the `trace=` field: it must name the zone
   role and the state (`PUBLISHED | CONFIRMED SELL ZR_RESISTANCE …`).
4. For every *suppressed* candidate there must be a reason line
   (`cooldown 3/10`, `BETWEEN ZONES …`, `HTF_BIAS: COUNTER-TREND …`).
   A silence with no reason is a defect (rule R6).
5. Remove and re-attach the indicator: `=> no leak` twice.

---

## 4. Run the self-test (no market data needed)

`QSMC_ArbiterTest.mq5` drives the **production** path
(`CQuantumRoot → CReactionDetector → CSignalArbiter → gates → CAlertManager`)
against a synthetic 40-bar series, so its result is deterministic and does not
depend on the symbol or the broker feed.

Compile it (F7), drop it on any chart, read the Experts tab:

```
QSMC v6.6.0 SIGNAL ARBITRATION - DETERMINISTIC SELF-TEST
PASS  T00 the synthetic ATR matches QST_ATR              [expected 0.60 ...]
PASS  T01a SELL published at resistance                  [state=CONFIRMED ...]
...
---------------------------------------------------------
 RESULT: 45 passed, 0 failed
---------------------------------------------------------
```

| Scenario | What it pins down |
|---|---|
| T00 | harness ATR geometry plus weighted HTF/local direction and warning-only early-break input handling |
| T01 | a closed rejection at resistance publishes **one** SELL, and never a second one on the same or the next 20 bars |
| T02 | a closed break above resistance publishes a BUY, not a SELL at the same level |
| T03 | the reported defect: a SELL inside a **support** zone is refused |
| T04 | price between zones → `BETWEEN ZONES`, no alert |
| T05 | a fact citing the **forming** bar can never be CONFIRMED |
| T06 | 30 M1 fires inside one zone collapse to ≤ 1 alert, with a named suppression reason |
| T07 | flip-flop guard: the opposite direction on the same zone is refused |
| T08 | two charts of one symbol publish at most one alert (GlobalVariable lock) |
| T09 | a candidate opposed by the HTF bias is downgraded and the reason says COUNTER-TREND |
| T10 | empty series → `BuildContext()` returns false, no signal, reason = data not ready |
| T11 | EW/CUSUM/Wilson/tick-volume profile arithmetic and invalid-input handling |
| T12 | causal swing confirmation, close-only BOS/CHoCH, and sweep-vs-break distinction |
| T14 | zone scorer hard gates, missing-input reporting, and bounded context rank |

Any `FAIL` line prints the measured value; the exit code of the script is the
failure count (visible in the last line `RESULT: x passed, y failed`).

---

## 5. Run the offline checks (any machine, no terminal)

```bash
python3 tools/static_check.py            # mechanical pass + dialect rules D1-D16
python3 tools/test_arbiter.py            # independent Python mirror of the gates
python3 tools/test_arbiter.py -v         # every scenario, printed
python3 tools/check_scenario_geometry.py # predicts the ATR geometry of every T0x
python3 tools/test_scanners.py           # arithmetic of QSMC_Scanners.mqh
python3 tools/test_quant_stats.py        # EW/CUSUM/Wilson/tick-volume profile
python3 tools/test_structure.py          # causal confirmed structure events
python3 tools/test_early_break.py        # warning-only heuristic contract
python3 tools/test_zone_scoring.py       # hard gates + normalized zone rank
python3 tools/test_edgebook_contract.py  # versioned storage/dedup contract
python3 tools/mql5_rules.py --root DIR   # dialect rules only, for another tree
python3 tools/apply_qsmc_arb_patch.py --check
python3 tools/check_release_gate.py      # go/no-go for a live chart (G1-G7)
```

`test_arbiter.py` is an **independent** re-implementation of rules R1–R7, not a
translation. If it and the MQL5 self-test ever disagree, one of them has a
defect — that is the point of keeping both. None of these scripts is a
backtest: no statistics, no win rate, no profitability claim.

Expected: `RESULT: 22 passed, 0 failed` (arbiter), `all geometry checks
passed`, `all scanner arithmetic checks passed`, and for `static_check.py`
`no errors` with 5 warnings (new/delete site counting is coarse on purpose; the
runtime `AllocCalls()/FreeCalls()` ledger is the real check; the fifth is the
probe's own single `new CMarketData`, freed in `OnDeinit`).

Those commands are also a CI gate since v6.6.2:
`.github/workflows/qsmc-verify.yml` runs exactly them on every push and PR (the
release gate since v6.6.4), adds a check that one header name is never committed
twice under `MQL5/`, uploads the logs, and ends with the step it cannot run for
you — **F7 in MetaEditor**.

---

## 5b. `QSMC_ScannerProbe.mq5` — the Phase 7 scanners (v6.6.3)

This is the host that `QSMC_Scanners.mqh` never had. Nothing in it decides a
trade: it ranks, describes, and prints text into the chart's `Comment()` — no
objects, no files, no orders.

1. F7, then drop it on any chart. The one warning that is *expected* here is
   `no indicator plot defined for indicator` — the probe declares
   `indicator_buffers 0 / indicator_plots 0` on purpose, because it draws text and
   nothing else. Every other file still targets `0 errors, 0 warnings`. Journal:
   `[QSMC_SCAN] probe ON | 6 symbols | tf PERIOD_H1 | bars 400 | budget 30ms | basis SERVER | observational only, no gate is decided here`
2. The first `Comment()` update can take a few timer ticks: `Scan()` is time-boxed
   by `InpProbeBudgetMs` (30 ms) and resumes from its cursor, so a 64-symbol
   universe costs nothing per tick. The panel says `pass in progress - n of m
   symbols` while it works.
3. Read the bottom of the panel, not just the table: every symbol that produced
   no row is listed with its reason (`MISSING SYMBOL`, `HISTORY NOT SYNCED`,
   `NO DATA`, `NO SETUP`). An empty table with no reasons below it is a bug report,
   not "no opportunities".
4. `InpProbeSymbols` takes `NAME` or `NAME:GROUP` (`FX`, `INDEX`, `COMMODITY`,
   `METAL`, `RATE`, `OTHER`). The mapping is an input because broker naming is not
   standardised — the probe never guesses a group.
5. Seasonality is withheld below `InpProbeMinN` and always shows `n`, years and
   dispersion. That is the module's honesty rule, not a formatting choice; do not
   lower `InpProbeMinN` to make a table appear.
6. `OnDeinit` prints `probe OFF after N pass(es) | alloc/free a/b => no leak`.

It is a triage tool. Its zones are swing-derived from price alone, **not** the
chart's ZRE zones, and a row surviving the score floor does **not** mean the
arbiter would accept it — the floor is a display threshold on a composite score
that includes zone strength, while the gate compares `evidence_count` itself.

---

## 6. `KLJ_DataFeeder.mq5` (optional, PART C)

A companion EA whose only job is to publish the series the scanners want into
`MQL5\Files\qsmc_feed\*.csv`, so the indicator never calls `CopyRates` on other
symbols.

1. Attach it to a **dedicated** chart (any symbol; it reads the symbol list from
   its own inputs).
2. Allow file writing on the common tab of the EA dialog; **no** trade
   permissions are needed — it contains no trading call.
3. Check `MQL5\Files\qsmc_feed\` for `series_id,as_of,value,prev,label` rows.
4. `QSMC_DataProvider.mqh` is the reader; it validates `as_of` freshness and
   returns `valid=false` for anything stale — the indicator then says
   `data not ready: …` instead of inventing a number.

The feeder is not required for the arbitration layer; the layer is fully
functional without it.

---

## 7. Rollback

* **Soft:** `InpArbEnabled=false`. The root is still created, but every entry
  point returns immediately; the indicator behaves as v6.5.5.
* **Hard:** delete `<Data Folder>/MQL5/Include/QSMC` and recompile
  `nadir2.mq5`. Compilation fails on the missing include, which is why the
  include sits behind the marker — restore the pre-v6.6.0 host file if you need
  a build with no arbitration source at all.
