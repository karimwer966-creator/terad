# QSMC v6.6.22 — دليل تشغيل سكالبر M5 (DEMO ثم الحقيقي)

> **اقرأ هذا أولًا، بصراحة:** لا يوجد في هذا المستودع باكتست ولا إحصائية ربح لهذا
> الإعداد. لا أحد — لا أنا ولا الكود — يستطيع أن يخبرك إن كان سكالبر M5 رابحًا على
> زوجك وبوسيطك. ما يلي يضمن شيئًا واحدًا فقط: **أنك تعرف بالضبط ما سيفعله النظام،
> ومتى سيرفض التداول، وكيف توقف الخسارة.** هذا ليس وعدًا بالربح.

---

## 0. ما تم إصلاحه للتو (كان يمنع F7)

| الخطأ | العدد | السبب | الإصلاح |
|---|---|---|---|
| `'why' - constant cannot be modified` | 12 | معامل `const string &why` يُكتب داخله — في MQL5 المرجع الثابت للقراءة فقط، وهو **مخرَج** لا مدخل | أُزيل `const` من `QSMC_ClassifySignal` و`QSMC_ApplyExecClassification` |
| `undeclared identifier 'bullish'/'bearish'/'pattern'` | 3 | `g_candle_intel` نوعه `SCandleIntelligence` (يحمل `confirms_buy`/`confirms_sell`/`description`) لا `SCandleIntel` | صُحّحت الأسماء |
| `implicit conversion from 'unknown' to 'string'` | 1 | نتيجة الخطأ أعلاه | يزول معه |

**والأهم:** هذه الأخطاء مرّت من **كل** الاختبارات offline. لذلك أُضيف
`tools/test_compile_errors.py` — يفحص **صنف الخطأ** لا المثال: أي دالة تكتب داخل
مرجع `const`، وأي وصول لعضو غير موجود في الـ struct الحقيقي. هو الآن داخل البوابة
(52 فحصًا) لن يمرّ هذا النوع مرة أخرى.

> هذا **ليس** ترجمة MetaEditor. اضغط F7 دائمًا.

---

## 1. التركيب — DEMO

1. انسخ `nadir2.mq5` إلى `MQL5/Indicators/` و`QSMC_AutoTrader.mq5` إلى `MQL5/Experts/`.
2. انسخ مجلد `MQL5/Include/QSMC/` كاملًا.
3. في MetaEditor: افتح كل ملف واضغط **F7**. لا تتابع قبل `0 errors, 0 warnings`.
4. افتح شارت **XAUUSD M5** (أو زوجك — لكن M5 إلزامي مع هذا الإعداد).
5. أرفق `nadir2` أولًا، ثم `QSMC_AutoTrader` على نفس الشارت.
6. في نافذة الخصائص: **Load** → `presets/QSMC_AutoTrader_v6.6.22_SCALP_M5.set`

### ما يجب أن تراه في اللوج فورًا

```
>>> v6.6.21 SIGNAL EXECUTION PROFILE: BALANCED
>>>   STRONG   score>=75 rel>=80 rr1>=1.50  allow=ON  risk 1.00x
>>>   MODERATE score>=60 rel>=60 rr1>=1.50  allow=ON  risk 0.50x
>>>   WEAK     score>=40 rel>=50 rr1>=1.20  allow=OFF  risk 0.25x
[QSMC_AT] ARMED PLAN | ... | DEMO
```

إن لم يظهر `ARMED PLAN` فالإعداد لم يُحمَّل.

---

## 2. مراجع النظام — اللوج الذي تقرأه فعليًا

قبل كل صفقة يطبع الخبير 12 سطرًا:

```
[QSMC_ENTRY_REVIEW] BEGIN key=... BUY XAUUSD @ 2319.40 class=STRONG_VALID
[QSMC_ENTRY_REVIEW]   PASS  R1  CLASS - STRONG_VALID executable (mult 1.00x)
[QSMC_ENTRY_REVIEW]   PASS  R2  ACCOUNT - DEMO armed
[QSMC_ENTRY_REVIEW]   PASS  R3  TICK_AGE - 0s old (cap 30s)
[QSMC_ENTRY_REVIEW]   PASS  R4  SPREAD - 18 pts (abs cap 25) = 3.1% of a 580-pt stop (share cap 10%)
[QSMC_ENTRY_REVIEW]   PASS  R5  SESSION - inside the session window
[QSMC_ENTRY_REVIEW]   PASS  R6  TRADES_TODAY - 1 of 6 today
[QSMC_ENTRY_REVIEW]   PASS  R7  OPEN_POSITIONS - 0 of 1 open on XAUUSD
[QSMC_ENTRY_REVIEW]   PASS  R8  GEOMETRY - sl 2318.20 / price 2319.40 / tp 2321.80
[QSMC_ENTRY_REVIEW]   PASS  R9  RR_AT_FILL - RR 1.71 at fill (floor 1.30)
[QSMC_ENTRY_REVIEW]   PASS  R10 STOPS_LEVEL - broker stops/freeze level accepts this SL/TP
[QSMC_ENTRY_REVIEW]   PASS  R11 RISK_SIZE - 0.12 lots = 0.25% of equity at the stop
[QSMC_ENTRY_REVIEW]   PASS  R12 NO_OPPOSITE - no opposite position of this magic
[QSMC_ENTRY_REVIEW] END verdict=READY
```

والمؤشر قبل ذلك يطبع **شروط الاستراتيجية** الاثني عشر
(`01 LIQUIDITY_SWEEP` … `12 NO_CONFLICT`).

> **أي `FAIL` يعني أن الصفقة لم تُفتح، والسبب مكتوب في السطر نفسه.** لا يوجد
> "رفض صامت".

---

## 3. ماذا تفعل في فترة DEMO (إلزامي)

| المدة | ما تراقبه |
|---|---|
| **أسبوع 1** | هل تظهر صفقات أصلًا؟ اقرأ `verdict=READY` مقابل `BLOCKED by R4 SPREAD`. إن كان السبب دائمًا السبريد فوسيطك غير مناسب لهذا الأسلوب. |
| **أسبوع 2–3** | عدد الصفقات/يوم، ومتوسط RR المحقق، ونسبة الفوز. **سجّلها بنفسك** — النظام لا يزعم أنها جيدة. |
| **قبل الحقيقي** | اقرأ `waiver`/`REJECT` في heartbeat: هل يرفض لأسباب منطقية أم دائمًا نفس السبب؟ |

**لا تنتقل للحقيقي** إذا: لم تُفتح أي صفقة، أو كل الصفقات ضربت الوقف، أو لم تفهم
سطرًا واحدًا من سطور المراجع.

---

## 4. تشغيل الحقيقي — الخطوات التي **أنت فقط** تستطيع فعلها

ملف `QSMC_AutoTrader_v6.6.22_SCALP_M5.set` يُشحن و**REAL معطّل**:
`InpAllowRealTrading=false` و`InpRealAccountConfirm=` فارغ و`InpRealServerConfirm=` فارغ.

**لن أضع رقم حسابك أو اسم سيرفرك — لا أعرفهما، ولن أخترعهما.** املأهما بنفسك:

1. على حسابك الحقيقي، افتح `Journal` → ستجد `login` و`server` (أو من نافذة الحساب).
2. في خصائص الخبير، اكتب **حرفيًا**:

| Input | القيمة |
|---|---|
| `InpAllowRealTrading` | `true` |
| `InpRealAccountConfirm` | رقم حسابك بالضبط، مثال `51234567` |
| `InpRealServerConfirm` | اسم السيرفر بالضبط، مثال `ICMarketsSC-Live12` |

3. اضغط OK. ستظهر في اللوج:

```
[QSMC_AT] REAL AUTHORIZED | login 51234567 | server ICMarketsSC-Live12
[QSMC_AT] REAL profile: risk 0.25% / daily 1.00% / DD 4.00% (HARD 0.50 / 2.00 / 8.00)
```

إن ظهر أي شيء آخر (`REAL REFUSED …`) فالمطابقة فشلت — **لا تتداول**.

### الحمايات التي ستبقى تعمل حتى بعد التصريح

- **سقف صلب**: 0.50% للصفقة / 2.00% لليوم / 8.00% للسحب — لا input يتجاوزها.
- **`VerifyPositionOpened`** قبل عدّ الصفقة: retcode ناجح بلا مركز مُتحقَّق ≠ صفقة.
- **ملكية التنفيذ**: خبير ثانٍ على نفس الحساب يرفض نفس الإشارة بدل مضاعفتها.
- **3 خسائر متتالية** = توقف. **100% drawdown من القمة** لا، بل 4% = توقف.
- **`InpResetBreakersAtInit=false`**: إعادة التشغيل لا تمسح أي قاطع.

---

## 5. إيقاف الطوارئ

| المستوى | الإجراء |
|---|---|
| إيقاف الدخول الجديد فقط | `InpEnableTrading=false` (المراكز المفتوحة تُدار) |
| إيقاف كل شيء | إزالة الخبير من الشارت (ستوب/تيبي موجودة على السيرفر تبقى) |
| مسح القواطع يدويًا | `InpResetBreakersAtInit=true` **لمرة واحدة** ثم أرجعه `false` |

---

## 6. ما لا يضمنه هذا النظام

- ❌ **لا يضمن ربحًا.** قد يخسر.
- ❌ **لم يُشغَّل على DEMO بعد** — أنت أول من يشغّله.
- ❌ **لم يُترجم بـ F7 بعد** — الإصلاحات أعلاه تخص أخطاء عرفناها من فحصك؛ قد تظهر أخرى.
- ❌ **لا باكتست.** أي رقم هنا (0.25% إلخ) هو **سقف مخاطرة**، لا توقع نتيجة.
- ✅ يضمن: أن كل صفقة تُفتح بعد 12 شرطًا استراتيجيًا + 12 شرط تنفيذ، وأن الخسارة
  محدودة بسقوف معلنة، وأن سبب كل رفض مكتوب.
