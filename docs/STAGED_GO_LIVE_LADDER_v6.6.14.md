# QSMC v6.6.14 — Staged Go-Live Ladder

⚠️ **DO NOT SKIP STAGES.** Every stage has pass/fail criteria. If a stage
fails any criterion, stay there and fix the root cause before moving on.

This ladder exists because the code itself is now production-ready (all 18/18
static contracts pass, release gate GO, brace balance 0), but only a
running MT5 terminal can prove order execution, slippage, spread handling,
kill-zone timing and news-guard behaviour.

All three preset files live in `presets/` and are loaded via
**EA → Inputs tab → Load**. They only set EA-side inputs (lot sizing, risk,
safety switches); the indicator itself keeps its INTRADAY preset defaults.

## Before starting any stage

1. Open **MetaEditor** → F7 on `nadir2.mq5`, then on
   `MQL5/Experts/QSMC_AutoTrader.mq5`. Both MUST compile with 0 errors.
2. Journal must print at EA startup:
   - `Quantum SMC Intelligence Engine v6.6.14 PRODUCTION BUILD`
   - `[QSMC_ARB] v6.6.14 arbitration layer ON`
   - `[QSMC_AT] QSMC v6.614 execution companion ON`
   - **NO** `self-test: FAIL` lines (ZRE, RXN, RM, KZ).
3. Attach `nadir2.ex5` to **XAUUSD M15** (INTRADAY preset).
4. Attach `QSMC_AutoTrader.ex5` to **XAUUSD M15**.

## STAGE 1 — Dry-run on demo (presets/QSMC_AutoTrader_STAGE1_DRYRUN.set)

| Setting | Value |
|---|---|
| InpDemoOnly | true |
| InpDryRun | true |
| InpEnableTrading | false |
| InpRiskPercent | 0.25% |
| InpMaxRiskPercent | 0.50% |
| InpMaxDailyLossPercent | 2.00% |
| InpLotMode | QSMC_LOT_RISK_PERCENT (0) |

**Duration:** 24 hours minimum, covering one full London + NY session.

**Pass criteria (all must hold):**
- Journal shows `would-send` lines (DryRun) with sane direction/stops/TPs on
  at least 2 qualified signals.
- Stops are set BELOW recent swing low (buys) / ABOVE recent swing high
  (sells); TPs line up with opposing liquidity.
- RR computed by EA ≥ `InpMinRRAtFill` (default 1.00) for every would-send.
- No `INSTANCE MISMATCH`, no `no diagnostic record`, no `ZONE-PURGE`, no
  buffer-copy errors.
- Dashboard shows verdict codes 10–34 matching chart arrows.
- No orders actually reach the broker (DryRun=true prevents this).

**Fail → stay here.** Common causes: wrong chart TF, wrong indicator attached,
indicator not compiled, input hash mismatch after manual edits.

## STAGE 2 — Signals visible, no sending (presets/QSMC_AutoTrader_STAGE2_SIGNALS.set)

| Setting | Value |
|---|---|
| InpDemoOnly | **false** |
| InpDryRun | true |
| InpEnableTrading | false |
| InpRiskPercent | **0.50%** |
| InpMaxRiskPercent | 1.00% |
| InpMaxDailyLossPercent | 2.00% |

**Duration:** another 24–48 hours.

**Why this stage exists:** DemoOnly=true refused to attach to non-demo
accounts entirely; flipping it off confirms the EA boots correctly on a
real (or real-API) account while still sending NOTHING because DryRun
remains true. Use this stage to verify broker-side contract specs
(min lot, max lot, step, tick value, freeze level, stops level) are
parsed correctly on the exact account type you intend to trade.

**Pass criteria:**
- EA starts without `DemoOnly refusal` log line.
- Broker contract parameters log as non-zero/non-default.
- Would-send log lines still appear; risk % computes to plausible lot
  sizes given current XAUUSD price and SL distance (≈0.01–0.05 lot per
  $1000 equity at 0.50% risk — sanity check the math).
- No "stops level" or "invalid stops" rejections appear.
- Daily-loss guard arms itself at session open.

## STAGE 3 — Live, micro/cent account first (presets/QSMC_AutoTrader_STAGE3_LIVE.set)

| Setting | Value |
|---|---|
| InpDemoOnly | false |
| InpDryRun | **false** |
| InpEnableTrading | **true** |
| InpRiskPercent | 0.50% |
| InpMaxRiskPercent | 1.00% |
| InpMaxDailyLossPercent | 2.00% |

**Duration:** 1 week minimum on a micro/cent account.
**Account:** micro/cent only (balance ≤ $200, lot resolution 0.01 or finer).
**Instrument:** XAUUSD M15 only.
**Session:** London + NY only (07:00–20:00 server time).

**Pass criteria:**
- Orders fill within normal spread, no requotes, no reject-codes ≥10014
  that are not "trade context busy" retries.
- SL/TP attached on the same ticket (no naked orders).
- No partial fills outside documented behaviour.
- Daily equity drawdown stays well under 2% (the guard should fire
  before it ever hits that number).
- Net P/L after the week is either slightly positive or only slightly
  negative (consistent with backtest drawdowns), with sensible RR.

**Move to normal-sized live account** only after 1 week clean AND net
expectancy is non-negative AND the journal shows no recurring errors.
When you do, keep InpRiskPercent ≤ 0.50% for another two weeks. You
may raise InpMaxDailyLossPercent to 3.00% once you have ≥ 20 trades of
live history.

## Emergency stops

If anything in this list appears, kill the EA immediately (remove from
chart or set InpEnableTrading=false in one click) and fall back a stage:

- Any message containing `INVALID STOPS`, `INVALID VOLUME`,
  `OFFQUOTES`, `TRADE DISABLED`, `ACCOUNT BLOCKED`.
- More than one opening in less than 5 minutes (rapid-fire glitch).
- A trade with SL = 0 or TP = 0.
- A lot size larger than 0.10 on a ≤$1000 account at 0.5% risk (lot
  math is wrong, halt and recheck).
- Dashboard shows verdict code 0 (NONE) for an hour while the chart
  shows active KZs — usually means indicator handle is dead.

## The code will never change your defaults silently

After this commit, the shipped source defaults remain
`InpEnableTrading=false`, `InpDryRun=true`, `InpDemoOnly=true`. That
means anyone (including you) who compiles and attaches the EA fresh
gets the STAGE-1-equivalent safety cage. You must explicitly load a
later-stage preset to arm live trading. There is no "silent" live
mode.
