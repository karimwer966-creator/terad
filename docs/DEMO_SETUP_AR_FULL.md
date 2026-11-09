# إعداد كامل جاهز للديمو — ملفَّي `set` وتفعيل كل شيء

**الملفان (مُولَّدان آلياً من الشفرة):**

| الملف | لمن | المحتوى |
|---|---|---|
| `presets/nadir2_PRODUCTION_XAUUSD.set` | المؤشر `nadir2` | **519 مُدخلاً** = كل مُدخلات المؤشر، منها 71 قيمة مُفعَّلة/مضبوطة |
| `presets/QSMC_AutoTrader_DEMO_0.10_200.set` | الإكسبرت | **51 مُدخلاً** = كل مُدخلات الـEA، منها 34 قيمة مضبوطة (0.10 لوت / 200 خسارة) |

> **مهم:** الملفان يُنتَجان من `tools/generate_set_presets.py` مباشرةً من تعريفات المُدخلات في الشفرة، والبوابة الآلية تفشل إن انحرف أي ملف عن الشفرة. لا تعدّلهما يدوياً — عدّل الشفرة أو جدول التجاوزات ثم أعد التوليد.

---

## 1) لماذا استبدلتُ بريست المؤشر القديم

بريست `nadir2_PRACTICAL_XAUUSD.set` كان **تالفاً فعلياً**، لا مجرد قديم. كل سطر فيه فقد ذيله:

| المُدخل | في الملف التالف | الصحيح (المُصرَّف) |
|---|---|---|
| `InpEMAFast` | **5** | 50 |
| `InpEMASlow` | **2** | 200 |
| `InpATRPeriod` / `InpADXPeriod` / `InpRSIPeriod` | **1** | 14 |
| `InpZoneLookback` | **1** | 150 |
| `InpLiquidityLookback` | **1** | 100 |
| `InpLiqToleranceATR` | **0** | 0.15 |
| `InpFVGMinSizeATR` | **0** | 0.2 |
| `InpMaxLiquidityKeep` | **4** | 40 |
| `InpOBMaxAgeBars` | **2** | 200 |
| مجموعات `"======...` | مقصوصة إلى `"======E` | أسماء كاملة |

`InpEMASlow=2` مع `InpEMAFast=5` يعني أن المؤشر كان يحسب اتجاهاً من شمعتين طويلتين بلا معنى، و`InpZoneLookback=1` يمنع تكوّن أي منطقة. **هذا وحده كافٍ لتفسير «لا إشارات»**. لذلك حُذف الملف القديم من المستودع، وحلّ محله ملف كامل مولَّد.

---

## 2) ما «فُعِّل» فعلياً في بريست المؤشر

**البوابات** — عبر مُدخل البروفايل نفسه (لا بتحريف العتبات):
```
InpGateProfile=QSMC_GATE_PRACTICAL
```
يفعّل الأرضيات الموثّقة: ثقة 60 / موثوقية 60 / RR 1.20 / وقف ≤ 6 ATR / بحث مرساة 120 شمعة.

**السلسلة السببية** (وهي التي كانت مخفية عنك):
```
InpEnableCausalInvariantChecks=true
InpPMIRunReplayAudit=true
InpInstitutionalSequence=true
```

**الوحدات السبع** بمفتاح واحد، كما صُمّمت (AUDIT-UX1):
```
InpEnableAllModules=true
```
تُفعّل PowerOf3 + SilverBullet + Wyckoff + PriceAction + MeanReversion + Confluence + RiskModel وتلميحاتها. وهي **طبقات عرض لا تُرخي بوابة** — أُبقيت منفصلة عن خط القرار عن قصد.

**طبقات الرصد** التي تجعل إعداد CORE قابلاً للوصول على الذهب:
```
InpUseZRE=true   InpUseRXN=true   InpUseSniperZoneEngine=true
InpUseQuantEngine=true   InpUseMasterVolumeProfile=true
InpUseHistoricalAnalysis=true   InpUseCandleIntelligence=true
InpUseInstitutionalBehavior=true   InpUseDirectionalScenarioEngine=true
InpUsePredictiveEngine=true
```

**التشخيص** — بلا هذه الأسطر يبقى «لا صفقات» بلا جواب:
```
InpShowGateAudit=true     InpGateAuditLogEveryBars=20
InpLogSignalDetails=true  InpSigLogCore=true
InpRuntimeNoLookaheadAudit=true   + كل self-tests
```

**مُعطَّل عن قصد** (وسُجّل صريحاً في الملف كي لا يُفهم كسهو):
`InpUseRetestLifecycle` (الدخول على الشمعة المغلقة المنشورة — وهو ما يفترضه `InpMaxSignalAgeBars=2` في الـEA)، `InpRequireMSSAfterSweep`، `InpBlockEquilibriumEntries`، `InpUseEMAVWAPConfluence`، وكل خيارات زحام الشارت (Fibo, debug, early-preview, push/sound).

---

## 3) الحدّ الذي يجب أن تعرفه: الـEA لا يقرأ بريست الشارت

الـEA ينشئ نسخته الخاصة من المؤشر بـ:
```
iCustom(_Symbol,_Period,InpIndicatorName)   // بلا قائمة مُدخلات
```
وهذا **عقد مقصود** (مُثبَّت في `test_autotrader_contract.py`) كي لا يُمرَّر مُدخل متسلل يتجاوز سلسلة البوابات. النتيجة العملية:

- بريست الشارت يغيّر **النسخة المرئية** فقط.
- الـEA يرى **الافتراضيات المُصرَّفة** في `nadir2.mq5`: بروفايل STRICT (75/80/1.50R)، `InpEnableAllModules=false`، `InpEnableCausalInvariantChecks=true`.

**أضفت لهذا سطراً في ربط الـEA** (`InpPinIndicatorDefaults=true`) يطبع الجرد صريحاً:
```
[QSMC_AT] INDICATOR INPUTS: this EA reads 'nadir2' on XAUUSD M15 with the indicator's COMPILED DEFAULTS ...
[QSMC_AT] INDICATOR INPUTS: ... InpGateProfile (compiled STRICT 75/80/1.50R vs PRACTICAL 60/60/1.20R) ...
```

### خياراك — اختر واحداً بوعي

**(أ) الأسلم (الأوصى به للديمو):** لا تحمّل بريست على المؤشر المرئي إطلاقاً. اترك المؤشر كما هو وأرفق الـEA. سترى حينها ما يراه الـEA بالضبط، وأي «لا إشارات» سيكون سببه الحقيقي في السجل لا تعارضاً بين نسختين.

**(ب) إن أردت أن ترى نفس ما يرى الـEA مع PRACTICAL:** غيّر **الافتراضيات في الشفرة** وأعد التصريف:
```
MQL5/Indicators/nadir2.mq5:1377   InpGateProfile = QSMC_GATE_STRICT  ->  QSMC_GATE_PRACTICAL
MQL5/Indicators/nadir2.mq5:907    InpEnableAllModules = false         ->  true
```
ثم `F7`. هذا يجعل النسخة المرئية والنسخة التي يقرأها الـEA متطابقتين. **لم أفعلها تلقائياً** لأنها تغيّر سلوك المنتج لكل مستخدم، وتحتاج قرارك — ولأنها تُخفّض عتبة الثقة عالمياً.

> تحذير: **لا** تحاول «تحسين» الأرقام بتحميل بريست مختلف على الشارت وتوقّع أن الـEA يتبعه. هو لا يتبعه، والسطر أعلاه في اللوج سيقول ذلك في كل ربط.

---

## 4) بريست الـEA — ما هو مُفعَّل

```
InpEnableTrading=true      InpDryRun=false        ← مُسلَّح ويُرسل فعلاً
InpDemoOnly=true           InpRealAccountConfirm= ← حساب حقيقي مرفوض دائماً
InpLotMode=QSMC_LOT_FIXED  InpFixedLots=0.10      ← 0.10 لوت لكل صفقة
InpFixedLotsMaxRiskPercent=6.00                   ← يرفض لوتاً وقفه > 6% من الإيكويتي
InpMaxDailyLossMoney=200.00                       ← حد الخسارة اليومي (عملة الحساب)
InpMaxDailyLossPercent=2.00                       ← احتياطي فقط
InpMaxAccountDrawdownPct=6.00                     ← فرامل ثانية مستقلة
InpStopAfterConsecLoss=2                          ← توقف بعد خسارتين متتاليتين
InpMaxTradesPerDay=3  InpMaxOpenPositions=1       ← 3 محاولات، صفقة واحدة
InpSessionStartHour=10  InpSessionEndHour=18      ← بتوقيت السيرفر
InpPinTimeframeMinutes=15                         ← يرفض أي فريم غير M15
InpMinRRAtFill=1.20                               ← إعادة فحص RR عند السعر الفعلي
InpResetBreakersAtInit=true                       ← يمسح day_base القديم عند التحميل
```

**إدارة الخروج بمدير واحد:** `InpTPLevel=QSMC_TP_LEVEL2` + `InpBreakEvenAtR=1.00`، وأُلغيت `InpPartialCloseAtR` وعطّلت سلالم TP بالنقاط (`InpUseTPPips=false` مع `MoveSL*` = false). مديران للخروج = سجلات متناقضة.

---

## 5) الترتيب التنفيذي

**أ. تصريف إلزامي** (لا مترجم MQL5 في بيئتي — أثبتُّ الشكل، لا التصريف):
1. `F7` على `MQL5/Indicators/nadir2.mq5` ⇒ 0 أخطاء.
2. `F7` على `MQL5/Experts/QSMC_AutoTrader.mq5` ⇒ 0 أخطاء.
3. `F7` على `MQL5/Scripts/QSMC_ResetGuards.mq5` (اختياري).

**ب. شارت نظيف:**
4. XAUUSD **M15**، بلا قوالب قديمة.
5. اسحب `nadir2.ex5` — وأدخل الإعدادات **يدوياً فقط إن اخترت الخيار (ب)**. وإلا فاتركه على افتراضياته.
6. انتظر ظهور اللوحات، وتأكد من غياب `[CausalInvariant] FAIL` متكرر.

**ج. الإكسبرت:**
7. اسحب `QSMC_AutoTrader.ex5` على نفس الشارت ⇒ Inputs ⇒ `Load` ⇒ `presets/QSMC_AutoTrader_DEMO_0.10_200.set` ⇒ ✅ Allow Algo Trading ⇒ OK.

**د. اقرأ سطر الربط قبل أي شيء:**
```
[QSMC_AT] ARMED PLAN | account ... (DEMO) | currency USD | equity ...
[QSMC_AT] ARMED PLAN | lot FIXED 0.10 (every trade) | fixed-lot guard: stop must cost <= 6.00% of equity = ...
[QSMC_AT] ARMED PLAN | daily stop: money stop 200.00 USD | trips at equity ...
[QSMC_AT] LOT CHECK: 0.10 lots is tradable on XAUUSD (min ... step ... max ...)
[QSMC_AT] INDICATOR INPUTS: ... COMPILED DEFAULTS ...
[QSMC_AT] state ARMED: demo account, live orders
```
أي `INIT REFUSED` / `TIMEFRAME PIN REFUSED` / `LOT CHECK` فاشل ⇒ **لا تتداول**؛ السبب مكتوب في السطر نفسه.

**هـ. بعد أول ربط:** أعِد `InpResetBreakersAtInit=false` واضغط `Save`.

---

## 6) تحقق سريع من نجاح التحميل

- في نافذة إعدادات المؤشر: `InpGateProfile` = `QSMC_GATE_PRACTICAL`، و`InpEnableAllModules` = `true`، و`InpMaxLiquidityKeep` = `40` (وليس 4)، و`InpEMASlow` = `200` (وليس 2). هذه الأربعة تكشف أي تحميل ناقص.
- في `Journal`: `[QSMC_INIT]` يعرض `Caps: Struct 30 Liq 40 FVG 25 Zones 20` و`Causal graph: max 160`.
- في `Experts`: سطر `GUARD ... loss_money=0.00/200.00 ... ARMED`.

---

## 7) الحدود

- **لم أُصرّف ولم أُشغّل MT5.** 43/43 فحصاً في البوابة تثبت الشكل والعقود فقط.
- **لا وعد بربحية.** 0.10 لوت على الذهب ≈ 10 دولار لكل دولار حركة؛ راجع حسابك مقابل ميزانية 200 قبل التفعيل.
- الحساب الحقيقي يحتاج `InpDemoOnly=false` **و** كتابة رقم الحساب في `InpRealAccountConfirm`، وهذا قرار منفصل موثّق في `docs/QSMC_GO_LIVE_RUNBOOK.md`.
- الخيار (ب) في القسم 3 (تغيير الافتراضيات) يغيّر سلوك المنتج لكل مستخدم — لم أفعله بلا قرارك.
