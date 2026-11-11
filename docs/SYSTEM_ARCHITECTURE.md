# شجرة نظام QuantumAutonomousTradingSystem — System Architecture

**النظام:** QuantumAutonomousTradingSystem (QATS) v1.20
**نوع الملف:** خبير MQL5 واحد مستقل (Standalone Expert Advisor) — `MQL5/Experts/QuantumAutonomousTradingSystem.mq5`
**التاريخ:** 2026-11-09، حُدِّث 2026-11-11 للنسخة v1.20 (محرك ثنائي الاتجاه)

> **v1.20:** طبقات التحليل والتقييم والتخطيط وعدّ الخسائر استُبدلت. كان v1.11 يختار اتجاهًا واحدًا قبل التقييم
> فيبقى ساعات يشتري دون أن يقيّم البيع. الأسباب والأدلة والحكم في
> [`QATS_DUAL_DIRECTION_AR.md`](QATS_DUAL_DIRECTION_AR.md) و
> [`QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md`](QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md).

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
│     ├─ ProcessClosedDeals()  نتيجة كل مركز من سجل الصفقات (ربح + سواب + عمولة + رسوم)
│     ├─ UpdateCooldownState() حالة التوقف: بداية / نهاية / عدد الخسائر، مع إصلاح الحالة المحفوظة
│     ├─ GuardBlocks()         السلسلة الكاملة، وتُسمّى كل الحواجز الفعّالة لا أولها فقط
│     └─ Persisted GVs         تبقى عبر إعادة تشغيل الشارت (لا تُصفَّر)
│
├─► [C] طبقة بيانات السوق — Market Data Engine (Closed Bars Only)
│     ├─ CopyBuffer/iHigh/iLow…    بيانات رسمية مغلقة فقط (shift ≥ 1)
│     ├─ LoadReading()             لقطة موحّدة D1/H4/H1/M15/M5 + ATR + VWAP + Volume
│     ├─ SessionVWAP()             VWAP جلسة اليوم (من بداية يوم الخادم)
│     └─ SmaVolume()               متوسط حجم التيك M5 (20 شمعة)
│
├─► [D] طبقة التحليل — Smart Money Concepts Engine (للاتجاهين في كل شمعة)
│     ├─ FindSwings()              نقاط انعكاس مؤكدة (fractal k=2)
│     ├─ BuildStructure()          هيكل H1 سببيًا: BOS (مع الاتجاه) / CHoCH (عكسه)
│     ├─ BuildLiquidityMap()       كل مستوى سيولة وحالته: INTACT / SWEPT / ACCEPTED / SPENT
│     ├─ SweepForDirection()       الاكتساح القائم الذي يتغذى عليه كل اتجاه (تنتهي صلاحيته ويسقط إن فشل)
│     ├─ DetectDisplacement()      شمعة اندفاعية (جسد ≥ 0.8×ATR) عند الاكتساح أو بعده
│     ├─ FindOrderBlock() / FindFVG() / ZoneStillValid()   مناطق لم تُخترق بعد
│     ├─ DealingRangePosition()    موقع السعر داخل النطاق (Premium/Discount)
│     ├─ M15Confirms() / M5Trigger()   تأكيد M15 وإشارة M5
│     └─ EvaluateSide(+1) و EvaluateSide(-1)   الدالة نفسها مرتين: أدلة الشراء وأدلة البيع
│
├─► [E] طبقة القرار — Core Gate → Score → Direction Policy
│     ├─ QATS_CoreGate()           InpStrategyProfile: محافظ / متوازن (افتراضي) / نشِط
│     │                            الاكتساح وحده لا يجتاز أي وضع
│     ├─ QATS_ScoreSide()          جدول واحد للاتجاهين، مجموعه 100:
│     │                            D1 17 · H4 13 · هيكل 17 · اكتساح 13 · اندفاع 9 · منطقة 9/4
│     │                            موقع 4 · VWAP 4 · حجم 4 · M15 5 · M5 5
│     ├─ عتبة: InpMinScore = 55 (بعد اجتياز البوابة فقط)
│     ├─ QATS_ResolveDirection()   عند تأهل الطرفين: فارق النقاط ← هيكل H1 ← D1 ← H4 ← لا صفقة
│     └─ على غير XAUUSD فقط: فيتو D1/H4 (إن فُعِّل)
│
├─► [F] طبقة التخطيط — Trade Plan (Entry/SL/TP)
│     ├─ BuildTradePlan()     SL = max(ATR×1.5, مدى M5×3) + هامش الوسيط؛ وقف البيع يُزاح بالسبريد
│     ├─ صيغة التحقق: stopsLevel / freezeLevel / InpMin|MaxStopPoints
│     ├─ TP: أقرب سيولة سليمة (INTACT) إن حققت RR ≥ InpMinRR، وإلا RR×2.0
│     └─ SetupAlreadyTraded()  دخول واحد لكل إعداد (هوية الإعداد = شمعة H1 للكسر أو الارتداد)
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
      ├─ OnTradeTransaction() سجل كل صفقة، وتحديث سلسلة الخسائر فور صفقة الإغلاق
      ├─ دورة حياة الإشارة: [DETECTED] ← [SIGNAL][SCORED] ← [BLOCK][REASON] / [EXECUTION][REJECTED]
      │                      ← [EXECUTION][APPROVED] ← [EXECUTION][FILLED]
      └─ [QATS][STATS]        عدّادات الشراء والبيع يوميًا وعند الإزالة
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
(نتيجة كل مركز ← سلسلة الخسائر)      D1 → H4 → H1 (BOS/CHoCH) → خريطة السيولة
                                     ثم EvaluateSide(BUY) و EvaluateSide(SELL):
                                     اكتساح → اندفاع → هيكل → OB/FVG → موقع → VWAP → M15 → M5
                                          │
                              [BUY][DETECTED] / [SELL][DETECTED]  (مرة لكل إعداد اجتاز البوابة)
                                          │
                              لا طرف مؤهل؟ ── ► [SIGNAL][SCORED] outcome=NO_SETUP / BELOW_MINIMUM
                              الطرفان مؤهلان؟ ──► [SIGNAL][CONFLICT] ثم القاعدة تحسم أو لا صفقة
                                          │ اتجاه واحد
                              ClosePositionOnOpposite()  (إن وُجد مركز معاكس والخيار مفعّل)
                                          │
                              CollectEntryBlocks() > 0؟ ──► [BLOCK][REASON] بكل الرموز + outcome=BLOCKED
                                          │ لا حواجز
                              BuildTradePlan() ── فشل؟ ──► [EXECUTION][REJECTED] stage=PLAN
                                          │
                              ExecuteSignal(): إعادة فحص حيّة ← الحجم ← السبريد مقابل الوقف
                                          │            فشل؟ ──► [EXECUTION][REJECTED] stage=…
                              [EXECUTION][APPROVED] → CTrade.Buy/Sell(SL,TP)
                                          │
                              retcode ∈ {10009,10010}? ── لا ──► [EXECUTION][REJECTED] stage=BROKER
                                          │ نعم                 (XAUUSD: بلا إعادة تلقائية)
                              VerifyPositionOpened() → [EXECUTION][FILLED] position=verified
                              (+طباعة SL/TP كما يراه الخادم فعلياً)
```

---

## 3. الخريطة الملفية — File Map

```
terad/
├── MQL5/Experts/QuantumAutonomousTradingSystem.mq5   ← ملف النشر الوحيد (v1.20)
├── presets/Quantum_XAUUSD_PRODUCTION.set             ← ملف الإعدادات الوحيد
├── tools/verify_quantum_ea.py                        ← فحص بنيوي offline (ليس مترجم)
├── tools/qats_native.py + tools/qats_sim/            ← بناء الملف بمترجم صارم + محاكي وسيط
├── tools/qats_backtest.py                            ← محاكاة تاريخية وإثبات التماثل
├── tools/qats_journal_report.py                      ← تقرير شراء/بيع من سجل MT5
├── docs/QATS_DUAL_DIRECTION_AR.md                    ← شرح v1.20 وخطوات التحقق
├── docs/SYSTEM_ARCHITECTURE.md                       ← هذا المستند
├── docs/PRODUCTION_AUDIT_2026-11-09_QUANTUM_EA.md    ← تقرير التدقيق والتنظيف
├── docs/PRODUCTION_VERIFICATION_2026-11-09_QUANTUM_EA.md  ← تقرير التحقق (Phases 1–7)
├── docs/incident-20261101/                           ← سجل حادثة سابق (محفوظ كما هو)
└── .github/workflows/quantum-verify.yml              ← CI: الفحص البنيوي + البناء + المحاكي
```

**شجرة النشر على جهاز Windows + MT5:** انقل ملف `.mq5` واحداً إلى `MQL5\Experts\` ثم F7. لا شيء آخر.

---

## 4. جداول الحراس والحدود (كودياً، لا وعدياً)

| الحارس | المصدر | القيمة الافتراضية |
|---|---|---|
| تفويض الحساب | DEMO مسموح افتراضيًا؛ REAL يحتاج `InpDemoOnly=false` و`InpAllowRealTrading=true` ورقم الحساب واسم الخادم مطابقين؛ CONTEST مرفوض — عند الإقلاع **وعند كل قرار دخول** | DEMO فقط |
| صلاحية الطرفية/الخبير/الرمز | `TERMINAL_TRADE_ALLOWED` + `MQL_TRADE_ALLOWED` + `ACCOUNT_TRADE_ALLOWED` + `SYMBOL_TRADE_MODE_FULL` | تُعاد فحوصها كل قرار |
| مخاطرة/صفقة | `Equity × EffectiveRiskPercent()` | 0.50% (إدخال ≤ ceiling ≤ سقف صلب 2.0%) |
| وقف الخسارة | max(ATR×1.5, 3×M5 bars) + broker buffer | **لا توجد صفقة بلا SL** |
| هدف الربح | سيولة معاكسة (RR≥1.5) أو 2.0R | لا يُقصَّر عن RR 1.5 |
| خسارة يومية | Equity-baseline مثبّت يومياً (GV بتاريخ اليوم) | 2.0% أو `InpMaxDailyLossMoney` |
| سحب الحساب | HWM مثبّت (GV `…_hwm`) — v1.10: يُحفظ عند أول رؤية | 8.0% من القمة |
| خسائر متتالية | 3 مراكز خاسرة صافيًا (بعد العمولة والسواب) ⇒ تهدئة 60 دقيقة؛ تُصفَّر بربح؛ `InpNeutralCloseR` نطاق التعادل | 3 / 60min / 0.0R |
| تأكيد الإعداد | `InpStrategyProfile` — الاكتساح وحده لا يكفي في أي وضع | BALANCED |
| دخول واحد لكل إعداد | هوية الإعداد محفوظة لكل اتجاه (GV) | دائمًا |
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
6. **DEMO افتراضيًا** — الحساب الحقيقي يحتاج تفويضًا صريحًا ومطابقة رقم الحساب والخادم؛ الفشل في إثبات نمط الحساب = حظر كامل.
7. **لا اتجاه افتراضي (v1.20)** — الشراء والبيع يُبنيان بالدالة نفسها؛ سوق معكوس السعر يُنتج الصفقات المعكوسة تمامًا (مُثبت بالمحاكاة).

---

## 6. كيف تقرأ سجلّ `[QATS]` (Journal)

```
[QATS][PROTECTION] PASS: DEMO account authorized ...  ← الشرط الأول للتداول
[QATS][POLICY] direction: BUY and SELL are scored independently ... profile=BALANCED ...
[QATS][RISK] per-trade risk = 0.50% ...              ← المخاطرة الفعلية بعد الأقفال
[QATS][COOLDOWN] state=IDLE at attach ...            ← حالة التوقف عند الربط
[QATS] data pipeline OK | ATR(H1)=... VWAP=...       ← البيانات تتدفق
[QATS][HB] equity=... dayPnL=... DD=... cooldown=YES(trigger=3 losses,start=...,until=...,remaining=...s) lastBUY=.. lastSELL=..
[QATS][SELL][DETECTED] ... setup=S-20261112-0900 score=62/100 ... core=PASS 2/3 | sweep=... displacement=... structure=CHOCH@...
[QATS][SIGNAL][SCORED] ... BUY=31/100 SELL=62/100 ... candidate=SELL eligible=yes outcome=EXECUTED reason=ORDER_FILLED | ... | BUY core=FAIL(...) [...] | SELL core=PASS 2/3 [...]
[QATS][BLOCK][REASON] ... direction=SELL ... reasons=LOSS_COOLDOWN,DAILY_TRADE_CAP detail=...
[QATS][EXECUTION][REJECTED] ... stage=SPREAD_VS_STOP reason=spread 31.00 pts exceeds 20.00% of stop distance
[QATS][EXECUTION][APPROVED] ... direction=SELL ... entry=... sl=... tp=... tpSource=LIQUIDITY:PDL rr=2.40 lots=0.02 risk=...
[QATS][EXECUTION][FILLED] ... direction=SELL ... retcode=10009 ... position=verified ticket=...
[QATS][VERIFY] server-side SL=... TP=... | openPrice=... volume=...
[QATS][GUARD] position ... SELL closed WIN net=+41.20 USD (neutral band 0.00) -> lossStreak=0/3
[QATS][COOLDOWN] state=STARTED trigger=3 losses start=... until=... remaining=3600s lossStreak restarts at 0
[QATS][MANAGE] ticket=... SL -> BREAK-EVEN @ ... (+1.02R)
[QATS][STATS] scope=session BUY detected=.. executed=.. closed=W./L./N. net=.. | SELL detected=.. executed=.. ...
```

الأسطر أعلاه أمثلة على الشكل لا نتائج تداول. لتحويل سجل حقيقي إلى جدول شراء/بيع:

```
python3 tools/qats_journal_report.py MQL5/Logs/YYYYMMDD.log
```

## 7. حدود صريحة (مهما قال التسويق)

- الاستراتيجية نفسها (edge) **غير مُثبتة، والمحاكاة التاريخية تُظهر توقعًا سالبًا** داخل العيّنة للنسختين v1.11 وv1.20 — انظر `QATS_BACKTEST_STUDY_2026-11-11.md`.
- نتيجة DEMO ≠ تنبؤ بالربح المستقبلي.
- v1.20 **لم يُجمَّع بعد في MetaEditor** (غير متوفر في بيئة التطوير) ولم يُشغَّل في Strategy Tester ولا على الديمو. الدليل الميداني الوحيد هو سجل v1.11: ثلاث صفقات شراء وصفر بيع. الخطوات ومعايير القبول في `QATS_DUAL_DIRECTION_AR.md`.
