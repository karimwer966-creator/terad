#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUDIT-SVP - the SMC + Volume Profile decision engine (QSMC_SmcVpEngine.mq5).

WHAT IS UNDER TEST
  MQL5/Indicators/QSMC_SmcVpEngine.mq5 and the modules it includes
  (QSMC_SvpCore / Liquidity / Zones / VolumeProfile / Decision / Chart,
  QSMC_SignalRegistry). The REAL source text is transpiled and compiled for the
  host together with a simulator of the terminal (series, chart objects,
  indicator buffers, timer) - tools/smcvp_native.py - and driven by
  tools/smcvp_sim/engine_driver.inc.

WHAT THIS SUITE DOES
  A  source contracts on the host and the modules (pure text, always run),
     including a stack estimate (an indicator's stack is fixed at 1 MB)
  B  strict host build (-Wall -Wextra -Werror ...), with the legacy
     CVolumeProfile of QSMC_Stats.mqh linked in as the parity reference
  C  every unit of the driver (10 groups), and a map from the requirements of
     the specification to the units that exercise them
  D  the synthetic story and its price mirror: one BUY SETUP, one SELL SETUP;
     the picture tool draws that bar, and the committed picture is not stale
  E  a replay through the HOST (OnInit / OnCalculate / OnTimer / OnDeinit) of a
     synthetic M15 series and of its mirror image: the two runs must agree bar
     for bar, object count for object count; no repaint (re-evaluation and
     fresh attach give the same answer); chart-hygiene counters all zero
  F  the same binary built with poisoned array growth (every ArrayResize hands
     out garbage, as the terminal may): byte-identical results
  G  AddressSanitizer + UndefinedBehaviorSanitizer build (float-divide-by-zero
     included: MetaTrader stops a program on a zero divide): every unit again,
     the story, and a replay through the host
  H  every operand of && || ! in the transpiled unit is a real `bool`
  I  a market cut into two OVERLAPPING files replays exactly like the same market
     in one file (the public dataset's yearly files overlap at their seams)
  J  (only when the XAUUSD M1 dataset is on this host) a real-data replay, its
     mirror, and the same window under the sanitizers

B-J need a host C++17 compiler; without one the suite exits 77 after A.

WHAT IT IS NOT
  Not a MetaEditor compile, not the Strategy Tester, not a live chart. A host
  build is evidence, never proof, of a clean F7. Nothing here measures or
  claims profitability: the replay counts setups and checks invariants.
"""
from __future__ import print_function

import concurrent.futures
import io
import json
import os
import re
import subprocess
import sys
import time
from xml.etree import ElementTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import smcvp_native as SN  # noqa: E402
import smcvp_chart_svg as SVG  # noqa: E402

HOST = os.path.join(ROOT, "MQL5", "Indicators", "QSMC_SmcVpEngine.mq5")
INC = os.path.join(ROOT, "MQL5", "Include", "QSMC")
DRIVER = os.path.join(HERE, "smcvp_sim", "engine_driver.inc")
WORK = os.path.join(SN.OUT_DIR, "suite")
DATA_DIRS = [os.environ.get("QSMC_XAU_DATA", ""), "/tmp/qats/data/XAUUSD_Dataset-main"]

MODULES = ["QSMC_SvpCore.mqh", "QSMC_SvpLiquidity.mqh", "QSMC_SvpZones.mqh", "QSMC_SvpVolumeProfile.mqh",
           "QSMC_SvpDecision.mqh", "QSMC_SvpChart.mqh", "QSMC_SignalRegistry.mqh"]
# the analysis modules: they must not know that a chart exists
PURE = ["QSMC_SvpCore.mqh", "QSMC_SvpLiquidity.mqh", "QSMC_SvpZones.mqh", "QSMC_SvpVolumeProfile.mqh",
        "QSMC_SvpDecision.mqh", "QSMC_SignalRegistry.mqh"]

# the fewest units each group may report: a unit that silently disappears fails the suite
GROUP_MIN = {"structure": 13, "liquidity": 13, "sweep": 30, "zones": 14, "volume": 32, "decision": 33,
             "signal": 14, "chart": 18, "dashboard": 10, "host": 22}

# requirement of the specification -> the units that exercise it (ids as the driver prints them)
COVERAGE = [
    ("01 H4 bias", "S01 S02 S03 S04 S05 D12"),
    ("02 H1 structure", "S06 S08 S10 S11"),
    ("03 M15 liquidity map", "L01 L02 L03 L05 L09 L12"),
    ("04 liquidity sweep", "W01 W02 W05 W06 W09 W13 W15"),
    ("05 displacement", "W02 W03 W08 Z01 Z02 D06"),
    ("06 BOS / CHoCH", "S06 S07 W02 W12 Z03"),
    ("07 OB / FVG lifecycle", "Z02 Z04 Z05 Z07 Z08 Z09 Z11 Z13"),
    ("08 volume profile", "V02 V03 V04 V05 V10 V24 V25 V26 V29 V32 D23 D24"),
    ("09 entry validation", "D06 D07 D08 D20 D22"),
    ("10 risk / reward, stop, target", "D09 D10 D13 D15 D16 D17 D18 D32"),
    ("11 BUY / SELL symmetry", "S02 Z10 V30 D11 D18b"),
    ("12 WAIT with its reason", "D02 D03 D12 D13 D14 B03 B07 H15"),
    ("13 no repaint", "S09 W13 D21 D29 G04 G07"),
    ("14 no look-ahead", "S13 Z14 V20 D28 D30"),
    ("15 one signal per setup", "G01 G03 G06 G08 G12 G13 G14 H12"),
    ("16 dashboard: 16 rows, fixed order", "B01 B02 B04 B05 B06b B06c"),
    ("17 clean chart", "C02 C03 C05 C06 C10 C11 C12 C15 C16 C17 C18 H08 H22"),
    ("18 volume named honestly", "V11 V12 V22 H02"),
    ("19 host: once per closed bar, display only", "H02 H04 H05 H07 H09 H10 H11 H13 H17 H20 H21"),
]

DASH_ROWS = ["MARKET", "TIMEFRAME", "H4 BIAS", "H1 STRUCTURE", "LIQUIDITY", "SWEEP", "OB/FVG", "POC", "VAH / VAL",
             "FINAL DECISION", "ENTRY", "STOP LOSS", "TAKE PROFIT", "RISK/REWARD", "VOLUME PROFILE", "WHY"]

PASSED = 0
FAILED = []
T0 = time.time()


def check(cond, label, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("PASS  " + label)
    else:
        FAILED.append(label)
        print("FAIL  " + label + (("  [" + detail + "]") if detail else ""))
    sys.stdout.flush()
    return bool(cond)


def finish(code=None):
    print("%d passed, %d failed  (%.0f s)" % (PASSED, len(FAILED), time.time() - T0))
    print("This suite executes host-compiled MQL5 text against a terminal simulator. It is NOT a MetaEditor "
          "compile, NOT the Strategy Tester and NOT a live chart, and it makes no statement about profitability.")
    sys.exit((1 if FAILED else 0) if code is None else code)


def code_of(path):
    return SN.QN.strip_comments_and_strings(SN.read_source(path))


# ---------------------------------------------------------------- A  source contracts
print("=== A  source contracts")
host_text = SN.read_source(HOST)
host_code = code_of(HOST)
TRADE = ["OrderSend", "OrderSendAsync", "OrderCheck", "CTrade", "PositionOpen", "PositionClose", "PositionModify",
         "OrderCalcMargin", "Trade.mqh", "AccountInfoDouble", "AccountInfoInteger"]
sources = [HOST] + [os.path.join(INC, m) for m in MODULES]
check(all(os.path.isfile(p) for p in sources), "A01 the host and its seven modules exist")
found = sorted(set(w for p in sources for w in TRADE if re.search(r"\b" + re.escape(w) + r"\b", code_of(p))))
check(not found, "A02 no order, position or account call anywhere in the host or its modules (display only)", str(found))
check('#define SVE_PREFIX  "QSVP_"' in host_text and "SVC_Init(SVE_PREFIX,ChartID());" in host_code.replace('""', "SVE_PREFIX")
      or ('#define SVE_PREFIX  "QSVP_"' in host_text and "SVC_Init(SVE_PREFIX,ChartID())" in host_text),
      "A03 every object of the program is named QSVP_* (nadir2 owns QSMC_*): the two can share a chart")
props = re.findall(r"^#property[ \t]+(\S+)[ \t]*(.*)$", host_text, re.M)
types = [v.strip() for k, v in props if k.startswith("indicator_type")]
check(("indicator_chart_window", "") in [(k, v.strip()) for k, v in props] and
      dict(props).get("indicator_buffers", "").strip() == "5" and types == ["DRAW_NONE"] * 5,
      "A04 a chart-window indicator with five buffers, all DRAW_NONE (decision, entry, stop, target, RR)", str(types))
banned = {}
for m in PURE:
    c = code_of(os.path.join(INC, m))
    hits = [w for w in ("ObjectCreate", "ObjectDelete", "ObjectSet", "ObjectMove", "ChartRedraw", "Alert(", "PlaySound",
                        "SendNotification", "iCustom", "CopyBuffer", "CopyRates", "iTime(", "iClose(", "iHigh(", "iLow(",
                        "SymbolInfoTick", "TimeCurrent", "TimeLocal", "GlobalVariable", "FileOpen", "MathRand")
            if w in c]
    if hits:
        banned[m] = hits
check(not banned, "A05 the analysis modules read nothing but the arrays they are given: no chart object, no series call, "
      "no clock, no tick, no file, no random number", str(banned))
chart_code = code_of(os.path.join(INC, "QSMC_SvpChart.mqh"))
creates = len(re.findall(r"\bObjectCreate\s*\(", chart_code))
check(creates == 1 and "ObjectCreate" not in host_code,
      "A06 ONE ObjectCreate call site in the whole program (the Chart Object Manager); the host creates nothing itself",
      "%d call sites" % creates)
check("ObjectsDeleteAll" not in chart_code + host_code or re.search(r"ObjectsDeleteAll\s*\(\s*g_svc_chart\s*,\s*g_svc_prefix", chart_code),
      "A07 nothing is ever deleted wholesale except under the program's own prefix")
chart_text = SN.read_source(os.path.join(INC, "QSMC_SvpChart.mqh"))
start = chart_text.find("int SVV_DashboardRows(const SSvpDecision")
body = chart_text[start:chart_text.find("\n}\n", start)] if start >= 0 else ""
order = [body.find('rows[k++]="' + name + ":") for name in DASH_ROWS]
check(all(i >= 0 for i in order) and order == sorted(order) and body.count("rows[k++]=") == len(DASH_ROWS),
      "A08 SVV_DashboardRows() writes the sixteen rows in the order of the specification", str(order))
vp_text = SN.read_source(os.path.join(INC, "QSMC_SvpVolumeProfile.mqh"))
check("BROKER TICK VOLUME" in vp_text and "not centralized exchange volume" in vp_text and "not bid/ask order flow" in vp_text,
      "A09 the volume profile names its source in its own text: broker tick volume, not exchange volume, not order flow")
check(re.search(r"input\s+bool\s+InpSveAlerts\s*=\s*false", host_text) and
      re.search(r"input\s+bool\s+InpSveShowHistogram\s*=\s*false", host_text) and
      re.search(r"input\s+bool\s+InpSveShowOptional\s*=\s*false", host_text),
      "A10 shipped defaults: alerts off, histogram off, optional layer off (the clean profile)")
check("CopyRates(_Symbol,PERIOD_M15" in host_text.replace(" ", "") and "PERIOD_H1" in host_text and "PERIOD_H4" in host_text,
      "A11 the host reads M15, H1 and H4 of the chart symbol, whatever the chart timeframe")
problems = SN.lint(sources)
check(not problems, "A12 MQL5 lint over the %d sources: no C++-only construct, no struct by value, no reserved word" % len(sources),
      "; ".join(problems[:4]))
CHANNELS = ("Alert", "PlaySound", "SendNotification", "SendMail", "MessageBox", "Comment")
talk = {}
for path in sources:
    c = code_of(path)
    hits = [w for w in CHANNELS if re.search(r"\b" + w + r"\s*\(", c)]
    if hits:
        talk[os.path.basename(path)] = hits
check(talk == {"QSMC_SmcVpEngine.mq5": ["Alert"]} and len(re.findall(r"\bAlert\s*\(", host_code)) == 1,
      "A14 the modules never talk to the operator: ONE Alert call in the whole program, in the host, fed by the module's "
      "outbox (SVV_NextAnnouncement) - no sound, no push, no mail, no Comment()", str(talk))
ids = set(i for _, units in COVERAGE for i in units.split())
drv = io.open(DRIVER, encoding="utf-8").read()
missing = sorted(i for i in ids if ('"%s ' % i) not in drv)
check(not missing, "A15 every unit named in the requirement map exists in the driver (%d ids, %d requirements)"
      % (len(ids), len(COVERAGE)), str(missing))
# MetaTrader gives an indicator a fixed 1 MB stack; overflowing it stops the program, and a host
# build (8 MB) would never notice. Estimated from the declarations - see SN.stack_estimate().
stack = SN.stack_estimate(HOST)
deep_bytes, deep_chain = max(stack["deepest"].values()) if stack["deepest"] else (0, [])
check(stack["functions"] > 150 and not stack["recursive"] and 0 < deep_bytes < 128 * 1024 and stack["largest"][0] < 64 * 1024,
      "A16 stack: none of the %d functions is recursive, and the deepest chain of local variables from an event handler "
      "is about %d KB (%d frames; an indicator's stack is fixed at 1 MB)" % (stack["functions"], (deep_bytes + 1023) // 1024, len(deep_chain)),
      "recursive %s | largest frame %s | deepest %d bytes" % (stack["recursive"][:2], stack["largest"], deep_bytes))

if not SN.QN.find_compiler():
    print("=== B-J need a host C++17 compiler")
    print("SKIP  qsmc-smcvp-engine: no usable C++17 compiler (g++, c++, clang++) on this host - the source contracts "
          "above ran, the executed sections did NOT")
    print("%d passed, %d failed (text contracts only)" % (PASSED, len(FAILED)))
    sys.exit(1 if FAILED else SN.SKIP_EXIT)

# ---------------------------------------------------------------- B  builds
print("=== B  strict host builds")
os.makedirs(WORK, exist_ok=True)
LEGACY = SN.legacy_volume_profile()


def build(tag, defines=(), sanitize=False):
    # the sanitizer binary is built without optimisation: it compiles seven times
    # faster, and nothing the optimiser folds away can hide from the sanitizers
    return SN.build(HOST, DRIVER, tag, strict=True, sanitize=sanitize, optimize="-O0" if sanitize else "-O2",
                    defines=tuple(defines) + ("SMCVP_WITH_LEGACY_VP",), extra_units=(LEGACY,))


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    jobs = {"eng": pool.submit(build, "suite_eng"),
            "poison": pool.submit(build, "suite_poison", ("QATS_POISON_ARRAYS",)),
            "san": pool.submit(build, "suite_san", (), True),
            "bool": pool.submit(SN.bool_audit, HOST, "suite_bool")}
    built = dict((k, f.result()) for k, f in jobs.items())

EXE = {}
for key, what in (("eng", "normal"), ("poison", "poisoned array growth"), ("san", "ASan + UBSan")):
    exe, rc, diag = built[key]
    check(rc == 0 and exe is not None, "B01 %s build: 0 errors, 0 warnings (-Wall -Wextra -Wshadow -Wconversion as errors)" % what,
          "\n".join(l for l in diag.splitlines() if "error" in l or "warning" in l)[:900])
    EXE[key] = exe
if not all(EXE.values()):
    finish()


def run(key, *args, **kw):
    env = dict(os.environ)
    env.update(kw.get("env", {}))
    proc = subprocess.run([EXE[key]] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, timeout=kw.get("timeout", 240), env=env)
    return proc.returncode, proc.stdout


# the sanitizer runs are slow: they start now, two at a time, and are read in sections G and J
BACKGROUND = concurrent.futures.ThreadPoolExecutor(max_workers=2)
SAN_UNIT = BACKGROUND.submit(run, "san", "unit", timeout=600)
SAN_STORY = BACKGROUND.submit(run, "san", "story", "--back", "5000", timeout=600)
# ... and the HOST itself (OnInit / OnCalculate / OnTimer / OnDeinit, the view, the dashboard) bar after bar
SAN_SYN_JSON = os.path.join(WORK, "san_syn.json")
SAN_SYN = BACKGROUND.submit(run, "san", "replay", "--synthetic", "7", "--bars", "3000", "--sym-grid", "--recheck", "40",
                            "--reattach", "200", "--out", SAN_SYN_JSON, timeout=600)
DATA = next((d for d in DATA_DIRS if d and os.path.isdir(d) and any(n.startswith("XAUUSD_M1_") for n in os.listdir(d))), None)
SAN_REAL_JSON = os.path.join(WORK, "san_real.json")
SAN_REAL = BACKGROUND.submit(run, "san", "replay", "--data", DATA, "--from", "2025-06-01", "--to", "2025-08-01", "--recheck", "40",
                             "--reattach", "200", "--out", SAN_REAL_JSON, timeout=900) if DATA else None

rc, out = run("eng", "probe")
check(rc == 0 and "poison=0" in out and "legacy_vp=1" in out, "B02 the normal binary: arrays grow zero-filled, the legacy profile is linked in", out.strip())
rc, out = run("poison", "probe")
check(rc == 0 and "poison=1" in out, "B03 the poison binary really poisons (the define reached the shim)", out.strip())

# ---------------------------------------------------------------- C  units
print("=== C  units")
rc, unit_out = run("eng", "unit")
groups = dict((m.group(1), (int(m.group(2)), int(m.group(3)))) for m in re.finditer(r"^GROUP (\w+): (\d+) passed, (\d+) failed$", unit_out, re.M))
total = re.search(r"^smcvp-engine: (\d+) passed, (\d+) failed$", unit_out, re.M)
for line in unit_out.splitlines():
    if line.startswith("FAIL"):
        print("      " + line[:400])
for name in sorted(GROUP_MIN):
    got = groups.get(name, (0, -1))
    check(got[1] == 0 and got[0] >= GROUP_MIN[name], "C01 group %-9s %3d passed, %d failed (at least %d expected)"
          % (name + ":", got[0], max(got[1], 0), GROUP_MIN[name]))
check(rc == 0 and total is not None and int(total.group(2)) == 0 and int(total.group(1)) == sum(g[0] for g in groups.values())
      and int(total.group(1)) >= sum(GROUP_MIN.values()),
      "C02 all units: %s passed, %s failed, exit code %d" % (total.group(1) if total else "?", total.group(2) if total else "?", rc))
passed_ids = set(re.findall(r"^PASS  \w+ (\S+) ", unit_out, re.M))
failed_ids = set(re.findall(r"^FAIL  \w+ (\S+) ", unit_out, re.M))
for name, units in COVERAGE:
    want = units.split()
    bad = [u for u in want if u not in passed_ids or u in failed_ids]
    check(not bad, "C03 requirement %-42s %2d units: %s" % (name + ":", len(want), units), "not passing: %s" % bad)
info = re.search(r"^INFO  volume parity: (.*)$", unit_out, re.M)
if info:
    print("NOTE  " + info.group(1))

# ---------------------------------------------------------------- D  story
print("=== D  the synthetic story and its mirror")
rc, story = run("eng", "story", "--back", "5000")
last = story.strip().splitlines()[-1] if story.strip() else ""
setups = [l for l in story.splitlines() if " SETUP | " in l]
check(rc == 0 and len(setups) == 1 and "BUY SETUP | buy 10/10 sell 0/10 | E 2122.60 SL 2116.84 TP 2135.20 RR 2.19" in last,
      "D01 story: exactly one setup line, on the last bar: BUY SETUP, entry 2122.60, stop 2116.84, target 2135.20, RR 1:2.19", last[:200])
rc, mirror = run("eng", "story", "--mirror", "--back", "5000")
mlast = mirror.strip().splitlines()[-1] if mirror.strip() else ""
msetups = [l for l in mirror.splitlines() if " SETUP | " in l]
check(rc == 0 and len(msetups) == 1 and "SELL SETUP | buy 0/10 sell 10/10 | E 2177.40 SL 2183.16 TP 2164.80 RR 2.19" in mlast,
      "D02 mirrored story: exactly one setup line: SELL SETUP, entry 2177.40, stop 2183.16, target 2164.80, the same RR", mlast[:200])


def shape(text):
    """The decision column of a story listing with BUY and SELL swapped."""
    rows = []
    for l in text.splitlines():
        m = re.match(r"^\s*(\d+) \S+ \S+ (BUY SETUP|SELL SETUP|WAIT) \| buy (\d+)/10 sell (\d+)/10", l)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return rows


a, b = shape(story), shape(mirror)
swap = {"BUY SETUP": "SELL SETUP", "SELL SETUP": "BUY SETUP", "WAIT": "WAIT"}
check(len(a) > 1000 and len(a) == len(b) and all(x[0] == y[0] and swap[x[1]] == y[1] and x[2] == y[3] and x[3] == y[2] for x, y in zip(a, b)),
      "D03 on all %d bars the mirrored story is the mirror image: decision swapped, the two step counts swapped" % len(a))


# The pictures under docs/img/ are drawn from the same binary by tools/smcvp_chart_svg.py.
# The tool is part of the evidence, so it is exercised here; and a committed picture that no
# longer shows the objects the code draws is a stale document, so that is checked too.
def picture_objects(svg_text):
    """(heading, names of the chart objects drawn, dashboard rows) of a picture."""
    root = ElementTree.fromstring(svg_text.encode("utf-8"))
    ns = "{http://www.w3.org/2000/svg}"
    names = sorted(t.text.split(":")[0] for t in root.iter(ns + "title"))
    texts = [t.text or "" for t in root.iter(ns + "text")]
    heading = next((t for t in texts if "chart objects" in t), "")
    rows = [t.split(":")[0] for t in texts if ":" in t and t.split(":")[0] in DASH_ROWS]   # "POC" alone is a level caption
    return heading, names, rows


rc, dump = run("eng", "render")
try:
    doc = json.loads(dump) if rc == 0 else {}
except ValueError:
    doc = {}
anchored = sorted(o["name"] for o in doc.get("objects", [])
                  if o["type"] in (0, 1, 2, 16, 22) or (o["type"] == 100 and o.get("text")))
try:
    heading, drawn, rows = picture_objects(SVG.render(doc)) if doc else ("", [], [])
except Exception as exc:                      # a picture that is not well-formed XML fails here
    heading, drawn, rows = "render failed: %r" % (exc,), [], []
check(bool(doc) and len(doc["candles"]) == 111 and len(doc["objects"]) == 44 and drawn == anchored and len(anchored) == 27
      and rows == DASH_ROWS and heading.endswith("44 chart objects (2 further back than this window)"),
      "D04 the picture tool draws the story bar as well-formed SVG: every one of the 27 chart-anchored objects once, "
      "the 16 dashboard rows in order, and a heading that accounts for all 44 objects", "%s | %d drawn, %d anchored" % (heading[-70:], len(drawn), len(anchored)))
committed = os.path.join(ROOT, "docs", "img", "smcvp_engine_story.svg")
try:
    with io.open(committed, encoding="utf-8") as fh:
        c_heading, c_drawn, c_rows = picture_objects(fh.read())
except (IOError, OSError, ElementTree.ParseError) as exc:
    c_heading, c_drawn, c_rows = "unreadable: %r" % (exc,), [], []
check(c_drawn == anchored and c_rows == DASH_ROWS and c_heading.endswith("44 chart objects (2 further back than this window)"),
      "D05 the committed docs/img/smcvp_engine_story.svg shows exactly the objects this build draws "
      "(regenerate with tools/smcvp_make_pictures.py when this fails)", c_heading[-70:])

# ---------------------------------------------------------------- E  replay through the host
print("=== E  replay through the host: synthetic series, seed 7, and its mirror image")
ZERO = ["duplicate_objects", "zone_boxes_overlapping", "captions_colliding", "level_captions_struck_through",
        "in_chart_captions_struck_through", "buffer_mismatches", "api_errors", "format_errors", "trade_requests",
        "objects_left_after_deinit", "dashboard_rows_clipped", "recheck_differ", "reattach_differ"]
TIMING = ("pass_mean_us", "pass_worst_us")


def replay(key, name, *args):
    base = os.path.join(WORK, name)
    rc_, out_ = run(key, "replay", *(list(args) + ["--trace", base + ".trace", "--signals", base + ".csv", "--out", base + ".json"]))
    try:
        with io.open(base + ".json", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (IOError, ValueError):
        doc = {}
    return rc_, doc, base


SYN = ["--synthetic", "7", "--bars", "9000", "--sym-grid", "--recheck", "40", "--reattach", "200"]
rc_a, A, base_a = replay("eng", "syn_a", *SYN)
rc_b, B, base_b = replay("eng", "syn_b", *(SYN + ["--mirror", "--canonical"]))
check(rc_a == 0 and rc_b == 0 and A.get("m15_bars_analysed", 0) >= 7000, "E01 both replays ran to the end (%s bars each through OnCalculate)"
      % A.get("m15_bars_analysed"), "rc %d / %d" % (rc_a, rc_b))
if A and B:
    bad = [(k, A.get(k), B.get(k)) for k in ZERO if A.get(k) != 0 or B.get(k) != 0]
    check(not bad, "E02 hygiene counters, both runs: 0 duplicate objects, 0 overlapping same-side boxes, 0 colliding captions, "
          "0 captions struck through, 0 buffer mismatches, 0 API / format errors, 0 trade requests, 0 objects left after deinit", str(bad))
    check(A["recheck_compared"] >= 1000 and A["reattach_compared"] >= 30,
          "E03 no repaint: %d decisions re-evaluated 40 bars later, and %d fresh attaches compared with the chart that had been "
          "open all along - not one differs" % (A["recheck_compared"], A["reattach_compared"]))
    same_trace = io.open(base_a + ".trace", "rb").read() == io.open(base_b + ".trace", "rb").read()
    same_sig = io.open(base_a + ".csv", "rb").read() == io.open(base_b + ".csv", "rb").read()
    lines = io.open(base_a + ".trace", encoding="utf-8").read().count("\n") - 1
    check(same_trace, "E04 mirror: on all %d bars the mirrored run shows the mirrored decision, the same step counts per side, "
          "the same blocking step and the SAME NUMBER OF CHART OBJECTS (traces byte-identical)" % lines)
    check(same_sig and A["setups"] >= 3, "E05 mirror: the %d setups of the run (%d BUY, %d SELL) come back as %d BUY, %d SELL with "
          "mirrored entry / stop / target and the same outcome" % (A["setups"], A["setups_buy"], A["setups_sell"], B["setups_buy"], B["setups_sell"]))
    check(A["setups_buy"] == B["setups_sell"] and A["setups_sell"] == B["setups_buy"] and A["setups_buy"] > 0 and A["setups_sell"] > 0,
          "E06 both directions occur in one run: the engine is not a one-way machine")
    check(A["wait_blocked_at"] == B["wait_blocked_at"] and A["objects_created"] == B["objects_created"] and A["objects_max"] == B["objects_max"],
          "E07 mirror: the same WAIT reasons bar for bar and the same chart work (%d objects created, at most %d on the chart)"
          % (A["objects_created"], A["objects_max"]), "%s | %s" % (A["wait_blocked_at"], B["wait_blocked_at"]))
    check(A["objects_max"] <= 60 and A["dashboard_labels_max"] <= 18 and A["dashboard_longest_row_chars"] <= 78,
          "E08 the chart never held more than %d objects (dashboard included); the dashboard never more than %d labels, no row over %d characters"
          % (A["objects_max"], A["dashboard_labels_max"], A["dashboard_longest_row_chars"]))
    check(A["lifecycle_compared"] >= 1 and A["lifecycle_agrees_with_candles"] == A["lifecycle_compared"],
          "E09 the engine's own verdict on a finished setup (target reached / stop reached) agrees with the candles that "
          "followed: %d of the %d setups that resolved inside the horizon" % (A["lifecycle_agrees_with_candles"], A["lifecycle_compared"]))
    print("NOTE  synthetic series (NOT market data): %d setups, target first %d, stop first %d - a count, not a result"
          % (A["setups"], A["buy_target_first"] + A["sell_target_first"], A["buy_stop_first"] + A["sell_stop_first"]))
    print("NOTE  WAIT was blocked at: %s" % json.dumps(A["wait_blocked_at"], sort_keys=True))
    print("NOTE  captions drawn %d, withheld %d (their lines stay); mean pass %.2f ms"
          % (A["captions_drawn"], A["captions_withheld"], A["pass_mean_us"] / 1000.0))

# ---------------------------------------------------------------- F  poison
print("=== F  poisoned array growth: the same answers")
rc, punit = run("poison", "unit")
strip = lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("INFO"))  # noqa: E731
check(rc == 0 and strip(punit) == strip(unit_out), "F01 units: byte-identical output")
rc1, pstory = run("poison", "story", "--back", "5000")
rc2, pmirror = run("poison", "story", "--mirror", "--back", "5000")
check(rc1 == 0 and rc2 == 0 and pstory == story and pmirror == mirror, "F02 story and mirrored story: byte-identical listings")
rc_p, P, base_p = replay("poison", "syn_p", *SYN)
if A and P:
    same = all(A[k] == P.get(k) for k in A if k not in TIMING)
    check(rc_p == 0 and same and io.open(base_a + ".trace", "rb").read() == io.open(base_p + ".trace", "rb").read()
          and io.open(base_a + ".csv", "rb").read() == io.open(base_p + ".csv", "rb").read(),
          "F03 host replay: the same summary (all %d fields but the two timings), trace and signals" % (len(A) - 2),
          str([k for k in A if k not in TIMING and A[k] != P.get(k)][:6]))

# ---------------------------------------------------------------- G  sanitizers
print("=== G  AddressSanitizer + UndefinedBehaviorSanitizer")
rc, sunit = SAN_UNIT.result()
stotal = re.search(r"^smcvp-engine: (\d+) passed, (\d+) failed$", sunit, re.M)
report = [l for l in sunit.splitlines() if "runtime error" in l or "AddressSanitizer" in l or "LeakSanitizer" in l]
check(rc == 0 and stotal is not None and stotal.group(2) == "0" and total is not None and stotal.group(1) == total.group(1) and not report,
      "G01 every unit again under ASan + UBSan (float-divide-by-zero included): %s passed, no report" % (stotal.group(1) if stotal else "?"),
      "; ".join(report[:3]))
rc, sstory = SAN_STORY.result()
check(rc == 0 and sstory == story and "runtime error" not in sstory, "G02 the story under the sanitizers: the same listing, no report")


def sanitized_replay(future, path):
    """(rc, summary, sanitizer lines) of a replay of the sanitizer binary."""
    rc_, out_ = future.result()
    try:
        with io.open(path, encoding="utf-8") as fh:
            doc_ = json.load(fh)
    except (IOError, ValueError):
        doc_ = {}
    return rc_, doc_, [l for l in out_.splitlines() if "runtime error" in l or "Sanitizer" in l]


rc, SS, report = sanitized_replay(SAN_SYN, SAN_SYN_JSON)
bad = [(k, SS.get(k)) for k in ZERO if SS.get(k) != 0]
check(rc == 0 and not report and not bad and SS.get("m15_bars_analysed", 0) >= 1000,
      "G03 the HOST under the sanitizers: %s bars of the synthetic series through OnInit / OnCalculate / OnDeinit, no report, "
      "every hygiene and no-repaint counter 0" % SS.get("m15_bars_analysed"), "rc %d | %s | %s" % (rc, "; ".join(report[:2]), bad))

# ---------------------------------------------------------------- H  bool audit
print("=== H  boolean operands")
count, rc, diag = built["bool"]
check(rc == 0 and count >= 1300, "H01 %d operands of && || ! in the transpiled unit are all real `bool` "
      "(MQL5 does not convert a number or a pointer in a condition the way C++ would silently)" % count, diag.strip()[-500:])

# ---------------------------------------------------------------- I  file seams
print("=== I  a market cut into two overlapping files")
import qats_backtest as BT  # noqa: E402  (the dataset-layout fixture generator)

seam_one, seam_two = os.path.join(WORK, "seam_one"), os.path.join(WORK, "seam_two")
for d in (seam_one, seam_two):
    if os.path.isdir(d):
        for name in os.listdir(d):
            os.remove(os.path.join(d, name))
    os.makedirs(d, exist_ok=True)
whole = BT.synthetic_m1(os.path.join(seam_one, "market.csv"), weeks=12)
BT.split_with_overlap(whole, seam_two, 9 * 7020 + 3000, repeated=300, names=("market_a.csv", "market_b.csv"))
SEAM = ["--from", "2024-02-26", "--to", "2024-03-18"]
rc_1, S1, sb1 = replay("eng", "seam_1", *(["--data", seam_one] + SEAM))
rc_2, S2, sb2 = replay("eng", "seam_2", *(["--data", seam_two] + SEAM))
if check(rc_1 == 0 and rc_2 == 0 and S1.get("m15_bars_analysed", 0) > 1000,
         "I01 a synthetic M1 market replayed from one file and from two files that overlap by 300 rows (the public dataset's "
         "yearly files overlap like that at their seams)", "rc %d / %d" % (rc_1, rc_2)):
    check(S1["m1_rows_skipped_repeated_at_a_file_seam"] == 0 and S2["m1_rows_skipped_repeated_at_a_file_seam"] == 300,
          "I02 exactly the 300 repeated rows are skipped: a row that does not move time forward is never fed twice")
    skip = TIMING + ("m1_rows_skipped_repeated_at_a_file_seam",)
    differ = [k for k in S1 if k not in skip and S1[k] != S2.get(k)]
    check(not differ and io.open(sb1 + ".trace", "rb").read() == io.open(sb2 + ".trace", "rb").read()
          and S1["bars_not_ready"] == 0 and S2["bars_not_ready"] == 0,
          "I03 the two replays are identical bar for bar (%d bars, every one analysed): no duplicate or out-of-order bar ever "
          "reaches the series" % S1["m15_bars_analysed"], "fields that differ: %s | not ready %s / %s"
          % (differ[:6], S1.get("bars_not_ready"), S2.get("bars_not_ready")))

# ---------------------------------------------------------------- J  real data, when present
print("=== J  real-data replay (optional)")
data = DATA
if not data:
    print("NOTE  NOT RUN: the XAUUSD M1 dataset is not on this host (set QSMC_XAU_DATA, or run "
          "`python3 tools/qats_backtest.py fetch --dest /tmp/qats/data/XAUUSD_Dataset-main`). Sections A-I do not need it.")
else:
    REAL = ["--data", data, "--from", "2025-06-01", "--to", "2025-08-01", "--recheck", "40", "--reattach", "200"]
    rc_r, R, base_r = replay("eng", "real", *REAL)
    if check(rc_r == 0 and R.get("m15_bars_analysed", 0) > 3500, "J01 XAUUSD M15 2025-06-02 .. 2025-07-31 through the host: %s bars"
             % R.get("m15_bars_analysed"), "rc %d" % rc_r):
        bad = [(k, R.get(k)) for k in ZERO if R.get(k) != 0]
        check(not bad and R["bars_not_ready"] == 0, "J02 the same hygiene and no-repaint counters on real candles: all zero, "
              "and every bar of the window was analysed", "%s | not ready %s" % (bad, R.get("bars_not_ready")))
        check(R["objects_max"] <= 60 and R["lifecycle_agrees_with_candles"] == R["lifecycle_compared"],
              "J03 at most %d objects on the chart; the engine's verdict agrees with the candles on %d of %d setups"
              % (R["objects_max"], R["lifecycle_agrees_with_candles"], R["lifecycle_compared"]))
        INT = ["--data", data, "--from", "2025-06-01", "--to", "2025-08-01", "--int-grid", "--sym-grid"]
        rc_1, R1, b1 = replay("eng", "real_i", *INT)
        rc_2, R2, b2 = replay("eng", "real_m", *(INT + ["--mirror", "--canonical"]))
        check(rc_1 == 0 and rc_2 == 0 and io.open(b1 + ".trace", "rb").read() == io.open(b2 + ".trace", "rb").read()
              and io.open(b1 + ".csv", "rb").read() == io.open(b2 + ".csv", "rb").read()
              and R1["wait_blocked_at"] == R2["wait_blocked_at"],
              "J04 the same window on whole points and its mirror image: traces, signals and WAIT reasons identical "
              "(%d BUY / %d SELL setups <-> %d BUY / %d SELL)" % (R1.get("setups_buy", -1), R1.get("setups_sell", -1),
                                                                R2.get("setups_buy", -1), R2.get("setups_sell", -1)))
        rc, SR, report = sanitized_replay(SAN_REAL, SAN_REAL_JSON)
        bad = [(k, SR.get(k)) for k in ZERO if SR.get(k) != 0]
        check(rc == 0 and not report and not bad and all(SR.get(k) == R.get(k) for k in ("m15_bars_analysed", "setups", "setups_buy",
                                                                                         "setups_sell", "objects_max", "wait_blocked_at")),
              "J05 the same real window under ASan + UBSan (float-divide-by-zero included): no report, and the same bars, setups, "
              "object peak and WAIT reasons as the normal binary", "rc %d | %s | %s" % (rc, "; ".join(report[:2]), bad))
        print("NOTE  real candles, feed volume as a PROXY for broker tick volume: %d setups (%d BUY, %d SELL), target first %d, "
              "stop first %d. Two months and a handful of setups: a count, NOT evidence of profitability."
              % (R["setups"], R["setups_buy"], R["setups_sell"], R["buy_target_first"] + R["sell_target_first"],
                 R["buy_stop_first"] + R["sell_stop_first"]))
        print("NOTE  WAIT was blocked at: %s" % json.dumps(R["wait_blocked_at"], sort_keys=True))

BACKGROUND.shutdown()
finish()
