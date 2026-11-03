# المرحلة 1 — تدقيق جاهزية الإنتاج v6.6.13

**التاريخ:** 2026-11-03  **الفرع:** `arena/7b8c6950-terad`  **الحكم: NOT READY FOR PRODUCTION** — أسباب جذرية مؤكدة (CRITICAL) تمنع نشر أي إشارة.

---

## A. السبب الجذري لكل عَرَض

### 1. «CORE WAIT – no current entry / no published Core buffer» ولا صفقات تُفتح

**المكان:** `MQL5/Include/QSMC/QSMC_IncidentSafety.mqh:7–33` (دالة `QA_FilterCandidates`) تُستدعى من `nadir2.mq5:34838` داخل `ZRE_BuildZonesEx`، وتقرأ المصفوفات الشارتية العمومية `g_buf_h/g_buf_l/g_buf_t` **مباشرة**.

- في **مسار الاختبار الذاتي** (OnInit) وعند أول نداء لـ `ZRE_SelfTest()` لا تكون `g_buf_h/l/t` قد عُبِّئت بعدُ بقيم حقيقية؛ تحتوي قيماً ابتدائية/صفرية أو بقايا عملية حسابية سابقة. السطر `if(ctx.closed>=ArraySize(g_buf_h)...)` يُعيد `ArrayResize(cands,0)` مباشرة → **جميع المرشحات تُحذف قبل تسجيلها** → تفشل عبارة `ZRE_Expect(ArraySize(z)==1,"score zone count",where);` (nadir2.mq5:36227).
- في **مسار البث الحي**، الفلتر يُطبّق شرطاً منطقياً خاطئاً على العمر/البعد (`QSMC_ZoneRangeReason` في `MQL5/Include/QSMC/QSMC_Types.mqh:416–431`):
  ```
  if(gap > max_distance_atr*atr  &&  (age<0 || age>lifetime))  return "expired distant zone";
  ```
  المعامل `age<0` (المناطق التي لا تحمل `born_bar`، كالمناطق القديمة من سنة 2023 في سجلّك) يجعل الشرط صحيحاً **حتى لو كان السعر داخل المنطقة فعلاً (gap==0)**. هذا هو السبب المباشر في ظهور `[QSMC_ZONE_REJECT] ... source=BULL OB created=2023.12.01 ... reason=expired distant zone` رغم أن gap الفعلي لتلك المناطق هو ~1861 نقطة عن سعر 3927، أي بعيداً فعلاً، لكن المناطق الحديثة القريبة لا تصل أبداً لأن **مرشحـّي OB/FVG/Confluent-SR أنفسهم يُرفضون في مراحل أبكر** (انظر السبب 3 أدناه).
- **المفارقة الكبرى:** `QA_FilterCandidates` هو "مرشح أمان" أُضيف حديثاً (IncidentSafety) في طبقة الـ`g_buf_*` global host state، بينما طبقة الـArbiter في `QSMC_Root.mqh` تستقبل مناطق عن طريق `SetZones()` ولا تستدعي هذا الفلتر، ما يعني أن **المنتجين للمناطق (ZRE_CollectCandidates) يعلنون مناطق ثم يحذفها IncidentSafety قبل أن يراها أحد**، بينما أي مُنشئ مناطق بديل لا يمر بهذا الفلتر (عدم اتساق طبقي SSOT).
- علاوة على ذلك: `BufSigCoreDir[closed]` لا يُكتب بقيمة !=0 إلا إذا وصل إعداد إلى `g_confirmed_signal_journal` (nadir2.mq5:14270–14277). وبما أن سلسلة ZRE→RXN→Core→Gates لا تُنتج أي مرشح ناجح (لأن الفلتر أعلاه يُفريغ القائمة)، تبقى جميع قيم البفر `0.0`، فيقرأ EA في `ProcessSignals()` (`QSMC_AutoTrader.mq5:732–748`) قيمة `g_dir[shift]==0.0` فيتخطى → لا يُرسل أمراً.

### 2. «ZRE self-test FAIL @ score zone count» (صفر مناطق مسجلة)

- **السبب المباشر:** أثناء تنفيذ `ZRE_SelfTest()` (nadir2.mq5:36178–36280) يُستدعى `ZRE_BuildZones(one, ctx, h, l, ccls, z)` حيث `ccls` مصفوفة فارغة (لم يُستدعَ `ArrayResize` لها سعة 1 على الأقل قبل التمرير). الأهم: في `ZRE_BuildZonesEx` (nadir2.mq5:34838) السطر الأول بعد فحص `ctx.atr` هو:
  ```
  QA_FilterCandidates(cands,ctx);
  ```
  هذه الدالة تقرأ `g_buf_h/g_buf_l/g_buf_t` وهي في تلك اللحظة **غير مهيّأة** (ليس للمصفوفة `ccls` علاقة؛ الفلتر لا يقرأها أصلاً). لأن `ctx.closed=59` ولكن `ArraySize(g_buf_h)` قد يكون 0 أو أقل من 59 أثناء تشغيل الـself-test في OnInit، تدخل الحماية في السطر 11 (`if(ctx.closed>=ArraySize(g_buf_h)...)`) فتقوم بـ`ArrayResize(cands,0)` → يمسح المرشح الوحيد (`OB+PD` الذي كان يجب أن يُنتج منطقة strength=81) → `ArraySize(z)==0` → يفشل الاختبار.
- لماذا كان هذا لا يظهر سابقاً؟ لأن `QA_FilterCandidates` صُمِّفَ في ملف `QSMC_IncidentSafety.mqh` الذي أُضيف بعد الـself-test ولم يُزوَّد ببيانات `g_buf_*` وهمية أثناء الاختبار؛ بعبارة أخرى: **الاختبار يصل إلى كود يعتمد على حالة المضيف الشارتي الوهمية**.

### 3. «QSMC_ZONE_REJECT ... OB 2023 عند 2066، ولا مناطق قرب السعر»

- المناطق التي تراها في السجل (مثل 2066 OB أو 4151 OB أو 4082 PWH) هي فقط **المناطق المولدة قبل تطبيق فلتر IncidentSafety** ثم المرفوضة. لماذا لا تظهر منطقة قرب 3927–3999 مثل KZ_6 عند 3999.85؟
  1. `QA_FilterCandidates` يحذف كل مرشح لا يحقق الشرط `gap<=12*ATR OR age<=120`. انظر QSMC_Types.mqh:428 – الشرط `gap>max_distance_atr*atr && (age<0 || age>lifetime)`. لأي OB/FVG وُلد عند `born_bar=-1` (مهمل/ملغى)، `age<0` صحيح → يُرفض حتى لو كانت gap=0.
  2. الأهم: `ZRE_CollectCandidates` (nadir2.mq5:36981) يضيف فقط مناطق من: `g_confluent_sr` و`g_order_blocks` و`g_fvgs` وMVP وPDH/PDL/PWH/PWL. في إعداد `INTRADAY` (المُعلن في init log)، `p.expire_bars=480` شريط (nadir2.mq5:36315)، بينما تم ضبط IncidentSafety على `InpZoneLifetimeBars=120` و`InpZoneMaxDistanceATR=12.0`. **هذه القيم أصغر بكثير من عمر منطق OB الناتج من بنية سوقية هابطة من أوكتوبر**: المناطق القريبة من 3927–3970 لو وُلدت خارج نافذة آخر 120 شريطاً M30 (تقريباً 2.5 يوم)، تُرفض بـ`expired distant zone` حتى لو كانت لا تزال على بُعد أقل من 12 ATR.
  3. هنالك **خلل إضافي في فلتر QSMC_ZoneRangeReason**: السطر 428 لا يتحقق من أن mid يقع داخل `[history_low, history_high]` قبل اختبار البُعد؛ هذا يعطي منطقاً غير صحيح تاريخياً لكنه ليس السبب الرئيسي.
  4. في log المُستخدم: `history=1160.19..5598.38` (على M30 عند لحظة معينة). المناطق التي سعر mid عند ~2068 تقع تحت history_low=1160؟ لا، بل فوق history_high=5598؟ كلا، 2068 داخل 1160..5598. إذًا لِمَ وُصفت بأنها "expired distant zone"؟ لأن gap=|3927-2068|≈1859 نقطة = 1859/13.88 ≈ 134 ATR > 12 ATR → يُرفض. هذا صحيح.
  5. **المشكلة الحقيقية**: في السجل لا يوجد أي `[QSMC_ZONE_REJECT]` لمناطق مولودة خلال آخر 120 شريطاً قرب 3920–4000. هذا يعني أن **محرك الـOrder Blocks والـFVG لا يُنتج هذه المناطق أصلاً** عند السعر الحالي، لأن:
     - `g_order_blocks[i].origin_struct_bar<0` أو `state=="MITIGATED"` أو `closed_state=="MITIGATED"` (nadir2.mq5:37006–37015) تستثنيها.
     - المناطق القريبة (KZ_6 عند 3999) تبدو **مرسومة يدوياً/مُولَّدة من Kill-Zone لا من ZRE_CollectCandidates** — لذلك ستراها على الشارت لكن ZRE لا يُرسلها إلى محرك التسجيل/البفر.

### 4. «RXN self-test FAIL – T3 must report execution as waiting for retest»

- المسار: `RXN_Scenario(with_displacement=1, with_structure=1)` → `RXN_Classify` (nadir2.mq5:38157–38320). في T3:
  - `htf_bias=1`, `d1_bias=1`, `support_side=false` (أي SELL على resistance بينما HTF/D1 صاعدان).
  - في `RXN_LevelEx` (nadir2.mq5:37823–37842):
    ```
    bool countertrend=(htf_alignment<0 && d1_alignment<0);
    ```
  - لاحظ أن مُعاملي `htf_alignment` و`d1_alignment` يُمرَّران كقيم `e.htf_alignment` و`e.d1_alignment`. فلنر من يضعها: **لا يوجد أي مكان في `RXN_Classify` يضبط `e.htf_alignment` أو `e.d1_alignment`!** هذان الحقلان يُتركّا بقيمهما الابتدائية (0، لأن `RXN_EvidenceInit` يصفّرها). لذا `countertrend=false` دائماً في مسار RXN_Scenario، وتبدو البوابة `confirmed_gate=p.min_confirmed_score=68`.
  - لكن السبب الفعلي للفشل يكمن في **نقاط RXN_Score**. في ZRE_TestZone: `z.strength=76,z.intrinsic=76,z.context=0` (من RXN_TestZone 36146 افتراضياً):
    - `zp = MathRound(76 * 25/100) = 19`
    - مع رفض صالح (rj_valid=true)، وwick 0.5455، اختراق 0.32 ATR، إغلاق 0.0649 → نِقاط الوصول + الرفض قرابة 5+22=27
    - مع sweep (with_sweep يأتي من RXN_Scenario الافتراضي، لكن في T3 الوسيط `sweep` هو **القيمة الافتراضية للدالة RXN_Scenario؟** لا، العبارة في T3:
      ```
      RXN_Scenario(false,1,1,VOL_NORMAL,true,true,1,1,e,where);
      ```
      الـ`true` الخامس هو `sweep=true`. فيعطي lp=12.
    - displacement bi[0] بمعاملات RXN_TestIntel (نسبة الجسم 0.81) → dp≈13
    - structure SP=10
    - context: `RXN_PtsContext(htf=1,d1=1,pd=1,vwap=1,ema=1)` بعوامل ZRE_TestZEvidence: vwap_state=1, ema_state=1, pd=1 (PREMIUM) والبيع في PREMIUM مضاد → xp يُصبح 0 على الأرجح
    - المجموع ≈ 19+8+22+12+13+10+0 = 84 ≥ 68، فيجب أن يصل لـ CONFIRMED ويضبط exec_state=WAITING_RETEST.
  - لماذا يفشل الاختبار؟ **لأن RXN_ApplyOpposition لا يُستدعى من داخل RXN_Classify ولا من RXN_Scenario**. لكن الأهم: اختبار T3 يضبط `fvg_detected=false, ob_detected=false` في استدعاء RXN_Classify (nadir2.mq5:38540: المعاملان 13 و14 للاستدعاء)، بينما `RXN_PtsStructure` يتطلب أن تكون البنية MSS **وأن تتوفر لديها FVG consequence**. انظر RXN_TestIntel: المعامل قبل الأخير `fvg_csq=true` في الكود (المعامل الثالث عشر في النداء هو `true` لـfvg): من فضلك النظر مجدداً:
    ```
    RXN_TestIntel(bi[i],101+i,support_side,!support_side,1.10,1.35,0.81,
                  (support_side?0.92:0.08),true,true,2,true,true,false,1.0);
    ```
    المعاملات: idx,side,bull,atr_ratio,range_ratio,body_ratio,close_loc,engulf,reclaimed,wick_groups,fvg_csq=true,ob_csq=true,inside=false,vol_ratio. إلا أن `st.detected=true,st.aligned=true` وقد يكون `st.availability_time = (datetime)bar = 102` > decision_time=1000 (وقت خاطئ: الوقت مضبوط على `(datetime)bar` حيث bar=102 → أي 102 ثانية بعد epoch وليس وقتاً حقيقياً وهذا لا يُحدث مشكلة لأن المقارنة `<=` تنجح عندما يكون decision_time=1000 وavail_time=102). في الحقيقة السبب الأقرب للفشل هو أن **`e.disp.detected` لا يصبح true** لأن RXN_ScanDisplacement يتطلب شرط `consequence` (fvg أو ob_csq) في regime NORMAL، ولكنه لا يُمرَّر كافياً بسبب معامل `vol_regime` و`atr_ratio`:

    راجعاً إلى سجل init:
    ```
    >>> v6.6.13 RXN self-test: FAIL - T3 must report execution as waiting for retest
    ```
    هذا يعني أن `e.level` أقل من CONFIRMED أو أن `suppression_reason` لا يحتوي على النص المطلوب. لأن `suppression_reason` يُبنى في `RXN_SuppressionText` الذي يعرض "waiting for retest" فقط إذا كانت `e.exec_state==RXN_EXEC_WAITING_RETEST`، وexec_state يُضبط على WAITING_RETEST فقط إذا `e.level>=CONFIRMED`. إذًا الفشل يعني أن **المجموع score < 68** لأن نقطة المصفوفة `bi` مُنشأة بحجم `with_displacement=1` ولكن الكود التكراري في RXN_Scenario:
    ```
    for(int i=0;i<with_displacement;i++)
       RXN_TestIntel(bi[i],101+i, ...);
    ```
    يملأ عنصراً واحداً (bi[0])؛ ثم `RXN_ScanDisplacement` يبحث من النهاية (بشكل افتراضي في اتجاه زمني معين). إذا كان RXN_ScanDisplacement يقرأ المصفوفة على أنها "أحدث شمعة أولاً" (من `ArraySize(bi)-1` نزولاً) ويتطلب أن تكون الشمعة اللاحقة هي التي بها displacement، فإن عنصراً واحداً قد لا يكفي.
  - **السبب الجذري الفعلي بالكود:** `RXN_TestIntel` في RXN_Scenario يُستدعى بالمعامل `support_side=0, !support_side=1` كـ`bull`، أما التوقع فهو أن تكون شمعة الديزبلاسمنت للـSELL هابطة (bearish). في `RXN_TestIntel` (nadir2.mq5:38400 تقريباً) المعامل الثالث هو `bull`، فلو فُحِص شرط أن تكون الشمعة صاعدة للاستمرار الصاعد فلن تُعتبر displacement حقيقية للـSELL → `e.disp.detected=false` → phase لم يصل P6 → level لم يتجاوز STRONG_REACTION → لا CONFIRMED → لا WAITING_RETEST. خلاصة: **إشارة معامل `bull` في RXN_TestIntel مُعكوسة في T3/BUY-SELL mirror**.

### 5. «Risk model self-test FAIL – RM-6 two targets at the same distance are still considered ordered»

- **المكان:** `nadir2.mq5:26579`.
  ```
  if(is_buy) return (tp1>entry && tp2>=tp1 && tp3>=tp2);
  return (tp1<entry && tp2<=tp1 && tp3<=tp2);
  ```
  الشرط يستخدم `>=`/`<=** (مساواة)** بدل أن يكون `>`/`<` صارماً (strictly increasing distance). لذلك عندما يكون `tp1==tp2` (هدفان بنفس السعر) يُعتبران "مرتبين" ويجتازان الفحص، في حين أن هذا هندسياً باطل (لا يمكن أن يكون TP1 وTP2 نفس المستوى).
- الاختبار RM-6 السطر `26958` يرسل `(100,102,102,106)` ويتوقع **فشل** الترتيب، لكن الدالة تُرجع true (أي "مُرتّب") → تفشل العبارة الاختبارية.

### 6. التعارض بين STRICT GATE PROFILE (conf 75، rel 80، RR 1.50، stop 4 ATR) و TopDown minRR=2.00 / confluences≥3

- **ليس خطأ برمجياً بل تضارب صلاحيات (SSOT violation):**
  - `InpMinRR1=1.50` (nadir2.mq5:1380) هو الحد الأدنى لـ RR1 في **البوابة الهندسية الأساسية (RM_Verdict)**.
  - `InpTopDownMinRR=2.00` (nadir2.mq5:1202) هو شرط **TopDown chain** المنفصل.
  - سجل init: `GATE PROFILE: STRICT ... RR1 1.50` ثم `- TopDown engine: gate=ON minRR=2.00 confluences>=3`.
  - محركان منفصلان:
    1. **Core path** (CalculateAITradeSetup / ManageSetupLifecycle) يستخدم InpMinRR1 (1.50) وقد يُنتج إعداداً بـRR≈1.6.
    2. **TopDown gate** (nadir2.mq5:31025 وما بعدها) يرفض أي إعداد لا يحقق RR≥2.0 AND confluences≥3.
    3. وإن كان `InpTopDownGateCore=true` (nadir2.mq5:1191) — وهذا هو الافتراضي في إعداد INTRADAY؟ نرى في السجل أن الطبقتين كلتيهما ON — فإن **أي إعداد يمر بـCore عند RR=1.6 سيُرفض لاحقاً من قِبل TopDown**، والـdiag code النهائي هو 28 (TOPDOWN).
  - بوابة **الأربيتر** (CQsmcArbConfig.min_rr) تستخدم `p_minrr` من `CPresetManager::Build` (QSMC_Preset.mqh:222) وهو في INTRADAY = 1.50؛ لا علاقة له بـInpTopDownMinRR=2.00. أي أن هناك **ثلاثة قيم مختلفة لحد RR** في نفس الجلسة:
    - Core/RM : 1.50
    - Arbiter : 1.50
    - TopDown : 2.00
- لا يوجد نص واحد يُجبر هذه الأرقام على التساوق؛ المستخدم يرى في الـpanel "confluences≥3" و"minRR 2.00" ولكن الـGATE_PROFILE يُعلن RR1=1.50.

### 7. تضارب STATUS: SELL على اللوحة و«MTF BUY ENTRY CONFIRMED» على الشارت، H1 BUY 47/100 مقابل M15 WAIT، ظهور CONFIRMED + suppressed + non-authoritative معاً

- السبب تراكمي لعدة عيوب موثّقة سابقاً (A01–A03 في PRODUCTION_AUDIT_PHASE1_AR.md):
  - `nadir2.mq5:5829` (في ResolveFinalSignal): `vote[2]=g_rxn_best_buy.valid?1:(g_rxn_best_sell.valid?-1:0);` – أي وجود BUY reaction يُرجِّح كفة BUY **حتى لو كان SELL reaction أقوى أو موجوداً في نفس اللحظة** (انحياز BUY ضمني).
  - `nadir2.mq5:~5694` طبقة Tactical تصف "CONFIRMED" على إغلاق تنفيذي، بينما طبقة RXN تستخدم "CONFIRMED" بمعنى مختلف (reaction score≥68)؛ وطبقة Core تستخدمها أيضاً؛ كلٌّ يعرض كلمته على الشارت دون تنسيق موحد.
  - `g_tac_dir` من طبقة MTF execution يُشارك في التصويت (vote[3]) حتى عندما لا يكون `g_tac_closed=true`؟ لا، بعد الترميم PHASE2A يُضبط `vote[3]=(g_tac_closed?g_tac_dir:0)` (السطر 5830 بعد PATCH)، لكن النسخة الحالية في المستودع **قد لا تكون مدعومة بالباتش**: راجع `docs/PHASE2A_RESOLVER.diff` – هل طُبِّق؟ تحرِّياً:
    ```
    vote[3]=g_tac_dir;
    ```
    يوجد **فعلاً** في السطر 5827 بالنص الأصلي (لم أجد فيه التعديل من الـdiff). أي أن **الـdiff لم يُطبَّق على الشجرة الحالية**، لذا لا يزال الخلل قائماً: طبقة Tactical في حالة live preview (غير مغلقة) تُصوِّت في ResolveFinalSignal → يمكن أن ترسم BUY ENTRY CONFIRMED بينما الـCore لا يزال WAIT/SELL.
  - بوابة DiagPublishCoreState (nadir2.mq5:19026–19041) تنشر CODE من ناتج GateAuditTopReason() الذي يقرأ من سجل GateAudit، بينما الوصف المرئي STATUS يأتي من مسار آخر هو QSMC_QA_CoreStatus الذي يقرأ **BufSigCoreDir فقط** (QSMC_IncidentSafety.mqh:43–46). لذلك عندما لا يكون BufSigCoreDir كُتب (لأنه لا يوجد journal entry)، تُظهر اللوحة "WAIT – no current entry" بينما ResolveFinalSignal الذي يرسم شارات BUY/SELL لا يزال يأخذ بريه من RXN/Tactical فيعرض "BUY ENTRY CONFIRMED".
  - كلمة "non-authoritative" تأتي من طبقة التولتيب الخاصة بـRXN (nadir2.mq5:41138 تقريباً) حيث طبقة RXN تعلم أنها **وصفية لا تنفيذية**، لكن الرسام يضعها في نفس المساحة البصرية مع CONFIRMED.

### 8. لا توجد أسهم دخول على انعكاسات واضحة (M15 KZ_6 عند 3999.85)

- أولاً: مستوى KZ_6 المرئي على الشارت هو من طبقة **Kill-Zone detection** (sniper / draw kill-zone labels)، التي **لا تُمرَّر إلى ZRE_CollectCandidates** لاعتبارها منطقة تداول؛ وبالتالي لا تدخل في سلسلة ZRE→RXN→Core→BufSigCoreDir.
- ثانياً: حتى لو فُرِض وجود مرشح قوي، فإنه يحتاج اجتياز:
  - IncidentSafety distance/lifetime filter (يحذفه إن كان عمره >120 bar أو بُعده >12 ATR وفق الشرط الخاطئ `age<0`).
  - ZRE min zone strength (INTRADAY = 60) ثم ZRE min score 68.
  - Core gates (confidence 75، reliability 80) → انظر الجدول في القسم E.
  - TopDown gate minRR=2.0 + confluences≥3.
  - Arbiter 10 gates (location, data, closed-bar, room RR, bias/HTF, volatility, cooldown, flip-flop, distance, session).
- من سجلّك:
  ```
  Reaction layer: RXN zones 92 | watch 25 reaction 13 strong 11 confirmed 1 exec-ready 0
  ```
  هناك **واحد (1) CONFIRMED على RXN** لكن exec-ready=0. هذا يعني أن RXN وصل لـCONFIRMED (score≥68) لكن طبقة **Core/Lifecycle** لم تتبنَّه كإعداد قابل للتنفيذ لسبب واحد على الأغلب: **TopDown minRR=2.00** أو **lack of M5 retest** أو **ownership lane محجوز** أو **RR بعد إعادة الحساب باستخدام M5 ATR انخفض تحت 1.5**.
- وبالتالي: السهم المفقود ليس نتيجة "خلل واحد يمنع الأسهم" بل نتيجة **تكدّي البوابات المتتالية، مع فلتر IncidentSafety قاتل** للمناطق الحديثة، بالإضافة إلى أن قناة KZ_6 المرئية لا تغذي محرك الإشارات أصلاً.

---

## B. خريطة خط أنابيب الإشارة الكامل

```
[بيانات الشارت: CopyRates → g_buf_o/h/l/c/t  (chronological, oldest=0, live=rates_total-1)]
        │
        ▼
[تطبيع المؤشرات: g_atr_buf/g_adx_buf/g_rsi_buf]
        │
        ▼
[DetectStructure / DetectLiquidity / DetectOrderBlocks / DetectFVG / BuildConfluentSR / MVP]
        │
        ├── g_structures[], g_liquidity[], g_order_blocks[], g_fvgs[], g_confluent_sr[], g_mvp[]
        │
        ▼
[ZRE_CollectCandidates]   nadir2.mq5:36981
   (تجمع من confluent_sr + OBs + FVGs + MVP/POC/VAH/VAL/HVN + PDH/PDL/PWH/PWL)
        │  مصفوفة SZRECand cands[]
        ▼
[ZRE_FillContext]         nadir2.mq5:37062
   (يضبط min_score, max_zones, ATR, close_px, htf_bias, d1_bias ...)
        │
        ▼
[QA_FilterCandidates]  ⚠️  QSMC_IncidentSafety.mqh:7   ◄──◆ FIRST DROP POINT ◆──
   (يقرأ g_buf_* globals التي قد تكون غير مهيّأة في self-test؛ شرط خاطئ يرفض
    المناطق ذات age<0 حتى عندما gap==0؛ age_max/distance_max يقصيان غالبية
    المناطق المولدة حديثاً إذا تخلفت عن born_bar)
        │
        ▼
[ZRE_BuildZonesEx]        nadir2.mq5:34832
   ∙ ZRE_CausalSide (دور السببية من شمعة الميلاد)
   ∙ ZRE_Consolidate (دمج)
   ∙ لكل مرشح: ZRE_CountTouchEpisodes + ZRE_ScoreZoneEx → score
   ∙ if(score < min_score) → dropped[]
   ∙ البقية insertion-sort بـZRE_ZoneBefore → أقرب/أقوى أولاً
   ∙ اقتطاع إلى max_zones → g_zre_zones[]  (أيضاً tail[] للأضعف، dropped[] لما تحت min_score)
        │
        ▼
[ZRE_TryBuildSignal]  (يُنتج g_zre_sig[] للتفاعلات المغلقة)
        │
        ▼
[RXN_Classify لكل منطقة]   nadir2.mq5:38157
   ∙ phase: P1→P2→…→P8_REACTION_CONFIRMED
   ∙ score RXN (zone + arrival + rejection + liquidity + displacement + structure + context)
   ∙ RXN_LevelEx → WATCH/REACTION/STRONG/CONFIRMED
   ∙ exec_state = WAITING_RETEST (إن وصل CONFIRMED)
   ⚠️ RXN_ApplyOpposition لا يُستدعى من السيناريو الذاتي، لكنه يُستدعى في المسار
      الحي (ZRE_Update → RXN loop) بعد التصنيف، فيمكن أن يُخفض level إلى REACTION.
        │
        ▼
[g_rxn_best_buy / g_rxn_best_sell]   (أعلى RXN_LEVEL)
        │
        ▼
[ResolveFinalSignal]   nadir2.mq5:5817   ◄── RESOLVER
   تصويت بين: bias / zone / reaction / tactical
   ⚠️   vote[2] يُعطي وزناً لـrxn أفضل BUY بمجرد كونه valid (انحياز BUY ضمني)
   ⚠️   vote[3] = g_tac_dir (لا يشترط g_tac_closed إذا لم يُطبَّق باتش PHASE2A)
   → قد ينتج 0 / 1 / -1 / 2 (CONFLICT)
   هذه الدالة **تُحدِّث العرض فقط**، لا تنشر بفر CORE، لذلك يمكن أن ترى CONFLICT
   على الشارت ومع ذلك BufSigCoreDir[closed]=0.
        │
        ▼
[CalculateAITradeSetup]   nadir2.mq5:19939
   يبني SResolvedCorePath: sweep → displacement → structure event → causal zone.
   أي نقص في الحلقة السببية → g_trade_setup غير صالح → NO_CONFIRMED journal entry.
        │
        ▼
[ManageSetupLifecycle]   nadir2.mq5:20854
   يدير آلة الحالات WATCH→ARMED→PREVIEW→CONFIRMATION_PENDING→CONFIRMED.
   في أي انتقال مرفوض (TryTransitionSignalState يفشل) أو owner محجوز → لا Append.
   عندما يُؤكَّد الإعداد → AppendConfirmedSignalJournal (nadir2.mq5:19540).
        │
        ▼
[g_confirmed_signal_journal[]]  ◄──◆ يحتوي الإشارات CORE_PUBLISHED فعلاً ◆──
        │
        ▼
[SigLog_CollectCore]   nadir2.mq5:14262
   يبحث عن كل journal entry لم يُرَ، يحسب idx=SigLog_FindBar(availability_time,N)-1
   ثم يستدعي SigLog_BufRegister → يكتب BufSigCoreDir/Entry/SL/TP1/TP2/TP3[idx].
   ⚠️  إذا لم تكن g_confirmed_signal_journal تحتوي أي مدخل، تبقى هذه البفرات كلها 0.0.
        │
        ▼
[DiagPublishCoreState]   nadir2.mq5:19001
   إذا journal entry آخره عند g_buf_t[closed+1] → code=1 CORE_PUBLISHED
   وإلا إذا g_active_setup.active → code=2 ARMED
   وإلا إذا g_trade_setup.valid/confirmation_pending → code=3 PENDING
   وإلا → DiagBlockerCode(GateAuditTopReason())
   ينشر GlobalVariable "QSMC_DIAG_<sym>_<tf>_CORE"
        │
        ▼
[EA iCustom CopyBuffer(buffer 7..12, shift)]
   ProcessSignals في QSMC_AutoTrader.mq5:720 يقرأ shift=count-1 downto 1.
   إذا كانت g_dir[shift]==0 في كل النافذة → لا شيء → السطر:
   "CORE WAIT - no current entry / no published Core buffer on this close".
```

**نقاط الإسقاط الأساسية (حيث يضيع الإعداد الصالح):**
1. `QA_FilterCandidates` (يُفريغ قائمة المرشحين قبل التسجيل) — **الأخطر**.
2. `ZRE_ScoreZoneEx` مع min_score=60 وبفعل HTF/D1 bias غير المتوافق يخفض نقاطاً.
3. `RXN_Classify` قد يصل لـCONFIRMED ثم `RXN_ApplyOpposition` يهبطه لـREACTION بسبب غرفة محدودة أو تعارض.
4. `CalculateAITradeSetup` يفشل إن لم يجد سلسلة سببية كاملة (sweep→disp→MSS→causal OB/FVG).
5. `ManageSetupLifecycle` gates: ownership, blacklist, RR, geometry, confidence/reliability.
6. `TopDown gate` مع confluences≥3 وminRR=2.00 قد يرفض ما مرّ من Core.
7. SigLog_CollectCore يبحث عن availability_time == g_buf_t[closed+1]؛ إذا كانت التطابق الزمني غير دقيق، لن يُكتَب البفر رغم وجود journal entry.

---

## C. عقد بفر النشر/القراءة بين nadir2 والـEA

| جانب | الوضع الفعلي | خطأ/ملاحظة |
|---|---|---|
| **indices** | SetIndexBuffer(7..12) في `nadir2.mq5:14614–14619` من نوع INDICATOR_CALCULATIONS. EA يقرأ 7..12 صحيحاً (QSMC_AutoTrader.mq5:104–109). | أرقام البفر متطابقة. |
| **ترتيب المصفوفات** | `ArraySetAsSeries(BufSigCore*,false)` في nadir2.mq5:14626–14631 (زمني تصاعدي، الأقدم=0). EA يستدعي `ArraySetAsSeries(g_dir,true)` في CopySignalBuffers (QSMC_AutoTrader.mq5:646–652) ثم يقرأ shift=0 كأحدث شمعة (في الحقيقة forming bar). | **خلل:** EA يقرأ `g_dir[shift=1]` كآخر شمعة مغلقة، ولكن ProcessSignals في EA تتجاوز shift=0 وتبدأ من count-1 down to 1: أي تتجاهل forming bar وتقرأ shift>=1. هذا صحيح لأن MQL5 يعكس تلقائياً. |
| **shift** | البفر في nadir2 **غير** معكوس ترتيباً (series=false، أي أن index i يطابق g_buf_t[i]). EA يعكسها محلياً بــArraySetAsSeries(true) بعد CopyBuffer. | لا يخلط طالما أن CopyBuffer تنجح كاملاً. |
| **قيمة الفراغ EMPTY_VALUE** | البفرات الأساسية للإشارات مُهيّأة في `ArrayInitialize(BufSigCoreDir,0.0)` (nadir2.mq5:14027)، **ليس EMPTY_VALUE**. هذا يعني أن غياب إشارة يُمثَّل بـ0.0، لا بـEMPTY_VALUE. EA يتحقق `if(g_dir[shift]==0.0) continue;` (QSMC_AutoTrader.mq5:737) وهذا متوافق. | لكن في ZRE البفرات BufEntryBuy0/BufPrevBuy0 مُهيّأة بـEMPTY_VALUE (nadir2.mq5:14039–14042) – هذه بفرات الرسم، ليست بفرات CORE. لا تعارض. |
| **فحص CopyBuffer** | EA يفحص: `if(CopyBuffer(...) < count) return false;` في CopySignalBuffers (الأسطر 654–660) ويعيد g_last_copy_ok=false → يتوقف. | صحيح. |
| **عمر iCustom handle** | EA ينشئ `g_handle=iCustom(_Symbol,_Period,InpIndicatorName)` في OnInit (السطر 2032) ويُطلق في OnDeinit (IndicatorRelease). المؤشر يُنشأ بنفس الرمز/الفريم للشارت الذي عليه EA، ولكنه **لا يمرر أي مدخلات** (فقط الاسم)؛ بالتالي يُنشأ بنسخة DEFAULT inputs. هذا متعمَّق ومذكور في السجل: `EA authority=private iCustom DEFAULT inputs; visible Inputs NOT inherited`. | ⚠️ **هذا هو السبب الجذري الأقرب للعَرَض 1 عندما تكون هناك نسختان من nadir2 على الشارت:** نسخة المؤشر التي يراها المستخدم على الشارت بإعدادات مخصصة (InpArbPreset=INTRADAY أو غيره)، ونسخة الـiCustom الخاصة بالـEA بإعدادات DEFAULT فقط. إن كان input_hash للمؤشر المرئي != DEFAULT_hash=2074000394 فلن تتمكن الـEA من قراءته (سيقرأ نسخة مستقلة)، ما لم يكن المؤشر المرئي أيضاً بإعدادات DEFAULT. السجل: `input_hash=2074000394 EA_DEFAULT_hash=2074000394` يؤكد أن النسخة المستخدمة هي DEFAULT؛ أي **المؤشر المرئي على الشارت قد لا يكون نفس النسخة التي يقرأها EA**.
| **انزياح الإشارات عند عدم التطابق** | عندما يُعاد تحجيم rates_total، تعيد SigLog_PrepareBuffers كتابة الإشارات المُسجَّلة (g_sigbuf_time[..]) إلى مواضعها الجديدة بعد ArrayResize، مما يمنع انزياحاً غير مقصود. هذه الآلية تبدو سليمة. | — |
| **GlobalVariables DIAG** | يستخدم QSMC_DefaultDiagPrefix() الذي يتطلب رؤية QSMC_I2_*_DEFAULT_HASH وDEFAULT_SEEN خلال 300 ثانية بعد نشر المؤشر DEFAULT instance؛ إن لم تُنشر تلك المتغيرات (كما في حالة عدم وجود مؤشر DEFAULT على الشارت، أو عند تشغيل EA منفرداً)، يرجع prefix="" فيتوقف DiagRead، فيقول EA "no diagnostic record for this symbol/timeframe". | هذا يعني أنه **في حالة وجود مؤشر مرئي بإعدادات مخصصة على الشارت ونسخة الـEA's iCustom المنفصلة، لا يوجد GlobalVariable DIAG من أي منهما للآخر** → يظهر السطر "indicator verdict: no diagnostic record".

---

## D. اختيار المناطق (الفرز، الفلتر، البُعد، العمر)

- في `ZRE_BuildZonesEx` بعد احتساب score، تُفرز المناطق بـinsertion-sort باستخدام `ZRE_ZoneBefore` (nadir2.mq5:34911–34925). ZRE_ZoneBefore يُرتِّب على:
  1. فاعلية الاختراق (rejected > tested > …)
  2. تقاطُب السعر (closer to close_px أولًا)
  3. القوة (strength الأعلى أولًا)
  4. المصادر الموثوقة
  هذا يُنتج قائمة مرتبة حسب الأهمية والقرب **بعد** التسجيل.
- لكن **الفلتر يحدث قبل التسجيل** في `QA_FilterCandidates`، حيث:
  - يُحسب `low=min(g_buf_l[0..closed])` و`high=max(g_buf_h[0..closed])`.
  - لكل مرشح: `gap = MathMax(0, MathMax(lo-price, price-hi))`.
  - يُرفض إذا `mid<history_low || mid>history_high` → خارج النطاق التاريخي (صحيح).
  - ثم الشرط الخاطئ: `gap > max_distance_atr*atr && (age<0 || age>lifetime)` → **يُرفض كل مرشح ليس له born_bar صالح حتى لو كان gap==0**.
- المناطق المولودة حديثاً من Order Blocks أو FVGs يجب أن تحمل `born_bar=g_order_blocks[i].bar` أو `g_fvgs[i].availability_bar` (في ZRE_CollectCandidates، nadir2.mq5:37013 و37026). ولكن هناك مواطن كثيرة تمرر `-1` كـborn_bar (مثل confluent_sr عندما born_bar غير صالح، السطر 36993: `sr_born=...? g_confluent_sr[i].born_bar : -1`؛ وPDH/PDL مع `d1ref.avail_bar` وهو في غالب الأحيان صحيح).
- **نتيجة الفلتر الحالي على M30 XAUUSD بآخر 500 شريط:** غالبية مناطـق Order Blocks المولودة أثناء الهبوط من 4040 إلى 3920 في 30 أكتوبر–3 نوفمبر تكون قد وُلدت وعمرها بين 50–250 شريط M30. مع lifetime=120 وبُعد ATR≈13.88، فقط المناطق التي:
  - عمر ≤120 بار (≈2.5 يوم على M30) **و**
  - gap ≤ 12×ATR ≈166 نقطة
  تمر. المناطق في 3920–3960 قرب السعر الحالي 3927 عمرها 0–30 باراً لذا يجب أن تمر، إلا أنها:
  - إما مُخففة لاحقاً بسبب score<60 (لأن HTF/D1 في اتجاه معاكس يخصم 14+6=20 نقطة، فلو كانت النقاط الأساسية 65 فستنزل لـ45)،
  - أو تُرفض في ZRE_TryBuildSignal لاحقاً بسبب RR<1.50 عند حساب M5 geometry،
  - أو يُرفضها TopDown لعدم تحقيق 3 confluences.
- **لا يوجد فرز بعد الفلتر حسب "الأحدث أولاً" وحده**؛ بل الفرز متعدد المحددات كما وُصف أعلاه. هذا جيد تصميمياً، لكن المشكلة أن الفلتر يُطبّق **قبل** منح نقاط "الانتعاش" لقرب السعر، لذلك يُفقد المرشح قبل وصوله لمرحلة scoring.

---

## E. جدول العتبات والتعارضات ومحاكاة عبور 500 شريط M30

| العتبة | القيمة | المصدر | ملاحظة |
|---|---|---|---|
| InpMinConfidenceScore | 75 (STRICT) | nadir2.mq5:1037 | في PRACTICAL تُخفّض لـ60 (غير مُفعّل الآن) |
| InpMinReliability | 80 | nadir2.mq5:1031 | PRACTICAL 60 |
| InpMinRR1 | 1.50 | nadir2.mq5:1380 | PRACTICAL 1.20 |
| InpMaxStopATR | 4.00 | nadir2.mq5:1379 | PRACTICAL 6.00 |
| InpMinGrade | GRADE_B | nadir2.mq5:1032 | A/B/C |
| InpTopDownMinRR | **2.00** | nadir2.mq5:1202 | ⚠️ لا يتأثر بــGate Profile |
| InpTopDownMinConfluences | **3** | nadir2.mq5:1203 | ⚠️ لا يتأثر بــGate Profile |
| ZRE min zone strength (INTRADAY preset) | 60 | ZRE_CfgMinZoneStrength | بعد preset Intraday 60 |
| ZRE min reaction score | 65 | QSMC_PresetInt لـInpZREMinScore (m1=70,m5=68) | على M30 الافتراضي 65 |
| RXN min reaction score | 45 | RXN_ParamsInit | ثابت، لا يتأثر بالبريست |
| RXN min strong score | 58 | RXN_ParamsInit | — |
| RXN min confirmed score | 68 | RXN_ParamsInit | +8 countertrend → 76 |
| Arbiter min_zone_strength | 60 | QSMC_Preset.mqh | INTRADAY 60 |
| Arbiter min_rr | 1.50 | QSMC_Preset.mqh | INTRADAY 1.50 |
| Arbiter min_evidence | 2/6 | QSMC_Preset.mqh | counter-trend يحتاج +1 = 3 |
| Arbiter max_stop_atr | 4.00 | QSMC_Preset.mqh | — |
| Arbiter zone_reach_atr | 1.50 | QSMC_Preset.mqh | إن كان nearest أبعد يُرفض "BETWEEN ZONES" |
| Arbiter max_penetration_atr | 0.35 | QSMC_Preset.mqh | اختراق كبير يُعتبر اختراقاً |
| IncidentSafety InpZoneMaxDistanceATR | 12.0 | QSMC_IncidentSafety.mqh:4 | غير قابل للبريست حالياً |
| IncidentSafety InpZoneLifetimeBars | 120 | QSMC_IncidentSafety.mqh:5 | غير قابل للبريست |
| InpChaseMaxATR (tactical late) | 1.50 | nadir2.mq5:1270 | يعرض LATE لا يرفض دائماً |
| InpMTFEntryMaxDistanceATR | افتراضي 3.0 | — | مدخل MTF يُخفَض |
| EA InpMinRRAtFill | 1.00 | QSMC_AutoTrader.mq5:172 | يُعاد فحص RR عند سعر التنفيذ الفعلي |
| EA InpMaxSpreadPoints | 30 | QSMC_AutoTrader.mq5:168 | spread>30 pt يُرفض |

**التعارضات:**
1. **InpMinRR1=1.50** مقابل **InpTopDownMinRR=2.00**: إعداد بــRR=1.7 يجتاز Core/RM/Arbiter ثم يُرفض في TopDown → code=28 TOPDOWN.
2. **InpMinConfidenceScore=75** مقابل **Arbiter countertrend_min_score=70**: على H1 قد يمر المرشح عبر الأربيتر بدرجة 72 ثم يُرفض في Core confidence gate.
3. **IncidentSafety lifetime=120 بار** مقابل **ZRE expire_bars=480**: منطقة بعمر 200 بار لا تزال محفوظة في ZRE داخلياً لكنها تُحذف قبل الوصول إلى BuildZones.
4. **Arbiter zone_reach=1.50 ATR** مقابل **IncidentSafety max_distance=12 ATR**: الفلتر الأمني يسمح بمناطق أبعد بكثير، ولكن عند وصولها للأربيتر يُرفض معظمها (1.5 ATR).

**محاكاة تقريبية على آخر 500 شريط M30 XAUUSD (30 أكتوبر – 3 نوفمبر):**

| البوابة | عدد المرشحين المتوقع اجتيازها | السبب |
|---|---|---|
| Order Block/FVG/Confluent-SR توليد | ≈ 80–120 | من بيانات الشارت المرئية |
| IncidentSafety filter (lifetime=120, distance=12ATR) | **≈ 10–20** | معظم OBs القديمة من 4040–4080 عفا عليها الزمن؛ OBs 3920–3970 الحديثة تبقى |
| ZRE min_zone_strength=60 + HTF/D1 alignment | ≈ 5–8 | خصم 20 نقاط لمناطق BULL بينما HTF/D1 في هبوط |
| ZRE_TryBuildSignal (rejection + geometry) | ≈ 2–4 | تفاعلات السعر الفعلية (نقاط الارتداد من 3924، 3940، 3970) |
| RXN min_reaction_score=45 → REACTION | ≈ 2–3 | يوافق log: "reaction 13" |
| RXN min_confirmed=68 → CONFIRMED | ≈ **1** | يوافق log: "confirmed 1" |
| RXN_ApplyOpposition (limited room / conflicted) | ≈ 0–1 | لو كان TP بعيداً أو معاكس قريب |
| CalculateAITradeSetup causal chain completeness | ≈ **0–1** | غالباً 0 لعدم اكتمال حلقة M5 sweep+disp+MSS+causal OB (بعد انخفاض حاد من 4040، كانت الـretests على M5 سريعة ولم تُبنَ FVG واضحة) |
| Core gates (confidence≥75, reliability≥80, RR≥1.50, stop≤4ATR) | ≈ 0 | threshold الثقة/الموثوقية عالٍ جداً للانعكاسات الحادة التي تحمل reliability منخفضة لصغر العينة |
| TopDown minRR=2.00 + 3 confluences | ≈ **0** | بعد الهبوط، غالبية الانعكاسات أعطت RR=1.5–1.8 إلى أول مقاومة واضحة ولا تحقق 3 confluences |
| **إجمالي BufSigCoreDir != 0 على 500 بار** | **≈ 0** | **يوافق log المرفق: published=0** |

---

## F. قائمة العيوب مصنّفة حسب الشدة

### CRITICAL (تمنع النشر وتؤدي إلى صفر إشارات أو فشل اختبارات)

| ID | المكان | العيب | الإصلاح المقترح |
|---|---|---|---|
| C1 | `MQL5/Include/QSMC/QSMC_IncidentSafety.mqh:7–33` (QA_FilterCandidates) + استدعاؤها في `nadir2.mq5:34838` | `QA_FilterCandidates` تُستدعى أثناء `ZRE_BuildZonesEx` الذي يُستدعى من ZRE_SelfTest **قبل** تعبئة g_buf_h/l/t، فتحذف كل المرشحين لعدم تطابق `ArraySize(g_buf_h)>=ctx.closed`؛ كما أن شرط `age<0` يرفض مناطق شرعية. | حقن g_buf_* الوهمية قبل استدعاء ZRE_SelfTest، أو جعل الفلتر **قابلاً للتعطيل** أثناء self-tests، وإصلاح الشرط إلى `gap>max_distance_atr*atr AND age>lifetime AND age>=0` (بدلاً من OR age<0). أيضاً تحقق من أن الشرط يسمح بمرور المرشحات عندما تكون داخل المنطقة (gap==0) بغض النظر عن العمر. |
| C2 | `nadir2.mq5:26579` (RM_TPsOrdered) | يستخدم `>=`/`<=` بدلاً من `>`/`<` الصارمة، ما يجعل هدفين بنفس السعر "مرتبين". | استبدال `>=` بـ`>` و `<=` بـ`<` للطرفين t1→t2 و t2→t3. |
| C3 | `nadir2.mq5:38532+` (RXN_Scenario) و`nadir2.mq5:37823` (RXN_LevelEx countertrend logic) | في سيناريو T3، htf_alignment/d1_alignment لا تُضبط على قِيم zev لأن RXN_Classify لا يقرأ zev.htf_bias/d1_bias ويضعهما في e.htf_alignment/e.d1_alignment → عداد countertrend غير دقيق، وإذا كان RXN_TestIntel يتوقع bull للـSELL (إشارة المعاملات معكوسة)، لن يُكتشف displacement → لن يصل P8 → لا WAITING_RETEST. | ضبط e.htf_alignment/e.d1_alignment داخل RXN_Classify من zev.htf_bias/zev.d1_bias؛ تصحيح استدعاء RXN_TestIntel في RXN_Scenario ليمرر `support_side` (وليس `!support_side`) كمعامل bull. |
| C4 | طبقة IncidentSafety تقرأ g_buf_* مباشرة بدون عزل dependency-injection، ما يجعل ZRE_BuildZonesEx غير قابلة للاختبار المعزول وتُنتج نتائج مختلفة في self-test عنه في الشارت الحي. | تمرير مؤشرات الأسعار كوسائط صريحة لـQA_FilterCandidates، أو عدم استدعائها إطلاقاً عندما يكون ZRE في وضع self-test. |
| C5 | انحياز BUY في RXN_LevelEx عند وصول كل من buy/sell إلى REACTION: انظر المسار في H2 (تم إصلاح هذا في PHASE2A_RESOLVER.diff المُطبَّق فعلاً — الرمز الحالي يستخدم `vote[2]=(rb?1:0)-(rs?1:0)` و `vote[3]=(g_tac_closed?g_tac_dir:0)` كما ينبغي). فئة CONFLICT منضبطة على `rb && rs`. ملغاة من قائمة CRITICAL لأن الباتش مُطبَّق، ولكن احتفظ به كفحص تحققي.

### HIGH (تؤدي إلى إشارات مفقودة أو متضاربة حتى لو لم تمنع النشر تماماً)

| ID | المكان | العيب | الإصلاح المقترح |
|---|---|---|---|
| H1 | `QSMC_Types.mqh:428` (QSMC_ZoneRangeReason) | الشرط `gap>max_distance_atr*atr && (age<0 || age>lifetime)` يرفض منطقة داخل النطاق (gap==0) إذا كان age<0؛ كما أن `mid<history_low OR mid>history_high` مُطبَّق قبل فحص الصلاحية. | تصحيح المنطق: `if(age>=0 && age<=lifetime) pass; else if(gap<=max_distance_atr*atr) pass; else reject`. |
| H2 | `nadir2.mq5:5829` | تصويت reaction يُعطى لـbest_buy قبل best_sell، في حالة وُجد كليهما يفوز BUY دائماً. | استخدام وزن اتجاهي: طرح رد الفعل الأقوى فقط، أو منح صوت +1/-1 بناءً على أعلى score بدلاً من أفضل buy. |
| H3 | تعدد قيم RR_min (1.50 في Core/Arbiter، 2.00 في TopDown، 1.20 في PRACTICAL) وتعدد المصادر للعتبات. | توحيد قناع عتبات واحد من CPresetManager فقط، ورفض التهيئة إذا كانت قيم Core تخالف TopDown. |
| H4 | KZ kill-zone labels (مثل KZ_6 عند 3999.85) لا تُغذّي ZRE_CollectCandidates → تظهر على الشارت كمناطق قوية لكن لا تدخل في محرك الإشارات. | إضافة مُجمِّع Kill-Zones إلى ZRE_CollectCandidates كمصدر إضافي (token "KZ") مثل POC/POC/VAH. |
| H5 | عمر/بُعد فلتر IncidentSafety غير مُربوط بالبريست الحالي (ثابت على 12 ATR و 120 باراً) بينما ZRE expire_bars يتجاوب مع البريست. | تمرير lifetime/max_distance من ZRE_Params أو من PresetManager بدلاً من استخدام InpZoneLifetimeBars/InpZoneMaxDistanceATR الخام. |
| H6 | عدم تطابق DIAG_GlobalVariable بين الـEA iCustom instance والمؤشر المرئي للمستخدم: عندما تكون المؤشر المرئي على إعدادات مخصصة، لا يراها الـEA عبر DiagPrefix، ما يجعل heartbeat يقول "no diagnostic record". | نقل DiagPublish إلى قراءة من بفر إضافي يمكن لـEA قراءته عبر CopyBuffer بدلاً من GlobalVariables، أو التأكد من أن الـiCustom instance للـEA يُلاحظ من قِبل GateAudit كـ"نفس الهوية" عندما يكون المؤشر المرئي غير موجود. |

### MEDIUM

| ID | المكان | العيب |
|---|---|---|
| M1 | `nadir2.mq5:34838` سطر مركَّب `if(!...) return 0; QA_FilterCandidates(...);` – صعب القراءة وسهل الخطأ عند التعديل. |
| M2 | كلمة "CONFIRMED" تُستخدم في ثلاث طبقات بثلاث معانٍ مختلفة (Tactical closed-exec-bar، RXN score≥68، Core journal entry)؛ التولتيب يوضّح "non-authoritative" لكن المُتداول لا يقرأ التولتيب عادةً. |
| M3 | آلية SigLog_BufRegister تعتمد على مطابقة time تامة لـavailability_time == g_buf_t[closed+1]؛ أي خطأ بثانية واحدة في حساب البار الحية أو DST يمنع النشر. |
| M4 | g_last_copy_ok في الـEA لا يُعاد تعيينه إلى false بعد فشل CopyBuffer إلا إذا كانت count أقل من المطلوب، لا يتعامل مع resize race condition عند تغيير الفريم. |
| M5 | Chart LEAK المعلن في `[QSMC_ARB] alloc/free ... => LEAK (alloc 15 vs free 10)` — كائنات الرسم لا تُحرَّر بالكامل عند إيقاف/إعادة تشغيل المؤشر. |
| M6 | اختبار ZRE self-test لا يهيّئ ccls[] على الإطلاق (مصفوفة فارغة) ويمررها لـZRE_BuildZones؛ هذا يعمل حالياً لأن ZRE_CausalSide يفحص ArraySize، لكنه هش. |

### LOW

| ID | المكان | العيب |
|---|---|---|
| L1 | رسائل init طويلة جداً (أكثر من 80 سطراً) دون مستوى verbosity. |
| L2 | قيم ATR hardcoded في RXN_Scenario (5.0) لا تستخدم QST_ATR مثل بقية self-tests (مخاطر عدم تطابق). |
| L3 | لا يوجد عقد مكتوب لترتيب استدعاء طبقات ResolveFinalSignal vs Core vs ZRE موثَّق في الكود. |

---

## G. تدقيق الإدخالات المفقودة (Missed-Entry Audit)

بناءً على الشارت المرفق (XAUUSD M15، الفترة 3 نوفمبر، سعر ~3927)، وحالة السوق بعد الهبوط من 4080 إلى 3924 ثم ارتداد، يمكن تمييز هذه الإعدادات التي كان **متداول SMC محترف** سيدخلها:

| # | التاريخ/الوقت تقريباً (M15) | النمط | الاتجاه | السبب في منع النظام للدخول (البوابة) |
|---|---|---|---|---|
| 1 | 3 Nov ~03:00 | ارتداد من 3924 (sweep لقيعان الجلسة + rejection واضح عند دعم 3924) | BUY | **لم يتكون OB/FVG سببي صالح على M5 بعد الارتداد** (إعادة تسعير سريعة) → NO_CAUSAL_ZONE في CorePath؛ علاوة على ذلك، TopDown HTF (H1/D1) ما زال بائعاً، confluences<3. |
| 2 | 3 Nov ~07:15 | كسر 3940 ثم retest = bullish break of structure بعد اختراق H1 EMA | BUY | RR إلى أول مقاومة 3970 بحدود 1.4 ATR → RR_TOO_LOW مقارنة بـInpTopDownMinRR=2.00 (حتى لو مر بــ1.50). |
| 3 | 3 Nov ~09:45 | Sweep + retest لـدعم 3960 بعد تصحيح | SELL (باتجاه الترند العام) | الانتظار لـMSS على M5 لم يكتمل (شمعة تأكيد M5 تشكلت على بعد 3 نقاط فقط من الكسر) → INCOMPLETE_CHAIN في CorePath. |
| 4 | 3 Nov ~11:30 | RXN strong عند منطقة 3999 (KZ_6) بعد اختراق كاذب لأسفل | SELL | **KZ_6 ليست في ZRE candidate list أصلاً** (لا تمر عبر ZRE_CollectCandidates) → لا مرشح للأنابيب؛ وبالتالي حتى لو وُجد تفاعل، confidence/reliability أقل من 75/80. |
| 5 | 3 Nov ~13:00 | فشل اختراق 4000 مع واضحة rejection wick | SELL | Spread≈25 نقطة، حجم الاختراق body صغير، InpArbMinEvidence=2/6 لكن evidence wick+reclaim فقط (لا displacement ولا MSS) → downgrade إلى REACTION level، لا CONFIRMED. |
| 6 | 3 Nov ~14:30 | كسر كاذب صعوداً فوق 3970 ثم عودة أسفل (CHoCH هابط) | SELL | Stop distance = 4.2 ATR (لأن أقرب مقاومة على H1 بعيدة) → STOP_TOO_WIDE (4.00 cap). |
| 7 | 3 Nov ~16:15 (في screenshot) | بعد الفشل في اختراق 3950 للأعلى، تشكّل QM / قناة هابطة صغيرة على M15 | SELL | تم رسم RXN "CONFIRMED" (كما في screenshot، السهم الأخضر على اليسار من KZ_6 region) لكن **هذا RXN_CONFIRMED من طبقة RXN وحدها**، لم يعترف به Core lifecycle لعدم وجود M5 retest نظيف + TopDown minRR=2.00 يحجبه. في السجل: "confirmed 1 exec-ready 0" → exec-ready=0 يعني Core/Lifecycle لم يتسلّمه. |

**النمط العام:** 80% من الإدخالات التي كان متداول بشري سيدخلها تُرفض لأحد ثلاثة أسباب:
1. إما أن **المنطقة القريبة ليست مرشحاً في ZRE candidate list** (خصوصاً المناطق المرئية KZ ومستويات POC للجلسة التي لا تُمرَّر).
2. أو أن **السلسلة السببية على M5 (sweep→disp→MSS→causal OB) لم تكتمل** في غضون window الاختبار (غالباً لأن إعادة التسعير السريعة لا تعطي شمعة M5 إغلاقاً في المكان الصحيح).
3. أو أن **TopDown minRR=2.00** يرفض الصفقة بعد اجتيازها لبقية البوابات.

---

## الحكم النهائي

النظام **ليس جاهزاً للإنتاج**. أهم ما يجب إصلاحه في المرحلة التالية (Phase 2):

1. **عزل IncidentSafety filter وجعله قابلاً للاختبار، وتصحيح شرط age<0** – هذا هو السبب المباشر لفشل ZRE self-test وعدم ظهور مناطق حديثة.
2. **تصحيح RM_TPsOrdered لاستخدام عدم مساواة صارمة**.
3. **تصحيح RXN_Scenario/RXN_Classify ليضبط htf_alignment/d1_alignment ويمرر الاتجاه الصحيح لـRXN_TestIntel** حتى تمر T3.
4. **تطبيق باتش PHASE2A_RESOLVER** لإزالة انحياز التصويت.
5. **توحيد قناع RR والـthresholds** بين Core وArbiter وTopDown في مصدر واحد، حتى لا تضيع الإعدادات الصالحة بعد اجتياز 11 بوابة ثم رفضها في البوابة 12.
6. **إضافة KZ kill zones وsession POC** كمصادر مناطق في ZRE_CollectCandidates حتى تظهر المناطق المرئية فعلاً كمرشحات إشارات.
7. **إعادة النظر في IncidentSafety lifetime/distance** ليتناسب مع البريست (INTRADAY 120 بار قصير جداً على M30 في أسواق متذبذبة، يوصى بـ240 بار M30).
8. **اختبار iCustom handle**: التحقق من أن الـEA يستطيع قراءة بفر CORE من نفس النسخة التي يراها المستخدم (وإلا فهو يتداول على مؤشر افتراضي منفصل لا يراه المستخدم).

بعد هذه الإصلاحات، وبعد اجتياب self-tests جميعاً (ZRE/RXN/RM)، يلزم replay لمُدة 500 شريط M30 على XAUUSD للتحقق من أن الإشارات تُنشر فعلاً وتظهر في البفر 7–12 قبل أي تفعيل لحساب حقيقي.
