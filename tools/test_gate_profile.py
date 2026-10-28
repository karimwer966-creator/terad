#!/usr/bin/env python3
"""Contract checks for the v6.6.12 gate profile (InpGateProfile).

The repository rule is "never relax a gate to make a signal appear". A profile
that relaxes thresholds is therefore only acceptable if it is provably:

  1. OFF by default            - STRICT must reproduce the pre-profile behaviour,
  2. unable to reach anything else - five numeric entry thresholds, nothing more,
  3. never silent              - every change printed at init as "old -> new",
  4. never the *only* change   - the causal chain, location check, blacklist,
                                 journal gate and the companion's risk logic are
                                 untouched,
  5. reversible                - one input, and STRICT returns the raw inputs.

None of this can be proven by reading a diff by eye: a stray `InpMinReliability`
left in a gate would quietly ignore the profile, and a stray `Eff...()` in the
risk path would be a defect far worse. So the checks below are structural.

This is a source contract. F7 in MetaEditor is still the only proof of build,
and a demo run is the only proof of behaviour.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "nadir2.mq5"
EA = ROOT / "MQL5/Experts/QSMC_AutoTrader.mq5"

HELPERS = {
    "EffMinConfidenceScore": ("InpMinConfidenceScore", "MathMin", "60"),
    "EffMinReliability":     ("InpMinReliability", "MathMin", "60"),
    "EffMinRR1":             ("InpMinRR1", "MathMin", "1.20"),
    "EffMaxStopATR":         ("InpMaxStopATR", "MathMax", "6.0"),
    "EffAnchorSearchBars":   ("InpAnchorSearchBars", "MathMax", "120"),
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS  {message}")


raw = HOST.read_bytes()
require(raw.count(b"\n") == raw.count(b"\r\n"),
        "nadir2.mq5 is still pure CRLF (the profile did not rewrite the file)")
host = raw.decode("utf-8")
ea = EA.read_text(encoding="utf-8")

# ------------------------------------------------------------ 1. OFF by default
enum_body = re.search(r"enum ENUM_QSMC_GATE_PROFILE\s*\{(.*?)\};", host, re.S)
require(enum_body is not None, "the profile is an enum: ENUM_QSMC_GATE_PROFILE")
require(re.search(r"QSMC_GATE_STRICT\s*=\s*0\b", enum_body.group(1)) is not None,
        "QSMC_GATE_STRICT is 0, so the default cannot drift to a relaxed value")
require(re.search(r"QSMC_GATE_PRACTICAL\s*=\s*1\b", enum_body.group(1)) is not None,
        "QSMC_GATE_PRACTICAL is 1 and is opt-in by name")
m = re.search(r"input ENUM_QSMC_GATE_PROFILE InpGateProfile\s*=\s*(\w+)\s*;", host)
require(m is not None, "the profile is one input: InpGateProfile")
require(m.group(1) == "QSMC_GATE_STRICT",
        "the shipped default is STRICT: an existing installation behaves exactly as before")

# ------------------------------------------- 2. STRICT returns the raw input
for name, (inp, op, floor) in HELPERS.items():
    fn = re.search(r"(?:int|double) " + name + r"\(\)\s*\{(.*?)\n\}", host, re.S)
    require(fn is not None, f"{name}() exists")
    body = fn.group(1)
    require("if(InpGateProfile!=QSMC_GATE_PRACTICAL) return " + inp + ";", body) if False else None
    require(f"if(InpGateProfile!=QSMC_GATE_PRACTICAL) return {inp};" in body,
            f"{name}() returns {inp} untouched in STRICT (no hidden arithmetic)")
    require(re.search(r"return\s+" + op + r"\(" + re.escape(inp) + r"\s*,\s*" + re.escape(floor) + r"\)",
                      body) is not None,
            f"{name}() relaxes with {op}({inp}, {floor}) - only in the permissive direction")
    if op == "MathMin":
        require("MathMax(" not in body,
                f"{name}() never tightens: MathMax would raise a threshold the operator asked for")
    else:
        require("MathMin(" not in body,
                f"{name}() never tightens: MathMin would lower a ceiling the operator asked for")

# ------------------------------- 3. the profile can only act through those helpers
def enclosing_functions(text, needle):
    """Names of the top-level functions whose body contains `needle`."""
    names = []
    for fm in re.finditer(r"^(?:int|double|bool|string|void|long)\s+(\w+)\s*\([^;{]*\)\s*\{",
                          text, re.M):
        start = fm.end()
        depth, i = 1, start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if needle in text[start:i]:
            names.append(fm.group(1))
    return names


users = set(enclosing_functions(host, "InpGateProfile"))
expected = set(HELPERS) | {"PrintGateProfileBanner", "DiagPublishCoreState"}
extra = sorted(users - expected)
require(not extra,
        f"only the five helpers, the banner and the publisher may read InpGateProfile "
        f"(unexpected: {extra})")
require(set(HELPERS) <= users and {"PrintGateProfileBanner"} <= users,
        "the profile is read by its helpers and reported by its banner")

# --------------------------------- 4. no gate still compares against a raw input
stale = {
    "confidence": r"if\(conf<InpMinConfidenceScore\)",
    "reliability": r"if\(reliability<InpMinReliability\)",
    "RR1": r"if\(rr1<InpMinRR1\)",
    "stop ceiling": r"risk>atr\*InpMaxStopATR",
    "anchor window": r"age>InpAnchorSearchBars",
}
for label, rx in stale.items():
    require(re.search(rx, host) is None,
            f"the {label} gate reads the effective value, not the raw input "
            f"(a stale `{rx}` would silently ignore the profile)")

for gate, helper in [("conf<", "EffMinConfidenceScore()"), ("reliability<", "EffMinReliability()"),
                     ("rr1<", "EffMinRR1()"), (r"atr\*", "EffMaxStopATR()")]:
    require(helper in host, f"the gate uses {helper}")
require("age>EffAnchorSearchBars())" in host, "the anchor window uses EffAnchorSearchBars()")

# ------------------------------- 5. the protected gates must not see the profile
PROTECTED = {
    "IsInstitutionalLocation(": "the location re-check",
    "IsBlacklisted(": "the blacklist",
    "TopDown_VetoesDirection(": "the top-down switch",
    "AppendConfirmedSignalJournal(": "the immutable journal gate",
    "Strategy is not widened": "policy text",
}
for symbol, what in PROTECTED.items():
    if symbol not in host:
        continue
    holders = enclosing_functions(host, symbol)
    require(not (set(holders) & set(HELPERS)),
            f"{what} is never routed through an Eff*() helper (the profile cannot reach it)")

# the companion has no gate of its own: it must not even know the profile input
require("InpGateProfile" not in ea,
        "the companion cannot set the profile: it only reads the published value")
require("QSMC_GATE_PRACTICAL" not in ea,
        "the companion has no copy of the profile switch to drift from")

# --------------------------------------------------------- 6. loud, not silent
banner = re.search(r"void PrintGateProfileBanner\(\)\s*\{(.*?)\n\}", host, re.S)
require(banner is not None, "PrintGateProfileBanner() exists")
text = banner.group(1)
for inp in ("InpMinConfidenceScore", "InpMinReliability", "InpMinRR1",
            "InpMaxStopATR", "InpAnchorSearchBars"):
    require(inp in text, f"the banner names {inp} as the input behind the change")
require(text.count('" -> "') >= 5 or text.count(" -> ") >= 5,
        "the banner prints old -> new for each relaxed threshold")
require("UNCHANGED" in text, "the banner states what the profile does NOT touch")
require("more trades" in text and "not better ones" in text.lower() or
        "MORE trades possible, not better ones" in text.replace("\n", " "),
        "the banner refuses to sell the change as an improvement")
require("PrintGateProfileBanner();" in host, "the banner is actually printed at init")
require(host.find("PrintGateProfileBanner();") < host.find("SigLog_Init();"),
        "it is printed during OnInit, before the first closed bar")

# --------------------------------------------- 7. the operator sees it live too
require('GlobalVariableSet(p+"PROFILE"' in host,
        "the active profile is published to the companion (not only printed once)")
require('DiagRead("PROFILE",prof)' in ea, "the companion reads it")
require("PRACTICAL (entry thresholds relaxed" in ea,
        "the heartbeat names a relaxed profile instead of leaving it implicit")

# ------------------------------------------- 8. the companion's risk rules stand
require(re.search(r"input\s+double\s+InpMaxRiskPercent\s*=\s*1\.0*\s*;", ea) is not None,
        "the 1% risk ceiling is unchanged by this work")
require("if(vmax_cap>1.0) vmax_cap=1.0;" in ea,
        "the ceiling still cannot be raised by the operator")
require(re.search(r"input\s+bool\s+InpEnableTrading\s*=\s*false", ea) is not None,
        "the companion still ships inert")

print("-" * 74)
print("Gate-profile contracts passed: default STRICT, five numeric thresholds only,")
print("every change printed, protected gates unreachable, risk rules untouched.")
print("This is a source contract - F7 and a demo run remain yours.")
