# التجربة جاهزة — XAUUSD / M15 (الدليل المصغّر)

الحالة: **جاهز للتركيب والتجربة على DEMO فقط.** كل ما يتطلب جهازك (تجميع، تشغيل،
forward) موسوم NOT VERIFIED حتى تُرجع السجلات.

## 1. الحزمة (موقّعة ومرتبة)

- المسار: `out/release/QSMC_v6.6.22_production.zip`
- sha256: `4e65019b345d11c2e0f78abd5ebfce4fe99ca0b68c4ca4e809372e75c79ef27c`
- بُنيت عند `5a8bc7a` (= `main` بعد دمج PR #80)، بتاريخ 2026-11-20.
- الداخل: `MQL5/Indicators/nadir2.mq5`، `MQL5/Experts/QSMC_AutoTrader.mq5`،
  الأدوات، كل `Include/QSMC` الموثقة، presets، docs مختارة — **بدون .ex5**.
- المستثنى عمدًا: `QSMC_OpportunityFunnel.mqh` (غير موصول ولا يُدرَّج في تخطيط
  الإنتاج) و`QSMC_FixedRangeDump.mq5` (تشخيص فقط؛ يُركَّب يدويًا عند الحاجة).
  هذا يحقق بوابة G2 على التخطيط الموثق.
- `MANIFEST.txt` داخل الحزمة يسجل: الفرع، الـ commit، `NOT COMPILED HERE`،
  البوابات. صحتها تُفحص من `MANIFEST.txt` نفسه.

## 2. البوابات (على هذا الفرع، offline)

- `tools/check_production_ready.py` — curated gate: **OFFLINE GO**.
- `tools/check_release_gate.py` — **GO (1 warning)**: `G2 headers present but not
  in the documented layout: QSMC_OpportunityFunnel.mqh` — تحذير سليم ومقصود
  (الحضور في الشجرة، لا في الحزمة)؛ لم تُعدَّل البوابة لإسكاته.
- `tools/check_repo_layout.py` — **8/8** (الحزمة تحت `out/` المصرّح بها فقط).
- دمج PR #80 مرّت فحوص CI خضراء قبل الدمج.

## 3. خطوات التجربة (Windows، DEMO أولًا)

1. افتح Data Folder بالطرفية، أغلقها، فك الضغط في الجذر، أعد الفتح.
2. MetaEditor → F7 بالترتيب: `nadir2.mq5` → `QSMC_AutoTrader.mq5` →
   `QSMC_ArbiterTest.mq5` → `QSMC_ResetGuards.mq5` (اختياري:
   `QSMC_FixedRangeDump.mq5`). المطلوب: `0 error(s)` لكل ملف.
   أي خطأ: توقف وأرسل لي السجل كاملًا.
3. الأسبوع الأول — **ملاحظة فقط**: شارت XAUUSD M15، الـ EA بـ
   `QSMC_AutoTrader_DIAG_XAUUSD_M15.set` (`InpEnableTrading=false`/`InpDryRun=true`).
   سجّل `Experts`/`Journal` كاملة + الأسطر التي تبدأ `[QSMC_AT]`.
4. الأسبوع 1–2 — **DEMO مسلح بحذر**: `QSMC_AutoTrader_DEMO_0.10_200.set`
   (0.10 لوت، وقف 200، صفقة واحدة، 3/يوم، جلسة 10:00–18:00 بتوقيت السيرفر).
   بعد أول إقلاع: اقرأ `[QSMC_AT] ARMED PLAN` و`LOT CHECK`، واضبط
   `InpResetBreakersAtInit=false` ثم أعد التحميل.
5. **قبل أي REAL**: 8 أسابيع DEMO أو 30 صفقة مغلقة (أيهما أطول) + مراجعة
   مكتوبة. REAL قرار مستقل موثق منك وحدك — لا بريست مرفوق يسلّحه.
6. شروط الإيقاف الفورية وإجراء ~$54 موصوفة في
   `docs/QSMC_PERSONAL_PRODUCTION_AR.md` (القسمان 4 و5) — اقرأهما قبل التشغيل.

## 4. ما أحتاج أن تُرجعه لي

- سجل F7 لكل مصدر (السطر الأخير `0 error(s)`).
- سطر الـ selftests من `Experts` عند init.
- بانر `ARMED PLAN` + `LOT CHECK` من أول attach.
- ملخص أسبوع التشغيل الأول: عدد الصفقات، أي breaker انطلق، retcodes، slippage.
- اختياري: CSV من `QSMC_FixedRangeDump` لنطاق فيه نشاط CORE.

## 5. ما لا يُدّعى حتى الآن

لا تجميع/تشغيل/اختبار من بيئة التأليف؛ لا تكافؤ؛ لا ربحية؛ لا جهوزية حساب
حقيقي؛ لا تغيير أي حماية/عتبة/magic/TF؛ الأداء الحقيقي يُقيّم فقط من نافذتك
الأمامية المتراكمة. PR #80 مدمج في `main` وهو مرجعك الوحيد لهذه الحزمة.
