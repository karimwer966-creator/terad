#!/usr/bin/env python3
"""Negative + positive contracts for tools/check_include_graph.py.

WHY THIS EXISTS
---------------
A gate that has only ever been run against a tree that passes is not evidence of
anything: it may be passing because its predicate is `return True`. This file
drives each predicate of the include-graph gate with input it must reject, and
then runs the real tree once. Every case below is a failure mode that occurred
in this repository or a near-miss observed while the gate was written:

  * a `//` comment containing `/*` opened a block comment that swallowed a real
    `#include` 13 lines later (`nadir2.mq5:635` vs `:648`); a regex-based scanner
    reported a 0-edge graph and passed;
  * a `#endif` followed by a trailing banner (the house style) is a well-formed
    guard, while a missing `#endif` is not - both must be told apart;
  * a header with no `#include` of its own reading `g_*` globals from the host is
    the norm for three headers and an accident for a fourth;
  * a host that splices a context-coupled header BEFORE `QSMC_Root.mqh` compiles
    only by luck, because the aggregator is what declares the types it needs.

Run:  python3 tools/test_include_graph.py
"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_gate():
    spec = importlib.util.spec_from_file_location("check_include_graph",
                                                  ROOT / "tools" / "check_include_graph.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reset(mod) -> None:
    mod.FAILS.clear()
    mod.PASSES.clear()


def case(cond: bool, label: str) -> None:
    assert cond, label


def main() -> int:
    g = load_gate()

    # ---- T1: the comment trap that a regex scanner falls into ---------------
    trap = (
        "//|   <data folder>/MQL5/Include/QSMC/*.mqh                           |\n"
        "#include <QSMC/QSMC_Root.mqh>\n"
        "int x = 1; // #include <QSMC/Ignored.mqh>\n"
        "/* #include <QSMC/BlockIgnored.mqh> */\n"
        "// #include <QSMC/LineIgnored.mqh>\n"
        "char *s = \"#include <QSMC/StringIgnored.mqh>\";\n"
        "   true /*sweep ok*/\n"
    )
    seen = [t for _, t in g.includes_of(trap)]
    case(seen == ["QSMC/QSMC_Root.mqh"],
         "T1 scanner must see exactly the real include, got %r" % (seen,))

    # ---- T2: real tree has the include the trap hides ----------------------
    host = g.read(ROOT / "nadir2.mq5")
    case("QSMC/QSMC_Root.mqh" in [t for _, t in g.includes_of(host)],
         "T2 nadir2.mq5's QSMC_Root.mqh include must be visible through the trap")

    # ---- T3: edges are header-to-header, by basename ------------------------
    known = {"A.mqh", "B.mqh"}
    case(g.qsmc_edges("A.mqh", "#include <QSMC/B.mqh>", known) == {"B.mqh"},
         "T3 include of a known header must be an edge")
    case(g.qsmc_edges("A.mqh", "#include <Trade/Trade.mqh>", known) == set(),
         "T3 platform include must not become an edge")

    # ---- T4: a cycle is rejected -------------------------------------------
    reset(g)
    g.check_acyclic({"A.mqh": "#include <QSMC/B.mqh>", "B.mqh": "#include <QSMC/A.mqh>"})
    case(g.FAILS and "cycle" in g.FAILS[0], "T4 cycle must fail: %r" % (g.FAILS,))

    # ---- T5: guards - well-formed with a trailing banner passes ------------
    good = ("//| banner |\n#ifndef X_MQH\n#define X_MQH\nint y;\n#endif\n"
            "//+------------------------------------------------------------------+\n")
    reset(g)
    g.check_guards({"good.mqh": good})
    case(not g.FAILS, "T5 well-formed guard with trailing banner must pass: %r" % (g.FAILS,))

    # ---- T6: guards - missing #endif / name mismatch fail ------------------
    for bad, why in ((good.replace("#endif\n", ""), "missing #endif"),
                     (good.replace("#define X_MQH", "#define Y_MQH"), "guard name mismatch")):
        reset(g)
        g.check_guards({"bad.mqh": bad})
        case(g.FAILS, "T6 %s must fail" % why)

    # ---- T7: context coupling is detected -----------------------------------
    fake_host = {"nadir2.mq5": "double g_live = 0.0;\n"}
    reset(g)
    g.check_context_coupled({"QSMC_New.mqh": "void f(){ g_live = 1.0; }"}, fake_host)
    case(g.FAILS and "QSMC_New.mqh" in g.FAILS[0],
         "T7 a new header reading host globals must fail: %r" % (g.FAILS,))

    # ---- T8: ordering - context header before the aggregator fails ---------
    reset(g)
    g.check_order({"h.mq5": "#include <QSMC/QSMC_IncidentSafety.mqh>\n"
                            "#include <QSMC/QSMC_Root.mqh>\n"})
    case(g.FAILS, "T8 context-coupled header spliced before the aggregator must fail")

    # ---- T9: the real tree passes, with the documented geometry ------------
    reset(g)
    quiet = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, quiet
    try:
        rc = g.main([])
    finally:
        sys.stdout = real_stdout
    case(rc == 0, "T9 the live tree must pass all include-graph checks")
    case(len(g.PASSES) == 6, "T9 expected 6 passing checks, got %d" % len(g.PASSES))
    text = "\n".join(g.PASSES)
    for token in ("34 header(s)", "54 edge(s)", "well-formed"):
        case(token in text, "T9 %r missing from the gate's own report" % token)

    print("PASS include-graph gate: comment trap, cycles, guards, coupling, order, "
          "and the live 34-header / 54-edge tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
