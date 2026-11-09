# DEMO-AUTO defaults — 2026-11-09

What this delivery does: **QSMC_AutoTrader runs on a DEMO account with the production
configuration from the first attach — no `.set` file, no Inputs editing.** A real-money
account is refused at `OnInit`, before the first tick.

Status of the evidence, stated first because it bounds everything below:

| | |
| --- | --- |
| Compiled in MetaEditor (F7) | **NO** — this environment has no MetaEditor. Nothing here is a compile result. |
| Run on an MT5 terminal | **NO** — no order was placed, no journal line was produced by this work. |
| Verified mechanically | `check_production_ready.py` 47/47, `check_release_gate.py` GO (0 warnings), `test_autotrader_contract.py`, `test_defaults_match_preset.py` (45), `test_execution_safety.py`, `test_at_risk_audit.py`, `test_causal_chain_regressions.py` |
| Version string | unchanged at **v6.6.20** (see "Decisions for you", item 1) |

---

## 1. Every changed default

Thirteen inputs changed. Everything else already matched
`presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set` and was left alone.

| input | before | after | why |
| --- | --- | --- | --- |
| `InpEnableTrading` | `false` | **`true`** | arm on demo |
| `InpDryRun` | `true` | **`false`** | actually send on demo |
| `InpMaxRiskPercent` | `1.00` | **`0.10`** | preset value |
| `InpMaxSpreadPoints` | `30` | **`60`** | preset value |
| `InpDeviationPoints` | `20` | **`30`** | preset value |
| `InpMinRRAtFill` | `1.00` | **`1.20`** | preset value |
| `InpSessionStartHour` | `0` | **`10`** | session 10:00–18:00 server |
| `InpSessionEndHour` | `0` | **`18`** | idem |
| `InpCooldownAfterLossMin` | `0` | **`60`** | preset value |
| `InpPartialCloseAtR` | `0.0` | **`1.50`** | partial 50 % at 1.5R |
| `InpPinTimeframeMinutes` | `0` | **`15`** | M15 pin (see Decisions, item 2) |
| `InpFixedLotsMaxRiskPercent` | `2.00` | **`1.00`** | one FIXED-mode ceiling (F2) |
| `HardMaxRiskPercent()` | `5.00` | **`0.50`** | F8 |
| `HardMaxDailyPercent()` | `10.00` | **`2.00`** | F8 |
| `HardMaxDDPercent()` | `20.00` | **`8.00`** | F8 |

Unchanged and verified equal to the preset: risk `0.10`, daily `0.50`, account DD `3.00`,
consecutive losses `2`, entries/day `3`, open positions `1`, spread ≤ 10 % of the stop,
tick age `30 s`, signal age `2` bars, stop `20..5000` pts, order retries `3`,
break-even `+1.00R`, partial `50 %`, TP source `LEVEL1`, pip ladder **off**,
close-on-opposite **off**, magic `20261027`, heartbeat `300 s` / `200` bars, poll `2 s`,
verbose `false`, lot mode `RISK%`.

**New preset files**

- `presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set` — a printout of the compiled defaults.
  Optional; loading it changes nothing (`[QSMC_AT PRESET CHECK] … IDENTICAL`).
- `presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set` — now means "the same
  configuration, but `InpEnableTrading=false` + `InpDryRun=true`", i.e. the old
  observation ladder. Its two **malformed keys are fixed** (below).

### Two defects found in the preset itself

```
IInpMaxDailyLossMoney=0.00        <- typo: MT5 silently ignores it
npMaxAccountDrawdownPct=3.00      <- typo: MT5 silently ignores it
```

An unknown key in a `.set` is not an error in MT5 — it is ignored. So loading the
"production safe" preset **never applied the 3.00 % account-drawdown halt**, and the
money stop was never configured. Both keys are corrected in that file; a test
(`test_defaults_match_preset.py`) now fails if any key in either preset does not match
an input.

---

## 2. Activation, and what still refuses

`InpEnableTrading=true`, `InpDryRun=false`, `InpDemoOnly=true`,
`InpRealAccountConfirm=""`.

`OnInit` now refuses a real account **unconditionally**:

```mql5
if(is_real)
  {
   if(InpDemoOnly)                     -> INIT_FAILED, "INIT REFUSED: this is a REAL account …"
   else if(InpRealAccountConfirm != login) -> INIT_FAILED, "… type the account number EXACTLY …"
  }
```

The old test fired only when the EA was *already armed* (`is_real && InpEnableTrading
&& !InpDryRun`). With armed-by-default that would have been a guard that arrives after
the decision. This is **stricter** than before: an inert EA used to be allowed to sit
on a real chart; now it will not initialise there at all. No breaker was removed, no
gate loosened, no stop may be widened.

---

## 3. The eight fixes

| # | fix | where |
| --- | --- | --- |
| F1 | `CountConsecutiveLosses()` counts from the last reviewed reset (`InpResetBreakersAtInit`), stamped in GV `QSMC_AT_RST_…`. Before, the reset cleared the flag and the next tick recomputed the same streak. | `CountConsecutiveLosses`, `ResetStampKey` |
| F2 | one FIXED-lot ceiling: `EffFixedLotRiskPct()`, used by the guard **and** the banner. Before: comment said 1 %, guard used 2.00, banner recomputed `min(InpMaxRiskPercent, 1.0)`. | `EffFixedLotRiskPct`, `CalcLots`, ladder banner |
| F3 | `CalcLots` (RISK %) and the printed `risk_money` use `EstimateLossAtSL` → `OrderCalcProfit`; fail closed (lots = 0) when the stop cannot be priced; the volume is stepped **down** until the measured loss fits. | `CalcLots`, `HandleSignal` |
| F4 | account drawdown measured from the **equity high-water mark**, persisted (GV `_HWM`), restored as `max(stored, session baseline, equity)`, cleared by a reviewed reset. | `SessionGuardUpdate`, `OnInit` |
| F5 | `DayGuardKey` / `SessionGuardKey` use `KeySafe(_Symbol)`. `GlobalVariableSet` rejects names outside `[A-Za-z0-9_]` **silently**, so `XAUUSD.m` never persisted a baseline. | both key builders |
| F6 | no message claims a restart clears a breaker. Daily: "clears by itself at the next server day roll". DD / streak: "needs a human reset after review; a restart does NOT clear it". | refusal texts |
| F7 | `DRY RUN` no longer spends `InpMaxTradesPerDay`: separate persisted counter `DRYTRADES`, printed in the discipline line, reset at the server-day roll. | `CountOneDryTrade` |
| F8 | HARD ceilings 0.50 % / 2.00 % / 8.00 %. | `HardMax*` |

## 4. Indicator wiring

- The EA still reads `nadir2` with **compiled defaults** (no input list). Nothing in
  the indicator's thresholds was changed: `InpMinConfidenceScore=75`,
  `InpMinReliability=80`, `InpMinRR1=1.5`, `InpMaxStopATR=4.0` are byte-identical to
  what the shipped log printed (`GATE PROFILE: STRICT | 75 | 80 | 1.50 | 4.00 ATR`).
- `presets/nadir2_PRODUCTION_XAUUSD.set` pins the same three floors numerically
  (75 / 80 / 1.5) but selects `InpGateProfile=QSMC_GATE_PRACTICAL`. **The numbers are
  equal; the profile enum is not** — see Decisions, item 3.
- **`input_hash` mismatch — cause found, and it was not the role field.** The hash
  covers the 576 inputs only (`QSMC_InputFingerprint.mqh`), and there is no role
  input. The defect was the *comparison*: `QSMC_InstanceBase()` is scoped by
  server|login|symbol|period, and every instance published `H<hash>`, so the VISUAL
  instance on the chart and the `EA_READER` instance created by the EA's `iCustom`
  compared their hashes with each other. They are *supposed* to differ when the chart
  has a `.set` loaded. The reader then reported `INSTANCE MISMATCH`, and
  `QA_CoreDisplayRefresh()` returned before publishing anything → the panel read
  `INSTANCE MISMATCH - WAIT` and the EA's heartbeat read `CORE signals: 0`.
  Fix: role-tagged namespace `H<role>_<hash>` (legacy `H<hash>` is still written),
  set via `QA_SetInstanceRole()` before the first publish. Cross-role comparison is
  gone; same-role divergence is still a mismatch.

---

## 5. What to check on the terminal (the part that cannot be tested here)

1. F7 in MetaEditor for `nadir2.mq5`, `MQL5/Indicators/nadir2.mq5`, the headers and
   `QSMC_AutoTrader.mq5`. **0 errors.** This has not been done.
2. Attach on XAUUSD **M15** on a **demo** account with no `.set`. Expect, in order:
   `[QSMC_AT PRESET CHECK] … IDENTICAL`, `[QSMC_AT] envelope: …`,
   `[QSMC_AT] state ARMED: demo account, live orders`.
3. Load the `.set` by hand and change one input: the same line must print that one
   difference (`InpX | preset=… | now=…`) and nothing else.
4. First heartbeat: `dd_hwm=…/3.00% hwm=…`, `entries today 0/3`, and — with
   `DRY RUN` back on — `dry rehearsals today N` that does **not** move the live counter.
5. Attach the same EA to a **real** account: it must print
   `INIT REFUSED: this is a REAL account …` and stay greyed out in the Navigator.

## 6. Decisions for you

1. **Version number.** These defaults ship under **v6.6.20**, the same string as the
   inert build. Anyone holding the older `QSMC_AutoTrader.ex5` and the new docs will
   read "armed" and run "inert". Say the word and I will bump the whole triple
   (`#property version "6.621"`, `QSMC_VERSION_TEXT`, gate G1, docs) to v6.6.21.
2. **`InpPinTimeframeMinutes`.** The preset said `0` (off); your expected-values list
   said `15`. I compiled **15** and this is now the one place the compiled default and
   the old preset disagreed. It means the EA refuses any chart that is not M15. If you
   want the pin optional, say so and I will set it back to 0.
3. **`InpGateProfile`.** Compiled `STRICT`, chart preset `PRACTICAL`. Since you told me
   any loosening is a separate decision, I changed nothing: the three floors are equal,
   so the numeric outcome is the same today, but flipping the enum would relax the
   derived gates (stop ATR / search window). Your call.
4. **Real-account behaviour changed.** The EA no longer initialises on a real chart
   even when inert. If any workflow depends on parking it there for observation, that
   workflow now needs `InpDemoOnly=false` + the login typed in.

---

## ملخّص عربي

- الـEA يعمل الآن على حساب **demo** من أول إرفاق: `InpEnableTrading=true`،
  `InpDryRun=false`، `InpDemoOnly=true`، وبلا ملف `.set`.
- الحساب الحقيقي يُرفض في `OnInit` قبل أول تيك، ولا يُسلَّح إلا بكتابة رقم الحساب في
  `InpRealAccountConfirm`.
- الافتراضات المترجمة = الإعداد الإنتاجي: مخاطرة 0.10%، خسارة يومية 0.50%، سحب حساب
  3.00% من **أعلى حقوق ملكية**، خسارتان متتاليتان، 3 دخولات/يوم، جلسة 10–18، تهدئة
  60 دقيقة، تعادل +1.0R، جزئي 50% عند +1.5R، سبريد 60، انزلاق 30، RR 1.20، تثبيت M15.
- السقوف الصلبة صارت 0.50% / 2.00% / 8.00%.
- ثمانية إصلاحات في نفس التسليم (F1–F8) — أهمها: حساب اللوت والمخاطرة عبر
  `OrderCalcProfit` وإغلاق آمن عند تعذّر التسعير، وقاطع السحب من أعلى قمة، وسلسلة
  الخسائر تبدأ من إعادة الضبط المعتمدة، و`DRY RUN` لا يستهلك ميزانية اليوم.
- **لم يُترجم ولم يُجرَّب على MT5:** لا يوجد MetaEditor هنا. اضغط F7 أولًا، ثم اقرأ
  سطر `[QSMC_AT PRESET CHECK] … IDENTICAL`.
