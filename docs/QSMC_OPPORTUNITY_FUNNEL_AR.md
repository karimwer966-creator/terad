# قمع الفرص — تشخيص بحت لكل شمعة مغلقة (Phase B)

الحالة: **الوحدة غير موصولة بمسارات الإنتاج بعد.** التوصيل (hooks) خطوة منفصلة
باعتراف وتحقق على ويندوز (F7). لا شيء في هذه المرحلة يغيّر قرار تداول أو بافر.

## 1. لماذا هذا موجود

نظيره دائمًا: دورة حياة الـ setup تُسجَّل كاملة من لحظة توفر البيانات حتى لحظة
التعبئة والتحقق من الحماية، بمعرّف ثابت ورمز سبب ثابت، بحيث يمكن الإجابة على:
«أين ضاعت الفرصة فعلًا؟» بدل التخمين. التشخيص لا يُصلِح ولا يفتح ولا يغلق ولا
يغيّر وزنًا ولا عتبة.

## 2. المراحل الثلاث عشرة (بالترتيب)

`DATA_READY → MARKET_EVENT → CANDIDATE → HTF_CONTEXT → STRUCTURE_AND_LIQUIDITY
→ ZONE_AND_GEOMETRY → QUALITY → CORE_EXPORTED → EA_RECEIVED → SESSION_ALLOWED
→ RISK_ALLOWED → ORDER_ATTEMPTED → FILL_AND_PROTECTION_VERIFIED`

لكل مرحلة ولكل حالة يُسجَّل `PASS | REJECT | DATA_UNAVAILABLE | NOT_REACHED`.
`NOT_REACHED` ليست فشلًا — تعني أن حاجزًا أبكر أوقف السلسلة؛ التفرقة بينهما شرط
صحة التحليل.

## 3. الوحدات والأكواد (file:line للمصدر)

`MQL5/Include/QSMC/QSMC_OpportunityFunnel.mqh`:

- المراحل: `ENUM_QSMC_OF_STAGE` (الأسطر ~51–66)
- الـ verdicts: `ENUM_QSMC_OF_VERDICT` (NOT_REACHED=0 أولًا — الأسطر ~68–74)
- الوحدات: `ENUM_QSMC_OF_UNIT` (NONE/POINTS/PRICE/ATR/PCT/TICKS/SECONDS/LOTS/R)
- أكواد الأسباب: `ENUM_QSMC_OF_REASON` (17 رمزًا) + `QSMC_OF_ReasonName()` —
  تُغطى كلها باختبار (`tools/test_opportunity_funnel.py`)

السبب يُميّز صراحةً بين: `NO_SETUP` (لا شيء تشكّل)، `INCOMPLETE_CHAIN` (السلسلة
السببية ناقصة)، `RULE_REJECT` (تشكّل وانرفض بقاعدة)، `DATA_UNAVAILABLE` /
`DATA_STALE` / `DATA_SHORT_READ` (=CopyBuffer قصير/فاشل، مستوى ABI)،
`INDICATOR_INPUT_MISMATCH` (إعدادات iCustom الخاصة تختلف عن شارت الـ EA)،
`SESSION`، `GUARD_ACCOUNT_WIDE` (يومي/equity HWM على مستوى الحساب كله)،
`GUARD_EA` (خاص بالـ magic)، `SPREAD_TOO_WIDE`، `RR_INVALID`، `BROKER_REJECT`،
`PROTECTION_MISSING`، `INTERNAL` (خطأ استعمال التشخيص نفسه — لا يُستخدم للحسم).

## 4. الثوابت غير القابلة للكسر (عقد عدم التداخل)

1. الوحدة لا تُرجع أي قيمة تستهلكها بوابة أو إشارة أو مخاطرة أو أمر.
2. لا أوامر (`OrderSend/Modify/...`)، لا `GlobalVariable*`، لا `SetIndexBuffer`،
   لا `CopyBuffer`، لا `FileOpen/FileWrite`، لا شبكة، لا `WebRequest`،
   لا `#import`. — مُتحقق منها آليًا في قسم B من الاختبار.
3. معطلة (الافتراضي): لا تسجيل ولا طباعة إطلاقًا (`g_qsmc_of_enabled=false`).
4. مفعّلة: تسجيل في حلقة ثابتة (1024 حدثًا) + عدّادات أحادية؛ I/O الوحيد هو
   `Print` عبر `QSMC_OF_PrintSummary()` — موجز سطر-لكل-مرحلة وسبب. لا ملفات.
5. `FNV-1a-64(symbol|family|direction|bar)` = معرّف ثابت عبر إعادة تشغيل نفس
   التاريخ — يسمح بمقارنة traces بين بناءين (deterministic setup id).
6. عند امتلاء الحلقة تُضبط `overflow` ويبقى الإجمالي أحاديًا؛ التفاصيل تُقتطع
   وتُعلَم — لا تكذب الأرقام.

كيف نثبت "buffers وقرارات التداول لا تتغير":
- بنيويًا: لا مسار في الإنتاج يقرأ أي شيء من الوحدة (لا include بعد).
- سلوكيًا (بعد التوصيل): إعادة تشغيل نفس النافذة مع التشخيص Off/On ومقارنة
  `QSMC_FixedRangeDump` CSV لكل buffers 0–25 وقرارات الـ EA في السجل — يجب أن
  تتطابق بايت-بايت للأوامر وبشكل القيم. هذا شرط توقيع Phase B مكتملة، ويحتاج
  F7 ومخرجات على جهاز المشغل.

## 5. التكامل الحالي (بالضبط)

- الأداة التشخيصية هي البرنامج الوحيد الذي يصل للوحدة الآن
  (`MQL5/Scripts/QSMC_FixedRangeDump.mq5`: `#include` واحد + `QSMC_OF_Reset()`
  في بداية `OnStart` — يمحو عدّادات الوحدة فقط، لا يغيّر CSV أو أي شيء آخر).
  السبب: بوابة `check_include_graph.py` I4 تحظر header لا يصل إليه برنامج
  ("optional dead weight"). لا تُحذف الوحدة ولا تُفعّل مخرجاتها في الأداة.
- nadir2.mq5 وQSMC_AutoTrader.mq5: **بدون أي تعديل.**

## 6. خريطة الخطافات المقترحة (لم تُنفذ؛ تُراجع سطرًا سطرًا مع المشغل)

المرساة = أسماء دوال ثابتة؛ أرقام الأسطر قد تنجرف بعد أي تعديل:

| المرحلة | مكان التوصيل المقترح | الملاحظة |
|---|---|---|
| DATA_READY | بداية `OnCalculate` في nadir2.mq5 (بعد فحص `rates_total` والشموع المغلقة) | PASS أو DATA_UNAVAILABLE+DATA_SHORT_READ عند فشل نسخ/نقص تاريخ |
| MARKET_EVENT | عند أول كشف حدث causal (`BuildCausalEventGraph`) | NO_SETUP مقابل حدث موجود |
| CANDIDATE | عند إنشاء setup في `g_history_setups` أو حالة `g_active_setup` | family="CORE" |
| HTF_CONTEXT | عند قرار الـ top-down/veto/confirm | نص القرار يُسجَّل كرمز سبب عند الرفض |
| STRUCTURE_AND_LIQUIDITY | عند تقييم `TopDown`/`VP` للسيولة والحواجز | — |
| ZONE_AND_GEOMETRY | عند التحقق من هندسة entry/SL/TP | RR_INVALID هنا قبل التنفيذ |
| QUALITY | عند `UpdateSignalMask` أو تصنيف الـ class | REASON_RULE_REJECT مع الدرجة |
| CORE_EXPORTED | داخل `DiagPublishCoreState` (قبل `GlobalVariableSet`) | لا نمنع النشر؛ نستمع فقط |
| EA_RECEIVED | بعد `CopyBuffer` الخصيصة في الـ EA (قراءة CORE: الاتجاه/الدخول/SL/TPs/SCORE/CLASS) | short read ⇒ DATA_SHORT_READ |
| SESSION_ALLOWED | عند قرار فلتر الجلسة في الـ EA | reason=SESSION |
| RISK_ALLOWED | عند قرارات guards الحساب-الواسعة/EA وجحيم spread/RR لحظة التعبئة | GUARD_* / SPREAD_TOO_WIDE / RR_INVALID |
| ORDER_ATTEMPTED | حول `OrderSend` مباشرة | BROKER_REJECT مع الـ retcode |
| FILL_AND_PROTECTION_VERIFIED | بعد التحقق من التعبئة + SL/TP فعليًا عند الوسيط | PROTECTION_MISSING إن غاب الحماية |

قواعد التوصيل: `if(!QSMC_OF_IsEnabled()) return original_path_unchanged;` —
أي أن استدعاءات التشخيص تبقى أسطرًا محايدة وظيفيًا، وأي خطأ في التشخيص لا يمكن
أن يعيق البوابة (لا early-return قبل أي قرار؛ كل الخطافات بعد القرار أو في
فرعها المحايد). التفعيل عبر مدخل جديد opt-in (مثلاً `InpOpportunityFunnelLog=false`)
يُضاف عند التوصيل، ولا يغيّر أي preset موجود.

## 7. صيغة CSV لكل حدث

```
<bar_epoch>,<symbol>,<family>,<direction>,<STAGE>,<VERDICT>,<REASON>,<value>,<threshold>,<unit>,<id>
```
`value/threshold` = `EMPTY_VALUE` عند عدم الانطباق (وليس 0!). `id` بالتصنيف FNV أعلاه.
مثال:
`1730000000,XAUUSD,CORE,-1,HTF_CONTEXT,DATA_UNAVAILABLE,DATA_UNAVAILABLE,EMPTY_VALUE,EMPTY_VALUE,none,13876403271122334455`

## 8. الاختبارات (tools/test_opportunity_funnel.py)

- **B. ثوابت المصدر (تعمل دائمًا):** لا أي API تداول/GV/بافر/ملفات/شبكة في
  الكود الحي؛ `StageName` تغطي 13 حالة مرة واحدة؛ `ReasonName` تغطي 17 مرة.
- **A. Native harness (g++، ASan/UBSan):** ثبات معرّف FNV؛ المعطلة صامتة تمامًا
  (لا أحداث ولا طباعة)؛ العدّادات لكل (مرحلة، verdict) ولكل سبب؛ قراءة الحلقة
  `GetRecent`؛ صيغة CSV (11 حقلًا)؛ overflow يُعلَم ولا يسقط الإجمالي؛
  `Summary` يذكر كل المراحل. بدون g++ تخرج بـ 77 (NOT verified) ولا تُدّعي PASS.

## 9. ما لا يُدّعى حتى الآن

- التجميع (compile) بـ MetaEditor: **NOT VERIFIED**.
- التشغيل على محطة حقيقية/tester: **NOT VERIFIED**.
- أن التشخيص يقيس "جودة الإشارة": لا؛ يقيس **أين** توقف السلسلة فقط.
- أن traces تثبت أي شيء عن الربحية: لا.
- لا تغيّر هذه الوحدة أي شيء في مسارات CORE أو القرار أو الأوامر — وأي علاقة
  لها بها هي قراءة فقط، تُضاف لاحقًا بمراجعة صريحة.
