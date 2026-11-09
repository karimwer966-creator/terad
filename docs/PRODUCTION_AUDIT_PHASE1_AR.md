# المرحلة 1 — تدقيق جاهزية الإنتاج

التاريخ: 2026-10-31. الفرع: `arena/ce90627f-terad`.
النطاق: شجرة العمل الحالية، بما فيها إضافة Liquidity + Value غير الملتزم بها سابقًا، لا نسخة main وحدها.

**الحكم: Partial / غير معتمدة للإنتاج بعد.** لا تعديلات للكود في هذه المرحلة. هذا التقرير هو الملف الجديد الوحيد للمرحلة؛ التعديلات الأخرى في git status موروثة من العمل السابق.

هذه قائمة بالعيوب التي ثبتت أثناء المراجعة، وليست ادعاءً باكتشاف جميع عيوب نظام يتجاوز 43 ألف سطر. ما يحتاج replay أو profiler مفصول عن العيوب المثبتة. أرقام الأسطر تخص نسخة التدقيق وقد تتحرك لاحقًا.

## 1. خريطة المعمارية وتدفق البيانات

| الطبقة | المصدر | الحالة الفعلية |
|---|---|---|
| المضيف والبيانات | `nadir2.mq5:14450,15023,15097`؛ OnInit/OnDeinit/OnCalculate | مضيف إجرائي كبير: مقابض، نسخ بيانات، كشف، قرار، رسم وتصدير |
| تطبيع السلاسل | `nadir2.mq5:15137–15290` | المرايا الزمنية chronological، الأقدم صفر، المغلقة total-2، الجارية total-1؛ معالجة series/short CopyBuffer موجودة |
| S/R وMTF | `nadir2.mq5:41300–41340,43037` | W1→D1→H4→H1→M30→M15→M5، لا مجرد فريم واحد |
| Core/TopDown/lifecycle | `nadir2.mq5`، `MQL5/Include/QSMC/QSMC_Root.mqh` | مرشح وأهلية وملكية setup وحالة تنفيذ؛ ليس مطابقًا لكل رأي رسومي |
| Tactical | `nadir2.mq5:5590–5803`؛ `QSMC_Root.mqh:761–968` | preview/closed trigger ثم fact إلى arbiter؛ توجد أيضًا حالة رسومية قديمة |
| ZRE | `nadir2.mq5:34395–37174` | تجميع مناطق، تصنيف سببي، دمج، لمس، قوة، rejection/acceptance، إسقاطات ونتائج |
| RXN | `nadir2.mq5:37199–41276` | يصف reaction/strong/confirmed؛ له snapshots وسجل ورسم؛ وصفه ليس إذن تداول |
| المحكّم | `QSMC_Arbiter.mqh`، `QSMC_Gates.mqh`، `QSMC_AlertManager.mqh` | طبقات OOP موجودة، gates وترتيب وتبريد تنبيه وتاريخ |
| Dispatcher | `nadir2.mq5:40079` | يختار primary من Core/ZRE/RXN بعد تغذية root، ويرسم/يبلغ وفق الأهلية |
| Final resolver | `nadir2.mq5:5817,15739` | تصويت مستقل آخر، اختياري، يغير بعض أسطح العرض؛ ليس بعدُ سلطة التنفيذ الوحيدة |
| الاستراتيجيات | `nadir2.mq5:898–1014` | OB/PO3/Silver Bullet/Wyckoff/PA/MR/Confluence/Risk؛ معظم الإضافات اختيارية وعرضية |
| Volume Profile | `nadir2.mq5:33048–34390`؛ `QSMC_Stats.mqh:178–274` | tick-volume profile، POC/VA، جلسات وclose-location proxy، لا bid/ask delta حقيقي |
| Liquidity + Value | `MQL5/Include/QSMC/QSMC_LiquidityValue.mqh` | مراقبة اختيارية: لقطة قبل السحب، تأكيد شمعة، retest وRR؛ ليست MSS كاملة ولا تنفيذًا |
| القياس | `QSMC_EarlyBreakDetector.mqh`، `QSMC_Stats.mqh` | early-break score وedgebook وأحجام عينات؛ لا إثبات ربحية أو معايرة خارج العينة |
| التنفيذ | `MQL5/Experts/QSMC_AutoTrader.mq5` | EA منفصل؛ المؤشر والheaders لا يرسلان أوامر؛ وجود صفقة في الصورة لا يثبت مصدر فتحها |

### ترتيب دورة القرار المهم

في OnCalculate: تطبيع/نسخ → تحديث alignment والكشف → MTF planner → إعدادات Core → Master VP (`15688`) → LV → PA/MR/CF/RM → ZRE (`15723`) → RXN (`15734`) → dispatcher/root (`15736`) → final resolver (`15739–15745`) → journal → RXN drawing → scenario → signal log → نشر Core diagnostics (`15759`).

**الاستنتاج:** هناك فصل جيد جزئيًا بين المعلومة والتنفيذ، لكن «مصدر واحد لكل شيء» غير متحقق. resolver يحسب بعد اختيار primary والتنبيهات، بينما EA يقرأ عقد Core منفصلًا.

## 2. العيوب المثبتة

الشدة High = قد يؤثر على معنى القرار/الإشارة؛ Medium = دقة البيانات أو الواجهة أو التفسير. ليست أي شدة ادعاءً بصفقة خاطئة مثبتة في حساب المستخدم.

| ID | الشدة | الملف/الأسطر | العيب والسبب الجذري | المطلوب لاحقًا |
|---|---|---|---|---|
| A01 | High | `nadir2.mq5:5831,5687–5694` | resolver يأخذ `g_tac_dir` دون اشتراط `g_tac_closed`. Tactical يبقي اتجاهًا أثناء live preview؛ لذلك يمكن لتصويت غير مغلق أن يشارك في verdict موصوف بأنه closed-bar. لا يعني أن كل preview ينتج BUY/SELL؛ يلزم بلوغ مجموع الأوزان. | اختبار preview-only: صفر تصويت تنفيذي، ثم gate مغلق صريح |
| A02 | High | `nadir2.mq5:5829` مقابل `40825–40857` | تصويت reaction يستخدم `best_buy.valid ? BUY : best_sell.valid ? SELL : 0`. عند وجود مرشحين صالحين للجهتين يفوز BUY دائمًا في التصويت، حتى لو SELL أقوى أو الطرفان متعارضين. كذلك valid لا يشترط مستوى reaction/confirmed. | تمثيل تعارض/مستوى دليل واضح، بلا انحياز BUY ضمني |
| A03 | High | `nadir2.mq5:15736–15745,40079–40170,31849–31885`؛ `QSMC_Preset.mqh:42–43` | primary/alerts تُحسم قبل final resolver؛ resolver ليس gate مشتركًا لكل من العرض والتنفيذ. افتراضي resolver=false وGateCore=false يبقي مسارات مختلفة عمدًا. تفعيل resolver وحده لا يجعل النظام SSOT؛ قد يتغير STATUS وتبقى تفاصيل PRIMARY لمسار آخر. | قرار نهائي واحد بعقد منشور، مع ترحيل اختياري ومقارنة سلوكية قبل تبديل الافتراضيات |
| A04 | Medium | `nadir2.mq5:23495–23575`؛ `QSMC_Structure.mqh:59–62` | DetectLiquidity ينشئ سجل EQH/EQL من أول fractal منفرد عند عدم وجود cluster، دون عدّ عضوين. محرك Structure يعرّف السيولة المتساوية بزوج/cluster. إذًا تسمية EQ في مخزن المضيف لا تثبت equal highs/lows فعلية؛ يؤثر أيضًا على دليل LV الذي يعيد استخدام الاسم. | تتبع عدد pivots وتوقيت تحقق الزوج؛ تمييز swing عن equal-pool |
| A05 | Medium | `nadir2.mq5:34599–34638,34846–34870` | الدمج الموجود side-aware ومقيد بالارتفاع/السلسلة، ويعيد حساب القوة واللمسات؛ ليس «دمج كل overlap وحفظ أقصى قوة». رفض دمج بعض السلاسل مقصود الآن، لكنه لا يحقق عقد المرحلة 2 المطلوب، ولا يشمل كل رسامي النظام. | تحديد عقد geometry/strength/touches وهوية موحدة قبل تغيير الدمج؛ عدم جمع اللمسات المتكررة عميانيًا |
| A06 | Medium | `nadir2.mq5:5694` مقابل `41141–41148` | مع resolver معطل، Tactical يستعمل كلمة CONFIRMED لوصف كسر مغلق، بينما RXN يستعمل CONFIRMED لوصف reaction؛ كلاهما ليس بالضرورة تفويض تنفيذ. السبب تعدد قواميس السلطة. | حجز كلمة ENTRY CONFIRMED للقرار النهائي؛ إبقاء وصف الحقائق منفصلًا |

### نواقص مانعة لاعتماد الإنتاج، وليست أخطاء تشغيل مثبتة

- لا ناتج MetaEditor لهذه الشجرة: لا إثبات **zero errors / zero warnings** ولا EX5 موثق.
- لا replay terminal لثبات الإشارات عبر incremental/full rebuild/reload على M1/M15/H1.
- لا ملف قياس تكلفة OnCalculate/ذاكرة/عدد كائنات طويل المدة على بيانات المستخدم.
- لا دليل معايرة 0–100 كاحتمال نجاح؛ الموجود score أدلة، ولا يجب تسويقه احتمالًا.
- لا ضمان عالمي بأن كل Print له سياسة منع تكرار N bars؛ توجد guards مختلفة وتنبيهات مكررة محمية جزئيًا. يلزم جرد call-sites واختبار شامل قبل ادعاء التغطية.

## 3. تفسير الصورة: ما نعرفه وما لا نعرفه

المشاهد: ملصقات خضراء متقاربة كثيرة، مخطط profile أزرق، tooltip يعلن RXN NON-AUTHORITATIVE؛ tooltip وحده ليس تصريح دخول. الرمز ليس مقروءًا بما يكفي لإثبات أنه XAUUSD؛ لا أستنتج الرمز من مستويات السعر.

**لا يمكن إثبات مصدر التكرار من الصورة وحدها.** النسخة الحالية في `nadir2.mq5:41199–41238` تحذف RXN القديم وتعرض `RXN_BEST` واحدًا، و`41133` يمنع رسم RXN بعكس primary. لذلك نسبة كل الملصقات الخضراء إلى RXN الحالي ستكون غير صحيحة. الاحتمالات: نسخة أقدم، أكثر من مؤشر، تاريخ/مسار آخر أو كائنات من مالك آخر. لإثباتها نحتاج قائمة Objects تتضمن names/types/text، قائمة المؤشرات وملف .set ورقم النسخة في init log.

ZRE ما زال يرسم عدة مسارات تاريخية مفتوحة (`36638–36735`)؛ هذه إسقاطات غير تنفيذية وليست وحدها دليل object leak. سياسة «ملصق لكل منطقة» يجب أن تميز annotation تاريخيًا عن التوصية الحالية وأن تراجع جميع prefixes، لا RXN فقط.

### missed entries

رؤية rejection صحيحة لا تثبت استحقاق سهم تنفيذ. RXN يحتفظ بمناطق أسقطها min-score أو render-cap (`37138–37152`)؛ Core قد يرفض للملكية (`40879–40903`) أو RR/room/HTF/closed confirmation. إزالة هذه الحمايات لإجبار السهم ليست إصلاحًا.

العيب المثبت هنا هو عدم توحيد تفسير القرار (A03/A06)، لا إثبات أن شمعة معينة كانت فرصة تنفيذ ضائعة. يلزم replay للشمعات مع سبب الرفض، وقت الإتاحة، مستويات SL/TP، spread وملكية setup.

## 4. repaint/look-ahead والأداء

- **موجود:** canonical indexing، تأكيد Tactical المغلق، فصل live preview في RXN (`40909–40925`)، تأكيد pivots، snapshot VP سابق للـLV.
- **ثغرة مثبتة:** انتقال preview إلى تصويت resolver (A01)، وليس اتهام كل الرسم بإعادة رسم.
- **بحاجة replay:** إعادة تجميع liquidity من pivots باستخدام ATR الحالي (`23486–23490`) ومتوسط أسعار cluster؛ اختلاف تاريخ/rolling windows قد يغير مناطق التحليل. لا يوجد في هذا التدقيق إثبات أن buffer تنفيذ تاريخيًا يعيد الرسم بسبب ذلك.
- **تكلفة معروفة لا benchmark:** `ZRE_Consolidate:34599` فيه بحث أزواج متكرر مع sort؛ `ZRE_DrawPaths:36710` يحذف ويعيد إسقاطات prefix؛ مسار LV يبحث event ثم parent. caps وincremental موجودة، لكنها لا تثبت زمن تنفيذ مقبولًا على جميع الإعدادات.
- **تسرب الكائنات:** cleanup وcaps موجودة؛ الصورة وحدها لا تثبت leak. يلزم مقارنة تعداد الأسماء بعد إضافة/إزالة/تغيير فريم وإعادة التحميل.

## 5. ما هو مكتمل وما هو ناقص

لم أجد من البحث عن TODO/FIXME/stub وحده قائمة features مفقودة؛ وجود تعليق placeholder-purge لا يعني دالة stub. ولم يثبت البحث أن كل دالة بلا استدعاء ميتة: MQL callbacks وواجهات OOP تحتاج reachability واعيًا.

- OB وSilver Bullet وPO3 وWyckoff وPA وMR وConfluence وRisk **موجودة**؛ لا داعي إعادة كتابتها في المرحلة 3. معظمها display-only/opt-in (`898–1014`).
- rejection/bounce وPOC/VA وsession profiles **موجودة جزئيًا**؛ المطلوب ربطها بعقد نهائي ثابت وليس إضافة أسماء فقط.
- آسيا→لندن→نيويورك: session profiles موجودة؛ سلسلة POC-bias واحدة تشارك التنفيذ غير مثبتة/غير مكتملة.
- winner باستخدام close-location/activity **proxy فقط** (`33048–33051`، `QSMC_EarlyBreakDetector.mqh:31–44`). bid/ask delta الفعلي غير متاح من OHLC/tick-volume وحدها؛ يلزم مصدر مستقل إن كان شرطًا.
- early-break وedgebook **موجودان**؛ ارتباط النتائج باستراتيجية early-break محددة ومعايرة خارج العينة ما زالا يحتاجان إثباتًا.
- OOP موجود في مكتبة QSMC، لكن المضيف ما زال يجمع طبقات عديدة إجرائيًا؛ شرط class per layer ليس مكتملًا.
- `docs/` و`tools/` وCI موجودة. لا README أو CHANGELOG في جذر المستودع في هذه النسخة.

## 6. Production Readiness Checklist

Done هنا تعني وجود بنية/تحقق محدد، لا شهادة ربحية أو اعتماد live.

| البند | الحالة | الدليل/المتبقي |
|---|---|---|
| architecture/data flow موثق | Done | هذا التقرير |
| SSOT واحد للعرض والتنبيه وEA | Partial | A01–A03 |
| BUY/SELL/WAIT موحد + score/reasons | Partial | أكثر من score وverdict؛ resolver له أيضًا CONFLICT=2 |
| advisory لا يرفع نفسه إلى إذن دخول | Partial | فصل موجود؛ عقد التصويت/الألفاظ يحتاج توحيدًا |
| دمج مناطق ATR | Partial | موجود؛ ليس عالميًا ولا نفس عقد max-strength المطلوب |
| ملصق واحد لكل منطقة عبر كل الرسامين | Partial | RXN واحد موجود؛ الصورة والـprefix owners تحتاج حصرًا |
| تنبيهات cooldown ومنع التكرار | Partial | CAlertManager/dispatcher موجودان؛ لا يغطي ذلك كل logs |
| منع تكرار كل رسالة خلال N bars | Missing | لا توجد سياسة شاملة مثبتة |
| closed-bar signals فقط | Partial | فصل جيد، A01، ويلزم terminal replay |
| rejection/bounce/POC entry النهائي | Partial | محركات موجودة؛ LV مراقبة فقط |
| POC bias chain موحد عبر الجلسات | Partial | profiles موجودة؛ عقد مشترك غير مثبت |
| winner proxy معلن بوضوح | Partial | proxy موجود؛ لا delta حقيقي ولا معايرة ربحية |
| early break + statistical edge موثق | Partial | detector/edgebook موجودان؛ attribution/OOS مطلوب |
| confluence للاستراتيجيات المطلوبة | Partial | الحسابات موجودة؛ توحيد سلطة القرار والمعايرة مطلوب |
| ATR/percentiles كل الرموز والفريمات | Partial | تطبيع واسع؛ صلاحية كل سوق لم تثبت |
| class لكل طبقة + interface واضح | Partial | المكتبة OOP، المضيف ليس كذلك بالكامل |
| input validation/history/deinit | Partial | تنفيذ موجود، acceptance في MT5 متبقٍ |
| debug logging off افتراضيًا | Done | switches quiet وrelease gate؛ سياسة N-bars منفصلة |
| alerts popup/push/cooldown | Done | البنية موجودة، اختبار تسليم المنصة متبقٍ |
| اختبارات offline وCI | Done | 32 suites ناجحة؛ ليست backtest أو compile |
| README + CHANGELOG بالجذر | Missing | docs موزعة موجودة |
| MetaEditor صفر أخطاء/تحذيرات | Missing | لا MetaEditor في البيئة |
| replay + 24h demo + resource soak | Missing | لا دليل تشغيل لهذه الشجرة |

## 7. التحقق المنفذ في هذه المرحلة

أعيد تشغيل `tools/test_*.py`: **32 مجموعة، 0 فشل**.
أعيد تشغيل `static_check.py` و`check_release_gate.py` و`check_scenario_geometry.py`: exit 0.
الفحص الساكن: **0 أخطاء، 5 تحذيرات تخص تحقق موازنة تخصيصات runtime في مكونات قائمة**؛ هذه ليست تحذيرات compiler.
Release gate: **0 blocking / 0 warnings**؛ يعني invariants ميكانيكية فقط.
تشغيل LV كمصدر C++ مع MT5 stubs وsanitizers لا يجمع MQL5 ولا يثبت تكامل المنصة.
السجلات المحلية في `out/phase1-audit/` مستبعدة من Git. لا compile أو backtest أو مزاعم ربحية.

## 8. التغيير والـdiff لهذه المرحلة

**لا تغيير برمجي.** ملف جديد فقط: `docs/PRODUCTION_AUDIT_PHASE1_AR.md`، وهذه محتوياته الكاملة. ملفات العمل السابقة لم تُعدّل أثناء المرحلة. لا commit/push/merge.

## 9. كيفية التحقق يدويًا — XAUUSD M1/M15/H1

1. احتفظ بنسخة EX5 و.set وسجل baseline قبل الاستبدال. استخدم Data Folder الصحيح وانسخ جميع headers كمجموعة واحدة.
2. افتح `Indicators/nadir2.mq5` في MetaEditor واضغط F7؛ احفظ build log وإصدار terminal/compiler. النجاح المطلوب **0 errors, 0 warnings**. لا أعطي هذه النتيجة قبل وجود السجل.
3. على حساب demo، افتح XAUUSD لدى نفس الوسيط على M1/M15/H1. سجّل suffix إن وجد ووقت server وspread وعدد bars.
4. مؤشر واحد فقط لكل شارت؛ صدّر .set وObjects list. قارن STATUS وPRIMARY وRXN/Tactical وbuffer Core عند **وقت الشمعة المغلقة نفسه**.
5. replay لحالة rejection وbreakout/acceptance وPOC retest وسحب جهتين، مرة resolver off ومرة on دون تغيير بقية المدخلات. لا تختبر بأموال حقيقية ولا تفعّل EA تلقائيًا.
6. التقط buffers والإشارات قبل/بعد الإغلاق، وبعد refresh/reload وتغيير الفريم. اختبر history ناقصة وفقد CopyBuffer. قارن full rebuild وincremental.
7. راقب عداد objects وزمن OnCalculate والذاكرة لمدة 24 ساعة، ثم أزل المؤشر وتحقق من حذف كائناته فقط.
8. أرفق سجل أسباب الرفض عند كل missed-entry مزعوم؛ لا تستنتج صحة الدخول من الشمعة وحدها.

## 10. حدود المرحلة والتسلسل المقترح

توقفت هنا حسب الطلب. لا بداية للمرحلة 2 دون موافقة.
الأولوية التالية: اختبارات A01/A02 أولًا، ثم تصميم عقد قرار مشترك ووضع مقارنة shadow قبل تحويل أي مصدر قائم؛ بعدها دمج الهوية/الرسم/log de-dup. لا إعادة كتابة صامتة ولا تخفيف gates لإظهار أسهم أكثر.
