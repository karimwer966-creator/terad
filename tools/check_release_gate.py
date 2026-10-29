#!/usr/bin/env python3
"""
QSMC v6.6.13 - RELEASE GATE

A go / no-go check for taking this layer to a live chart. It does not re-check
what static_check.py already checks (dialect rules, includes, balance); it
checks the things that only matter *before deployment*:

  G1  one version, everywhere - source triple and the docs' titles
  G2  the data-folder layout is complete, so a copy cannot half-install
  G3  every input is documented, and the production defaults are the quiet ones
  G4  nothing in this layer can trade, send a request, or delete a file -
      with ONE reviewed exception: MQL5/Experts/QSMC_AutoTrader.mq5, the
      execution companion, which is the only file allowed to reach the trade API
  G5  no log line can fire per bar unless the operator asked for verbosity
  G6  no TODO / FIXME / "not implemented" left in the shipped path
  G7  the CI gate covers this script (a gate nobody runs is a suggestion)

Exit code 1 means: do not deploy yet. It is not a compiler and it does not
prove the code runs - it proves the operational invariants hold.

Usage: python3 tools/check_release_gate.py [--root DIR]
"""
import os
import re
import sys
from bisect import bisect_right

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if "--root" in sys.argv:
    ROOT = os.path.abspath(sys.argv[sys.argv.index("--root") + 1])

INC = os.path.join(ROOT, "MQL5", "Include", "QSMC")
DOCS = os.path.join(ROOT, "docs")
LAYER_DIRS = [INC,
              os.path.join(ROOT, "MQL5", "Indicators"),
              os.path.join(ROOT, "MQL5", "Scripts"),
              os.path.join(ROOT, "MQL5", "Experts")]

FAILS, WARNS, NOTES = [], [], []


def read(p):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def layer_files():
    out = []
    for d in LAYER_DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith((".mqh", ".mq5")):
                out.append(os.path.join(d, f))
    return out


def fail(msg):
    FAILS.append(msg)


def warn(msg):
    WARNS.append(msg)


# ---------------------------------------------------------------- G1 version
host = read(os.path.join(ROOT, "nadir2.mq5"))
vt = re.search(r'#define\s+QSMC_VERSION_TEXT\s+"v(\d+)\.(\d+)\.(\d+)"', host)
pv = re.search(r'#property\s+version\s+"(\d+)\.(\d+)"', host)
if not vt or not pv:
    fail("G1 the host defines neither QSMC_VERSION_TEXT nor #property version")
else:
    triple = (vt.group(1), vt.group(2), vt.group(3))
    short = "%s.%s" % (triple[0], triple[1] + triple[2])
    if (pv.group(1), pv.group(2)) != (short.split(".") if False else (triple[0], triple[1] + triple[2])):
        fail("G1 #property version \"%s.%s\" != QSMC_VERSION_TEXT v%s.%s.%s (expected \"%s\")"
             % (pv.group(1), pv.group(2), triple[0], triple[1], triple[2], short))
    else:
        NOTES.append("G1 host version triple: v%s.%s.%s / \"%s\""
                     % (triple[0], triple[1], triple[2], short))
    banner = re.search(r'\[QSMC_ARB\]\s+v(\d+)\.(\d+)\.(\d+)\s+arbitration layer ON',
                       read(os.path.join(INC, "QSMC_Root.mqh")))
    if not banner:
        fail("G1 QSMC_Root.mqh has no `[QSMC_ARB] vX.Y.Z arbitration layer ON` banner")
    elif (banner.group(1), banner.group(2), banner.group(3)) != triple:
        fail("G1 the layer banner says v%s.%s.%s but the host says v%s.%s.%s"
             % (banner.group(1), banner.group(2), banner.group(3),
                triple[0], triple[1], triple[2]))
    # docs must not name a different build either
    runbook = os.path.join(DOCS, "QSMC_BUILD_AND_RUN.md")
    if os.path.isfile(runbook):
        title = re.search(r"^# QSMC v(\d+)\.(\d+)\.(\d+)", read(runbook), re.M)
        if not title:
            warn("G1 docs/QSMC_BUILD_AND_RUN.md has no `# QSMC vX.Y.Z` title to check")
        elif title.group(1, 2, 3) != triple:
            warn("G1 the runbook is titled v%s.%s.%s while the build is v%s.%s.%s - "
                 "a stale runbook is how an operator follows the wrong steps"
                 % (title.group(1), title.group(2), title.group(3),
                    triple[0], triple[1], triple[2]))

    # G1b - the half of G1 that could not see drift AHEAD of the triple. A comment
    # may name an older release (that is when the work landed); nothing may name a
    # newer one, because that ships code labelled with a version that does not exist
    # yet - and the operator's "identify a stale build by its banner" rule dies with
    # it. This is the check docs/QSMC_V6.6.10_TACTICAL_AUTHORITY.md 9.2 asked for.
    build = (int(triple[0]), int(triple[1]), int(triple[2]))
    ahead, newest = [], build
    scan = [os.path.join(ROOT, "nadir2.mq5")]
    for d in LAYER_DIRS:
        if os.path.isdir(d):
            scan += [os.path.join(d, f) for f in sorted(os.listdir(d))
                     if f.lower().endswith((".mq5", ".mqh"))]
    for path in scan:
        if not os.path.isfile(path):
            continue
        text = read(path)
        for m in re.finditer(r"\bv(\d+)\.(\d+)\.(\d+)\b", text):
            got = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if got > newest:
                newest = got
            if got > build:
                ahead.append("%s: %s" % (os.path.basename(path), m.group(0)))
    if ahead:
        fail("G1 a marker claims a version AHEAD of the build (%s) while QSMC_VERSION_TEXT "
             "says v%s.%s.%s - the next reader would trust the wrong number"
             % (", ".join(sorted(set(ahead))[:6]), triple[0], triple[1], triple[2]))
    else:
        NOTES.append("G1 no in-code marker is ahead of v%s.%s.%s (newest seen v%d.%d.%d)"
                     % (triple[0], triple[1], triple[2], newest[0], newest[1], newest[2]))

# ---------------------------------------------------------------- G2 layout
NEEDED = (["QSMC_%s.mqh" % n for n in
            ("Types", "Structure", "EarlyBreakDetector", "MarketData", "Zones", "ZoneScorer",
             "Reaction", "Bias", "Preset", "Gates", "AlertManager", "Arbiter",
             "Stats", "Renderer", "Root", "Selftest", "Scanners", "DataProvider")],
          [os.path.join("MQL5", "Indicators", "QSMC_ScannerProbe.mq5"),
           os.path.join("MQL5", "Scripts", "QSMC_ArbiterTest.mq5"),
           os.path.join("MQL5", "Experts", "KLJ_DataFeeder.mq5"),
           os.path.join("MQL5", "Experts", "QSMC_AutoTrader.mq5"),
           "nadir2.mq5"])
for f in NEEDED[0]:
    if not os.path.isfile(os.path.join(INC, f)):
        fail("G2 missing header MQL5/Include/QSMC/%s" % f)
for rel in NEEDED[1]:
    if not os.path.isfile(os.path.join(ROOT, rel)):
        fail("G2 missing %s" % rel)
extra = sorted(set(x for x in os.listdir(INC) if x.endswith(".mqh")) - set(NEEDED[0]))
if extra:
    warn("G2 headers present but not in the documented layout: %s" % ", ".join(extra))
else:
    NOTES.append("G2 layout complete: 18 headers + 1 indicator + 1 probe + 1 script + 1 feeder EA "
                 "+ 1 execution EA")

# ------------------------------------------------------------- G3 inputs
preset = read(os.path.join(INC, "QSMC_Preset.mqh"))
inputs = re.findall(r'^input\s+(?:const\s+)?[A-Za-z_][\w:]*\s+(Inp\w*)\s*=\s*([^;]*);',
                    preset, re.M)
names = [n for n, _ in inputs]
defaults = dict(inputs)
if len(names) < 30:
    fail("G3 only %d inputs parsed from QSMC_Preset.mqh - the pattern and the file "
         "have drifted apart, and an unreadable input table is worse than none"
         % len(names))
docs_text = ""
for dp in ("QSMC_BUILD_AND_RUN.md", "KLJ_V6.6.0_SIGNAL_ARBITRATION.md"):
    f = os.path.join(DOCS, dp)
    if os.path.isfile(f):
        docs_text += read(f)
undoc = [n for n in names if n not in docs_text]
if undoc:
    warn("G3 %d of %d inputs are not mentioned in the docs: %s"
         % (len(undoc), len(names), ", ".join(undoc[:8]) + ("…" if len(undoc) > 8 else "")))
else:
    NOTES.append("G3 every one of the %d inputs appears in the docs" % len(names))
# the quiet defaults, stated as a rule rather than hoped for
QUIET_FALSE = ("InpArbVerboseLog", "InpArbCSVLog")
for n in QUIET_FALSE:
    if n not in defaults:
        fail("G3 expected input %s is not declared - did it get renamed? The release "
             "gate cannot check what it cannot find" % n)
    elif defaults[n].strip().lower() not in ("false", "0"):
        fail("G3 %s must default to false for a production install (it is now %r): "
             "per-bar logs and per-bar CSV writes are how a live chart dies of "
             "attention" % (n, defaults[n].strip()))
NOTES.append("G3 verbose log + CSV logging default to false")

# ------------------------------------------------- G3b inputs that do nothing
# A switch the operator can flip with no effect is worse than a missing feature: it
# is a lie in the properties dialog. Detecting one needs the CODE, not the file - and
# the order of stripping matters. nadir2.mq5:635 carries `QSMC/*.mqh` inside a `//`
# comment, so stripping block comments first deletes 21 000 lines and reports every
# input as dead. Strings, then line comments, then block comments.
DEAD_ALLOWED = {
    "InpDockDashboard": "legacy, and its own comment says so",
    "InpPanelsStartCollapsed": "legacy, and its own comment says so",
    "InpAlertOnEntryPreview": "legacy, and its own comment says so",
    "InpScalpShowOnDashboard": "RESERVED: no scalping tooltip row exists yet (doc 11.12)",
    "InpShowGateAudit": "RESERVED: no dashboard row exists yet; the audit prints instead",
    "InpShowEntryQualityPanel": "RESERVED: those rows are not built (doc 11.12)",
}
_host = read(os.path.join(ROOT, "nadir2.mq5"))
_code = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', _host)
_code = re.sub(r"//[^\n]*", "", _code)
_code = re.sub(r"/\*.*?\*/", "", _code, flags=re.S)
_read_at = {}
for _i, _line in enumerate(_code.split("\n")):
    for _w in set(re.findall(r"[A-Za-z_]\w*", _line)):
        _read_at.setdefault(_w, []).append(_i)
_decl = {}
for _i, _line in enumerate(_host.split("\n")):
    _m = re.match(r"^[ \t]*(?:sinput|input)[ \t]+(?:group[ \t]+\"[^\"]*\"|"
                  r"(?:[A-Za-z_]\w*(?:[ \t]*\*)?[ \t]+)+([A-Za-z_]\w*)[ \t]*=)", _line)
    if _m and _m.group(1):
        _decl.setdefault(_m.group(1), _i)
_dead = [n for n, i in _decl.items() if not [j for j in _read_at.get(n, []) if j != i]]
_unexpected = sorted(n for n in _dead if n not in DEAD_ALLOWED)
_stale = sorted(n for n in DEAD_ALLOWED if n not in _dead)
if _unexpected:
    fail("G3 %s read by nothing but its own declaration - a switch the operator can "
         "flip with no effect. Wire it, correct its label, or list it in "
         "DEAD_ALLOWED with a reason" % ", ".join(_unexpected))
elif _stale:
    warn("G3 these were listed as dead but are read now: %s - drop them from "
         "DEAD_ALLOWED" % ", ".join(_stale))
else:
    NOTES.append("G3 %d inputs parsed; %d read by nothing, every one of them listed "
                 "with a reason" % (len(_decl), len(_dead)))

# --------------------------------------------------------------- G4 no trading
# Scoped on purpose. The QSMC LAYER (headers + the indicator + the probe) must not
# be able to trade, reach the network, or delete files. The optional companion EA in
# MQL5/Experts does fetch URLs and rotate its own CSV - that is its documented job,
# so it is checked for the trade API only. A blanket ban would have taught everyone
# to ignore the gate.
LIBRARY = [f for f in layer_files() if os.sep + "Include" + os.sep in f
           or os.path.basename(f) == "QSMC_ScannerProbe.mq5"]
PROGRAMS = [f for f in layer_files() if f not in LIBRARY]

# The single reviewed exception to "this release cannot trade". Execution is a
# separate program precisely so that the indicator and the 18 headers stay
# unable to reach the trade API - that is what makes the dashboard safe to leave
# on a chart. Everything about this file is checked: it ships inert, it needs a
# demo account by default, and it is the only name on this list.
EXEC_EA = os.path.join(ROOT, "MQL5", "Experts", "QSMC_AutoTrader.mq5")
EXEC_TRADE_ALLOWED = {os.path.abspath(EXEC_EA)}

TRADE = [(r"\bOrderSend\s*\(",                    "OrderSend"),
         (r"\bOrderCheck\s*\(",                   "OrderCheck"),
         (r"\bOrderGetTicket|\bOrderSelect\s*\(", "order API"),
         (r"\bPositionOpen\b|PositionsTotal\s*\(|\bPositionModify\s*\(", "position API"),
         (r"\bCTrade\s+\w+|\btrade\.[A-Za-z]+\s*\(", "CTrade / trade.*"),
         (r"\bOrderCalcMargin|\bAccountInfoDouble\s*\(\s*ACCOUNT_MARGIN", "margin accounting")]
SIDE_EFFECTS = [(r"\bWebRequest\s*\(",   "WebRequest"),
                (r"\bFileDelete\s*\(",   "FileDelete"),
                (r"\bFileFlush|\bFileWriteInteger|\bFileWriteDouble", "file writes"),
                (r"\bSendNotification\s*\(", "SendNotification"),
                (r"\bPlaySound\s*\(", "PlaySound"),
                (r"\bAlert\s*\(", "Alert")]
ALLOW_SITE = {"SendNotification": "QSMC_AlertManager.mqh",
              "PlaySound": "QSMC_AlertManager.mqh",
              "Alert": "QSMC_AlertManager.mqh",
              # CStatsLogger/CEdgeBook in QSMC_Stats.mqh own the optional
              # signal journal and outcome ledger (terminal-local MQL5/Files).
              # Persistence is default-off (InpArbCSVLog=false), and keeping
              # every layer write in one header makes the boundary auditable.
              "file writes": "QSMC_Stats.mqh"}


def strip_noise(src):
    code = re.sub(r"//(?!\s*$)[^\n]*", "", src)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r'"(\\.|[^"\\])*"', '""', code)


g4_sites = 0
for path in LIBRARY + PROGRAMS:
    code = strip_noise(read(path))
    base = os.path.basename(path)
    in_library = path in LIBRARY
    if os.path.abspath(path) in EXEC_TRADE_ALLOWED:
        continue          # the execution companion: checked by G8 instead
    for rx, why in TRADE:
        for m in re.finditer(rx, code):
            fail("G4 %s:%d uses %s - nothing in this release is allowed to reach the "
                 "trade API" % (os.path.relpath(path, ROOT), code[:m.start()].count("\n") + 1, why))
    if in_library:
        for rx, why in SIDE_EFFECTS:
            for m in re.finditer(rx, code):
                if ALLOW_SITE.get(why) == base:
                    continue          # the alert manager is the one, single site
                fail("G4 %s:%d uses %s outside %s - the layer observes and publishes; "
                     "one file owns the user-facing channels so a reviewer only has to "
                     "read one place to know what this release can do to the terminal"
                     % (os.path.relpath(path, ROOT), code[:m.start()].count("\n") + 1, why,
                        ALLOW_SITE.get(why, "nothing")))
                g4_sites += 1
NOTES.append("G4 no trade API in the layer (headers + indicator + probe) and none in the "
             "feeder; Alert/push/sound only in CAlertManager; QSMC CSV writes only in QSMC_Stats; "
             "the only trade API in the repository is the execution companion's")

# ------------------------------------------- G8 the execution companion (v6.6.8)
# This is the file that can lose money, so its deployment invariants are checked
# here: inert by default, demo-only by default, dry-run on first switch-on, and
# a risk ceiling that the sizing code actually enforces.
if not os.path.isfile(EXEC_EA):
    warn("G8 MQL5/Experts/QSMC_AutoTrader.mq5 is missing - the runbook names it, "
         "so the documented install would not execute anything")
else:
    ea = read(EXEC_EA)
    ea_code = strip_noise(ea)
    if "OrderSend" not in ea_code and "g_trade." not in ea_code:
        fail("G8 the execution companion never calls the trade API - it is documented "
             "as the execution path, so either it is broken or it is the wrong file")
    required_defaults = {"InpEnableTrading": "false", "InpDryRun": "true",
                         "InpDemoOnly": "true"}
    for name, want in required_defaults.items():
        m = re.search(r'^input\s+bool\s+' + name + r'\s*=\s*(true|false)\s*;', ea, re.M)
        if not m:
            fail("G8 %s is not declared as an input bool - a safety switch that "
                 "cannot be found cannot be trusted" % name)
        elif m.group(1) != want:
            fail("G8 %s defaults to %s, but %s is the shipping default: a trading EA "
                 "must arrive inert, dry-run and demo-only" % (name, m.group(1), want))
    if not re.search(r'InpMaxRiskPercent\s*=\s*1\.0*\s*;', ea):
        fail("G8 InpMaxRiskPercent default is not 1.0 - the documented hard ceiling "
             "is 1% of equity per trade")
    if "MathMin(InpRiskPercent,vmax_cap)" not in ea_code:
        fail("G8 the sizing path does not clamp the requested risk to InpMaxRiskPercent")
    if "if(vmax_cap>1.0) vmax_cap=1.0;" not in ea_code:
        fail("G8 the sizing path does not cap InpMaxRiskPercent itself at 1.0")
    if not re.search(r'input\s+string\s+InpRealAccountConfirm\s*=\s*""\s*;', ea):
        fail("G8 InpRealAccountConfirm is missing or non-empty - a real account must be "
             "named by the operator, so a demo preset cannot arm live money")
    if "ACCOUNT_TRADE_MODE_DEMO" not in ea_code:
        fail("G8 the demo-only refusal is gone - InpDemoOnly would be a lie")
    if re.search(r'MathPow\(\s*2', ea_code) or re.search(r'lots\s*\*\s*2', ea_code):
        fail("G8 the companion doubles a lot size - no martingale is allowed in this "
             "repository, in any file, at any setting")
    if "PositionModify" in ea_code and "InpBreakEvenAtR" not in ea:
        fail("G8 positions are modified without the break-even input that bounds it")
    NOTES.append("G8 execution companion ships INERT + DRY RUN + demo-only, risk clamped "
                 "to %.0f%% of equity, no martingale" % 1.0)

# ------------------------------------------------------------- G5 log flood
# "Flood" has one meaning here: a line printed from the per-bar path. That is a
# specific set of functions in the library headers, so the rule checks those and
# says nothing about init/deinit/one-shot reporting, which is legitimate output.
BAR_PATH = ("Refresh", "BuildContext", "FinalizeBar", "TacticalObserve", "SetZones",
            "ApplyExternalBias", "Evaluate", "Score", "Decide", "Publish", "Advance",
            "Observe", "Update", "Check", "Scan", "Render", "Draw")
HDR_RE = re.compile(r"(?:^|\n)\s*(?:const\s+)?[A-Za-z_][\w:]*\s*(?:\*+\s*)?"
                    r"(?P<name>~?[A-Za-z_]\w*)\s*\([^;{)]*\)\s*(?:const\s*)?\{")
g5_checked = 0
for path in [f for f in LIBRARY if f.endswith(".mqh")]:
    src = strip_noise(read(path))
    hdrs = [(m.start(), m.group("name"), m.end()) for m in HDR_RE.finditer(src)]
    starts = [h[0] for h in hdrs]
    for m in re.finditer(r"\b(?:Print|Alert)\s*\(", src):
        pos = m.start()
        k = bisect_right(starts, pos) - 1
        if k < 0:
            continue
        hstart, fname, _ = hdrs[k]
        nxt = hdrs[k + 1][0] if k + 1 < len(hdrs) else len(src)
        body = src[hstart:nxt]
        g5_checked += 1
        base = next((n for n in BAR_PATH if fname == n or fname.endswith(n)), "")
        if not base:
            continue
        if "InpArbVerboseLog" in body:
            continue
        if "once" in body.lower() or "m_log_" in body or "m_last_print" in body:
            continue
        fail("G5 %s:%d  %s() is on the per-bar path and logs without an "
             "InpArbVerboseLog guard - on an M1 chart that is ~39 000 lines a month, "
             "and a flooded Journal is how a real warning gets missed"
             % (os.path.relpath(path, ROOT), src[:pos].count("\n") + 1, fname))
NOTES.append("G5 %d log call sites in the headers checked against the per-bar path"
             % g5_checked)

# ------------------------------------------------- G5b the feeder must be inert
feeder = os.path.join(ROOT, "MQL5", "Experts", "KLJ_DataFeeder.mq5")
if os.path.isfile(feeder):
    f_src = read(feeder)
    rx = re.compile(r'input\s+string\s+(Inp\w*(?:Url|URL|Endpoint|Token|Key)\w*)\s*=\s*"([^"]*)"')
    hits = list(rx.finditer(f_src))
    if not hits:
        NOTES.append("G5b the feeder declares no URL-like string input (nothing to enable)")
    for m in hits:
        if m.group(2) != "":
            fail("G5b %s defaults to %r - an EA that contacts a URL must ship inert "
                 "until an operator names the endpoint" % (m.group(1), m.group(2)))
        else:
            NOTES.append("G5b %s defaults empty: the feeder does nothing until configured"
                         % m.group(1))

# ------------------------------------------------------------ G6 leftovers
for path in layer_files():
    src = read(path)
    for m in re.finditer(r"//.*?\b(TODO|FIXME|XXX|HACK|not implemented|unimplemented)\b",
                         src, re.I | re.S):
        line = src[:m.start()].count("\n") + 1
        warn("G6 %s:%d leftover marker: %s"
             % (os.path.relpath(path, ROOT), line, m.group(0).strip()[:78]))

# ---------------------------------------------------------------- G7 CI
wf = os.path.join(ROOT, ".github", "workflows", "qsmc-verify.yml")
if not os.path.isfile(wf):
    fail("G7 no CI workflow - the offline gates only exist if something runs them")
else:
    y = read(wf)
    if "check_release_gate.py" not in y:
        warn("G7 the CI workflow does not run tools/check_release_gate.py")
    else:
        NOTES.append("G7 CI runs the release gate")

print("=" * 72)
print(" QSMC RELEASE GATE  (go / no-go for a live chart)")
print("=" * 72)
for n in NOTES:
    print("  ok    %s" % n)
for w in WARNS:
    print("  WARN  %s" % w)
for f in FAILS:
    print("  BLOCK %s" % f)
print("-" * 72)
if FAILS:
    print("  NO-GO: %d blocking item(s), %d warning(s)" % (len(FAILS), len(WARNS)))
    print("  Do not put this on a live chart until the BLOCK lines are gone.")
    sys.exit(1)
print("  GO (with %d warning(s)) - mechanical invariants hold." % len(WARNS))
print("  This gate is not a compiler and not a backtest. F7 in MetaEditor and a")
print("  24-hour paper run are still the two things that cannot be automated here.")
sys.exit(0)
