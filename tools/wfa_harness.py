#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WFA-HARNESS - turn a discipline into a repeatable MT5 workflow.

WHY THIS EXISTS
---------------
Walk-forward analysis is easy to describe and easy to do dishonestly. The
dishonest version is a folder of optimisation reports, a spreadsheet, and a
human who "picks the parameter set that looks most stable" after seeing all the
out-of-sample windows. That is not walk-forward analysis; it is optimisation
with extra steps, and the OOS result is contaminated by the choice.

This harness removes the human from the loop where the human is the leak:

  plan         fixed, contiguous IS/OOS windows from ONE date range, with the
               final holdout sliced off before anything else happens.
  configs      one MT5 tester .ini + .set per window per pass - the optimisation
               pass over IS, the single-pass evaluation over OOS - plus the
               scripts that run them in order. Nothing is hand-edited later.
  ingest       the terminal's own exports become a tidy CSV the stats engine
               understands (MT5 writes numbers with locale separators; that is
               a parsing problem, not a judgement call).
  apply        the parameter set chosen from the IS surface is written into the
               OOS .set mechanically, so "the parameters I used for OOS" is a
               file with a timestamp, not a memory.

WHAT IT CANNOT DO
-----------------
  * It cannot compile MQL5. F7 in MetaEditor is still a human step.
  * It cannot run here: the terminal is Windows software and this sandbox has
    no MetaTrader. `configs` writes the files and the runner; the operator runs
    them. Nothing in this file launches a process.
  * It cannot make an optimisation honest by itself. If you look at the OOS
    window, change a parameter and look again, no tool will save you - the
    only defence is that the workflow makes the extra look visible.

MT5 FILE FORMAT NOTES (verified against the terminal's documented config keys,
not against a live terminal from this sandbox - say so in your own audit)
-------------------------------------------------------------------------
  * `[Tester]` keys used here: Expert, ExpertParameters, Symbol, Period, Model,
    Optimization, OptimizationCriterion, FromDate, ToDate, ForwardMode, Deposit,
    Currency, Leverage, Visual, ShutdownTerminal, Report, ReplaceReport.
  * Dates are written `YYYY.MM.DD`.
  * Model: 0 every tick, 1 1-minute OHLC, 2 open prices, 3 math, 4 every tick
    based on REAL ticks. For a system with intra-bar stops, 4 is the only model
    that can be taken seriously; 1 and 2 will flatter it.
  * A `.set` line is `Name=value||start||step||stop||Y|N`. For a value that is
    not being optimised, MT5 writes `Name=value||value||0||value||N`.
  * If a build ignores `ExpertParameters`, the fallback is the `[TesterInputs]`
    block written next to each ini as `<window>_opt.testerinputs.txt`.

Exit codes: 0 = ok, 2 = bad input or a plan that cannot be run.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

VALID_PERIODS = ("M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20",
                 "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1")

MODELS = {0: "every tick", 1: "1 minute OHLC", 2: "open prices only",
          3: "math calculations", 4: "every tick based on real ticks"}

CRITERIA = {0: "balance max", 1: "balance + max profit factor",
            2: "balance + max expected payoff", 3: "balance + min drawdown",
            4: "balance + max recovery factor", 5: "balance + max Sharpe",
            6: "custom max (OnTester)"}

MIN_WINDOWS_WARN = 5
MAX_FREE_PARAMS_WARN = 6


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def parse_date(text: str) -> dt.date:
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(str(text).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError("unparseable date %r (use YYYY-MM-DD)" % (text,))


def add_months(d: dt.date, months: int) -> dt.date:
    """Calendar-month arithmetic with end-of-month clamping."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def mt5_date(d: dt.date) -> str:
    return d.strftime("%Y.%m.%d")


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def build_plan(date_from, date_to, is_months: int, oos_months: int,
               step_months: int = None, holdout_months: int = 0,
               label: str = "") -> dict:
    """Rolling IS/OOS windows with the holdout removed BEFORE windowing.

    The order matters. Compute the holdout boundary first, then pack windows
    inside what is left, so no window can ever overlap the holdout - the most
    common way a "holdout" quietly becomes training data.

    Step defaults to the OOS length, giving contiguous, non-overlapping OOS
    segments: window i+1 starts exactly where window i stopped trading. A step
    shorter than the OOS length would make the stitched curve double-count time
    (still valid as a robustness view, invalid as a track record), so a shorter
    step is rejected rather than warned about.
    """
    start = parse_date(date_from)
    end = parse_date(date_to)
    step = oos_months if step_months is None else step_months
    if is_months <= 0 or oos_months <= 0 or step <= 0:
        raise ValueError("is-months, oos-months and step-months must all be > 0")
    if holdout_months < 0:
        raise ValueError("holdout-months cannot be negative")
    if step < oos_months:
        raise ValueError("step-months (%d) < oos-months (%d) would overlap OOS "
                         "segments and double-count time" % (step, oos_months))
    if start >= end:
        raise ValueError("--from must be before --to")

    usable_end = add_months(end, -holdout_months) if holdout_months else end
    holdout = None
    if holdout_months:
        holdout = {"start": usable_end.isoformat(), "end": end.isoformat()}
    if add_months(start, is_months) > usable_end:
        raise ValueError("the data range is shorter than one IS window (%d months)"
                         % is_months)

    windows = []
    i = 0
    while True:
        is_start = add_months(start, i * step)
        is_end = add_months(is_start, is_months)
        oos_start = is_end
        oos_end = add_months(oos_start, oos_months)
        if oos_end > usable_end:
            break
        windows.append({
            "id": "w%02d" % (i + 1),
            "index": i,
            "is_start": is_start.isoformat(),
            "is_end": is_end.isoformat(),
            "oos_start": oos_start.isoformat(),
            "oos_end": oos_end.isoformat(),
            "is_days": (is_end - is_start).days,
            "oos_days": (oos_end - oos_start).days,
        })
        i += 1
        if i > 1000:
            raise ValueError("plan produced more than 1000 windows; check inputs")

    if not windows:
        raise ValueError("no complete window fits: %d months of data, %d IS + "
                         "%d OOS months required"
                         % ((usable_end.year - start.year) * 12 +
                            (usable_end.month - start.month), is_months, oos_months))

    covered = (parse_date(windows[-1]["oos_end"]) - start).days
    total = (usable_end - start).days
    plan = {
        "label": label or "%s to %s" % (start.isoformat(), usable_end.isoformat()),
        "from": start.isoformat(),
        "to": usable_end.isoformat(),
        "requested_to": end.isoformat(),
        "is_months": is_months,
        "oos_months": oos_months,
        "step_months": step,
        "holdout": holdout,
        "windows": windows,
        "coverage": {"used_days": covered, "available_days": total,
                     "fraction": covered / float(total) if total else 0.0},
    }
    return plan


def plan_warnings(plan: dict, n_free_params: int = 0) -> list:
    """Discipline warnings - things a careful operator would want to hear."""
    out = []
    n = len(plan["windows"])
    if n < MIN_WINDOWS_WARN:
        out.append("%d OOS window(s): fewer than %d means one good month can "
                   "carry the whole walk-forward. Lengthen the range or shorten "
                   "the OOS block." % (n, MIN_WINDOWS_WARN))
    if plan["coverage"]["fraction"] < 0.85:
        out.append("only %.0f%% of the range is inside a window; the tail is "
                   "unused" % (100 * plan["coverage"]["fraction"]))
    if not plan.get("holdout"):
        out.append("no holdout reserved: you will have nothing left that has "
                   "been looked at exactly once")
    if n_free_params > MAX_FREE_PARAMS_WARN:
        out.append("%d parameters are being optimised; above %d the search finds "
                   "noise faster than it finds edge"
                   % (n_free_params, MAX_FREE_PARAMS_WARN))
    if n_free_params:
        need = n_free_params * 30
        out.append("30 trades per free parameter means about %d stitched OOS "
                   "trades are needed; count them after the run, not before"
                   % need)
    return out


# ---------------------------------------------------------------------------
# Parameter specification
# ---------------------------------------------------------------------------

def normalise_params(spec) -> list:
    """Accept a list of param dicts or a {name: {...}} mapping.

    Each parameter becomes {name, value, start, step, stop, optimize}. A missing
    `value` defaults to `start`, which is the IS-grid lower bound - never a
    "best" number taken from a previous run.
    """
    items = []
    if isinstance(spec, dict):
        if "params" in spec and isinstance(spec["params"], list):
            spec = spec["params"]
        else:
            for name, cfg in spec.items():
                cfg = dict(cfg) if isinstance(cfg, dict) else {"value": cfg}
                cfg.setdefault("name", name)
                items.append(cfg)
            spec = items
    if not isinstance(spec, list) or not spec:
        raise ValueError("params must be a non-empty list or mapping")
    out = []
    for entry in spec:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError("each parameter needs a 'name': %r" % (entry,))
        name = str(entry["name"]).strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError("invalid MT5 input name %r" % (name,))
        val = entry.get("value", entry.get("start"))
        if val is None:
            raise ValueError("parameter %s has no value or start" % name)
        start = entry.get("start", val)
        stop = entry.get("stop", val)
        step = entry.get("step", 0)
        step = 0 if step in (None, "") else step
        opt = bool(entry.get("optimize", entry.get("optimise", False)))
        # A non-optimised input may legitimately carry a non-numeric value
        # (`InpEnableTrading=false`, an enum `QSMC_LOT_RISK_PERCENT`, a symbol
        # string). Only the optimisation range must be numeric, and a value only
        # has to be numeric when it is also the start of a numeric grid.
        numeric_checks = ([("value", val), ("start", start), ("stop", stop),
                           ("step", step)] if opt else [])
        for label, num in numeric_checks:
            try:
                float(num)
            except (TypeError, ValueError):
                raise ValueError("parameter %s: %s=%r is not numeric"
                                 % (name, label, num))
        if opt:
            if float(step) <= 0:
                raise ValueError("parameter %s is optimised but step=%r; a "
                                 "zero step means one value, not a grid"
                                 % (name, step))
            if float(start) > float(stop):
                raise ValueError("parameter %s: start > stop" % name)
        out.append({"name": name, "value": val, "start": start, "step": step,
                    "stop": stop, "optimize": opt})
    names = [p["name"] for p in out]
    if len(set(names)) != len(names):
        raise ValueError("duplicate parameter names: %s" % ", ".join(names))
    return out


def param_warnings(params) -> list:
    out = []
    opt = [p for p in params if p["optimize"]]
    if not opt:
        out.append("no parameter is marked optimize:true - the IS pass will be a "
                   "single run, and 'optimisation surface' will be empty")
    if len(opt) > MAX_FREE_PARAMS_WARN:
        out.append("%d free parameters; every extra axis multiplies the number "
                   "of ways to fit noise" % len(opt))
    for p in opt:
        lo, hi, st = float(p["start"]), float(p["stop"]), float(p["step"])
        steps = int(round((hi - lo) / st)) + 1
        if steps < 3:
            out.append("%s has %d grid values; a plateau cannot be seen in 2"
                       % (p["name"], steps))
        if steps > 60:
            out.append("%s has %d grid values - widen the step or accept a "
                       "search nobody can explain" % (p["name"], steps))
    total = 1
    for p in opt:
        total *= int(round((float(p["stop"]) - float(p["start"]))
                           / float(p["step"]))) + 1
    if total > 20000:
        out.append("the full grid is %d combinations; count every one of them as "
                   "a trial when you deflate the Sharpe ratio" % total)
    return out


def safety_warnings(expert: str, params) -> list:
    """Repo-specific trap: this EA ships INERT.

    QSMC_AutoTrader defaults to InpEnableTrading=false, InpDryRun=true,
    InpDemoOnly=true. In the Strategy Tester those three mean the EA logs a
    beautiful explanation of why it did nothing, and the report shows zero
    trades - which, if you only look at the equity curve, looks like "no
    signal" rather than "no permission". A tester run therefore needs its OWN
    arming inputs, and arming them in a shared .set that later reaches a live
    chart is a catastrophic mistake. This warning exists so the arming set is a
    deliberate, visible act.
    """
    if "autotrader" not in str(expert).lower():
        return []
    vals = {p["name"]: str(p["value"]).strip().lower() for p in params
            if p["name"] in ("InpEnableTrading", "InpDryRun", "InpDemoOnly",
                             "InpRealAccountConfirm")}
    out = []
    if vals.get("InpEnableTrading") not in ("true", "1"):
        out.append("%s ships with InpEnableTrading=false: the tester will record "
                   "ZERO trades. Add it to the spec as value \"true\" for the "
                   "backtest .set only - never to a live preset." % expert)
    if vals.get("InpDryRun") not in ("false", "0"):
        out.append("InpDryRun is not false: orders would be journaled, not sent, "
                   "and the report would contain no trades")
    if vals.get("InpDemoOnly") in ("false", "0"):
        out.append("InpDemoOnly=false in a backtest spec is meaningless at best "
                   "and dangerous if the same .set is reused on a real account")
    return out


def grid_size(params) -> int:
    total = 1
    for p in params:
        if p["optimize"]:
            total *= int(round((float(p["stop"]) - float(p["start"]))
                               / float(p["step"]))) + 1
    return total


# ---------------------------------------------------------------------------
# MT5 config emission
# ---------------------------------------------------------------------------

def set_line(p, value=None) -> str:
    v = p["value"] if value is None else value
    if p["optimize"] and value is None:
        return "%s=%s||%s||%s||%s||Y" % (p["name"], v, p["start"], p["step"], p["stop"])
    return "%s=%s||%s||0||%s||N" % (p["name"], v, v, v)


def render_set(params, values=None, optimize_grid: bool = True,
               banner=None) -> str:
    """A .set file: one line per input, MT5's `value||start||step||stop||flag`.

    `optimize_grid=False` writes every input as a single value with flag N.
    That is the OOS pass: if the OOS .set still carried a range, the runner
    would silently re-optimise inside the out-of-sample window and the whole
    study would be invalid - exactly the mistake this flag exists to make
    impossible.
    """
    values = values or {}
    lines = []
    if banner:
        for line in banner.strip().splitlines():
            lines.append("; " + line.strip())
    for p in params:
        if p["name"] in values:
            v = values[p["name"]]
            lines.append("%s=%s||%s||0||%s||N" % (p["name"], v, v, v))
        elif not optimize_grid:
            v = p["value"]
            lines.append("%s=%s||%s||0||%s||N" % (p["name"], v, v, v))
        else:
            lines.append(set_line(p))
    return "\n".join(lines) + "\n"


def render_ini(expert: str, set_name: str, symbol: str, period: str,
               date_from: str, date_to: str, model: int, optimization: int,
               criterion: int, deposit: float, currency: str, leverage: str,
               report_name: str, forward_mode: int = 0,
               visual: bool = False, header_comment: str = "") -> str:
    L = []
    if header_comment:
        for line in header_comment.strip().splitlines():
            L.append("; " + line.strip())
    L.append("; generated by tools/wfa_harness.py - do not hand-edit; re-run the")
    L.append("; generator instead, so the file on disk matches the plan.")
    L.append("[Tester]")
    L.append("Expert=%s" % expert)
    L.append("ExpertParameters=%s" % set_name)
    L.append("Symbol=%s" % symbol)
    L.append("Period=%s" % period)
    L.append("Model=%d" % model)
    L.append("Optimization=%d" % optimization)
    if optimization > 1:
        L.append("OptimizationCriterion=%d" % criterion)
    L.append("FromDate=%s" % date_from)
    L.append("ToDate=%s" % date_to)
    L.append("ForwardMode=%d" % forward_mode)
    L.append("Deposit=%s" % ("%g" % deposit))
    L.append("Currency=%s" % currency)
    L.append("Leverage=%s" % leverage)
    L.append("Visual=%d" % (1 if visual else 0))
    L.append("ShutdownTerminal=1")
    L.append("Report=%s" % report_name)
    L.append("ReplaceReport=1")
    return "\n".join(L) + "\n"


def render_testerinputs(params, values=None) -> str:
    """The `[TesterInputs]` fallback block for builds that ignore a .set path."""
    values = values or {}
    L = ["[TesterInputs]"]
    for p in params:
        if p["name"] in values:
            L.append("%s=%s||%s||0||%s||N"
                     % (p["name"], values[p["name"]], values[p["name"]],
                        values[p["name"]]))
        else:
            L.append(set_line(p))
    return "\n".join(L) + "\n"


def render_runner(plan: dict, files: list, terminal: str, os_name: str) -> str:
    """A sequential runner. Serialise deliberately: parallel runs fight for the
    same terminal, the same history cache and the same CPU, and a half-run
    window is indistinguishable from a failed one."""
    if os_name == "windows":
        L = ["# generated by tools/wfa_harness.py",
             "# Run with MetaTrader CLOSED. Each config starts the terminal, runs",
             "# one pass, writes its report and exits (ShutdownTerminal=1).",
             "$ErrorActionPreference = 'Stop'",
             "$Terminal = '%s'" % terminal.replace("'", "''")]
        for f in files:
            L.append("Write-Host '=== %s ==='" % f["label"])
            L.append("& $Terminal '/config:%s'" % f["path"])
            L.append("if ($LASTEXITCODE -ne 0) "
                     "{ Write-Error \"terminal exited $LASTEXITCODE on %s\" }"
                     % f["path"])
        return "\n".join(L) + "\n"
    L = ["#!/bin/sh", "# generated by tools/wfa_harness.py",
         "# Illustrative: the MT5 terminal is a Windows binary. Under Wine, the",
         "# same sequence applies; on Windows use run_all.ps1.",
         'TERMINAL="%s"' % terminal.replace('"', '\\"')]
    for f in files:
        L.append('echo "=== %s ==="' % f["label"])
        L.append('"$TERMINAL" "/config:%s" || echo "FAILED: %s"' % (f["path"], f["path"]))
    return "\n".join(L) + "\n"


def emit_configs(plan: dict, params, out_dir: str, expert: str, symbol: str,
                 period: str, deposit: float = 10000.0, currency: str = "USD",
                 leverage: str = "1:100", model: int = 4,
                 optimization: int = 2, criterion: int = 5,
                 terminal: str = r"C:\Program Files\MetaTrader 5\terminal64.exe",
                 base_report_dir: str = None) -> dict:
    """Write every file one plan needs, and return the file manifest.

    Two passes per window, on purpose:
      * `<id>_opt` - the optimiser sees the IS dates ONLY. Its report is a
        surface, not an answer.
      * `<id>_oos` - a single deterministic run over the OOS dates with whatever
        `apply` last wrote into `<id>_oos.set`. Nothing is optimised here.
    """
    if period not in VALID_PERIODS:
        raise ValueError("period %r is not an MT5 timeframe (%s)"
                         % (period, ", ".join(VALID_PERIODS)))
    if model not in MODELS:
        raise ValueError("model must be one of %s" % sorted(MODELS))
    if optimization not in (1, 2, 3):
        raise ValueError("optimization must be 1 (off), 2 (complete) or 3 (genetic)")
    if criterion not in CRITERIA:
        raise ValueError("criterion must be one of %s" % sorted(CRITERIA))

    os.makedirs(out_dir, exist_ok=True)
    report_dir = base_report_dir or out_dir
    files = []
    for w in plan["windows"]:
        wid = w["id"]
        for pass_name, date_from, date_to, opt in (
                ("opt", w["is_start"], w["is_end"], optimization),
                ("oos", w["oos_start"], w["oos_end"], 1)):
            set_name = "%s_%s.set" % (wid, pass_name)
            ini_name = "%s_%s.ini" % (wid, pass_name)
            report_name = os.path.join(report_dir, "%s_%s_report" % (wid, pass_name))
            header = ("window %s / %s pass / %s %s -> %s / %s"
                      % (wid, pass_name, symbol, date_from, date_to,
                         "optimise over IS" if pass_name == "opt"
                         else "evaluate the frozen parameters over OOS"))
            ini = render_ini(expert, set_name, symbol, period,
                             mt5_date(parse_date(date_from)),
                             mt5_date(parse_date(date_to)),
                             model, opt, criterion, deposit, currency, leverage,
                             report_name, header_comment=header)
            with io.open(os.path.join(out_dir, ini_name), "w",
                         encoding="utf-8", newline="\r\n") as fh:
                fh.write(ini)
            banner = None
            if pass_name == "oos":
                banner = ("NOT APPLIED YET: these are grid-start values.\n"
                          "Run tools/wfa_harness.py apply to freeze the parameters "
                          "chosen from the IS surface.\n"
                          "This file must never contain an optimisation range.")
            with io.open(os.path.join(out_dir, set_name), "w",
                         encoding="utf-8", newline="\r\n") as fh:
                fh.write(render_set(params, optimize_grid=(pass_name == "opt"),
                                    banner=banner))
            with io.open(os.path.join(out_dir, "%s_%s.testerinputs.txt"
                                      % (wid, pass_name)), "w",
                         encoding="utf-8", newline="\r\n") as fh:
                fh.write(render_testerinputs(params))
            files.append({"window": wid, "pass": pass_name, "label": "%s %s"
                          % (wid, pass_name),
                          "path": os.path.join(out_dir, ini_name),
                          "set": os.path.join(out_dir, set_name),
                          "report": report_name})

    manifest = {
        "plan": plan,
        "expert": expert, "symbol": symbol, "period": period,
        "model": model, "model_label": MODELS[model],
        "optimization": optimization, "criterion": criterion,
        "criterion_label": CRITERIA[criterion],
        "params": params,
        "grid_size": grid_size(params),
        "files": files,
        "out_dir": out_dir,
    }
    with io.open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with io.open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    ps1 = render_runner(plan, files, terminal, "windows")
    with io.open(os.path.join(out_dir, "run_all.ps1"), "w",
                 encoding="utf-8", newline="\r\n") as fh:
        fh.write(ps1)
    sh = render_runner(plan, files, terminal, "posix")
    with io.open(os.path.join(out_dir, "run_all.sh"), "w", encoding="utf-8",
                 newline="\n") as fh:
        fh.write(sh)

    with io.open(os.path.join(out_dir, "CONFIGS.md"), "w", encoding="utf-8") as fh:
        fh.write(render_configs_md(manifest))
    return manifest


def render_configs_md(m: dict) -> str:
    p = m["plan"]
    L = ["# Walk-forward configuration set", ""]
    L.append("`%s` · %s %s · model %d (%s) · optimisation %d · criterion %d (%s)"
             % (m["expert"], m["symbol"], m["period"], m["model"],
                m["model_label"], m["optimization"], m["criterion"],
                m["criterion_label"]))
    L.append("")
    L.append("Grid: **%d combinations** across %d parameter(s), %d of them optimised."
             % (m["grid_size"], len(m["params"]),
                sum(1 for x in m["params"] if x["optimize"])))
    L.append("")
    if p.get("holdout"):
        L.append("Holdout reserved: **%s → %s** (do not run it until the very end)."
                 % (p["holdout"]["start"], p["holdout"]["end"]))
        L.append("")
    L.append("| window | IS (optimise) | OOS (frozen) | days IS / OOS |")
    L.append("|---|---|---|---|")
    for w in p["windows"]:
        L.append("| %s | %s → %s | %s → %s | %d / %d |"
                 % (w["id"], w["is_start"], w["is_end"], w["oos_start"], w["oos_end"],
                    w["is_days"], w["oos_days"]))
    L.append("")
    L.append("## Run order")
    L.append("")
    L.append("1. Close MetaTrader. Run `run_all.ps1` (or execute the `_opt` inis in")
    L.append("   order). Each pass writes its own report and exits.")
    L.append("2. Ingest every optimisation export:")
    L.append("   `python3 tools/wfa_harness.py ingest --input <reports> --out <tidy>`.")
    L.append("3. Pick parameters per window with")
    L.append("   `python3 tools/wfa_stats.py plateau --runs <w01 tidy> --params ...`,")
    L.append("   which returns the centre of the plateau, not the peak.")
    L.append("4. Freeze the choice: `python3 tools/wfa_harness.py apply --selection ...`.")
    L.append("5. Run the `_oos` inis. They contain one parameter set and no optimiser.")
    L.append("6. Judge with `python3 tools/wfa_stats.py report --manifest study.json`.")
    L.append("")
    L.append("## State isolation between passes (read this before you run)")
    L.append("")
    L.append("QSMC_AutoTrader persists state in terminal GlobalVariables: the day and")
    L.append("session breakers (cleared by `InpResetBreakersAtInit=true`, and logged when")
    L.append("it fires) and ONE duplicate-suppression key per signalled bar")
    L.append("(`QSMC_AT_<magic>_<symbol>_<bartime>_<B|S>`), which nothing in this")
    L.append("repository clears. If those keys survive from one pass to the next, a bar")
    L.append("already 'seen' in an earlier pass is silently suppressed in a later one.")
    L.append("Adjacent windows overlap inside their IS ranges by construction, so this is")
    L.append("not a theoretical symmetry.")
    L.append("")
    L.append("Falsify it once, before trusting a multi-window study:")
    L.append("")
    L.append("1. run `w02_opt` alone in a fresh terminal profile; record the trade count;")
    L.append("2. run `w01_oos` and then `w02_opt` in the same profile; record it again.")
    L.append("")
    L.append("Identical numbers mean this terminal build isolates tester runs and the")
    L.append("plan is safe as configured. Different numbers mean every pass must run in")
    L.append("its own data folder (a portable terminal copy per pass), or the EA needs")
    L.append("a tester guard that ignores persisted seen-keys. Do NOT 'fix' it with")
    L.append("`InpResetBreakersAtInit=true`: that clears the breakers, not the keys.")
    L.append("")
    L.append("## What is deliberately NOT here")
    L.append("")
    L.append("- No forward-test window (`ForwardMode=1`): MT5's forward mode")
    L.append("  re-optimises at the end, and its OOS segment is then one sample,")
    L.append("  not a distribution. This plan rolls windows explicitly instead.")
    L.append("- No `UseCloud`/`UseRemote`: a grid must run on the same terminal")
    L.append("  build, history and symbol settings, or the windows are not comparable.")
    L.append("- No optimisation over an OOS date, in any file, ever.")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Apply a selection to the OOS sets
# ---------------------------------------------------------------------------

def apply_selection(plan: dict, params, selection: dict, out_dir: str) -> list:
    """Rewrite every `<id>_oos.set` from a selection, mechanically.

    Selection shapes accepted:
      * {"w01": {"InpX": 12}, "w02": {...}}   - per-window parameters
      * {"chosen": {"params": {"InpX": 12}}}   - one set for all windows
      * {"InpX": 12}                           - one set for all windows
    """
    if "chosen" in selection and isinstance(selection["chosen"], dict):
        selection = selection["chosen"].get("params", selection["chosen"])
    by_window = (all(str(k).startswith("w") and isinstance(v, dict)
                     for k, v in selection.items())
                 and any(str(k) in {w["id"] for w in plan["windows"]} for k in selection))
    known = {p["name"] for p in params}
    written = []
    for w in plan["windows"]:
        wid = w["id"]
        vals = selection.get(wid) if by_window else selection
        if not vals:
            continue
        unknown = [k for k in vals if k not in known]
        if unknown:
            raise ValueError("selection for %s names inputs that are not in the "
                             "parameter spec: %s" % (wid, ", ".join(unknown)))
        missing = [p["name"] for p in params if p["name"] not in vals]
        path = os.path.join(out_dir, "%s_oos.set" % wid)
        with io.open(path, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(render_set(params, {k: vals[k] for k in vals},
                                optimize_grid=False))
        with io.open(os.path.join(out_dir, "%s_oos.testerinputs.txt" % wid), "w",
                     encoding="utf-8", newline="\r\n") as fh:
            fh.write(render_testerinputs(params, {k: vals[k] for k in vals}))
        written.append({"window": wid, "path": path, "set": {k: vals[k] for k in vals},
                        "unset": missing})
    if not written:
        raise ValueError("selection matched no window in the plan")
    with io.open(os.path.join(out_dir, "selection_applied.json"), "w",
                 encoding="utf-8") as fh:
        fh.write(json.dumps({"selection": selection, "by_window": bool(by_window),
                             "written": written}, indent=2, sort_keys=True) + "\n")
    return written


# ---------------------------------------------------------------------------
# Ingest: the terminal's exports -> tidy CSV
# ---------------------------------------------------------------------------

def _flatten_cells(el) -> list:
    out = []
    for child in el:
        text = "".join(child.itertext()).strip()
        out.append(text)
    return out


def parse_xml_table(path: str):
    """Read an MT5 optimisation export.

    Three shapes are accepted because the terminal's export format depends on
    the build and on how the operator saved it:
      A. repeated elements carrying attributes  <Row Profit="..." Trades="..."/>
      B. repeated elements with child columns   <Row><Profit>..</Profit></Row>
      C. the report's cell grid                 <Row><Cell><Data>..</Data></Cell></Row>
    A header row (all cells non-numeric) is used as column names when present;
    otherwise columns are named col1..colN.
    """
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError("%s: not valid XML (%s)" % (path, exc))

    groups = {}
    for el in root.iter():
        if el is root:
            continue
        groups.setdefault(el.tag, []).append(el)

    # Three possible table shapes, in priority order:
    #   0. repeated elements carrying attributes  <Row Profit=".." Trades=".."/>
    #   1. repeated elements with >= 2 children    <Row><A/><B/></Row>
    #   2. anything repeated                        (flattened cell values)
    # Within a shape, the COARSEST table wins (fewest rows): a report nests
    # <Row><Cell><Data>, so counting occurrences would pick <Data> - one value
    # per row - and silently produce a one-column "grid".
    def width(el):
        return len(el)

    attr_groups = [(t, e) for t, e in groups.items()
                   if len(e) >= 2 and all(x.attrib for x in e)
                   and not any(width(x) for x in e)]
    multi = [(t, e) for t, e in groups.items()
             if len(e) >= 2 and min(width(x) for x in e) >= 2]
    rest = [(t, e) for t, e in groups.items() if len(e) >= 2]

    ordered = []
    for bucket in (sorted(attr_groups, key=lambda kv: -len(kv[1])),
                   sorted(multi, key=lambda kv: (len(kv[1]),
                                                 -max(width(x) for x in kv[1]))),
                   sorted(rest, key=lambda kv: -len(kv[1]))):
        for item in bucket:
            if item not in ordered:
                ordered.append(item)

    errors = []
    for tag, els in ordered:
        try:
            return _table_from_elements(els)
        except ValueError as exc:
            errors.append("%s: %s" % (tag, exc))
            continue
    raise ValueError("%s: no readable row structure (%s)"
                     % (path, "; ".join(errors) or "no repeated elements"))


def _text(el) -> str:
    return "".join(el.itertext()).strip()


def _table_from_elements(els):
    """Turn a list of sibling XML elements into (columns, rows)."""
    if all(el.attrib for el in els) and not any(len(el) for el in els):
        cols = []
        for el in els:
            for key in el.attrib:
                if key not in cols:
                    cols.append(key)
        return cols, [{k: el.attrib.get(k, "") for k in cols} for el in els]

    # One child element per column, each with a distinct tag.
    tag_sets = [[c.tag for c in el] for el in els]
    if all(len(set(t)) == len(t) for t in tag_sets) and len(set(tag_sets[0])) > 1:
        cols = list(tag_sets[0])
        rows = []
        for el in els:
            rows.append({c.tag: _text(c) for c in el})
        if rows and not _row_is_numeric([rows[0].get(c, "") for c in cols]):
            # A first element whose cells are all text is a header row: its
            # values name the columns of the elements that follow.
            header = [str(rows[0].get(c, "")).strip() or c for c in cols]
            rows = rows[1:]
            return header, [{header[i]: _text(list(el)[i])
                             for i in range(min(len(header), len(el)))} for el in els[1:]]
        return cols, rows

    rows_raw = [r for r in ([_text(c) for c in el] for el in els)
                if any(c.strip() for c in r)]
    if not rows_raw:
        raise ValueError("elements carry no data")
    width = max(len(r) for r in rows_raw)

    if not _row_is_numeric(rows_raw[0]):
        cols = [c.strip() or "col%d" % (i + 1) for i, c in enumerate(rows_raw[0])]
        rows_raw = rows_raw[1:]
    else:
        cols = ["col%d" % (i + 1) for i in range(width)]
    if not rows_raw:
        raise ValueError("only a header row was found")
    cols = list(cols) + ["col%d" % (i + 1) for i in range(len(cols), width)]
    rows = []
    for r in rows_raw:
        r = list(r) + [""] * (width - len(r))
        rows.append({cols[i]: r[i] for i in range(width)})
    return cols, rows


def _row_is_numeric(cells) -> bool:
    if not cells:
        return False
    hits = sum(1 for c in cells if _looks_numeric(c))
    return hits >= max(1, len(cells) // 2)


def _looks_numeric(cell) -> bool:
    s = str(cell).strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        return False
    s = s.rstrip("%").replace(",", ".")
    try:
        float(s)
        return True
    except ValueError:
        return False


def load_table(path: str):
    """Dispatch on extension: .csv/.txt via csv, .xml via the XML reader."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xml":
        return parse_xml_table(path)
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        # Pick the delimiter the header actually uses. Semicolon wins ties only
        # when a comma is absent, which is the locale case that breaks a naive
        # split: "1,23;456" is one number and one column, not two fields.
        counts = {d: sample.count(d) for d in (",", ";", "\t")}
        delim = max(counts, key=lambda d: counts[d])
        if counts[delim] == 0:
            delim = ","
        reader = csv.reader(fh, delimiter=delim)
        rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("%s: empty" % path)
    header = [c.strip() or "col%d" % (i + 1) for i, c in enumerate(rows[0])]
    out = []
    for r in rows[1:]:
        out.append({header[i]: (r[i] if i < len(r) else "") for i in range(len(header))})
    return header, out


def tidy_table(path: str) -> dict:
    """Normalise column names and drop rows that carry no numbers at all."""
    cols, rows = load_table(path)
    mapping = {}
    metrics = []
    params = []
    for c in cols:
        canon = canonical(c)
        mapping[c] = canon or c
        if canon:
            if canon not in metrics:
                metrics.append(canon)
        elif c not in params:
            params.append(c)
    tidy = []
    for row in rows:
        out = {}
        numeric_hits = 0
        for src, dst in mapping.items():
            val = to_number(row.get(src, ""))
            out[dst] = val
            if val is not None:
                numeric_hits += 1
        if numeric_hits:
            tidy.append(out)
    if not tidy:
        raise ValueError("%s: no numeric rows after normalisation" % path)
    columns = params + [m for m in metrics]
    return {"path": path, "columns": columns, "params": params,
            "metrics": metrics, "rows": tidy}


# Kept local to avoid importing wfa_stats' argparse-laden module surface into a
# tool that must stay runnable on a bare interpreter.
METRIC_NAMES = {
    "profit": "net_profit", "net profit": "net_profit",
    "total net profit": "net_profit", "result": "net_profit",
    "balance": "net_profit", "total profit": "net_profit",
    "gross profit": "gross_profit", "gross loss": "gross_loss",
    "trades": "trades", "total trades": "trades", "orders": "trades",
    "total deals": "trades",
    "profit factor": "profit_factor",
    "maximal drawdown %": "max_dd_pct", "equity dd %": "max_dd_pct",
    "max drawdown %": "max_dd_pct", "drawdown %": "max_dd_pct",
    "maximal drawdown": "max_dd_abs", "equity dd": "max_dd_abs",
    "max drawdown": "max_dd_abs",
    "sharpe ratio": "sharpe", "sharpe": "sharpe",
    "expected payoff": "expectancy", "expectancy": "expectancy",
    "recovery factor": "recovery",
    "profit trades %": "win_rate", "win rate": "win_rate",
}


def canonical(name: str):
    """Metric label -> canonical name. Accepts "Profit Factor" and "ProfitFactor"."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name).replace("\ufeff", "").strip())
    key = re.sub(r"[\s_]+", " ", text).strip().lower()
    if key in METRIC_NAMES:
        return METRIC_NAMES[key]
    if "profit factor" in key:
        return "profit_factor"
    if key.startswith("sharpe"):
        return "sharpe"
    if "drawdown" in key:
        return "max_dd_pct" if ("%" in key or "percent" in key) else "max_dd_abs"
    if "expected payoff" in key or "expectancy" in key:
        return "expectancy"
    if key in ("trades", "results", "deals"):
        return "trades"
    return None


def to_number(cell):
    s = str(cell).strip().replace("\u00a0", "").replace(" ", "").replace("'", "")
    if not s or s in ("-", "--"):
        return None
    s = s.rstrip("%")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        tail = s.rsplit(",", 1)[1]
        s = s.replace(",", ".") if len(tail) <= 2 else s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v == v and abs(v) != float("inf") else None


def write_tidy(tidy: dict, out_path: str) -> int:
    rows = tidy["rows"]
    cols = tidy["columns"]
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols)
        for row in rows:
            writer.writerow(["" if row.get(c) is None else row.get(c) for c in cols])
    return len(rows)


def cmd_ingest(args):
    src = args.input
    if os.path.isdir(src):
        targets = [os.path.join(src, n) for n in sorted(os.listdir(src))
                   if os.path.splitext(n)[1].lower() in (".csv", ".txt", ".xml")]
    else:
        targets = [src]
    if not targets:
        print("no .csv/.txt/.xml files under %s" % src, file=sys.stderr)
        return 2
    summary = []
    for path in targets:
        try:
            tidy = tidy_table(path)
        except ValueError as exc:
            print("skip: %s" % exc, file=sys.stderr)
            continue
        base = os.path.splitext(os.path.basename(path))[0]
        out = args.out
        if os.path.isdir(src) or out.endswith(os.sep):
            os.makedirs(out, exist_ok=True)
            out = os.path.join(out, base + ".tidy.csv")
        n = write_tidy(tidy, out)
        summary.append({"source": path, "out": out, "rows": n,
                        "params": tidy["params"], "metrics": tidy["metrics"]})
        print("%-48s -> %-40s %4d rows  metrics=%s"
              % (os.path.basename(path), os.path.basename(out), n,
                 ",".join(tidy["metrics"]) or "-"))
    if not summary:
        print("nothing ingested", file=sys.stderr)
        return 2
    if args.json:
        with io.open(args.json, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_json(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_plan(args):
    plan = build_plan(args.date_from, args.date_to, args.is_months, args.oos_months,
                      args.step_months, args.holdout_months, args.label)
    warns = plan_warnings(plan, args.free_params or 0)
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    with io.open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    with io.open(os.path.join(out_dir, "plan.md"), "w", encoding="utf-8") as fh:
        fh.write("# Walk-forward plan\n\n")
        fh.write("%s · IS %d months · OOS %d months · step %d months\n\n"
                 % (plan["label"], plan["is_months"], plan["oos_months"],
                    plan["step_months"]))
        if plan.get("holdout"):
            fh.write("Holdout reserved: **%s → %s**\n\n"
                     % (plan["holdout"]["start"], plan["holdout"]["end"]))
        fh.write("| window | IS | OOS |\n|---|---|---|\n")
        for w in plan["windows"]:
            fh.write("| %s | %s → %s | %s → %s |\n"
                     % (w["id"], w["is_start"], w["is_end"], w["oos_start"], w["oos_end"]))
        fh.write("\nCoverage: %.0f%% of the usable range.\n"
                 % (100 * plan["coverage"]["fraction"]))
        if warns:
            fh.write("\n## Warnings\n\n")
            for w in warns:
                fh.write("- %s\n" % w)
    print("windows: %d  coverage %.0f%%  -> %s"
          % (len(plan["windows"]), 100 * plan["coverage"]["fraction"], out_dir))
    for w in warns:
        print("WARN  %s" % w)
    return 0


def cmd_configs(args):
    plan = _load_json(args.plan)
    params = normalise_params(_load_json(args.params))
    for w in param_warnings(params):
        print("WARN  %s" % w)
    for w in plan_warnings(plan, sum(1 for p in params if p["optimize"])):
        print("WARN  %s" % w)
    for w in safety_warnings(args.expert, params):
        print("WARN  %s" % w)
    manifest = emit_configs(plan, params, args.out, args.expert, args.symbol,
                            args.period, args.deposit, args.currency, args.leverage,
                            args.model, args.optimization, args.criterion,
                            args.terminal)
    print("wrote %d files for %d windows, grid %d -> %s"
          % (len(manifest["files"]), len(plan["windows"]), manifest["grid_size"],
             args.out))
    print("next: run run_all.ps1 with MetaTrader closed, then ingest the reports")
    if "autotrader" in str(args.expert).lower():
        print("NOTE  this EA writes per-bar duplicate-suppression keys to terminal "
              "GlobalVariables;\n      read 'State isolation between passes' in %s "
              "before trusting a\n      multi-window study."
              % os.path.join(args.out, "CONFIGS.md"))
    return 0


def cmd_apply(args):
    plan = _load_json(args.plan)
    params = normalise_params(_load_json(args.params))
    selection = _load_json(args.selection)
    written = apply_selection(plan, params, selection, args.out)
    for w in written:
        note = (" (left at grid default: %s)" % ", ".join(w["unset"])) if w["unset"] else ""
        print("%s <- %s%s" % (w["window"], json.dumps(w["set"], sort_keys=True), note))
    print("wrote %d OOS .set file(s) -> %s" % (len(written), args.out))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Plan and configure a walk-forward study for the MT5 tester.")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("plan", help="build IS/OOS windows and reserve the holdout")
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)
    p.add_argument("--is-months", type=int, default=24)
    p.add_argument("--oos-months", type=int, default=6)
    p.add_argument("--step-months", type=int, default=None,
                   help="default: equal to --oos-months (contiguous OOS)")
    p.add_argument("--holdout-months", type=int, default=0)
    p.add_argument("--free-params", type=int, default=0,
                   help="how many parameters you intend to optimise (for warnings)")
    p.add_argument("--label", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("configs", help="emit MT5 .ini/.set files and the runner")
    p.add_argument("--plan", required=True)
    p.add_argument("--params", required=True, help="parameter spec JSON")
    p.add_argument("--out", required=True)
    p.add_argument("--expert", default="QSMC_AutoTrader")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--period", default="H1")
    p.add_argument("--deposit", type=float, default=10000.0)
    p.add_argument("--currency", default="USD")
    p.add_argument("--leverage", default="1:100")
    p.add_argument("--model", type=int, default=4)
    p.add_argument("--optimization", type=int, default=2)
    p.add_argument("--criterion", type=int, default=5)
    p.add_argument("--terminal", default=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    p.set_defaults(func=cmd_configs)

    p = sub.add_parser("apply", help="freeze a selection into the OOS .set files")
    p.add_argument("--plan", required=True)
    p.add_argument("--params", required=True)
    p.add_argument("--selection", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("ingest", help="normalise MT5 exports into a tidy CSV")
    p.add_argument("--input", required=True, help="file or directory")
    p.add_argument("--out", required=True, help="file, or directory ending in /")
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_ingest)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args)
    except (ValueError, KeyError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
