# تثبيت QSMC v6.6.20 للإنتاج — خطوة بخطوة

**الحالة الآلية:** `OFFLINE GO` من `python3 tools/check_production_ready.py`، و`GO (0 warnings)` من `python3 tools/check_release_gate.py`.

**ما لا يثبته هذا تلقائيًا:** ترجمة MetaEditor (F7)، الربحية، أو زمن شبكة الوسيط. لا يوجد MetaEditor في بيئة البناء. لذلك لا تنتقل إلى حساب حقيقي قبل إكمال سلّم demo في `docs/QSMC_GO_LIVE_RUNBOOK.md`.

---

## 1. ما الذي تنسخه؟

من حزمة الإنتاج، انسخ المجلدات كما هي إلى **Data Folder** في MT5:

```text
MQL5/Indicators/nadir2.mq5
MQL5/Indicators/QSMC_ScannerProbe.mq5        (اختياري)
MQL5/Include/QSMC/*.mqh                     (23 ملفًا)
MQL5/Scripts/QSMC_ArbiterTest.mq5
MQL5/Experts/QSMC_AutoTrader.mq5            (اختياري للتنفيذ)
MQL5/Experts/KLJ_DataFeeder.mq5             (اختياري، يصل معطلًا)
```

افتح MT5 → `File` → `Open Data Folder`. أغلق MT5/MetaEditor أثناء النسخ إن كانت ملفات قديمة مقفلة.

**مهم:** لا تترك نسختين من `nadir2.mq5` أو `nadir2.ex5` بأسماء/مجلدات مختلفة. النسخة القديمة هي أشهر سبب لبقاء الشعار القديم أو استمرار التأخير.

---

## 2. الترجمة F7 — بالترتيب

في MetaEditor، افتح كل ملف واضغط **F7**، واقرأ النتيجة:

1. `MQL5/Indicators/nadir2.mq5`
2. `MQL5/Scripts/QSMC_ArbiterTest.mq5`
3. `MQL5/Indicators/QSMC_ScannerProbe.mq5` إن استخدمته
4. `MQL5/Experts/KLJ_DataFeeder.mq5` إن استخدمته
5. `MQL5/Experts/QSMC_AutoTrader.mq5` إن أردت التنفيذ

المطلوب: **0 errors**. لا تكمل إذا ظهر خطأ. التحذير الوحيد المقبول عادة هو عدم وجود plot للماسح لأنه لا يرسم.

بعد الترجمة، تأكد أن تاريخ `nadir2.ex5` و `QSMC_AutoTrader.ex5` جديد.

---

## 3. تشغيل المؤشر المرئي

1. افتح شارت XAUUSD على الفريم الذي تستخدمه.
2. أزل أي `nadir2` قديم من الشارت.
3. أضف `nadir2` الجديد.
4. حمّل الإعداد الاستعراضي:
   - `presets/QSMC_v6.6.20_production_chart.set`
   - هذا الإعداد **عرضي فقط** ولا يغيّر بوابات الدخول.
5. في Experts/Journal يجب أن ترى:

```text
[QSMC_ARB] v6.6.20 arbitration layer ON | preset ...
```

إذا رأيت `v6.6.19` أو أقدم، فأنت ما زلت تشغّل نسخة قديمة. أوقف كل شيء وأعد النسخ/الترجمة.

---

## 4. تشغيل EA بأمان

الـ EA يصل الآن (2026-11-09) **مُسلَّحًا على حساب demo** بلا أي `.set`:

```text
InpEnableTrading=true
InpDryRun=false
InpDemoOnly=true
InpRealAccountConfirm=      (فارغ)
InpPinTimeframeMinutes=15   (شارت M15 فقط)
```

أي أنه **يرسل أوامر حقيقية على demo** من أول إرفاق. الحساب الحقيقي يُرفض في
`OnInit` (`INIT_FAILED`) ولا يمكن تسليحه إلا بـ `InpDemoOnly=false` **وكتابة رقم
الحساب** في `InpRealAccountConfirm`. القواطع كلها تعمل كما هي: خسارة يومية
0.50%، سحب حساب 3.00% من أعلى حقوق ملكية، خسارتان متتاليتان، 3 دخولات/يوم.

إن أردت سلّم المشاهدة القديم (خامل ثم DRY RUN) فحمّل
`presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set`: يعطي نفس الإعداد مع
`InpEnableTrading=false` و`InpDryRun=true`.

1. حمّل:
   - `presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set`
2. أرفق `QSMC_AutoTrader` على نفس الرمز/الفريم.
3. ابحث عن:

```text
[QSMC_AT] QSMC v6.620 execution companion ON
[QSMC_AT] iCustom handshake OK ... silent EA_READER
```

إذا لم يظهر `silent EA_READER` أو ظهر fallback متكرر، أزل الـEA، أعد ترجمة `nadir2.mq5`، ثم أعد الإرفاق.

**قاعدة صارمة:** الـEA يقرأ نسخة `iCustom` خاصة تستخدم **افتراضيات المؤشر**، لا إعدادات الشارت المرئي. لا تغيّر مدخلات القرار على الشارت وتعتبر أن الـEA يتداولها.إما أبقِ الافتراضيات، أو افصل شارت المراقبة عن شارت التنفيذ واعتبر لوحة الشارت استشارية.

---

## 5. تشخيص تأخير Bid / استهلاك الموارد

لتشخيص التأخير، حمّل على النسخة المرئية فقط:

```text
presets/QSMC_v6.6.20_latency_diagnosis.set
```

ثم اجمع عدة أسطر:

```text
[QSMC_PERF] role=VISUAL ... calc_avg_us=... calc_max_us=... bar_max_us=... quote_age_ms=...
```

التفسير:

- `calc_avg_us` / `calc_max_us` منخفضان، لكن `quote_age_ms` كبير أو خط Bid متأخر: المشكلة الأقرب تغذية الأسعار/الشبكة/رسم الطرفية، وليست حساب المؤشر.
- `calc_max_us` أو `bar_max_us` مرتفعان جدًا: أرسل الأسطر مع سجل Experts لتحديد المسار الثقيل.
- هذا المقياس يقيس جسم `OnCalculate` فقط، لا زمن أمر الوسيط ولا زمن رسم MT5 نفسه.

---

## 5b. قراءة سجل الإقلاع/الإيقاف في v6.6.20

- شعار المؤشر يقول `LIVE MARKET | ANALYSIS ONLY (no orders)`؛ هذا لا يعني أن الـEA أرسل أمرًا. حالة التنفيذ تُقرأ من سطر الـEA نفسه (`INERT` / `DRY RUN` / `BLOCKED`).
- انتظار ATR/ADX الأولي قد يظهر كـ `not ready` أو `partial history` مع دور النسخة والخطأ وعدد القيم المحسوبة. ابحث بعدها عن `READY`. إذا تكرر `WARNING` بعد نفاد المحاولات، أرسل السطر كاملًا ولا تغيّر بوابات الدخول عشوائيًا.
- القارئ الخاص يطبع هويته وأخطاء الفشل، لكن لا يكرر لافتات PASS/الإيقاف المرئية. الاختبارات الذاتية ما زالت تعمل.
- عند الإزالة، الميزان المهم هو `owned remaining 0` وتوازن alloc/free. عدّادات `created/deleted` عمرية وقد تختلف إذا حذف المضيف كائنًا أولًا.
- `BLOCKED` من حارس الخسارة اليومية حالة سلامة محفوظة. لا تمسحها تلقائيًا؛ راجع `docs/QSMC_RUNTIME_LOG_REVIEW_AR.md` وrunbook الإيقاف/التراجع.

---

## 6. الملاحظة قبل الحقيقي

شغّل على demo أو paper على الأقل دورة كاملة من الإشارات/الـheartbeats، وراقب:

- لا توجد أخطاء ترجمة أو runtime.
- الشعار v6.6.20.
- handshake صحيح.
- لا يوجد تسريب كائنات/مقابض عند الإزالة.
- قواطعDaily/DD/consecutive تعمل كما هو موثق.
- لا أوامر على حساب حقيقي أبدًا: الـEA يرفض الحساب الحقيقي في `OnInit` ما لم تكتب رقمه في `InpRealAccountConfirm`.

الحقيقي يتطلب قرارًا يدويًا عبر `docs/QSMC_GO_LIVE_RUNBOOK.md`، وليس مجرد تحميل preset.

---

## 7. rollback سريع

إذا ظهر سلوك غير متوقع:

1. أوقف Algo Trading.
2. أزل `QSMC_AutoTrader` من الشارت.
3. أزل `nadir2` من الشارت.
4. أعد النسخة الاحتياطية من `MQL5/Indicators`, `MQL5/Include/QSMC`, و presets.
5. أعد ترجمة F7 وأرفق النسخة القديمة فقط بعد التحقق من الشعار.

---

## 8. أوامر التحقق الآلية (من جذر المستودع)

```bash
python3 tools/check_production_ready.py
python3 tools/check_release_gate.py
```

النتيجة المتوقعة على Linux أو CI (حيث `g++` موجود):

```text
OFFLINE GO: 46/46 curated checks passed.
GO (with 0 warning(s)) - mechanical invariants hold.
```

### على Windows بدون مترجم C++

سبع فحوص لا تكتفي بقراءة المصدر: تُترجم مقاطع C++ حقيقية من دوال المؤشر (بعد استبدال واجهة MT5) وتُشغّلها، وتحتاج `g++`. إن لم يكن مثبتًا على الجهاز:

- تُطبع `SKIP` وتخرج الفحوص بالرمز `77` — لا `PASS` ولا `FAIL`؛
- يصبح الحكم `OFFLINE GO (PARTIAL): 39/46 verified, 7 SKIPPED` مع أسماء الفحوص المتخطاة؛
- هذه الفحوص **لم تُتحقق على جهازك**، والحكم لا يغطيها؛ اقرأ نتيجة CI على Linux، أو ثبّت MSYS2/MinGW-w64 (مع AddressSanitizer) وأعد التشغيل؛
- `--require-native` يحوّل التخطي إلى `NO-GO` صريح، وهو ما يستخدمه CI حتى لا يمر مشغّل بلا مترجم بصمت.

`QSMC_NO_NATIVE=1` يفرض مسار التخطي لاختبار السلوك فقط؛ لا يحوّل أي فحص فاشل إلى ناجح.

هذه النتيجة لا تعني أن MetaEditor ترجم الملف، ولا أن الاستراتيجية مربحة.
