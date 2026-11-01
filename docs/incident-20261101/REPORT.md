# تحقيق QSMC 6.6.13 — حادثة 2026-11-01

## تصحيح لاحق لنتيجة F7

أبلغ المستخدم بعد الدمج عن **32 errors, 0 warnings** في `QSMC_InputFingerprint.mqh`. ثبت أن المولّد القديم لا يفصل declarators المتعددة بفاصلة؛ فدمج Start/End في تعبير غير صالح وأغفل ثمانية End من البصمة. صُحّح المولّد وأعيد توليد header إلى 576 متغيرًا. أحدث تشغيل محلي: **47 فحصًا ناجحًا**؛ الأدلة في `fingerprint-fix/` والتفاصيل في `fingerprint-fix/NOTE.md`. نتائج 46 فحصًا أدناه توثّق المرحلة السابقة، وليست إثباتًا لصحة compilation؛ F7 بعد الإصلاح ما زال غير متاح هنا.

## الحكم التنفيذي

**هذه نهاية مرحلة إصلاح المصدر والاختبارات المحلية، وليست موافقة نشر للإنتاج.**
نجحت الفحوص المحلية الإلزامية الأربعة وجميع ملفات `tools/test_*.py`: **46 فحصًا، صفر فشل**. لا توجد منصة MT5 أو MetaEditor هنا؛ لم يُجرَ F7، ولا replay/backtest، ولا اختبار ICMarkets حي. لا يصح وصف البناء بأنه 0 errors / 0 warnings أو جاهز للإنتاج قبل اجتياز الخطوات أدناه.

الأدلة الأصلية صور/وصف، وليست Journal خامًا يربط المنطقة 25,745 بالرمز ونسخة المؤشر. لذلك لم أثبت سبب هذه المنطقة بعينها، أو سبب فرق السعر بعينه. فصلت العيوب المؤكدة في المصدر عن هذه الفرضيات.

## قبل / بعد — المقصود في المصدر، لا نتيجة منصة مثبتة

| المهمة | قبل | بعد التعديل |
|---|---|---|
| P0 المنطقة | لا يوجد فحص plausibility مشترك قبل scoring | رفض band غير الصالح أو مركز خارج تاريخ الرمز المحمّل؛ تقادم المنطقة البعيدة مشروط بالعمر؛ سجل سبب ومصدر |
| P0 السلطة | Tactical يكوّن ENTRY + CONFIRMED؛ حالة اللوحة من arbiter/resolver | Tactical غير دخول، RXN غير دخول؛ headline اللوحة وbadge الحالة من snapshot واحد لـCore buffer 7 |
| P1 scanner | reset قبل استهلاك العدادات | الجدول والعدادات يقرآن pass نفسه ثم reset |
| P1 ATR | نافذة ناقصة قد تنتج صفرًا يوحي بنظام LOW | 100/250 عينات سابقة صالحة كاملة؛ current مستبعد؛ missing=-1، LOW فقط من percentile صالح |
| P1 instances | Global Variables باسم الرمز والفريم فقط؛ iCustom يستخدم defaults | ABI تشخيص v2 مفصول بالحساب/السيرفر/الرمز/الفريم/بصمة Inputs؛ EA يقرأ هوية defaults فقط؛ اختلاف نشط ظاهر كـINSTANCE MISMATCH |
| P2 السعر | لا تكفي المعلومات المرئية لإثبات مصدر فرق الأسعار | tooltip الحالة يفصل Bid/Ask ووقت tick وعمره عن CLOSED[1] ووقت شمعتها |
| P2 العرض | badge الحالة الجديد ثابت الموضع وقد يصطدم بلوحة | قياس عرض فعلي، اختصار مع النص الكامل في tooltip، تفادي مستطيلات اللوحات بمحاولات محدودة؛ PRIMARY القديم معلّم CONTEXT (NOT ENTRY) |

## 1. P0: المنطقة والتسعير

- **المؤكد:** `CBarSeries` يستقبل بيانات الرمز المحدد ويحوّل التخزين إلى oldest→newest (`QSMC_MarketData.mqh:157–204`). `CZoneRegistry::Rebuild` يبدأ بـClear (`QSMC_Zones.mqh:143–146`). لم أجد في هذا المسار دليل تحميل منطقة من ملف أو registry عالمي لرمز آخر. هذه ليست برهنة غياب كل مسارات التلوث في المنصة.
- **غير المثبت:** أن 25,745 كانت أصلًا منطقة BTCUSD، أو خطأ point scaling، أو منطقة EUR/ذهب عُرضت دون تسمية المصدر، أو بقايا instance أخرى. لا يوجد Journal خام لتعيين أي منها.
- **التعديل:** `QSMC_Types.mqh:416` دالة range pure؛ `QSMC_IncidentSafety.mqh:7` فلتر host؛ `nadir2.mq5:34838` قبل استهلاك المرشحين للتقييم؛ `QSMC_Scanners.mqh:475` قبل scoring؛ `QSMC_ScannerProbe.mq5:134` يربط ConfigureZoneGuard فعلًا و`:189` يكتب SOURCE.
- **السياسة:** `InpZoneMaxDistanceATR=12` و`InpZoneLifetimeBars=120`. الرفض بسبب البعد يتطلب **gap > N×ATR AND (age > lifetime أو العمر مجهول)**. أما band غير الصالح أو مركزه خارج low/high التاريخ المغلق المحمّل فيُرفض مستقلًا. الاختبار التاريخي الحالي على **المركز**، وليس شرط احتواء كل حافة band داخل التاريخ. لا يُدّعى أنه يفحص كامل تاريخ الأداة المتاح لدى الوسيط.
- **التشخيص:** `[QSMC_ZONE_REJECT]` يسجل symbol/tf/source/created/lo/hi/closed/history/ATR/point/digits و`scale=raw-price` والسبب. الحالات المبكرة لفقد/فساد مصفوفة host تُسقط المرشحين دون هذا السجل التفصيلي؛ تحسين تشخيص هذا المسار ما زال مطلوبًا.
- **الاختبار:** `test_zone_provenance.py` يستخرج predicate الفعلية ويشغّلها native مع assertions لمسار قبل scoring. الفشل السابق محفوظ في `evidence/zone-before.log`.
- **Commit:** `b7c819b`.

## 2. P0: النصوص وسلطة الدخول

- **المؤكد:** النص القديم في Tactical كان يستخدم ENTRY/CONFIRMED رغم أن سلطة EA مستقلة. headline اللوحة كان يستطيع اتخاذ اتجاه من alert primary أو resolver، وليس بالضرورة Core buffer المنشور.
- **التعديل:** `nadir2.mq5:5779` يصبح `TACTICAL TOUCH (not an entry)` مع CLOSED/PREVIEW؛ `:41152` يصبح RXN `REACTION CONFIRMED (not an entry)`.
- `QSMC_IncidentSafety.mqh:48–65` يبني snapshot من `BufSigCoreDir[closed]` فقط؛ التحديث بعد `SigLog_Update` عند `nadir2.mq5:15756`؛ headline اللوحة عند `:31862` وbadge الحالة يستهلكان `QA_CoreStatus()` نفسه. لا تكتب هذه الوظائف في buffers 7–12.
- `InpAdvisoryLabelMaxDistanceATR=3` و`InpAdvisoryLabelLifetimeBars=12`: انتهاء الرسم عند تجاوز **أحد** البعد أو العمر، أو invalidation/retirement/conflict المعني. RXN يُفحص قبل cache (`:41221`)؛ Tactical يحذف الرسم فقط، بعد نشر الواقعة إلى مسارها المعتاد.
- `nadir2.mq5:28569` لا يعرض ENTRY+ للسلسلة عند غياب اتجاه Core المنشور؛ صف PRIMARY صار CONTEXT (NOT ENTRY). هذا لا يحذف معلومات المعارضة أو السياق.
- **حد التغطية:** badge وheadline الحاليان موحدان. لم تُثبت بصريًا كل الكائنات التاريخية أو أسطح renderer القديم (`QSMC_Renderer.mqh:97`) أو كل تداخلات الرسومات. الاختبار الجديد source wiring، لا اختبار MT5 سلوكي كامل.
- **الاختبار:** `test_display_authority.py`؛ `evidence/authority-before.log`.
- **Commit:** `0156127`؛ توضيح صف السياق في commit العرض أدناه.

## 3. P1: snapshot الماسح

- **المؤكد:** BeginPass كان يصفر الحالة قبل بناء counters، بينما الصفوف مأخوذة من المرور المكتمل.
- **التعديل:** `QSMC_ScannerProbe.mq5:287–311`: Scan ثم Sort/render/counters ثم Comment ثم BeginPass.
- Rows المرفوضة ليست scannable ولا نجاحًا؛ SOURCE يحدد رمز السطر ولا يوحي بأنها مستويات رمز الشارت.
- **الاختبار:** `test_scanner_snapshot.py`؛ `evidence/scanner-before.log`.
- **Commit:** `3331ded`.

## 4. P1: ATR/percentile

- **المؤكد:** قبول warm-up جزئي/مقارنة عينات غير متكافئة كان يسمح بصفر لا يثبت حدًا أدنى صحيحًا.
- **التعديل:** `QSMC_Scanners.mqh:707–779`: عينات ATRAt السابقة `ci-window ... ci-1` بالضبط، مع رفض nonfinite/EMPTY/nonpositive. Current يستخدم ATRAt نفسه. لا مقارنة ذاتية. percentile=-1 عند نقص النافذة؛ regime UNKNOWN إن لم تتوافر أي نافذة كاملة. النافذة 100 وحدها يمكن أن تعطي regime صالحًا مع بقاء 250 غير متاح.
- percentile يُحسب بنسبة العينات الأقل strict؛ لذلك constant/ties = 0 مشروع بعد إثبات اكتمال وصلاحية العينات. عبارة verified minimum/tie تشرح 0/0.
- `InpProbeDumpATR=true` يطبع `[QSMC_ATR_SAMPLE]` للـ100 والـ250 مع index/time/ATR والقيمة الحالية؛ مرة لكل نافذة/شمعة في هذا host.
- **الاختبار:** `test_volatility_window.py` يشغّل Percentile الفعلية native: increasing/decreasing/constant/short/invalid. لا يثبت بيانات الوسيط الأصلية.
- **Commit:** `dec1065`؛ `evidence/atr-before.log`.

## 5. P1: instances وخطة توافق التشخيص

- **المؤكد:** EA يستدعي `iCustom(_Symbol,_Period,InpIndicatorName)` بلا قائمة Inputs. لا يرث الإعدادات المرئية. مفتاح التشخيص القديم كان مشتركًا للرمز والفريم.
- **التعديل:** `QSMC_InstanceIdentity.mqh:1–78`؛ `QSMC_InputFingerprint.mqh` مولّد من **576 متغير input فعليًا** (568 سطر declaration؛ بعض الأسطر يعرّف متغيرين) في host والملفات المضمّنة ذات المدخلات. `generate_input_fingerprint.py --check` يكشف drift في الأسماء/الترتيب/defaults. الـdouble يُسلسل إلى 16 منزلة؛ لا تُطبع قيم المدخلات الخام.
- heartbeat يسجل الهوية قبل early returns في `nadir2.mq5:15102`. يسجل `[QSMC_INSTANCE]` الرمز والفريم وchart ID وactual/default hash ويذكر عدم توريث Inputs. EA يسجل `[QSMC_AT INSTANCE]` عند التهيئة.
- اختلاف hashes النشطة لنفس scope خلال 300 ثانية server-time ينتج `INSTANCE MISMATCH - WAIT` في حالة العرض المشتركة. **هذه علامة عرض وتشخيص، وليست بوابة تداول جديدة ولا تعطيلًا للـEA**. لا يتغير Core buffer بسببها.
- مفتاح v2 يحتوي بصمة الحساب/السيرفر/الرمز + الفريم + بصمة المدخلات؛ EA `DiagVarName` عند `QSMC_AutoTrader.mq5:1056` يكتشف فقط default-equivalent حديثة. لا fallback إلى متغيرات التشخيص القديمة؛ missing identity يعني no record.
- **خطة التوافق:** تحديث مؤشر host والـEA معًا. buffers 7 direction / 8 entry / 9 SL / 10–12 TP1–3 ونداء iCustom بلا arguments بقيت كما هي؛ لا rename/reorder للـInputs القديمة، inputs السلامة أُلحقت. التغيير المقصود هو **diagnostic ABI v2 فقط**. الأدوات الخارجية التي تقرأ `QSMC_DIAG_*` مباشرة تحتاج ترحيلًا إلى v2. لا تحذف متغيرات terminal القديمة آليًا، ولا تستعملها لإثبات سلامة النسخة الجديدة.
- **حدود:** FNV32 checksum تشخيصية وليست hash أمنية أو ضمانًا رياضيًا ضد collision. الكشف على مستوى الحساب/الرمز/الفريم لا يحدد أي مرئي اختاره المستخدم ليكون مرجعًا وحيدًا. namespaces كائنات الشارت القديمة المشتركة لم تُعزل كلها. التوقيت server-time قد لا يتقدم عند توقف ticks. الأداء مع Global Variables كثيرة يحتاج قياسًا في MT5.
- **الاختبار:** `test_instance_identity.py` + تحديث `test_diag_bridge.py` لاختبار ABI v2 والفشل المغلق دون fallback. الفشل السابق في `evidence/instance-before.log`.
- **Commit:** `e76dbca`.

## 6. P2: السعر

- `QSMC_IncidentSafety.mqh:68` يكتب في tooltip الحالة: symbol/tf، وقت render server، BID/ASK، tick_ms، quote_age_s، STALE إذا تجاوز العمر 300 ثانية أو لا يوجد tick، وCLOSED[1] مع bar_open. السعر المغلق ليس bid/ask.
- هذا snapshot **وقت الرسم**، وليس وعدًا بتحديث tooltip أثناء توقف الحساب. عمر quote لا يساوي بالضرورة latency الشبكة؛ clock unknown معلن حين يمكن كشفه.
- **غير المثبت:** هل فرق 77903.45 مقابل 77873.92 كان closed/live أو tick قديمًا أو قراءة في وقت مختلف. يلزم التقاط tooltip وJournal متزامنين لكل فريم.
- **الاختبار:** `test_price_provenance.py`؛ `evidence/price-before.log`.
- **Commit:** `7503a1e`.

## 7. P2: compact/collision

- `QSMC_IncidentSafety.mqh:91` يقيس النص بخط Consolas، يختصره حسب عرض viewport، ويحفظ النص الكامل مع السبب والهوية والسعر في tooltip.
- يتفادى docked `OBJ_RECTANGLE_LABEL` بمحاولات محدودة، دون تعديل scoring أو إزالة معلومات القرار. يوضح صف PRIMARY أنه سياق لا دخول.
- **الحدود:** ليس layout engine جديدًا لجميع كائنات الشارت. الرسم فوق شارت ممتلئ جدًا، labels بلا خلفيات، الشاشات الصغيرة، DPI وتغيّر الحجم والتداخل مع كائنات EA لم تُثبت بصريًا. لا ضمان عدم collision مطلقًا بعد 8 محاولات.
- **الاختبار:** `test_incident_compact.py`؛ `evidence/compact-before.log`.
- **Commit:** `e03f1f3`.

## الفحوص والأدلة

- `python tools/static_check.py` — PASS.
- `python tools/check_release_gate.py` — PASS.
- `python tools/check_scenario_geometry.py` — PASS.
- `python tools/apply_qsmc_arb_patch.py --check` — PASS.
- **جميع 42 ملفات** `tools/test_*.py` — PASS. المجموع 46؛ `evidence/summary.txt` والسجل المنفصل لكل ملف محفوظان.
- أول تشغيل شامل كشف 8 failures؛ محفوظة باسم `integration-before-*`. خمسة تخص pins للأسطر/includes بعد إضافة headers؛ الباقي نصوص Tactical/Reaction وعقد diagnostic prefix القديم. حُدّثت إلى inventories دقيقة وعقد v2/non-entry، دون خفض RR أو gates أو veto أو شروط التداول.
- فحص CRLF للـhost نجح: 43,359 سطرًا. `git diff --check` الافتراضي يعتبر CRLF trailing whitespace في هذه البيئة؛ الفحص الصحيح مع `git -c core.whitespace=cr-at-eol diff 34f38ec --check` يحترم تنسيق الملف المفروض.
- الاختبارات native/source ليست MQL compilation. لا تداول مضاف إلى المؤشر/الماسح. لا تعديل عمدي لبوابات RR/spread/ownership/confirmation لزيادة الإشارات. تغيّر zone admission مقصود كفلتر سلامة محافظ، لا كوسيلة لإنتاج إشارات أكثر.
- README العربي السابق بقي خارج commits هذه المهمة.

## بوابة MT5 الإلزامية قبل النشر — خطوات محددة

1. استخدم terminal تجريبي منفصل، احفظ نسخة source/ex5 وملفات set وJournal الأصلي. **أوقف AutoTrading أثناء التحقق البصري**؛ المؤشر نفسه لا ينفذ صفقات.
2. انسخ host وكل headers الجديدة والـEA والـScannerProbe إلى مواضعها الصحيحة. Compile بالـMetaEditor/F7 للمؤشر والـEA والماسح. احفظ logs كاملة تثبت 0 errors و0 warnings لكل واحد؛ عالج أي خطأ قبل المتابعة.
3. أرفق BTCUSD على H1/H4/D1 بحساب وسيرفر ICMarkets المعنيين، وحمّل تاريخًا كافيًا لـ250 ATR سابقة صالحة. احفظ symbol الكامل/digits/point وserver time وInputs لكل instance. لا تفترض مساواة أسماء رموز الوسطاء.
4. شغّل ScannerProbe بقائمة الرموز الستة الأصلية، ثم بقائمة لا تحتوي رموزًا قابلة للفحص. التقط snapshot بعد اكتمال pass: rows/scannable/counters/rejections يجب أن تنتمي إلى pass واحد، ولا يعد SYMBOL/NOT_READY نجاحًا. تحقق أن كل نطاق سعري تحته SOURCE صحيح.
5. فعّل `InpProbeDumpATR=true` لشمعة واحدة مكتملة؛ صدّر `[QSMC_ATR_SAMPLE]` للـ100 والـ250. احسب يدويًا عدد القيم الأقل من current، تحقق الترتيب وعدم تضمين current، ثم اختبر history أقصر. لا تقبل 0/0 LOW دون الـ250 عينة السابقة الصالحة وتفسير minimum/tie.
6. أعد حالة المنطقة الأصلية إن أمكن. اجمع `[QSMC_ZONE_REJECT]` مع الرمز والفريم والمصدر وraw prices وpoint/digits وتاريخ الشمعة. اختبر نطاقًا خارج تاريخ الرمز، نطاقًا بعيدًا حديثًا، وآخر بعيدًا أقدم من 120 bar: الأخير يُرفض، الحديث لا يُرفض بسبب العمر/المسافة وحدهما. تحقق أن المرفوض لا يصل إلى scoring/display بقوة موجبة.
7. اختبر Tactical/RXN مع Core WAIT، ثم Core BUY وSELL: Tactical/RXN لا يكتبان ENTRY CONFIRMED؛ headline وbadge الحاليان متطابقان. تقدّم أكثر من 12 bar، ابتعد أكثر من 3 ATR، وافعل invalidation/conflict/retirement؛ تحقق حذف الرسم advisory حتى لو draw signature لم يتغير. راجع أيضًا root primary القديم والسهام التاريخية، لا headline فقط.
8. أرفق EA بالـdefaults، ثم مؤشرًا مرئيًا defaults: طابق default hash في `[QSMC_INSTANCE]` و`[QSMC_AT INSTANCE]`. غيّر input واحدًا في المرئي: actual hash يختلف ويظهر INSTANCE MISMATCH؛ تأكد أن EA لا يقرأ diagnostics المرئي custom. أزل custom وانتظر 300 ثانية server-time مع ticks ثم أعد الحساب. اختبر شارتين وحسابًا آخر وعدم تسرب diagnostics بينهما.
9. صدّر buffers 7–12 من **handle الـEA نفسه** ومؤشر مرئي متطابق المدخلات عند شمعة مغلقة واحدة. راعِ أن EA CopyBuffer shift0 forming بينما host chronological closed=rates_total-2. لا تقارن indexين مختلفين. تحقق بقاء اتجاه/entry/SL/TP والعقود القديمة كما هي.
10. التقط tooltip الحالة على H1/H4/D1 في اللحظة نفسها: قارن tick_ms/Bid/Ask وCLOSED[1]/bar_open. أوقف التغذية مؤقتًا على demo للتحقق من stale/time semantics؛ لا تستنتج latency من اختلاف سعرين بلا timestamp.
11. جرّب نوافذ 800×600 و1280×720 و1920×1080، DPI مختلفًا، مع panels وEA trade labels. اختبر resize/zoom/collapse والتبديل بين الرموز والفريمات وإزالة المؤشر. النص المختصر يجب أن يحتفظ بالتفاصيل في tooltip، ولا يبقى badge يتيم. صوّر أي تداخلات متبقية لإكمال layout.
12. نفّذ replay/backtest على البيانات التي أظهرت العطل، ثم demo soak مع قياس CPU/عدد الكائنات/Global Variables/log throttling. قارن قبول/رفض الإشارات قبل/بعد، ولا تعالج قلة الإشارات بخفض gates. لا تنقل إلى حساب حي قبل توقيع نتائج هذه الخطوات.

## ما بقي مفتوحًا بوضوح

سبب منطقة 25,745 الأصلي، وسبب فرق السعر الأصلي؛ compile/F7؛ تطابق الـEA handle حيًا؛ عزل جميع أسماء كائنات instances؛ التدقيق البصري الكامل لـrenderer التاريخي؛ تشخيص early exits في zone filter؛ collision الشامل والأداء تحت حمل حقيقي؛ replay والـdemo soak. النجاح المحلي لا يغلق هذه البنود.
