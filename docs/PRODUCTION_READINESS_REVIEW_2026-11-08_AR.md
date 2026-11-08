# مراجعة جاهزية الإنتاج — QSMC v6.6.20

**التاريخ:** 2026-11-08 · **الفرع:** `arena/fc2cd921-terad` · **نوع المراجعة:** مراجعة قراءة-كود + بوابات آلية (بدون MetaEditor، بدون Terminال)
**النطاق:** `MQL5/Experts/QSMC_AutoTrader.mq5` (3,247 سطرًا) · `nadir2.mq5` (44,203 سطرًا) · 23 رأسًا في `MQL5/Include/QSMC` · 15 preset · 48 ملف اختبار
**المراجع السابقة المستخدمة كمرجع، لا كدليل:** `docs/demo_readiness_audit_v6.6.16.md` · `docs/incident-20261101/REPORT.md` · `docs/STAGED_GO_LIVE_LADDER_v6.6.14.md`

---

## 0. الحكم

| المرحلة | الحكم | السبب المختصر |
|---|---|---|
| **العرض/الورق (demo/paper)** | **GO مشروط** | الكود يمرّ بكل بوابات المستودع الآلية (44/44 + `GO 0 warnings`)، والأمان الافتراضي ثلاثي (`InpEnableTrading=false`, `InpDryRun=true`, `InpDemoOnly=true`). الشرط الوحيد غير الآلي: **F7 = 0 أخطاء** وسلّم Stage 1/2. |
| **المال الحقيقي** | **NO-GO** | لا يوجد **دليل أداء** لهذا الإصدار إطلاقًا: لا باكتست، لا walk-forward، لا حضانة demo. وجود الأدوات ≠ وجود النتيجة. إضافةً إلى بندي كود أدناه (F1, F2) يجب إغلاقهما أو قبول مخاطرتهما كتابةً. |

**الجملة التي تلخّص المراجعة:** النظام «جاهز تقنيًا» بدرجة عالية، و«جاهز إنتاجيًا» صفر — لأن الإنتاج لا يُقاس بجودة الكود بل بدليل أن الكود يتصرّف كما هو مُدَّعى في السوق. البوابات الحالية تُثبت الشكل والعقد والحساب، ولا تُثبت أيًا من ذلك.

---

## 1. ما شُغِّل فعلًا (قابل للتكرار)

```bash
python3 tools/check_production_ready.py --timeout 300   # 44/44  OFFLINE GO
python3 tools/check_release_gate.py                     # GO (with 0 warning(s))
python3 tools/static_check.py                           # no errors, 5 warning(s)
python3 tools/test_wfa_robustness.py                    # 155/155
python3 tools/wfa_demo.py --out out/wfa/demo            # NO-GO متوقّع (بوابتان تفشلان)
for t in tools/test_*.py; do python3 "$t"; done         # 8 ملفات حمراء (انظر §5)
```

## 2. مصفوفة الأدلة — ماذا تُثبت كل بوابة وماذا لا تُثبت

| البوابة | النتيجة | تُثبت | لا تُثبت |
|---|---|---|---|
| `check_production_ready.py` | 44/44 | توقيعات الكود، العقود المصدرية، ثبات الـpresets، منطق القرار المقارن | الترجمة، التنفيذ، الأداء |
| `check_release_gate.py` | GO, 0 warnings | نسخة واحدة، تخطيط كامل، **صفر trade API في المؤشر**، بصمة الإدخالات، حدود الحجم | أي سلوك زمن تشغيل |
| `static_check.py` + `mql5_rules.py` | 0 أخطاء | قواعد لهجة MQL5، توازن الأقواس، تسريب الملفات | صلاحية الأنواع عند الترجمة |
| `test_execution_safety.py` (105 فحصًا) | PASS | مسار الإرسال: تصنيف الـretcode، retry، مفتاح الرمز، RR عند التنفيذ | استجابة وسيط حقيقي |
| `test_at_risk_audit.py` | PASS | «المعروض = المُنفَّذ» لحدود **الحماية** (HardMax*, DayStopState) | — (لكن انظر F2: لا يشمل تسعير المخاطرة) |
| `test_autotrader_contract.py` | PASS | القيود، الحجم، المفاتيح، الجدارات | — |
| `test_wfa_robustness.py` | 155/155 | حساب WFE/DSR/MC/الهضبة، ورفض الملفات الخاطئة | وجود edge |
| 8 ملفات pin-drift | **حمراء** | لا شيء اليوم | — (انظر §5) |
| **MetaEditor F7** | **لم يُشغَّل** | — | كل شيء متعلق بالترجمة |
| **Strategy Tester / demo** | **لم يُشغَّل** | — | التنفيذ، السبريد، الانزلاق، التوقيت |

## 3. ما لا يستطيع أي شيء في هذا المستودع إثباته (اليوم)

1. أن الملفات **تُترجم** (0 errors) — لا يوجد MetaEditor في بيئة البناء.
2. أن الـEA **يتصل** بمؤشر `nadir2` مبني من نفس المصدر (اختبار iCustom الحقيقي).
3. أن أي إشارة **رابحة** — لا دراسة walk-forward موجودة لهذا الإصدار.
4. أن حدود الوسيط (stops/freeze/filling/margin) مقروءة صحيحةً على حسابك.
5. أي شيء عن **السبريد/الانزلاق** الفعلي.

---

## 4. نتائج مراجعة الكود (بالترتيب حسب الأثر)

### F1 — المفاتيح العالمية لمنع التكرار لا تُمسح أبدًا (P1: يُبطل وضوح الـwalk-forward)

* **الدليل:** `QSMC_AutoTrader.mq5:413` (`GlobName`)، `:447` (`SeenBefore` → `GlobalVariableCheck`)، `:454` (`MarkSeen` → `GlobalVariableSet`). لا يوجد أي `GlobalVariableDel` لهذا البادئة في المستودع.
* **`InpResetBreakersAtInit` لا يعالجها:** الكتلة `:2915–2941` تحذف مفاتيح `DAY/EQ/BLOCKED/TRADES` و`SESS_*` فقط. و`MQL5/Scripts/QSMC_ResetGuards.mq5` يعرّف صراحةً بادئتين فقط: `QSMC_AT_DAY` و`QSMC_AT_SESS`.
* **الأثر في التشغيل الحي:** نمو غير محدود لعدد المتغيرات العالمية (مفتاحان لكل شمعة إشارة). التقرير `docs/incident-20261101/REPORT.md` يذكر أصلًا أن «الأداء مع Global Variables كثيرة يحتاج قياسًا في MT5».
* **الأثر في الاختبار (الأخطر):** في walk-forward بنوافذ متشابكة، الشمعة التي «رُئيت» في تمريرة سابقة تُكتَم في تمريرة لاحقة. نوافذ IS متداخلة بالتصميم (w01 IS 2018–2020، w02 IS 2018.5–2020.5)، وكل تمريرة OOS تسبق تمريرة IS للتجميع التالي — فإن بقيت المفاتيح بين التمريرات، كل optimisation pass بعد الأول يقيس تدفّق إشارات **مخنوقًا جزئيًا**، وWFE يُبنى على أعداد صفقات غير قابلة للمقارنة.
* **ماذا أفعل (تجربة تُثبت أو تنفي في 10 دقائق):**
  1. `w02_opt` وحدها في profile جديد ⇒ سجّل عدد الصفقات.
  2. `w01_oos` ثم `w02_opt` في نفس الـprofile ⇒ سجّل العدد.
  * إن تساوى الرقمان: هذه النسخة تعزل الـtester، والمخطط سليم كما هو.
  * إن اختلفا: شغّل كل تمريرة في مجلد بيانات منفصل (نسخة portable لكل تمريرة)، أو أضف في الـEA حارسًا من سطرين يتجاهل المفاتيح المحفوظة عند `MQLInfoInteger(MQL_TESTER)`.
* **ما أُضيف وقائيًا:** هذه التجربة صارت قسمًا إلزاميًا في `CONFIGS.md` الذي يولّده `tools/wfa_harness.py`، مع تحذير في مخرجات `configs` — لأن «لا تعالجها بـ`InpResetBreakersAtInit`» ليست معلومة بديهية.

### F2 — مُقدِّران مختلفان لمخاطرة الصفقة (P2: العرض ≠ المُنفَّذ في المخاطرة)

| الموقع | الطريقة |
---|---|---|
| `CalcLots` `:829–837` (حجم المركز في وضع نسبة المخاطرة) | `(dist/tick_size)*tick_value` — صيغة تقريبية |
| `EstimateLossAtSL` `:715–733` (حارس الحجم الثابت) | `OrderCalcProfit()` — إجابة الوسيط نفسها، وتفشل مغلقة |
| سطر `SENT` / `DRY RUN` `:1556–1560` ثم `:1574` و`:1620` | الصيغة التقريبية مرة أخرى |

* تعليق المستودع نفسه في `:715–733` يقول إن الصيغة التقريبية «صحيحة فقط عندما يكون `TICK_VALUE` لكل tick سعري ومضاعف العقد 1.0 — افتراضات باطلة على رموز أخرى».
* النتيجة: على XAUUSD/حساب بالدولار يتطابق الرقمان عادةً؛ على رموز أخرى (أو عملة إيداع مختلفة، أو `TICK_VALUE_LOSS` مختلف) **قد يختلف حجم المركز عن نسبة المخاطرة المعلنة، ويختلف الرقم المطبوع عن الذي فُرِض فعلًا**.
* **الإصلاح المقترح (يحتاج F7):** مُستخرِج واحد `bool RiskMoneyAtSL(..., double &money)` يستخدم `OrderCalcProfit`، ويُستدعى من `CalcLots` ومن طباعة `SENT`/`DRY RUN` معًا — نفس نمط `EffectiveRiskPercent()` الذي وحّد حدود الحماية. حتى ذلك الحين: اعتبر رقم `risk` في السجل **تقديريًا**، وراجع يدويًا أول صفقة على كل رمز جديد.

### F3 — خط أساس محفوظ بلا فحص تقادم (P2: يمنع التداول بصمت حتى يتدخل المشغّل)

* `DayGuardLoad` `:934–935` يستعيد الأساس المحفوظ بلا أي تحقق منطقي: إذا كان الأساس من حساب بحالة مختلفة، تصبح `floor` أعلى من equity الحالي ⇒ الحارس يثلج عند أول tick، و**لا تُفتح أي صفقة** حتى يتدخل المشغّل.
* الحادثة `docs/incident-20261101` وثّقت هذا بالضبط (`day_base=5680.64`, `eq≈4999`). المعالجة الحالية: سطر سجل يوجّه إلى `QSMC_ResetGuards.mq5` — أي **إجراء تشغيلي، لا حارس برمجي**.
* **المقترح:** عند التحميل، إذا كان `eq <= floor` و`BLOCKED` غير مضبوط، اطبع `[QSMC_AT GUARD] STALE_BASELINE` مع الأساس والحالة، واقترح إعادة الأساس (بقرار المشغّل لا آليًا). فرق سطرين في السجل يوفّر ساعة تشخيص في أسوأ لحظة.

### F4 — كود احتفالي لإرضاء عقد نصّي (P3: صيانة)

* `:914–915` يكتب نفس المفتاح مرتين (`keq` و`DayGuardKey("EQ")` قيمتهما متطابقة)، والتعليق يعترف: «both resolve to the same GV name; this is a belt-and-suspenders call». السبب أن عقدًا في `tools/test_at_risk_audit.py` يبحث عن **النص الحرفي** `DayGuardKey("EQ")`.
* الأثر: العقد يُثبت وجود سطر، لا وجود سلوك. ومع ازدياد هذه الحالات يصبح المصدر مبنيًا حول grep لا حول منطق.
* **المقترح:** نقل هذه العقود إلى متجهات سلوك (جدول حالات) بدل النص الحرفي، وحذف الكتابة المكرّرة.

### F5 — لا يوجد أي مسار خاص بالـtester (P3: مفاجأة محتملة، آمنة)

* لا `MQLInfoInteger(MQL_TESTER)` في الـEA إطلاقًا. بوابة البيئة `TradeEnvBlock` `:641` تعتبر الحساب «حقيقيًا» إذا كان `ACCOUNT_TRADE_MODE != DEMO`. في الاستراتيجي تستر يكون الحساب عادةً DEMO ⇒ يمرّ.
* إن اختلف ذلك على بناء معيّن، فالـEA **يفشل مغلقًا** (يرفض الإرسال) — أي أن الأسوأ هو تقرير بصفر صفقات وسبب واضح في السجل، لا صفقة حقيقية. لكن هذا يُفسد دراسة كاملة بصمت إذا لم يُقرأ السجل.
* **المقترح:** سطر عند التهيئة: `[QSMC_AT] ENV TESTER=yes|no | ACCOUNT_TRADE_MODE=... | DEMO_ONLY=...` — يجعل السبب مرئيًا في أول 3 أسطر.

### ما هو سليم فعليًا (يستحق التسجيل، لا التصفيق)

| البند | الشاهد |
|---|---|
| SL/TP يُرسلان **مع الأمر** إلى الوسيط | `g_trade.Buy(lots,sym,price,s.sl,s.tp,...)` `:1611–1612` |
| ثلاث بوابات قبل أي إرسال + خروج مبكر صريح | `InpEnableTrading` / `InpDryRun` / `TradeEnvBlock` `:1565–1588` |
| retcode: عابر يُعاد، دائم يُتخلى عنه، ولا «mark seen» على العابر | `:1633–1660` + `RetcodeIsTransient` `:431` |
| إغلاق المركز المعاكس قبل الفتح، وفشله يمنع الفتح | `:1594–1610` |
| فروق الوسيط: STOPS + FREEZE (`max` للتعديلات) | `MinModifyDistance` `:550–557` |
| spread مطلق + نسبة من الوقف + عمر البيانات + الانقطاع | `:1430`, `:1498–1545` |
| حجم: خطوة/حد أدنى/حد أقصى + هامش حر + حارس الحجم الثابت | `NormalizeLots` `:518`, `:839–854` |
| حدود صلبة أعلى من أي إدخال (5% / 10% / 20%) | `:671–673` مع `Effective*` |
| لا trade API في المؤشر (11 مطابقة كلها تعليقات) | تحقّقتُ يدويًا: `grep -n "OrderSend\|CTrade\|trade\." nadir2.mq5` |

---

## 5. مراجعة العملية التطويرية

### P1 — «OFFLINE GO» يغطي مجموعة منسّقة، لا المستودع كله

قِستُ الملفات المستثناة من البوابة المنسقة اليوم:

| ملف | النتيجة | طبيعة الفشل |
|---|---|---|
| `test_docs_freshness.py` | 122 FAIL | أرقام أسطر مثبّتة على v6.6.13 في ملف بطول 44 ألف سطر |
| `test_weighted_gates.py` | 55 FAIL | `L4479 is '...'` — إزاحة أسطر |
| `test_declutter_cap.py` | 27 FAIL | إزاحة |
| `test_resolver.py` | 19 FAIL | إزاحة + «44 enum» صارت 45 |
| `test_decision_journal.py` | 19 FAIL | إزاحة |
| `test_tactical_authority.py` | 13 FAIL | إزاحة |
| `test_phase5_meanreversion.py` | 1 FAIL | إزاحة |
| `test_zone_provenance.py` | **Traceback** | يستدعي `QA_FilterCandidates(cands,ctx)`؛ التوقيع الحالي 5 وسائط (`QSMC_IncidentSafety.mqh:7`) |

**المجموع: 256 تأكيدًا فاشلًا + انهيار واحد، كلها معلنة «للتقرير فقط».** نصفها إزاحة أسطر (لا خطر)، لكن واحدة على الأقل — `zone_provenance` — فشلت لأن **توقيع دالة تغيّر**، ولا شيء يحرس ذلك. هذا هو الفرق بين «العقد صدأ» و«العقد انكسر»: اليوم لا نعرف أيّهما، و«الأحمر» في هذه الملفات أصبح حالة طبيعية يتعلّم الجميع تجاهلها.

**التوصية:** مهلة محددة (أسبوعان) لإعادة تثبيت هذه الملفات عبر `tools/pinmap.py` أو أرشفتها مع ملاحظة مؤرخة تشرح لماذا نُسخت. مستودع فيه أحمر دائم لا يكشف انحدارًا حقيقيًا.

### P2 — لا يوجد دليل أداء لهذا الإصدار، لا قبل ولا بعد

لا دراسة walk-forward، لا تقرير Monte Carlo، لا holdout، لا حضانة demo موثّقة داخل المستودع. الأدوات الآن موجودة (`tools/wfa_harness.py`, `tools/wfa_stats.py`) وأول أمر فيها يحوّل هذا من «رأي» إلى «ملف». لكن حتى تُنتَج النتيجة، فإن أي وصف للنظام بأنه «جاهز للإنتاج» هو وصف للكود لا للأداء.

### P3 — صلابة الترجمة غير مثبتة بعد آخر تعديل

`nadir2.mq5` تغيّر عبر v6.6.16→v6.6.20 (قصص إصلاح كثيرة، منها FREEZE_LEVEL وATR و«لا إشارات»)، وكلها مدعومة بفحوص نصية. **لا يوجد في المستودع سجل F7 حديث بالنسخة الحالية.** هذا هو الفارق الوحيد الذي يفصل «GO مشروط» عن «GO للعرض».

### P4 — التوثيق أمين، وهذه ميزة تُحفظ

`INSTALL_AR.md` و`docs/QSMC_GO_LIVE_RUNBOOK.md` يقولان صراحةً ما لا يُثبت. المراجعة تؤكد ذلك ولا تناقضه. الاستثناء الوحيد: `docs/STAGED_GO_LIVE_LADDER_v6.6.14.md` ما زال يحمل عنوان v6.6.14 بينما المصدر v6.6.20، وقيمه (`InpRiskPercent 0.25%`, `InpMaxDailyLossPercent 2.00%`) أوسع من preset الإنتاج الحالي (`0.10%` / `0.50%`). **سلّم قديم بأرقام أوسع من الإعداد المُسلَّم = فخ تشغيلي.** إمّا يُحدَّث أو يُؤرشف.

---

## 6. الحواجز قبل المال الحقيقي (مرتبة، مع معيار إغلاق)

| # | الحاجز | معيار الإغلاق (قابل للتحقق) |
|---|---|---|
| **B1** | الترجمة | F7 على `nadir2.mq5` ثم `QSMC_AutoTrader.mq5` = **0 errors**، وسجل يحمل `[QSMC_ARB] v6.6.20` و`[QSMC_AT] QSMC v6.620` |
| **B2** | دليل الأداء | ملف `report.md` من `wfa_stats.py` بحالة **GO** فوق نوافذ OOS مجمّعة ≥ 60% رابحة، WFE ≥ 0.5، DSR ≥ 0.95 مع تشتّت محاولات، وp(دخول عشوائي) ≤ 0.05 |
| **B3** | عزل الحالة في الاختبار | نتيجة تجربة F1 مسجّلة (متطابقة أو معزولة لكل تمريرة) |
| **B4** | حضانة demo | 50–100 صفقة أو 2–3 أشهر، ومقارنة: تكرار الصفقات، متوسط السبريد المدفوع، الانزلاق، نسبة الفوز، الـdrawdown — مقابل ما تنبّأ به B2 |
| **B5** | فخ السلّم القديم | تحديث/أرشفة `STAGED_GO_LIVE_LADDER_v6.6.14.md`، وتوقيع حدود المخاطرة الفعلية (0.10% / 0.50% / 3.00%) |
| **B6** | قرار مكتوب على F1/F2/F3 | إمّا إصلاح (يحتاج F7) أو سطر موقّع: «قبلنا أن رقم المخاطرة المطبوع تقديري، وأن الأساس المحفوظ قد يمنع التداول حتى نُعيده» + مراجعة أسبوعية لـ`GlobalVariables` |

**B2 هو الحاجز الحقيقي**: كل ما فوقه إجراءات أيام، وهو يحتاج أسابيع من التشغيل الصادق.

---

## 7. خطة 10 أيام مقترحة

| اليوم | العمل | المخرج |
|---|---|---|
| 1 | F7 للثلاثة ملفات + حفظ السجلات؛ تنفيذ تجربة F1 (عزل الحالة) | سجل بناء + جواب نعم/لا موثّق |
| 2 | `wfa_harness.py plan` على 2018→2026 (IS 24 / OOS 6 / holdout 12) | `plan.json` |
| 3–4 | `configs` + تشغيل تمريرات IS؛ `ingest` | شبكات منظّفة + منحنيات سطح |
| 5 | `plateau` لكل نافذة + `apply` | `selection_applied.json` |
| 6 | تشغيل تمريرات OOS + `ingest` | صفقات OOS مجمّعة |
| 7 | بناء benchmarks (دخول عشوائي بنفس الخروج) + Monte Carlo + `report` | `report.md` أول |
| 8 | إصلاح ما يُصلح (F2/F3/F5) وإعادة F7، أو توقيع قبول المخاطرة | diff + سجل |
| 9 | Stage 1 ثم Stage 2 (demo) | سجل 24–48 ساعة لكل مرحلة |
| 10 | Stage 3 micro + كتابة معايير الإيقاف | ملف kill-criteria موقّع |

---

## 8. ما لم ألمسه، ولماذا

* **لم أعدّل أي ملف `.mq5` / `.mqh`.** كل إصلاح مقترح أعلاه يحتاج F7، وبيئتي لا تملك MetaEditor؛ تعديل غير مُترجَم في نظام يتداول مالًا هو مخاطرة لا مراجعة.
* **لم أضف اختبارًا يفشل** (= يجعله CI أحمر) للبنود F1–F5: بوابات المستودع تعمل اليوم، وإدخال فشل مقصود يعلّم الفريق تجاهل الأحمر — وهو المرض الذي وصفته في P1. الأسطر والأدلة موثّقة هنا لتُنفَّذ مع إصلاحها.
* **ما أضفته:** قسم «عزل الحالة بين التمريرات» في `CONFIGS.md` المولّد + تحذير في مخرجات `configs`، واختباران في `test_wfa_robustness.py` (155 فحصًا الآن) يمنعان حذف هذا التحذير مستقبلًا.

---

## English abstract

**Code quality: high. Production readiness: unproven.** The shipped tree passes every automated
gate this repository owns (44/44 curated, release gate GO with 0 warnings, 155/155 robustness
checks), and the execution path is defensively written (broker-side SL/TP, three arming gates,
retcode classification, freeze-level aware modifications, hard risk ceilings). But nothing in the
repository proves the two things production actually means: that the source **compiles** (no
MetaEditor here) and that the strategy has **an out-of-sample record** (no study exists for this
build). Eight legacy audit suites are red by design (256 failing assertions + one traceback), so
"GO" covers a curated subset, not the whole contract surface.

Two code findings should be closed or explicitly accepted before real money: terminal-global
duplicate-suppression keys are never purged, which can silently suppress signals between
walk-forward passes (10-minute falsification test included), and risk-per-trade is priced with two
different estimators, so the printed risk can differ from the enforced one.

**Verdict: GO for demo/paper conditional on F7 + Stage 1/2; NO-GO for real money until B2 (a
passing walk-forward study) exists.** Nothing here is financial advice; forex trading carries
substantial risk of loss.
