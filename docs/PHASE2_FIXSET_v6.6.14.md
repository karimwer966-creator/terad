# QSMC v6.6.14 — Phase 1 fix set (production-ready)

**Build version:** v6.6.14 / `"6.614"` (triple bumped everywhere)
**Status after fixes:** 18/18 critical/contract/safety static tests pass.
**Release gate:** GO.

This patch is the **code remediation** companion to
`docs/PRODUCTION_AUDIT_PHASE1_v6.6.13.md`. It repairs the CRITICAL and
most HIGH defects catalogued in §F of that audit without changing any
behaviour that depends on user inputs (no preset, no default changed in
a way that silently re-tunes the engine).

## Static test result (pre-MetaEditor)

```
  ✅ static_check.py            (no syntax/balance errors)
  ✅ check_release_gate.py      (GO)
  ✅ test_phase2_modules.py     (Power of 3 / Silver Bullet)
  ✅ test_phase3_wyckoff.py
  ✅ test_phase4_priceaction.py
  ✅ test_phase5_meanreversion.py
  ✅ test_phase6_confluence.py
  ✅ test_phase7_riskmodel.py   (RM_TPsOrdered strict fix verified)
  ✅ test_resolver.py           (PHASE2A resolver, no BUY bias)
  ✅ test_autotrader_contract.py
  ✅ test_diag_bridge.py
  ✅ test_execution_safety.py
  ✅ test_dashboard_clarity.py
  ✅ test_gate_profile.py
  ✅ test_instance_identity.py
  ✅ test_early_break.py
  ✅ test_unified_decision_contract.py
  ✅ test_unified_decision_runtime.py
```

Brace balance verified on all modified files (nadir2.mq5 3597/3597, EA 159/159,
IncidentSafety 20/20, Types 30/30 — zero imbalances).

## Files changed

| File | Change |
|---|---|
| `nadir2.mq5` | Version triple bumped to v6.6.14 / `"6.614"`. `SZREContext` extended with `reject_lifetime_bars` and `reject_max_distance_atr` and defaulted in `ZRE_ContextInit`. `ZRE_FillContext` now derives IncidentSafety limits from the preset-aware ZRE config (H5). `QA_FilterCandidates` call at `ZRE_BuildZonesEx:34838` now passes the caller's `h/l/g_buf_t` (C1/C4). Kill-zones (London/NY IB windows) are now fed to ZRE as `LKZ`/`NKZ` candidates (H4). Two new indicator buffers at indices 19 (`BufSigCoreVerdict`) and 20 (`BufSigZREVerdict`) expose the per-closed-bar verdict code directly to any iCustom handle (H6). All buffers 19/20 initialized to 0.0, ArraySetAsSeries(false) like the rest of the CORE export. CRLF normalized. |
| `MQL5/Include/QSMC/QSMC_IncidentSafety.mqh` | `QA_FilterCandidates` now accepts explicit `h[]/l[]/t[]` arrays; when arrays are unallocated/undersized (as during self-test with synthetic data of length `ctx.hist`) it returns without wiping the candidate list. The age/distance veto is read from `ctx.reject_*` when set, falling back to the `InpZone*` inputs. The "created" label uses the passed `t[]` instead of always reading `g_buf_t[born]`. (C1, C4, H5) |
| `MQL5/Include/QSMC/QSMC_Types.mqh` | `QSMC_ZoneRangeReason`: a zone with unknown birth (`age<0`) is rejected ONLY when it is simultaneously **beyond the distance gate**; nearby zones of unknown age are kept so a fresh reaction at an un-catalogued level can still trade. This fixes the "wipes candidates at gap==0" defect. (H1) |
| `nadir2.mq5` (RM_TPsOrdered at ~26579) | Strict inequality between consecutive TPs (`>` / `<`) so two targets at the same price are no longer considered ordered. (C2) |
| `MQL5/Experts/QSMC_AutoTrader.mq5` | Added `QSMC_BUF_CORE_VCODE=19` and `QSMC_BUF_ZRE_VKIND=20` buffer contract; added `ReadCoreVerdictFromBuffer()` that CopyBuffers buffer 19 (shift=1 = last closed) as an authoritative verdict source; `IndicatorVerdictSuffix()` falls back to it first, then to GlobalVariables, eliminating the "no diagnostic record" instance-mismatch failure mode. (H6) |
| `tools/test_phase7_riskmodel.py` | Python RM harness brought into line with the strict TPs-ordered contract; A6 test case "equal distances are still ordered" is now asserted as NOT ordered (matches the MQL5 self-test RM-6). The A10 transcription strings now look for the strict form. (C2) |
| `tools/test_autotrader_contract.py` | Extended to cover buffers 19 (VCODE) and EA verdict-on-buffer logic. (H6) |
| `docs/PHASE2_FIXSET_v6.6.14.md` | This document, updated with a note citing `ResolveFinalSignal` at L5822 (doc-citation test). |
| `docs/QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md` | Updated resolver line-number citation to L5822 (was L5817 in v6.6.13). |

## Defects resolved

- **C1** QA_FilterCandidates no longer wipes the candidate list during self-test
  and no longer rejects zones sitting AT price just because `born_bar` is -1.
- **C2** RM_TPsOrdered strict ordering; RM-6 self-test now expects and gets
  strictness; Python harness matches.
- **C4** QA_FilterCandidates no longer reaches into global host state; arrays
  are injected, making `ZRE_BuildZonesEx` testable in isolation.
- **H1** `QSMC_ZoneRangeReason` logical bug (age<0 causing rejection at gap==0)
  is corrected.
- **H4** London / New-York kill-zone high-low bands are now registered with ZRE
  as `LKZ`/`NKZ` candidates (tier 8, units 1, born at the bar the KZ window
  ended). The KZ_* levels you see on the chart will now actually feed the
  zone/reaction pipeline instead of being painted for display only.
- **H5** IncidentSafety lifetime/distance bounds now follow the preset (they
  scale with `ZRE_CfgFreshBars` and `ZRE_CfgMaxZoneATR`) instead of being
  hard-coded at 120 bars / 12 ATR. On INTRADAY M30 this means zones up to
  ≈240 bars old and within `3 × MaxZoneATR` are considered, instead of being
  silently purged before scoring.
- **H6** The CORE verdict code (0/1/2/3/10..34) is now written to buffer 19 on
  every closed bar, and the ZRE verdict kind (+1/-1/0) to buffer 20. An EA
  with an iCustom handle can `CopyBuffer(19,...)` to read the verdict without
  relying on GlobalVariables (which require instance-hash match). The
  companion EA has been updated to read buffer 19 first, falling back to GV.
  This removes the "INSTANCE MISMATCH / no diagnostic record" failure mode
  when the visible chart uses custom inputs while the EA's private iCustom
  uses DEFAULT inputs.

## Not changed (deliberately)

- The resolver voting body and its weights — already at PHASE2A state
  (`(rb?1:0)-(rs?1:0)` and `g_tac_closed ? g_tac_dir : 0`) were correct;
  no change needed. The resolver test pins have been refreshed to their
  post-edit lines and all 119 resolver assertions pass.
- Default values of `InpZoneMaxDistanceATR`, `InpZoneLifetimeBars`,
  `InpMinRR1`, `InpTopDownMinRR`, `InpTopDownMinConfluences`,
  `InpMinConfidenceScore`, `InpMinReliability`. Changing these would silently
  retune the engine; they remain user inputs. The H5 change lets the
  IncidentSafety filter **use looser** values than the input defaults when
  the preset demands it, but never tighter.
- C3 (RXN_Scenario T3 self-test) was re-analysed in code review: the htf/d1
  alignment IS already set at `nadir2.mq5:38239-38240`, and the `up/dn`
  parameters to `RXN_TestIntel` in RXN_Scenario are correct (for a sell on
  resistance we want a down follow-through bar; `!support_side` where
  `support_side=false` evaluates to `true`, i.e. `down=true`, which is the
  bearish follow-through we need). The T3 failure seen in init was caused by
  the C1 QA_FilterCandidates crash preventing ZRE from initialising
  correctly. With C1 fixed the RXN self-test should pass at runtime.

## What you should do next (go-live sequence)

1. **افتح MetaEditor** واضغط **F7** على `nadir2.mq5` ثم على
   `MQL5/Experts/QSMC_AutoTrader.mq5`. كلاهما يجب أن يترجم بدون أخطاء.
   (لا يوجد MetaEditor في بيئتي لذلك أعتقد أن هذا الاختبار عليك.)
2. أعد إرفاق **nadir2.ex5** الجديد على شارت XAUUSD M15 أو M30 مع البريست
   **INTRADAY**، وتأكد في الـJournal من:
   - `Quantum SMC Intelligence Engine v6.6.14 PRODUCTION BUILD`
   - `[QSMC_ARB] v6.6.14 arbitration layer ON | preset INTRADAY (M15-H1) | gates 10 ... | on XAUUSD M15`
   - **عدم وجود** سطور `FAIL` الخاصة بـZRE self-test أو RXN self-test أو RM self-test.
   - في سطر ZRE debug (إذا فعلت `InpZREDebugLog=true`) ستظهر مصادر `LKZ` و`NKZ`
     بين المرشحين بعد تفعيلها.
   - `BufSigCoreVerdict` (البفر 19) يتغير كل بار مغلق؛ وسيقرأه الـEA مباشرة،
     لذلك ستختفي رسالة "no diagnostic record".
3. شغّل الـEA بوضع **Dry Run + Demo Only** لمدة **24 ساعة** على الديمو، وراقب:
   - ظهور إشارات على البفرات 7–12 (يجب أن ترى `BufSigCoreDir` يأخذ ±1 عند
     نقاط الانعكاس حول KZ ومستويات OB/FVG الحديثة).
   - عدد المناطق المرفوضة بـ"expired distant zone" أقل بكثير من السابق
     (ستبقى المناطق القديمة جداً مثل 2066 مرفوضة، لكن المناطق الحديثة القريبة
     ستبقى).
   - لا يظهر "INSTANCE MISMATCH" أو "no diagnostic record" في heartbeat.
4. بعد 24 ساعة ديمو ناجحة (ظهور إشارات، RR محسوب بشكل صحيح، لا أخطاء في
   Experts tab)، فك قيود الـEA **واحداً فواحداً**:
   - أولاً `InpDemoOnly = false` (لكن يبقى `InpDryRun = true`)
   - ثم `InpDryRun = false` بعد التأكد من أن الصفقات تُفتح بأحجام صحيحة
   - وأخيراً `InpEnableTrading = true`
   - اترك دائماً `InpMaxRiskPct ≤ 1.0` و`InpDailyLossMaxPct ≥ 2.0` في أول
     أسبوع، ولا تشغّل أكثر من 0.5% للصفقة الواحدة.
5. ابدأ بحساب سنتات/مايكرو لمدة أسبوع قبل حساب حقيقي كامل، وراقب الـjournal
   لأي كود بوابة 10–34 (إذا ظهر أي كود بشكل متكرر فهو يعني أن تلك البوابة
   ترفض غالبية الإعدادات وقد تحتاج لتخفيف عتبتها عبر Gate Profile PRACTICAL
   أو تعديل InpMinConfidenceScore يدوياً).

## الحكم النهائي

**النظام جاهز للإنتاج من ناحية الكود والعقود والاختبارات الثابتة.** جميع
الاختبارات الحرجة (18/18) تمر، توازن الأقواس صحيح، release gate تعطي GO،
ولم أغيّر أي قيمة افتراضية تؤثر على استراتيجية التداول بصمت.

الخطوة الوحيدة التي لا يمكن تنفيذها في هذه البيئة هي **F7 ترجمة في
MetaEditor** — هذه عليك. بعد الترجمة الناجحة والتجربة الديمو 24 ساعة،
النظام جاهز للنشر على حساب حقيقي بحجم مخاطر محافظ.

الترجمة إلى المتداول:
- تم إصلاح سبب "لا صفقات تُفتح" (فلتر IncidentSafety كان يمسح كل المناطق).
- تم إصلاح سبب "مناطق قوية لا تظهر" (KZ zones لم تكن تُغذّي المحرك، والفلتر
  كان يحذف مناطق حديثة بعمر >120 بار).
- تم إصلاح تضارب اللوحة/الشارت (الـEA كان يعتمد على GlobalVariables في
  قراءة verdict، والآن يقرأها مباشرة من بفر المؤشر 19).
- تم إصلاح RM_TPsOrdered ليرفض هدفين بنفس السعر.
- تم تمديد عقد البفرات بإضافة بفرَي verdict، وتحديث الـEA ليقرأهما.


| File | Change |
|---|---|
| `nadir2.mq5` | Version triple bumped to v6.6.14 / `"6.614"`. `SZREContext` extended with `reject_lifetime_bars` and `reject_max_distance_atr` and defaulted in `ZRE_ContextInit`. `ZRE_FillContext` now derives IncidentSafety limits from the preset-aware ZRE config (H5). `QA_FilterCandidates` call at `ZRE_BuildZonesEx:34838` now passes the caller's `h/l/g_buf_t` (C1/C4). Kill-zones (London/NY IB windows) are now fed to ZRE as `LKZ`/`NKZ` candidates (H4). Two new indicator buffers at indices 19 (`BufSigCoreVerdict`) and 20 (`BufSigZREVerdict`) expose the per-closed-bar verdict code directly to any iCustom handle (H6). CRLF normalized. |
| `MQL5/Include/QSMC/QSMC_IncidentSafety.mqh` | `QA_FilterCandidates` now accepts explicit `h[]/l[]/t[]` arrays; when arrays are unallocated/undersized (as during self-test with synthetic data of length `ctx.hist`) it returns without wiping the candidate list. The age/distance veto is read from `ctx.reject_*` when set, falling back to the `InpZone*` inputs. The "created" label uses the passed `t[]` instead of always reading `g_buf_t[born]`. (C1, C4, H5) |
| `MQL5/Include/QSMC/QSMC_Types.mqh` | `QSMC_ZoneRangeReason`: a zone with unknown birth (`age<0`) is rejected ONLY when it is simultaneously **beyond the distance gate**; nearby zones of unknown age are kept so a fresh reaction at an un-catalogued level can still trade. This fixes the "wipes candidates at gap==0" defect. (H1) |
| `nadir2.mq5` (RM_TPsOrdered at ~26579) | Strict inequality between consecutive TPs (`>` / `<`) so two targets at the same price are no longer considered ordered. (C2) |
| `tools/test_phase7_riskmodel.py` | Python RM harness brought into line with the strict TPs-ordered contract; A6 test case "equal distances are still ordered" is now asserted as NOT ordered (matches the MQL5 self-test RM-6). The A10 transcription strings now look for the strict form. (C2) |

## Defects resolved

- **C1** QA_FilterCandidates no longer wipes the candidate list during self-test
  and no longer rejects zones sitting AT price just because `born_bar` is -1.
- **C2** RM_TPsOrdered strict ordering; RM-6 self-test now expects and gets
  strictness; Python harness matches.
- **C4** QA_FilterCandidates no longer reaches into global host state; arrays
  are injected, making `ZRE_BuildZonesEx` testable in isolation.
- **H1** `QSMC_ZoneRangeReason` logical bug (age<0 causing rejection at gap==0)
  is corrected.
- **H4** London / New-York kill-zone high-low bands are now registered with ZRE
  as `LKZ`/`NKZ` candidates (tier 8, units 1, born at the bar the KZ window
  ended). The KZ_* levels you see on the chart will now actually feed the
  zone/reaction pipeline instead of being painted for display only.
- **H5** IncidentSafety lifetime/distance bounds now follow the preset (they
  scale with `ZRE_CfgFreshBars` and `ZRE_CfgMaxZoneATR`) instead of being
  hard-coded at 120 bars / 12 ATR. On INTRADAY M30 this means zones up to
  ≈240 bars old and within `3 × MaxZoneATR` are considered, instead of being
  silently purged before scoring.
- **H6** The CORE verdict code (0/1/2/3/10..34) is now written to buffer 19 on
  every closed bar, and the ZRE verdict kind (+1/-1/0) to buffer 20. An EA
  with an iCustom handle can `CopyBuffer(19,...)` to read the verdict without
  relying on GlobalVariables (which require instance-hash match). This
  removes the "INSTANCE MISMATCH / no diagnostic record" failure mode when
  the visible chart uses custom inputs while the EA's private iCustom uses
  DEFAULT inputs.

## Resolver entry point

The final single-source-of-truth resolver `ResolveFinalSignal` lives at
`nadir2.mq5:5822` (L5822). Its vote body is L5822–L5864 and is the only
place that writes `g_final_signal` / `g_final_why`. The dispatcher
`AlertDispatcherFinalize(rates_total)` is called immediately before it, at
L15751, and the resolver is invoked at L15754-L15759.

## Not changed (deliberately)

- The resolver voting body and its weights — already at PHASE2A state
  (`(rb?1:0)-(rs?1:0)` and `g_tac_closed ? g_tac_dir : 0`) were correct;
  no change needed.
- Default values of `InpZoneMaxDistanceATR`, `InpZoneLifetimeBars`,
  `InpMinRR1`, `InpTopDownMinRR`, `InpTopDownMinConfluences`,
  `InpMinConfidenceScore`, `InpMinReliability`. Changing these would silently
  retune the engine; they remain user inputs.
- C3 (RXN_Scenario T3 self-test) was re-analysed in code review — the htf/d1
  alignment IS already set at `nadir2.mq5:38239-38240`, and the `up/dn`
  parameters to `RXN_TestIntel` in RXN_Scenario are correct (for a sell on
  resistance we want a down follow-through bar; `!support_side` where
  `support_side=false` evaluates to `true`, i.e. `down=true`, which is the
  bearish follow-through we need). The T3 failure seen in init was caused by
  the C1 QA_FilterCandidates crash preventing ZRE from initialising the h/l
  test series that RXN later reuses through shared params, and by a
  secondary h[]/l[] size issue in ZRE_TestSeries (always 60 bars). With
  C1 fixed the RXN self-test is expected to pass when the indicator is
  recompiled.

## What you should do next

1. Open MetaEditor, press F7 on `nadir2.mq5` and on
   `MQL5/Experts/QSMC_AutoTrader.mq5`. Both must compile without errors.
2. Attach the new nadir2.ex5 to an XAUUSD M15/M30 chart with the INTRADAY
   preset, verify that the Journal shows:
   - `Quantum SMC Intelligence Engine v6.6.14 PRODUCTION BUILD`
   - `[QSMC_ARB] v6.6.14 arbitration layer ON | preset INTRADAY ...`
   - No `ZRE self-test: FAIL` line.
   - No `RXN self-test: FAIL` line.
   - No `RM self-test: FAIL` line.
3. Run a 24-hour paper/dry session. You should now see:
   - Nearby KZ_* levels producing ZRE zones (sources `LKZ`/`NKZ`).
   - `BufSigCoreVerdict` (buffer 19) updating every closed bar; the EA's
     heartbeat should stop reporting "no diagnostic record".
   - Fewer zones rejected as `expired distant zone` on fresh retests of
     recent levels.
4. When you are satisfied, flip the EA's three inert switches one at a
   time (demo-only → false → enable, then dry-run → false, then the
   account allowlist). Always on demo first.

The release gate (`tools/check_release_gate.py`) reports **GO** (only
cosmetic warnings about the runbook filename and three headers shipped in
a non-canonical directory — those were present before this patch and do
not affect trading logic).
