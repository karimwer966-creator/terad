# Quantum Autonomous Trading System (QATS)

One standalone, self-contained **MQL5 Expert Advisor** for MetaTrader 5 that
analyses the chart symbol top-down (Smart Money Concepts), scores the confluence
and executes **real market orders with server-side SL/TP on a verified DEMO
account**.

```
MQL5/Experts/QuantumAutonomousTradingSystem.mq5   <- the ONLY deployment file
```

No external custom indicators. No separate include installation. No `.set`
presets. No DLLs. The only dependency is the standard library `Trade/Trade.mqh`,
which ships with every MT5 terminal.

## What it does

```
D1 bias -> H4 context -> H1 structure -> liquidity map -> liquidity sweep
-> displacement -> MSS/BOS -> order block / fair value gap -> premium/discount
-> M15 confirmation -> M5 entry trigger -> confluence scoring -> risk validation
-> CTrade market execution -> position management (break-even, partial bank)
```

- **Market data / MTF engine** — closed candles only; D1/H4/H1/M15/M5 analysis,
  session VWAP (anchored to server day), ATR(14), EMA 20/50 (D1/H4/H1/M15).
- **SMC engine** — swing/fractal structure, BOS/MSS, liquidity pools (prior
  day/week high/low, equal highs/lows), sweep detection, displacement, order
  blocks, fair value gaps, premium/discount dealing range.
- **Scoring** — 0–100 weighted confluence; trades only at or above
  `InpMinScore` (default 65); hard veto when D1 and H4 both oppose.
- **Risk** — equity-based position sizing (never a fixed balance), hard-capped
  at 2% per trade; daily loss lock (persisted), account drawdown halt from
  equity high-water mark, consecutive-loss stand-down with cooldown, daily
  trade cap, max positions, spread and slippage filters, broker stop/freeze
  level validation, margin validation with automatic volume shrink-to-fit.
- **Execution** — `CTrade` market orders, server-side SL/TP, retcode
  classification (transient retried, permanent abandoned), post-order
  **position verification** (a retcode is not proof of a fill), duplicate-order
  prevention, persisted guard state across reloads.
- **Protection** — refuses to trade unless `ACCOUNT_TRADE_MODE == DEMO`;
  REAL and CONTEST accounts are execution-blocked at attach **and re-verified at
  every entry decision**. Terminal, EA and symbol trade permissions are
  re-verified at every entry decision. There is no input that can switch this
  EA to a real account.

## Build (MetaEditor — required)

MetaEditor ships with MetaTrader 5 (Windows). Compilation cannot be done on a
headless Linux CI box.

1. Copy `MQL5/Experts/QuantumAutonomousTradingSystem.mq5` to
   `<TerminalDataFolder>\MQL5\Experts\`
   (in MT5: **File → Open Data Folder**, then `MQL5\Experts`).
2. Open it in MetaEditor (F4), press **F7**.
   Expected: **0 errors, 0 warnings**. Output:
   `QuantumAutonomousTradingSystem.ex5` next to the source.
3. (Optional, offline sanity check) `python3 tools/verify_quantum_ea.py` —
   structural verifier; **not a compiler**.

## Attach & verify (MT5, DEMO only)

1. Log into a **DEMO** account. Enable **Algo Trading** in the toolbar.
2. Drag `QuantumAutonomousTradingSystem` onto a chart (any symbol; the full
   multi-timeframe analysis runs internally regardless of chart timeframe).
3. Read the attach banner in the Experts journal:
   - `[QATS][PROTECTION] PASS: ACCOUNT_TRADE_MODE=DEMO confirmed ...` —
     anything else means **the EA will not trade**.
   - `[QATS][RISK] per-trade risk = ...` — the effective risk after caps.
   - `[QATS] data pipeline OK | ATR(H1)=... VWAP=...` — market data flowing.
4. `InpHeartbeatSeconds=300` prints a status heartbeat every 5 minutes
   (equity, day P/L, drawdown, guards, spread, last score).

## Operating modes

| Deliberate setting | Behaviour |
|---|---|
| `InpEnableTrading=false` | never sends an order (analysis only) |
| `InpDryRun=true` | logs the exact order it would send; sends nothing |
| `InpDemoOnly=false` | REFUSED at runtime — there is deliberately no path to real money |
| `InpResetBreakersAtInit=true` | one-shot operator reset of persisted guards at attach, then set back to `false` |

Defaults ship **armed on DEMO** (`InpEnableTrading=true`, `InpDryRun=false`,
`InpDemoOnly=true`). One chart per symbol per magic number.

## Repository layout

```
MQL5/Experts/QuantumAutonomousTradingSystem.mq5   the EA
tools/verify_quantum_ea.py                        offline structural verifier
docs/incident-20261101/                           preserved incident audit record
docs/PRODUCTION_AUDIT_2026-11-09_QUANTUM_EA.md    audit & deployment report
.github/workflows/quantum-verify.yml              CI: structural verification
```

Historical recovery point before the consolidation cleanup:
`439420d588d5ac3bbe64bf7ca2260e230abd2d95` (current `main` tip; branch
`arena/f83fc236-terad` is based on it). `git log` retains the full pre-cleanup
history.
