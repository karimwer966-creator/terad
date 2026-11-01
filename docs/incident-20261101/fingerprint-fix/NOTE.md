# إصلاح أخطاء QSMC_InputFingerprint.mqh المبلغ عنها من MetaEditor

## السبب المؤكد

المستخدم أرسل نتيجة F7: **32 errors, 0 warnings**. تطابقت ثمانية مواضع مع أسطر multi-declarator مثل:

```mql5
input int InpAsianStart = 9, InpAsianEnd = 18;
```

regex القديم التقط اسم Start فقط واعتبر `9, InpAsianEnd = 18` قيمة افتراضية واحدة. ولّد تعبيرًا لا يقبله MQL5، وأغفل End من البصمة. فحص freshness القديم كان يقارن ناتج المولّد بنفسه، ولذلك لم يكشف فساد الصياغة أو نقص التغطية. هذه ثغرة في الاختبارات السابقة، لا مشكلة في مدخلات المستخدم.

## الإصلاح

- فصل جميع declarators على الفواصل ذات المستوى الأعلى مع احترام strings، color literals والأقواس.
- إزالة التعليقات دون تغيير محتوى literals، ودعم declarations متعددة الأسطر.
- رفض declarations غير المدعومة/غير المكتملة بدل إسقاطها بصمت.
- إعادة توليد header: **576 متغيرًا بدل 568**؛ أُضيفت ثمانية End، وصُحّحت defaults الثمانية لـStart. لا تغيير لتعريفات Inputs أو ترتيبها في المؤشر أو buffers أو gates.
- `main` guard يمنع كتابة ملفات بمجرد استيراد المولّد في الاختبارات.

## الدليل والاختبارات

- `before.log`: الاختبار الجديد يفشل قبل الإصلاح بسبب غياب InpAsianEnd.
- `test_input_fingerprint_parser.py`: الثمانية End، القيم الافتراضية، strings ذات commas/semicolons/escaped quotes، التعليقات، multiline، nested calls، color literal، ورفض الصياغة المعيبة.
- نفس الاختبار يترجم الدالة المولّدة الفعلية بـC++ مع stubs للـMQL primitives والـenum/color، ويثبت تساوي runtime/default checksum عند defaults وتغيّر runtime عند تغيير كل End على حدة. **هذا ليس MQL compilation** ولا يثبت قيم enum الحقيقية.
- **47 فحصًا محليًا ناجحًا**: الفحوص الإلزامية الأربعة وجميع 43 ملفات `tools/test_*.py`. النتائج المنفصلة و`summary.txt` في هذا المجلد. لم تُخفف أي assertion قديمة أو بوابة تداول لإمرار الإصلاح.

## تحقق المنصة المطلوب

1. انسخ `MQL5/Include/QSMC/QSMC_InputFingerprint.mqh` المصحّح إلى Include/QSMC في نفس terminal الذي تستخدمه. احتفظ أيضًا بالمولّد المصحّح في المستودع؛ لا تصلح generated header وحده يدويًا.
2. نفّذ F7 لـ`nadir2.mq5` وأرسل سجل compilation الجديد. لا يمكن تأكيد اختفاء كل الأخطاء أو 0 warnings دون ذلك السجل.
3. أعد تحميل المؤشر بعد البناء؛ checksum ستتغير بسبب اكتمال المدخلات. وحّد نسخة host المستخدمة للمرئي ولـiCustom، ولا تفسّر اختلاف بصمات نسختين مختلفتين على أنه اختلاف إعدادات فقط.
4. عند defaults تحقق تساوي actual/default hash، ثم غيّر أحد متغيرات End وتحقق تغيّر actual وحده. لا تغيّر إعدادات تداول على حساب حي لهذا الاختبار.
