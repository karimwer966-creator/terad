# لماذا لا يفتح النظام صفقة؟ — تقرير كامل (QSMC v6.6.9)

هذا التقرير يجمع **كل** سبب يمكن أن يمنع صفقة، مرتباً بترتيب الفحص الصحيح:
الأسباب التي تُفحص أولاً هي التي تُفسّر ٩٠٪ من الحالات، وما بعدها حالات أندر.
كل سبب مكتوب بجانبه **السطر الحرفي** الذي تبحث عنه في تبويب `Experts` /
`Journal`، والإعداد الذي يغيّره.

> **قاعدة واحدة تختصر كل شيء:** المؤشر لا يفتح صفقات أبداً. الذي يفتحها هو
> `QSMC_AutoTrader.mq5` فقط، وهو يصل **معطّلاً**. ولن يفتح شيئاً إن لم يجد
> إشارة `CORE` منشورة **بعد إغلاق شمعة**. أي مشكلة في السلسلة تعني صفراً من
> الأوامر، بلا رسالة خطأ تلقائية.

---

## 0. الخلاصة في ثلاث نقاط

| # | السبب الأكثر احتمالاً | الدليل |
| --- | --- | --- |
| 1 | **الـ EA غير مُرفق أو غير مُترجم** — لا يوجد أي سطر `[QSMC_AT]` في Journal | تبويب Experts فارغ |
| 2 | **الـ EA مُرفق بإعداداته الافتراضية**: `InpEnableTrading=false` أو `InpDryRun=true` أو `InpDemoOnly=true` على حساب حقيقي | سطر `state INERT` / `state DRY RUN` / `state BLOCKED` |
| 3 | **لا توجد إشارة CORE** لأن المؤشر لم ينشر شيئاً (نسخة قديمة، أو بوابات التحكيم رفضت، أو الاتجاه `MIXED`) | صف `NEEDS:` في اللوحة يسمّي المانع |

---

## 0.1 الجديد في v6.6.10: الـ EA نفسه يقول لك أي بوابة رفضت

كان السطر القديم `CORE signals ...: 0` يثبت أن المؤشر لم ينشر شيئاً، لكنه لا
يقول **لماذا**. واللوحة تحتاج أن تنظر إليها، و`InpGateAuditLogEveryBars`
تحتاج أن تعدّل إعدادات المؤشر. الآن صار المؤشر ينشر نتيجة بواباته كمتغيّرات
عامة (`QSMC_DIAG_<الرمز>_<الفريم>_CORE`)، والـ EA يقرؤها ويطبعها في نبضته:

```text
[QSMC_AT] heartbeat: INERT | CORE signals in last 200 closed bars: 0 -> the indicator published NO CORE setup, ... | indicator verdict: RELIABILITY - score below InpMinReliability in the indicator | indicator funnel: bars 143 armed 6 confirmed 0 | last closed bar 2026.10.28 09:15
```

اقرأه كأربعة أسئلة:

| المقطع | السؤال الذي يجيب عنه |
| --- | --- |
| `indicator verdict: …` | أي بوابة رفضت آخر مرشّح |
| `indicator funnel: bars N armed A confirmed C` | هل وصلت السلسلة إلى `ARMED` أصلاً أم ماتت قبلها |
| `last closed bar …` | هل المؤشر يقيّم **هذا** الرمز وهذه الفريم فعلاً |
| `no diagnostic record for …` | البرنامجان ليسا على نفس المخطط/الرمز/الفريم، أو المؤشر غير مُترجم |

معاني الأكواد (نفس الجدول في الملفين، ويفحصه `tools/test_diag_bridge.py`):

| الكود | المعنى | المفتاح الذي يغيّره |
| --- | --- | --- |
| 0 | `NO_DATA` — لا شمعة مغلقة قُيِّمت بعد | انتظر إغلاق شمعة |
| 1 | `CORE_PUBLISHED` — نُشرت إشارة | إن لم تُفتح صفقة فالمشكلة في سطر `skip` |
| 2 / 3 | `SETUP_ARMED` / `SETUP_PENDING` — إعداد موجود وغير مؤكد | لا شيء؛ هذا التصميم |
| 10 / 11 | لا مرتكز بنية / سلسلة سببية ناقصة | السلسلة sweep → displacement → structure → zone لم تكتمل |
| 12–16 | لا كنس سيولة أو لا إزاحة أو لا زون مرتبط | السوق لم يُنتج التسلسل |
| 17 / 18 | الزون فشل في فحص الموقع أو السببية | — |
| 19 | ساق الكنس/الكسر ضعيفة | `InpDisplacementATR` |
| 20 / 21 / 22 | RR أقل من الحد / الوقف أوسع من الحد / الأهداف غير قابلة للترتيب | مدخلات الهندسة |
| 23 / 24 / 25 | الثقة أو الموثوقية أو التقييم تحت الحد | `InpMinConfidenceScore`, `InpMinReliability`, `InpMinGrade` |
| 26 | EMA200/VWAP يعارض الاتجاه | — |
| 27 | السبريد فوق `InpMaxSpreadPts` | `InpMaxSpreadPts` |
| 28 | سلسلة D1→M5 تحجب الاتجاه | `InpTopDownGateCore`, `InpRequireInstitutionalConfirm` |
| 29 | إعداد آخر يحتكر مسار التنفيذ | انتظر إبطاله أو انتهاءه |
| 30–33 | فيتو اتجاه / قائمة سوداء / دورة حياة / تراجع فرع | — |
| 34 | بوابة أخرى رفضت | `InpGateAuditLogEveryBars` للنص الحرفي |

ثلاث ملاحظات صادقة: الكود **للقراءة فقط** ولا يغيّر أي قرار؛ وهو يسمّي
**المانع الأكثر تكراراً في الجلسة** لا نبوءة عن الشمعة القادمة؛ و`1` لشمعة
واحدة لا يعني أن التالية ستنشر.

أما إن كان المؤشر ميتاً لا بطيئاً: صار الـ EA يفرّق بينهما. مقبض `iCustom`
صالح مع `BarsCalculated()` سالب لم يعد يُطبع «still warming up» إلى الأبد، بل
يقول إن النسخة موجودة لكنها **لا تحسب** — وهذه مشكلة مؤشر (مدخلات مرفوضة أو
تاريخ ناقص) لا مشكلة إشارة.

---

## 0.2 v6.6.11: المسافة لا العدّاد — كم كان المرشّح بعيداً عن المرور؟

`top blocker` عدّاد أصوات: يقول أي بوابة ترفض **أكثر**، ولا يقول أبداً إن كان
الحدّ مرتفعاً بنقطة واحدة أو أن السوق لم يُنتج النمط أصلاً. الفرق بين الاثنين
هو الفرق بين «خفّض الحدّ» و«لا تلمس شيئاً».

لذلك يقيس المؤشر الآن القيمة التي رآها كل فحص، ويطبع الـ EA الفرق:

```text
... | closest rejection: RELIABILITY short by 3.1 point(s) - the best candidate of this session was ONE input away from passing | best reached: conf 71, reliability 77, RR1 1.42, anchors 118 | profile window: 143 closed bars since attach
```

اقرأه هكذا:

| المقطع | المعنى |
| --- | --- |
| `closest rejection: RELIABILITY short by 3.1` | أقرب مرشّح سقط على الموثوقية بفارق 3.1 نقطة (`InpMinReliability`) |
| `closest rejection: none … the causal chain did not complete` | **لا حدّ كان السبب**: السلسلة السببية لم تُنتج صفقة. تخفيض أي عتبة هنا لن يفتح شيئاً |
| `best reached: conf 71, reliability 77, RR1 1.42, anchors 118` | أعلى قيمة وصلها أي مرشّح في الجلسة، وعدد المرتكزات التي فُحصت |
| `profile window: N closed bars` | حجم العيّنة؛ «أعلى قيمة» بلا عدد من الشموع ليس دليلاً |

نقطتان مهمتان:

- الفارق **لا يُحسب** إلا للبوابات الأربع التي هي عتبات رقمية: الثقة،
  الموثوقية، RR1، ومسافة الوقف. أمّا السلسلة السببية (كنس ← إزاحة ← بنية ←
  زون) فلا يُقال عنها «ناقصة بثلاث نقاط»، لأن ذلك سيكون كذباً رقمياً.
- البروفايل **قراءة فقط**: لا شيء فيه يدخل قراراً، ولو حُذف لما تغيّر أي
  إشارة منشورة. تغيير أي عتبة يبقى قرارك أنت، مكتوباً ومسجَّلاً — لا شيئاً
  يفعله الكود سراً.

---

## 0.3 v6.6.12: وضع عملي **باسمه** بدل تعديل الحدود خفية

إن قال المقياس في §0.2 إن الفارق نقطة أو نقطتان، فهناك مفتاح واحد صريح:

```text
InpGateProfile = QSMC_GATE_STRICT      (الافتراضي — كل حدّ كما كتبته)
InpGateProfile = QSMC_GATE_PRACTICAL   (اختياري — تخفيف خمس عتبات رقمية، معلن)
```

PRACTICAL يفعل **خمسة أشياء فقط**، وكل واحد منها يُطبع في Journal عند الإرفاق:

| المدخل | STRICT | PRACTICAL |
| --- | --- | --- |
| `InpMinConfidenceScore` | 75 | 60 |
| `InpMinReliability` | 80 | 60 |
| `InpMinRR1` | 1.50 | 1.20 |
| `InpMaxStopATR` | 4.0 | 6.0 |
| `InpAnchorSearchBars` | 60 | 120 |

وهو **لا** يصل إلى: السلسلة السببية، فحص الموقع، القائمة السوداء، بوابة
السجل غير القابل للتغيير، مفتاح الاتجاه العام، ولا إلى أي قاعدة مخاطر في
الـ EA (سقف 1%، الحجم، الوقف، الحد اليومي). ولا يشدّ عتبة كتبتها أنت أشدّ
منها: `MathMin/MathMax` تتحرّك في اتجاه التساهل فقط.

يقول سطر الافتتاح بالحرف:

```text
>>> QSMC v6.6.9 GATE PROFILE: PRACTICAL (opt-in) - the following entry thresholds are RELAXED:
>>>   reliability 80 -> 60  (InpMinReliability, floored at 60)
>>>   ...
>>>   UNCHANGED: causal chain, location, blacklist, journal gate, top-down switch, and every risk rule of the execution companion.
>>>   WARNING: this makes MORE trades possible, not better ones.
```

وسطر النبضة في الـ EA يعرض الوضع النشط: `indicator gate profile: PRACTICAL`.

**الحدّ الصادق:** هذا يجعل الصفقات **أكثر**، لا **أفضل**. وإن كان المانع
بنيوياً (أكواد 10–16: لا سلسلة سببية مكتملة) فهذا المفتاح لن يفتح شيئاً،
لأنه لا يمسّ السلسلة. اقرأ `closest rejection` أولاً ثم قرّر.

---

## 1. الطبقة الأولى: هل يوجد مُنفّذ أصلاً؟

| السبب | كيف تتأكد | الحل |
| --- | --- | --- |
| المؤشر يعمل وحده | لا سطر `[QSMC_AT]` في Journal عند إرفاق أي شيء | أرفق `QSMC_AutoTrader.mq5` |
| الـ EA لم يُترجم | في Navigator ← Expert Advisors لا تجد `QSMC_AutoTrader` | انسخه إلى `MQL5\Experts\` واضغط F7 |
| اسم المؤشر خاطئ | `could not create an instance of 'nadir2' (error …)` | `InpIndicatorName` = اسم الملف المترجم بالضبط، بلا `.mq5` |
| مدخلات غير صحيحة تمنع الإقلاع | `risk inputs out of range` / `stop bounds are inconsistent` / `InpMagic must be positive` | أصلح الأرقام؛ الـ EA يرفض الإقلاع بدل أن يعمل بقيم خطرة |
| `InpMagic` صفر أو مكرر مع EA آخر | `InpMagic must be positive` | استخدم رقماً فريداً لكل EA |

---

## 2. الطبقة الثانية: سطر الحالة عند الإرفاق

يُطبع مرة واحدة عند الإرفاق، وقبل وجود أي إشارة:

| السطر | المعنى | الحل |
| --- | --- | --- |
| `state INERT: no order can be sent` | `InpEnableTrading=false` (الافتراضي) | اجعله `true` |
| `state DRY RUN: orders are printed, never sent` | `InpDryRun=true` (الافتراضي) | اجعله `false` |
| `state BLOCKED: <السبب>` | كل شيء مسلّح لكن البيئة ترفض — انظر الجدول التالي | عالج السبب المذكور |
| `state ARMED: REAL account, live orders` | سيُرسل فعلاً عند أول إشارة | لا شيء |

### تفصيل `state BLOCKED`

| السبب الحرفي | ما يجب فعله |
| --- | --- |
| `the terminal's Algo Trading button is OFF` | زر **Algo Trading** في شريط MT5 |
| `expert trading is disabled for this EA` | خصائص الـ EA ← تبويب Common ← *Allow Algo Trading* |
| `the account is not allowed to trade (broker side)` | الحساب للقراءة فقط أو موقوف |
| `the server forbids expert trading on this account` | تفعيل من الوسيط |
| `trading is disabled on this symbol` | الرمز مغلق للتداول |
| `this symbol is close-only right now` | إغلاق فقط (قرب نهاية الجلسة/عطلة) |
| `this symbol is sell-only / buy-only right now` | قيد اتجاه على الرمز |
| `real account and InpDemoOnly=true` | **الحالة الأكثر شيوعاً على حساب حقيقي**: `InpDemoOnly=false` |
| `real account: set InpRealAccountConfirm to this account number (…)` | اكتب رقم حسابك في `InpRealAccountConfirm` |

ملاحظة مقصودة: الحساب الحقيقي يحتاج **مفتاحين** لا واحداً
(`InpDemoOnly=false` **و** رقم الحساب)، حتى لا يسلّح قالب محفوظ من حساب ديمو
مالاً حقيقياً.

---

## 3. الطبقة الثالثة: لا توجد إشارة CORE أصلاً

إن كان سطرك `state ARMED` ومع ذلك لا صفقة، فالمشكلة في الإشارة لا في التنفيذ.
الـ EA يقرأ **مخازن المؤشر 7–12** فقط، وهي تُملأ عند **إغلاق** شمعة بإشارة
`CORE` منشورة.

| السبب | كيف تتأكد |
| --- | --- |
| تصدير المخازن مُعطّل | `InpExportSignalBuffers=true` في المؤشر (وهو الافتراضي) |
| المؤشر لم يُضَف على المخطط | المخازن تأتي من نسخة الـ EA الخاصة عبر `iCustom`، لكن يجب أن يكون المؤشر مُترجماً وموجوداً |
| المؤشر ما زال يحمّل التاريخ | `CopyBuffer` يعيد أقل من المطلوب؛ ينتظر الـ EA الشمعة التالية |
| بوابات طبقة التحكيم رفضت | صف `NEEDS:` في اللوحة يعرض `arbiter top blocker: …` |
| الاتجاه متعارض | اللوحة تعرض `LOCAL READY / DIRECTION MIXED - WAIT` |
| لا مستوى MTF مُتحقق | `BEST LEVEL: none | waiting for validated MTF confluence` |
| نسخة قديمة على المخطط | أول سطر Journal ليس `[QSMC_ARB] v6.6.9 arbitration layer ON` |
| معاينة الشمعة الحالية فقط | اللوحة تقول `TOUCHED ON THE LIVE CANDLE only` — لا تنبيه ولا صفقة قبل الإغلاق |

**الفرق الجوهري:** منطقة مرسومة ≠ إشارة. المنطقة تُرسم عندما تُكتشف السيولة؛
الإشارة تُنشر فقط بعد ارتداد مؤكد على شمعة مغلقة يجتاز كل البوابات.

---

## 4. الطبقة الرابعة: إشارة موجودة والـ EA تجاهلها

كل سبب هنا يُطبع سطراً واحداً: `[QSMC_AT] skip <bar>|<dir> - <السبب>`.

| السطر الحرفي | المعنى | الإعداد |
| --- | --- | --- |
| `signal has no stop` / `signal has no target` | هندسة ناقصة في الإشارة | لا حل من الـ EA؛ رفض دائم |
| `BUY geometry is not (sl<entry<tp)` | الوقف/الهدف في الجهة الخاطئة | رفض دائم |
| `stop is N pts, under the minimum` | وقف أقرب من الحد | `InpMinStopPoints` |
| `stop is N pts, over the maximum` | وقف أوسع من الحد | `InpMaxStopPoints` |
| `price already at/below the BUY stop` | السعر تجاوز الوقف قبل التنفيذ | لا تدخّل |
| `... target already reached - not chasing` | الهدف تحقق قبل الدخول | لا مطاردة، بالتصميم |
| `spread above N pts` | السبريد أوسع من الحد | `InpMaxSpreadPoints` |
| `daily loss guard is active` | خسارة اليوم بلغت الحد | `InpMaxDailyLossPercent` |
| `already N position(s) open` | عدد الصفقات بلغ السقف | `InpMaxOpenPositions` |
| `opposite position of this magic is open` | صفقة معاكسة مفتوحة | `InpCloseOnOpposite` |
| `broker stops level rejects this SL/TP` | الوسيط يمنع SL/TP قريباً جداً | لا حل من الـ EA |
| `volume resolves to 0 (risk cap, margin or broker minimum)` | الحجم أقل من حد الوسيط أو الهامش لا يكفي | ارفع `InpRiskPercent` |
| `no price yet` | لا سعر (سوق مغلق/لا تيكات) | انتظر |
| لا سطر skip إطلاقاً + لا `DRY RUN` | الـ EA لا يرى إشارة | عُد إلى §3 |

### لماذا الحجم صفر؟

الحجم = المخاطرة ÷ (مسافة الوقف × قيمة التك)، مقرّباً **للأسفل** إلى خطوة
الوسيط. إن كان الناتج أقل من الحد الأدنى للعقد، فالجواب «لا صفقة» وليس
«الحد الأدنى» — لأن استخدام الحد الأدنى يضاعف المخاطرة بصمت.

حساب سريع (ذهب، قيمة النقطة ≈ 1$ لكل 0.01 لوت لكل 0.01$ حركة):

| رأس المال | المخاطرة | الوقف | الناتج |
| --- | --- | --- | --- |
| 10,000$ | 0.25% = 25$ | 1.00$ | 0.25 لوت |
| 1,000$ | 0.10% = 1$ | 1.00$ | 0.01 لوت (الحد الأدنى) |
| 500$ | 0.10% = 0.50$ | 2.00$ | **0 → لا صفقة** |

---

## 5. الطبقة الخامسة: أُرسل الأمر وفشل

| السطر | التفسير |
| --- | --- |
| `ORDER FAILED retcode=… <الوصف>` | رفض من الوسيط: `Invalid stops`، `No money`، `Requote`، `Market closed`، `Invalid volume` |
| `closed opposite position #…` | نجح إغلاق الصفقة المعاكسة |
| `stop moved to break-even on #…` | نقل الوقف إلى الدخول عند +1R (التعديل الوحيد المسموح) |

الـ EA لا يعيد المحاولة بشكل أعمى بعد فشل الأمر؛ ينتظر إشارة جديدة.

---

## 6. ما لا يفعله النظام أبداً (وليس عطلاً)

- لا يفتح صفقة بلا وقف.
- لا يفتح على شمعة غير مغلقة.
- لا يعزّز خسارة، ولا يضاعف العقود، ولا يوسّع وقفاً.
- لا يتداول إشارة أقدم من `InpMaxSignalAgeBars`.
- لا يتداول إشارة وُجدت قبل إرفاقه.
- لا يفتح صفقة ثانية إن كان السقف مكتملاً.
- لا يفتح صفقة بعد تجاوز حد الخسارة اليومي.

كل واحدة من هذه **قرار تصميم**، لا خطأ برمجي.

---

## 7. خطوات التشخيص في خمس دقائق

0. **اقرأ سطر النبضة** `[QSMC_AT] heartbeat:` (يُطبع تلقائياً عند الإرفاق ثم كل
   `InpHeartbeatSeconds`=300 ثانية، ولا يرسل أي أمر). سطر واحد يحسم أصل المشكلة:
   - `CORE signals in last 200 closed bars: 0 -> the indicator published NO CORE
     setup` → المؤشر لم ينشر أي إشارة CORE أصلًا؛ المشكلة في بوابات المؤشر لا في
     الـ EA. الحل في الخطوة 4 (صف `NEEDS:`) وليس في أي مفتاح من مفاتيح الـ EA.
   - `CORE signals …: N` مع `last skip: …` → النقل سليم والـ EA يرفض لسبب مكتوب
     بالحرف (سبريد/حجم/وقف/سقف صفقات…)؛ عالج ذلك السبب تحديداً.
   - `handle INVALID` → المؤشر غير مترجم أو ليس في مجلد `MQL5\Indicators`.
   - `still warming up` → المؤشر ما زال يحمّل التاريخ؛ انتظر النبضة التالية.
1. **أول سطر** في Journal عند الإرفاق: هل هو `[QSMC_AT] QSMC v6.69 execution companion ON`؟
   إن لا → الـ EA غير مُرفق أو لم يُترجم.
2. **سطر الحالة**: `INERT` / `DRY RUN` / `BLOCKED` / `ARMED`. لا تنتقل قبل
   أن يصبح `ARMED` أو `DRY RUN`.
3. **مرّر إلى DRY RUN أولاً** (`InpEnableTrading=true`، `InpDryRun=true`).
   إن ظهر سطر `DRY RUN BUY …` فالتنفيذ سليم والمشكلة في المفتاح المتبقي فقط.
4. **إن لم يظهر شيء أبداً** → لا إشارة. افتح اللوحة واقرأ صف `NEEDS:`:
   سيقول لك بالحرف أي بوابة رفضت. ولتفصيل أعمق فعّل في المؤشر
   `InpGateAuditLogEveryBars=50` فيطبع `[GateAudit] … top blocker: …`.
5. **تأكد من الإصدار**: `[QSMC_ARB] v6.6.9` في Journal، وليس رقماً أقدم.

> النبضة للقراءة فقط: تنسخ المخزن 7 وتطبع، لا تلمس بوابة ولا أمراً ولا صفقة.
> إيقافها: `InpHeartbeatSeconds=0`.

---

## 8. حالة جهازك تحديداً

من الصور التي أرسلتها:

- نص اللوحة `CONTEXT: UNVALIDATED (… M15 disabled) - no weight or tiers` و
  `SCORE: n/a (no authoritative instance)` **غير موجود في هذا المستودع ولا في
  تاريخه**. النسخة العاملة عندك ليست هذه.
- الصفقة الظاهرة (`buy 0.01 @ 4046.54`) ليست من هذا النظام؛ المؤشر لا يستطيع
  إرسال أمر.
- لذلك لن يعمل الـ EA عندك قبل استبدال الملفات و**F7**، لأن هذه النسخة لا تنشر
  إشارة `CORE` بالصيغة التي يقرأها.

**الترتيب الصحيح:** انسخ `nadir2.mq5` + ١٨ ملف `Include/QSMC` +
`QSMC_AutoTrader.mq5` → F7 على المؤشر ثم على الـ EA → أعد إرفاق المؤشر →
تأكد `v6.6.9` → شغّل `DRY RUN` ساعة → ثم `InpDemoOnly=false` +
`InpRealAccountConfirm=<رقم حسابك>` → ثم راقب أول صفقة.

---

## 9. جدول مرجعي سريع

| الحالة | السبب | مفتاح واحد للتغيير |
| --- | --- | --- |
| `heartbeat: … CORE signals …: 0` | المؤشر لا ينشر CORE (بواباته ترفض) | اقرأ `indicator verdict:` في نفس السطر (جدول §0.1) أو `InpGateAuditLogEveryBars` |
| `indicator verdict: <كود>` | البوابة التي رفضت آخر مرشّح | الجدول في §0.1 |
| `indicator funnel: … armed 0` | السلسلة لم تصل إلى إعداد مسلّح | مشكلة في توليد الإعداد لا في الـ EA |
| `indicator verdict: no diagnostic record` | المؤشر لا يقيّم هذا الرمز/الفريم | نفس المخطط، نفس الرمز، F7 على nadir2 |
| `heartbeat: … last skip: …` | الإشارة موجودة والـ EA يرفض | عالج السبب المذكور في السطر |
| `heartbeat: handle INVALID` | المؤشر غير مترجم/في المكان الخطأ | F7 على `nadir2` داخل `MQL5\Indicators` |
| لا شيء في Journal | EA غير مُرفق | أرفقه |
| `INERT` | معطّل | `InpEnableTrading=true` |
| `DRY RUN` | لا يرسل | `InpDryRun=false` |
| `BLOCKED: … InpDemoOnly` | حساب حقيقي | `InpDemoOnly=false` |
| `BLOCKED: … InpRealAccountConfirm` | رقم الحساب | اكتبه |
| `BLOCKED: … Algo Trading` | زر التداول | شغّله |
| `skip … spread` | سبريد | `InpMaxSpreadPoints` |
| `skip … volume resolves to 0` | الحجم | `InpRiskPercent` |
| `skip … position(s) open` | السقف | `InpMaxOpenPositions` |
| لا سطر skip | لا إشارة | صف `NEEDS:` في اللوحة |
| `ORDER FAILED` | رفض الوسيط | راجع retcode |

هذا التقرير وصف لسلوك الكود، وليس وعداً بربح. لا شيء في هذا المستودع يجعل
الاستراتيجية مربحة، والفحوص الثابتة لا تُغني عن **F7** ولا عن تجربة ديمو.
