# QSMC v6.6.13 — the execution companion (`QSMC_AutoTrader.mq5`)

## 0. العربية — باختصار

**ما أُضيف:** برنامج تداول آلي منفصل اسمه `QSMC_AutoTrader.mq5`. المؤشر نفسه
وطبقة QSMC بقيت **كما هي: لا تستطيع فتح صفقة**. التنفيذ يعيش في ملف واحد معزول
لأن لوحة القرار يجب أن تبقى آمنة عند تركها على المخطط.

**كيف يقرأ الإشارة:** ينشئ نسخة خاصة من `nadir2` عبر `iCustom` ويقرأ فقط
مخازن الإشارة المؤكدة (CORE) التي يملأها المؤشر بعد **إغلاق** الشمعة:
الاتجاه، الدخول، الوقف، TP1/TP2/TP3. لا يقرأ معاينة الشمعة الحالية ولا
إشارات ZRE التكتيكية.

**بوابات الدخول لم تُرخَّ إطلاقاً:** البرنامج لا يعدّل أي بوابة في المؤشر، ولا
يمرّر أي إعداد يتجاوزها (`iCustom` بلا مدخلات = إعدادات المؤشر الافتراضية).
هو **مُنفّذ** لما نشره المؤشر، وليس مصدر إشارة ثانياً.

**الأمان الافتراضي:** يصل **معطّلاً** (`InpEnableTrading=false`)، وأول تشغيل
يكون **تجربة على الورق** (`InpDryRun=true`)، ويرفض الحساب الحقيقي
(`InpDemoOnly=true`). سقف المخاطرة 1% من رأس المال لكل صفقة، والبرنامج يرفض
أي صفقة بلا وقف، أو بوقف في الجهة الخاطئة، أو بوقف أوسع من الحد.

**ما لا يفعله:** لا مضاعفة عقود (martingale)، ولا تعزيز للخسارة، ولا توسيع
للوقف، ولا مطاردة لسعر تحرّك. وليس ضماناً للربح: الحجم والفلاتر إدارة مخاطر،
وليست ميزة سعرية.

---

## 1. Why execution is a second program

The indicator and the 18 headers of the QSMC layer are observation-only, and that
is a checked property, not a slogan: `tools/check_release_gate.py` G4 fails the
build if any file in the layer reaches `OrderSend`, `CTrade`, `PositionOpen`,
`OrderCalcMargin` or the margin API. `tools/test_autotrader_contract.py` repeats
the check independently.

That property is what lets you leave the dashboard on a chart without arming
anything. It would be lost if trading were bolted into `nadir2.mq5`. So execution
lives in **one** file with **one** purpose:

```
MQL5/Experts/QSMC_AutoTrader.mq5     <- the only file allowed to trade (G4 allowlist)
```

Everything about that exception is checked as well:

| Check | What it proves |
| --- | --- |
| G4 | the layer (18 headers + indicator + probe) and the data feeder still contain no trade API |
| G8 | the companion ships inert, dry-run and demo-only, its risk ceiling is 1% and the sizing code actually clamps to it, and there is no lot doubling anywhere |
| contract test | it reads only the CORE buffers (7–12), never shift 0, never a preview or ZRE buffer; a signal with no stop or with wrong-side geometry is refused |

---

## 2. What signal it trades — and what it will not

It creates one private instance of `nadir2` (`iCustom`) on the chart's own symbol
and timeframe, and reads the buffers the indicator already fills for the
**published CORE signal**, after the bar closes:

| Buffer | Meaning |
| --- | --- |
| 7 | direction: `+1` buy, `-1` sell, `0` none |
| 8 | entry |
| 9 | stop |
| 10 | TP1 |
| 11 | TP2 |
| 12 | TP3 |

Refused by design:

- the **forming** bar (shift 0). A signal exists only when its bar has closed;
- the **tactical preview** mark and the **ZRE/RXN** layers: they are observations,
  not the published core signal;
- a signal whose bar is older than `InpMaxSignalAgeBars`, or that existed before
  the EA was attached (`g_start_bar`);
- a signal already acted on in this terminal session (a terminal GlobalVariable
  keyed by `magic|bar_time|direction`, so a reload cannot re-fire it).

**Entry gates are not touched.** The companion passes no inputs to `iCustom`, so
the instance it reads runs the indicator's documented default settings — the same
10-gate chain the dashboard explains. To trade a different preset you must change
the indicator, recompile, and re-read §4 of this document; there is no "loosen it
from the EA" path, and that is deliberate.

> Practical consequence, stated rather than hidden: if you attach the indicator
> to the chart with **custom** inputs, the EA is still reading the **default**
> instance. Keep the indicator defaults, or copy the same values into the
> indicator's `#default` inputs before compiling.

---

## 3. The switches

### Switches — the first three decide whether money can move

| Input | Default | Meaning |
| --- | --- | --- |
| `InpEnableTrading` | `false` | master switch. `false` = the EA can never send an order; it still logs what it *would* do |
| `InpDryRun` | `true` | with trading enabled, still only prints the order line; nothing is sent |
| `InpDemoOnly` | `true` | refuses any account whose trade mode is not `DEMO` |
| `InpRealAccountConfirm` | `""` | on a real account you must type **the account number** here. A preset copied from a demo chart therefore cannot arm real money |
| `InpMagic` | `20261027` | this EA only counts, closes and modifies positions with this magic |
| `InpIndicatorName` | `nadir2` | compiled indicator file name (no extension) |
| `InpTradeComment` | `QSMC-AUTO` | comment stamped on the order |

### Sizing

| Input | Default | Meaning |
| --- | --- | --- |
| `InpLotMode` | risk % | `QSMC_LOT_RISK_PERCENT` or `QSMC_LOT_FIXED` |
| `InpRiskPercent` | `0.25` | % of **equity** risked between entry and stop |
| `InpMaxRiskPercent` | `1.00` | hard ceiling. Values above `1.0` are ignored by the code, not just by advice |
| `InpFixedLots` | `0.00` | fixed volume for `QSMC_LOT_FIXED`; refused if its stop loss would exceed the ceiling |

The volume is `floor(risk_money / loss_per_lot / step) * step`:

- it is **floored**, never rounded up — rounding up is how a "0.25%" trade becomes
  a 0.4% trade;
- below the broker minimum the answer is **no trade**, not "the minimum lot";
- the stop comes from the signal, so a wider stop means a smaller position — never
  a widened stop to keep a preferred size;
- free margin is checked with `OrderCalcMargin`; if the size does not fit, it is
  **halved** up to eight times, and then the trade is skipped. The stop is not
  touched.

Worked example (XAUUSD-like: tick `0.01`, $1 per tick per lot, step `0.01`):

| Equity | Risk | Stop distance | Volume | Real risk |
| --- | --- | --- | --- | --- |
| $10,000 | 0.25% = $25 | $1.00 | 0.25 | $25.00 |
| $10,000 | 0.25% = $25 | $2.00 | 0.12 | $24.00 |

Both rows are reproduced by an independent model in
`tools/test_autotrader_contract.py`.

### Exits and filters

| Input | Default | Meaning |
| --- | --- | --- |
| `InpTPLevel` | TP1 | which indicator target becomes the order's TP |
| `InpBreakEvenAtR` | `1.00` | move the stop to the entry after +1R; `0` disables it |
| `InpMaxSpreadPoints` | `30` | skip while the spread is wider |
| `InpMaxOpenPositions` | `1` | cap on this magic + symbol |
| `InpMaxDailyLossPercent` | `3.00` | stop opening trades for the day after this equity drawdown |
| `InpMaxSignalAgeBars` | `2` | ignore a signal older than this many closed bars |
| `InpMinStopPoints` | `20` | refuse a stop tighter than this |
| `InpMaxStopPoints` | `5000` | refuse a stop wider than this |
| `InpCloseOnOpposite` | `false` | close this magic's position when the opposite signal publishes |
| `InpPollSeconds` | `2` | timer period; the EA also works from `OnTick` |
| `InpVerbose` | `false` | add the repeated "still skipped" polls |
| `InpHeartbeatSeconds` | `300` | print a read-only diagnostic line every N seconds; `0` disables it |
| `InpHeartbeatLookback` | `200` | how many closed bars the heartbeat scans for any published CORE signal |

### The heartbeat: silence is the failure you will actually meet

When no order appears there are only **two** root causes, and a quiet Journal
used to make them indistinguishable:

1. the indicator published **no CORE signal** (its own gate chain rejected every
   bar), so the EA literally had nothing to execute; or
2. the indicator **did** publish, and an EA filter refused it (spread, stop
   bounds, volume 0, position cap, …).

Every `InpHeartbeatSeconds` (default 5 minutes, and once immediately after
attach) the EA prints one `[QSMC_AT] heartbeat:` line that decides between them
by scanning the CORE direction buffer (slot 7) over the last
`InpHeartbeatLookback` closed bars:

* `CORE signals in last 200 closed bars: 0 -> the indicator published NO CORE
  setup` → the problem is upstream; read the chart panel's `NEEDS:` row, or set
  `InpGateAuditLogEveryBars>0` inside `nadir2` to see which gate rejected.
* `CORE signals in last 200 closed bars: 3 … last skip: <bar>|<dir> - <reason>`
  → the transport works; the printed reason is the exact filter to adjust.

The line also carries the mode (`INERT` / `DRY RUN` / `BLOCKED: …` / `ARMED`),
the processed/sent/dry/refused counters, the open-position count, the daily
guard state and the age of the most recent signal (so a signal older than
`InpMaxSignalAgeBars` is named as no longer tradable). It is strictly read-only:
it copies one buffer and prints; it never touches a gate, an order or a
position.

`OnTimer` exists because a quiet symbol can go minutes without a tick. It reads
the same closed-bar buffers, so it cannot create a signal that `OnTick` would not
see.

### v6.6.12 — `InpGateProfile`: the one sanctioned way to relax a threshold

`InpGateProfile` is an enum with two values. `QSMC_GATE_STRICT` (the default)
returns every input untouched, so an existing installation is byte-for-byte
unchanged. `QSMC_GATE_PRACTICAL` relaxes exactly five numeric entry thresholds
and prints each change at init:

| Input | STRICT | PRACTICAL |
| --- | --- | --- |
| `InpMinConfidenceScore` | 75 | 60 |
| `InpMinReliability` | 80 | 60 |
| `InpMinRR1` | 1.50 | 1.20 |
| `InpMaxStopATR` | 4.0 | 6.0 |
| `InpAnchorSearchBars` | 60 | 120 |

Why this is not "the AI lowered the gates": the gates read effective values
from five `Eff*()` helpers, and each helper returns the raw input unless the
operator chose PRACTICAL. `tools/test_gate_profile.py` proves structurally that
(a) the default is STRICT, (b) the profile is read **only** by those five
helpers, the banner and the publisher, (c) no gate still compares against a raw
input, (d) the location check, blacklist, top-down switch and journal gate are
unreachable from it, and (e) the companion cannot set it — it can only print
which one is active.

The profile never tightens a value you set stricter yourself (`MathMin` /
`MathMax`, permissive direction only), and it says out loud what it does not
fix: *"this makes MORE trades possible, not better ones."* If the measured
blocker is structural (`closest rejection: none`), the profile changes nothing,
because it does not touch the causal chain.

### v6.6.11 — the heartbeat reports the DISTANCE, not only the vote count

The verdict names the gate that refused most often. That is still a count: it
cannot distinguish "the threshold is one point too high" from "the market never
produced the pattern". The companion now also prints the measured shortfall of
the best candidate of the session:

```
... | closest rejection: RELIABILITY short by 3.1 point(s) - the best candidate of
this session was ONE input away from passing | best reached: conf 71,
reliability 77, RR1 1.42, anchors 118 | profile window: 143 closed bars since attach
```

* `closest rejection: <GATE> short by N` — the gap to the input that refused it.
* `closest rejection: none … the causal chain did not complete` — no threshold
  was the reason; lowering one would open nothing. This is the single most
  useful sentence in the whole diagnostic, because it stops a pointless
  threshold change.
* `best reached: …` — the highest value any candidate achieved, to compare with
  the indicator's own minimum inputs.
* `profile window: N closed bars` — the sample size. A peak without a window is
  not evidence.

A shortfall is only ever computed for the four numeric thresholds (confidence,
reliability, RR1, stop distance in ATR) and only for a candidate that already
cleared the structural gates — the chain never gets "you were 3 points short".
The profiler is read-only: no value it records reaches a gate, and deleting it
leaves every published signal identical. Acting on a number is your decision,
made explicitly, not something the code does quietly.

### v6.6.10 — the heartbeat now carries the INDICATOR'S verdict

`CORE signals in last 200 closed bars: 0` proves the transport is healthy and
the indicator published nothing, but it does not say **why**. The panel's
`NEEDS:` row answers that only while you are looking at the right chart, and
`InpGateAuditLogEveryBars` answers it only if you edited the indicator's inputs.

So `nadir2` now publishes the result of its own gate chain for the last closed
bar as terminal globals, and the heartbeat decodes them:

```
[QSMC_AT] heartbeat: INERT | CORE signals in last 200 closed bars: 0 -> the indicator published NO CORE setup, ... | indicator verdict: RELIABILITY - score below InpMinReliability in the indicator | indicator funnel: bars 143 armed 6 confirmed 0 | last closed bar 2026.10.28 09:15
```

Read it as four questions answered in one line:

| Fragment | Question it answers |
| --- | --- |
| `indicator verdict: <CODE> - <sentence>` | which gate refused the last candidate |
| `indicator funnel: bars N armed A confirmed C` | did the chain ever arm a setup, or did it die before that |
| `last closed bar …` | is the indicator actually evaluating *this* symbol and timeframe |
| `no diagnostic record for …` | the two programs are not on the same chart/symbol/timeframe, or the indicator is not compiled |

The published codes (identical table in both files, checked by
`tools/test_diag_bridge.py`):

| Code | Meaning | The input that changes it |
| --- | --- | --- |
| 0 | `NO_DATA` — no closed-bar pass yet | wait for one closed bar; check symbol/TF |
| 1 | `CORE_PUBLISHED` — a signal *was* published | if no order followed, read the `skip` line instead |
| 2 / 3 | `SETUP_ARMED` / `SETUP_PENDING` — a setup exists, not confirmed | nothing to fix; by design |
| 10 / 11 | no structure anchor / incomplete causal chain | the sweep → displacement → structure → zone sequence did not complete |
| 12–16 | sweep, displacement or the bound zone is missing | market did not produce the sequence |
| 17 / 18 | the zone failed the location or causality re-check | — |
| 19 | the sweep/break leg is too weak | `InpDisplacementATR` |
| 20 / 21 / 22 | RR below `InpMinRR1` / stop above `InpMaxStopATR` / targets unorderable | the indicator's geometry inputs |
| 23 / 24 / 25 | confidence / reliability / grade below the minimum | `InpMinConfidenceScore`, `InpMinReliability`, `InpMinGrade` |
| 26 | EMA200/VWAP opposes the direction | — |
| 27 | spread above `InpMaxSpreadPts` | `InpMaxSpreadPts` |
| 28 | the D1→M5 top-down chain blocks this direction | `InpTopDownGateCore`, `InpRequireInstitutionalConfirm` |
| 29 | another setup owns the execution lane | wait for its invalidation/expiry |
| 30 / 31 / 32 / 33 | direction veto / blacklist / lifecycle / branch rollback | — |
| 34 | some other gate refused it | `InpGateAuditLogEveryBars` for the literal sentence |

Two honest limits. First, the verdict is **read-only**: it copies nothing into a
gate, an order or a position, and the indicator's decisions are identical with
and without it. Second, it names the **top blocker of the session** (the gate
that refused most often), not a prophecy about the next bar: a long enough
sample can still produce a signal, and `CORE_PUBLISHED` for one bar does not
mean the next one fires.

The companion also distinguishes a dead indicator from a slow one now: a valid
`iCustom` handle whose `BarsCalculated()` is negative used to print "still
warming up" forever; it now says the instance exists but is **not calculating**,
which is an indicator-side problem (bad inputs, no history), not a signal
problem.

---

## 4. Install and the safe progression

1. Copy `nadir2.mq5` → `MQL5\Indicators\`, the 18 headers → `MQL5\Include\QSMC\`,
   and `QSMC_AutoTrader.mq5` → `MQL5\Experts\`.
2. MetaEditor: **F7** on `QSMC_AutoTrader.mq5`. It includes the terminal's own
   `<Trade/Trade.mqh>`; `0 errors, 0 warnings` is the target. F7 on `nadir2.mq5`
   as well — the EA is useless without the indicator compiled.
3. Attach the EA to the chart with **Algorithmic trading** enabled. Read the first
   journal line, it states the whole configuration:
   ```
   [QSMC_AT] QSMC v6.613 execution companion ON | XAUUSD PERIOD_M15 | magic 20261027 | mode RISK% risk 0.25% | tp 1 | break-even 1.00R | INERT | demo-only | closed-bar signals only, no martingale, no stop widening
   ```
4. **Session one — INERT.** Leave `InpEnableTrading=false`, set `InpVerbose=true`
   and read every `[QSMC_AT] skip ...` line. You are checking that the refusals
   make sense for your symbol (spread, stops level, signal age), not that the
   signals are "right".
5. **Session two — DRY RUN.** `InpEnableTrading=true`, keep `InpDryRun=true`. The
   EA prints `DRY RUN BUY/SEL ... lots ... sl ... tp ... risk ...` and compares
   those lines with what you would have done.
6. **Session three — demo, real orders.** `InpDryRun=false`, account stays demo.
   Check that the filled volume matches the printed one and the SL/TP are where
   the journal says.
7. Only then consider a real account. It takes **two** deliberate inputs, not one:
   `InpDemoOnly=false` **and** `InpRealAccountConfirm=<your account number>`.
   If the number does not match, every signal is refused with
   `REFUSED ... real account: set InpRealAccountConfirm to this account number`.
   Nothing in this repository makes a strategy profitable; this step is a risk
   decision, not a verification step. Start with `InpMaxOpenPositions=1` and
   `InpRiskPercent` at or below `0.25`.

### The attach banner answers "why is it not trading?"

One line, printed at attach, before any signal exists:

| Banner | Meaning |
| --- | --- |
| `state INERT` | `InpEnableTrading=false` (shipping default) |
| `state DRY RUN` | armed but `InpDryRun=true`; orders are only printed |
| `state BLOCKED: <reason>` | arming is complete but the environment refuses: Algo Trading off, EA trading disabled, broker/account permission, symbol disabled/close-only, `InpDemoOnly=true` on a real account, or a wrong `InpRealAccountConfirm` |
| `state ARMED: REAL account, live orders` | every switch has been set on purpose; orders will be sent |

`TradeEnvBlock()` is the single function behind `BLOCKED`, so the same reason is
printed whenever a specific signal is refused: `[QSMC_AT] REFUSED to send BUY
XAUUSD: <reason>`.

**Rollback in one action:** set `InpEnableTrading=false`, or remove the EA. Open
positions are not closed by this switch — the EA stops managing them too, so close
them by hand or the stop you placed remains your only protection.

---

## 4a. Full "why is there no trade?" report

`docs/QSMC_WHY_NO_TRADES.md` lists every refusal path in the order worth checking,
with the literal Journal line for each and the single input that changes it. Start
there when a bar passes and nothing happens; this section is the short version.

## 4b. "The dashboard showed a zone but nothing traded"

The EA trades only a **published CORE signal**, not a drawn zone and not the
tactical preview mark. If a zone is visible and the EA did nothing, read the
journal: every refusal is one line, `[QSMC_AT] skip <bar>|<dir> - <reason>`
(spread, signal age, stop bounds, broker stops level, open-position cap, daily
guard, or `INERT`). If there is no `skip` line at all, the indicator published no
CORE signal for that bar — the dashboard's `NEEDS:` row names the blocker, see
§"A zone appeared on the chart but the system did not alert me" in
`docs/QSMC_DASHBOARD_CLARITY.md`.

## 5. What this does not do

- It does not add, change, or relax **any** entry gate, confluence rule, zone
  ranking or arbiter decision. Those live in the indicator, unchanged.
- It does not convert the indicator's strength or evidence scores into a
  probability. Sizing by risk % is risk control, not forecasting.
- It does not pyramide, average down, martingale, or widen a stop. Break-even is
  the only stop movement, and only toward the entry.
- It does not manage positions opened by hand or by another EA (different magic).
- It is not tested against your broker's execution: slippage, swap, commission,
  stop levels and requotes are broker facts. A requote produces
  `[QSMC_AT] ORDER FAILED retcode=...` and the signal is not retried blindly.
- A demo result is not a live result, and neither is a forecast.

## 6. Offline checks (no terminal needed)

```bash
python3 tools/test_autotrader_contract.py   # buffer map, switches, sizing arithmetic
python3 tools/check_release_gate.py         # G4 boundary + G8 how it ships
python3 tools/mql5_rules.py --quiet         # MQL5 dialect rules, including this unit
python3 tools/static_check.py               # balance / includes / forbidden constructs
```

`tools/mql5_rules.py` now also rejects invented converter names
(`LongToString`, `IntToString`, `ULongToString`, `BoolToString`,
`FloatToString`). MQL5 spells the integer converter `IntegerToString()`, which
already takes a `long`; `LongToString()` does not exist and produced 27 compile
errors on six lines of this EA when it was used.

All four run in CI. None of them is a compile: **F7 in MetaEditor** and one
`INERT` session are still required before the master switch is touched.
