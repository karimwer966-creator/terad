#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QATS-BUILD - the whole EA must build with a strict host compiler, cleanly.

WHAT THIS PROVES
----------------
tools/qats_native.py rewrites QuantumAutonomousTradingSystem.mq5 mechanically
into C++ and compiles the ENTIRE file against a typed MQL5 API shim with
-Wall -Wextra -Wconversion -Wshadow ... -Werror. This suite asserts:

  A. the MQL5-only lint finds nothing (struct by value, assignment to an input,
     C++-only syntax ...);
  B. the strict host build of the shipped source is clean: zero errors AND zero
     warnings;
  C. the gate has teeth: fourteen deliberate defects, one per MetaEditor
     diagnostic class this repository has actually shipped or that the rewrite
     could hide, are each REJECTED - and the diagnostic points at the right
     .mq5 line;
  D. the rewrite itself is sound: every function has a generated prototype,
     every input is registered, diagnostics keep their .mq5 line numbers;
  E. every PrintFormat / StringFormat call - including the ones no test reaches -
     carries exactly as many arguments as its format string has conversions;
  F. every operand of every if / while / for / ?: / && / || / ! is a `bool`
     (MetaEditor: "expression not boolean"), established by the host compiler's
     type checker - and eight deliberate integer conditions are each rejected.

WHAT IT DOES NOT PROVE
----------------------
This is NOT MetaEditor. MQL5 and C++ are different languages; a clean host
build is strong evidence, not proof, of a clean F7. Press F7.

Exit code: 0 verified, 77 no host C++ compiler here, 1 verified and failed.
"""
from __future__ import print_function

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qats_native as Q  # noqa: E402

FAILURES = []
COUNT = [0]


def check(ok, label, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + label)
    else:
        print("FAIL  " + label + (("  [" + detail + "]") if detail else ""))
        FAILURES.append(label)


def first_error_line(diag, name):
    m = re.search(re.escape(name) + r":(\d+):\d+: error", diag)
    return int(m.group(1)) if m else -1


def main():
    if not Q.find_compiler():
        print("SKIP  qats-native-build: this host has no usable C++17 compiler (g++, c++, clang++)")
        print("      NOT verified here. The Linux CI run on every push has one.")
        return Q.SKIP_EXIT

    with open(Q.EA_SOURCE, "r", encoding="utf-8") as fh:
        src = fh.read()

    # ---------------------------------------------------------------- A. lint
    lint = Q.mql5_lint(src)
    check(not lint, "A1 MQL5-only lint finds nothing in the shipped source", "; ".join(lint[:3]))
    check("\r" not in src and "\t" not in src and all(ord(c) < 128 for c in src),
          "A2 the source is pure ASCII, LF line ends, no tabs (byte-exact for MetaEditor)")
    check(src.count('#include') == 1 and '#include <Trade/Trade.mqh>' in src,
          "A3 single-file rule: the only include is <Trade/Trade.mqh>")

    # ------------------------------------------------- B. strict clean build
    exe, rc, diag = Q.build(Q.EA_SOURCE, "strict")
    check(rc == 0, "B1 the WHOLE EA builds against the typed MQL5 shim (0 errors)",
          diag.strip().splitlines()[0] if diag.strip() else "")
    check(rc == 0 and diag.strip() == "", "B2 ... with zero warnings under %d strict flags" % len(Q.STRICT_FLAGS),
          diag.strip()[:300])
    check(exe is not None and os.path.isfile(exe), "B3 the build produced a runnable simulator binary")

    # --------------------------------------------- C. the gate rejects defects
    name = "defect.mq5"
    path = os.path.join(Q.OUT_DIR, name)

    def line_of(text, needle):
        return text[:text.index(needle)].count("\n") + 1

    anchor = "   double atrStop = 1.5 * atr;"
    assert src.count(anchor) == 1
    cases = [
        ("double -> int without a cast (possible loss of data)",
         src.replace(anchor, anchor + "\n   int lossy = atrStop * 2.0; atrStop += lossy;"), "build", "int lossy"),
        ("long -> int without a cast (possible loss of data)",
         src.replace(anchor, anchor + "\n   int narrow = SymbolInfoInteger(_Symbol, SYMBOL_DIGITS); atrStop += narrow;"), "build", "int narrow"),
        ("a double property read through SymbolInfoInteger",
         src.replace("SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT)", "SymbolInfoInteger(_Symbol, SYMBOL_VOLUME_LIMIT)"), "build",
         "SymbolInfoInteger(_Symbol, SYMBOL_VOLUME_LIMIT)"),
        ("an integer deal property read through HistoryDealGetDouble",
         src.replace("HistoryDealGetDouble(ticket, DEAL_SWAP)", "HistoryDealGetDouble(ticket, DEAL_MAGIC)"), "build",
         "HistoryDealGetDouble(ticket, DEAL_MAGIC)"),
        ("a local that hides a global (declaration hides global declaration)",
         src.replace(anchor, "   double g_dayPnL = 1.5 * atr;\n   double atrStop = g_dayPnL;"), "build", "double g_dayPnL = 1.5"),
        ("an unused local variable", src.replace(anchor, anchor + "\n   int neverUsed = 3;"), "build", "int neverUsed"),
        ("string + number (implicit conversion from 'number' to 'string')",
         src.replace('g_executionReason = "invalid direction";', 'g_executionReason = "invalid direction" + 5;'), "build",
         '"invalid direction" + 5'),
        ("an undeclared identifier", src.replace(anchor, "   double atrStop = 1.5 * atrr;"), "build", "atrr;"),
        ("a function that does not return on every path",
         src.replace("   if(net < -b) return -1;\n   return 0;\n}", "   if(net < -b) return -1;\n}"), "build", None),
        ("a call with a missing argument",
         src.replace("QATS_ScoreEligible(dir, e.score, InpMinScore)", "QATS_ScoreEligible(dir, e.score)"), "build",
         "QATS_ScoreEligible(dir, e.score)"),
        ("a member that the struct does not have",
         src.replace("   e.vwapSide   = bull", "   e.vwapside   = bull"), "build", "e.vwapside"),
        ("a struct parameter passed by value (objects are passed by reference only)",
         src.replace("int QATS_ScoreSide(const SSide &e)", "int QATS_ScoreSide(const SSide e)"), "lint", None),
        ("an assignment to an input (constant cannot be modified)",
         src.replace(anchor, anchor + "\n   InpMinScore = 10;"), "lint", None),
        ("a free function declared static",
         src.replace("int SideIndex(const int dir)", "static int SideIndex(const int dir)"), "lint", None),
    ]
    for label, text, how, needle in cases:
        if text == src:
            check(False, "C  defect '%s' could not be injected (anchor moved)" % label)
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        if how == "lint":
            problems = Q.mql5_lint(text)
            check(bool(problems), "C  lint rejects: " + label, "no lint problem reported")
            continue
        # the missing-return diagnostic is flow-sensitive: it needs the full compile
        _, drc, ddiag = Q.build(path, "defect", syntax_only=("every path" not in label))
        check(drc not in (0, Q.SKIP_EXIT), "C  build rejects: " + label)
        if needle is not None and drc not in (0, Q.SKIP_EXIT):
            want = line_of(text, needle)
            got = first_error_line(ddiag, name)
            check(got == want, "C    ... and the diagnostic points at .mq5 line %d" % want, "reported line %d" % got)

    # ------------------------------------------------- D. the rewrite is sound
    cpp = Q.transpile(src)
    functions = Q.parse_functions(src)
    inputs = Q.parse_inputs(src)
    handlers = {"OnInit", "OnDeinit", "OnTick", "OnTradeTransaction"}
    missing = [n for _, n, _, _ in functions if n not in handlers and not re.search(r"\b%s\(" % re.escape(n), cpp.split("#line", 2)[1])]
    check(len(functions) >= 100, "D1 every top-level function of the EA is discovered (%d)" % len(functions))
    check(not missing, "D2 every function has a generated forward declaration", ", ".join(missing[:5]))
    check(len(inputs) == len(re.findall(r"^input\s", src, re.M)), "D3 every input is discovered (%d)" % len(inputs))
    check(all(('if(qn == "%s")' % n) in cpp for _, n in inputs), "D4 every input is settable by name in the simulator")
    check("#property" not in Q.strip_comments_and_strings(cpp), "D5 #property lines are blanked for the host build")
    # the #line directive after the generated prototypes must resume at the exact
    # .mq5 line of the first function, or every later diagnostic would be shifted
    resume = re.findall(r'^#line (\d+) "', cpp, re.M)
    first_fn_line = src.count("\n", 0, functions[0][3]) + 1
    check(len(resume) == 2 and int(resume[0]) == 1 and int(resume[1]) == first_fn_line,
          "D6 #line resumes at the first function's own .mq5 line (%d): diagnostics keep their line numbers" % first_fn_line,
          "directives: %s" % resume)
    for handler in sorted(handlers):
        check(any(n == handler for _, n, _, _ in functions), "D7 event handler %s is defined" % handler)

    # ------------------------------------- E. static printf audit (every call)
    # The simulator type-checks every format string it EXECUTES. This pass covers
    # the ones a test never reaches: each PrintFormat / StringFormat must carry
    # exactly as many arguments as its format has conversions.
    code = Q.strip_comments_and_strings(src)
    spec_re = re.compile(r"%(?!%)[-+ #0]*\d*(?:\.\d+)?(?:I64|ll|l|h)?[diuxXfeEgGsc]")
    calls, bad_calls, non_literal = 0, [], 0
    for m in re.finditer(r"\b(PrintFormat|StringFormat)\s*\(", code):
        i = m.end()
        depth, args, start = 1, [], i
        while i < len(code) and depth:
            ch = code[i]
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
                if depth == 0:
                    args.append((start, i))
            elif ch == "," and depth == 1:
                args.append((start, i))
                start = i + 1
            i += 1
        calls += 1
        fmt = src[args[0][0]:args[0][1]].strip()
        if not (fmt.startswith('"') and fmt.endswith('"')):
            non_literal += 1
            continue
        specs = len(spec_re.findall(fmt.replace("%%", "")))
        if specs != len(args) - 1:
            bad_calls.append("line %d: %d conversions, %d arguments" % (src.count("\n", 0, m.start()) + 1, specs, len(args) - 1))
    check(calls >= 80, "E1 every PrintFormat / StringFormat call is audited (%d calls)" % calls)
    check(not bad_calls, "E2 every format string has exactly as many conversions as arguments", "; ".join(bad_calls[:4]))
    check(non_literal == 0, "E3 every format string is a literal (auditable)", "%d non-literal formats" % non_literal)

    # --------------------------------- F. "expression not boolean" (every condition)
    # C++ turns an integer into a condition silently; MetaEditor warns. The audit
    # wraps every operand MQL5 requires to be boolean in a checker that accepts
    # only `bool` and lets the host compiler decide from the real types.
    operands, brc, bdiag = Q.bool_audit()
    check(operands >= 500, "F1 every boolean context of the EA is audited (%d operands)" % operands)
    check(brc == 0, "F2 every one of them is a bool: no 'expression not boolean' candidate",
          "\n".join(l for l in bdiag.splitlines() if "required from here" in l or "error" in l)[:300])
    probes = [
        ("an int function call as a condition", "\n   if(PositionsTotal()) atrStop += 0.0;"),
        ("while(int)", "\n   int nLeft = 0; while(nLeft) nLeft--;"),
        ("an int operand of &&", "\n   if(g_tradesToday && g_dayLocked) atrStop += 0.0;"),
        ("an int as the condition of ?:", "\n   atrStop += (g_tradesToday ? 0.0 : 0.0);"),
        ("a long as the condition of an unparenthesised ?:", "\n   atrStop += InpMagic ? 0.0 : 0.0;"),
        ("for(;int;)", "\n   for(int qq = 3; qq; qq--) atrStop += 0.0;"),
        ("a bit test without a comparison", "\n   if(g_spec.fillingMode & 1) atrStop += 0.0;"),
        ("logical NOT of an integer", "\n   if(!PositionsTotal()) atrStop += 0.0;"),
    ]
    for label, extra in probes:
        text = src.replace(anchor, anchor + extra)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        _, prc, pdiag = Q.bool_audit(path, "defect")
        want = line_of(text, anchor) + 1
        m = re.search(r"defect\.mq5:(\d+):\d+:\s+(?:required from here|error)", pdiag)
        check(prc not in (0, Q.SKIP_EXIT) and "expression not boolean" in pdiag and m is not None and int(m.group(1)) == want,
              "F3 the audit rejects: %s (at .mq5 line %d)" % (label, want),
              "rc=%d line=%s" % (prc, m.group(1) if m else "none"))
    text = src.replace(anchor, anchor + "\n   if(PositionsTotal() > 0 && (g_tradesToday != 0 || !g_dayLocked)) atrStop += (g_dayLocked ? 0.0 : 0.0);")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    _, prc, pdiag = Q.bool_audit(path, "defect")
    check(prc == 0, "F4 ... and accepts the same conditions written as comparisons", pdiag.strip()[:200])

    # more lint teeth: constructs C++ accepts and MQL5 does not
    for label, extra in (
            ("a reference variable", "\n   double &alias = atrStop; alias += 0.0;"),
            ("a struct declared inside a function", "\n   struct SLocal { int a; };"),
            ("an MQL5 reserved word used as a variable name", "\n   int input = 3; atrStop += input;")):
        problems = Q.mql5_lint(src.replace(anchor, anchor + extra))
        check(bool(problems), "F5 lint rejects: " + label, "no lint problem reported")

    print("")
    print("-" * 74)
    print("qats-native-build: %d checked, %d failed" % (COUNT[0], len(FAILURES)))
    if FAILURES:
        for f in FAILURES:
            print("  FAILED: " + f)
        return 1
    print("The whole EA builds cleanly against the typed MQL5 shim, and the gate rejects")
    print("every injected defect. This is NOT a MetaEditor compile: F7 remains the gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
