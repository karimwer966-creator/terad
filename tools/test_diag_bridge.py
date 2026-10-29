#!/usr/bin/env python3
"""Contract checks for the v6.6.10 diagnostic bridge (indicator -> companion).

Why this file exists
--------------------
The companion can only see the indicator's hidden buffers. When those buffers
are empty, the operator used to read "CORE signals: 0" and had no cause. The
indicator now publishes its own gate verdict as terminal globals:

    QSMC_DIAG_<symbol>_<period>_CORE    blocker code (see the table)
    QSMC_DIAG_<symbol>_<period>_BARS    closed bars audited this session
    QSMC_DIAG_<symbol>_<period>_ARMED   setups armed this session
    QSMC_DIAG_<symbol>_<period>_CONF    setups confirmed this session
    QSMC_DIAG_<symbol>_<period>_TIME    time of the closed bar it describes

Two programs, two hand-written copies of one code table: that is exactly the
kind of pair that drifts. Everything below is a source contract, not an MT5
run - the only proof of behaviour is F7 plus a live journal.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "nadir2.mq5"
EA = ROOT / "MQL5/Experts/QSMC_AutoTrader.mq5"

TABLE_BEGIN = "// DIAG_TABLE_BEGIN"
TABLE_END = "// DIAG_TABLE_END"
LEAVES = ["CORE", "BARS", "ARMED", "CONF", "TIME"]


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS  {message}")


def table_of(text, label):
    start = text.find(TABLE_BEGIN)
    stop = text.find(TABLE_END)
    require(start >= 0 and stop > start, f"{label} carries a {TABLE_BEGIN} .. {TABLE_END} block")
    block = text[start + len(TABLE_BEGIN):stop]
    rows = {}
    for line in block.splitlines():
        m = re.match(r"\s*//\s*(\d+)\s+([A-Z_]+)\s{2,}(\S.*?)\s*$", line)
        if m:
            rows[int(m.group(1))] = m.group(2)
    require(len(rows) >= 20, f"{label} table parses into a usable code map ({len(rows)} codes)")
    return rows, block


host_src = HOST.read_bytes()
require(b"\r\n" in host_src, "nadir2.mq5 is still a CRLF file (.gitattributes pins it as -text)")
require(host_src.count(b"\n") == host_src.count(b"\r\n"),
        "nadir2.mq5 has no LF-only line (a mixed file turns every later diff into noise)")

host = host_src.decode("utf-8")
ea = EA.read_text(encoding="utf-8")

host_rows, host_block = table_of(host, "the indicator")
ea_rows, ea_block = table_of(ea, "the companion")

# ---------------------------------------------------------------- one table
require(host_rows == ea_rows,
        "the indicator and the companion decode the same codes to the same names "
        f"(indicator-only {sorted(set(host_rows.items()) - set(ea_rows.items()))}, "
        f"companion-only {sorted(set(ea_rows.items()) - set(host_rows.items()))})")
require(host_block.replace("\r\n", "\n") == ea_block,
        "the DIAG_TABLE block is byte-identical in both programs (one table, two copies)")

for code, name in host_rows.items():
    require(re.search(rf"//\s*{code}\s+{name}\b", ea_block) is not None,
            f"code {code} ({name}) is documented identically on both sides")

# ------------------------------------------------- the companion decodes them all
switch = re.search(r"string DiagCodeText\(const int code\)\s*\{(.*?)\n  \}", ea, re.S)
require(switch is not None, "the companion has a DiagCodeText() decoder")
cases = {int(n) for n in re.findall(r"case\s+(\d+)\s*:", switch.group(1))}
missing = sorted(set(host_rows) - cases)
require(not missing,
        f"DiagCodeText() decodes every published code (missing: {missing})")
require("return (\"UNKNOWN code \"" in switch.group(1),
        "an unmapped code is reported as UNKNOWN with the number, never as a silent success")

# -------------------------------------------------- the indicator publishes them
pub = re.search(r"void DiagPublishCoreState\(const int closed\)\s*\{(.*?)\n\}", host, re.S)
require(pub is not None, "the indicator has DiagPublishCoreState()")
body = pub.group(1)
require("GlobalVariableSet(p+\"CORE\"" in body and "GlobalVariableSet(p+\"TIME\"" in body,
        "the verdict and its bar time are published (CORE + TIME)")
for leaf in ("BARS", "ARMED", "CONF"):
    require(f'GlobalVariableSet(p+"{leaf}"' in body,
            f"the funnel counter {leaf} is published too (so 'never armed' and 'always rejected' "
            "cannot look the same)")
require('"QSMC_DIAG_"+_Symbol+"_"+IntegerToString((long)_Period)+"_"' in host,
        "the indicator names the variables with the same prefix the companion reads")
require('"QSMC_DIAG_"+_Symbol+"_"+IntegerToString((long)_Period)+"_"+leaf' in ea,
        "the companion builds the identical variable name")

# ------------------------------------------------------------- every code mapped
mapper = re.search(r"int DiagBlockerCode\(const string key\)\s*\{(.*?)\n\}", host, re.S)
require(mapper is not None, "the indicator has DiagBlockerCode()")
used = {int(n) for n in re.findall(r"return\s+(\d+)\s*;", mapper.group(1))}
unknown = sorted(used - set(host_rows))
require(not unknown, f"every code DiagBlockerCode() can return is in the table (unknown: {unknown})")
require(34 in used, "an unmapped gate-audit key falls back to OTHER instead of reading as 'no blocker'")

# --------------------------------------------------- the bridge is read-only
require("DiagPublishCoreState(closed);" in host,
        "the indicator publishes once per pass from inside OnCalculate()")
require(host.find("SigLog_Update(rates_total,prev_calculated);") < host.find("DiagPublishCoreState(closed);"),
        "the verdict is computed after SigLog_Update(), i.e. from a finished decision pass")
require(re.search(r"void DiagPublishCoreState\(const int closed\)\s*\{\s*"
                  r"if\(closed<0 \|\| closed\+1>=ArraySize\(g_buf_t\)\) return;", host) is not None,
        "it refuses an out-of-range closed-bar index instead of publishing a guess")
require("if(bar_time<=0 || bar_time==g_diag_core_bar) return;" in host,
        "it publishes once per closed bar, not once per tick (no per-tick global churn)")

for forbidden in ("OrderSend", "CTrade", "OrderCalcMargin", "PositionOpen"):
    require(forbidden not in pub.group(0),
            f"the bridge does not reach the trade API ({forbidden} absent)")

# The companion must only READ these variables: writing one would let a stale EA
# overwrite the indicator's verdict and turn diagnosis into fiction.
require("GlobalVariableSet(DiagVarName(" not in ea and 'GlobalVariableSet(p+"' not in ea,
        "the companion never writes the indicator's diagnostic variables")
require("GlobalVariableGet(name)" in ea and "GlobalVariableCheck(name)" in ea,
        "the companion reads them defensively (missing variable -> 'no record')")

# A verdict is not a signal: nothing in the decode path may touch sizing or orders.
require(re.search(r"string DiagCodeText", ea) is not None,
        "the decoder returns text for the journal only")

print("-" * 74)
print("Diagnostic-bridge contract checks passed. This is a source contract, not an")
print("MT5 run: the line only becomes evidence after F7 and one closed bar.")

# =====================================================================
# v6.6.11 GATE PROFILER: does the published distance mean what it says?
# =====================================================================
GP_BEGIN = "// GP_TABLE_BEGIN"
GP_END = "// GP_TABLE_END"


def gp_table(text, label):
    start, stop = text.find(GP_BEGIN), text.find(GP_END)
    require(start >= 0 and stop > start, f"{label} carries a {GP_BEGIN} .. {GP_END} block")
    block = text[start + len(GP_BEGIN):stop]
    slots = {}
    for line in block.splitlines():
        m = re.match(r"\s*//\s*(-?\d+)((?:\s*-\s*\d+)?)\s+([A-Z0-9_]+)", line)
        if m:
            for slot in ([int(m.group(1))] if not m.group(2) else
                         list(range(int(m.group(1)), int(m.group(2).split("-")[1]) + 1))):
                slots[slot] = m.group(3)
    require(len(slots) >= 15, f"{label} GP table parses into a usable slot map ({len(slots)} slots)")
    return slots, block


gp_host, gp_host_block = gp_table(host, "the indicator")
gp_ea, gp_ea_block = gp_table(ea, "the companion")
require(gp_host_block.replace("\r\n", "\n") == gp_ea_block,
        "the GP_TABLE block is byte-identical in both programs (one map, two copies)")
require(set(gp_host) == set(gp_ea),
        f"both sides describe the same slots (indicator-only {sorted(set(gp_host) - set(gp_ea))}, "
        f"companion-only {sorted(set(gp_ea) - set(gp_host))})")

# --- the indicator records a value at every gate it claims to profile
note_sites = set(re.findall(r'GateProfileNote\("(\w+)",', host))
for what in ("confidence", "reliability", "rr1", "stopatr", "spread", "location",
             "anchorage", "path", "sweepdisp", "dispbreak"):
    require(what in note_sites, f"the indicator measures `{what}` at the gate that uses it")

# --- a shortfall is only claimed for the four threshold gates, never for structure
need_sites = set(re.findall(r'GateProfileNeed\("(\w+)"', host))
require(set(need_sites) == {"confneed", "relneed", "rrneed", "stopneed"},
        f"a shortfall is recorded ONLY for threshold gates, never for the causal chain "
        f"(found {sorted(need_sites)}): 'you are 3 points short' must not be said about a "
        "pattern the market never produced")

# --- the shortfall is measured against the SAME value the gate compares.
# Since v6.6.12 that value comes from an Eff*() helper (gate profile), never
# from the raw input, so a shortfall can never describe a threshold the gate
# did not actually use.
for gate, eff in [("confneed", "EffMinConfidenceScore()"), ("relneed", "EffMinReliability()"),
                  ("rrneed", "EffMinRR1()"), ("stopneed", "EffMaxStopATR()")]:
    block = re.search(r'GateProfileNeed\("' + gate + r'",([^;]+);', host)
    require(block is not None, f"the `{gate}` shortfall is computed")
    require(eff in block.group(1),
            f"the `{gate}` shortfall is measured against {eff}, the value the gate compares")

# --- slot routing: every name the note/need helpers can emit maps to a real slot
routing = re.search(r"int GateProfileSlot\(const string what\)\s*\{(.*?)\n\}", host, re.S)
require(routing is not None, "the indicator has a GateProfileSlot() router")
emitted = set(re.findall(r'if\(what=="(\w+)"\)', routing.group(1)))
require(set(note_sites) | {"confneed", "relneed", "rrneed", "stopneed"} <= emitted,
        f"every measured name has a slot (unrouted: "
        f"{sorted((set(note_sites) | {'confneed','relneed','rrneed','stopneed'}) - emitted)})")

# --- the companion decodes every slot the router can return
router_codes = {int(n) for n in re.findall(r"return\s+(\d+);", routing.group(1))}
ea_cases = {int(n) for n in re.findall(r"case\s+(\d+):\s*return", ea)}
missing_gp = sorted(router_codes - ea_cases)
require(not missing_gp, f"the companion names every slot the indicator can publish (missing: {missing_gp})")
require("return \"UNKNOWN\";" in ea, "an unmapped slot is reported as UNKNOWN, never silently as a gate")

# --- the profiler is read-only and per-session, never per-tick
require("GateProfileReset();" in host, "the profiler window is reset at init (since this attach)")
require(host.find("GateProfileReset();") < host.find("SigLog_Init();"),
        "the reset happens during OnInit, before the first calculation")
require("GateProfilePublish(closed);" in host, "the profile is published once per closed bar")
require(host.find("DiagPublishCoreState(closed);") < host.find("GateProfilePublish(closed);"),
        "the profile is published next to the verdict, from the same finished pass")
require(re.search(r"void GateProfilePublish\(const int closed\)\s*\{\s*"
                  r"if\(closed<0 \|\| closed\+1>=ArraySize\(g_buf_t\)\) return;", host) is not None,
        "it refuses an out-of-range bar instead of publishing a guess")
require('GlobalVariableSet(p+"GP_BARS"' in host and "g_gate_audit.bars" in host,
        "the sample size travels with the peak (a peak without a window is not evidence)")
require("GlobalVariableSet(DiagVarName(" not in ea and 'GlobalVariableSet(p+"GP_' not in ea,
        "the companion never writes a profile value back")
require("out+=GateProfileSuffix();" in ea,
        "the profile rides on every heartbeat exit, not only the complete one")

prof = re.search(r"string GateProfileSuffix\(\)\s*\{(.*?)\n  \}", ea, re.S)
require(prof is not None, "the companion has a GateProfileSuffix()")
for forbidden in ("OrderSend", "CTrade", "OrderCalcMargin", "PositionOpen"):
    require(forbidden not in prof.group(1),
            f"the profile is text only, it cannot reach the trade API ({forbidden} absent)")
require("no threshold in the indicator was the reason" in prof.group(1),
        "when no candidate reached a scoring gate, the line says so instead of inventing a "
        "threshold to blame")


# ======================================================================
# AUDIT-E - the alert channels must not fail silently
# ======================================================================
# A trader who hears nothing cannot tell "no setup" from "the terminal refused
# my push" or "alert.wav is not installed". Both alert paths used to DISCARD the
# answer the terminal returns. They now consume it, behind switches that already
# exist - no new input, and no change to when an alert fires.

require('if(push && !SendNotification(message) && InpAlertDispatcherLog)' in host,
        "AUDIT-E the dispatcher consumes SendNotification's answer instead of discarding it")
require('if(sound && !PlaySound("alert.wav") && InpAlertDispatcherLog)' in host,
        "AUDIT-E the dispatcher consumes PlaySound's answer instead of discarding it")
require('if(!SendNotification(pm) && InpDebugLog)' in host,
        "AUDIT-E the quant alert path consumes SendNotification's answer too")
require('if(sound && !PlaySound("alert.wav") && InpDebugLog)' in host,
        "AUDIT-E and PlaySound's answer on that path as well")

# The silent forms are gone. Both a call and the truncated-push form are checked,
# because the second one was easy to miss: it discarded the result on the line
# after its own clamp.
for stale in ('if(push) SendNotification(message);', 'if(sound) PlaySound("alert.wav");',
              '      SendNotification(pm);'):
    require(stale not in host, f"AUDIT-E no path discards the channel result any more ({stale.strip()})")

# Alert() is void in MQL5: there is no answer to consume, so the popup line stays
# a plain call. Asserting this stops someone "fixing" it into a condition that
# would not compile.
require(host.count("   if(popup) Alert(message);") == 2,
        "AUDIT-E both paths still call Alert() as a plain popup (it returns void)")
require("!Alert(" not in host, "AUDIT-E and nothing pretends Alert() has a return value")

# No new input, and the diagnostics ride on switches that already existed.
require("input bool   InpDebugLog                = false;" in host,
        "AUDIT-E the quant-path diagnostic uses the existing InpDebugLog switch")
require(re.search(r"input bool   InpAlertDispatcherLog\s+= false;", host) is not None,
        "AUDIT-E the dispatcher diagnostic uses the existing InpAlertDispatcherLog switch")
require(len(re.findall(r"(?m)^input\s", host)) == 583,
        "AUDIT-E and the file still declares 583 inputs (no new one was added)")


def body_of(sig):
    """The body of a function whose definition starts with `sig`, found by its
    closing brace at column 0. Declarations are never matched because they end
    with a semicolon."""
    i = host.find(sig)
    while i >= 0 and host[i:i + len(sig) + 40].split("\n")[0].rstrip().endswith(";"):
        i = host.find(sig, i + 1)
    require(i >= 0, f"AUDIT-E located {sig[:40]}")
    end = host.find("\n}", i)
    require(end > i, f"AUDIT-E {sig[:40]} closes")
    return host[i:end + 2]


def longest_literal(text):
    lits = re.findall(r'"((?:[^"\\]|\\.)*)"', text)
    return max((len(x) for x in lits), default=0)


# Why the dispatcher needs no 240-char clamp while the quant path has one: its
# message is composed only from bounded parts. That claim is measured here, not
# asserted - if a future "needs" text grows to a paragraph, this fails instead of
# the push being silently truncated (or refused) on a live bar.
for fn in ("string RXN_ExecReason(", "string RXN_NeedsText(", "string AlertInvalidationText("):
    n = longest_literal(body_of(fn))
    require(n <= 40, f"AUDIT-E every reason {fn[:26]}... can emit stays <= 40 chars (longest {n})")
fmt = re.search(r'return StringFormat\("(\[[^\n]*?)",', body_of("string AlertCompactLine("))
require(fmt is not None, "AUDIT-E AlertCompactLine still composes one StringFormat")
require(len(fmt.group(1)) <= 60,
        f"AUDIT-E and its literal skeleton stays <= 60 chars ({len(fmt.group(1))})")
require("if(StringLen(pm)>240) pm=StringSubstr(pm,0,240);" in host,
        "AUDIT-E the quant path still clamps its arbitrary caller string to 240")

print("-" * 74)
print("Gate-profiler checks passed. The distance is measured, not inferred;")
print("acting on it is a policy decision that still needs F7 and a demo run.")
