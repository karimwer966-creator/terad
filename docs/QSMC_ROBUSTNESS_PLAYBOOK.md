# Robustness playbook — how a QSMC study earns the right to go live

**Scope:** `QSMC_AutoTrader` + `nadir2` · **Shipped build:** v6.6.20 · **Written:** 2026-11-08
**Tooling added with this document:** `tools/wfa_harness.py`, `tools/wfa_stats.py`,
`tools/wfa_demo.py`, `tools/test_wfa_robustness.py` · **Examples:** `docs/wfa/params.example.json`,
`docs/wfa/study.example.json` · **العربية:** `docs/QSMC_ROBUSTNESS_PLAYBOOK_AR.md`

This is the discipline that sits *between* "the EA compiles" and "the EA trades money". It is
deliberately boring: windows fixed before the first run, parameters frozen before the first
out-of-sample look, verdicts decided by thresholds written down in advance.

> **What this document cannot claim.** There is no MetaTrader and no MetaEditor in this
> repository's environment. Nothing here has been compiled, and **no number in this document is a
> QSMC backtest result** — the worked example is synthetic and says so where it appears. The
> automated gates prove arithmetic, file emission and refusal behaviour. They do not prove an
> edge, and they never will. This is general educational material, not financial advice; forex
> trading carries substantial risk of loss.

---

## Part A — The enemy, stated once

Over-optimisation (curve-fitting) is a model that learned the noise of one historical sample.
You cannot detect it from the winning equity curve, because the winning equity curve *is* the
symptom. You detect it from the things below.

| Telltale sign | What it actually means |
|---|---|
| Equity collapses when the test period shifts by a few months | The "edge" is a property of a date range |
| RSI 14 works, RSI 15 destroys it | You chose a spike, not a plateau |
| Many parameters, few trades | More degrees of freedom than observations |
| Profit concentrated in a handful of trades or one regime | You are long a single event, not a behaviour |

Every mechanism in Parts B–D exists to make those four failures visible **before** money is at
risk, and to make the moment you cheat visible too.

### A1. Start from a hypothesis, not from an optimiser

Write, before any run:

1. **The edge in one sentence** — why should this exist, and who is on the other side?
2. **Expected behaviour** — win-rate range, holding time, trades per month.
3. **Expected failure regimes** — trending vs ranging, high vs low volatility, news windows.

If (1) cannot be said in one sentence, you are mining noise with a nice UI. Keep the written
hypothesis next to the study manifest: a system whose results contradict its own hypothesis is
information, not a disappointment.

### A2. Keep the model small — and decide what "small" means in this repo

`nadir2.mq5` declares **583 inputs**; `QSMC_AutoTrader.mq5` declares **51** (measured on the
shipped source, v6.6.20). That is a configuration surface, not an optimisation surface. Two facts
make the distinction concrete:

* **The EA reads the indicator with its compiled defaults.** `QSMC_AutoTrader` instantiates the
  indicator as `iCustom(_Symbol, _Period, InpIndicatorName)` with **no input list** (see
  `docs/QSMC_GO_LIVE_RUNBOOK.md` §3). The 583 indicator inputs are therefore *not reachable* from
  the EA: an optimisation of an indicator threshold is not a walk-forward, it is a rebuild.
* **The EA's own inputs are the optimisable set.** Choose **at most six** of the 51 and freeze
  the rest at a validated preset (e.g. `presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set`).

| Rule | Concrete form |
|---|---|
| 3–6 free parameters | the `optimize: true` entries in your spec, nothing else |
| ≥ 30 trades per free parameter | 4 parameters ⇒ ≥ 120 stitched OOS trades |
| Round, logical grid values | ATR multiple 1.5 / 2.0 / 2.5, not 2.137 |
| No filter that helps in exactly one test | a filter must survive several markets **and** periods |

Temptation to add a seventh parameter is the signal to stop, not to extend.

### A3. Data and simulation honesty

| Requirement | QSMC / MT5 setting |
|---|---|
| Real tick data, not modelled | `Model=4` ("every tick based on real ticks") is the harness default; `Model=1/2` will flatter a system with intra-bar stops |
| Costs included | broker commission and swap in the account; test again at **1.5–2×** spread |
| Latency | MT5 tester delay setting; a strategy that only works on the first tick after a signal dies here |
| Gaps and spikes | weekend gaps, NFP/FOMC spreads, stop-outs through the SL |
| No look-ahead | signals on **closed** bars only; no higher-timeframe data that is not final |
| One feed is not evidence | if the edge exists only on one broker's history, it is an artefact of that history |

### A4. Split the data once, before anything else

```
|------------ in-sample (60-70%) ------------|-- OOS (20-30%) --|-- holdout (10%) --|
       optimisation and development            untouched          ONE look, at the end
```

The harness enforces the boundary mechanically: `plan` removes the holdout from the date range
**first**, then packs windows into what is left, so no window can overlap it. If you look at the
holdout, tweak, and look again, you no longer have a holdout — you have more in-sample data with
extra steps.

---

## Part B — The concrete MT5 walk-forward workflow

One baseline plus six numbered steps. Each produces a file, and each file is the input to the next
one. Nothing is typed into the terminal by hand, because hand-editing is where the discipline
leaks.

```
plan ──> configs ──> run (_opt inis) ──> ingest ──> plateau ──> apply ──> run (_oos inis)
                                                                     └──> report
```

### B0. Baseline preset (once)

Start from the shipping preset, not from a blank chart:

```bash
cp presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set /path/to/backtest_base.set
```

**Trap:** that preset ships inert — `InpEnableTrading=false`, `InpDryRun=true`, `InpDemoOnly=true`.
In the Strategy Tester those three mean *zero trades and a perfectly flat report*. The backtest
`.set` must therefore arm the EA **for the tester only**:

```json
{"name": "InpEnableTrading", "value": "true"},
{"name": "InpDryRun",        "value": "false"},
{"name": "InpDemoOnly",      "value": "true"}
```

`wfa_harness.py configs` warns when a QSMC spec would leave the EA inert. Keep that arming set in
a separate file and never let it reach a live chart.

### B1. Fix the windows

```bash
python3 tools/wfa_harness.py plan \
  --from 2018-01-01 --to 2026-01-01 \
  --is-months 24 --oos-months 6 --holdout-months 12 \
  --free-params 4 --out out/wfa/plan
```

Produces `out/wfa/plan/plan.json` and `plan.md` — ten contiguous six-month OOS segments plus a holdout of
`2025-01-01 → 2026-01-01` that is now off-limits until the very end.

The planner **refuses** rather than warns on structural mistakes:

| Refused input | Why it is refused, not warned |
|---|---|
| `--step-months` < `--oos-months` | overlapping OOS segments double-count time; the stitched curve stops being a track record |
| negative holdout | an inverted boundary is a bug in your intent, not a setting |
| range shorter than one IS window | there is nothing to validate; a "GO" would be empty |
| `--from` ≥ `--to` | reversed range |

It **warns** (loudly, and continues) on: fewer than 5 OOS windows, no holdout reserved, less than
85% coverage of the range, more than 6 free parameters.

### B2. Emit the MT5 configuration

```bash
python3 tools/wfa_harness.py configs \
  --plan out/wfa/plan/plan.json \
  --params docs/wfa/params.example.json \
  --symbol XAUUSD --period H1 \
  --model 4 --optimization 2 --criterion 5 \
  --out out/wfa/cfg
```

Two passes per window, and the difference between them is the entire study:

| File | Dates | Optimiser | Purpose |
|---|---|---|---|
| `wNN_opt.ini` + `wNN_opt.set` | IS only | **on** | read the *surface* |
| `wNN_oos.ini` + `wNN_oos.set` | OOS only | **off** | one frozen parameter set, one result |

Notes on the emitted files:

* `OptimizationCriterion=5` (balance + max Sharpe) is the default because **this EA implements no
  `OnTester`**, so criterion 6 ("custom max") has nothing to call. The criterion only affects how
  the terminal *sorts* the result list; the verdict is computed again by `wfa_stats.py` against
  its own gates, on its own criteria, and does not trust the sort.
* `ExpertParameters=<window>.set` is the portable path. A build that ignores it can use the
  `*.testerinputs.txt` block generated next to every ini.
* `ForwardMode=0` on purpose: MT5's forward mode re-optimises at the end of the run, which turns
  the OOS segment into one sample instead of a distribution. This plan rolls windows explicitly.
* **An OOS `.set` never contains an optimisation range.** Writing one that does would re-optimise
  inside the out-of-sample window and silently invalidate the study; the emitter asserts the
  absence, `apply` rewrites the file with single values, and
  `tools/test_wfa_robustness.py` fails the build if that ever regresses.

### B3. Run the optimisation passes

Close MetaTrader, then run `out/wfa/cfg/run_all.ps1` (Windows) — sequential by design: parallel
runs fight over the same terminal, history cache and CPU, and a half-run window is
indistinguishable from a failed one.

### B4. Ingest the exports

```bash
python3 tools/wfa_harness.py ingest --input "C:/MT5/reports" --out out/wfa/tidy/
```

The ingester accepts MT5's three export shapes (`<Row Profit="…"/>` attributes, one child element
per column, and the `<Row><Cell><Data>` grid) plus locale CSVs (`1 234,56` and `1.234,56`), and
normalises the columns to canonical names (`Profit` → `net_profit`, `ProfitFactor` → `profit_factor`,
`Equity DD %` → `max_dd_pct`). Numbers are parsed, never coerced: an `n/a` cell becomes an empty
value, not a zero that would flatter an average.

### B5. Read the surface, not the optimum

```bash
python3 tools/wfa_stats.py plateau \
  --runs out/wfa/tidy/w01_opt.tidy.csv \
  --params InpRsiPeriod,InpAtrMult \
  --min-trades 100 --k 4 --heatmap InpRsiPeriod,InpAtrMult --perturbation \
  --json out/wfa/w01_choice.json
```

What the chooser does, in order:

1. **Drops** rows below `--min-trades` before ranking. A 12-trade cell with profit factor 9 is
   noise, and averaging it into a neighbourhood poisons the average.
2. **Scores each cell by the median of its k nearest neighbours** (in per-axis normalised space),
   not by its own result. A single lucky cell three steps away can lift a neighbour *mean* above
   the real plateau; a median ignores it.
3. **Prefers the interior**: among cells within 2% of the best neighbourhood score, the one
   furthest from the grid boundary wins. If two regions are equally good, the one you can move
   inside without falling off is strictly better.
4. **Reports the peak anyway**, plus its distance from the grid mean in standard deviations, so a
   spike is documented rather than hidden. `chosen_is_peak=True` is allowed but suspicious: it
   means the search's best cell is also its broadest region, which is rarer than it feels.
5. **Perturbs ± one grid step** per parameter. Smooth degradation = a real feature; a cliff one
   step away = the optimiser picked the last lucky cell before the edge of the grid.

Then freeze the choice:

```bash
python3 tools/wfa_harness.py apply \
  --plan out/wfa/plan/plan.json --params docs/wfa/params.example.json \
  --selection out/wfa/w01_choice.json --out out/wfa/cfg
```

`apply` accepts `{"chosen": {"params": {...}}}` (one set for every window, written into each
`wNN_oos.set`) or `{"w01": {...}, "w02": {...}}` (per-window). It refuses input names that are not
in the spec, and reports which parameters were left at their grid default instead of inventing
values. The applied selection is dumped to `selection_applied.json` next to the sets, so "the
parameters I traded OOS" is a timestamped file rather than a memory.

### B6. Run the OOS passes, then judge

```bash
python3 tools/wfa_stats.py report --manifest docs/wfa/study.example.json \
  --out out/wfa/report.md --json out/wfa/report.json
```

Exit code 0 = no FAIL, 1 = at least one FAIL, 2 = bad input. The report contains its own
limitations section, because a verdict without one is marketing.

`docs/wfa/study.example.json` is a **template**: paths resolve against the manifest's own
directory, so it exits 2 until the files it names exist. That is the tool refusing to invent
measurements — the correct failure mode, and the reason no gate can be satisfied by a missing
file.

---

## Part C — Metrics and default gates

A healthy system does not look spectacular; it looks *stable*. Defaults live in
`DEFAULT_GATES` in `tools/wfa_stats.py` and are meant to be edited **before** a study, in the
manifest, consciously.

| Gate | Default | Reading |
|---|---|---|
| Sample size | ≥ 100 stitched OOS trades | below this, every other number is a rumour |
| Trades per free parameter | ≥ 30 | 4 parameters ⇒ 120 trades |
| Free parameters | ≤ 6 | above six the search finds noise faster than edge |
| Profit factor | 1.3 – 3.0 | above 3.0 on a large sample is a survivor of the search, not an edge |
| Walk-forward efficiency | ≥ 0.50 | aggregate OOS ÷ IS |
| Profitable OOS windows | ≥ 60% | consistency, not total |
| Parameter stability | worst-axis relative spread ≤ 0.50 | a moving optimum is fitting |
| Monte Carlo drawdown p95 | ≤ 30% of peak | order-dependence of the equity path |
| Drop best 5–10% of trades | p05 > 0 | reliance on a handful of winners |
| Deflated Sharpe | ≥ 0.95 | probability the true Sharpe beats the best-of-N zero-skill hurdle. The hurdle needs the **dispersion** of trial Sharpes (`trial_sharpes` or `trial_sharpe_sd`), not only their count |
| Random-entry benchmark | p ≤ 0.05 | do the *entries* beat random entries with the same exits? |
| Cost stress | still profitable at +1.5–2× cost | edge thickness |
| Holdout | net profit > 0 | one look, one verdict |

A trial count without dispersion deflates nothing: with V=0 the expected best-of-N zero-skill
Sharpe is 0 and "5000 trials" costs you nothing. That is why the gate **fails** in that case with
`no trial-Sharpe dispersion supplied` rather than reporting a very strict-looking pass — the
easiest way to fake a multiple-testing correction is to report the number of trials and hide the
dispersion.

Also read, even when a gate does not own them: **drawdown duration** (time underwater is a
psychological constraint, not a cosmetic one), **expectancy per trade relative to costs**, and the
**distribution of trade results** (a martingale or an unbounded grid hides tail risk behind a high
win rate — evaluate the worst path explicitly, never the average one).

### What a FAIL means

| FAIL | Do this | Do not do this |
|---|---|---|
| Walk-forward efficiency | shorten the IS window or reduce the parameter count | re-run with a different metric until it passes |
| Parameter stability | remove the unstable parameter entirely | pin it to the value that looked best |
| Monte Carlo drawdown p95 | size down; re-examine position sizing | average the Monte Carlo result away |
| Deflated Sharpe | count **every** variant you tried (including this one) | argue that "only the last few counted" |
| Random-entry benchmark | the edge is in the exits or nowhere | add filters until the p-value drops |
| Cost stress | widen stops or reduce frequency | assume the broker's spread is the good one |

---

## Part D — Risk, engineering, incubation, kill criteria

### D1. Risk knobs are robustness, not tuning

* Position sizing is volatility-based (ATR) or fixed-fractional, **never** fitted to the backtest.
  QSMC: `InpLotMode`, `InpRiskPercent`, `InpMaxRiskPercent` (with the code's hard ceiling winning).
* Martingale, unbounded grids and averaging down inflate backtests and fail catastrophically.
* Hard limits exist so that being wrong is survivable: `InpMaxDailyLossPercent` /
  `InpMaxDailyLossMoney`, `InpMaxAccountDrawdownPct`, `InpStopAfterConsecLoss`,
  `InpMaxOpenPositions`, `InpMinStopPoints` / `InpMaxStopPoints`.
* A stop loss belongs at the broker, not only in EA logic.

### D2. Engineering robustness — most "strategy failures" are code failures

| Requirement | Where it lives in this repo |
|---|---|
| Retries on requote / rejected order / busy trade context | `test_execution_safety.py`, `test_at_risk_audit.py` |
| State rebuilt from the terminal after a restart | EA reconstructs positions by magic + symbol |
| Broker normalisation: digits, min stop, lot step, filling mode | companion sizing path |
| Logging of every decision with inputs and result | `test_decision_journal.py`, `test_diag_bridge.py` |
| No ad-hoc live parameter edits | presets are generated: `tools/generate_set_presets.py --check` |

The last row is why the harness writes files instead of instructions: **a preset that drifts from
the source is a live incident waiting for a weekend.**

### D3. Incubation

1. Forward test on demo/cent for **2–3 months or 50–100 trades**, whichever is later.
2. Compare live vs backtest expectations: trade frequency, average spread paid, slippage, win
   rate, drawdown. A large gap means the *simulation* is wrong, not the market.
3. Go live at minimal size; scale only while performance stays inside the Monte Carlo bands.

### D4. Kill criteria — written while you are still unemotional

| Written in advance | Example |
|---|---|
| Expected ranges | win rate 52–62%, profit factor 1.3–1.8, max DD 8–14% (from the Monte Carlo) |
| Halt conditions | drawdown > 1.5× the historical max; 20 consecutive trades outside the 95% band |
| Review cadence | monthly and quarterly reviews — not reactions to a bad week |
| Re-optimisation policy | fixed schedule, same walk-forward procedure, never to chase recent losses |

---

## Part E — End-to-end checklist

| # | Gate | Concrete artefact / command |
|---|---|---|
| 1 | Written hypothesis + expected failure regimes | a paragraph in the study manifest's `label`, kept with the report |
| 2 | Simple rules, ≤ 6 free parameters | `docs/wfa/params.example.json` — `optimize: true` count |
| 3 | Real-tick data, realistic costs and latency | `--model 4`, cost stress in the manifest |
| 4 | IS / OOS / holdout defined up front | `wfa_harness.py plan` → `plan.json` |
| 5 | Surface read, parameters from a plateau | `wfa_stats.py plateau` → `chosen` |
| 6 | Walk-forward passed | `wfa_stats.py report` → `wfe_aggregate` |
| 7 | Multiple-testing correction + random entries | `trials` in the manifest, `benchmarks/` directory |
| 8 | Monte Carlo, cost stress, regime split | `mc`, `cost_stress`, `windows` in the manifest |
| 9 | Risk limits and volatility sizing | preset + `test_at_risk_audit.py` |
| 10 | Hardened code, logging, error handling | `python3 tools/check_production_ready.py` |
| 11 | Demo incubation, then small live | `docs/QSMC_GO_LIVE_RUNBOOK.md` |
| 12 | Monitoring, halt and re-optimisation rules written | the table in D4, signed and dated |

Steps 1–8 are offline and repeatable. Steps 9–12 are operational and human. The report can only
close the first group; pretending otherwise is how a green table becomes a red account.

---

## Part F — Run the pipeline yourself, on data that is openly fake

```bash
python3 tools/wfa_demo.py --out out/wfa/demo
```

One command builds a complete synthetic study — 420 OOS trades, a 3-parameter grid shaped as a
bowl with one deliberate corner spike, six decaying walk-forward windows, 60 random-entry
benchmarks and the manifest that wires them together — then judges it and writes
`out/wfa/demo/report.md`. Default output:

```
gate                               measured               verdict
sample size                        420 trades             PASS
trades per free parameter          420 trades / 3 params  PASS
free parameters                    3                      PASS
profit factor in range             1.64                   PASS
walk-forward efficiency            0.28                   FAIL
profitable OOS windows             5/6 (83%)              PASS
parameter stability (worst axis)   0.00 relative spread   PASS
Monte Carlo drawdown p95           9.2%                   PASS
drop 5-10% of trades               p05 = 9300.00          PASS
deflated Sharpe ratio (150 trials) 0.0                    FAIL
random-entry benchmark             p = 0.016 (60 runs)    PASS
cost stress (extra 12.00/trade)    5440.0                 PASS

verdict: NO-GO (2 gate(s) failed)
```

Read what the demo actually demonstrates, because each line is a mechanism and not a result:

| Observation | Mechanism it exercises |
|---|---|
| `peak row 900000.00`, `chosen 2000.00`, `peak 12.17σ from the grid mean` | the chooser refuses a 450× outlier and lands on the interior maximum |
| `walk-forward efficiency 0.28` | the synthetic edge decays across windows; the roll-forward says so |
| `deflated Sharpe 0.0 (150 trials)` | the spike also inflates trial dispersion — one lucky cell poisons the correction as well as the choice |
| `random-entry p = 0.016` | the entries do beat random entries with the same exits, on this data |
| two runs, same seed, byte-identical report | the pipeline is deterministic; a verdict can be reproduced |

`NO-GO` is the expected verdict, and `tools/test_wfa_robustness.py` asserts it: **a clean GO out of
this demo would mean a gate moved.** The demo also proves the report is legible *before* a real
multi-window MT5 sweep exists to be judged.

> Every number above is generated inside `tools/wfa_demo.py`. None of it describes XAUUSD, EURUSD,
> or any QSMC build, and none of it should be quoted as a backtest result — the same sentence is
> printed at the top of the generated report, on purpose.

## Part G — Maintaining this document

* The gates are defaults in code (`DEFAULT_GATES`), and the tests in
  `tools/test_wfa_robustness.py` pin the arithmetic behind them. If you change a default, change
  the test that describes it in the same commit.
* `tools/wfa_demo.py` is the end-to-end smoke test of the *pipeline*, and its expected verdict
  (`NO-GO`, two failures) is asserted. Do not "fix" that by making the demo's synthetic edge
  stronger — fix the gate only if the gate is wrong.
* The workflow is three commands (`plan`, `configs`, `report`) and one judgement (`plateau` →
  `apply`). If a step needs a human decision, it is named as such; if it does not, it is a file.
* MT5's own export schema is not versioned by MetaQuotes. The ingester accepts three shapes and
  fails loudly on a fourth rather than guessing — a silently mis-parsed grid would poison every
  downstream number. If a new build writes a new shape, add it to `_table_from_elements` **and**
  to the fixtures in the test file.

Closing thought, unchanged from the methodology this playbook implements: over-optimisation is a
discipline problem, not a tooling problem. The goal is not the best backtest — it is a system
whose live results land *inside* the range its testing predicted.
