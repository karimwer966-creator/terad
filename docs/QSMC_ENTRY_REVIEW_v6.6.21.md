# QSMC v6.6.21 — مراجع نظام الدخول (Entry Review)

> **ما هذا الملف:** المرجع الوحيد لسلسلة الشروط التي يجب أن تتحقق قبل فتح صفقة،
> وكيف تُسجَّل كل واحدة منها في اللوج. لا يقرأه الكود؛ الكود يطبّقه والاختبارات تثبته.
>
> **ليس هذا:** نتيجة باكتست، ولا وعد ربح، ولا دليل أن MetaEditor يترجم الملف.
> F7 وتشغيل DEMO يبقيان بوابتين بشريتين.

---

## 1. لماذا "مراجع" وليس "بوابة" أخرى

البوابات (`InpMinConfidenceScore` / `InpMinReliability` / `InpMinRR1` / TopDown…)
**تقرر**. المراجع **لا يقرر شيئًا** — بل يسجّل كل شرط بنتيجة `PASS` أو `FAIL`
مع الرقم الذي رآه، في اللحظة التي تُؤكَّد فيها الإشارة أو تُرسَل فيها الصفقة.

الفرق عملي: عندما لا تُفتح صفقة، اللوج يقول **أي شرط بالتحديد** رفضها، لا "لا إشارة".

---

## 2. سلسلة الشروط الكاملة (المؤشر — nadir2.mq5)

الترتيب هو الترتيب الحقيقي في الكود، وهو عقد يثبته
`tools/test_signal_execution_profiles.py`.

| # | الشرط | أين | ملاحظة |
|---|---|---|---|
| 1 | **سحب سيولة** (Liquidity Sweep) | `sweep_event_id != ""` + `sweep_price>0` | لا يوجد سحب = لا يوجد فكرة |
| 2 | **جهة السحب** | `sweep_price` مقابل حدود الزون | **BUY يجب أن يسحب قيعان (sell-side)**؛ سحب قمة ثم شراء = مطاردة اختراق لا انعكاس |
| 3 | **Displacement** | `displacement_event_id` | لا اندفاع = لا نية مؤسسية |
| 4 | **MSS** (كسر هيكل) | `structure_event_id` | عكس الهيكل ضد الجهة المسحوبة |
| 5 | **POI** (OB/FVG سببي) | `zone_event_id` + `zone_top>zone_bottom` | الزون مربوطة بالاندفاع نفسه |
| 6 | **الموقع** | دخول داخل الزون + DISCOUNT للشراء / PREMIUM للبيع | `g_quant.pd_position` |
| 7 | **شمعة الانعكاس** | `g_candle_intel.bullish/bearish` + score | شمعة مغلقة فقط، لا تشكيل |
| 8 | **تحيز HTF** | `g_d1_structure_state` يوافق أو محايد | معارضة صريحة = فشل |
| 9 | **الجلسة** | `g_quant.session_label != OFF` | ASIA/LONDON/NY/OVERLAP |
| 10 | **السبريد** | مطلق (`InpMaxSpreadPts`) **و** نسبي (≤10% من الوقف) | 60 نقطة لا شيء أمام وقف 5000 وفاتلة أمام 25 |
| 11 | **الهندسة** | `sl < entry < tp` + `RR1 ≥ QSMC_RRAcceptFloor()` | يُقاس على الخطة لا على السعر الحالي |
| 12 | **لا تعارض** | لا يوجد setup معاكس حي على نفس الشمعة | |

ثم يأتي **التصنيف** (`QSMC_ClassifySignal`) و**الملف** (`ENUM_SIGNAL_EXECUTION_PROFILE`):

| الفئة | score | reliability | RR1 | مضاعف المخاطرة |
|---|---|---|---|---|
| `WEAK_VALID` | ≥ 40 | ≥ 50 | ≥ 1.20 | **0.25×** |
| `MODERATE_VALID` | ≥ 60 | ≥ 60 | ≥ 1.50 | **0.50×** |
| `STRONG_VALID` | ≥ 75 | ≥ 80 | ≥ 1.50 | **1.00×** |

- `STRICT` = STRONG فقط · `BALANCED` = MODERATE+STRONG · `PERMISSIVE` = الثلاثة.
- `InpAllowWeakSignals` / `InpAllowModerateSignals` مفتاحان صريحان؛ **كلاهما `false` افتراضيًا**،
  لذا السلوك الافتراضي = STRICT تمامًا ولا يتغير شيء حتى تُشغّلها بنفسك.
- لا بروفايل يسمح أبدًا بإشارة: مُبطلة، منتهية، بلا وقف، أو بلا بيانات جاهزة.

**اللوج:**
```
[QSMC_ENTRY_REVIEW] BEGIN setup=… dir=BUY entry=… sl=… tp1=… class=STRONG_VALID verdict=READY
[QSMC_ENTRY_REVIEW]   PASS 01 LIQUIDITY_SWEEP - swept 2318.40000 on bar 412
[QSMC_ENTRY_REVIEW]   PASS 02 SWEEP_SIDE - swept 2318.40000 vs zone 2319.10000-2321.50000 (sell-side (lows))
…
[QSMC_ENTRY_REVIEW] END pass=12/12 fail=0 verdict=READY
[QSMC_SIGNAL_AUDIT] stage=CONFIRM setup=… class=STRONG_VALID score=82 reliability=85 rr1=1.80 risk_mult=1.00 profile=PERMISSIVE why=published review=READY 12/12
```

---

## 3. مراجع التنفيذ (QSMC_AutoTrader — قبل إرسال الأمر)

المراجع هنا لا يعيد تقييم الإشارة، بل **يعيد قراءة الحساب والسوق** في اللحظة الأخيرة،
لأن هذه هي الأشياء التي تتغيّر بين نشر المؤشر ووصول الأمر.

| # | الفحص | يمنع |
|---|---|---|
| R1 | CLASS | فئة غير مسموحة في هذا الملف |
| R2 | ACCOUNT | حساب REAL غير مُصرَّح / تبويب محظور |
| R3 | TICK_AGE | تيك متجمد / انقطاع |
| R4 | SPREAD | سبريد فوق السقف المطلق أو نسبة الوقف |
| R5 | SESSION | خارج نافذة الجلسة |
| R6 | TRADES_TODAY | تجاوز السقف اليومي |
| R7 | OPEN_POSITIONS | تجاوز عدد المراكز |
| R8 | GEOMETRY | `sl<entry<tp` على السعر الحالي |
| R9 | RR_AT_FILL | RR بعد الانزلاق أقل من `InpMinRRAtFill` |
| R10 | STOPS_LEVEL | وسيط يرفض SL/TP |
| R11 | RISK_SIZE | لا يوجد حجم عند مخاطرة الفئة |
| R12 | NO_OPPOSITE | مركز معاكس حي |

كل سطر يُطبع `PASS` أو `FAIL`. أي `FAIL` يوقف الصفقة ويسمّي الشرط.

---

## 4. الحمايات التي لا يفتحها أي بروفايل

- سقف المخاطرة الصلب: **0.50% / 2.00% / 8.00%** لكل صفقة / يوم / سحب.
- مضاعف الفئة **لا يرفع** أبدًا فوق الأساس (مضبوط ≤ 1.0).
- ملكية التنفيذ عبر الخبيرين: `QSMC_EXEC_OWNER_<login>_<magic>_<key>` — الثاني يرفض.
- هوية الإشارة مقيّدة بـ `login + magic + symbol + bar + direction`.
- REAL يبقى معطّلًا ما لم تتحقق الشروط السبعة (`InpAllowRealTrading` + login + server…).

---

## 5. كيف تتحقق بنفسك

```bash
python3 tools/test_signal_execution_profiles.py   # 98 عقدًا على المصدر + نموذج مرجعي
python3 tools/check_production_ready.py           # 47 فحصًا منسّقًا
```

ثم **يدويًا**: F7 في MetaEditor، وتشغيل DEMO، وقراءة أول 20 سطرًا من
`[QSMC_ENTRY_REVIEW]` للتحقق من أن الشروط التي تتوقعها هي التي تُطبع.
