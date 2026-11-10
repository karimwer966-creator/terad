#!/usr/bin/env python3
"""MQL5 compile-error contracts: the mistakes MetaEditor rejects that a regex
suite happily accepts.

WHY THIS EXISTS
---------------
v6.6.21 shipped a build that failed F7 with 15 errors that every offline suite
in this tree passed:

  * 12x "'why' - constant cannot be modified"
        QSMC_ClassifySignal(..., const string &why) writes `why`. In MQL5 a
        `const` reference is read-only, so every rejection branch was a compile
        error. The parameter is an OUTPUT; it must not be const.

  * 2x "undeclared identifier 'bullish' / 'bearish'", 1x "undeclared identifier
        'pattern'" + "implicit conversion from 'unknown' to 'string'"
        The entry review read g_candle_intel.bullish/.bearish/.pattern.
        SCandleIntelligence has confirms_buy/confirms_sell/description. Two
        different candle structs exist in the same file (SCandleIntel has
        bullish/bearish/pattern), which is exactly how a member name gets
        borrowed from the wrong one.

Neither is a logic bug - both are pure compile errors - and no static suite in
this tree looked for either. This one does, structurally, because a source scan
is the only compiler we have offline.

This is NOT a MetaEditor compile. It catches these two classes of error and
nothing else. Press F7.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES = []
COUNT = [0]


def check(ok, label, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + label)
    else:
        print("FAIL  " + label + (("  [" + detail + "]") if detail else ""))
        FAILURES.append(label)


def strip(src):
    """Strip comments then strings, in that order (a // inside a string is not a comment)."""
    src = re.sub(r'"(\\.|[^"\\\n])*"', '""', src)
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def body_of(code, open_brace):
    depth = 0
    i = open_brace
    while i < len(code):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[open_brace:i + 1]
        i += 1
    return code[open_brace:]


def functions(code):
    """(name, params, body) for every function DEFINITION (not a declaration)."""
    out = []
    for m in re.finditer(r"(?m)^[A-Za-z_][\w:<>]*\s+(\w+)\s*\(([^;{]*)\)\s*\{", code):
        brace = code.index("{", m.end() - 1)
        out.append((m.group(1), m.group(2), body_of(code, brace)))
    return out


HOST = ROOT / "nadir2.mq5"
SRC = HOST.read_text(encoding="utf-8", errors="replace")
CODE = strip(SRC)

# ---------------------------------------------------------------------------
# 1. A const reference is read-only. Writing through one is a compile error.
#    Found by scanning: every `const T &name` parameter vs assignments to name
#    inside that function's body.
# ---------------------------------------------------------------------------
written_const = []
for fname, params, body in functions(CODE):
    for pm in re.finditer(r"const\s+(?:string|int|double|bool|long|datetime|float)\s*&?\s*(\w+)", params):
        p = pm.group(1)
        if re.search(r"(?<![\w.])" + re.escape(p) + r"\s*=(?!=)", body):
            written_const.append("%s(%s)" % (fname, p))
check(not written_const,
      "no function writes through a `const` reference parameter (12 F7 errors in v6.6.21)",
      ", ".join(sorted(set(written_const))[:6]))

# The two functions that carried the defect, asserted by name so a rename cannot
# quietly reintroduce it.
for fn in ("QSMC_ClassifySignal", "QSMC_ApplyExecClassification"):
    m = re.search(re.escape(fn) + r"\s*\(([^;{]*)\)\s*\n?\s*\{", CODE)
    check(m is not None, "%s is defined (the entry classifier exists)" % fn)
    if m:
        check("const string &why" not in m.group(1),
              "%s takes `string &why` as an OUTPUT, not a const reference" % fn)
        check(("string &why" in m.group(1)),
              "%s still reports why it refused (the reason is not dropped)" % fn)

# ---------------------------------------------------------------------------
# 2. Struct member names must exist on the struct the global actually is.
#    `g_candle_intel` is SCandleIntelligence, NOT SCandleIntel - the two have
#    different member sets and borrowing one from the other is a compile error.
# ---------------------------------------------------------------------------
structs = {}
for m in re.finditer(r"struct\s+(\w+)\s*\{", CODE):
    name = m.group(1)
    b = CODE.index("{", m.end() - 1)
    members = set(re.findall(r"\b(\w+)\s*(?:\[[^\]]*\])?\s*[;,)]", body_of(CODE, b)))
    structs[name] = members

globals_of = {}
for m in re.finditer(r"(?m)^([A-Z]\w+)\s+(g_\w+)\s*;", CODE):
    globals_of[m.group(2)] = m.group(1)

unknown = []
for m in re.finditer(r"\b(g_\w+)\.(\w+)", CODE):
    g, field = m.group(1), m.group(2)
    st = globals_of.get(g)
    if not st or st not in structs:
        continue
    if field not in structs[st]:
        line = CODE[:m.start()].count("\n") + 1
        unknown.append("L%d %s.%s (%s)" % (line, g, field, st))
check(not unknown,
      "every g_<global>.<member> access names a member that struct really declares",
      "; ".join(unknown[:6]))

# The specific borrow that failed F7, pinned both ways.
check("bullish" not in structs.get("SCandleIntelligence", set()),
      "SCandleIntelligence does NOT declare `bullish` (that is SCandleIntel's member)")
check("pattern" not in structs.get("SCandleIntelligence", set()),
      "SCandleIntelligence does NOT declare `pattern` (it carries `description`)")
for need in ("confirms_buy", "confirms_sell", "description", "score", "valid"):
    check(need in structs.get("SCandleIntelligence", set()),
          "SCandleIntelligence declares `%s` (what the entry review must read)" % need)
for banned in ("g_candle_intel.bullish", "g_candle_intel.bearish",
               "g_candle_intel.pattern"):
    check(banned not in CODE,
          "the entry review does not read %s" % banned)

# ---------------------------------------------------------------------------
# 3. The entry review itself must survive: it is new code, so a rename here is
#    how the whole feature disappears silently.
# ---------------------------------------------------------------------------
check("QSMC_BuildEntryReview" in CODE, "the entry review builder is still defined")
check("confirms_buy" in CODE and "confirms_sell" in CODE,
      "the review still tests the candle in BOTH directions")

# ---------------------------------------------------------------------------
# 4. Every `input` used somewhere must be declared (the QATS defect this same
#    family of check caught in CI).
# ---------------------------------------------------------------------------
# The declaration table spans nadir2.mq5 AND the headers it includes, and it
# contains comma declarations (`input int InpAsianStart = 9, InpAsianEnd = 18;`).
# Reinventing that parser here is how the first version of this check produced
# eight false positives, so this borrows the one that already handles both.
sys.path.insert(0, str(ROOT / "tools"))
import generate_input_fingerprint as FP  # noqa: E402

declared = set()
for rel in FP.paths:
    f = ROOT / rel
    if f.is_file():
        declared.update(name for _, name, _ in FP.parse_inputs(f.read_text(encoding="utf-8")))
used = set(re.findall(r"\b(Inp\w+)\b", CODE))
undeclared = sorted(u for u in used if u not in declared)
check(not undeclared,
      "every Inp* identifier used in code is declared as an input",
      ", ".join(undeclared[:8]))

print("")
print("-" * 74)
print("compile-error contracts: %d checked, %d failed" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: " + f)
    print("")
    print("These are the errors MetaEditor rejects. Fix them before F7.")
    sys.exit(1)
print("No const-reference writes, no unknown struct members, no undeclared inputs.")
print("This is NOT a MetaEditor compile - it catches these classes and nothing else.")
