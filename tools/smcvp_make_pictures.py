#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate the chart pictures under docs/img/ from the host-built binaries.

    python3 tools/test_qsmc_chart_hygiene.py     # builds smcvp_hyg_before / smcvp_hyg_after
    python3 tools/test_qsmc_smcvp.py             # builds smcvp_suite_eng
    python3 tools/smcvp_make_pictures.py

Every picture is the object list a host-compiled run of the real MQL5 text left
on a simulated chart, drawn by tools/smcvp_chart_svg.py. None of them is a
MetaTrader screenshot.

  nadir2_primary_marks_before.svg   nadir2.mq5 before v6.6.22: one scenario that
                                    stays primary for 12 closed bars (the real
                                    AlertDispatcherDrawPrimary(), pre-fix lines)
  nadir2_primary_marks_after.svg    the same 12 publications after the fix
  smcvp_engine_story.svg            QSMC_SmcVpEngine, default layers, on the bar
                                    that confirms the synthetic BUY setup
  smcvp_engine_story_all_layers.svg the same bar with the histogram and the
                                    optional layer switched on
  smcvp_engine_xauusd_20250708.svg  XAUUSD M15, 2025-07-08 05:45 (only when the
                                    M1 dataset is on this host)
"""
from __future__ import print_function

import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import smcvp_chart_svg as SVG  # noqa: E402

BIN = os.path.join(ROOT, "out", "smcvp_native")
IMG = os.path.join(ROOT, "docs", "img")
DATA_DIRS = [os.environ.get("QSMC_XAU_DATA", ""), "/tmp/qats/data/XAUUSD_Dataset-main"]


def dump(exe, *args):
    path = os.path.join(BIN, exe)
    if not os.path.isfile(path):
        raise SystemExit("missing %s - run the two suites named in the docstring first" % path)
    proc = subprocess.run([path] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=300)
    if proc.returncode != 0:
        raise SystemExit("%s %s failed (%d): %s" % (exe, " ".join(args), proc.returncode, proc.stderr[-400:]))
    return proc.stdout


def save(name, doc, **kw):
    svg = SVG.render(doc, **kw)
    with io.open(os.path.join(IMG, name), "w", encoding="utf-8") as fh:
        fh.write(svg)
    print("%-36s %3d candles, %3d objects" % (name, len(doc["candles"]), len(doc["objects"])))


def main():
    os.makedirs(IMG, exist_ok=True)
    schedule = "A" * 12
    for tag, title in (("before", "nadir2.mq5 before v6.6.22: one scenario primary for 12 closed bars"),
                       ("after", "nadir2.mq5 v6.6.22: the same 12 publications")):
        doc = json.loads(dump("smcvp_hyg_%s" % tag, "picture", schedule, title))
        save("nadir2_primary_marks_%s.svg" % tag, doc, width=1100, height=420, right_bars=24, left_bars=24)

    doc = json.loads(dump("smcvp_suite_eng", "render"))
    doc["title"] = "QSMC_SmcVpEngine, default layers: synthetic story, the bar that confirms the BUY setup"
    save("smcvp_engine_story.svg", doc)
    doc = json.loads(dump("smcvp_suite_eng", "render", "--optional", "--histogram"))
    doc["title"] = "QSMC_SmcVpEngine, histogram + optional layer ON (both are off by default): the same bar"
    save("smcvp_engine_story_all_layers.svg", doc)

    data = next((d for d in DATA_DIRS if d and os.path.isdir(d) and any(n.startswith("XAUUSD_M1_") for n in os.listdir(d))), None)
    if not data:
        print("NOT RUN: smcvp_engine_xauusd_20250708.svg needs the XAUUSD M1 dataset (QSMC_XAU_DATA); the committed copy is kept")
        return 0
    out = os.path.join(BIN, "picture_real.json")
    dump("smcvp_suite_eng", "replay", "--data", data, "--from", "2025-06-01", "--to", "2025-07-09",
         "--render-at", "2025.07.08 05:45", "--render-out", out)
    with io.open(out, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["title"] = "QSMC_SmcVpEngine on XAUUSD M15 candles, 2025-07-08 05:45 (feed volume as a proxy for tick volume)"
    save("smcvp_engine_xauusd_20250708.svg", doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
