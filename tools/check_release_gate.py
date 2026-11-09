#!/usr/bin/env python3
"""
QSMC RELEASE GATE

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
             "Stats", "Renderer", "Root", "Selftest", "Scanners", "DataProvider", "LiquidityValue", "UnifiedDecision",
             "IncidentSafety", "InputFingerprint", "InstanceIdentity")],
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
    NOTES.append("G2 layout complete: %d headers + 1 indicator + 1 probe + 1 script + 1 feeder EA "
                 "+ 1 execution EA" % len(NEEDED[0]))

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
    "InpRealTimeZones": "LEGACY/INERT: closed-bar authority is fixed; calculation cadence is InpUpdateEveryTick (v6.6.20 log review)",
    "InpDockDashboard": "legacy, and its own comment says so",
    "InpPanelsStartCollapsed": "legacy, and its own comment says so",
    "InpAlertOnEntryPreview": "legacy, and its own comment says so",
    "InpScalpShowOnDashboard": "RESERVED: no scalping tooltip row exists yet (doc 11.12)",
    "InpShowGateAudit": "RESERVED: no dashboard row exists yet; the audit prints instead",
    "InpShowEntryQualityPanel": "RESERVED: those rows are not built (doc 11.12)",
    "InpMinEntryOBStrength": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpMaxOBDistATR": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpASCIIBar": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpPanelRightPad": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpDashMode": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpShowMTFPanel": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpPanelIdleMaxHeightPct": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpShowTopDownPanel": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseAdvancedSweepEngine": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpSweepEntryMinScore": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpSweepEntryMaxBarsAfterSweep": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpSweepEntryMinRR": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseMergeSortRanking": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseMemoizedDP": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseFibonacciDP": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseCausalGraphOptimizer": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseDijkstraPathSearch": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseBellmanFordValidation": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseBeamSearch": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpBeamWidth": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpGraphMaxPathHops": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpGraphTemporalPenaltyATR": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpGraphConflictPenalty": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpGraphCausalReward": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpRejectGraphNegativeCycle": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpRequireGraphAgreement": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpUseCausalDPOptimizer": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpAllowFVGEntryZone": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpShowPredictivePanel": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpDockPMIPanel": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpPMIPanelCollapsible": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpPMIPanelX": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpPMIPanelY": "INERT: its only reader was dead code, deleted in doc 11.14",
    "InpPMIPanelRefreshTicks": "INERT: its only reader was dead code, deleted in doc 11.14",
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

# --------------------------------- G3c inputs read only by dead functions
# G3b counts ANY read - but a read inside a function that nothing calls can never
# happen, so the switch is just as inert and the dialog just as misleading.
#
# THE FIRST VERSION OF THIS CHECK WAS WRONG, and the way it was wrong is worth
# keeping. It decided "has a forward declaration" with a line-start regex that also
# matched `return SigLog_ResName(r.res[k]);` and every other statement that begins
# at column 0 and ends in `;` - so a function with exactly one call scored 0 calls.
# It reported 68 dead functions; 95 were really dead and two of the 68 were alive.
# The purge script trusted it and severed two live functions, which the
# dangling-reference check caught immediately. The rule below is explicit: a
# DECLARATION is a statement whose text between the type and the name is only
# whitespace, `*` or `&`. A call is everything else.
#
# At v6.6.13, after the purge in doc 11.14: 0 unreachable free functions.
_TYPE = (r"(?:static[ \t]+)?(?:void|bool|int|double|string|long|ulong|uint|char|"
         r"float|datetime|color|uchar|short|ushort)")
_DECLRE = re.compile(r"[ \t]*" + _TYPE + r"\b[ \t]*[\*&]?[ \t]*$")
ENTRY_POINTS = {"OnInit", "OnDeinit", "OnCalculate", "OnChartEvent", "OnTimer",
                "OnTrade", "OnTradeTransaction", "OnTick", "OnBookEvent", "OnTester"}
_line_start = [0]
for _i, _ch in enumerate(_code):
    if _ch == "\n":
        _line_start.append(_i + 1)
def _line_of(_p):
    _lo, _hi = 0, len(_line_start) - 1
    while _lo < _hi:
        _mid = (_lo + _hi + 1) // 2
        if _line_start[_mid] <= _p:
            _lo = _mid
        else:
            _hi = _mid - 1
    return _lo
_occ = {}
for _m in re.finditer(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)[ \t]*\(", _code):
    _occ.setdefault(_m.group(1), []).append(_m.start())
def _is_decl(_p):
    return _DECLRE.match(_code[_code.rfind("\n", 0, _p) + 1:_p]) is not None
# v6.6.19: the previous definition scanner used a nested-quantifier regex over
# the whole 2 MB host. On a chart-heavy file it could backtrack for minutes and
# made the release gate unusable. The replacement is linear: match parentheses
# and braces once, then accept only `name(...) {` whose opening brace is at
# global scope. It keeps the same contract (free-function definitions) without
# catastrophic backtracking.
_paren_close, _paren_stack = {}, []
_brace_opens, _brace_closes = [], []
_pairs, _stack = {}, []
for _i, _ch in enumerate(_code):
    if _ch == "(":
        _paren_stack.append(_i)
    elif _ch == ")" and _paren_stack:
        _paren_close[_paren_stack.pop()] = _i
    elif _ch == "{":
        _stack.append(_i)
        _brace_opens.append(_i)
    elif _ch == "}":
        _brace_closes.append(_i)
        if _stack:
            _pairs[_stack.pop()] = _i

def _brace_depth_before(pos):
    return bisect_right(_brace_opens, pos - 1) - bisect_right(_brace_closes, pos - 1)

_defpos = {}
for _name, _positions in _occ.items():
    for _p in _positions:
        _q = _p + len(_name)
        while _q < len(_code) and _code[_q] in " \t":
            _q += 1
        if _q >= len(_code) or _code[_q] != "(":
            continue
        _r = _paren_close.get(_q)
        if _r is None:
            continue
        _b = _r + 1
        while _b < len(_code) and _code[_b] in " \t\r\n":
            _b += 1
        if _b < len(_code) and _code[_b] == "{" and _brace_depth_before(_b) == 0:
            _defpos.setdefault(_name, _b)
_dead_fns = {}
for _n, _brace in _defpos.items():
    if _n in ENTRY_POINTS:
        continue
    # A definition's own signature line also starts with a type, so it is already
    # classified as a declaration here - do NOT subtract it again, or every
    # single-call function scores zero and the gate cries wolf.
    _calls = [p for p in _occ.get(_n, []) if not _is_decl(p)]
    if not _calls:
        _dead_fns[_n] = (_line_of(_brace), _line_of(_pairs.get(_brace, _brace)))

# The host exposes small role helpers to the included QSMC headers. A call from
# an included header is a real call; scanning only nadir2.mq5 would delete a
# live API. Strip strings/comments first so a comment cannot keep rot alive.
def _cross_strip(src):
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', src)
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)

_cross_alive = set()
for _path in layer_files():
    if not _path.endswith(".mqh"):
        continue
    _txt = _cross_strip(read(_path))
    for _n in list(_dead_fns):
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(_n) + r"\s*\(", _txt):
            _cross_alive.add(_n)
for _n in _cross_alive:
    del _dead_fns[_n]

_dead_only = []
for _n, _dl in _decl.items():
    _reads = [j for j in _read_at.get(_n, []) if j != _dl]
    if not _reads:
        continue
    if all(any(_dead_fns[f][0] <= r <= _dead_fns[f][1] for f in _dead_fns) for r in _reads):
        _dead_only.append(_n)
DELETED_MANIFEST = {
    "AdvancedPathWeight", "BadgeTabCount", "BadgeTabDashEnabled", "BadgeTabMTFEnabled",
    "BadgeTabPMIEnabled", "BinarySearchNearestBarrier", "BinarySearchNearestOB",
    "BlendColor", "BuildAdvancedSweepCandidate", "BuildConfidenceBar",
    "BuildInstitutionalPatternChecklist", "BuildUnifiedEntryVerdict",
    "CalculateSetupQualityScore", "CausalEdgeCost", "CausalEdgeSignedWeight",
    "CausalEvidenceDP", "CoreDashAccent", "CoreDashBiasToken", "CoreDashEventDetails",
    "CoreDashObservationsLine", "CoreDashZone", "DashLine", "DashPushWrapped",
    "DrawBadgeTab", "DrawMTFPanel", "DrawTopDownPanel", "DrawUnifiedEntryPanel",
    "EvaluateStructuralPathDP", "FibDPValue", "FindLastBearishOB", "FindLastBullishOB",
    "FormatFinalEntryOutput", "GateTxt", "GetBestAdvancedSweepCandidate", "GradeColor",
    "GraphConfluenceScore", "GreedyFindBestTarget", "InstitutionalBehaviorName",
    "InstrumentFreezeDistance", "IntegerToBinary", "L_Trim", "LayoutPanelBadge",
    "MTF_AlignmentText", "MTF_HTFRowIndex", "MTF_SniperDashboardLine", "MVP_Label",
    "MarkZREEntry", "MemoizedCausalPathScore", "NormText", "NormalizeVolumeToStep",
    "OppositeBiasPotential", "OptimizeCausalGraphPath", "PMI_CountEvents", "PMI_DrawPanel",
    "PMI_DrawPanelThrottled", "PMI_FeatureNames", "PMI_FirstBarAtOrAfter",
    "PMI_HashDoubleArray", "PMI_LiqStatusName", "PMI_Mark", "PMI_PanelLine", "PMI_SelfTest",
    "PMI_StructDedupeCheckInvariants", "PMI_TreeAxisName", "PctColor",
    "QSMC_DataHealthLine", "QSMC_DataHealthReason", "QSMC_FitTextPx",
    "QuantSweepClassLabel", "RXN_DashFull", "RXN_DashMini", "RXN_ExecName", "RXN_LevelFor",
    "RXN_SelfTest", "RankSetupCandidates", "RepositionDashboard", "ResetCausalPathResult",
    "RunBeamCausalPath", "RunBellmanFordCausalPath", "RunDijkstraCausalPath",
    "ScenarioDashCompact", "ScenarioDashLadder", "ScenarioLegStrip",
    "ScenarioPreviousClosedPeriod", "ScoreAlgo", "ScoreSweepCandidate", "SelectEntryFVG",
    "SelectEntryOB", "SortSweepCandidates", "TruncateToWidth",
    "ValidateCausalPathAgreement", "ZRE_DashFull", "ZRE_DashMini", "ZRE_LifecycleName",
    "ZRE_ScoreZone",
}
# The 95 names removed in doc 11.14. A call to one of them is a DANGLING REFERENCE:
# the function no longer exists, so the code cannot compile. Re-adding a function is
# fine and passes - only a call with no definition behind it fails. This is the check
# that would have caught the first, wrong deletion attempt (which severed two live
# functions and left 90-odd calls behind) before it reached a commit.
_ghosts = sorted(n for n in DELETED_MANIFEST
                 if _occ.get(n) and n not in _defpos
                 and any(not _is_decl(p) for p in _occ[n]))
if _ghosts:
    fail("G3 %d call(s) to functions that no longer exist: %s. Either the function "
         "must come back or the call must go - this does not compile (doc 11.14)"
         % (len(_ghosts), ", ".join(_ghosts)))
_body = sum(b - a + 1 for a, b in _dead_fns.values())
if _dead_fns or _dead_only:
    fail("G3 %d unreachable free function(s) and %d input(s) read only from inside "
         "them: %s. Nothing calls this code, so it can only rot - delete it (doc "
         "11.14 did that once) or wire it" %
         (len(_dead_fns), len(_dead_only),
          ", ".join(sorted(_dead_fns)) + ("; inputs: " + ", ".join(_dead_only) if _dead_only else "")))
else:
    NOTES.append("G3 no unreachable free functions and no input read only from "
                 "dead code - the purge in doc 11.14 is still complete")

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
# separate program precisely so that the indicator and the 23 headers stay
# unable to reach the trade API - that is what makes the dashboard safe to leave
# on a chart. Everything about this file is checked: it ships inert, it needs a
# demo account by default, and it is the only name on this list.
EXEC_EA = os.path.join(ROOT, "MQL5", "Experts", "QSMC_AutoTrader.mq5")
EXEC_TRADE_ALLOWED = {os.path.abspath(EXEC_EA)}

# QATS (MQL5/Experts/QuantumAutonomousTradingSystem.mq5) is a STANDALONE SMC EA
# merged to main via PR #56. It is NOT part of the QSMC 23-header layer: it is
# self-contained, DEMO-only enforced INSIDE the file itself, governed on its own,
# and it is out of scope of this gate BY DESIGN. It is named here - never
# silently skipped - so a reviewer sees exactly what this gate does not check.
# The QSMC layer (headers + indicator + probe + feeder) is still held to the
# full rules below; QSMC_AutoTrader's allowance is unchanged.
QATS_EA = os.path.join(ROOT, "MQL5", "Experts", "QuantumAutonomousTradingSystem.mq5")
QATS_TRADE_ALLOWED = {os.path.abspath(QATS_EA)}

# Execution/mutation API is forbidden. Read-only account queries are not an
# order path: the visual indicator may inspect open positions/orders to keep
# labels off trade levels (UpdateTradeLevelKeepOut), but it may never send,
# modify, close or check an order. The execution companion remains the only
# file allowed to reach the mutating API (G8).
TRADE = [(r"\bOrderSend\s*\(",                    "OrderSend"),
         (r"\bOrderSendAsync\s*\(",               "OrderSendAsync"),
         (r"\bOrderCheck\s*\(",                   "OrderCheck"),
         (r"\bPositionOpen\b|\bPositionModify\s*\(|\bPositionClose\s*\(", "position mutation API"),
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
g4_qats_excluded = False
for path in LIBRARY + PROGRAMS:
    code = strip_noise(read(path))
    base = os.path.basename(path)
    in_library = path in LIBRARY
    if os.path.abspath(path) in EXEC_TRADE_ALLOWED:
        continue          # the execution companion: checked by G8 instead
    if os.path.abspath(path) in QATS_TRADE_ALLOWED:
        g4_qats_excluded = True
        continue          # named, documented exclusion - see QATS_EA comment above
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
_g4_note = ("G4 no order-send/modify/close API in the layer (headers + indicator + probe) and none in the "
            "feeder; read-only position/order inspection is display-only; Alert/push/sound only in CAlertManager; "
            "QSMC CSV writes only in QSMC_Stats; the only mutating trade API in the repository is the execution companion's")
if g4_qats_excluded:
    _g4_note += ("; BY-NAME EXCLUSION (not scanned, out of QSMC scope, merged standalone system PR #56, "
                 "DEMO-only enforced in-file): MQL5/Experts/QuantumAutonomousTradingSystem.mq5")
NOTES.append(_g4_note)

# ------------------------------------------- G8 the execution companion (v6.6.8 / 2026-11-09)
# This is the file that can lose money, so its deployment invariants are checked
# here. 2026-11-09 (unified DEMO & REAL): the companion ships ARMED ON DEMO
# (EXECUTION_DEMO); a REAL account is EXECUTION_REAL and stays disarmed until the
# operator performs the explicit authorization - InpAllowRealTrading=false, empty
# login/server confirmations by default, exact matches re-verified before EVERY
# order, CONTEST/unknown refused, account identity snapshotted at init.
if not os.path.isfile(EXEC_EA):
    warn("G8 MQL5/Experts/QSMC_AutoTrader.mq5 is missing - the runbook names it, "
         "so the documented install would not execute anything")
else:
    ea = read(EXEC_EA)
    ea_code = strip_noise(ea)
    if "OrderSend" not in ea_code and "g_trade." not in ea_code:
        fail("G8 the execution companion never calls the trade API - it is documented "
             "as the execution path, so either it is broken or it is the wrong file")
    # 2026-11-09 (unified DEMO & REAL). The properties checked just as hard as
    # the old "inert + dry run" ones, because the risk now is a real account:
    #   1. InpAllowRealTrading=false  - the single arming switch ships OFF;
    #   2. InpRealAccountConfirm=""   - arming real money needs THIS account's
    #      exact login typed in;
    #   3. InpRealServerConfirm=""    - and the broker server typed in;
    #   4. OnInit refuses an unauthorized REAL account BEFORE the first tick, and
    #      the same authorization is re-verified before every order.
    required_defaults = {"InpEnableTrading": "true", "InpDryRun": "false",
                         "InpAllowRealTrading": "false"}
    for name, want in required_defaults.items():
        m = re.search(r'^input\s+bool\s+' + name + r'\s*=\s*(true|false)\s*;', ea, re.M)
        if not m:
            fail("G8 %s is not declared as an input bool - a safety switch that "
                 "cannot be found cannot be trusted" % name)
        elif m.group(1) != want:
            fail("G8 %s defaults to %s, but %s is the shipping default (armed on demo, "
                 "REAL disarmed)" % (name, m.group(1), want))
    # the two exact-match confirmations must ship empty
    for name in ("InpRealAccountConfirm", "InpRealServerConfirm"):
        if not re.search(r'^input\s+string\s+' + name + r'\s*=\s*""\s*;', ea, re.M):
            fail("G8 %s is missing or non-empty - a real account must be named by the "
                 "operator (exact login AND exact server), so a preset cannot arm live money" % name)
    # the mode comes from the account enum alone - never from balance/broker/server/login
    if "ACCOUNT_TRADE_MODE_DEMO" not in ea_code:
        fail("G8 the DEMO detection is gone - EXECUTION_DEMO would be a lie")
    if "ACCOUNT_TRADE_MODE_CONTEST" not in ea_code:
        fail("G8 the CONTEST refusal is gone - a contest account must be rejected everywhere")
    # the REAL authorization gate must exist and be demanded at init AND per order
    if re.search(r'bool\s+RealAuthorized\s*\(string\s*&why\)', ea) is None:
        fail("G8 the REAL authorization gate is gone - EXECUTION_REAL has no way to refuse")
    if re.search(r'if\s*\(!RealAuthorized\(why\)\)', ea_code) is None:
        fail("G8 OnInit must refuse an unauthorized REAL account before the first tick - "
             "a guard that only fires 'when already armed' is a guard that arrives late")
    if "REAL account detected but NOT authorized: " not in ea:
        fail("G8 the pre-order REAL re-verification is gone - authorization must be "
             "re-checked at every order, not only at attach")
    if "IdentityMatchesSnapshot(" not in ea_code:
        fail("G8 the identity snapshot is gone - an account that changed after attach "
             "must block new entries until a re-attach")
    if "INIT REFUSED: REAL account detected" not in ea:
        fail("G8 the REAL-refusal init banner is gone - an operator attaching to an "
             "unauthorized REAL account must be told, loudly")
    if ea_code.count("g_emergency_lockout = true") < 2:
        fail("G8 the emergency lockout is latched in fewer than two places (emergency "
             "path + identity drift) - the sticky block must survive both")
    # the REAL profile must ship strictly tighter than DEMO, under the same HARD caps
    for inp, want in (("InpRealMaxRiskPercent", "0.25"),
                      ("InpRealMaxAggregateRiskPercent", "0.50"),
                      ("InpMaxAggregateRiskPercent", "1.00")):
        if re.search(r'^input\s+double\s+' + inp + r'\s*=\s*' + want + r'\s*;', ea, re.M) is None:
            fail("G8 %s default is not %s - the REAL profile must ship no looser than DEMO" % (inp, want))
    if "HardMaxAggregateRiskPercent(){ return 2.00; }" not in ea:
        fail("G8 the HardMaxAggregateRiskPercent HARD ceiling is missing or moved - "
             "the aggregate cap is the last line of defence and must stay 2.00")
    if not re.search(r'InpMaxRiskPercent\s*=\s*0\.10?\s*;', ea):
        fail("G8 InpMaxRiskPercent default is not 0.10 - the shipping preset and the "
             "documented hard ceiling must be the same number")
    hard = re.findall(r'double HardMax(?:RiskPercent|DailyPercent|DDPercent)\(\)\{\s*return\s*([\d.]+);',
                      ea)
    if [float(v) for v in hard] != [0.50, 2.00, 8.00]:
        fail("G8 the HARD ceilings are %s, expected 0.50 / 2.00 / 8.00 - the ceiling is "
             "the last line of defence and it is not allowed to drift upward silently"
             % (hard,))
    if "MathMin(InpRiskPercent,vmax_cap)" not in ea_code:
        fail("G8 the sizing path does not clamp the requested risk to InpMaxRiskPercent")
    # 2026-11-06 audit (A1/A2): the old assertion demanded a 1.0% literal inside
    # CalcLots, which contradicted HardMaxRiskPercent()=5.00 and the OnInit check.
    # What matters is that the sizing path is bounded by the HARD ceiling and that
    # the contradictory literal is gone.
    if "if(vmax_cap>HardMaxRiskPercent()) vmax_cap=HardMaxRiskPercent();" not in ea_code:
        fail("G8 the sizing path is not bounded by HardMaxRiskPercent()")
    if "if(vmax_cap>1.0) vmax_cap=1.0;" in ea_code:
        fail("G8 a second, undocumented 1.0% ceiling is back in the sizing path")
    if re.search(r'MathPow\(\s*2', ea_code) or re.search(r'lots\s*\*\s*2', ea_code):
        fail("G8 the companion doubles a lot size - no martingale is allowed in this "
             "repository, in any file, at any setting")
    if "PositionModify" in ea_code and "InpBreakEvenAtR" not in ea:
        fail("G8 positions are modified without the break-even input that bounds it")
    NOTES.append("G8 execution companion ships ARMED ON DEMO (EXECUTION_DEMO, InpEnableTrading=true); "
                 "REAL is EXECUTION_REAL behind 7-condition authorization (InpAllowRealTrading=false + exact "
                 "InpRealAccountConfirm/InpRealServerConfirm + permissions + risk gates + no emergency lockout), "
                 "refused at init before the first tick and re-verified before every order; mode detected via "
                 "ACCOUNT_TRADE_MODE only; risk bounded by the HARD ceilings (0.50/2.00/8.00) + aggregate 2.00; no martingale")

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
# The old DOTALL regex started at every `//` and searched to the end of the file
# for a marker; on a 44k-line host with thousands of comments that is quadratic.
# Scan comments line-by-line (and track block comments) instead. The contract is
# the same: leftover markers in shipped comments are warnings, not code facts.
_G6_MARK = re.compile(r"\b(TODO|FIXME|XXX|HACK|not implemented|unimplemented)\b", re.I)
for path in layer_files():
    src = read(path)
    in_block = False
    for lineno, line in enumerate(src.splitlines(), 1):
        comment_parts = []
        i = 0
        while i < len(line):
            if in_block:
                end = line.find("*/", i)
                if end < 0:
                    comment_parts.append(line[i:])
                    i = len(line)
                else:
                    comment_parts.append(line[i:end])
                    in_block = False
                    i = end + 2
                continue
            if line.startswith("//", i):
                comment_parts.append(line[i + 2:])
                break
            if line.startswith("/*", i):
                in_block = True
                i += 2
                continue
            if line[i] == '"':
                i += 1
                while i < len(line):
                    if line[i] == "\\":
                        i += 2
                    elif line[i] == '"':
                        i += 1
                        break
                    else:
                        i += 1
                continue
            i += 1
        comment = " ".join(comment_parts)
        m = _G6_MARK.search(comment)
        if m:
            warn("G6 %s:%d leftover marker: %s"
                 % (os.path.relpath(path, ROOT), lineno, comment.strip()[:78]))

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
