# QSMC v6.6.24 — Demo Trial Runbook

**Read this first.** This is a **technical and statistical test of execution**,
not a product launch, not a profit promise, and not investment advice. Nothing
in this document, in the repository, or in the tooling predicts a return. A
trial that passes every threshold below has proven that *the software did what
it was built to do on that sample*. That is the whole claim.

**What has NOT been done before you start:**

* no file in this repository has been compiled by MetaEditor. The build host has
  no MQL5 compiler; `F7` in MetaEditor is the first real compile, and it is
  yours to run;
* no backtest, no optimisation, no walk-forward result is claimed anywhere;
* `QSMC_RunSelfTest()` has not been executed (it needs the terminal);
* the buffer diff (R4) has not been produced.

If any of those four is uncomfortable, stop here — a demo trial on an
uncompiled build is how a "demo" turns into a surprise.

---

## 0. What is being tested

| Question | Answered by |
|---|---|
| Does the executor take only the signals the indicator published, at the bar it published? | `QSMC_trial_<login>.csv` (`signal_seen` → `order_sent` → `fill`) |
| Why were the other signals refused? | the `order_refused` rows, grouped by `tools/analyze_trial.py` |
| Does the plan survive contact with the broker (slippage)? | the `slip_points` field in the `fill` rows |
| Do the breakers fire where they should, and only there? | the `breaker_trip` rows + the unit tests in `tools/test_execution_rules.py` |
| Is the risk per trade the risk that was configured? | `lots`, `risk_money` and `sl` on every `fill` row |
| What did each trade return in R? | the `close` rows (profit and R are reconstructed from the deal history) |

## 1. Before attaching anything (30 minutes, do it in this order)

1. **Compile.** Open MetaEditor, `F7` on: `nadir2.mq5`, `QSMC_AutoTrader.mq5`,
   `QSMC_ResetGuards.mq5`, `QSMC_ArbiterTest.mq5`, `QSMC_BufferDump.mq5`,
   `QSMC_ScannerProbe.mq5`, `KLJ_DataFeeder.mq5`. Zero errors, zero warnings
   that mention the QSMC include folder. *This step has never been run by the
   author of the release; it is the first thing that can fail.*
2. **Self-test.** Attach nothing. Run `MQL5/Scripts/QSMC_ArbiterTest.mq5`. It
   prints `[QSMC_ARB] self-test: N passed, 0 failed`. Any failure stops the
   trial: post the log, do not "work around" it.
3. **The mechanical preflight** (on a machine with Python, in the repository):

   ```
   python3 tools/preflight_demo.py
   ```

   It must print `GO for a DEMO attach` (24 checks). The three failures a
   stale tree produces are version strings — see §2.
4. **The buffer diff** — `docs/BUFFER_DIFF_v6.6.23_v6.6.24.md` §2, if you are
   upgrading from v6.6.23 and want to know whether the two Class B commits
   changed what the indicator publishes. If you cannot produce it, start the
   trial with **both Class B commits reverted** and the diff becomes moot.
5. **Set the acceptance thresholds** in `tools/trial_acceptance.json` **now**,
   before the first trade, and do not touch them again until the trial ends.

## 2. The build you are testing

* `QSMC_VERSION_TEXT` must read `v6.6.24`, and every shipped program must
  declare `#property version "6.624"`. If the preflight says otherwise, you are
  not testing this release.
* the presets and the EA must be one object: `python3 tools/check_presets.py`
  → `9 presets bound to their source, 0 invalid`;
* the EA ships with `InpRiskPercent = 0.10` (per trade), `InpMaxDailyLossPercent
  = 0.50`, `InpMaxAccountDrawdownPct = 3.00`, `InpMaxOpenPositions = 1`,
  `InpPinTimeframeMinutes = 15`, `InpMagic = 20261027`, and the HARD ceilings
  `0.50 % / 2.00 % / 8.00 %` that no input can widen.

## 3. Attach — demo only

1. **A DEMO account. Not a real one, not a contest account.** The EA detects the
   account mode from the terminal (`ACCOUNT_TRADE_MODE`); on a REAL account it
   refuses to leave `INIT_PARAMETERS_INCORRECT` unless
   `InpAllowRealTrading = true` **and** `InpRealAccountConfirm` equals the exact
   login **and** `InpRealServerConfirm` equals the exact server. Leave all three
   alone during the trial. If the EA ever prints `EXECUTION_REAL` during a demo
   trial, stop immediately — that is a defect, not a configuration slip.
2. Chart: **XAUUSD M15** (the preset's pinned timeframe; the EA refuses to trade
   a chart whose period differs from `InpPinTimeframeMinutes`).
3. Attach `nadir2` first (compiled defaults, no `.set`), confirm the dashboard
   shows a version banner, then attach `QSMC_AutoTrader` with
   `presets/QSMC_AutoTrader_DEMO_0.10_200.set`.
4. Read the attach banner end to end. It prints the account mode, the effective
   risk after the HARD clamps, the daily stop and its **state** (MONEY /
   PERCENT / DISABLED — `DISABLED` is a choice, not a default), the session
   window, the position cap and the trial-journal path. If any line disagrees
   with what you intended, detach and fix it before week 0 ends.
5. Confirm `MQL5/Files/QSMC_trial_<login>.csv` exists and has a header row.

## 4. Week 0 — the rehearsal (`InpDryRun = true`)

The owner's decision for v6.6.24 was to **keep `InpDryRun` as shipped** (false),
so this week is a deliberate manual step, not a default.

* Set `InpDryRun = true`. The EA logs every order it *would* send, sends
  nothing, and consumes **no** entry budget (`InpEnableTrialJournal` still
  records the `order_refused` rows with reason `DRY RUN`).
* Run for **one full week** with the market you intend to trade.
* At the end of the week, check the CSV:
  * is `signal_seen` non-zero? If it is zero for a week, the trial cannot start —
    either the session window, the spread cap or the class filter is too tight
    for this symbol, and that is a finding, not a failure;
  * do the `order_refused` reasons match what you expected to see?
  * does `risk_money` on the dry rows equal 0.10 % of your equity at the stop
    (within rounding)? If yes, the ladder is doing what it says.
* Turn `InpDryRun` back to **false** only after that week, and note the time in
  the trial log.

## 5. Weeks 1–8 — the live-demo phase

* Leave the EA alone. Every parameter change invalidates the sample; if you must
  change one, record the timestamp and analyse the phases separately.
* Check once a day, at the same time: the Experts log for `[QSMC_AT GUARD]`,
  `[QSMC_AT][EMERGENCY]`, `UNCONFIRMED`, and the CSV row count.
* Check once a week:

  ```
  python3 tools/analyze_trial.py /path/to/QSMC_trial_<login>.csv
  ```

  Read the funnel and the refusals **before** the thresholds. A trial whose
  funnel reads 40 signals / 4 orders / 4 fills is telling you about the gates;
  a trial whose funnel reads 40 / 4 / 1 is telling you about the broker.

## 6. Stop conditions — detach, do not "wait it out"

Stop the trial immediately if **any** of these appears:

| Condition | Why it stops the trial |
|---|---|
| `[QSMC_AT][EMERGENCY]` — a position without a verified server-side SL | the loss bound is gone; the EA may already have closed it. Verify manually. |
| `UNCONFIRMED` — the server accepted something the EA cannot see | the EA marked the signal seen and consumed an entry slot without counting it as sent. Verify the position in the terminal. |
| `EXECUTION_REAL` on a demo trial, or an identity-drift lockout | account authorisation is not what you think it is. |
| a `breaker_trip` row you cannot explain from the trades before it | the breaker may be measuring the wrong baseline. Connects to the arithmetic in `tools/test_execution_rules.py`. |
| any position whose `lots` exceeds the planned size | sizing defect. |
| two EA instances on one terminal with two magics | the ownership lane exists to refuse the second one; if both traded, report it (F-002). |
| the trial journal stops growing while trades happen | the CSV is silently disabled; the trial has no evidence. |

Report every stop with: the CSV, the Experts log excerpt, the chart screenshot,
and the EA's attach banner.

## 7. Reading the result

`tools/analyze_trial.py` prints the funnel, the refusals, the breakers and then
four lines against `tools/trial_acceptance.json`:

| Threshold | Meaning |
|---|---|
| `min_trades` | below this, every statistic is noise |
| `max_dd_r` | worst peak-to-trough of the cumulative R curve — **check this first** |
| `min_expectancy_r` | mean R per closed trade |
| `max_avg_slippage_points` | mean \|fill − planned entry\| in points |

Below `min_sample_for_conclusion` closed trades (default 100) the tool prints

```
sample size too small to conclude
```

and that sentence stands even if all four thresholds pass. Eight weeks on one
symbol will very often land under 100 closed trades; the honest conclusion then
is "no conclusion", and the correct next step is a longer sample — not a bigger
position.

**No profitability claim is made, implied or measured by this tooling.** R-multiples
describe the execution of a plan; they are not a forecast, a win rate, or a
recommendation to trade.

## 8. What to send back

1. `QSMC_trial_<login>.csv` (R1);
2. the output of `tools/analyze_trial.py` with the acceptance file you used;
3. the Experts log covering the whole trial;
4. the buffer diff (R4) if you produced one;
5. the MetaEditor compile log from step 1.1;
6. a one-paragraph narrative of every manual action you took — especially every
   time you were tempted to intervene and did not.
