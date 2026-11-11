# PRODUCTION AUDIT & DEPLOYMENT REPORT
## QuantumAutonomousTradingSystem (QATS) — 2026-11-09

Branch: `arena/f83fc236-terad` · Pre-cleanup recovery point: `439420d588d5ac3bbe64bf7ca2260e230abd2d95` (main tip)
Consolidation commit: `8ae2156` · Result: **one standalone EA source, zero presets, zero custom indicators**

Statuses used (as mandated): `PASS` = verified in this environment · `FAIL` = verified broken ·
`BLOCKED` = cannot be verified here, with the exact blocker named · `NOT TESTED` = no claim made either way.
**Nothing in this report marks an untested feature as PASS.**

> **Superseded in part by v1.20 (2026-11-11).** The statement in section 7 that "both directions are fully
> symmetric" did not survive execution: v1.11 chose its direction before scoring and scored one side only, and a
> price-mirrored replay did not mirror its trades. The signal engine, the weights, the trade plan and the loss
> accounting described here were replaced. Current state, evidence and verdict:
> [`QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md`](QATS_DUAL_DIRECTION_AUDIT_2026-11-11.md).
> The repository-consolidation record below is unchanged.

---

## 1. Original repository architecture (as found at commit `439420d`)

```
terad/
├── nadir2.mq5                      # 44,207-line monolithic indicator (ALSO duplicated at root:
│                                   #   md5-identical to MQL5/Indicators/nadir2.mq5)
├── MQL5/
│   ├── Experts/QSMC_AutoTrader.mq5 # 3,545-line execution EA (reads nadir2's published buffers)
│   ├── Experts/KLJ_DataFeeder.mq5  # 524-line WebRequest data feeder (never trades)
│   ├── Indicators/nadir2.mq5       # deployed copy of the monolith
│   ├── Indicators/QSMC_ScannerProbe.mq5
│   ├── Include/QSMC/*.mqh          # 23 QSMC modules (dashboard, arbitration, selftest, stats, …)
│   └── Scripts/QSMC_ArbiterTest.mq5, QSMC_ResetGuards.mq5
├── presets/*.set                   # 16 preset files (.set)
├── tools/*.py, *.json              # ~77 QSMC-specific harness scripts and tests
├── docs/ (60 QSMC docs) + docs/incident-20261101/ (113-file incident audit record)
├── .github/workflows/{liquidity-value,qsmc-production,qsmc-verify}.yml
└── README/INSTALL_AR/QSMC_v6.6.15_*.md / root reports
```

Architecture in one sentence: **a 44k-line indicator published signal buffers (7–12, 19–20); a 3.5k-line
companion EA consumed them through iCustom; 23 include modules rendered a dashboard; nothing executed
a trade unless a human stacked all three on one chart.**

## 2. Problems discovered (audit)

1. **44,207-line indicator, duplicated verbatim** at the repo root and under `MQL5/Indicators/`
   (md5 `202d9b1ff128f573e12cb02184412673` both). The EA could only see signals when the indicator
   was compiled, loaded with `InpExportSignalBuffers=true`, on the SAME symbol/timeframe as the EA,
   with defaults matching the EA's expectations — a six-leg deployment contract enforced by a Python
   contract test, not by the platform.
2. **Multi-artifact deployment**: 1 EA + 1 indicator + 23 include files + 16 `.set` presets, with
   documented "one expert per chart" constraints and a companion data feeder for external inputs.
3. **Six configuration presets for XAUUSD alone** (0.05–0.10 lot, 100/200/300-pip ladders) hard-wiring
   a $700–$5,000 trial narrative into the repo; the brief bans fixed-balance assumptions outright.
4. **Astronaut architecture**: signal arbiter registries, unified-decision tables, fingerprints,
   "gauntlet" gates, wfa harnesses, against an execution path that had **never been demo-verified**
   (per repo's own docs/demo_readiness_audit_v6.6.16.md and tools/fixtures/no_trades_2026-11-09.log).
5. **Demo-readiness was explicitly NOT met** by the old system at HEAD: its own docs record zero
   executed trades, "silence is the failure mode you will actually meet", and an "armed by default"
   flag that only armed a *demo chart after a human attached everything correctly*.
6. Duplicated trilingual documentation (EN/AR), contradictory "production ready" vs
   "MetaEditor compile still required" notices scattered across docs.
7. Dead pathways: scanner probe indicator, arbiter test script, WFA (walk-forward) harness that
   trained nothing, `KLJ_DataFeeder` for external data the strategy never used.
8. Tooling coupled to source line numbers (`test_*.py` regex-asserts against nadir2/QSMC sources) —
   any consolidation broke ~77 of them by construction.

## 3. Files removed (168 files, all reversible via Git history)

| Category | Count | Files |
|---|---|---|
| Monolith indicator (duplicated copies) | 2 | `nadir2.mq5` (root), `MQL5/Indicators/nadir2.mq5` (88,414 lines combined) |
| QSMC include modules | 23 | `MQL5/Include/QSMC/*.mqh` (Structure, Bias, Gates, Zones, Scanners, Arbiter, Selftest, Stats, …) |
| Superseded EAs | 2 | `QSMC_AutoTrader.mq5` (3,545 lines), `KLJ_DataFeeder.mq5` (524 lines) |
| Superseded indicator probe | 1 | `MQL5/Indicators/QSMC_ScannerProbe.mq5` |
| Scripts | 2 | `QSMC_ArbiterTest.mq5`, `QSMC_ResetGuards.mq5` |
| Preset files (.set) | 16 | entire `presets/` directory |
| QSMC Python tooling | 69 | `tools/*` (static_check, release gates, 70 tests, WFA harness, fingerprints…) |
| Superseded documentation | 46 | all QSMC docs/, root QSMC_v6.6.15 reports, INSTALL_AR.md, phase diffs, Arabic setup guides |
| Old CI workflows | 3 | `liquidity-value.yml`, `qsmc-production.yml`, `qsmc-verify.yml` |
| Root | 4 | `INSTALL_AR.md` + 3 QSMC_v6.6.15 reports |

Kept deliberately: `docs/incident-20261101/**` (113 files — incident audit
record; per brief, audit records are not deleted), `.gitignore`, `.gitattributes`,
recovery tag `recovery/pre-quantum-cleanup-2026-11-09` at `439420d`.

**No sensitive data existed in the removed files** (no credentials; `.set` numbers were account-size
trial plans, not account numbers).

## 4. Files merged / consolidated

| Source (deleted) | Functionality | Where it went |
|---|---|---|
| nadir2.mq5 + QSMC Structure/Bias/LiquidityValue/Zones/Reaction/Scanners logic | SMC detection (swings, BOS/MSS, liquidity pools, sweeps, displacement, OB/FVG, premium/discount) | Re-implemented, closed-bar only, in §11–§15 of the EA |
| QSMC_AutoTrader.mq5 | DEMO-only guard, CTrade execution, retcode classification, persisted day-loss breaker, cooldown, heartbeat, dry-run | Re-implemented and hardened in §9/§18–§25 of the EA (AND'ed with per-decision permission re-verification) |
| nadir2 dashboard / QSMC_Renderer | Chart panel | Minimal `Comment()` panel + journal heartbeat |
| tools/test_diag_bridge.py (GV diag protocol) | Cross-file diag tables | Removed — no longer needed with a single binary |
| 16 presets | Configuration | **Deleted by mandate.** Only code-defaults + inputs remain; broker specs are read live |

Net result: **173 files changed, +2,149 / −144,991 lines.**

## 5. Files retained (unchanged/trimmed)

- `docs/incident-20261101/**` — incident audit record (retained verbatim, 113 files).
- `.gitignore`, `.gitattributes` (comment modernised), `.github/workflows/quantum-verify.yml` (new).
- `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` (new, 1,809 lines, 74,568 bytes).

## 6. Final project architecture

```
terad/
├── MQL5/Experts/QuantumAutonomousTradingSystem.mq5   # THE deployment file (1,809 lines)
├── tools/verify_quantum_ea.py                        # offline structural verifier (not a compiler)
├── README.md                                         # build + attach + verify instructions
├── docs/PRODUCTION_AUDIT_2026-11-09_QUANTUM_EA.md    # this report
├── docs/incident-20261101/                           # preserved incident audit record
└── .github/workflows/quantum-verify.yml              # CI: structural verification
```

Deployment footprint: **copy one file to `MQL5\Experts\`, press F7.**

## 7. Trading engine architecture (as built, not as promised)

Single-pass pipeline, evaluated once per **new closed M5 bar** (decisions use shift ≥ 1 only —
no forming candles, no look-ahead):

1. **D1 bias** — EMA20 vs EMA50 (close vs both).
2. **H4 context** — same construction; used for alignment veto and scoring.
3. **H1 structure** — confirmed fractal swings (k=2); BOS/MSS = closed H1 close beyond the most
   recent confirmed swing high/low.
4. **Liquidity mapping** — prior day high/low, prior week high/low, equal highs/lows
   (tolerance = `InpLiquidityToleranceATR` × ATR(H1)).
5. **Liquidity sweep** — a closed H1 bar that pierced a level and closed back inside (±4 bars).
6. **Displacement** — body ≥ `InpDisplaceATR` × ATR(H1), or body/range ≥ 0.65 with range ≥ 1.3 × ATR.
7. **MSS / BOS binding** — impulse bar ← sweep bar ← displacement; used to anchor zones.
8. **Order block / FVG** — last opposite candle before the impulse (OB); 3-candle imbalance (FVG).
9. **Premium / Discount** — dealing range (last `InpSwingLookback` H1 bars); longs favoured in
   discount, shorts in premium.
10. **M15 confirmation** — closed M15 candle in direction (vs its own open and EMA20).
11. **M5 entry trigger** — closed-bar engulfing / pin bar / strong-body marubozu.
12. **Confluence score 0–100** — D1 align 20, H4 align 15, H1 structure 20/10, sweep 15,
    displacement 10, zone touch (or presence) 10/5, P/D location 5, volume 5, M15 5, M5 5.
    Trade requires score ≥ `InpMinScore` (65) **and** no hard veto (D1 and H4 both opposed, or
    counter-D1 when `InpAllowCounterBias=false`).
13. **Risk validation → execution → management** — see §8.

Both directions are fully symmetric (bull and bear legs are separate code paths, no shared sign
hacks). Every EA decision is logged as `[QATS][SKIP ...]` / `[QATS][ORDER] ...` with the full
confluence vector (`D1=%+d H4=%+d H1=%+d sweep=... P/D=...`) so silence is always explained.

## 8. Risk management implementation (verified by code review + verifier; runtime NOT TESTED)

- **Per-trade risk**: `Risk = Equity × EffectiveRiskPercent()`, default 0.50%, input ceiling
  `InpMaxRiskPercent` (1.00%), code hard cap 2.00% — see `EffectiveRiskPercent()`.
- **Sizing**: `Volume = RiskMoney / ((StopDist / TickSize) × TickValue)` — broker-provided
  tick economics, **never a fixed balance and never a hardcoded contract size**. Volume is
  floored to `SYMBOL_VOLUME_STEP`, clamped to `SYMBOL_VOLUME_MIN/MAX` and `SYMBOL_VOLUME_LIMIT`,
  shrunk step-by-step to fit `InpMaxMarginUse` × free margin (via `OrderCalcMargin`), else refused.
- **Stops**: structure-based (last 3 M5 bars extreme) vs ATR-based (1.5 × ATR) — the WIDER wins,
  plus one broker stops-level buffer; validated against `InpMinStopPoints`, broker
  `SYMBOL_TRADE_STOPS_LEVEL`, `SYMBOL_TRADE_FREEZE_LEVEL` and `InpMaxStopPoints`.
  **No valid stop ⇒ no trade.** Every position is opened with server-side SL and TP.
- **TP**: nearest opposing liquidity if RR ≥ `InpMinRR` (1.5), else `InpRewardRisk` × stop (2.0).
- **Daily loss lock**: equity baseline captured on first tick of the server day (persisted in a
  date-keyed terminal global variable); locked beyond `InpMaxDailyLossPercent` (2.0%) or
  `InpMaxDailyLossMoney`; persisted — a chart reload cannot re-base it.
- **Account drawdown halt**: equity high-water mark (persisted `…_hwm`); new entries halted beyond
  `InpMaxAccountDrawdownPct` (8.0% from peak). Position management (BE/partial/SL-rescue) continues.
- **Consecutive losses**: closed deals of this magic are matched against a persisted watermark
  ticket; after `InpStopAfterConsecLoss` (3) losing closes, entries stand down for
  `InpCooldownAfterLossMin` (60 min). A win resets the counter.
- **Daily trade cap**: `InpMaxTradesPerDay` (4), persisted per day.
- **Max simultaneous positions**: `InpMaxOpenPositions` (1), per magic+symbol; one chart per symbol.
- **Spread filter** (absolute points AND fraction of stop distance), slippage `InpDeviationPoints`,
  stale-tick guard, session filter, margin validation, duplicate-order prevention (position cap +
  pending-retry serialization + one decision per new closed M5 bar).
- **No martingale, no grid, no averaging down, stops are never widened**; SL only ever moves
  toward break-even.
- **Protection of stops**: a position found without an SL gets one rebuilt from ATR immediately
  (`[QATS][PROTECT]`).

## 9. Automatic account adaptation implementation

Read at runtime (never assumed): `ACCOUNT_BALANCE/EQUITY/MARGIN/MARGIN_FREE/MARGIN_LEVEL? (level not
required for sizing, margin free is)/LEVERAGE/TRADE_MODE/CURRENCY/TRADE_ALLOWED`, `SYMBOL_DIGITS,
SYMBOL_POINT, SYMBOL_TRADE_TICK_SIZE/VALUE, SYMBOL_TRADE_CONTRACT_SIZE, SYMBOL_VOLUME_MIN/MAX/STEP/
LIMIT, SYMBOL_TRADE_STOPS_LEVEL, SYMBOL_TRADE_FREEZE_LEVEL, SYMBOL_TRADE_MODE/FILLING/EXEMODE,
SYMBOL_TIME`. Verified in code at `LoadSymbolSpec()` and re-verified per decision in
`VerifyAccountProtection()` + `EntriesAllowed()`. XAUUSD, FX majors, indices: no per-instrument
special cases exist; all sizing is derived.

Equity adaptation is proportional in both directions: `Volume ∝ Equity / StopDist` — a $500,
$5,000 and $50,000 demo account each get proportionally correct volume at the same risk %.

## 10. DEMO account verification — **BLOCKED (not performed)**

No MT5 terminal exists in the execution environment (Linux sandbox, 2026-11-09). Evidence:

- `which wine wine64 MetaEditor*` → nothing found; no `/opt` MT5 installation.
- MetaQuotes distribution hosts unreachable from this sandbox:
  `curl https://download.mql5.com/...mt5setup.exe → HTTP 000 (SSL connect error, code 35)`;
  `https://www.metatrader5.com/... → HTTP 000 (code 35)` — same for `www.mql5.com`.
- `pip index versions MetaTrader5` → "No matching distribution found" (the PyPI bridge is Windows-only
  and still needs a Windows terminal).
- No broker credentials, no DEMO server endpoint, no network path to any broker are available here.

**Consequence: every runtime-dependent item in this report is BLOCKED or NOT TESTED, not PASS.**
The DEMO guard itself (the check that would refuse a real account) is implemented and statically
verified, but has never executed against a live terminal.

## 11. Actual BUY execution evidence — **BLOCKED (none)**

Not performed. No order was sent from this environment; no ticket, deal or position ID exists to
report. Fabricating one is refused.

## 12. Actual SELL execution evidence — **BLOCKED (none)**

Not performed. Same reason as §11.

## 13. Stop Loss / Take Profit verification — **NOT TESTED (design verified)**

Design: every `g_trade.Buy/Sell` call passes explicit SL and TP (server-side). Post-send, the EA
(a) reads the retcode, (b) scans positions for magic+symbol opened ≤ 120 s ago and logs
`[QATS][VERIFY] POSITION CONFIRMED …` or a `[CRITICAL]` line — an RPC success is never treated as
proof of a fill. `ManagePositions()` enforces the SL every tick and re-creates a missing SL from
ATR. None of this has run against a live server.

## 14. Compilation results — **BLOCKED**

There is no MetaEditor on this Linux sandbox and none can be obtained (see §10). The `.ex5`
artifact was **not produced**. Substitutes performed (and their limits):

| Check | Tool | Result | Limit |
|---|---|---|---|
| Balance, structure, single-file rule, includes | `tools/verify_quantum_ea.py` | **PASS** (structural) | Not a compiler |
| Identifier audit (42 inputs / 34 globals / 53 user functions: every referenced name declared, no duplicates, no MQL4-isms, no DLL/`#import`, lifecycle present, DEMO-guard markers present, `mode != ACCOUNT_TRADE_MODE_DEMO` refusal condition found) | `tools/verify_quantum_ea.py` | **PASS** (structural) | Not a compiler |
| `printf`-style format string vs argument count audit (all `PrintFormat`/`StringFormat`) | bespoke scanner | **PASS** (0 mismatches) | Cosmetic only |
| Full line-by-line manual review (1,809 lines) + `(string)` cast purge + enum/retcode audit + closed-bar indexing audit | human (agent) | **PASS with caveats** | Human error possible |
| **MetaEditor F7 compile** | — | **BLOCKED** | Requires Windows MT5/MetaEditor |

**Honest bottom line: the EA is not yet compiled anywhere. Zero errors/zero warnings are expected,
but they are NOT proven — F7 is the gate, and it has not been run.**

## 15. Runtime test results — **BLOCKED**

No chart attachment, no market data, no heartbeat, no guards tripped, no positions opened. Nothing
runtime is claimed.

## 16. Remaining blockers (exact, in order to clear)

1. **Compile gate**: a Windows machine (or Wine with the MT5 installer) + MetaEditor → F7 on
   `MQL5/Experts/QuantumAutonomousTradingSystem.mq5`. Expected: 0/0; treat any diagnostic as FAIL.
2. **Runtime gate**: MT5 logged into a **DEMO** broker account with Algo Trading enabled.
3. **Execution gate**: attach EA to XAUUSD (then EURUSD etc.) chart; confirm the attach banner
   prints `PROTECTION: PASS ... DEMO confirmed`, `data pipeline OK`, and watch for
   `[QATS][ORDER]` → `[QATS][EXEC] retcode=10009 …` → `[QATS][VERIFY] POSITION CONFIRMED`.
4. **Evidence capture**: Experts journal export + deal tickets for at least one BUY and one SELL,
   then SL/TP presence verified via `PositionsTotal()`/Positions tab or `HistoryDealGet…` audit.
5. If signals are absent (no closed-bar sweep/structure confluence ≥ 65), the EA stays operational
   and logs `[QATS][SKIP]` with the exact missing component — this is the designed behaviour, not
   evidence of failure; force-trading is explicitly not done.
6. Strategy edge after deployment is **unproven**; forward-demo it before any staged capital
   consideration, and note a demo result is not a forecast.

## 17. Final deployment instructions

1. Recovery exists: `git log` (branch `arena/f83fc236-terad`) and tag
   `recovery/pre-quantum-cleanup-2026-11-09` → `439420d` (= current `main` tip).
   Restore with: `git checkout recovery/pre-quantum-cleanup-2026-11-09`.
2. Copy `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` → `<data folder>\MQL5\Experts\`; F7.
3. Attach to a DEMO chart (any timeframe); one chart per symbol for this magic.
4. Confirm the attach banner (`PROTECTION: PASS`, `data pipeline OK`). If it prints BLOCKED for any
   reason, fix the named permission/account issue — do not trade around it.
5. Defaults are **armed on DEMO** with `InpDemoOnly=true` and no real-money path exists in the
   binary. To observe without sending: `InpDryRun=true`. To stand down: `InpEnableTrading=false`.
6. Optional operator reset after mid-session guard trip: set `InpResetBreakersAtInit=true` for one
   attach, then set it back to `false` (log line `[QATS][RESET]` will appear).
7. Parameters: none are required for a correct deployment — broker economics are read live. Risk
   inputs default to the conservative 0.50% equity model.

---

### APPENDIX A — status summary

| # | Item | Status |
|---|---|---|
| A | Stage A source validation (audit, dependency, structural verification, format audit, review) | **PASS (structural only)** |
| A′ | MetaEditor compilation | **BLOCKED** (no MetaEditor in this environment; MT5 hosts unreachable) |
| B | Stage B MT5 runtime validation (attach, permissions, data, specs) | **BLOCKED** |
| C | Stage C actual DEMO execution (BUY/SELL, SL/TP, server verification) | **BLOCKED** |
| 11 | BUY evidence | **BLOCKED** |
| 12 | SELL evidence | **BLOCKED** |
| 13 | SL/TP verification | **NOT TESTED** (design PASS by review) |
| — | DEMO-account guard implementation | **PASS** (code + marker audit; runtime NOT TESTED) |
| — | Account-size independence (no fixed balance anywhere) | **PASS** (code review: risk derives from ACCOUNT_EQUITY per tick) |
| — | No presets / one-file deployment / no custom indicators | **PASS** |

### APPENDIX B — environment evidence (captured 2026-11-09)

```
$ which wine wine64                → (empty)
$ ls /opt                          → (empty)
$ curl -sI https://download.mql5.com/...  → HTTP 000 (exit 35, SSL connect error)
$ curl -sI https://www.metatrader5.com/   → HTTP 000 (exit 35)
$ pip index versions MetaTrader5          → No matching distribution found
$ python3 tools/verify_quantum_ea.py      → ALL CHECKS PASSED (structural only)
$ git diff --stat 439420d..HEAD           → 173 files changed, +2149 / −144,991
```
