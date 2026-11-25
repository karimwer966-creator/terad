#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-A2  ICT PULLBACK PLAYBOOK - transcription + wiring contract.

Phase 8 of the strategy-module extension for nadir2.mq5. What this file proves,
and what it deliberately does NOT claim:

  * It transcribes the module's five PURE playbook predicates into Python,
    re-derives their behaviour, and then checks that the transcribed guard
    ORDER and the reason literals are the ones actually present in the .mq5
    text. Without that second step the transcription could drift from the
    source and still pass.
  * It proves the display-only contract structurally: the A2 sections of the
    file name no trade API, no buffer, no object creation and no alert, and the
    tooltip rows are gated by BOTH the module switch and the dashboard switch -
    exactly the RM/PA pattern - never on the hard-capped 11-row card.
  * It proves the module cannot authorize anything: A2_Update is called once
    per closed bar (never per tick), the module adds no input that can widen,
    move or confirm an entry, and the switch is OFF by default.
  * It is a static contract test. It is NOT a backtest, produces no win rate,
    and does NOT prove MetaEditor compiles the file - only F7 does that.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "nadir2.mq5")

FAILURES = []
COUNT = [0]


def check(cond, label, detail=""):
    COUNT[0] += 1
    if cond:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s%s" % (label, ("  [%s]" % detail) if detail else ""))
        FAILURES.append(label)


with io.open(SRC, encoding="utf-8", newline="") as fh:
    TEXT = fh.read()
BARE_LF = TEXT.count("\n") - TEXT.count("\r\n")


def strip_comments(src):
    """Remove comments and blank literal contents in ONE pass (see phase5)."""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == '"' or c == "'":
            q = c
            out.append('""' if q == '"' else "''")
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _fn_end(text, sig_at):
    i, depth, started, n = sig_at, 0, False, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            if j < 0:
                return -1
            i = j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            if j < 0:
                return -1
            i = j + 2
            continue
        if c in '"\'':
            q = c
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == q:
                    break
                i += 1
            i += 1
            continue
        if c == '{':
            depth += 1
            started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return i + 1
        i += 1
    return -1


def body_of(sig, label, floor=0):
    """Body of the DEFINITION matching `sig`, skipping forward declarations."""
    j = floor
    while True:
        j = TEXT.find(sig, j)
        if j < 0:
            break
        sc = TEXT.find(';', j)
        br = TEXT.find('{', j)
        if br >= 0 and (sc < 0 or br < sc):
            end = _fn_end(TEXT, j)
            if end > 0:
                return TEXT[j:end]
        j += len(sig)
    check(False, label + " (definition located)", sig)
    return ""


def precedes(hay, first, second, label):
    a, b = hay.find(first), hay.find(second)
    check(a >= 0 and b >= 0 and a < b, label, "first@%d second@%d" % (a, b))


def input_default(name):
    m = re.search(r"\binput\s+[A-Za-z_][\w\s\*&]*?\b" + re.escape(name) +
                  r"\s*=\s*([^,;]+)[,;]", TEXT)
    return m.group(1).strip() if m else None


c_all = strip_comments(TEXT)


def call_count(sig_call):
    n = 0
    for m in re.finditer(re.escape(sig_call), c_all):
        ls = c_all.rfind('\n', 0, m.start()) + 1
        le = c_all.find('\n', m.end())
        line = c_all[ls:le if le >= 0 else len(c_all)]
        if re.match(r'^\s*(?:void|int|bool|string|double|datetime|long|ushort|struct)\s+', line) \
                and line.rstrip().endswith(';'):
            continue
        n += 1
    return n


# The A2 sections, sliced once: the declaration block in the inputs region and
# the implementation at end of file. Everything "nothing existing was modified"
# is checked against the WHOLE file; everything "display only" is checked
# against these slices.
IMPL_BANNER = "// AUDIT-A2 ICT PULLBACK PLAYBOOK  implementation (display only)"
DECL_BANNER = "// AUDIT-A2 ICT PULLBACK PLAYBOOK  (DISPLAY ONLY)"
i0 = TEXT.find(IMPL_BANNER)
i1 = TEXT.find(DECL_BANNER)
a2_impl = TEXT[i0:] if i0 >= 0 else ""
a2_decl = ""
if i1 >= 0:
    k = TEXT.find('input group "====== Premium / Discount', i1)
    a2_decl = TEXT[i1:k if k >= 0 else i1 + 6000]
a2_code = strip_comments(a2_impl)


# =====================================================================
# A. PURE CORES - transcribed, then pinned back to the source text
# =====================================================================
# Every predicate reads ONLY the SIctPlaybookState snapshot. Guard order is
# part of the contract: the first missing leg is the reason that prints.
class S(object):
    """The SIctPlaybookState snapshot, transcribed."""

    def __init__(self):
        self.closed_bar = 100
        self.bar_time = 0
        self.close = 100.0
        self.atr = 1.0
        self.lookback = 12
        self.poi_atr = 1.5
        self.range_valid = True
        self.ote_dir = 0
        self.in_ote = False
        self.struct_dir = 0
        self.struct_age = 9999
        self.poi_count = 0
        self.poi_near = False
        self.sweep_dir = 0
        self.sweep_age = 9999
        self.sweep_in_kz = False
        self.fvg_after_sweep = 0
        self.p3_phase = 0
        self.p3_dir = 0
        self.sb_dir = 0
        self.setup_state = 0
        self.in_london_kz = False
        self.in_ny_kz = False
        self.news_blackout = False


def row(met=False, dir_=0, reason="", invalidation=""):
    return {"met": met, "dir": dir_, "reason": reason, "invalidation": invalidation}


def a2_structure_ote(s):
    r = row()
    if s.closed_bar < 2:
        r["reason"] = "no closed-bar snapshot yet"
        return r
    if s.struct_dir == 0:
        r["reason"] = "no MSS/BOS/CHoCH inside the search window"
        return r
    if s.struct_age > s.lookback:
        r["reason"] = "the structure break is %d bars old (window %d)" % (s.struct_age, s.lookback)
        return r
    if not s.range_valid:
        r["reason"] = "no dealing range, so no OTE zone exists"
        return r
    if not s.in_ote or s.ote_dir != s.struct_dir:
        r["reason"] = "price is not inside the OTE zone aligned with structure"
        return r
    if s.poi_count <= 0:
        r["reason"] = "no live OB/FVG in the structure direction"
        return r
    if not s.poi_near:
        r["reason"] = "the nearest live POI is further than the allowed ATR distance"
        return r
    r["met"] = True
    r["dir"] = s.struct_dir
    r["reason"] = ("bullish" if s.struct_dir > 0 else "bearish") + \
        " structure %d bars ago + OTE + live POI" % s.struct_age
    r["invalidation"] = "a closed bar back through the structure break level"
    return r


def a2_amd_ote(s):
    P3_NONE, P3_MANIPULATION, P3_DISTRIBUTION = 0, 1, 2
    r = row()
    if s.closed_bar < 2:
        r["reason"] = "no closed-bar snapshot yet"
        return r
    if s.p3_phase != P3_MANIPULATION and s.p3_phase != P3_DISTRIBUTION:
        r["reason"] = "no resolved manipulation/distribution phase today"
        return r
    if s.p3_dir == 0:
        r["reason"] = "the phase resolved but carries no direction"
        return r
    if s.news_blackout:
        r["reason"] = "inside the +/-30m news window - the playbook stands aside"
        return r
    if not s.range_valid:
        r["reason"] = "no dealing range, so no OTE zone exists"
        return r
    if not s.in_ote or s.ote_dir != s.p3_dir:
        r["reason"] = "price is not inside the OTE zone aligned with the AMD resolution"
        return r
    r["met"] = True
    r["dir"] = s.p3_dir
    r["reason"] = ("distribution" if s.p3_phase == P3_DISTRIBUTION else "manipulation") + \
        " resolved " + ("long" if s.p3_dir > 0 else "short") + " + OTE"
    r["invalidation"] = "a closed bar back inside the manipulation candle (the Judas swing failed)"
    return r


def a2_session_grab_fvg(s):
    r = row()
    if s.closed_bar < 2:
        r["reason"] = "no closed-bar snapshot yet"
        return r
    if s.sweep_dir == 0:
        r["reason"] = "no SSL/BSL sweep inside the search window"
        return r
    if s.sweep_age > s.lookback:
        r["reason"] = "the sweep is %d bars old (window %d)" % (s.sweep_age, s.lookback)
        return r
    if not s.sweep_in_kz:
        r["reason"] = "the sweep did not land in London or New York kill zone"
        return r
    if s.fvg_after_sweep <= 0:
        r["reason"] = "no FVG created in the reclaim direction after the sweep"
        return r
    if s.struct_dir != s.sweep_dir or s.struct_age > s.lookback:
        r["reason"] = "no MSS/BOS/CHoCH in the reclaim direction inside the window"
        return r
    r["met"] = True
    r["dir"] = s.sweep_dir
    r["reason"] = ("SSL" if s.sweep_dir > 0 else "BSL") + \
        " taken %d bars ago in kill zone + FVG + structure" % s.sweep_age
    r["invalidation"] = "a closed bar back through the swept level"
    return r


def a2_session_raid_confirm(s):
    P3_DISTRIBUTION = 2
    r = row()
    if s.closed_bar < 2:
        r["reason"] = "no closed-bar snapshot yet"
        return r
    raid_dir = s.sb_dir if s.sb_dir != 0 else (s.p3_dir if s.p3_phase == P3_DISTRIBUTION else 0)
    if raid_dir == 0:
        r["reason"] = "neither the silver-bullet chain nor a distribution phase has resolved"
        return r
    if not s.in_london_kz and not s.in_ny_kz:
        r["reason"] = "decision bar is outside the London/New York kill zones"
        return r
    if s.struct_dir != raid_dir or s.struct_age > s.lookback:
        r["reason"] = "no MSS/BOS/CHoCH in the raid direction inside the window"
        return r
    if s.fvg_after_sweep <= 0:
        r["reason"] = "no FVG after the raid in the reclaim direction"
        return r
    r["met"] = True
    r["dir"] = raid_dir
    r["reason"] = ("silver-bullet" if s.sb_dir != 0 else "distribution") + \
        " raid + kill zone + structure + FVG"
    r["invalidation"] = "a closed bar back through the raid origin"
    return r


def a2_break_retest(s):
    r = row()
    if s.closed_bar < 2:
        r["reason"] = "no closed-bar snapshot yet"
        return r
    if s.setup_state == 0:
        r["reason"] = "no causal chain in progress (nothing broke, nothing retests)"
        return r
    if s.sweep_dir == 0:
        r["reason"] = "the chain has no recorded sweep leg"
        return r
    if s.sweep_age > 2 * s.lookback:
        r["reason"] = "the break is stale (%d bars)" % s.sweep_age
        return r
    r["met"] = True
    r["dir"] = s.sweep_dir
    r["reason"] = ("ARMED - waiting for the retest" if s.setup_state == 1
                   else "retest held - chain confirmed") + \
        " | break %d bars ago" % s.sweep_age
    r["invalidation"] = "the battle zone gives way on a closed bar"
    return r


def a2_row_text(r):
    if not r["met"]:
        return "stand aside | " + r["reason"]
    side = "MET long | " if r["dir"] > 0 else "MET short | "
    inv = " | inv: " + r["invalidation"] if r["invalidation"] != "" else ""
    return side + r["reason"] + inv


# A0 the sections located at all.
check(i0 >= 0, "A0 the A2 implementation banner is present")
check(i1 >= 0, "A0 the A2 declaration banner is present")
check(a2_impl.count("SIctPlaybookState s;") >= 2,
      "A0 the host glue and the self-test both build SIctPlaybookState snapshots")

# A1 an empty snapshot stands aside everywhere - missing evidence is never a
# free point. Exhaustive over the five predicates.
EMPTY = S()
for name, fn in (("structure+OTE", a2_structure_ote), ("AMD+OTE", a2_amd_ote),
                 ("session grab", a2_session_grab_fvg), ("session raid", a2_session_raid_confirm),
                 ("break-retest", a2_break_retest)):
    r = fn(EMPTY)
    check(not r["met"] and r["dir"] == 0 and r["reason"],
          "A1 an empty snapshot stands aside (%s)" % name)

# A2 the closed_bar guard fires before every other leg, in all five cores.
for name, fn in (("structure+OTE", a2_structure_ote), ("AMD+OTE", a2_amd_ote),
                 ("session grab", a2_session_grab_fvg), ("session raid", a2_session_raid_confirm),
                 ("break-retest", a2_break_retest)):
    s = S()
    s.closed_bar = 1
    s.struct_dir = 1
    s.struct_age = 0
    s.in_ote = True
    s.ote_dir = 1
    s.poi_count = 3
    s.poi_near = True
    s.sweep_dir = 1
    s.sweep_age = 0
    s.sweep_in_kz = True
    s.fvg_after_sweep = 2
    s.p3_phase = 2
    s.p3_dir = 1
    s.sb_dir = 1
    s.setup_state = 2
    s.in_london_kz = True
    r = fn(s)
    check(not r["met"] and r["reason"] == "no closed-bar snapshot yet",
          "A2 a pre-first-closed-bar snapshot stands aside (%s)" % name)

# A3 structure+OTE: every leg, both directions.
def _full_struct(d=1):
    s = S()
    s.struct_dir = d
    s.struct_age = 3
    s.in_ote = True
    s.ote_dir = d
    s.poi_count = 2
    s.poi_near = True
    return s

for d in (1, -1):
    r = a2_structure_ote(_full_struct(d))
    check(r["met"] and r["dir"] == d, "A3 the complete %s structure+OTE picture is MET" % ("long" if d > 0 else "short"))
s = _full_struct()
s.ote_dir = -1
check(not a2_structure_ote(s)["met"], "A3 an opposing OTE zone vetoes structure+OTE")
s = _full_struct()
s.in_ote = False
check(not a2_structure_ote(s)["met"], "A3 flat price outside the OTE zone vetoes structure+OTE")
s = _full_struct()
s.struct_age = 99
check(not a2_structure_ote(s)["met"], "A3 a stale structure break stands aside")
s = _full_struct()
s.struct_age = s.lookback
check(a2_structure_ote(s)["met"], "A3 a structure break exactly at the window edge still counts")
s = _full_struct()
s.poi_count = 0
check(not a2_structure_ote(s)["met"], "A3 no live POI stands aside")
s = _full_struct()
s.poi_near = False
check(not a2_structure_ote(s)["met"], "A3 a POI further than the ATR allowance stands aside")
s = _full_struct()
s.range_valid = False
check(not a2_structure_ote(s)["met"], "A3 no dealing range, no OTE zone, stand aside")

# A4 AMD+OTE.
def _full_amd(d=-1):
    s = S()
    s.p3_phase = 1  # MANIPULATION
    s.p3_dir = d
    s.in_ote = True
    s.ote_dir = d
    return s

r = a2_amd_ote(_full_amd(-1))
check(r["met"] and r["dir"] == -1, "A4 manipulation resolved short + aligned OTE is MET short")
s = _full_amd(1)
s.p3_phase = 2  # DISTRIBUTION
check(a2_amd_ote(s)["met"] and a2_amd_ote(s)["dir"] == 1, "A4 distribution resolved long + aligned OTE is MET long")
s = _full_amd(-1)
s.news_blackout = True
check(not a2_amd_ote(s)["met"], "A4 the news window vetoes the AMD playbook")
s = _full_amd(-1)
s.p3_phase = 0  # NONE
check(not a2_amd_ote(s)["met"], "A4 no resolved phase today stands aside")
s = _full_amd(-1)
s.p3_dir = 0
check(not a2_amd_ote(s)["met"], "A4 a phase with no direction stands aside")
s = _full_amd(-1)
s.ote_dir = 1
check(not a2_amd_ote(s)["met"], "A4 an AMD resolution against the OTE zone stands aside")

# A5 session liquidity grab + FVG.
def _full_grab(d=1):
    s = S()
    s.sweep_dir = d
    s.sweep_age = 2
    s.sweep_in_kz = True
    s.fvg_after_sweep = 1
    s.struct_dir = d
    s.struct_age = 2
    return s

r = a2_session_grab_fvg(_full_grab(1))
check(r["met"] and r["dir"] == 1, "A5 the complete SSL-grab picture is MET long")
s = _full_grab(-1)
check(a2_session_grab_fvg(s)["met"] and a2_session_grab_fvg(s)["dir"] == -1,
      "A5 the complete BSL-grab picture is MET short")
s = _full_grab()
s.sweep_in_kz = False
check(not a2_session_grab_fvg(s)["met"], "A5 a sweep outside the kill zones stands aside")
s = _full_grab()
s.fvg_after_sweep = 0
check(not a2_session_grab_fvg(s)["met"], "A5 no FVG after the sweep stands aside")
s = _full_grab()
s.struct_dir = -1
check(not a2_session_grab_fvg(s)["met"], "A5 structure against the reclaim stands aside")
s = _full_grab()
s.struct_age = 99
check(not a2_session_grab_fvg(s)["met"], "A5 a reclaim structure outside the window stands aside")
s = _full_grab()
s.sweep_age = s.lookback + 1
check(not a2_session_grab_fvg(s)["met"], "A5 a stale sweep stands aside")

# A6 session raid + confirmation.
def _full_raid(d=1):
    s = S()
    s.sb_dir = d
    s.in_london_kz = True
    s.struct_dir = d
    s.struct_age = 4
    s.fvg_after_sweep = 1
    return s

r = a2_session_raid_confirm(_full_raid(1))
check(r["met"] and r["dir"] == 1, "A6 the complete silver-bullet raid picture is MET long")
s = _full_raid()
s.sb_dir = 0
s.p3_phase = 2  # distribution fallback
s.p3_dir = 1
check(a2_session_raid_confirm(s)["met"], "A6 the distribution phase is a valid raid leg when no silver bullet resolved")
s = _full_raid()
s.sb_dir = 0
s.p3_phase = 0
check(not a2_session_raid_confirm(s)["met"], "A6 neither leg resolved stands aside")
s = _full_raid()
s.in_london_kz = False
check(not a2_session_raid_confirm(s)["met"], "A6 a raid outside London/New York stands aside")
s = _full_raid()
s.struct_dir = -1
check(not a2_session_raid_confirm(s)["met"], "A6 structure against the raid stands aside")
s = _full_raid()
s.fvg_after_sweep = 0
check(not a2_session_raid_confirm(s)["met"], "A6 no FVG after the raid stands aside")

# A7 break -> retest.
def _full_chain(d=-1):
    s = S()
    s.setup_state = 2
    s.sweep_dir = d
    s.sweep_age = 5
    return s

r = a2_break_retest(_full_chain(-1))
check(r["met"] and r["dir"] == -1, "A7 a confirmed chain with a recorded sweep leg is MET short")
s = _full_chain(1)
s.setup_state = 1
check(a2_break_retest(s)["met"], "A7 an ARMED chain (confirmation pending) is still MET")
s = _full_chain(-1)
s.setup_state = 0
check(not a2_break_retest(s)["met"], "A7 no chain in progress stands aside")
s = _full_chain(-1)
s.sweep_dir = 0
check(not a2_break_retest(s)["met"], "A7 a chain with no recorded sweep leg stands aside")
s = _full_chain(-1)
s.sweep_age = 2 * s.lookback + 1
check(not a2_break_retest(s)["met"], "A7 a break older than the doubled window stands aside")
s = _full_chain(-1)
s.sweep_age = 2 * s.lookback
check(a2_break_retest(s)["met"], "A7 a break exactly at the doubled window edge still counts")

# A8 the tooltip line: a stand-aside prints the first missing leg, a met row
# prints the side, the reason and the invalidation.
check(a2_row_text(row(met=False, reason="no MSS/BOS/CHoCH inside the search window")) ==
      "stand aside | no MSS/BOS/CHoCH inside the search window",
      "A8 a stand-aside row prints the first missing leg")
r = a2_structure_ote(_full_struct(1))
line = a2_row_text(r)
check(line.startswith("MET long | ") and " | inv: a closed bar back through the structure break level" in line,
      "A8 a met row prints the side, the reason and the invalidation")

# A9 the guard ORDER is the reason order: the first missing leg is what prints.
bodies = {
    "A2_StructureOTE": ("if(s.closed_bar<2)", "if(s.struct_dir==0)", "if(s.struct_age>s.lookback)",
                        "if(!s.range_valid)", "if(!s.in_ote || s.ote_dir!=s.struct_dir)",
                        "if(s.poi_count<=0)", "if(!s.poi_near)"),
    "A2_AmdOte": ("if(s.closed_bar<2)", "P3_PHASE_MANIPULATION && s.p3_phase!=(int)P3_PHASE_DISTRIBUTION",
                  "if(s.p3_dir==0)", "if(s.news_blackout)", "if(!s.range_valid)",
                  "if(!s.in_ote || s.ote_dir!=s.p3_dir)"),
    "A2_SessionGrabFvg": ("if(s.closed_bar<2)", "if(s.sweep_dir==0)", "if(s.sweep_age>s.lookback)",
                          "if(!s.sweep_in_kz)", "if(s.fvg_after_sweep<=0)",
                          "if(s.struct_dir!=s.sweep_dir || s.struct_age>s.lookback)"),
    "A2_SessionRaidConfirm": ("if(s.closed_bar<2)", "raid_dir==0",
                              "if(!s.in_london_kz && !s.in_ny_kz)",
                              "if(s.struct_dir!=raid_dir || s.struct_age>s.lookback)",
                              "if(s.fvg_after_sweep<=0)"),
    "A2_BreakRetest": ("if(s.closed_bar<2)", "if(s.setup_state==0)", "if(s.sweep_dir==0)",
                       "if(s.sweep_age>2*s.lookback)"),
}
for fn, guards in sorted(bodies.items()):
    src = body_of(fn + "(const SIctPlaybookState &s)", "A9 " + fn)
    pos = -1
    ok = bool(src)
    for g in guards:
        p = src.find(g)
        if p < 0 or p < pos:
            ok = False
            break
        pos = p
    check(ok, "A9 %s checks its legs in the transcribed order" % fn)

# A10 the pure cores never touch globals, series or trading - their ONLY input is
# the snapshot. The host glue is the only place state is read.
for fn in ("A2_StructureOTE", "A2_AmdOte", "A2_SessionGrabFvg", "A2_SessionRaidConfirm", "A2_BreakRetest", "A2_RowText"):
    src = strip_comments(body_of(fn + "(const SIctPlaybookRow &r)", "") if fn == "A2_RowText"
                         else strip_comments(body_of(fn + "(const SIctPlaybookState &s)", "")))
    leak = [tok for tok in ("rates_", "iClose", "iHigh", "iLow", "ObjectCreate", "OrderSend", "Alert(")
            if tok in src]
    if re.search(r"\bg_[A-Za-z_]", src):
        leak.append("g_*")
    check(not leak, "A10 %s reads nothing but its argument" % fn, str(leak))

# =====================================================================
# B. THE FIVE PLAYBOOKS AND THEIR CATALOG NUMBERS
# =====================================================================
check("#30 structure-ote" in a2_decl, "B catalog #30 structure-ote is named")
check("#31 po3-ote-adr" in a2_decl and "#44 amd-model" in a2_decl, "B catalog #31/#44 AMD+OTE are named")
check("#34 nexus-blast-strategy" in a2_decl, "B catalog #34 session-grab is named")
check("#38 intraday-liquidity-volatility-model" in a2_decl, "B catalog #38 session-raid is named")
check("#47 break-retest" in a2_decl and "#49 liquidity-strategy" in a2_decl, "B catalog #47/#49 break-retest are named")
check("DISPLAY ONLY" in DECL_BANNER, "B the declaration banner claims display only")

# =====================================================================
# C. WIRING - called once per closed bar, resets in OnInit, self-test gated
# =====================================================================
check(call_count("A2_Update(closed);") == 1, "C A2_Update is called exactly once")
upd_at = c_all.find("A2_Update(closed);")
seg = c_all[max(0, upd_at - 200):upd_at + 200]
check("is_new_bar || detection_updated" in seg,
      "C the call sits under the closed-bar guard, so it never runs per tick")
check("MR_Update(closed,rates_total,full_indicators);" in c_all[max(0, upd_at - 1500):upd_at],
      "C the call sits beside MR_Update, after the state it reads is final")

_norm = TEXT.replace("\r\n", "\n")
_pc = _norm.find("RM_Clear();\n   A2_Clear();")
check(_pc > 0, "C A2_Clear() is called in OnInit")
check("CF_Clear();" in _norm[max(0, _pc - 200):_pc + 40],
      "C A2_Clear sits with the other module resets in OnInit")
check(call_count("A2_Clear();") >= 1, "C A2_Clear has at least one call")

st = c_all.find("A2_SelfTest(mtee_fail)")
check(st > 0, "C A2_SelfTest is registered in the in-terminal self-test block")
check("InpMTEERunSelfTest" in c_all[max(0, st - 12000):st],
      "C A2_SelfTest runs under the existing InpMTEERunSelfTest switch")
check('" ICT Pullback Playbook self-test: PASS (16/16)"' in TEXT,
      "C the self-test result uses the version-tagged visual-only PASS helper with 16 checks")
check(call_count("A2_SelfTest(mtee_fail)") == 1, "C A2_SelfTest has exactly one registration")

# The tooltip rows: both switches, never the 11-row card.
check('tooltip+="\\nA2 STRUCT+OTE (#30): "+A2_RowText(g_a2_p1);' in TEXT,
      "C the playbook rows go to the dashboard tooltip")
_d = TEXT.find('tooltip+="\\nA2 STRUCT+OTE')
dash_seg = TEXT[max(0, _d - 400):_d + 900]
check("if((InpEnableIctPlaybook||InpEnableAllModules) && (InpA2ShowOnDashboard||InpEnableAllModules))" in dash_seg,
      "C the A2 rows need BOTH the module switch and the dashboard switch")
check("A2_RowText(g_a2_p" in dash_seg, "C five rows, one per playbook")
check(dash_seg.count("A2_RowText(g_a2_p") == 5, "C exactly five playbook rows are appended")
check("if(ln>11) ln=11;" in TEXT and "string lines[11]; color cols[11]; int ln=0;" in TEXT,
      "C the 11-row card contract is untouched")

# Journal: only MET rows, only under the existing InpLogLifecycleTransitions.
upd = body_of("void A2_Update(const int closed)", "C A2_Update (definition)")
journal_at = upd.find("if(InpLogLifecycleTransitions)")
check(journal_at > 0, "C the journal block sits under InpLogLifecycleTransitions")
check(upd.count("LogLifecycle(") == 5, "C exactly five LogLifecycle calls (one per MET row)",
      str(upd.count("LogLifecycle(")))
check(upd.count(".met) LogLifecycle") == 5, "C every logged row is a MET row")

# =====================================================================
# D. NOTHING EXISTING WAS MODIFIED (pure function of the file)
# =====================================================================
code_only = strip_comments(TEXT)
check(TEXT.count('#property version   "6.624"') == 1, "D the version property is 6.624 (v6.6.24 audit release)")
check(len(re.findall(r'(?m)^#property indicator_buffers\s+26\b', TEXT)) == 1,
      "D indicator_buffers is 26 (21 shipped + 5 classification, v6.6.21)")
check(len(re.findall(r'(?m)^#property indicator_plots\s+7\b', TEXT)) == 1,
      "D indicator_plots is still 7")
idx = sorted(int(m) for m in re.findall(r'SetIndexBuffer\(\s*(\d+)', TEXT))
check(idx == list(range(26)), "D buffer indices are 0..25 with no gap or shift", str(idx))
ENUMS = len(re.findall(r'(?m)^enum\s+ENUM_', TEXT))
check(ENUMS == 47,
      "D enum count is still 47 (this phase adds NO enum, so no enumerator can shift): %d" % ENUMS)
CLOSED_CONV = code_only.count("int closed=rates_total-2;")
check(CLOSED_CONV == 12,
      "D all 12 closed=rates_total-2 sites are unchanged (%d)" % CLOSED_CONV)
check(code_only.count("int closed=ArraySize(g_buf_c)-2;") == 2,
      "D both surviving mirrored-array closed-bar sites are unchanged")
check(BARE_LF == 0, "D the file has no bare LF (%d)" % BARE_LF)

# The A2 sections name no trade API, no buffer, no object manager, no alert.
for banned in ("OrderSend", "SetIndexBuffer", "#property indicator_buffers", "ObjectCreate",
               "ObjectsDeleteAll", "Alert(", "iCustom(", "SendNotification", "WebRequest",
               "FileWrite", "IndicatorRelease", "OnDeinit"):
    check(banned not in (a2_decl + a2_code),
          "D the A2 sections contain no %r" % banned)
check("QueueAlert" not in a2_code and "g_mtf_entry" not in a2_code and "g_final_signal" not in a2_code,
      "D the A2 module never reads or writes the alert/resolver state")
check("g_a2_" in a2_code and "g_a2_valid=true;" in a2_code,
      "D the module publishes only its own g_a2_* state")

# =====================================================================
# E. INPUTS AND PUBLISHED STATE
# =====================================================================
EXPECT = {"InpEnableIctPlaybook": "false", "InpA2ShowOnDashboard": "false",
          "InpA2LookbackBars": "12", "InpA2PoiATR": "1.50"}
for name, want in sorted(EXPECT.items()):
    got = input_default(name)
    check(got == want, "E input %s defaults to %s" % (name, want), "found %r" % got)
for flag in ("InpEnableIctPlaybook", "InpA2ShowOnDashboard"):
    check(input_default(flag) == "false", "E the switch %s is OFF by default" % flag)
a2_inputs = set(re.findall(r'\b(InpA2\w+)\s*=', TEXT)) | set(re.findall(r'\b(InpEnableIctPlaybook)\s*=', TEXT))
check(a2_inputs == set(EXPECT),
      "E the declared inputs are exactly the documented set (%s)" % ", ".join(sorted(a2_inputs)))
for nm in sorted(a2_inputs):
    check(TEXT.count(nm) >= 2, "E %s is declared and actually referenced" % nm)
check('input group "====== ICT Pullback Playbook (AUDIT-A2, display only) ======"' in TEXT,
      "E the module owns an input group banner")

for st_name in ("g_a2_p1", "g_a2_p2", "g_a2_p3", "g_a2_p4", "g_a2_p5", "g_a2_valid"):
    check(re.search(r'\b%s\b' % st_name, a2_decl) is not None, "E the published state %s is declared" % st_name)
cl = strip_comments(body_of("void A2_Clear()", "E A2_Clear"))
for st_name in ("g_a2_p1", "g_a2_p2", "g_a2_p3", "g_a2_p4", "g_a2_p5"):
    check(st_name in cl, "E A2_Clear resets %s" % st_name)
check("g_a2_valid=false;" in cl, "E A2_Clear also drops the validity flag")

for st_name in ("SIctPlaybookRow", "SIctPlaybookState"):
    check(("struct %s" % st_name) in TEXT, "E the %s struct is declared" % st_name)

upd = strip_comments(body_of("void A2_Update(const int closed)", "E A2_Update"))
check("InpEnableIctPlaybook||InpEnableAllModules" in upd,
      "E the module honours the master module switch, like its neighbours")
check("g_atr_buf" in upd and "g_atr;" in upd,
      "E the ATR falls back to the global when the per-bar copy is missing")
check("closed>=ArraySize(g_buf_c)" in upd,
      "E the update refuses out-of-range bars instead of reading past them")
check("MTF_SniperIsNewsBlackout" in upd and "IsInKillZone" in upd and "GetOTEZone" in upd,
      "E the update reuses the file's own OTE definition and kill zones")
check("P3_PHASE_MANIPULATION" in upd or "p3_phase" in upd,
      "E the AMD leg reads the P3 state the file publishes")
check("InpA2LookbackBars" in upd and "InpA2PoiATR" in upd,
      "E the search window and POI distance are the operator's inputs")
check("g_trade_setup.confirmation_pending" in upd,
      "E the break-retest leg reads the causal chain's own pending state")

st_test = body_of("bool A2_SelfTest(string &where)", "E A2_SelfTest")
for t in range(1, 17):
    check('"A2-%d' % t in st_test, "E the self-test covers A2-%d" % t)

print("")
print("=" * 74)
print("AUDIT-A2 checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("This is a static transcription + wiring contract. It is NOT a backtest, it")
print("produces no win rate, and it does NOT prove MetaEditor compiles the file.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
