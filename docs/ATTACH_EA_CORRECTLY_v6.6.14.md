# كيف تُرفق QSMC بشكل صحيح على الشارت (v6.6.14)

إذا كنت ترى المؤشر يُحلل على الشارت لكن لا تُفتح صفقات أبداً، فهذا غالباً لأن
**الـEA لم يُرفق بعد** أو أن المؤشر يعمل ببروفيل STRICT بينما تتوقع إشارات من
نماذج 64/100 مثل التي ظهرت اليوم على XAUUSD M15.

## الدليل من الشارت على أن الـEA ليس مرفقاً

- أعلى يمين الشارت: لا يوجد "وجه مبتسم" 😊 لـQSMC_AutoTrader. الوجوه التي
  تراها هناك هي لمؤشرات/خبراء آخرين (مثل KLJ_DataFeeder).
- تبويب **Experts** في الأسفل لا يظهر سطور `[QSMC_AT]` أو `[QSMC_ARB]`.
- علامة التبويب النشطة في الأسفل هي `Trade` وليس `Experts`.

## التسلسل الصحيح (يعمل على XAUUSD M15 أو M30)

1. اضغط **F7** في MetaEditor على `nadir2.mq5` ثم على
   `MQL5/Experts/QSMC_AutoTrader.mq5`. تأكد من 0 errors.
2. اسحب **nadir2.ex5** من نافذة Navigator → Indicators إلى شارت
   **XAUUSD M15**.
3. في نافذة الإعدادات الخاصة بالمؤشر → تبويب Inputs → **Load** →
   اختر الملف `presets/nadir2_PRODUCTION_XAUUSD.set`. اضغط OK.
4. انتظر حتى يكتمل تحميل التاريخ وتظهر جميع مناطق Sniper / Zones
   على الشارت (قد يستغرق 10–20 ثانية). تأكد في الـJournal من سطور
   `v6.6.14 PRODUCTION BUILD` وكل self-test: PASS.
5. الآن اسحب **QSMC_AutoTrader.ex5** من Navigator → Experts إلى
   **نفس الشارت**.
6. في نافذة إعدادات الـEA → Inputs → **Load** → اختر
   `presets/QSMC_AutoTrader_STAGE1_PRACTICAL_DRYRUN.set`.
7. قبل الضغط على OK، تأكد من ✅ **Allow Algo Trading**.
8. اضغط OK.

## ما الذي يجب أن تراه بعد الرفق الناجح

في تبويب **Experts** (وليس Journal) من المفترض أن ترى خلال ثواني:

```
[QSMC_ARB] v6.6.14 arbitration layer ON | preset INTRADAY (M15-H1) ...
[QSMC_AT] QSMC v6.614 execution companion ON | XAUUSD M15 | magic 20261027 |
          mode RISK% risk 0.25% | tp ...
[QSMC_AT INSTANCE] authority=private iCustom DEFAULT inputs;
                   Default input hash and diagnostics: [QSMC_INSTANCE], ABI v2 ...
[QSMC_AT] envelope: risk<= 0.25% daily_stop 2.00% minRR 1.00 ...
[QSMC_AT] discipline: session ALL, cooldown 0s, max 0/day ...
```

وكل ~30 ثانية في تبويب Experts سطر "heartbeat" يُظهر verdict المؤشر
ورقم الكود (10-34) واسم البوابة.

## ما معنى "NEEDS: structure / confidence 64/100"؟

بروفيل STRICT الافتراضي يطلب **ثقة ≥75 وموثوقية ≥80** قبل الإشارة. الإشارة
في الشارت التي رأيتها (BUY @ 4038 بثقة 64) لا تجتاز STRICT، لذلك تُرفض —
هذا سلوك دفاعي صحيح وليس عطل. بروفيل PRACTICAL المُضمّن في البريستات يُخفّض
العتبة إلى ≥60 ثقة و≥60 موثوقية مع الحفاظ على جميع قواعد المخاطر.

## ما الذي تغير في v6.6.14-build بعد إرسالك اللقطة؟

- تحذير `cannot be used for static allocated array` في السطر 1297 تم
  إصلاحه (المصفوفة صارت ديناميكية).
- تكرار تسميات "SNIPER MS 1.00" على الشارت تم إصلاحه: لم يعد الـرسم
  يضع label مكرر فوق الـrectangle؛ الآن التسمية الكاملة تبقى داخل
  الـrectangle مع شريط قصير على الحافة فقط.
- خفض سقف الكائنات على الشارت من 1200 إلى 500 لإزالة الفوضى البصرية
  (InpMaxChartObjects=500).
