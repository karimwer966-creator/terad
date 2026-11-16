# QSMC v6.6.22 — Staged Go-Live Ladder

⚠️ **DO NOT SKIP STAGES.** Every stage has pass/fail criteria. If a stage
fails any criterion, stay there and fix the root cause before moving on.

This ladder exists because the code itself is production-ready (the curated gate
runs 64 suites, the release gate is GO with 0 warnings, and the brace balance is
0/0), but only a running MT5 terminal can prove order execution, slippage,
spread handling, kill-zone timing and news-guard behaviour.

Every stage below is **one file in `presets/`**, loaded through
**EA → Inputs tab → Load**. The presets only set EA-side inputs (sizing, risk,
safety switches); `nadir2` keeps its own preset (`presets/nadir2_PRODUCTION_XAUUSD.set`).
`tools/check_presets.py` proves offline that each of these files binds to
`MQL5/Experts/QSMC_AutoTrader.mq5`, that every key is a real input, and that no
preset can arm REAL trading.

> Historical note: this document was written at v6.6.14 against three presets
> (`QSMC_AutoTrader_STAGE1_DRYRUN/STAGE2_SIGNALS/STAGE3_LIVE.set`) and an input
> named `InpDemoOnly` that does not exist in the v6.6.22 companion. The stages
> are the same idea; the file names below are the ones that actually ship.

## Before starting any stage

1. Open **MetaEditor** → F7 on `nadir2.mq5`, then on
   `MQL5/Experts/QSMC_AutoTrader.mq5`. Both MUST compile with 0 errors.
2. Journal must print at startup (v6.6.22 strings):
   - the indicator banner containing `v6.6.22`
   - `[QSMC_ARB] ... arbitration layer ON`
   - `[QSMC_AT] QSMC v6.622 execution companion ON`
   - **NO** `self-test: FAIL` lines (ZRE, RXN, RM, KZ).
3. Attach `nadir2.ex5` to **XAUUSD M15**, then load
   `presets/nadir2_PRODUCTION_XAUUSD.set` (full production input surface).
4. Attach `QSMC_AutoTrader.ex5` to **XAUUSD M15**.

## STAGE 1 — Nothing is sent (`presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set`)

| Setting | Value |
|---|---|
| InpEnableTrading | false |
| InpDryRun | true |
| InpAllowRealTrading | false |
| InpRiskPercent / InpMaxRiskPercent | 0.10 / 0.10 |
| InpMaxDailyLossPercent | 0.50 |
| InpPinTimeframeMinutes | 15 |

**Why this file:** the master switch is off *and* dry-run is on, so neither
switch alone is the only thing between the account and an order.

**Duration:** 24 hours minimum, covering one full London + NY session.

**Pass criteria (all must hold):**
- The terminal's **Trade** tab stays empty for the whole session: no orders, no
  deals, no pending requests.
- The dashboard's verdict codes (10–34) match the arrows actually drawn.
- Stops and TPs on the chart sit where the runbook says: below the swing low for
  buys, above the swing high for sells, TP at the opposing liquidity.
- No `INSTANCE MISMATCH`, no `no diagnostic record`, no `ZONE-PURGE`, no
  buffer-copy errors in the Experts log.
- The EA prints its `EFFECTIVE DEFAULTS vs PRESET` table at attach and reports
  **0 differences** for this file's keys.

**Fail → stay here.** Common causes: wrong chart TF, wrong indicator attached,
indicator not compiled, input hash mismatch after manual edits.

## STAGE 2 — Demo armed (`presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set`)

| Setting | Value |
|---|---|
| InpEnableTrading | true |
| InpDryRun | false |
| InpAllowRealTrading | **false** |
| InpRiskPercent / InpMaxRiskPercent | 0.10 / 0.10 |
| InpMaxDailyLossPercent | 0.50 (account DD halt 3.00) |
| InpMaxTradesPerDay | 3, cooldown after a loss 60 min, session 10:00–18:00 server |

This file is a printout of the compiled defaults, so "attach and go" and "load
the preset" are the same configuration. Loading it is still worth one click: it
proves the terminal accepts the file (a key MT5 cannot parse is silently
ignored, which is exactly what `tools/check_presets.py` prevents offline).

**Why this stage exists:** a demo account is the only place where a wrong lot
size, a wrong stop distance or a wrong TP rung costs nothing. It also proves the
broker contract is parsed correctly (min/max lot, step, tick value, stops level,
freeze level) on the account type you intend to trade.

**Duration:** 48 hours minimum, or 20 trades.

**Pass criteria:**
- Journal shows `[QSMC_AT] state ARMED: DEMO account, live orders`.
- Lot sizes match the risk math (≈0.01–0.05 lot per $1000 equity at 0.10 % risk
  and a normal XAUUSD stop) — sanity-check two of them by hand.
- SL and TP are attached to the same ticket; no `INVALID STOPS`, no
  `INVALID VOLUME`, no `OFFQUOTES` run.
- The daily-loss guard arms at session open and the day cap holds at 3 entries.
- No "stops level" or "invalid stops" rejections.

## STAGE 3 — Live, micro/cent account first

| Account | Preset |
|---|---|
| XAUUSD M15, balance ≤ $200 | `presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set` |
| XAUUSD M5 scalping | `presets/QSMC_AutoTrader_v6.6.22_SCALP_M5.set` |
| fixed 0.05 lot, pip TP ladder | `presets/QSMC_fixed005_tp100_200_300.set` |

**REAL trading is a separate, explicit act.** Every shipped preset carries
`InpAllowRealTrading=false`, and the EA refuses a REAL account until that input,
`InpRealAccountConfirm` (the exact login) and `InpRealServerConfirm` (the exact
server) all match — the refusal is logged as
`[QSMC_AT] INIT REFUSED: REAL account detected`. A preset must never carry a
login, and none does.

**Duration:** 1 week minimum on a micro/cent account.

**Pass criteria:**
- Orders fill within normal spread, no requotes, no reject codes ≥ 10014 that
  are not "trade context busy" retries.
- SL/TP attached on the same ticket (no naked orders).
- No partial fills outside documented behaviour.
- Daily equity drawdown stays well under the preset's `InpMaxDailyLossPercent`
  (the guard should fire before the number is reached).
- Net P/L after the week is consistent with the backtests, with sensible RR.

**Move to a normal-sized live account** only after one clean week AND non-negative
expectancy AND no recurring journal errors. Keep `InpRiskPercent` ≤ 0.25 % for
another two weeks, and only then consider raising the caps — the HARD ceilings
are 0.50 % risk, 2.00 % daily loss and 8.00 % account drawdown, and no input can
exceed them.

## Emergency stops

If anything in this list appears, kill the EA immediately (remove it from the
chart, or set `InpEnableTrading=false` in one click) and fall back a stage:

- Any message containing `INVALID STOPS`, `INVALID VOLUME`, `OFFQUOTES`,
  `TRADE DISABLED`, `ACCOUNT BLOCKED`.
- More than one entry in less than 5 minutes (rapid-fire glitch).
- A trade with SL = 0 or TP = 0.
- A lot size larger than 0.10 on a ≤$1000 account at 0.25 % risk (the lot math
  is wrong — halt and recheck).
- The dashboard shows verdict code 0 (NONE) for an hour while the chart shows
  active kill zones: the indicator handle is dead.

## What the compiled defaults do (v6.6.22)

Anyone who compiles and attaches `QSMC_AutoTrader` **fresh, with no preset**,
gets: `InpEnableTrading=true` + `InpDryRun=false` (armed) and
`InpAllowRealTrading=false`. On a demo account that trades immediately; on a
REAL account it refuses to start until the three REAL inputs are set by hand.
There is no "silent" live mode, and there is no input that can widen a HARD
ceiling. Load `QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set` to go back to
"nothing is sent".
