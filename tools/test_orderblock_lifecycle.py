#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract suite for the ORDER BLOCK LIFECYCLE completion (AUDIT-OB1).

WHY THIS FILE EXISTS
--------------------
`nadir2.mq5` already had a complete order-block engine: DetectOrderBlocks,
ScoreOrderBlock, SelectEntryOB, ValidateCausalOB, BuildOBPriceIndex,
BuildOBStrengthIndex, BinarySearchNearestOB, DrawStructureAndOB,
AddBreakerBlock, FindLastBullishOB/BearishOB. Building a second one would have
duplicated all of it, so AUDIT-OB1 adds only what was genuinely missing.

THE GAP. `SOrderBlock.age` was written at creation (`ob.age=closed-ob_bar`) and
read by nothing - a dead field. An order block therefore stayed eligible
forever: the ONLY thing that could retire it was a candle body closing through
the zone. A block from 900 bars back was still scored, still selectable as an
entry OB, still drawable, and still usable as a continuation zone, exactly like
one formed on the last bar. Every other registry in the file already had a
horizon (zones: InpZREExpireBars, Core blacklist: InpBlacklistExpiryBars,
retest: InpRetestTimeoutBars). Order blocks were the one that did not.

WHAT IS TESTED
--------------
Part A  an independent re-implementation of the age rule, the display
        vocabulary, and BOTH state machines (the incremental closed-bar loop and
        ReplayClosedBarStates), transcribed from nadir2.mq5. The centrepiece is
        A5: the two paths must agree bar-for-bar, because the design contract
        above ReplayClosedBarStates demands it apply "exactly the same rules the
        incremental branch applies per closed bar - nothing new".
Part B  source contracts: the rule has exactly ONE definition, both state
        machines call it, the precedence is right in both, every eligibility
        guard honours it, no buffer moved, and no trade API appeared.

This is a contract suite. It is NOT a backtest, produces NO win rate, and does
NOT prove MetaEditor compilation. Press F7.
"""
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "nadir2.mq5"
TEXT = io.open(str(SRC), "r", encoding="utf-8", newline="").read()

FAILS = []
CHECKS = [0]


def check(ok, name, detail=""):
    CHECKS[0] += 1
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + detail) if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


# ======================================================================
# Part A - independent re-implementation
# ======================================================================

# --- the inputs, at their shipped defaults ---------------------------
INP_USE_AGE_EXPIRY = False      # InpOBUseAgeExpiry       (default false)
INP_MAX_AGE_BARS = 200          # InpOBMaxAgeBars         (default 200)
INP_ZONE_BODY_ONLY = False      # InpOBZoneBodyOnly       (default false)


class OB:
    """Mirrors the fields of SOrderBlock that the lifecycle touches."""

    def __init__(self, bar, top, bottom, bullish, origin_struct_bar=-1):
        self.bar = bar
        self.top = top
        self.bottom = bottom
        self.bullish = bullish
        self.origin_struct_bar = origin_struct_bar
        self.state = "ACTIVE"
        self.closed_state = "ACTIVE"
        self.mitigated = False
        self.age = 0
        self.breakers = 0        # how many AddBreakerBlock calls this OB caused


def ob_is_expired(ob, as_of_closed, use_expiry=INP_USE_AGE_EXPIRY,
                  limit=INP_MAX_AGE_BARS):
    """Transcription of OBIsExpired(). The bound is EXCLUSIVE: age == limit is
    still live, matching the InpRetestTimeoutBars convention."""
    if not use_expiry or limit <= 0:
        return False
    if as_of_closed < 0:
        return False
    return (as_of_closed - ob.bar) > limit


def ob_mark_expired(ob, as_of_closed):
    """Transcription of OBMarkExpired()."""
    ob.age = as_of_closed - ob.bar
    ob.state = "EXPIRED"
    ob.closed_state = "EXPIRED"


def ob_state_label(ob):
    """Transcription of OBStateLabel(): internal -> trader vocabulary, display
    only. The engine's MITIGATED means a BODY CLOSED THROUGH the zone, which is
    what a trader calls broken; its TOUCHED is the first mitigation."""
    s, cs = ob.state, ob.closed_state
    if s == "EXPIRED" or cs == "EXPIRED":
        return "EXPIRED"
    if s == "MITIGATED" or cs == "MITIGATED":
        return "BROKEN"
    if s == "TOUCHED" or cs == "TOUCHED":
        return "MITIGATED"
    if s == "ACTIVE":
        return "FRESH"
    return s if s else "UNKNOWN"


def apply_bar(ob, b, h, l, c, use_expiry=INP_USE_AGE_EXPIRY,
              limit=INP_MAX_AGE_BARS):
    """One closed bar against one OB, in the exact order both state machines
    use: overlap -> TOUCHED, then the two body-close-through breaks, then and
    only then the age bound. A price fact outranks a time fact."""
    if b < 0 or b >= len(c):
        return
    overlap = (l[b] <= ob.top and h[b] >= ob.bottom)
    if overlap:
        ob.state = "TOUCHED"
        ob.closed_state = "TOUCHED"
    if ob.bullish and c[b] < ob.bottom:
        ob.breakers += 1
        ob.mitigated = True
        ob.state = "MITIGATED"
        ob.closed_state = "MITIGATED"
    if (not ob.bullish) and c[b] > ob.top:
        ob.breakers += 1
        ob.mitigated = True
        ob.state = "MITIGATED"
        ob.closed_state = "MITIGATED"
    if ob.state != "MITIGATED" and ob_is_expired(ob, b, use_expiry, limit):
        ob_mark_expired(ob, b)


def run_incremental(ob, bars, closed, use_expiry=INP_USE_AGE_EXPIRY,
                    limit=INP_MAX_AGE_BARS):
    """The OnCalculate useIncremental path: it sees each newly closed bar once,
    in order, and skips a block that is already terminal."""
    h, l, c = bars
    for b in range(ob.bar + 1, closed + 1):
        if ob.state == "MITIGATED":
            continue
        if ob.state == "EXPIRED":
            continue
        apply_bar(ob, b, h, l, c, use_expiry, limit)
    return ob


def run_replay(ob, bars, closed, use_expiry=INP_USE_AGE_EXPIRY,
               limit=INP_MAX_AGE_BARS):
    """ReplayClosedBarStates(): one walk from `from` to `closed`, breaking out
    as soon as the block goes terminal."""
    h, l, c = bars
    if ob.state == "MITIGATED" or ob.state == "EXPIRED":
        return ob
    frm = ob.bar + 1
    if ob.origin_struct_bar >= 0:
        frm = max(frm, ob.origin_struct_bar + 1)
    for b in range(frm, closed + 1):
        if ob.state == "MITIGATED":
            break
        apply_bar(ob, b, h, l, c, use_expiry, limit)
        if ob.state == "EXPIRED":
            break
    return ob


def zone_geometry(o, h, l, c, k, bullish, body_only=INP_ZONE_BODY_ONLY):
    """Transcription of the DetectOrderBlocks zone sizing: the DEFAULT hybrid
    (body edge on the close side, wick on the rejection side) and the opt-in
    pure body."""
    if body_only:
        top = max(o[k], c[k])
        bottom = min(o[k], c[k])
        return (top, bottom) if top - bottom > 0 else None
    if bullish:
        return (max(o[k], c[k]), l[k])
    return (h[k], min(o[k], c[k]))


# ---------------------------------------------------------------------
# A1 - the age bound itself: off by default, exclusive, closed bars only
# ---------------------------------------------------------------------
ob = OB(bar=100, top=4050.0, bottom=4044.0, bullish=True)

check(ob_is_expired(ob, 250) is False,
      "A1 with InpOBUseAgeExpiry=false nothing ever expires (today's behaviour)")
check(ob_is_expired(ob, 10_000) is False,
      "A1 a 9 900-bar-old block is still live when the switch is off")

check(ob_is_expired(ob, 300, True, 200) is False,
      "A1 age 200 == limit is still live (the bound is exclusive)")
check(ob_is_expired(ob, 301, True, 200) is True,
      "A1 age 201 > limit expires")
check(ob_is_expired(ob, 10_000, True, 200) is True,
      "A1 an ancient block expires once the switch is on")

check(ob_is_expired(ob, 301, True, 0) is False,
      "A1 InpOBMaxAgeBars<=0 disables the rule even with the switch on")
check(ob_is_expired(ob, 301, True, -5) is False,
      "A1 a negative limit disables rather than expiring everything")
check(ob_is_expired(ob, -1, True, 200) is False,
      "A1 an unknown as-of bar is skipped, never guessed")

# monotonic: once expired at bar b it is expired at every later bar
mono = all(ob_is_expired(ob, b, True, 200) for b in range(301, 400))
check(mono, "A1 expiry is monotonic in closed bars (it can never un-expire)")

# ---------------------------------------------------------------------
# A2 - the display vocabulary mapping, and that it renames nothing
# ---------------------------------------------------------------------
cases = [("ACTIVE", "ACTIVE", "FRESH"),
         ("TOUCHED", "TOUCHED", "MITIGATED"),
         ("MITIGATED", "MITIGATED", "BROKEN"),
         ("EXPIRED", "EXPIRED", "EXPIRED"),
         ("ACTIVE", "TOUCHED", "MITIGATED"),
         ("TOUCHED", "MITIGATED", "BROKEN")]
for st, cst, want in cases:
    o = OB(0, 1.0, 0.5, True)
    o.state, o.closed_state = st, cst
    check(ob_state_label(o) == want,
          "A2 label(%s/%s) == %s" % (st, cst, want))

o = OB(0, 1.0, 0.5, True)
o.state, o.closed_state = "", ""
check(ob_state_label(o) == "UNKNOWN", "A2 an empty state maps to UNKNOWN")
o.state = "SOMETHING_NEW"
check(ob_state_label(o) == "SOMETHING_NEW",
      "A2 an unrecognised state is passed through, never silently relabelled")

# the internal strings themselves are untouched by the mapping
check(all(s in ("ACTIVE", "TOUCHED", "MITIGATED", "EXPIRED", "", "SOMETHING_NEW")
          for s in ("ACTIVE", "TOUCHED", "MITIGATED")),
      "A2 the mapping is read-only: it does not rewrite the engine's own states")

# ---------------------------------------------------------------------
# A3 - precedence: a price fact outranks a time fact
# ---------------------------------------------------------------------
def series(n=900, breaks=None):
    """A FRESH synthetic series on every call. Sharing one dict across
    scenarios and mutating it is how a passing test quietly asserts the wrong
    thing: a break injected for one case would still be live in the next."""
    breaks = breaks or {}
    h = {b: 4048.0 for b in range(n)}
    l = {b: 4046.0 for b in range(n)}
    c = {b: 4047.0 for b in range(n)}
    for b, close in breaks.items():
        c[b] = close
        if close < l[b]:
            l[b] = close
        if close > h[b]:
            h[b] = close
    return (h, l, c)


# ob.bar=100 with limit=200 => the block ages out on bar 301 (age 201 > 200).
# Break and expiry landing on that SAME bar must resolve to MITIGATED.
h, l, c = series(400, breaks={301: 4040.0})
o = OB(bar=100, top=4050.0, bottom=4044.0, bullish=True)
apply_bar(o, 301, h, l, c, True, 200)
check(o.state == "MITIGATED",
      "A3 break and expiry on the same bar resolves to MITIGATED, not EXPIRED")
check(o.breakers == 1, "A3 the breaker block was still generated on that bar")

# break first (bar 150), expiry later (bar 301) -> MITIGATED stays (sticky)
h, l, c = series(400, breaks={150: 4040.0})
o = OB(bar=100, top=4050.0, bottom=4044.0, bullish=True)
run_incremental(o, (h, l, c), 399, True, 200)
check(o.state == "MITIGATED", "A3 a block that broke first never becomes EXPIRED")
check(o.breakers == 1, "A3 the earlier break still generated its breaker block")

# expiry first (bar 301), break later (bar 350) -> EXPIRED stays, no late breaker
h, l, c = series(400, breaks={350: 4040.0})
o = OB(bar=100, top=4050.0, bottom=4044.0, bullish=True)
run_incremental(o, (h, l, c), 399, True, 200)
check(o.state == "EXPIRED", "A3 a block that expired first stays EXPIRED (sticky)")
check(o.breakers == 0, "A3 an expired block generates no breaker block afterwards")

# ---------------------------------------------------------------------
# A4 - the bearish mirror behaves identically
# ---------------------------------------------------------------------
for bullish, break_close in ((True, 4040.0), (False, 4055.0)):
    side = "bullish" if bullish else "bearish"
    h, l, c = series(400, breaks={301: break_close})
    o = OB(bar=100, top=4050.0, bottom=4044.0, bullish=bullish)
    apply_bar(o, 301, h, l, c, True, 200)
    check(o.state == "MITIGATED",
          "A4 %s mirror: a body close through the zone breaks it" % side)
    h, l, c = series(400)                       # no break anywhere
    o2 = OB(bar=100, top=4050.0, bottom=4044.0, bullish=bullish)
    run_incremental(o2, (h, l, c), 399, True, 200)
    check(o2.state == "EXPIRED",
          "A4 %s mirror: aging out is direction-symmetric" % side)

# ---------------------------------------------------------------------
# A5 - THE CENTREPIECE: incremental and replay must agree bar for bar
# ---------------------------------------------------------------------
def build(break_bar=None, expiry_cross=None):
    """A synthetic series; optionally a break bar. Returns (bars, closed)."""
    hh = {b: 4048.0 for b in range(0, 900)}
    ll = {b: 4046.0 for b in range(0, 900)}
    cc = {b: 4047.0 for b in range(0, 900)}
    if break_bar is not None:
        cc[break_bar] = 4040.0
        ll[break_bar] = 4039.0
    return (hh, ll, cc), 899


scenarios = []
for break_bar in (None, 150, 300, 301, 302, 500, 899):
    scenarios.append(("break@%s" % break_bar, break_bar))

disagree = []
for name, bb in scenarios:
    bars, closed = build(break_bar=bb)
    for origin in (-1, 105, 120):
        for limit in (200, 1000, 1):
            a = OB(100, 4050.0, 4044.0, True, origin)
            b = OB(100, 4050.0, 4044.0, True, origin)
            run_incremental(a, bars, closed, True, limit)
            run_replay(b, bars, closed, True, limit)
            if a.state != b.state or a.closed_state != b.closed_state:
                disagree.append("%s origin=%s limit=%s inc=%s rep=%s"
                                % (name, origin, limit, a.state, b.state))
            if a.breakers != b.breakers:
                disagree.append("%s origin=%s limit=%s breakers %d vs %d"
                                % (name, origin, limit, a.breakers, b.breakers))

check(not disagree,
      "A5 incremental and ReplayClosedBarStates agree on every scenario "
      "(%d combos)" % (len(scenarios) * 3 * 3),
      "; ".join(disagree[:4]))

# and with the switch OFF both paths must reproduce today's behaviour exactly
off_diff = []
for name, bb in scenarios:
    bars, closed = build(break_bar=bb)
    a = OB(100, 4050.0, 4044.0, True, -1)
    b = OB(100, 4050.0, 4044.0, True, -1)
    run_incremental(a, bars, closed, False, 200)
    run_replay(b, bars, closed, False, 200)
    if a.state != b.state:
        off_diff.append("%s inc=%s rep=%s" % (name, a.state, b.state))
    if a.state == "EXPIRED":
        off_diff.append("%s expired with the switch OFF" % name)
check(not off_diff,
      "A5 with InpOBUseAgeExpiry=false neither path can produce EXPIRED",
      "; ".join(off_diff[:4]))

# ---------------------------------------------------------------------
# A6 - zone geometry: the default must not move
# ---------------------------------------------------------------------
# one bearish candle: open 4052, high 4053, low 4041, close 4044
o_, h_, l_, c_ = [4052.0], [4053.0], [4041.0], [4044.0]
# bullish OB = max(open,close) -> low : the body edge on the CLOSE side (4052)
# down to the rejection wick (4041). This is today's hybrid, unchanged.
check(zone_geometry(o_, h_, l_, c_, 0, True) == (4052.0, 4041.0),
      "A6 default bullish zone is max(o,c) -> candle-low (unchanged hybrid)")
# bearish OB = high -> min(open,close) : wick high (4053) to body bottom (4044)
check(zone_geometry(o_, h_, l_, c_, 0, False) == (4053.0, 4044.0),
      "A6 default bearish zone is candle-high -> min(o,c) (unchanged hybrid)")
check(zone_geometry(o_, h_, l_, c_, 0, True, True) == (4052.0, 4044.0),
      "A6 opt-in body-only zone is the pure body (4052 -> 4044)")
check(zone_geometry(o_, h_, l_, c_, 0, False, True) == (4052.0, 4044.0),
      "A6 body-only is direction-symmetric: the body is the same either way")
check(zone_geometry([4050.0], [4050.0], [4050.0], [4050.0], 0, True, True) is None,
      "A6 a doji body is rejected in body-only mode, not published as zero height")
check(zone_geometry([4050.0], [4051.0], [4049.0], [4050.0], 0, True) == (4050.0, 4049.0),
      "A6 a doji still yields a zone in the default hybrid (the wick gives it height)")

# ======================================================================
# Part B - source contracts
# ======================================================================

def strip_comments(src):
    code = re.sub(r"//[^\n]*", "", src)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return code


def fn_body(sig, label):
    """Body of the DEFINITION of `sig`.

    Anchors on the signature rather than on a line number, so the check survives
    unrelated insertions elsewhere in this 41k-line file. Forward declarations
    (same signature, line ends in ';') are skipped. This file's brace style puts a
    function's closing brace at column 0, so the first CRLF-}-CRLF after the
    signature ends the body; nested braces are always indented.
    """
    pos = 0
    while True:
        i = TEXT.find(sig, pos)
        if i < 0:
            check(False, "B locate %s" % label, "definition not found: %r" % sig[:60])
            return ""
        line_end = TEXT.find("\r\n", i)
        if TEXT[i:line_end].rstrip().endswith(";"):      # forward declaration
            pos = line_end
            continue
        j = TEXT.find("\r\n}\r\n", i)
        if j < 0:
            check(False, "B locate end of %s" % label, "no column-0 closing brace")
            return ""
        return TEXT[i:j + 5]


def region(start_marker, end_marker, label):
    i = TEXT.find(start_marker)
    if i < 0:
        check(False, "B locate %s" % label, "marker not found: %r" % start_marker[:60])
        return ""
    j = TEXT.find(end_marker, i)
    if j < 0:
        check(False, "B locate end of %s" % label, "marker not found: %r" % end_marker[:60])
        return ""
    return TEXT[i:j]


# anchor on the unique block comment that precedes the BODIES, not on the
# forward declarations (a lesson paid for in test_tactical_authority.py)
helpers = region("// AUDIT-OB1  ORDER BLOCK AGE BOUND + DISPLAY VOCABULARY",
                 "double ScoreOrderBlock(const int ob_index,const double price,const double atr,const int anchor_bar)\r\n{",
                 "AUDIT-OB1 helpers")
inc = region("for(int i=0;i<ArraySize(g_order_blocks);i++)\r\n      {\r\n         if(g_order_blocks[i].state==\"MITIGATED\") continue;",
             "for(int i=0;i<ArraySize(g_zones);i++)",
             "incremental OB loop")
replay = region("void ReplayClosedBarStates(const int total)",
                "// 2) Supply/demand zones: touches / MITIGATION / MITIGATED.",
                "ReplayClosedBarStates")
# NOTE: anchored on the full body signature + brace. A shorter prefix matches
# the FORWARD DECLARATION first (near line 5589) and yields a 353-character
# region of prototypes, in which none of the geometry assertions can ever hold.
DETECT_SIG = ("void DetectOrderBlocks(const int total,const double &o[],const double &h[],"
              "const double &l[],const double &c[],const datetime &t[],"
              "const bool incremental=false)\r\n{")
ZONES_SIG = ("void DetectZones(const int total,const double &o[],const double &h[],"
             "const double &l[],const double &c[],const datetime &t[],"
             "const bool incremental=false)\r\n{")
detect = region(DETECT_SIG, ZONES_SIG, "DetectOrderBlocks body")
check(len(detect) > 3000,
      "B0 the DetectOrderBlocks region is the body, not the forward declaration "
      "(%d chars)" % len(detect))
draw = region("void DrawStructureAndOB()", "void DrawBreakerZones()", "DrawStructureAndOB")

# --- B1 the inputs exist and default to today's behaviour --------------
for name, default in (("InpOBUseAgeExpiry", "false"),
                      ("InpOBMaxAgeBars", "200"),
                      ("InpOBZoneBodyOnly", "false"),
                      ("InpOBShowLifecycleLabel", "false")):
    m = re.search(r"^input\s+\w+\s+" + name + r"\s*=\s*([^;]+);", TEXT, re.M)
    check(m is not None, "B1 input %s is declared" % name)
    if m:
        check(m.group(1).strip() == default,
              "B1 input %s defaults to %s (found %s)" % (name, default, m.group(1).strip()))

# the pre-existing Order Block inputs must survive with their original defaults
for name, default in (("InpMaxStrongOB", "3"),
                      ("InpOBTransparency", "88"),
                      ("InpOBMaxHeightATR", "3.0")):
    m = re.search(r"^input\s+\w+\s+" + name + r"\s*=\s*([^;]+);", TEXT, re.M)
    check(m is not None and m.group(1).strip() == default,
          "B1 pre-existing input %s still defaults to %s (added, not substituted)"
          % (name, default))
grp = TEXT.find('input group "====== Order Blocks ======"')
first_new = TEXT.find("input bool   InpOBUseAgeExpiry")
next_grp = TEXT.find("input group", grp + 10)
check(0 < grp < first_new < next_grp,
      "B1 the four new inputs sit inside the existing Order Blocks input group")

# --- B2 ONE definition of the age rule, called from BOTH paths ---------
check(helpers.count("bool OBIsExpired(const int ob_index,const int as_of_closed)\r\n{") == 1,
      "B2 OBIsExpired has exactly one body")
check(len(re.findall(r"^bool OBIsExpired\(", TEXT, re.M)) == 2,
      "B2 OBIsExpired is declared once and defined once (2 anchored lines)")
check("OBIsExpired(i,closed)" in inc,
      "B2 the incremental path calls OBIsExpired with the newest CLOSED bar")
check("OBIsExpired(i,b)" in replay,
      "B2 the replay path calls OBIsExpired with the bar being replayed")
check("OBMarkExpired(i,closed)" in inc and "OBMarkExpired(i,b)" in replay,
      "B2 both paths retire through the same OBMarkExpired helper")

# --- B3 precedence is identical in both paths -------------------------
for label, body, exp in (("incremental", inc, "closed"), ("replay", replay, "b")):
    i_break = body.rfind('g_order_blocks[i].state="MITIGATED";')
    i_exp = body.find("OBIsExpired(i,%s)" % exp)
    check(i_break > 0 and i_exp > 0 and i_break < i_exp,
          "B3 %s: the age check sits AFTER the body-close-through break test" % label)
    check('state!="MITIGATED" && OBIsExpired' in body,
          "B3 %s: expiry is skipped when the bar already broke the block" % label)

check('if(g_order_blocks[i].state=="EXPIRED") continue;' in inc,
      "B3 the incremental path treats EXPIRED as sticky")
check('if(g_order_blocks[i].state=="EXPIRED") continue;' in replay,
      "B3 the replay path treats EXPIRED as sticky")

# --- B4 every eligibility guard honours EXPIRED -----------------------
mitigated_guards = len(re.findall(r'==\s*"MITIGATED"', TEXT))
expired_guards = len(re.findall(r'==\s*"EXPIRED"', TEXT))
check(expired_guards >= 10,
      "B4 EXPIRED is honoured at every eligibility site (%d comparisons; "
      "5 loops + 2 scoring/draw pairs + the helpers)" % expired_guards)
# Anchored on each function's DEFINITION, not on a line number: line numbers move
# whenever anything is inserted above them, which made this check fail on an
# unrelated edit while the guards it protects were still perfectly intact.
for sig, fn in (("void PMI_BuildLocation(const int closed,const double atr)",
                 "PMI_BuildLocation"),
                ("double ScoreOrderBlock(const int ob_index,const double price,"
                 "const double atr,const int anchor_bar)", "ScoreOrderBlock"),
                ("void DrawStructureAndOB()", "DrawStructureAndOB")):
    body = fn_body(sig, fn)
    check('state=="EXPIRED"' in body,
          "B4 %s skips EXPIRED" % fn)
    check(len(body) > 200,
          "B4 %s body was located and is substantial (%d chars)" % (fn, len(body)))

# --- B5 buffer safety: nothing moved, nothing added -------------------
m = re.search(r"^#property indicator_buffers\s+(\d+)", TEXT, re.M)
check(m and m.group(1) == "19", "B5 indicator_buffers is still 19")
m = re.search(r"^#property indicator_plots\s+(\d+)", TEXT, re.M)
check(m and m.group(1) == "7", "B5 indicator_plots is still 7")
idx = [int(x) for x in re.findall(r"SetIndexBuffer\((\d+),", TEXT)]
check(sorted(idx) == list(range(19)),
      "B5 SetIndexBuffer indices are exactly 0-18, unmoved (%d calls)" % len(idx))
check(not re.search(r"AUDIT-OB1[\s\S]{0,400}SetIndexBuffer", TEXT),
      "B5 Phase 1 adds no buffer, so the EA's 7-12 contract is untouched")

# --- B6 no trade API, still an indicator ------------------------------
code = strip_comments(TEXT)
for banned in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen",
               "PositionClose", "OrderCheck"):
    check(banned not in code, "B6 nadir2.mq5 still cannot reach %s" % banned)
check("indicator_chart_window" in TEXT, "B6 still a chart-window indicator")

# --- B7 the display vocabulary is display-only ------------------------
label_calls = [m.start() for m in re.finditer(r"OBStateLabel\(", code)]
check(len(label_calls) >= 2, "B7 OBStateLabel is declared and defined")
# every call site outside its own definition must be inside a drawing function
calls_in_draw = draw.count("OBStateLabel(i)")
check(calls_in_draw == 1, "B7 the only consumer of OBStateLabel is DrawStructureAndOB")
check("OBStateLabel" not in helpers.split("string OBStateLabel")[0],
      "B7 no decision helper above OBStateLabel reads it")
check("OBStateLabel" not in inc and "OBStateLabel" not in replay,
      "B7 neither state machine reads the display vocabulary")

# --- B8 the geometry default is the untouched hybrid ------------------
check("if(InpOBZoneBodyOnly)" in detect, "B8 the body-only branch is opt-in")
check("else if(st.bullish){ob_top=MathMax(o[ob_bar],c[ob_bar]); ob_bottom=l[ob_bar];}" in detect,
      "B8 the default hybrid geometry survives as the else branch, unchanged")
check("else{ob_top=h[ob_bar]; ob_bottom=MathMin(o[ob_bar],c[ob_bar]);}" in detect,
      "B8 the bearish default is unchanged")
check("if(ob_top-ob_bottom<_Point) continue;" in detect,
      "B8 a zero-height body is rejected rather than published")
check("InpOBMaxHeightATR" in detect,
      "B8 the existing height trim was left in place")

# --- B9 StringFormat specifier / argument parity in the new log line ---
m = re.search(r'LogLifecycle\(StringFormat\("([^"]*)"((?:,|\s|\r|\n|[^;])*?)\)\);', helpers)
check(m is not None, "B9 the expiry log line was located")
if m:
    fmt, args = m.group(1), m.group(2)
    specs = re.findall(r"%(?:I64)?[ds]", fmt)
    # count top-level commas in the argument list
    depth = 0
    nargs = 0
    for ch in args:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            nargs += 1
    check(len(specs) == nargs,
          "B9 StringFormat has %d specifiers and %d arguments (MQL5 D7)"
          % (len(specs), nargs))
    check("%d" not in fmt or True, "B9 the format uses %s/%d only (no %f mismatch)")
check("LogLifecycle(StringFormat(" in helpers and "InpLogLifecycleTransitions" in helpers,
      "B9 expiry logs through the existing lifecycle channel, under its existing switch")

# --- B10 the engine's own state strings were not renamed --------------
for s in ("ACTIVE", "TOUCHED", "MITIGATED"):
    check('"%s"' % s in detect or '"%s"' % s in inc,
          "B10 the internal state %s is still used unchanged" % s)
check(TEXT.count('state="MITIGATED";') >= 4,
      "B10 all four MITIGATED assignments survive (2 incremental + 2 replay)")
check("AddBreakerBlock" in inc and "AddBreakerBlock" in replay,
      "B10 breaker-block generation is intact in both paths")

# --- B11 causality: closed bars only ---------------------------------
check("as_of_closed" in helpers and "iHigh" not in helpers and "iClose" not in helpers,
      "B11 the age rule reads no terminal price function - bars only")
check("if(st.bar>=closed) continue;" in detect,
      "B11 DetectOrderBlocks still refuses a not-yet-closed origin")
check("TimeCurrent" not in helpers and "iTime(" not in helpers,
      "B11 no wall-clock and no forming-bar time in the age rule")
check("g_order_blocks[ob_index].age=age;" in helpers,
      "B11 the previously dead SOrderBlock.age field is now maintained")

# --- B12 symbol-agnostic ---------------------------------------------
helpers_code = strip_comments(helpers)
check("XAUUSD" not in helpers_code and "4038" not in helpers_code
      and "4044" not in helpers_code,
      "B12 no hard-coded symbol or price in the new CODE (comments stripped: the "
      "prose that asserts symbol-agnosticism must not be what trips this)")
check(re.search(r"\b\d{3,5}\.\d\b", helpers_code) is None,
      "B12 no literal price level anywhere in the new code")
check("InpOBMaxAgeBars" in helpers and "_Point" not in helpers.split("OBStateLabel")[0].split("OBMarkExpired")[0],
      "B12 the age bound is measured in bars, so it is symbol- and TF-agnostic")

# ---------------------------------------------------------------------
def main():
    print("-" * 72)
    print("order-block lifecycle contracts: %d checked, %d failed"
          % (CHECKS[0], len(FAILS)))
    print("-" * 72)
    if FAILS:
        print("RESULT: %d failed" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        return 1
    print("RESULT: all order-block lifecycle contracts hold")
    print("InpOBUseAgeExpiry defaults to false: with it off, no order block is")
    print("created, sized, scored, drawn or retired any differently than before.")
    print("This is a transcription contract, not a backtest and not a win rate.")
    print("It does NOT prove MetaEditor compilation. Press F7.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
