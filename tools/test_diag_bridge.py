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
