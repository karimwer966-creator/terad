# تقرير الإصلاح — 06/11/2026 — XAUUSD / nadir2 + QSMC_AutoTrader

**النطاق:** `MQL5/Indicators/nadir2.mq5` (v6.6.20) و `MQL5/Experts/QSMC_AutoTrader.mq5` (magic 20261027، مخاطرة 0.10%، جلسة 10:00–18:00، 3 صفقات/يوم، سقف يومي صارم 1.00%).

**الحالة:** جميع الإصلاحات مطبقة في الفرع، و42/42 فحصاً آلياً في بوابة المستودع تمر (`OFFLINE GO`). ما تبقّى خارج قدرتي هنا: **F7 في MetaEditor** (لا يوجد مترجم MQL5 في هذه البيئة) وتشغيل تجريبي.

---

## الخلاصة في أربع نقاط

| # | ما ظهر في اللوج | ما كان يحدث فعلاً | الحالة |
|---|---|---|---|
| 1 | `Total Signals Generated: 0` + `[CausalBranch] ROLLBACK … OB exact displacement/structure binding mismatch` | **هذا هو السبب الحقيقي.** حقل `SOrderBlock.source_structure_time` كان يُصفَّر فقط ولا يُكتب أبداً، فيفشل **كل** OB في `ValidateCausalGraphInvariants`، فيُرجع كل setup ويُمحى من الرسم السببي | ✅ مُصلح (سطر واحد) |
| 2 | `[GateLeg] … sweep_bar 0 … bars_apart 50584` | **تشخيص كاذب، ليس بوابة.** `MathMax(0,-1)` حوّل «لا يوجد sweep» إلى «البار 0 من التاريخ»، ثم كتب ماسح الـOB هذا الرقم فوق لقطة تشخيص مسار الإشارة | ✅ مُصلح (حارس + عزل التشخيص) |
| 3 | `DAY_BLOCKED` يظهر عند كل ربط | `day_base=5680.64` مقابل `eq≈4999` وسقف 0.50% ⇒ الحد 5652.24 **أعلى من الإيكويتي**، فيُطلق الحظر فوراً ويعود عند كل `OnInit` لأنه محفوظ في متغيرات التيرمنال | ✅ أداة تصفير مُدقّقة + التحقق |
| 4 | `M1→M5→M15→H1→H4` ثم `[PMI] shutdown` | **الـEA لا يبدّل الفريم أبداً** — لا يوجد في الشفرة أي استدعاء لتغيير الفريم. التبديل من الشارت/البروفايل، وكل تبديل يعيد تشغيل `OnInit` فيعيد استرجاع الحظر | ✅ تثبيت + رفض واضح |

**تصحيح مهم لتحليلي السابق:** الخطأ `sweep_bar 0` لم يكن هو المانع، بل كان يجعل تقرير «أعلى مانع» مضلِّلاً. المانع الحقيقي هو `OB binding mismatch`، و`chain: structure event missing/invalidated in the graph (435)` هو **نتيجة ثانوية** له: عند كل rollback تُمحى عقدة البنية من الرسم، فتصبح البنية التالية «مفقودة»، فيتصدّر هذا السبب قائمة الموانع.

---

## 1) السبب الجذري لصفر إشارات CORE (بالتسلسل)

1. `DetectStructure` يُنتج `g_structures` → `DetectOrderBlocks` يبني `g_order_blocks` بـ `source_structure_time = 0` (تصفير فقط).
2. `BuildCausalEventGraph` يربط كل OB بحدث الإزاحة والبنية وكتب `source_displacement_event_id` و`source_structure_event_id`… **لكنه لم يكتب `source_structure_time`** (مسار الـFVG كان يكتبه فعلاً).
3. `ValidateCausalGraphInvariants` (فرع `CE_ORDER_BLOCK`) يقارن `source_structure_time` بوقت حدث البنية ⇒ `0 != t[st.bar]` ⇒ فشل دائم.
4. `CreateSetupBranchTransactional` → إن فشل الفحص ⇒ `RollbackCausalGraphToSize` ⇒ `[CausalBranch] ROLLBACK`.
5. النتيجة: أي setup يُحسب ثم يُلغى. لهذا كان `signals CORE armed` يتقدّم أحياناً بينما `Total Signals Generated: 0`.

> ملاحظة دقيقة: الأعلام `[CausalInvariant] FAIL` و`[CausalReplay] FAIL` هي **آليات كشف** وليست بوابة منع. لكن إصلاح الحقل يوقفها لأن سببها كان بنيوياً في نفس الربط.

---

## 2) التعديلات — أرقام الأسطر الحالية

> الأرقام بعد التعديل؛ قد تنزلق قليلاً إن أضفت أسطراً قبلها.

### 2.1 السطر الحاسم — `nadir2.mq5:17179`

داخل `BuildCausalEventGraph`، في حلقة ربط الـOB:

```mql5
         g_order_blocks[oi].source_displacement_event_id=did;
         g_order_blocks[oi].source_structure_time=t[st.bar];      // ← مُضاف
         g_order_blocks[oi].source_structure_event_id=sid;
         SOrderBlock ob=g_order_blocks[oi];
         string oid="CE_ORDER_BLOCK_"+ob.id;
```

الموضع الصحيح هو **قبل** `AddCausalEvent(oid,CE_ORDER_BLOCK,…)`، لأن الفحص يُقرأ فيه على نفس التمريرة.
(المسار المكافئ للـFVG عند السطر `17201` كان موجوداً أصلاً — وهذا ما جعل الفرق واضحاً.)

### 2.2 حارس `sweep_bar` — `nadir2.mq5:23803`

داخل `DetectOrderBlocks`:

```mql5
      int liq=FindAlignedLiquiditySweep(st.bullish,st.bar,InpSweepToStructureMaxBars,sweep_price);
      int sweep_bar=(liq>=0 ? g_liquidity[liq].origin_bar : -1);

      if(sweep_bar<0) continue;        // ← لا مرساة سببية ⇒ لا OB

      int impulse_bar=-1;
      bool leg_ok=ValidateDisplacementLeg(sweep_bar,st.bar,st.bullish,
                                          st.price,o,h,l,c,impulse_bar,false);
```

**قبل:** `ValidateDisplacementLeg(MathMax(0,sweep_bar), …)` — أي `MathMax(0,-1)==0` ⇒ قياس «ساق» من البار 0 إلى البار المغلق (`bars_apart 50584`).

### 2.3 عزل التشخيص — `nadir2.mq5:16826 / 16874 / 16944`

لماذا: `[GateLeg]` لا يطبع «كل» المحاولات، بل **آخر** لقطة كتبها أي مُتصل. وماسح الـOB يقيّم الساق على **كل** كسر بنية (ومعظمها لا يصبح إشارة)، وكان يعمل **بعد** تمريرة الرسم السببي — فيطمس لقطة مسار الإشارة. لذلك كانت الأرقام لا تنتمي لأي مرشح فعلي.

```mql5
void LegNoteFail(const string key,const bool record_diag)
{
   if(record_diag) g_gate_audit.leg_fail_key=key;
   GateAuditReject(key);          // العدّاد يبقى غير مشروط
}
```

- توقيع الدالة صار: `bool ValidateDisplacementLeg(...,int& impulse_bar,const bool record_diag)`
  والتقرير الافتراضي `=true` موضوع في **الإعلان** (`5360`) لا في التعريف.
- لقطة `g_gate_audit.leg_*` كلها داخل `if(record_diag){ … }` (`16874`).
- موضعا النداء فقط:
  - الرسم السببي `17122`: `candidate_impulse,true` ← **هو صاحب التشخيص**.
  - ماسح الـOB `23806`: `impulse_bar,false`.
- إضافة أمان: قراءة ATR محمية بالمدى، و`sweep_extreme` لا تُقرأ من البار 0 عند غياب الساق.

كل حالات الرفض ما زالت تصل إلى `GateAuditReject` وبالتالي إلى «أعلى مانع» وعدّاداته — **لم أفقد أي معلومة تصنيف**، بل منعت الإسناد الخاطئ فقط.

### 2.4 المفاجأة: البريست كان يمنع الإشارة بنيوياً

الدليل `docs/ATTACH_EA_CORRECTLY_v6.6.14.md` يطلب تحميل `presets/nadir2_PRACTICAL_XAUUSD.set`. هذا الملف كان يحمل:

| المُدخل | كان في البريست | الافتراضي في الشفرة | لماذا يهم |
|---|---|---|---|
| `InpDisplacementATR` | **0** | 0.9 | بوابة الساق: `net >= atr*InpDisplacementATR`. بـ0 تصبح 0.00 وتُقبل أي ساق — **وليس** هناك أي «auto-heal» لهذا المُدخل |
| `InpMaxStructuresKeep` | **3** | 30 | لا يبقى ما يكفي لمرساة بنيوية |
| `InpMaxLiquidityKeep` | **4** | 40 | الزوج (pool+sweep) هو وحدة بقاء ذرّية: 4 صفوف = بركتان فقط في التاريخ كله |
| `InpMaxFVGKeep` | **2** | 25 | — |
| `InpMaxZonesKeep` | **2** | 20 | — |
| `InpMaxCausalEventsKeep` | **1** | 160 | `PruneCausalEventGraph` يحتفظ بسلسلة واحدة فقط ⇒ يستحيل وجود مسار pool→sweep→displacement→structure |

**تمت إعادة هذه الستة إلى الافتراضات الآمنة.** `InpAnchorSearchBars=120` و`InpGateProfile=1` و`InpEnableCausalInvariantChecks=false` (وضع مراقبة في البريست) تُركت كما هي لأنها قرارات مضبوطة وليست أعطالاً — **لكن إن أردت رؤية الفحص السببي يعمل، اجعل `InpEnableCausalInvariantChecks=true`**.

---

## 3) تثبيت الإكسبرت على فريم واحد

أضفت مُدخلاً جديداً — **افتراضياً مُعطّل** حتى لا أفرض سلوكاً جديداً على حساب حقيقي:

```mql5
input int    InpPinTimeframeMinutes  = 0;   // 0 = off. غير ذلك: طول البار بالدقائق (1/5/15/30/60/240)
```

السلوك:
- `PinnedTimeframeMatches()` (`2241`) يقارن `PeriodSeconds(_Period)` بالدقائق المطلوبة.
- داخل `OnInit` (`2301`): إن لم يطابق ⇒ رسالة `[QSMC_AT] TIMEFRAME PIN REFUSED` ثم `INIT_PARAMETERS_INCORRECT`، **قبل** طلب أي `iCustom` — أي لا تيار بيانات ثانٍ إطلاقاً.
- `OnTick` (`2777`) و`OnTimer` (`2787`): إن حُرّك الفريم أثناء العمل ⇒ خروج فوري بلا قراءة إشارة ولا أمر.
- **لا يوجد** أي استدعاء لتغيير الفريم من داخل الـEA، ولن أضيفه. هذا «كاشف» لا «مُبدّل».

**ما تفعله أنت:** ضع `InpPinTimeframeMinutes=15` إن كان شارتك M15 (أو 5 لـM5). ثم لا تضغط أزرار الفريم على شارت الـEA، واستخدم شارتاً مخصصاً محفوظاً في بروفايل بدل شارت تتقليب عليه.

أضفت أيضاً `InpPinTimeframeMinutes=0` إلى **8 ملفات بريست** للـEA؛ بدونها كان «Load preset» سيرجع المُدخل إلى 0 بصمت (وهذا كان سيُلغي التثبيت الذي ضبطته).

---

## 4) تصفير الحظر اليومي (`DAY_BLOCKED`)

### القراءة من اللوج

```
GUARD day_base=5680.64 sess_base=3954.10 bal≈… eq≈4999 daily_dd=…  DAY_BLOCKED
```

بسقف صارم 0.50%: `floor = 5680.64 × (1 − 0.005) = 5652.24`. وبما أن `eq ≈ 4999 < 5652.24`، فالحظر يُطلق في **أول** تك؛ ولأن `BLOCKED` محفوظ في متغير تيرمنال، فهو يعود مع **كل** إعادة ربط. أي أن `day_base` خاطئ/قديم (لحالة حساب مختلفة)، وليس خطأ في معادلة الحماية.

### الخيار A (المفضَّل) — أداة مُدقّقة بدل قلب مُدخل على حساب حقيقي

`MQL5/Scripts/QSMC_ResetGuards.mq5` (جديد):

1. `F7` لترجمته، ثم أرفقه على **نفس شارت الرمز**.
2. شغّله أولاً بـ `InpApply=false` (الافتراضي) ⇒ يطبع قائمة المفاتيح فقط، بالقيمة وتاريخ آخر كتابة، ومعها `skipped[other account=… other symbol=…]`.
3. راجع أنها لنفس `login/magic/symbol`. عندها فقط `InpApply=true` وأعد التشغيل.
4. يعيد ربط الـEA ⇒ توقّع في اللوج: `[QSMC_AT] day guard: new baseline ≈ <equity الحالي>` ثم `state ARMED`.

الأداة: لا تربط أي دالة تداول (لا `OrderSend` ولا `CTrade`)، تمسح فقط البادئتين `QSMC_AT_DAY`/`QSMC_AT_SESS` لنفس الحساب والرمز، وتطبع سطراً لكل مفتاح محذوف.

### الخيار B — كما في الشفرة

`InpResetBreakersAtInit=true` عند الربط ⇒ يطبع `[QSMC_AT RESET] RESET_REASON=…` ويأخذ خط أساس جديداً، **ثم أعِده إلى `false`**. تحذيري: نسيان الرجوع يُعطّل الحماية في كل ربط لاحق، ولهذا فضّلت الخيار A.

### التحقق بعد التصفير

في سطر `heartbeat` → `GUARD` يجب أن ترى `day_base ≈ eq` والحالة `ARMED` بدل `DAY_BLOCKED`، و`daily_dd` صغيراً موجباً (لا 12%+).

---

## 5) التحقق الذي أجريته

| الفحص | النتيجة |
|---|---|
| `python3 tools/check_production_ready.py` | **OFFLINE GO — 42/42** (كان 41، أضفت فحصاً واحداً) |
| `tools/test_causal_chain_regressions.py` (جديد) | 30 عقداً: B1..B6 — كلها PASS |
| نهايات الأسطر | `nadir2.mq5` و`nadir2.mq5` في `MQL5/Indicators` متطابقان بايت-ببايت، CRLF خالص؛ `.set` بترميز MetaEditor (`\r\r\n`) كما هو |
| `tools/mql5_rules.py` (D1–D16) | لا أخطاء لهجة |
| مُدخلات البريست | 519/519 مطابقة لسطح مُدخلات المؤشر |

**عقد جديد يمنع الرجوع:** `tools/test_causal_chain_regressions.py` يُثبّت: كتابة `source_structure_time` قبل إنشاء الحدث، غياب `MathMax(0,sweep_bar)`، أن اللقطة محصورة بالعلم وأن موضعي النداء صحيحان، قيم البريست الستة، عدم وجود أي تبديل فريم في الشفرة، وتطابق بادئات أداة التصفير مع مفاتيح الـEA.

**ما لا أستطيع إثباته هنا:** لا يوجد MetaEditor ⇒ لم أترجم. الأرقام أعلاه عقود مصدرية وليست تشغيل MT5، ولم أُجرِ اختباراً تاريخياً.

---

## 6) ماذا يجب أن تراه في اللوج بعد F7 وإعادة الربط

1. اختفاء `[CausalBranch] ROLLBACK … OB exact displacement/structure binding mismatch`.
2. اختفاء `[CausalInvariant] FAIL`، و`[CausalReplay] PASS` بدل `FAIL`.
3. سطر `[GateLeg]` يحمل `sweep_bar` حقيقياً (لا 0) و`bars_apart` في حدود 2..`InpSweepToStructureMaxBars`، وإن لم تُوجد ساق فالسطر سيصف مرشح مسار الإشارة لا مرشح الماسح.
4. `signals CORE armed/confirmed` أكبر من 0، و`Total Signals Generated` غير صفري.
5. `heartbeat: … CORE signals in last 200 closed bars: <n>` بقيمة غير صفرية عند وجود بنية.
6. `GUARD day_base ≈ eq` و`ARMED`.

إن بقي `top blocker` من نوع `chain: no confirmed liquidity sweep behind the displacement`، فهذا **ليس عطلاً** بل نقص بنية سوقية حقيقي في تلك الفترة — والمكان الصحيح لتوسيعه هو `InpSweepToStructureMaxBars` (الافتراضي 8) لا تعطيل البوابات.

---

## 7) حدود ومسؤولية

- هذه إصلاحات **صحة بيانات وسببية**، لا وعد بربحية. البوابات نفسها لم أُرخِها: عدّادات الرفض باقية، ومعايير min-confidence/min-reliability/RR لم تُمس.
- تشغيل الأموال الحقيقية لا يزال محكوماً بـ `docs/QSMC_GO_LIVE_RUNBOOK.md`، والـEA يبقى `INERT`/`DRY RUN` حتى تُفعّله أنت يدوياً.
- قبل أي تفعيل: جرّب على **Demo** أولاً مع `InpGateAuditLogEveryBars>0` في المؤشر حتى ترى عدّادات البوابات تتحرك.

---

## 8) ملحق: خريطة الدوال

| الدالة | السطر | الدور |
|---|---|---|
| `ValidateDisplacementLeg` | 16832 (إعلان 5360) | التحقق من ساق sweep→structure + اختيار شمعة الإزاحة |
| `LegNoteFail` | 16826 | رفض + لقطة تشخيص (بشرط `record_diag`) |
| `ValidateCausalOB` | ~16953 | ربط الـOB بشمعة الإزاحة الصحيحة |
| `BuildCausalEventGraph` | ~17113 | بناء الرسم السببي وربط OB/FVG (فيه الإصلاح الحاسم) |
| `ValidateCausalGraphInvariants` | ~17700 | فحص الثوابت (فرع OB يقرأ `source_structure_time`) |
| `ResolveCausalPath` | ~17890 | pool→sweep→displacement→structure→OB/FVG |
| `CreateSetupBranchTransactional` | ~18885 | إدراج ذرّي + rollback عند فشل الفحص |
| `DetectOrderBlocks` | ~23770 | ماسح الـOB (فيه إصلاح `sweep_bar`) |
| `SignalGateLegDiagLine` | ~19300 | طبع سطر `[GateLeg]` |
| `DayGuardKey` / `DayGuardLoad` / `DayGuardUpdate` | 701 / 712 / 774 | مفتاح الحظر، استرجاع/خط أساس، الإطلاق |
| `PinnedTimeframeMatches` / `TimeframePinRefusal` | 2241 / 2262 | تثبيت الفريم |
