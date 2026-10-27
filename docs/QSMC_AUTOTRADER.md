# QSMC v6.6.8 — the execution companion (`QSMC_AutoTrader.mq5`)

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

`OnTimer` exists because a quiet symbol can go minutes without a tick. It reads
the same closed-bar buffers, so it cannot create a signal that `OnTick` would not
see.

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
   [QSMC_AT] QSMC v6.66 execution companion ON | XAUUSD PERIOD_M15 | magic 20261027 | mode RISK% risk 0.25% | tp 1 | break-even 1.00R | INERT | demo-only | closed-bar signals only, no martingale, no stop widening
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
