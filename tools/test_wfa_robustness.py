#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WFA-ROBUSTNESS - independent tests for the walk-forward harness and stats.

WHY THIS EXISTS
---------------
tools/wfa_harness.py and tools/wfa_stats.py decide whether a trading system is
allowed to go live. A silent bug in either one is worse than no gate at all: it
would print "GO" with a straight face. So the arithmetic here is checked against
hand-computed values, not against the modules' own output:

  * drawdown / profit factor / expectancy on a five-trade path worked by hand;
  * the Deflated Sharpe Ratios's Gumbel hurdle against its closed form for N=2;
  * PSR's monotonicity, and DSR == PSR when only one trial was made;
  * "one permutation cannot change the sum" (an invariant of fixed-size sizing);
  * a plateau chooser that must refuse an isolated spike three standard
    deviations above a flat grid;
  * MT5 file emission: an OOS .set that contains an optimisation range is the
    single most expensive mistake in the whole workflow, so it is asserted
    absent, not assumed;
  * every MT5 export shape (attributes / child tags / cell grid / locale CSV)
    normalising to the same tidy numbers.

These are tests of IMPLEMENTATION arithmetic. They are not a backtest, not a
compiler, and they prove nothing about any strategy's profitability.
"""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import wfa_demo as D
import wfa_harness as H
import wfa_stats as S

FAILS = []
COUNT = [0]


def check(ok, name, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s%s" % (name, ("  [%s]" % detail) if detail else ""))
        FAILS.append(name)


def close(a, b, tol=1e-9):
    return a is not None and b is not None and abs(a - b) <= tol


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ---------------------------------------------------------------------------
# 1. Numeric parsing - MT5 writes locale-formatted numbers
# ---------------------------------------------------------------------------
check(close(S.to_float("1 234.56"), 1234.56), "thousands separator (space) parses")
check(close(S.to_float("1.234,56"), 1234.56), "decimal comma with dot grouping parses")
check(close(S.to_float("1,234.56"), 1234.56), "comma grouping parses")
check(close(S.to_float("12,5"), 12.5), "lone decimal comma parses")
check(close(S.to_float("42%"), 42.0), "percent sign is stripped, not invented")
check(S.to_float("") is None and S.to_float("n/a") is None and S.to_float("-") is None,
      "empty and n/a cells are None, never 0.0")
check(S.to_float("abc") is None, "text cells are rejected rather than coerced")

# ---------------------------------------------------------------------------
# 2. Normal distribution helpers
# ---------------------------------------------------------------------------
check(close(S.norm_cdf(0.0), 0.5, 1e-12), "norm_cdf(0) == 0.5")
check(abs(S.norm_ppf(0.975) - 1.959964) < 1e-5, "norm_ppf(0.975) is the 95% quantile")
check(abs(S.norm_ppf(S.norm_cdf(1.3)) - 1.3) < 1e-8, "ppf/cdf round-trip to 1e-8")
try:
    S.norm_ppf(1.0)
    check(False, "norm_ppf rejects 1.0")
except ValueError:
    check(True, "norm_ppf rejects 1.0")

# ---------------------------------------------------------------------------
# 3. Trade statistics against values computed by hand
# ---------------------------------------------------------------------------
P = [100.0, -50.0, 100.0, -200.0, 100.0]
st = S.trade_stats(P, start_equity=1000.0)
check(close(st["net_profit"], 50.0), "net profit is the plain sum", st["net_profit"])
check(close(st["profit_factor"], 300.0 / 250.0), "profit factor = gross win / gross loss",
      st["profit_factor"])
check(close(st["win_rate"], 0.6), "win rate counts strictly positive trades")
check(close(st["expectancy"], 10.0), "expectancy is net profit per trade")
check(close(st["max_dd_abs"], 200.0), "max drawdown is peak-to-trough (200 of 1150)",
      st["max_dd_abs"])
check(close(st["max_dd_pct"], 200.0 / 1150.0, 1e-12), "drawdown % is relative to the peak",
      st["max_dd_pct"])
check(st["longest_dd_trades"] >= 2, "underwater duration is measured in trades")
check(close(st["sharpe"], 10.0 / S.stdev(P)), "per-trade Sharpe is mean / sample sd")
check(S.trade_stats([100.0])["max_dd_abs"] == 0.0, "a single winner has no drawdown")
check(not math.isfinite(S.trade_stats([100.0])["profit_factor"]),
      "no losing trade => profit factor is infinite, not a large number")

path = S.equity_path([100.0, 100.0], 1000.0, compounding=True)
check(close(path["net_profit"], 210.0), "compounding grows the second trade's size", path)
check(close(S.equity_path([-2000.0], 1000.0)["final_equity"], 0.0),
      "equity is floored at zero, not allowed negative")
check(S.equity_path([-2000.0], 1000.0)["ruined"] is True, "ruin is reported explicitly")

# ---------------------------------------------------------------------------
# 4. Monte Carlo invariants
# ---------------------------------------------------------------------------
mc_a = S.mc_shuffle(P, iterations=300, seed=11, start_equity=1000.0)
mc_b = S.mc_shuffle(P, iterations=300, seed=11, start_equity=1000.0)
check(mc_a["net_profit"] == mc_b["net_profit"], "same seed => identical Monte Carlo")
check(mc_a["net_profit"]["min"] == mc_a["net_profit"]["max"] == sum(P),
      "a permutation cannot change the summed P/L of fixed-size trades")
check(mc_a["dd_pct"]["max"] >= st["max_dd_pct"] - 1e-12,
      "some permutation is at least as bad as the historical order")
check(S.mc_shuffle(P, iterations=50, seed=12)["dd_pct"]["max"] != mc_a["dd_pct"]["max"]
      or mc_a["dd_pct"]["max"] == mc_a["dd_pct"]["min"],
      "a different seed produces a different drawdown distribution")

bs = S.mc_bootstrap(P, iterations=400, seed=3, start_equity=1000.0)
check(bs["trades"] == len(P), "bootstrap keeps the sample size")
check(bs["net_profit"]["p05"] <= bs["net_profit"]["p95"], "bootstrap percentiles are ordered")

skip_rand = S.mc_skip([100.0] * 90 + [-10.0] * 10, iterations=200, seed=5,
                      drop_frac=0.10, start_equity=1000.0)
check(skip_rand["net_profit"]["p05"] > 0, "dropping 10% of a strongly positive set stays positive")
skip_best = S.mc_skip([100.0] * 10 + [-10.0] * 90, iterations=5, seed=5,
                      drop_frac=0.20, randomised=False, start_equity=1000.0)
check(close(skip_best["net_profit"]["min"], sum(sorted([100.0] * 10 + [-10.0] * 90)[:80])),
      "deterministic mode removes the BEST trades (the pessimistic reading)",
      skip_best["net_profit"]["min"])

# ---------------------------------------------------------------------------
# 5. PSR / DSR - the multiple-testing correction
# ---------------------------------------------------------------------------
check(S.psr(0.2, 400, 0.0, 3.0) > 0.5, "a positive Sharpe over 400 trades beats SR=0")
check(S.psr(0.2, 4000, 0.0, 3.0) > S.psr(0.2, 400, 0.0, 3.0), "more trades => more certainty")
check(S.psr(0.0, 400, 0.0, 3.0) == 0.5, "zero Sharpe is a coin flip against zero")
check(abs(S.expected_max_sharpe(2, 1.0) - 0.5195) < 0.002,
      "E[max SR] for N=2 matches the closed form (gamma * z(1-1/2e))",
      S.expected_max_sharpe(2, 1.0))
check(S.expected_max_sharpe(100, 0.01) > S.expected_max_sharpe(10, 0.01) >
      S.expected_max_sharpe(1, 0.01) == 0.0,
      "the hurdle rises with the number of trials, and is 0 for one trial")

mom = S.moments(P)
single = S.deflated_sharpe(P, 1)
check(single["sr0"] == 0.0 and close(single["dsr"],
                                     S.psr(mom["sharpe"], len(P), mom["skew"],
                                           mom["kurtosis"], 0.0), 1e-12),
      "DSR with one trial degenerates exactly to PSR against zero",
      (single["dsr"], single["psr"]))
check(close(single["dsr"], single["psr"], 1e-12),
      "with no selection bias there is nothing to deflate")
# The real assertion: 1000 trials must produce a stricter test than 10 trials.
d10 = S.deflated_sharpe(P, 10, [0.05 * i / 10.0 for i in range(10)])
d1000 = S.deflated_sharpe(P, 1000, [0.05 * i / 10.0 for i in range(10)])
check(d1000["sr0"] > d10["sr0"] > 0, "SR* grows with the trial count",
      (d10["sr0"], d1000["sr0"]))
check(d1000["dsr"] < d10["dsr"], "the same track record deflates with more trials")

# ---------------------------------------------------------------------------
# 6. Random-entry benchmark
# ---------------------------------------------------------------------------
real = [5.0, -2.0, 5.0, -2.0, 5.0]
benches = [[1.0, -2.0, 1.0, -2.0, 1.0], [0.0, 0.0, 0.0, 0.0, 0.0]]
bm = S.benchmark(real, benches)
check(bm["p_value"] == (1.0 + 0) / (1.0 + 2), "p = (1+beaten)/(1+N) with no benchmark better",
      bm["p_value"])
bm2 = S.benchmark([1.0], [[10.0], [20.0]])
check(bm2["p_value"] == 1.0 and bm2["beat_or_equal"] == 2,
      "a benchmark that beats the real system yields p = 1")
try:
    S.benchmark([1.0], [], metric="net_profit")
    check(False, "benchmark rejects an empty random set")
except ValueError:
    check(True, "benchmark rejects an empty random set")

# ---------------------------------------------------------------------------
# 7. Walk-forward aggregation
# ---------------------------------------------------------------------------
windows = [
    {"name": "w1", "is_net_profit": 1000.0, "oos_net_profit": 500.0,
     "params": {"a": 10, "b": 2}},
    {"name": "w2", "is_net_profit": 1000.0, "oos_net_profit": 600.0,
     "params": {"a": 10, "b": 2}},
    {"name": "w3", "is_net_profit": 500.0, "oos_net_profit": -100.0,
     "params": {"a": 12, "b": 3}},
    {"name": "w4", "is_net_profit": -200.0, "oos_net_profit": 100.0,
     "params": {"a": 14, "b": 4}},
]
wf = S.walk_forward(windows)
check(close(wf["wfe_aggregate"], 1100.0 / 2300.0),
      "aggregate WFE = sum(OOS) / sum(IS)", wf["wfe_aggregate"])
check(wf["wfe_aggregate"] == wf["wfe_aggregate"], "aggregate WFE is a number, not NaN")
check(wf["profitable_windows"] == 3 and wf["oos_windows"] == 4,
      "profitable OOS windows are counted, not averaged")
check(wf["profitable_frac"] == 0.75, "profitable fraction is reported")
check(wf["windows"][3]["wfe"] is None and wf["loss_making_is_windows"] == 1,
      "a loss-making IS window has no WFE and is flagged, not silently dropped")
check(close(wf["wfe_median"], 0.5), "median per-window WFE ignores the loss-making IS window",
      wf["wfe_median"])
check(wf["stability"]["a"]["relative_spread"] > 0, "parameter drift is measured per axis")
check(close(wf["stability"]["a"]["relative_spread"], (14 - 10) / 11.5, 1e-9),
      "relative spread = range / mean", wf["stability"]["a"]["relative_spread"])
check(close(wf["oos_curve"][-1]["cumulative"], 1100.0), "the stitched OOS curve sums the windows")

# ---------------------------------------------------------------------------
# 8. Plateau selection refuses an isolated spike
# ---------------------------------------------------------------------------
def grid_rows(spike=False):
    rows = []
    for x in range(7):
        for y in range(7):
            v = 1000.0 - 40.0 * (x - 3) ** 2 - 30.0 * (y - 3) ** 2
            if spike and (x, y) == (0, 0):
                v = 999999.0
            rows.append({"px": float(x), "py": float(y), "net_profit": v,
                         "trades": 200.0})
    return rows


clean = grid_rows()
pl = S.plateau(clean, ["px", "py"], k=4)
check(pl["chosen"]["params"] == {"px": 3.0, "py": 3.0},
      "on a symmetric bowl the centre of the plateau is chosen", pl["chosen"]["params"])
check(pl["chosen_is_peak"] is True, "when the peak IS the plateau centre, the two agree")

spiked = grid_rows(spike=True)
pl2 = S.plateau(spiked, ["px", "py"], k=4)
check(pl2["peak"]["score"] == 999999.0, "the spike is still reported as the peak row")
check(not pl2["chosen_is_peak"], "the spike is NOT chosen")
check(pl2["chosen"]["params"] == {"px": 3.0, "py": 3.0},
      "the recommendation ignores a 1000x outlier three axes away",
      pl2["chosen"]["params"])
check(pl2["chosen"]["neighbour_median"] > pl2["peak"]["neighbour_median"],
      "the plateau centre has a better neighbourhood than the spike")

try:
    S.plateau([dict(r, trades=5.0) for r in clean], ["px", "py"], min_trades=100)
    check(False, "min_trades filters out an entire grid")
except ValueError:
    check(True, "min_trades filters out an entire grid (explicit error, no silent pass)")

pert = S.perturbation_report(clean, ["px", "py"], {"px": 3.0, "py": 3.0})
check(pert["params"]["px"]["tested_min"] == 2.0 and pert["params"]["px"]["tested_max"] == 4.0,
      "perturbation looks exactly one grid step each way", pert["params"]["px"])
check(pert["params"]["px"]["score_min"] > 0, "one step away from the plateau is still positive")

hm = S.heatmap_rows(spiked, "px", "py")
check(hm["grid"][0][0] == 999999.0 and len(hm["x"]) == 7 and len(hm["y"]) == 7,
      "heatmap collapses the grid onto the requested axes")
check("columns = px" in S.render_heatmap(hm), "heatmap text names its axes")

# ---------------------------------------------------------------------------
# 9. Gates: a missing measurement is never a PASS
# ---------------------------------------------------------------------------
gates = S.build_gates({"trades_stats": S.trade_stats(P), "selection": {"a": 1}})
statuses = {g["gate"]: g["status"] for g in gates}
check(statuses.get("walk-forward efficiency") == "FAIL",
      "no WFE supplied => FAIL, not an optimistic default", statuses)
check(statuses.get("deflated Sharpe ratio") == "FAIL",
      "no trial count => DSR gate FAILs loudly")
check(statuses.get("sample size") == "FAIL", "5 trades cannot pass a 100-trade gate")

good = S.trade_stats([100.0] * 70 + [-80.0] * 30, 10000.0)
statuses2 = {g["gate"]: g["status"] for g in S.build_gates(
    {"trades_stats": good, "selection": {"a": 1, "b": 2},
     "wfa": S.walk_forward(windows)})}
check(statuses2["sample size"] == "PASS" and statuses2["profit factor in range"] == "PASS",
      "a 400-trade, PF 2.9 sample passes the sample and factor gates", statuses2)

# ---------------------------------------------------------------------------
# 10. End-to-end study + CLI exit codes
# ---------------------------------------------------------------------------
TMP = tempfile.mkdtemp(prefix="wfa_test_")
try:
    write(os.path.join(TMP, "trades.csv"),
          "time,profit\n" + "".join("2024-01-01 00:00:00,%s\n"
                                    % ("100.0" if i % 10 < 7 else "-80.0")
                                    for i in range(400)))
    grid_csv = ["InpA,InpB,Profit,Trades,Profit Factor"]
    for x in range(5):
        for y in range(5):
            v = 1000.0 - 30.0 * (x - 2) ** 2 - 20.0 * (y - 2) ** 2
            grid_csv.append("%d,%d,%.2f,200,%.2f" % (x, y + 1, v, 1.0 + v / 10000.0))
    write(os.path.join(TMP, "grid.csv"), "\n".join(grid_csv) + "\n")
    os.makedirs(os.path.join(TMP, "bench"), exist_ok=True)
    benches = []
    for i in range(25):
        rel = "bench/b%d.csv" % i
        benches.append(rel)
        write(os.path.join(TMP, rel),
              "profit\n" + "".join("%s\n" % (5 if (i + j) % 2 else -6) for j in range(400)))

    good_windows = [
        {"name": "w1", "is_net_profit": 600.0, "oos_net_profit": 500.0,
         "params": {"InpA": 2, "InpB": 3}},
        {"name": "w2", "is_net_profit": 600.0, "oos_net_profit": 600.0,
         "params": {"InpA": 2, "InpB": 3}},
        {"name": "w3", "is_net_profit": 500.0, "oos_net_profit": 300.0,
         "params": {"InpA": 2, "InpB": 3}},
        {"name": "w4", "is_net_profit": 400.0, "oos_net_profit": 200.0,
         "params": {"InpA": 2, "InpB": 3}},
    ]
    manifest = {
        "label": "test study",
        "trades": "trades.csv",
        "selection": {"InpA": 2, "InpB": 3},
        "plateau": {"runs": "grid.csv", "params": ["InpA", "InpB"], "min_trades": 100,
                    "heatmap": ["InpA", "InpB"]},
        "windows": good_windows,
        "benchmarks": benches,
        "mc": {"iterations": 200, "seed": 4},
        "cost_stress": {"extra_cost_per_trade": 1.0},
        "trials": 25,
        "trial_sharpe_sd": 0.05,
    }
    write(os.path.join(TMP, "study.json"), json.dumps(manifest, indent=2))
    out_md = os.path.join(TMP, "report.md")
    rc = S.main(["report", "--manifest", os.path.join(TMP, "study.json"),
                 "--out", out_md, "--date", "2026-01-01"])
    text = io.open(out_md, encoding="utf-8").read() if os.path.exists(out_md) else ""
    check(rc == 0, "a study that clears every gate exits 0", rc)
    check("## Verdict: **GO" in text, "the report states a verdict up front")
    check("What this report does not prove" in text,
          "the report carries its own limitations section")
    check("| gate | measured | threshold | verdict |" in text, "gate table is rendered")

    # Counting trials without supplying their dispersion deflates nothing.
    # The gate must say so instead of reporting the strictest-looking pass.
    undispersed = dict(manifest)
    undispersed.pop("trial_sharpe_sd")
    write(os.path.join(TMP, "study_undispersed.json"), json.dumps(undispersed))
    rc_und = S.main(["report", "--manifest", os.path.join(TMP, "study_undispersed.json"),
                     "--out", os.path.join(TMP, "und.md"), "--date", "2026-01-01"])
    und_text = io.open(os.path.join(TMP, "und.md"), encoding="utf-8").read()
    check(rc_und == 1 and "no trial-Sharpe dispersion supplied" in und_text,
          "trials without dispersion FAIL the DSR gate with an explanation", rc_und)

    hard = S.deflated_sharpe([20.0] * 60 + [-20.0] * 40, 5000,
                             [0.01 * i for i in range(50)])
    hard_none = S.deflated_sharpe([20.0] * 60 + [-20.0] * 40, 5000)
    check(hard["sr0"] > hard_none["sr0"] == 0.0,
          "a supplied dispersion produces a hurdle; its absence produces zero")

    manifest["cost_stress"] = {"extra_cost_per_trade": 100.0}
    write(os.path.join(TMP, "study_bad.json"), json.dumps(manifest, indent=2))
    rc_bad = S.main(["report", "--manifest", os.path.join(TMP, "study_bad.json"),
                     "--out", os.path.join(TMP, "bad.md"), "--date", "2026-01-01"])
    check(rc_bad == 1, "a study that fails a gate exits 1", rc_bad)

    check(S.main(["mc", "--trades", os.path.join(TMP, "nope.csv")]) == 2,
          "a missing input file is an input error (exit 2), not a pass")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

# ---------------------------------------------------------------------------
# 11. Harness: planning arithmetic and its refusals
# ---------------------------------------------------------------------------
check(H.add_months(H.parse_date("2024-01-31"), 1).isoformat() == "2024-02-29",
      "month arithmetic clamps to the end of a month")
check(H.add_months(H.parse_date("2024-01-15"), -1).isoformat() == "2023-12-15",
      "negative month arithmetic crosses the year boundary")

plan = H.build_plan("2018-01-01", "2026-01-01", 24, 6, holdout_months=12)
check(len(plan["windows"]) == 10, "10 windows fit 2018-2025 with 24/6", len(plan["windows"]))
check(plan["holdout"] == {"start": "2025-01-01", "end": "2026-01-01"},
      "the holdout is the last 12 months, untouched", plan["holdout"])
check(plan["windows"][0]["oos_start"] == plan["windows"][0]["is_end"],
      "OOS starts exactly where IS ends")
check(plan["windows"][1]["oos_start"] == plan["windows"][0]["oos_end"],
      "OOS segments are contiguous: no month is traded twice")
check(all(w["oos_end"] <= plan["holdout"]["start"] for w in plan["windows"]),
      "no window reaches into the holdout")
check(H.parse_date(plan["windows"][-1]["oos_end"]) <= H.parse_date(plan["holdout"]["start"]),
      "the last OOS window stops at the holdout boundary")

for kwargs, label in (
        ({"step_months": 3, "holdout_months": 0}, "a step shorter than the OOS block"),
        ({"holdout_months": -1}, "a negative holdout"),
        ({"is_months": 0, "holdout_months": 0}, "a zero-length IS window")):
    try:
        H.build_plan("2020-01-01", "2026-01-01", kwargs.pop("is_months", 24), 6, **kwargs)
        check(False, "plan rejects %s" % label)
    except ValueError:
        check(True, "plan rejects %s" % label)
try:
    H.build_plan("2025-01-01", "2026-01-01", 24, 6)
    check(False, "plan rejects a range shorter than one IS window")
except ValueError:
    check(True, "plan rejects a range shorter than one IS window")
try:
    H.build_plan("2026-01-01", "2018-01-01", 24, 6)
    check(False, "plan rejects a reversed range")
except ValueError:
    check(True, "plan rejects a reversed range")

warns = H.plan_warnings(H.build_plan("2024-01-01", "2025-07-01", 12, 6), 0)
check(any("holdout" in w for w in warns), "the planner complains when no holdout is reserved")
check(any("OOS window" in w for w in warns), "the planner complains about too few windows")

# ---------------------------------------------------------------------------
# 12. Harness: parameter spec validation
# ---------------------------------------------------------------------------
spec = H.normalise_params([
    {"name": "InpA", "start": 10, "step": 2, "stop": 20, "optimize": True},
    {"name": "InpB", "value": 2.0},
    {"name": "InpOn", "value": "false"},
])
check(spec[0]["value"] == 10 and spec[0]["optimize"] is True,
      "an optimised parameter defaults its value to the grid start")
check(spec[2]["value"] == "false", "a non-optimised boolean input keeps its text value")
check(H.grid_size(spec) == 6, "grid size is the product of the optimised ranges",
      H.grid_size(spec))
mapped = H.normalise_params({"InpA": {"start": 1, "step": 1, "stop": 3,
                                      "optimize": True}})
check(mapped[0]["name"] == "InpA", "a mapping spec is accepted as well as a list")
for bad, label in (
        ([{"name": "InpA", "start": 1, "step": 0, "stop": 5, "optimize": True}],
         "an optimised parameter with step 0"),
        ([{"name": "InpA", "start": 5, "step": 1, "stop": 1, "optimize": True}],
         "a grid whose start exceeds its stop"),
        ([{"name": "InpA", "value": 1}, {"name": "InpA", "value": 2}],
         "duplicate input names"),
        ([{"name": "1bad", "value": 1}], "an input name that is not an identifier"),
        ([{"value": 1}], "a parameter without a name")):
    try:
        H.normalise_params(bad)
        check(False, "spec rejects %s" % label)
    except ValueError:
        check(True, "spec rejects %s" % label)
check(any("free parameters" in w for w in H.param_warnings(
    H.normalise_params([{"name": "P%d" % i, "start": 1, "step": 1, "stop": 9,
                         "optimize": True} for i in range(8)]))),
    "more than six free parameters produces a warning")

# The EA ships inert; a tester run needs its own arming inputs, and the harness
# must say so instead of emitting a report full of zero trades.
inert = H.normalise_params([{"name": "InpEnableTrading", "value": "false"},
                            {"name": "InpDryRun", "value": "true"}])
check(len(H.safety_warnings("QSMC_AutoTrader", inert)) == 2,
      "an inert EA spec warns that the tester will record zero trades")
armed = H.normalise_params([{"name": "InpEnableTrading", "value": "true"},
                            {"name": "InpDryRun", "value": "false"}])
check(H.safety_warnings("QSMC_AutoTrader", armed) == [],
      "an armed backtest spec is accepted without noise")
check(H.safety_warnings("SomeoneElsesEA", inert) == [],
      "the QSMC arming rule does not leak onto other experts")

# ---------------------------------------------------------------------------
# 13. Harness: the emitted MT5 files
# ---------------------------------------------------------------------------
params = H.normalise_params([
    {"name": "InpRsiPeriod", "start": 10, "step": 2, "stop": 22, "optimize": True},
    {"name": "InpAtrMult", "start": 1.5, "step": 0.5, "stop": 3.0, "optimize": True},
    {"name": "InpEnableTrading", "value": "false"},
])
opt_set = H.render_set(params)
check("InpRsiPeriod=10||10||2||22||Y" in opt_set, "the optimisation .set carries the grid")
check("InpEnableTrading=false||false||0||false||N" in opt_set,
      "a non-optimised input is written with flag N")
oos_set = H.render_set(params, optimize_grid=False)
check("||Y" not in oos_set, "an OOS .set contains NO optimisation flag")
check("InpRsiPeriod=10||10||0||10||N" in oos_set,
      "an OOS .set collapses every input to a single value")

ini = H.render_ini("QSMC_AutoTrader", "w01_opt.set", "XAUUSD", "H1",
                   "2018.01.01", "2020.01.01", 4, 2, 5, 10000.0, "USD", "1:100",
                   "w01_opt_report")
for needle in ("[Tester]", "Expert=QSMC_AutoTrader", "ExpertParameters=w01_opt.set",
               "Symbol=XAUUSD", "Period=H1", "Model=4", "Optimization=2",
               "OptimizationCriterion=5", "FromDate=2018.01.01",
               "ToDate=2020.01.01", "ShutdownTerminal=1", "Leverage=1:100"):
    check(needle in ini, "ini contains %s" % needle)
check("OptimizationCriterion" not in H.render_ini(
    "E", "s.set", "XAUUSD", "H1", "2020.01.01", "2020.07.01", 4, 1, 5, 10000.0,
    "USD", "1:100", "rep"),
    "a single-pass (OOS) ini has no optimisation criterion")

tf_tmp = tempfile.mkdtemp(prefix="wfa_tf_")
try:
    H.emit_configs(plan, params, tf_tmp, "E", "XAUUSD", "H7")
    check(False, "an unknown timeframe is rejected")
except ValueError:
    check(True, "an unknown timeframe is rejected")
finally:
    shutil.rmtree(tf_tmp, ignore_errors=True)

tmp2 = tempfile.mkdtemp(prefix="wfa_harness_")
try:
    manifest = H.emit_configs(plan, params, tmp2, "QSMC_AutoTrader", "XAUUSD", "H1",
                              terminal=r"C:\MT5\terminal64.exe")
    expect = ["manifest.json", "plan.json", "CONFIGS.md", "run_all.ps1", "run_all.sh",
              "w01_opt.ini", "w01_opt.set", "w01_oos.ini", "w01_oos.set",
              "w10_opt.ini", "w10_oos.ini"]
    missing = [f for f in expect if not os.path.exists(os.path.join(tmp2, f))]
    check(not missing, "every promised file is written", missing)
    check(manifest["grid_size"] == 28, "grid size is reported in the manifest",
          manifest["grid_size"])
    check(len(manifest["files"]) == 2 * len(plan["windows"]),
          "two passes per window are configured")
    oos_file = io.open(os.path.join(tmp2, "w01_oos.set"), encoding="utf-8").read()
    check("||Y" not in oos_file, "the generated OOS .set refuses to carry a range")
    check("NOT APPLIED YET" in oos_file, "an unfrozen OOS .set says so out loud")
    ini_text = io.open(os.path.join(tmp2, "w01_opt.ini"), encoding="utf-8").read()
    check("FromDate=%s" % H.mt5_date(H.parse_date(plan["windows"][0]["is_start"])) in ini_text,
          "the optimisation pass is bounded by the IS dates only")
    ps1 = io.open(os.path.join(tmp2, "run_all.ps1"), encoding="utf-8").read()
    check("$Terminal = 'C:\\MT5\\terminal64.exe'" in ps1,
          "the PowerShell runner quotes the path without doubling backslashes")
    check(ps1.count("/config:") == 2 * len(plan["windows"]),
          "the runner invokes every pass exactly once")
    check("Terminal" in ps1 and "terminal64" in ps1, "the runner knows its terminal")

    sel = {"w01": {"InpRsiPeriod": 18, "InpAtrMult": 2.5}, "w10": {"InpRsiPeriod": 14}}
    written = H.apply_selection(plan, params, sel, tmp2)
    frozen = io.open(os.path.join(tmp2, "w01_oos.set"), encoding="utf-8").read()
    check("InpRsiPeriod=18||18||0||18||N" in frozen,
          "apply freezes the chosen value into the OOS set", frozen)
    check("NOT APPLIED YET" not in frozen, "the applied set drops the warning")
    check(written[1]["unset"] == ["InpAtrMult", "InpEnableTrading"],
          "unset inputs are reported, not invented", written[1]["unset"])
    global_sel = {"chosen": {"params": {"InpRsiPeriod": 16, "InpAtrMult": 2.0}}}
    H.apply_selection(plan, params, global_sel, tmp2)
    check(close(H.to_number("16"), 16.0), "harness keeps its own number parser")
    try:
        H.apply_selection(plan, params, {"w01": {"NotAnInput": 1}}, tmp2)
        check(False, "apply rejects an unknown input name")
    except ValueError:
        check(True, "apply rejects an unknown input name")
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

# ---------------------------------------------------------------------------
# 14. Ingest: every export shape lands on the same numbers
# ---------------------------------------------------------------------------
tmp3 = tempfile.mkdtemp(prefix="wfa_ingest_")
try:
    write(os.path.join(tmp3, "attrs.xml"),
          '<O><Row InpA="14" Profit="1 234.56" Trades="240" ProfitFactor="1.42"/>\n'
          '<Row InpA="16" Profit="2 010.10" Trades="301" ProfitFactor="1.61"/></O>')
    write(os.path.join(tmp3, "children.xml"),
          "<R><Run><InpA>14</InpA><Profit>1234.56</Profit><Trades>240</Trades></Run>"
          "<Run><InpA>16</InpA><Profit>2010.10</Profit><Trades>301</Trades></Run></R>")
    write(os.path.join(tmp3, "cells.xml"),
          "<Report>"
          "<Row><Cell><Data>InpA</Data></Cell><Cell><Data>Profit</Data></Cell>"
          "<Cell><Data>Trades</Data></Cell></Row>"
          "<Row><Cell><Data>14</Data></Cell><Cell><Data>1234.56</Data></Cell>"
          "<Cell><Data>240</Data></Cell></Row>"
          "<Row><Cell><Data>16</Data></Cell><Cell><Data>2010.10</Data></Cell>"
          "<Cell><Data>301</Data></Cell></Row></Report>")
    write(os.path.join(tmp3, "locale.csv"),
          "Profit;InpA;Trades\n1 234,56;14;240\n2 010,10;16;301\n")

    for name in ("attrs.xml", "children.xml", "cells.xml", "locale.csv"):
        tidy = H.tidy_table(os.path.join(tmp3, name))
        rows = tidy["rows"]
        ok = (len(rows) == 2
              and abs((rows[0]["net_profit"] or 0) - 1234.56) < 1e-6
              and abs((rows[1]["net_profit"] or 0) - 2010.10) < 1e-6
              and rows[1]["trades"] == 301
              and "net_profit" in tidy["metrics"])
        check(ok, "%s normalises to the same numbers" % name, rows[:1])

    check("profit_factor" in H.tidy_table(os.path.join(tmp3, "attrs.xml"))["metrics"],
          "camelCase attribute names are recognised as metrics (ProfitFactor)")
    rc = H.main(["ingest", "--input", tmp3, "--out", os.path.join(tmp3, "tidy") + os.sep])
    produced = sorted(os.listdir(os.path.join(tmp3, "tidy"))) if rc == 0 else []
    check(rc == 0 and len(produced) == 4, "directory ingest writes one tidy CSV per file",
          produced)
    check(H.to_number("1.234,56") == 1234.56 and H.to_number("x") is None,
          "harness number parsing handles grouping and refuses text")
finally:
    shutil.rmtree(tmp3, ignore_errors=True)

# ---------------------------------------------------------------------------
# 15. Harness CLI: bad input is an input error, never a pass
# ---------------------------------------------------------------------------
tmp4 = tempfile.mkdtemp(prefix="wfa_cli_")
try:
    rc = H.main(["plan", "--from", "2018-01-01", "--to", "2026-01-01",
                 "--is-months", "24", "--oos-months", "6",
                 "--holdout-months", "12", "--out", tmp4])
    check(rc == 0 and os.path.exists(os.path.join(tmp4, "plan.json")),
          "the planner CLI writes plan.json")
    check(H.main(["plan", "--from", "2018-01-01", "--to", "2020-01-01",
                  "--is-months", "24", "--oos-months", "12", "--out", tmp4]) == 2,
          "an impossible plan exits 2")
    check(H.main(["configs", "--plan", os.path.join(tmp4, "plan.json"),
                  "--params", os.path.join(tmp4, "missing.json"),
                  "--out", os.path.join(tmp4, "cfg")]) == 2,
          "a missing parameter file exits 2")
finally:
    shutil.rmtree(tmp4, ignore_errors=True)

# ---------------------------------------------------------------------------
# 16. The synthetic demo: reproducible, honest about being fake, still NO-GO
# ---------------------------------------------------------------------------
demo_dir = tempfile.mkdtemp(prefix="wfa_demo_")
try:
    rc = D.main(["--out", demo_dir, "--iterations", "150", "--benchmarks", "20",
                 "--quiet"])
    report_path = os.path.join(demo_dir, "report.md")
    first = io.open(report_path, encoding="utf-8").read() if os.path.exists(report_path) else ""
    check(rc == 0 and report_path and first, "the demo runs end to end")
    check(first.startswith("# Walk-forward robustness report — SYNTHETIC STUDY"),
          "the demo's report announces itself as synthetic on line 1")
    check("## Verdict: **NO-GO**" in first,
          "the demo produces the expected NO-GO (a clean GO would mean the gates moved)")
    check("| score (net_profit) | 900000.00 |" in first and "chosen == peak row: **False**" in first,
          "the demo's deliberate spike is reported as the peak and refused as the choice")
    check("InpAtrMult=2.0" in first and "InpRsiPeriod=16.0" in first,
          "the demo's plateau centre is the interior maximum, not the corner spike")
    check(len(D.make_trades(7)) == 420, "the demo's trade generator is sized as documented")
    D.main(["--out", demo_dir, "--iterations", "150", "--benchmarks", "20", "--quiet"])
    second = io.open(report_path, encoding="utf-8").read()
    check(first == second, "two runs with the same seed produce a byte-identical report")
finally:
    shutil.rmtree(demo_dir, ignore_errors=True)

if FAILS:
    print("%d of %d robustness test(s) failed" % (len(FAILS), COUNT[0]))
    raise SystemExit(1)
print("%d robustness checks passed; these test the arithmetic, not an edge." % COUNT[0])
