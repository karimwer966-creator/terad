# Confirmation-Score Engine — Phase 1 Audit

**Scope:** read-only audit of the repository as of 2026-11-25 on `arena/13d1250e-terad` (base `ea298c9`). No MQL5 production source, preset, risk setting, REAL authorization, buffer, public interface, or live-trading default is changed in Phase 1. The only tooling edit is the repository-root allowlist needed to ship this document.

## 0. Assumptions and ambiguities

1. The user says the indicator draws objects named `Z|BUY|<epoch>` / `Z|SELL|<epoch>`. The checked-in source does **not** agree: `Z|...` is the internal `SSvpZone.id` (`MQL5/Include/QSMC/QSMC_SvpZones.mqh:45`, `MQL5/Include/QSMC/QSMC_SvpZones.mqh:90`) and the **tooltip/setup field** (`MQL5/Include/QSMC/QSMC_SvpChart.mqh:1142-1148`), while chart object names are `QSVP_ZN_B0` / `QSVP_ZN_S0` (`MQL5/Include/QSMC/QSMC_SvpChart.mqh:91`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:248`, `docs/img/smcvp_engine_xauusd_20250708.svg:40-42`). Phase 2 must parse **both** forms and keep both backward compatible.
2. "01:15 chart time" and "18:30 chart time" are assumed to be **broker server chart time** because the user says broker server time differs. If they are Algeria local time instead, both are still outside the default `10..18` server filter under either plausible broker offset, but the exact UTC conversion changes.
3. Broker winter offset is ambiguous: configured `InpBrokerUTCOffsetWinterMinutes=120` means UTC+2 (`nadir2.mq5:858`), while the prior audit records an owner observation of UTC+1 (`docs/AUDIT_v6.6.24.md:252-275`). Both are carried below.
4. No runtime Experts log, trial CSV, exact `.set`, account type, broker symbol suffix, tick data, or AI-agent endpoint was supplied. Therefore "would have blocked" below is a **source-default judgement**, not proof of the actual runtime reason.
5. No AI-agent integration exists in the current zone/order path. The nearest external-data path is `KLJ_DataFeeder.mq5` + `QSMC_DataProvider.mqh`, which is a generic CSV/flat-JSON feeder, not an opinion service. It is not included by `nadir2.mq5` or `QSMC_Root.mqh` (`MQL5/Include/QSMC/QSMC_Root.mqh:33-46`; only `MQL5/Experts/KLJ_DataFeeder.mq5:69` includes it).
6. `Z|...` object names, tooltip text, and the new score engine are **not** currently read by `QSMC_AutoTrader.mq5`: there are no `ObjectGet*`, `ObjectFind`, `QSVP`, or `SVP_` references in that file. Its documented contract is a private `nadir2` CORE buffer stream (`MQL5/Experts/QSMC_AutoTrader.mq5:7-23`, `MQL5/Experts/QSMC_AutoTrader.mq5:152-173`, `MQL5/Experts/QSMC_AutoTrader.mq5:2299-2305`, `MQL5/Experts/QSMC_AutoTrader.mq5:4603-4625`).

---

## 1. Architecture map and data flow

### 1.1 Products and order boundaries

| Layer | Files | Role | Evidence |
|---|---|---|---|
| Canonical analytical host | `nadir2.mq5`, `MQL5/Indicators/nadir2.mq5` | 26 buffers / 603 inputs / 0 trade API; draws zones, publishes CORE buffers 7–12 and classification 19/21–25. | `nadir2.mq5:1935`, `nadir2.mq5:15348-15369`, `MQL5/Experts/QSMC_AutoTrader.mq5:152-173` |
| QSVP display/decision engine | `MQL5/Indicators/QSMC_SmcVpEngine.mq5`, `MQL5/Include/QSMC/QSMC_Svp*.mqh`, `QSMC_SignalRegistry.mqh`, `QSMC_SvpChart.mqh` | Separate 5-buffer indicator. Builds `SSvpZone`, scores BUY/SELL, draws `QSVP_ZN_*` boxes, updates a 64-slot registry. It does **not** trade. | `MQL5/Indicators/QSMC_SmcVpEngine.mq5:259-264`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:339-351`, `MQL5/Include/QSMC/QSMC_SvpZones.mqh:40-92`, `MQL5/Include/QSMC/QSMC_SignalRegistry.mqh:30`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:91` |
| QSMC production EA | `MQL5/Experts/QSMC_AutoTrader.mq5` | Only QSMC production order boundary. Reads private `nadir2` CORE buffers, applies account/risk/session gates, calls `g_trade.Buy/Sell`. | `MQL5/Experts/QSMC_AutoTrader.mq5:7-23`, `MQL5/Experts/QSMC_AutoTrader.mq5:2299-2305`, `MQL5/Experts/QSMC_AutoTrader.mq5:2938-2941`, `tools/check_release_gate.py:462-485` |
| QATS experimental EA | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` | Standalone SMC EA with its own zones, market/limit paths, guard codes. Not production-ready and not the QSVP object reader. | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:1-17`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:1735-1802`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3931-4120` |
| Generic external-data feeder | `MQL5/Experts/KLJ_DataFeeder.mq5`, `MQL5/Include/QSMC/QSMC_DataProvider.mqh` | WebRequest -> flat JSON/CSV -> common-folder CSV. No trading, no zone decision. | `MQL5/Experts/KLJ_DataFeeder.mq5:1-35`, `MQL5/Experts/KLJ_DataFeeder.mq5:69-81`, `MQL5/Experts/KLJ_DataFeeder.mq5:274-300`, `MQL5/Include/QSMC/QSMC_DataProvider.mqh:1-19` |

### 1.2 Zone creation -> display -> decision -> execution

1. `SVP_AddZone()` creates an `SSvpZone` with `direction`, `kind`, `lo/hi`, origin/availability bar, `state=SVP_ZS_DETECTED`, and `id="Z|BUY|..."` or `"Z|SELL|..."` (`MQL5/Include/QSMC/QSMC_SvpZones.mqh:78-92`).
2. `SVP_ZoneLifecycle()` mutates state to PARTIAL / MITIGATED / INVALIDATED / EXPIRED on touches (`MQL5/Include/QSMC/QSMC_SvpZones.mqh:147-175`); `SVP_ZoneAlive()` rejects only NONE / INVALIDATED / EXPIRED, so MITIGATED remains alive (`MQL5/Include/QSMC/QSMC_SvpZones.mqh:67-70`).
3. `SVP_PickZone()` selects a zone by direction, origin/availability timing and OB+FVG quality; it does **not** explicitly filter MITIGATED (`MQL5/Include/QSMC/QSMC_SvpDecision.mqh:236-251`).
4. `SVP_EvaluateSide()` runs ten steps including liquidity, sweep, displacement, BOS, zone alive, volume profile, retest/close-out, stop/target and RR. A zone retest must close back outside the zone with a same-direction candle; a touch alone is PENDING (`MQL5/Include/QSMC/QSMC_SvpDecision.mqh:335-401`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:490-499`).
5. `SVP_Resolve()` returns WAIT if both or neither side qualifies (`MQL5/Include/QSMC/QSMC_SvpDecision.mqh:510-517`); `plan_valid` requires a non-WAIT state (`MQL5/Include/QSMC/QSMC_SvpDecision.mqh:629`).
6. `QSMC_SmcVpEngine.mq5` writes decision/entry/stop/target/RR into five `DRAW_NONE` buffers once per closed M15 bar (`MQL5/Indicators/QSMC_SmcVpEngine.mq5:339-351`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:419-481`).
7. `QSMC_SvpChart.mqh` draws boxes named `QSVP_ZN_B<n>` / `QSVP_ZN_S<n>` and puts the zone text plus `Z|...` id into `OBJPROP_TOOLTIP` (`MQL5/Include/QSMC/QSMC_SvpChart.mqh:386-401`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:1142-1148`). The object manager claims/reuses/deletes these names every pass (`MQL5/Include/QSMC/QSMC_SvpChart.mqh:241-295`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:330-355`).
8. `QSMC_AutoTrader.mq5` does **not** consume steps 1–7. It creates `iCustom(_Symbol,_Period,"nadir2")` with no overridden inputs, copies CORE buffers 7–12 / 21–25, and only then calls `HandleSignal()` (`MQL5/Experts/QSMC_AutoTrader.mq5:4603-4625`, `MQL5/Experts/QSMC_AutoTrader.mq5:2289-2307`, `MQL5/Experts/QSMC_AutoTrader.mq5:3278-3401`).
9. `HandleSignal()` applies price/geometry/spread/account/session/risk/review gates and finally `g_trade.Buy/Sell` (`MQL5/Experts/QSMC_AutoTrader.mq5:2527-2941`). Order result/retcode/retry handling follows at `MQL5/Experts/QSMC_AutoTrader.mq5:3174-3221`.

**Consequence:** a visible QSVP zone can exist, change state, and even produce a SELL decision buffer while the production EA sees no CORE SELL at all. This is the central architectural mismatch.

### 1.3 Existing "AI-agent" / external-data integration

| Question | Finding | Evidence |
|---|---|---|
| What does it read? | Up to three configured HTTP sources; flat JSON or CSV; no endpoint/API key ships. | `MQL5/Experts/KLJ_DataFeeder.mq5:16-21`, `MQL5/Experts/KLJ_DataFeeder.mq5:71-90`, `MQL5/Experts/KLJ_DataFeeder.mq5:274-300` |
| What does it return? | `SDataPoint` rows: `series_id`, `as_of`, `value`, `prev`, `label`, `valid`; written as `QSMC\data_feed.csv`. It does **not** return `{direction, confidence, reasons, invalidation}`. | `MQL5/Include/QSMC/QSMC_DataProvider.mqh:34-42`, `MQL5/Include/QSMC/QSMC_DataProvider.mqh:58-60`, `MQL5/Experts/KLJ_DataFeeder.mq5:387-395` |
| How is it called? | Feeder `OnTimer()` -> `RefreshAll()` -> `WebRequest("GET", ..., InpTimeoutMs, ...)`; the provider class itself is read on `OnTimer`, never `OnCalculate`. | `MQL5/Experts/KLJ_DataFeeder.mq5:438-463`, `MQL5/Experts/KLJ_DataFeeder.mq5:505-521`, `MQL5/Include/QSMC/QSMC_DataProvider.mqh:177-180` |
| Timeout / retry | `InpTimeoutMs=8000`, `InpMaxRetries=3`, linear backoff `InpRetryBackoffSec=5`; non-200 or empty body increments failures and writes a status file. | `MQL5/Experts/KLJ_DataFeeder.mq5:74-77`, `MQL5/Experts/KLJ_DataFeeder.mq5:269-295`, `MQL5/Experts/KLJ_DataFeeder.mq5:415-431` |
| Failure handling | Provider status `QDP_NODATA` / `QDP_STALE` / `QDP_SCHEMA`; "NO DATA" is displayed and the value is excluded from scores. It never authorises or loosens an entry gate. | `MQL5/Include/QSMC/QSMC_DataProvider.mqh:25-30`, `MQL5/Include/QSMC/QSMC_DataProvider.mqh:12-18`, `MQL5/Include/QSMC/QSMC_DataProvider.mqh:264-286`, `MQL5/Include/QSMC/QSMC_DataProvider.mqh:324-345` |
| Is it connected to zones/orders? | No. `QSMC_DataProvider.mqh` is included only by `KLJ_DataFeeder.mq5`; `nadir2.mq5` and `QSMC_Root.mqh` do not include it. | `MQL5/Experts/KLJ_DataFeeder.mq5:69`, `MQL5/Include/QSMC/QSMC_Root.mqh:33-46` |

Phase 2 therefore must add a **new, optional, file-based opinion component** with a restricted JSON schema, a max-age timeout, and "score without it" failure handling. It must never be the sole authority.

---

## 2. Every gate that can block an entry

Legend: **S1** = Bearish OB+FVG `3547.06-3568.91`, born ~01:15 chart time, MITIGATED, aligned with H4 BOS down. **S2** = Bullish OB `3447.85-3464.37`, born ~18:30, VALIDATED, counter to H4 BOS down, no retest. "YES" means the default rule can block the described setup; "COND" means runtime state must be known.

| Gate | Default | `file:line` | S1 | S2 | Why |
|---|---|---|---|---|---|
| Master switch | `InpEnableTrading=true` QSMC / QATS | `MQL5/Experts/QSMC_AutoTrader.mq5:268`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:159`, `MQL5/Experts/QSMC_AutoTrader.mq5:2854-2858` | COND | COND | YES only if a safe preset or operator set false (`presets/QSMC_AutoTrader_DIAG_XAUUSD_M15.set:8`, `presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set:35`). |
| Dry-run | `false` QSMC / QATS | `MQL5/Experts/QSMC_AutoTrader.mq5:269`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:160`, `MQL5/Experts/QSMC_AutoTrader.mq5:2860-2875` | COND | COND | YES only if dry-run preset loaded (`presets/QSMC_AutoTrader_DIAG_XAUUSD_M15.set:9`). |
| REAL authorization | `InpAllowRealTrading=false`, empty login/server | `MQL5/Experts/QSMC_AutoTrader.mq5:275-300`, `MQL5/Experts/QSMC_AutoTrader.mq5:1240-1267`, `MQL5/Experts/QSMC_AutoTrader.mq5:2877-2884`, `MQL5/Experts/QSMC_AutoTrader.mq5:2921-2928` | COND | COND | YES on REAL; NO on DEMO. |
| Permissions / identity | terminal/EA/account/symbol flags; identity drift latch | `MQL5/Experts/QSMC_AutoTrader.mq5:1144-1155`, `MQL5/Experts/QSMC_AutoTrader.mq5:1162-1188`, `MQL5/Experts/QSMC_AutoTrader.mq5:1240-1267` | COND | COND | Unknown without runtime log. |
| Session (EA) | `10..18` server, half-open `[10,18)` | `MQL5/Experts/QSMC_AutoTrader.mq5:393-394`, `MQL5/Experts/QSMC_AutoTrader.mq5:1998-2011`, `MQL5/Include/QSMC/QSMC_ExecutionRules.mqh:139-144`, `MQL5/Experts/QSMC_AutoTrader.mq5:2732-2735` | **YES** | **YES** | 01:15 and 18:30 server are outside the default window; even if the zone was retested later, the CORE signal may have aged out. |
| Session (QATS) | `0/0` = off | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:190-191`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3015-3025` | NO | NO | QATS default has no session veto. |
| Session (sniper zone creation) | `InpSniperSessionFilter=true`; London `10..13`, NY `13..17` on raw `bar_time`, Asia only if strength >= 0.90 | `nadir2.mq5:1944`, `nadir2.mq5:44426-44437`, `nadir2.mq5:44595` | **YES** | **YES** | Born 01:15 is Asia/off-peak; 18:30 is after NY. The function treats server datetime as GMT, which is wrong when broker offset is not zero. |
| HTF / trend veto | `InpUseHTFBias=true`, `InpTopDownGateCore=true`, H4 bias, 3 confluences, RR >= 2.0 | `nadir2.mq5:1282-1300`, `nadir2.mq5:1464-1476`, `nadir2.mq5:21055-21059`, `nadir2.mq5:21069-21077` | NO | **YES** | S1 is aligned with H4 BOS down; S2 is counter to it and is hard-vetoed before publication. |
| Premium/discount veto (QATS) | `InpPDEnforceMarket=true`, `InpLimitNeedPD=true` | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:226`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:236`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3733-3914` | COND | **YES** | S2 counter-H4 is likely not in discount/premium alignment; S1 may be. |
| State | `SVP_ZS_*`; `SVP_ZoneAlive()` rejects NONE/INVALIDATED/EXPIRED, accepts MITIGATED | `MQL5/Include/QSMC/QSMC_SvpCore.mqh:52-60`, `MQL5/Include/QSMC/QSMC_SvpZones.mqh:67-70`, `MQL5/Include/QSMC/QSMC_SvpZones.mqh:147-175` | NO | NO | MITIGATED is not rejected outright by QSVP; **but** the user-visible state is not consumed by AutoTrader at all. |
| Retest-only / confirmation candle | Touch + close back outside zone; no touch => PENDING | `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:367-401`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:490-499`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:512-517` | **YES** | **YES** | S1 is MITIGATED (already touched) but needs second reaction/CHoCH; S2 explicitly had no retest. |
| Age / signal expiry | `InpMaxSignalAgeBars=1`, `InpRetestTimeoutBars=40`; expired setup rejected in classification | `MQL5/Experts/QSMC_AutoTrader.mq5:366`, `MQL5/Experts/QSMC_AutoTrader.mq5:3281-3327`, `nadir2.mq5:1391`, `nadir2.mq5:19915-19919`, `nadir2.mq5:21063-21064` | **YES** | **YES** | A zone born at 01:15 or 18:30 cannot be traded hours later on the same CORE identity. |
| News | `InpSniperNewsFilter=true`; ±30 min high-impact; disabled in backtest. QATS opt-in `false`. | `nadir2.mq5:1945`, `nadir2.mq5:6368-6372`, `nadir2.mq5:44440-44460`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:252`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3027-3033` | COND | COND | Unknown calendar; not a deterministic cause from source alone. |
| Score / class | STRONG-only by default: score 75, reliability 80, RR1 1.5; `InpAllowWeakSignals=false`, `InpAllowModerateSignals=false`; QATS `InpMinScore=55` | `nadir2.mq5:1127`, `nadir2.mq5:1133`, `nadir2.mq5:1985-1999`, `nadir2.mq5:19857-19895`, `nadir2.mq5:19903-19967`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:205` | **YES** | **YES** | Sweep + zone alone is not a STRONG CORE signal; S2 also loses trend confluence. |
| Spread | QSMC 60 pts / 0.10 of stop; QATS 50 pts / 0.20; `QER_SpreadOk()` truncates and lacks finite validation | `MQL5/Experts/QSMC_AutoTrader.mq5:344`, `MQL5/Experts/QSMC_AutoTrader.mq5:349`, `MQL5/Experts/QSMC_AutoTrader.mq5:1024-1031`, `MQL5/Experts/QSMC_AutoTrader.mq5:2661-2665`, `MQL5/Experts/QSMC_AutoTrader.mq5:2761-2773`, `MQL5/Include/QSMC/QSMC_ExecutionRules.mqh:171-185`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:186-187` | COND | COND | Only during a spread spike; the reproduced bug tends to **admit** bad spreads, not block good ones. |
| ATR / volatility | `InpMaxStopATR=4.0`, `InpTopDownChaseATR=1.5`, H1 ADX >= 20, chop/trend 18/25 | `nadir2.mq5:1297`, `nadir2.mq5:1308-1309`, `nadir2.mq5:1475`, `nadir2.mq5:1943`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:393-397` | COND | COND | Unknown ATR/ADX; a wide `3547–3569` zone can fail chase/stop-ATR limits. |
| Max trades / day | 3 QSMC / 4 QATS | `MQL5/Experts/QSMC_AutoTrader.mq5:395`, `MQL5/Experts/QSMC_AutoTrader.mq5:2737-2744`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:176`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3011-3013` | COND | COND | Unknown today's earlier entries. |
| Daily loss / DD / loss streak | 0.50% / 3% / 2 losses QSMC; 2% / 8% / 3 losses QATS | `MQL5/Experts/QSMC_AutoTrader.mq5:356-363`, `MQL5/Experts/QSMC_AutoTrader.mq5:2680-2700`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:177-181`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3002-3010` | COND | COND | Persisted breakers unknown. |
| Cooldown | 60 min after loss | `MQL5/Experts/QSMC_AutoTrader.mq5:396`, `MQL5/Experts/QSMC_AutoTrader.mq5:2745-2749`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:181` | COND | COND | Unknown. |
| Stale feed / disconnected | 30 s QSMC, 60 s QATS; `SymbolInfoTick()` failure skipped in QSMC | `MQL5/Experts/QSMC_AutoTrader.mq5:365`, `MQL5/Experts/QSMC_AutoTrader.mq5:2706-2730`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:192`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3034-3041` | COND | COND | Unknown. |
| Stops / freeze / RR / size | min 20 pts, max 5000 pts, RR at fill 1.20, broker stops level, lots > 0, measurable risk | `MQL5/Experts/QSMC_AutoTrader.mq5:371-379`, `MQL5/Experts/QSMC_AutoTrader.mq5:1002-1009`, `MQL5/Experts/QSMC_AutoTrader.mq5:2567-2657`, `MQL5/Experts/QSMC_AutoTrader.mq5:2775-2833` | COND | COND | A plan priced at a zone edge can fail RR at the later market fill. |
| Owner lane / duplicates | `InpOwnExecutionLane=true`; ring + terminal GV; `MarkSeen()` on many refusals | `MQL5/Experts/QSMC_AutoTrader.mq5:419`, `MQL5/Experts/QSMC_AutoTrader.mq5:845-905`, `MQL5/Experts/QSMC_AutoTrader.mq5:2174-2209`, `MQL5/Experts/QSMC_AutoTrader.mq5:3329`, `MQL5/Experts/QSMC_AutoTrader.mq5:3395`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:2502-2528` | **YES** | **YES** | One earlier dry-run/refusal/other EA claim can burn the bar identity before the London/NY retest. |
| Rejection logging | `InpVerbose=false`; one `g_last_note` throttle; selective CSV rows; GateAudit every 25 bars with keyed counters | `MQL5/Experts/QSMC_AutoTrader.mq5:402`, `MQL5/Experts/QSMC_AutoTrader.mq5:907-955`, `MQL5/Experts/QSMC_AutoTrader.mq5:3374-3379`, `nadir2.mq5:1333`, `nadir2.mq5:16608-16621`, `nadir2.mq5:19614-19633` | **YES** | **YES** | Not a trading veto, but it is why the exact runtime blocker cannot be proven today. |

---

## 3. Time handling

| Clock | Source | Evidence | Problem |
|---|---|---|---|
| EA session | `TimeCurrent()` server hour, `QER_SessionInside(h,10,18)` | `MQL5/Experts/QSMC_AutoTrader.mq5:1998-2011`, `MQL5/Include/QSMC/QSMC_ExecutionRules.mqh:139-144` | Hard server-hour filter; no UTC/Algeria conversion. |
| QATS session | `TimeTradeServer()`; default off | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3015-3025` | Different clock from QSMC EA. |
| Indicator session scoring | `SessionLocalTime()` uses `ServerToUTC()` and EU/US DST rules | `nadir2.mq5:858-860`, `nadir2.mq5:24417-24449`, `nadir2.mq5:24463-24486` | Correctly DST-aware for local market sessions, but separate from the EA hard filter. |
| Sniper session gate | raw `bar_time` compared to `10..13` / `13..17` as if GMT | `nadir2.mq5:44426-44437`, `nadir2.mq5:44595` | Wrong whenever broker server != UTC; likely blocks 01:15 and 18:30 server-born zones. |
| Algeria local | fixed UTC+1, no DST | `nadir2.mq5:10028-10030` | Used in PMI banner, not in the EA entry filter. |
| PMI banner | fixed, non-DST | `docs/AUDIT_v6.6.24.md:263-275` | Already flagged as disagreeing with DST-aware indicator reality. |

### Exact allowed windows on 2026-11-25 (winter, EU DST off)

`QER_SessionInside(10,18)` is half-open: server `10:00:00–17:59:59`.

| Broker offset | UTC allowed | Algeria (UTC+1) allowed | London 09:00–12:00 Algeria | NY 15:30–19:00 Algeria |
|---|---|---|---|---|
| Configured UTC+2 (`nadir2.mq5:858`) | 08:00:00–15:59:59 | **09:00:00–16:59:59** | 09:00–11:59:59 allowed; **12:00 excluded** | 15:30–16:59:59 allowed; **17:00–19:00 blocked** |
| Owner-observed UTC+1 (`docs/AUDIT_v6.6.24.md:252-275`) | 09:00:00–16:59:59 | **10:00:00–17:59:59** | 09:00–09:59:59 blocked; 10:00–11:59:59 allowed; **12:00 excluded** | 15:30–17:59:59 allowed; **18:00–19:00 blocked** |

Phase 2 must use **one UTC-based clock**: `TimeCurrent()` -> configurable broker offset -> UTC -> session/score; Algeria and London/NY local labels are derived from UTC, never from three independent clocks. DST edges must be unit-tested.

---

## 4. BUY/SELL asymmetry, Bid/Ask, SL/TP and parsing fragility

| Finding | Evidence | Assessment |
|---|---|---|
| QSMC AutoTrader chooses ask for BUY, bid for SELL. | `MQL5/Experts/QSMC_AutoTrader.mq5:2532-2535` | Correct. |
| BUY geometry `sl<entry<tp`, SELL geometry `tp<entry<sl`; current-price and RR-at-fill checks are symmetric. | `MQL5/Experts/QSMC_AutoTrader.mq5:2581-2594`, `MQL5/Experts/QSMC_AutoTrader.mq5:2611-2638`, `MQL5/Experts/QSMC_AutoTrader.mq5:2646-2657` | No inverted sign bug found. |
| `g_trade.Buy/Sell` are symmetric. | `MQL5/Experts/QSMC_AutoTrader.mq5:2938-2941` | Correct. |
| QATS evaluates both directions through one `EvaluateSide()`, resolves direction symmetrically, and validates both sides' stops. | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:2621-2624`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:2008-2027`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:1937-1946` | No obvious BUY/SELL copy-paste inversion. |
| QATS `BuildTradePlan()` uses ask for BUY / bid for SELL and adds one spread above the swing high for SELL stops. | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:2665-2705` | Correct and explicitly spread-aware. |
| `QER_SpreadOk()` casts `double` spread to `int` and lacks finite/nonnegative validation; 20.9/20, 60.9/60, NaN and -5 can be mishandled. | `MQL5/Include/QSMC/QSMC_ExecutionRules.mqh:171-185`, `MQL5/Experts/QSMC_AutoTrader.mq5:2452-2464` | Real defect; affects both directions but is not a SELL-only veto. **Fixed v6.6.25 (AUD-04):** compared as a double, non-finite/negative fail closed, cap 0 disables. |
| `SpreadOK()` uses `SYMBOL_ASK-SYMBOL_BID` without `MathIsValidNumber`; `SymbolInfoTick()` failure is skipped. | `MQL5/Experts/QSMC_AutoTrader.mq5:1024-1031`, `MQL5/Experts/QSMC_AutoTrader.mq5:2706-2720` | Fail-open data-quality gaps. |
| `RunEntryReview()` returns `""` when `InpPrintEntryReview=false`, so the 12-check final review can be bypassed. | `MQL5/Experts/QSMC_AutoTrader.mq5:420`, `MQL5/Experts/QSMC_AutoTrader.mq5:2411-2522`, `MQL5/Experts/QSMC_AutoTrader.mq5:2908-2915` | A print input must not change safety semantics. **Fixed v6.6.25 (AUD-03):** the review always runs; the switch now guards only the Journal lines. |
| QATS `PlaceLimitOrder()` starts `onServer=true` for a nonzero ticket, so "no pending order found" is unreachable. | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:4078-4097`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:4104-4106` | Verification/logging defect, not a direction sign error. |
| Object names are `QSVP_ZN_B0/S0`, not `Z|BUY|...`; `Z|...` lives in tooltip/setup field. | `MQL5/Include/QSMC/QSMC_SvpZones.mqh:45`, `MQL5/Include/QSMC/QSMC_SvpZones.mqh:90`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:91`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:248`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:1142-1148` | User-described contract is not implemented as object names. |
| Tooltip is built by concatenating free text, price strings, state text, "area ...", and id; objects are renumbered/deleted every pass. | `MQL5/Include/QSMC/QSMC_SvpChart.mqh:1143-1148`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:241-295`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:330-355` | Scattered `StringFind` parsing would be fragile. Phase 2 needs one `ZoneParser` with fixtures for both legacy and current formats. |
| No production EA reads `OBJPROP_TOOLTIP` or `Z|...`. | `MQL5/Experts/QSMC_AutoTrader.mq5:17-23`, `MQL5/Experts/QSMC_AutoTrader.mq5:152-173`, `MQL5/Experts/QSMC_AutoTrader.mq5:2299-2305` | The visible zone is not the execution input. |

---

## 5. Execution risks

| Risk | Evidence | Notes |
|---|---|---|
| Stops/freeze distance | `MQL5/Experts/QSMC_AutoTrader.mq5:1002-1009`, `MQL5/Experts/QSMC_AutoTrader.mq5:1015-1022`, `MQL5/Experts/QSMC_AutoTrader.mq5:2775-2779` | Checks `MathAbs(price-sl)` and `MathAbs(tp-price)` against broker minimum; should remain in any future executor. |
| Filling mode | `MQL5/Experts/QSMC_AutoTrader.mq5:4558-4564`; QATS limit fallback `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:4043-4074` | QSMC picks FOK -> IOC -> RETURN; QATS retries RETURN/IOC/FOK on invalid fill. |
| Retcode / retries | `MQL5/Experts/QSMC_AutoTrader.mq5:866`, `MQL5/Experts/QSMC_AutoTrader.mq5:2938-2961`, `MQL5/Experts/QSMC_AutoTrader.mq5:3174-3221`; QATS `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3317-3369` | Transient/permanent classification exists; QATS has no transient retry for XAUUSD/REAL at `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:3350-3354`. |
| Pending-order verification | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:4078-4097` | `onServer` bug hides a missing limit order. |
| Duplicate protection that burns zones | `MQL5/Experts/QSMC_AutoTrader.mq5:845-905`, `MQL5/Experts/QSMC_AutoTrader.mq5:2854-2858`, `MQL5/Experts/QSMC_AutoTrader.mq5:2860-2875`, `MQL5/Experts/QSMC_AutoTrader.mq5:2880-2883`, `MQL5/Experts/QSMC_AutoTrader.mq5:2922-2928`, `MQL5/Experts/QSMC_AutoTrader.mq5:3329`, `MQL5/Experts/QSMC_AutoTrader.mq5:3384-3390`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:2502-2528` | `MarkSeen()` on INERT/dry-run/class/env/pre-submit means a later valid retest of the same bar is ignored. Zone state and order identity must be separated. |
| Unprotected / repair paths | `MQL5/Experts/QSMC_AutoTrader.mq5:3010-3013`, `MQL5/Experts/QSMC_AutoTrader.mq5:3066-3088`, `MQL5/Experts/QSMC_AutoTrader.mq5:3111-3130` | Any new engine must never widen SL, average down, grid, or martingale. |
| Limit expiry / setup persistence | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:4098-4103`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:222-223` | Pending limit does not consume setup identity until fill; this is the right pattern for a zone registry. |

---

## 6. Code quality

| Topic | Finding | Evidence |
|---|---|---|
| OOP boundaries | QSVP is split into pure-ish headers but still depends on large file-scope globals (`g_svp`, `g_qsr`, `g_svc`). `QSMC_SignalRegistry.mqh` is explicitly pure/bounded; `QSMC_SvpChart.mqh` owns terminal object side effects. | `MQL5/Include/QSMC/QSMC_SignalRegistry.mqh:23-30`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:90-107`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:625-629` |
| Data structures | Fixed capacities: `QSR_CAPACITY=64`, `SVP_ZONE_MAX=160`, `SVC_MAX_OBJECTS=320`; linear scans and sorted insertion. | `MQL5/Include/QSMC/QSMC_SignalRegistry.mqh:30`, `MQL5/Include/QSMC/QSMC_SvpZones.mqh:27`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:36-37`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:881-909` |
| OnTick cost | QSMC AutoTrader calls `ProcessSignals()` on every tick and every 2 s timer; QSVP `SVE_Step()` guards on one closed M15 bar and kills its timer after start. | `MQL5/Experts/QSMC_AutoTrader.mq5:401`, `MQL5/Experts/QSMC_AutoTrader.mq5:5119-5150`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:419-453`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:484-488` |
| Rate copying | `SVP_Analyze()` copies 1500 M15 / 600 H1 / 300 H4 rates per pass. | `MQL5/Indicators/QSMC_SmcVpEngine.mq5:113-115`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:375-379` |
| Global state / persistence | Seen keys and owner lane use terminal global variables; breakers persist; QSVP registry is in-memory and rebuilt at start-up with backfill. | `MQL5/Experts/QSMC_AutoTrader.mq5:845-905`, `MQL5/Experts/QSMC_AutoTrader.mq5:2174-2209`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:388-402`, `MQL5/Include/QSMC/QSMC_SignalRegistry.mqh:56-64` |
| Repainting | Decisions are closed-bar based; `InpUpdateEveryTick=true` but `InpRealTimeZones=true` is inert and `InpRealTimeFractal=true` draws provisional markers only. | `nadir2.mq5:1335-1337`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:421-453`, `MQL5/Indicators/QSMC_SmcVpEngine.mq5:455-481` |
| Observability | QSMC refusals are throttled prose; QATS has structured `BLOCK/REJECTED` codes; indicator GateAudit is every 25 bars with keyed counters, not per-zone values. | `MQL5/Experts/QSMC_AutoTrader.mq5:907-955`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:2974-2981`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:4860-4886`, `nadir2.mq5:16608-16621`, `nadir2.mq5:19614-19633` |

---

## 7. Ranked root causes for the two missed setups

Ranking is by source-default likelihood, not runtime proof. No logs were supplied.

| Rank | Root cause | S1 Bearish MITIGATED | S2 Bullish VALIDATED | Evidence |
|---|---|---|---|---|
| 1 | **Architecture mismatch:** visible QSVP zone / `Z|...` id is not the QSMC AutoTrader CORE buffer input. | Dominant. | Dominant. | `MQL5/Experts/QSMC_AutoTrader.mq5:17-23`, `MQL5/Experts/QSMC_AutoTrader.mq5:2299-2305`, `MQL5/Experts/QSMC_AutoTrader.mq5:4603-4625`, `MQL5/Include/QSMC/QSMC_SvpChart.mqh:1142-1148` |
| 2 | **Rigid HTF trend veto** before publication. | Not blocking; aligned with H4 BOS down. | Blocking; counter to H4 BOS down. | `nadir2.mq5:1283`, `nadir2.mq5:1287`, `nadir2.mq5:21055-21077`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:236` |
| 3 | **Session filter / wrong clock**, applied as a hard creation or entry veto. | 01:15 server-born zone is Asia/off-peak; later NY portion can be outside 10..18. | 18:30 is outside 10..18 server and after NY sniper window. | `MQL5/Experts/QSMC_AutoTrader.mq5:393-394`, `MQL5/Experts/QSMC_AutoTrader.mq5:1998-2011`, `MQL5/Experts/QSMC_AutoTrader.mq5:2732-2735`, `nadir2.mq5:44426-44437`, `docs/AUDIT_v6.6.24.md:268-275` |
| 4 | **One-bar CORE age + duplicate/owner marking.** | A 01:15 CORE identity cannot survive to London/NY retest. | Same. | `MQL5/Experts/QSMC_AutoTrader.mq5:366`, `MQL5/Experts/QSMC_AutoTrader.mq5:3281-3327`, `MQL5/Experts/QSMC_AutoTrader.mq5:845-905`, `MQL5/Experts/QSMC_AutoTrader.mq5:3395` |
| 5 | **Retest-only / confirmation-candle requirement.** | MITIGATED needs second reaction/CHoCH; no evidence it occurred. | Explicitly no retest. | `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:367-401`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:490-499`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:512-517` |
| 6 | **STRONG-only class / causality / score floors.** | Sweep + zone + MITIGATED is not enough without complete causal chain and score >=75 / rel >=80 / RR >=1.5. | Same, plus trend penalty. | `nadir2.mq5:1127`, `nadir2.mq5:1133`, `nadir2.mq5:1985-1999`, `nadir2.mq5:19903-19967`, `nadir2.mq5:21043-21084` |
| 7 | **MITIGATED treated as inferior/terminal by operator expectation, even though `SVP_ZoneAlive()` accepts it; no second-reaction path.** | Direct. | Not applicable (VALIDATED). | `MQL5/Include/QSMC/QSMC_SvpZones.mqh:67-70`, `MQL5/Include/QSMC/QSMC_SvpZones.mqh:147-175`, `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:236-251` |
| 8 | **No structured rejection log**, so the exact blocker is unrecoverable. | Direct diagnostic gap. | Direct diagnostic gap. | `MQL5/Experts/QSMC_AutoTrader.mq5:402`, `MQL5/Experts/QSMC_AutoTrader.mq5:907-955`, `MQL5/Experts/QSMC_AutoTrader.mq5:3374-3379`, `nadir2.mq5:16608-16621` |
| 9 | Runtime guards (master/dry-run/REAL/preset, max trades, breakers, cooldown, spread, news, stops, size). | Possible but unproven. | Possible but unproven. | §2 table above |
| 10 | Direction-specific sign / Bid-Ask bug. | **Ruled out by source inspection.** | **Ruled out by source inspection.** | `MQL5/Experts/QSMC_AutoTrader.mq5:2532-2535`, `MQL5/Experts/QSMC_AutoTrader.mq5:2581-2657`, `MQL5/Experts/QSMC_AutoTrader.mq5:2938-2941`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:1937-1946`, `MQL5/Experts/QuantumAutonomousTradingSystem.mq5:2621-2624` |

**Conclusion:** a confirmation-score engine must be a new zone-centric layer, not a relaxation of the existing CORE buffer path. It must own zone identity/state across sessions, score independent evidence, log every component, and only then hand a reviewed plan to an explicitly disarmed executor. It must not silently change `QSMC_AutoTrader.mq5` risk or REAL authorization.
