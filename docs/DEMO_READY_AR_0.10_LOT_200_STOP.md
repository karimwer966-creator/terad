# جاهز للإنتاج على حساب ديمو — 0.10 لوت / حد خسارة يومي 200

**البريست الجاهز:** `presets/QSMC_AutoTrader_DEMO_PRODUCTION_0.10_200.set`
**تاريخ الإعداد:** 06/11/2026 · **الرمز المقصود:** XAUUSD · **الفريم المقترح:** M15

---

## 1) ما طلبته وما نُفِّذ فعلاً

| المطلوب | الحالة | كيف نُفِّذ |
|---|---|---|
| «يعمل على **أي حساب**» | ✅ | أُزيلت السقوف المطلقة التي كانت تمنع أي خطة حقيقية: كانت `0.25% / 1.00% / 3.00%` فتصادر أي إعداد 2% أو 6% **بصمت** على أي حساب. صارت `5% / 10% / 20%`—سقف أمان خارجي فقط |
| **حد خسارة يومي 200** | ✅ | مُدخل جديد `InpMaxDailyLossMoney=200` بالعملة الحقيقية للحساب. **يتقدّم** على النسبة، ومقيَّد بسقف HARD (10% من خط أساس اليوم) كي لا يُعطّله رقم ضخم بالخطأ |
| **لوت الصفقة 0.1** | ✅ | `InpLotMode=FIXED` + `InpFixedLots=0.10`، مع حارس `InpFixedLotsMaxRiskPercent=6%` يرفض اللوت إن كان وقفه أغلى من ذلك (بدل أن يخسر بصمت) |
| **جاهز للديمو** | ✅ | البريست **مُسلَّح فعلاً** (`InpEnableTrading=true` + `InpDryRun=false`) ومع ذلك يرفض أي حساب **حقيقي** (`InpDemoOnly=true`) |

---

## 2) ثلاث نقاط يجب أن تعرفها قبل التشغيل

**أ) «200» بالعملة التي يعلنها الوسيط — وليست بالدولار تلقائياً.**
سطر الربط يطبعها صريحاً:
```
[QSMC_AT] ARMED PLAN | account 12345678 (DEMO) | currency USD | equity 5000.00 ...
[QSMC_AT] ARMED PLAN | daily stop: money stop 200.00 USD | trips at equity 4800.00
```
إن ظهرت عملة أخرى (EUR مثلاً)، فإن 200 تعني 200 يورو. عدّل الرقم إن كنت تقصد رقماً آخر — **لا تفترض**.

**ب) 0.10 لوت على XAUUSD ≈ 10 دولار لكل دولار حركة سعر.**
وقف نموذجي 2–5 دولار = مخاطرة 20–50 دولاراً **للصفقة الواحدة**، أي 10–25% من ميزانية 200 اليومية. لذلك:
- على حساب 500 دولار: ربح/خسارة 20–50 دولاراً لكل صفقة = 4–10% من الحساب. **ثقيل جداً**؛ الحارس سيرفض الصفقة إن تجاوز وقفها 6% من الإيكويتي (30 دولاراً على 500) ويطبع `FIXED_LOT_TOO_BIG`.
- على حساب 5,000 دولار: 20–50 دولاراً = 0.4–1.0% — معقول.
- على حساب 10,000 دولار أو أكثر: مريح.

إن رفض الحارس صفقات كثيرة فالمشكلة في **حجم اللوت مقابل الحساب**، لا في المؤشر: أنزل `InpFixedLots` أو استخدم `InpLotMode=QSMC_LOT_RISK_PERCENT` مع `InpRiskPercent=0.75`.

**ج) حد 200 يتطلب مسافة من البداية.**
الحارس يقيس من **إيكويتي بداية اليوم**. إن كان حسابك قد خسر أصلاً قبل التشغيل، فالخط يُحسب من الآن — وبريست الديمو يمسح الحالة القديمة عند التحميل (`InpResetBreakersAtInit=true`) كي لا يتكرر سيناريو `day_base=5680.64` الذي حظر يومك السابق كاملاً. بعد أول ربط ناجح **أعِد هذا المُدخل إلى `false`**.

---

## 3) خطوات التركيب (بالترتيب)

**A. التصريف — لا تتجاوزها**
1. `F7` على `MQL5/Indicators/nadir2.mq5` ⇒ صفر أخطاء.
2. `F7` على `MQL5/Experts/QSMC_AutoTrader.mq5` ⇒ صفر أخطاء.
3. `F7` على `MQL5/Scripts/QSMC_ResetGuards.mq5` (أداة التشخيص، اختيارية لكن مفيدة).

> لا يوجد مترجم MQL5 في بيئتي؛ كل ما أثبتّه هو عقود مصدرية (42/42 فحصاً). **الفشل المحتمل الوحيد هو خطأ تصريف**، ولهذا خطوة F7 إلزامية قبل أي ربط.

**B. المؤشر أولاً**
4. افتح شارت **XAUUSD M15** نظيفاً (لا مؤشرات أخرى، لا قوالب قديمة).
5. اسحب `nadir2.ex5` ⇒ Inputs ⇒ `Load` ⇒ `presets/nadir2_PRACTICAL_XAUUSD.set`.
6. انتظر 10–30 ثانية وتحقق من `Journal`: سطور `v6.6.20` وبصمة `input_hash`، وعدم وجود `[CausalInvariant] FAIL` متكرر.

**C. الإكسبرت بعده، على نفس الشارت**
7. اسحب `QSMC_AutoTrader.ex5` على **نفس** الشارت ⇒ Inputs ⇒ `Load` ⇒ `presets/QSMC_AutoTrader_DEMO_PRODUCTION_0.10_200.set`.
8. تأكد من ✅ **Allow Algo Trading** قبل OK.

**D. تحقق من سطر الربط (هذه هي البوابة الحقيقية)**
```
[QSMC_AT] ARMED PLAN | account ... (DEMO) | currency USD | equity ...
[QSMC_AT] ARMED PLAN | lot FIXED 0.10 (every trade) | fixed-lot guard: stop must cost <= 6.00% of equity = 300.00 USD
[QSMC_AT] ARMED PLAN | daily stop: money stop 200.00 USD | trips at equity ... (money stop wins ... HARD 10.00%)
[QSMC_AT] ARMED PLAN | entry budget 3 trade(s)/day | max 1 open | session 10:00-18:00 server
[QSMC_AT] LOT CHECK: 0.10 lots is tradable on XAUUSD (min 0.01 step 0.01 max 100.00)
[QSMC_AT] state ARMED: demo account, live orders
```
إن ظهر `INIT REFUSED` أو `TIMEFRAME PIN REFUSED` أو `LOT CHECK` فاشل ⇒ **لا تتداول**، واقرأ السبب في السطر نفسه.

**E. بعد أول يوم**
9. أعِد `InpResetBreakersAtInit=false` واحفظ `Save` في البريست.
10. راقب سطر `heartbeat`:
```
GUARD day_base=... sess_base=... bal=... eq=... daily_dd=0.40%/2.00% loss_money=20.00/200.00 USD floor=4800.00 ... ARMED
```
`loss_money` هنا هو عدّاد خسارتك اليومية الحقيقي، و`floor` هو الإيكويتي الذي سيتوقف عنده.

---

## 4) ماذا يعني كل رقم في البريست

| المُدخل | القيمة | الأثر |
|---|---|---|
| `InpEnableTrading` / `InpDryRun` | `true` / `false` | مُسلَّح ويُرسل فعلاً |
| `InpDemoOnly` | `true` | حساب حقيقي مرفوض مهما كان الرقم السري |
| `InpLotMode` / `InpFixedLots` | `FIXED` / `0.10` | لوت ثابت لكل صفقة |
| `InpFixedLotsMaxRiskPercent` | `6.00` | يرفض صفقة وقفها > 6% من الإيكويتي |
| `InpMaxDailyLossMoney` | `200.00` | التوقف عند −200 عملة |
| `InpMaxDailyLossPercent` | `2.00` | يُستخدم فقط إذا صفّرت المبلغ |
| `InpMaxAccountDrawdownPct` | `6.00` | مفتاح ثانٍ: توقف عند −6% من إيكويتي بداية الجلسة |
| `InpStopAfterConsecLoss` | `2` | توقف بعد خسارتين متتاليتين |
| `InpMaxTradesPerDay` / `InpMaxOpenPositions` | `3` / `1` | 3 محاولات، صفقة واحدة مفتوحة |
| `InpSessionStartHour` / `End` | `10` / `18` | بتوقيت **السيرفر** كما في سجلك |
| `InpPinTimeframeMinutes` | `15` | يرفض أي فريم غير M15 (يمنع دوران M1→H4) |
| `InpMinRRAtFill` | `1.20` | يرفض الدخول إن تدهورت النسبة عند السعر الفعلي |
| `InpResetBreakersAtInit` | `true` | امسح الحالة القديمة عند التحميل، ثم أعده `false` |

ملاحظة: `InpTPLevel=QSMC_TP_LEVEL2` مع وقف متحرك على R1، ولذلك أُبقيت إدارة الخروج على **مدير واحد** فقط (أُلغيت `InpPartialCloseAtR`، وأُوقفت سلالم TP بالنقاط). مديران للخروج = تناقض في السجلات.

---

## 5) لو تكرر «لا صفقات»

راجع بالترتيب، فكل بند له سطر في اللوج:
1. `CORE signals in last 200 closed bars: 0` ⇒ المشكلة في **المؤشر** لا الـEA. شغّل `InpGateAuditLogEveryBars=20` في المؤشر واقرأ `top blocker`، وارجع إلى `docs/REPORT_AR_2026-11-06_CAUSAL_CHAIN.md`.
2. `FIXED_LOT_TOO_BIG` ⇒ اللوت كبير على حسابك (انظر 2‑ب).
3. `DAY_BLOCKED` مع `day_base` شاذ ⇒ شغّل `MQL5/Scripts/QSMC_ResetGuards.mq5` (يعرض القائمة أولاً بلا حذف).
4. `chain: no confirmed liquidity sweep behind the displacement` ⇒ نقص بنية سوقية حقيقي؛ وسّع `InpSweepToStructureMaxBars` من 8 إلى 12 بدل تعطيل البوابات.
5. `TIMEFRAME PIN REFUSED` ⇒ الشارت ليس M15.

---

## 6) حدود هذه الجاهزية

- **لم أُصرّف** ولم أُشغّل MT5 هنا: العقد المصري (42/42) يثبت الشكل لا السلوك وقت التشغيل.
- **لا وعد بربحية.** هذه إصلاحات صحة بيانات وضبط مخاطر. 0.10 لوت على XAUUSD حجم كبير على حسابات صغيرة، والأرقام في القسم 2‑ب صريحة في ذلك.
- الحساب الحقيقي يبقى محكوماً بـ `docs/QSMC_GO_LIVE_RUNBOOK.md`، ويتطلب `InpDemoOnly=false` **و** كتابة رقم الحساب في `InpRealAccountConfirm` — لا يكفي تحميل بريست.
- الفحص الحقيقي الوحيد المتبقي: يوم تداول كامل على الديمو مع مراقبة `heartbeat` وسجل الإشارات.
