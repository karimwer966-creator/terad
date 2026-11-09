# شجرة نظام QuantumAutonomousTradingSystem — System Architecture

**النظام:** QuantumAutonomousTradingSystem (QATS) v1.10
**نوع الملف:** خبير MQL5 واحد مستقل (Standalone Expert Advisor) — `MQL5/Experts/QuantumAutonomousTradingSystem.mq5`
**التاريخ:** 2026-11-09 · الفرع: `arena/f83fc236-terad` · PR #56

> قراءة سريعة: هذا المستند يشرح **شجرة النظام** — الطبقات، المكوّنات، تدفّق البيانات من الشمعة
> المغلقة إلى الأمر الفعلي على خادم DEMO، خريطة الملفات، وجداول الحراس والحدود.
> كل قرار تنفيذي يمر عبر **خط أنابيب واحد مغلق**، وكل ما لا يمر به لا يُنفَّذ.

---

## 1. شجرة النظام — System Tree

```
QATS (QuantumAutonomousTradingSystem.mq5)
│
├─► [A] طبقة الإقلاع والتحقق — Bootstrap & Verification
│     ├─ OnInit()
│     ├─ LoadSymbolSpec()            مواصفات الرمز من الوسيط (لا افتراضات)
│     ├─ VerifyAccountProtection()   حارس DEMO الإلزامي + الصلاحيات
│     ├─ إنشاء مقابض المؤشرات (iMA/iATR ×9) + ReleaseHandles()
│     └─ InitDealWatermark()         علامة مرجعية للصفقات المغلقة
│
├─► [B] طبقة حماية رأس المال — Capital Protection (تُعاد فحوصها كل قرار)
│     ├─ UpdateDailyGuards()   baseline يومي + HWM + قفل اليوم + وقف السحب
│     ├─ ProcessClosedDeals()  كرة الثلج: صفقات خاسرة متتالية → تهدئة
│     ├─ EntriesAllowed()      السلسلة الكاملة للأذون قبل أي أمر
│     └─ Persisted GVs         تبقى عبر إعادة تشغيل الشارت (لا تُصفَّر)
│
├─► [C] طبقة بيانات السوق — Market Data Engine (Closed Bars Only)
│     ├─ CopyBuffer/iHigh/iLow…    بيانات رسمية مغلقة فقط (shift ≥ 1)
│     ├─ LoadReading()             لقطة موحّدة D1/H4/H1/M15/M5 + ATR + VWAP + Volume
│     ├─ SessionVWAP()             VWAP جلسة اليوم (من بداية يوم الخادم)
│     └─ SmaVolume()               متوسط حجم التيك M5 (20 شمعة)
│
├─► [D] طبقة التحليل — Smart Money Concepts Engine
│     ├─ FindSwings()              نقاط انعكاس مؤكدة (fractal k=2)
│     ├─ HighestHigh/LowestLow()   dealing range + أهداف السيولة
│     ├─ BuildLiquidityPools()     PDH/PDL/PWH/PWL + equal highs/lows
│     ├─ DetectSweep()             اكتساح السيولة ثم إغلاق داخلها
│     ├─ DetectDisplacement()      شمعة اندفاعية (جسد ≥ 0.8×ATR)
│     ├─ FindOrderBlock()          كتلة الأوامر = آخر شمعة معاكسة قبل الاندفاع
│     ├─ FindFVG()                فجوات القيمة العادلة (3 شمعات)
│     ├─ DealingRangePosition()    موقع السعر داخل النطاق (Premium/Discount)
│     ├─ M15Confirms()             تأكيد الإطار M15
│     └─ M5Trigger()               إشارة الدخول M5 (Engulfing/Pin/Marubozu)
│
├─► [E] طبقة التسجيل — Confluence Scoring (0..100)
│     ├─ D1 توافق 20 · H4 توافق 15 · H1 بنية 20/10
│     ├─ اكتساح 15 · اندفاع 10 · منطقة OB/FVG 10/5
│     ├─ Premium/Discount 5 · Volume 5 · VWAP 5 · M15 5 · M5 5
│     ├─ Hard Veto: D1 وH4 ضدّان معاً ⇒ رفض (إن فُعِّل)
│     └─ عتبة: InpMinScore = 65
│
├─► [F] طبقة التخطيط — Trade Plan (Entry/SL/TP)
│     ├─ BuildTradePlan()     SL = max(ATR×1.5, مدى M5×3) + هامش الوسيط
│     ├─ صيغة التحقق: stopsLevel / freezeLevel / InpMin|MaxStopPoints
│     └─ TP: أقرب سيولة معاكسة إن حققت RR ≥ InpMinRR، وإلا RR×2.0
│
├─► [G] طبقة المخاطر — Dynamic Position Sizing
│     ├─ EffectiveRiskPercent()   Equity × pct، سقف إدخال ثم سقف صلب 2.0%
│     └─ CalcPositionVolume()     Risk$ ÷ ((StopDist÷TickSize)×TickValue)
│           → Floor to step → Clamp min/max → ملاءمة الهامش (shrink loop)
│
├─► [H] طبقة التنفيذ — Execution Engine (CTrade)
│     ├─ ExecuteSignal()      Spread guard → Order BUY/SELL (SL/TP على الخادم)
│     ├─ IsTransientRetcode() 10004/10012/10020/10021/10024/10031 → إعادة (≤3)
│     ├─ IsSuccessRetcode()   10009/10010 فقط تُعد نجاحاً
│     ├─ VerifyPositionOpened() تحقق من وجود مركز فعلي على الخادم + طباعة SL/TP
│     └─ ProcessPendingRetry()   إعادة محدودة بمعدل ≤ مرة كل 5 ثوانٍ
│
├─► [I] طبقة إدارة المراكز — Position Management (كل tick)
│     ├─ ManagePositions()    SL مفقود ⇒ إعادة بناء فورية من ATR (حماية)
│     ├─ Break-even @ +1R     يُحرَّك مرة واحدة إلى الدخول (لا يُوسَّع أبداً)
│     ├─ Partial Close @ +1.5R  تثبيت 50% (Hedging: بالرقم، Netting: تلقائي)
│     └─ Opposite-signal close  إغلاق على إشارة معاكسة (اختياري)
│
└─► [J] طبقة التشخيص — Diagnostics
      ├─ Heartbeat()         "[QATS][HB]" كل InpHeartbeatSeconds
      ├─ DrawPanel()          لوحة Comment() على الشارت
      ├─ OnTradeTransaction() سجل كل صفقة بختم الأداة
      └─ [QATS][SKIP/ORDER/VERIFY]  كل قرار مع سببه الكامل
```

---

## 2. تدفّق القرار — من الشمعة إلى الأمر

```
OnTick()
  │
  ├─ UpdateDailyGuards()        (baseline/HWM/قفل اليوم/السحب/التهدئة)
  ├─ ManagePositions()          (BE / partial / SL-rescue)
  ├─ ProcessPendingRetry()      (أوامر رُفضت TRANSITIENT، ≤1 كل 5 ثوانٍ)
  │
  ├─ هل بدأت شمعة M5 جديدة؟ (g_lastBarM5)  ── لا ──► HB + Panel ثم انتهاء
  │                                        │
  │                                        نعم
  ▼                                        ▼
ProcessClosedDeals()                 AnalyzeMarket()
(كرة-الخسارة ← watermark)            D1 → H4 → H1(SWING) → LIQUIDITY
                                     → SWEEP → DISPLACE → MSS/BOS
                                     → OB / FVG → PREMIUM/DISCOUNT
                                     → M15 → M5
                                          │
                              Score < 65? ── نعم ──► [SKIP] + السبب
                                          │ لا
                              EntriesAllowed()? ── لا ──► [SKIP] + الحارس
                                          │ نعم
                              require zoneTouch & غير ملموسة؟ ──► [SKIP]
                                          │
                              BuildTradePlan() ── SL غير صالح؟ ──► [SKIP]
                                          │ صالح
                              CalcPositionVolume() ── الحجم < broker min؟ ──► [SIZE] refusal
                                          │
                              ExecuteSignal() → CTrade.Buy/Sell(SL,TP)
                                          │
                              retcode ∈ {10009,10010}? ── لا ──► transient? → retry≤3 : abandon
                                          │ نعم
                              VerifyPositionOpened() → [VERIFY] POSITION CONFIRMED
                              (+طباعة SL/TP كما يراه الخادم فعلياً)
```

---

## 3. الخريطة الملفية — File Map

```
terad/
├── MQL5/Experts/QuantumAutonomousTradingSystem.mq5   ← ملف النشر الوحيد (v1.10)
├── tools/verify_quantum_ea.py                        ← فحص بنيوي offline (ليس مترجم)
├── docs/SYSTEM_ARCHITECTURE.md                       ← هذا المستند
├── docs/PRODUCTION_AUDIT_2026-11-09_QUANTUM_EA.md    ← تقرير التدقيق والتنظيف
├── docs/PRODUCTION_VERIFICATION_2026-11-09_QUANTUM_EA.md  ← تقرير التحقق (Phases 1–7)
├── docs/incident-20261101/                           ← سجل حادثة سابق (محفوظ كما هو)
└── .github/workflows/quantum-verify.yml              ← CI: الفحص البنيوي فقط
```

**شجرة النشر على جهاز Windows + MT5:** انقل ملف `.mq5` واحداً إلى `MQL5\Experts\` ثم F7. لا شيء آخر.

---

## 4. جداول الحراس والحدود (كودياً، لا وعدياً)

| الحارس | المصدر | القيمة الافتراضية |
|---|---|---|
| حساب DEMO فقط | `ACCOUNT_TRADE_MODE==DEMO` عند الإقلاع **وعند كل قرار دخول** | إلزامي، لا يوجد مدخل لإلغاءه |
| صلاحية الطرفية/الخبير/الرمز | `TERMINAL_TRADE_ALLOWED` + `MQL_TRADE_ALLOWED` + `ACCOUNT_TRADE_ALLOWED` + `SYMBOL_TRADE_MODE_FULL` | تُعاد فحوصها كل قرار |
| مخاطرة/صفقة | `Equity × EffectiveRiskPercent()` | 0.50% (إدخال ≤ ceiling ≤ سقف صلب 2.0%) |
| وقف الخسارة | max(ATR×1.5, 3×M5 bars) + broker buffer | **لا توجد صفقة بلا SL** |
| هدف الربح | سيولة معاكسة (RR≥1.5) أو 2.0R | لا يُقصَّر عن RR 1.5 |
| خسارة يومية | Equity-baseline مثبّت يومياً (GV بتاريخ اليوم) | 2.0% أو `InpMaxDailyLossMoney` |
| سحب الحساب | HWM مثبّت (GV `…_hwm`) — v1.10: يُحفظ عند أول رؤية | 8.0% من القمة |
| خسائر متتالية | 3 × `DEAL_PROFIT<0` ⇒ تهدئة 60 دقيقة (تُصفَّر بربح) | 3 / 60min |
| صفقات/يوم | عدّاد GV بتاريخ اليوم | 4 |
| مراكز متزامنة | magic+symbol | 1 |
| سبريد / كلغة / بيانات قديمة | pts + frak<stop | 50pts (20% من المسافة) |
| هامش | `OrderCalcMargin` + shrink-to-fit `InpMaxMarginUse` | 90% كحد أقصى |

**لا يوجد:** Martingale · Grid · Averaging down · توسيع SL · مضاعفة بعد الخسارة · أي افتراض لحجم حساب ثابت.

---

## 5. قرارات تصميمية مهمة (ولماذا)

1. **ملف واحد** — لا مؤشرات مخصصة خارجية، لا DLLs، لا presets: يقلّص سطح الفشل من 52 ملفاً إلى ملف واحد قابل للمراجعة الشاملة.
2. **شموع مغلقة فقط** — كل قرار من `shift ≥ 1`؛ الشمعة الحالية تُستخدم فقط لكشف بداية الشمعة الجديدة ولإدارة المراكز، أبداً للإشارات.
3. **netting = hedging** — الإغلاق الجزئي والحماية تعملان في النمطين (`ACCOUNT_MARGIN_MODE` يتفرع صراحة).
4. **الحراس مثبّتون في GlobalVariables** — إعادة تشغيل الشارت لا تُصفّر baseline اليوم ولا HWM ولا عدّاد اليوم.
5. **Retcode ≠ تنفيذ** — يُكتشف المركز فعلياً من الخادم قبل اعتبار الأمر "تم".
6. **DEMO فقط، دائماً** — لا يوجد مسار كودي إلى حساب حقيقي؛ الفشل في إثبات نمط الحساب = حظر كامل.

---

## 6. كيف تقرأ سجلّ `[QATS]` (Journal)

```
[QATS][PROTECTION] PASS: ... DEMO confirmed ...     ← الشرط الأول للتداول
[QATS][RISK] per-trade risk = 0.50% ...              ← المخاطرة الفعلية بعد الأقفال
[QATS] data pipeline OK | ATR(H1)=... VWAP=...       ← البيانات تتدفق
[QATS][HB] equity=... dayPnL=... DD=...              ← نبض كل 5 دقائق
[QATS][SKIP] score 55 < minimum 65 | D1=+1 ...       ← لماذا لم تُفتح صفقة (مع التفصيل)
[QATS][ORDER] BUY 0.02 lots XAUUSD @ ... SL ... TP ... score 78
[QATS][EXEC] retcode=10009 (Done) deal=...
[QATS][VERIFY] POSITION CONFIRMED on server: ticket=... server-side SL=... TP=...
[QATS][GUARD] DAILY LOSS LIMIT HIT ... LOCKED for 20261109
[QATS][MANAGE] ticket=... SL -> BREAK-EVEN @ ... (+1.02R)
```

## 7. حدود صريحة (مهما قال التسويق)

- الاستراتيجية نفسها (edge) غير مُثبتة تاريخياً — الاختبار الأمامي على DEMO هو البوابة.
- نتيجة DEMO ≠ تنبؤ بالربح المستقبلي.
- هذا البناء **لم يُجمَّع بعد** (MetaEditor غير متوفر في بيئة التطوير الحالية) ولا توجد صفقة تنفيذ فعلي بعد — انظر `PRODUCTION_VERIFICATION_2026-11-09_QUANTUM_EA.md` للحالات والحواجز.
