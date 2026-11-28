#!/usr/bin/env python3
"""Include-graph gate: the 34 headers are a DAG, and the context-coupled ones are frozen.

WHY THIS EXISTS
---------------
`MQL5/Include/QSMC/` is not a library, it is a textual splice into a 45 002-line
indicator. MQL5 has no compile-time check for any of the properties that keep
such a splice honest, and every failure mode below has already happened once in
this repository:

  * a header included another header that included it back - harmless only while
    both guards are in place, a hard error the day one guard is edited;
  * a guard was opened with `__QSMC_X_MQH__` and closed with a trailing banner
    after `#endif`, so the file "ended" without closing and the next edit inside
    it compiled into the wrong translation unit;
  * seven headers include NOTHING and compile only because the host happens to
    include them in the right order AFTER `QSMC_Root.mqh`. Three of them read
    globals that exist only in `nadir2.mq5` (555 file-scope globals live there),
    so their dependency is invisible to grep, to the compiler's diagnostics and
    to a reader of the header itself;
  * a header nobody includes is dead weight that still costs the reader's trust.

The dependency graph this gate enforces is the one written down in
`docs/ARCHITECTURE_AUDIT_v6.6.24.md`. The document and this checker must agree:
the document explains, this file refuses to let the explanation rot.

WHAT IT CHECKS
--------------
  I1 Every `#include <QSMC/...>` target resolves to a real file; platform
     includes (`<Trade/...>`, `<Object...>`) are allowlisted, not guessed.
  I2 The header graph is acyclic (DFS colouring, all 34 nodes).
  I3 Every header has a well-formed guard: matching `#ifndef`/`#define` names,
     balanced `#if*`/`#endif`, the closing `#endif` is the last code line, and
     the guard opens before the first `#include`.
  I4 No orphan header: every header is reachable from at least one program.
  I5 The set of CONTEXT-COUPLED headers (no `#include` of their own, yet reading
     a global that is declared only in a host `.mq5`) equals a frozen allowlist.
     A new one fails here instead of compiling by luck.
  I6 Every host includes its context-coupled headers AFTER `QSMC_Root.mqh` (the
     one aggregator), never before it - that ordering is what makes the splice
     reproducible.
  I7 No header calls a FUNCTION that only one host `.mq5` defines. I5 covers
     `g_` globals and skips any header that includes something, so it cannot see
     this: `QSMC_Root.mqh` called `QSMC_SilentReader()`, defined only in
     `nadir2.mq5`, and `QSMC_ArbiterTest.mq5` reaches the aggregator through
     `QSMC_Selftest.mqh` with no indicator in its translation unit. F7 reported
     eight errors for that program; every offline gate passed. A header is
     spliced into whatever includes it, so what it calls must exist in EVERY
     translation unit that reaches it.

WHAT IT DELIBERATELY DOES NOT DO
-------------------------------
It does not compile MQL5, it does not check dialects (`tools/mql5_rules.py`),
it does not decide whether a module boundary is *good*, and it does not re-check
the trade-API allowlist already owned by `tools/check_release_gate.py` (G4/G8).
Rename a header and both gates say so, each in its own vocabulary.

Usage:
  python3 tools/check_include_graph.py            # gate (exit 1 on any FAIL)
  python3 tools/check_include_graph.py --verbose  # print every PASS line too
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INC = ROOT / "MQL5" / "Include"

# Platform includes: resolved by the MetaEditor include path, not by this tree.
PLATFORM_PREFIXES = ("Trade/", "Object", "Chart", "Arrays", "Files")

# I5 - the frozen set of context-coupled headers. Each one includes nothing and
# reads at least one global that only `nadir2.mq5` declares. Adding to this set is
# an architecture decision, not a convenience: edit the list AND the audit doc.
CONTEXT_COUPLED = {
    "QSMC_IncidentSafety.mqh",
    "QSMC_LiquidityValue.mqh",
    "QSMC_UnifiedDecision.mqh",
}

# The one aggregator. Context-coupled headers must be spliced after it.
AGGREGATOR = "QSMC_Root.mqh"

# Hosts = every program that includes the include layer.
HOST_GLOBS = ("*.mq5", "MQL5/Experts/*.mq5", "MQL5/Indicators/*.mq5",
              "MQL5/Scripts/*.mq5")

FAILS: list[str] = []
PASSES: list[str] = []


def ok(msg: str) -> None:
    PASSES.append(msg)


def fail(msg: str) -> None:
    FAILS.append(msg)


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def strip_comments(text: str) -> str:
    """Blanking scanner: code stays, comments and string bodies become spaces.

    A regex pass cannot do this. `nadir2.mq5:635` is a `//|` comment that contains
    the text `<data folder>/MQL5/Include/QSMC/*.mqh`; a `/* */` regex therefore
    opens a block comment at line 635 and closes it at the first `*/` in the file
    (line 21 756), swallowing the real `#include <QSMC/QSMC_Root.mqh>` at line 648.
    A checker that does that reports a graph with 0 edges and passes. Only a real
    line/block/string state machine sees the include.
    """
    out: list[str] = []
    i, n = 0, len(text)
    state = "code"   # code | line | block | dq | sq
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                state = "line"; out.append("  "); i += 2; continue
            if ch == "/" and nxt == "*":
                state = "block"; out.append("  "); i += 2; continue
            if ch == '"':
                state = "dq"; out.append(" "); i += 1; continue
            if ch == "'":
                state = "sq"; out.append(" "); i += 1; continue
            out.append(ch); i += 1; continue
        if state == "line":
            if ch == "\n":
                state = "code"; out.append("\n")
            else:
                out.append(" ")
            i += 1; continue
        if state == "block":
            if ch == "*" and nxt == "/":
                state = "code"; out.append("  "); i += 2; continue
            out.append("\n" if ch == "\n" else " ")
            i += 1; continue
        # string / char literal: never spans a line in MQL5 source we care about
        if ch == "\\" and nxt:
            out.append("  "); i += 2; continue
        if (state == "dq" and ch == '"') or (state == "sq" and ch == "'"):
            state = "code"; out.append(" "); i += 1; continue
        if ch == "\n":
            state = "code"; out.append("\n"); i += 1; continue
        out.append(" "); i += 1
    return "".join(out)


def read(path: Path) -> str:
    return io.open(path, encoding="utf-8", errors="replace").read().replace("\r\n", "\n")


def headers() -> dict[str, str]:
    """Keyed by basename: MQL5 resolves `#include <QSMC/X.mqh>` by basename too."""
    out: dict[str, str] = {}
    for p in sorted(INC.rglob("*.mqh")):
        if p.name in out:
            fail("I0 two headers share the basename %s - includes would be ambiguous" % p.name)
        out[p.name] = read(p)
    return out


INCLUDE_RE = re.compile(r'#include\s+([<"])([^>"]+)[>"]')


def includes_of(text: str) -> list[tuple[str, str]]:
    """[(kind, target)] where kind is '<' or '"'."""
    return [(m.group(1), m.group(2).strip()) for m in INCLUDE_RE.finditer(strip_comments(text))]


def qsmc_edges(name: str, text: str, known: set[str]) -> set[str]:
    """Header-to-header edges, by basename inside MQL5/Include/."""
    edges: set[str] = set()
    for _, target in includes_of(text):
        base = os.path.basename(target)
        if base in known and base != name:
            edges.add(base)
    return edges


DECL_RE = re.compile(r"^[ \t]*(?:static[ \t]+)?(?:const[ \t]+)?[A-Za-z_][\w \t\*&]*[ \t]+(g_[A-Za-z_]\w*)\s*(?:[=;\[])", re.M)


def declared(text: str) -> set[str]:
    return set(DECL_RE.findall(text))


GLOBAL_USE_RE = re.compile(r"\b(g_[A-Za-z_]\w*)")


def hosts() -> dict[str, str]:
    out: dict[str, str] = {}
    for pattern in HOST_GLOBS:
        for p in sorted(ROOT.glob(pattern)):
            if p.is_file():
                out[p.relative_to(ROOT).as_posix()] = read(p)
    return out


# --------------------------------------------------------------------------- #
# I1 - every include resolves
# --------------------------------------------------------------------------- #
def check_resolution(hdrs: dict[str, str], host_texts: dict[str, str]) -> None:
    missing: list[str] = []
    platform = 0
    sources = dict(hdrs)
    sources.update(host_texts)
    for src, text in sources.items():
        for _, target in includes_of(text):
            base = os.path.basename(target)
            if any(target.startswith(p) for p in PLATFORM_PREFIXES):
                platform += 1
                continue
            if not any((INC / target).exists() for _ in (0,)) and base not in {
                os.path.basename(p) for p in INC.rglob("*.mqh")}:
                missing.append("%s -> %s" % (src, target))
    if missing:
        fail("I1 include target(s) that do not exist: %s" % ", ".join(sorted(missing)[:6]))
    else:
        ok("I1 every include resolves (%d platform include(s) allowlisted)" % platform)


# --------------------------------------------------------------------------- #
# I2 - acyclic
# --------------------------------------------------------------------------- #
def check_acyclic(hdrs: dict[str, str]) -> None:
    known = set(hdrs)
    graph = {h: qsmc_edges(h, t, known) for h, t in hdrs.items()}
    colour: dict[str, int] = {}

    def dfs(node: str, path: list[str]) -> list[str] | None:
        colour[node] = 1
        for nxt in sorted(graph.get(node, ())):
            if colour.get(nxt) == 1:
                return path + [node, nxt]
            if nxt not in colour:
                cycle = dfs(nxt, path + [node])
                if cycle:
                    return cycle
        colour[node] = 2
        return None

    for node in sorted(graph):
        if node not in colour:
            cycle = dfs(node, [])
            if cycle:
                fail("I2 include cycle: %s" % " -> ".join(cycle))
                return
    ok("I2 include graph is acyclic (%d header(s), %d edge(s))"
       % (len(graph), sum(len(v) for v in graph.values())))


# --------------------------------------------------------------------------- #
# I3 - guards
# --------------------------------------------------------------------------- #
def check_guards(hdrs: dict[str, str]) -> None:
    bad: list[str] = []
    for name, text in sorted(hdrs.items()):
        lines = [ln.rstrip() for ln in text.split("\n")]
        code = [ln for ln in lines if ln.strip() and not ln.strip().startswith("//")]
        opens = sum(1 for ln in code if re.match(r"\s*#(ifndef|ifdef|if)\b", ln))
        closes = sum(1 for ln in code if re.match(r"\s*#endif\b", ln))
        last_is_endif = bool(code) and re.match(r"\s*#endif\b", code[-1]) is not None
        m = re.search(r"#ifndef\s+(\w+)[^\n]*\n\s*#define\s+(\w+)", text)
        guard_ok = bool(m) and m.group(1) == m.group(2)
        pos_if, pos_inc = text.find("#ifndef"), text.find("#include")
        order_ok = pos_if >= 0 and (pos_inc == -1 or pos_if < pos_inc)
        if not (opens == closes and last_is_endif and guard_ok and order_ok):
            bad.append("%s(open=%d close=%d last=%s guard=%s order=%s)"
                       % (name, opens, closes, last_is_endif, guard_ok, order_ok))
    if bad:
        fail("I3 malformed include guard(s): %s" % "; ".join(bad[:6]))
    else:
        ok("I3 all %d header guards well-formed (#ifndef/#define/#endif, opens before first include)"
           % len(hdrs))


# --------------------------------------------------------------------------- #
# I4 - no orphan header
# --------------------------------------------------------------------------- #
def reachable_from(seeds: list[str], graph: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, ()))
    return seen


def check_reachability(hdrs: dict[str, str], host_texts: dict[str, str]) -> dict[str, set[str]]:
    known = set(hdrs)
    graph = {h: qsmc_edges(h, t, known) for h, t in hdrs.items()}
    per_host: dict[str, set[str]] = {}
    for host, text in host_texts.items():
        seeds = [os.path.basename(t) for _, t in includes_of(text)
                 if os.path.basename(t) in known]
        per_host[host] = reachable_from(seeds, graph)
    covered = set().union(*per_host.values()) if per_host else set()
    orphans = sorted(known - covered)
    if orphans:
        fail("I4 header(s) reachable from no program: %s" % ", ".join(orphans))
    else:
        ok("I4 every header is reachable from a program (all %d covered)" % len(known))
    return per_host


# --------------------------------------------------------------------------- #
# I5 - context-coupled set is frozen
# --------------------------------------------------------------------------- #
def check_context_coupled(hdrs: dict[str, str], host_texts: dict[str, str]) -> None:
    host_globals: dict[str, set[str]] = {}
    for host, text in host_texts.items():
        if host.endswith(".mq5"):
            host_globals[host] = declared(text)
    all_host_globals = set().union(*host_globals.values()) if host_globals else set()

    coupled: dict[str, list[str]] = {}
    for name, text in sorted(hdrs.items()):
        if any(True for _ in includes_of(text)):
            continue
        own = declared(text)
        external = sorted(set(GLOBAL_USE_RE.findall(strip_comments(text))) &
                          all_host_globals - own)
        if external:
            coupled[name] = external

    found = set(coupled)
    if found != CONTEXT_COUPLED:
        new = sorted(found - CONTEXT_COUPLED)
        gone = sorted(CONTEXT_COUPLED - found)
        detail = []
        if new:
            detail.append("new: " + ", ".join("%s (%s)" % (h, ", ".join(coupled[h][:3]))
                                              for h in new))
        if gone:
            detail.append("no longer coupled: " + ", ".join(gone))
        fail("I5 context-coupled set drifted from the frozen allowlist - " + "; ".join(detail))
    else:
        ok("I5 context-coupled headers match the frozen allowlist (%s)"
           % ", ".join(sorted(CONTEXT_COUPLED)))


# --------------------------------------------------------------------------- #
# I6 - ordering: context-coupled headers after the aggregator
# --------------------------------------------------------------------------- #
def check_order(host_texts: dict[str, str]) -> None:
    bad: list[str] = []
    for host, text in sorted(host_texts.items()):
        seq = [os.path.basename(t) for _, t in includes_of(text)]
        if AGGREGATOR not in seq:
            continue
        agg_at = seq.index(AGGREGATOR)
        early = [h for i, h in enumerate(seq) if h in CONTEXT_COUPLED and i < agg_at]
        if early:
            bad.append("%s: %s before %s" % (host, ", ".join(early), AGGREGATOR))
    if bad:
        fail("I6 context-coupled header(s) spliced before the aggregator: %s" % "; ".join(bad))
    else:
        ok("I6 every host splices %s before its context-coupled headers" % AGGREGATOR)


# --------------------------------------------------------------------------- #
# I7 - no header calls a function that only one host defines
# --------------------------------------------------------------------------- #
STR_RE = re.compile(r'"(?:\\.|[^"\\])*"')


def strip_strings(text: str) -> str:
    return STR_RE.sub('""', text)


# A global-scope definition: a type token, then the name, then an open paren.
# Two identifiers are required, so a bare call at line start (`Print(`) or one
# behind an assignment (`got[s]=CopyBuffer(`) does not match.
CALL_RE = re.compile(r"\b([A-Za-z_]\w*)[ \t]*\(")


def funcs_defined(text: str) -> set[str]:
    # A definition's parameter list is followed by `{`, on the same line or the
    # next. Requiring that is what keeps `return MathMin(a,b);` and every other
    # call out of the set - without it the built-ins look like host definitions
    # and the check drowns in false positives.
    src = strip_comments(strip_strings(text))
    out: set[str] = set()
    for m in re.finditer(r"(?m)^[ \t]*(?:static[ \t]+|const[ \t]+)?"
                         r"[A-Za-z_]\w*(?:[ \t]*[*&])?[ \t]+([A-Za-z_]\w*)[ \t]*\(",
                         src):
        close = src.find(")", m.end())
        if close < 0:
            continue
        tail = src[close + 1:close + 60].lstrip()
        # A method may carry `const` (and `final`) between the parameter list
        # and its brace - QSMC_MarketData.mqh declares `HighestHigh(...) const`,
        # and missing that qualifier made two perfectly local methods look like
        # host-only symbols.
        for qual in ("const", "final"):
            if tail.startswith(qual):
                tail = tail[len(qual):].lstrip()
        if tail.startswith("{"):
            out.add(m.group(1))
    return out


def funcs_called(text: str) -> set[str]:
    return set(CALL_RE.findall(strip_comments(strip_strings(text))))


def check_host_only_calls(hdrs: dict[str, str], host_texts: dict[str, str],
                          per_host: dict[str, set[str]]) -> None:
    # A header is spliced into whatever program includes it, so a function it
    # calls must exist in EVERY translation unit that reaches it - not just in
    # the host it was first written for. QSMC_Root.mqh called QSMC_SilentReader()
    # at four sites and that function was defined only in nadir2.mq5, so
    # QSMC_ArbiterTest.mq5 - which reaches QSMC_Root.mqh through
    # QSMC_Selftest.mqh with no indicator in its translation unit - could not
    # compile. F7 reported eight errors for it; every offline gate passed.
    #
    # I5 does not catch this class, for two reasons. It only looks for `g_`
    # prefixed GLOBALS, and a function is not one. And it skips any header that
    # includes something - which exempts QSMC_Root.mqh, the one aggregator that
    # every program reaches.
    host_funcs: dict[str, set[str]] = {
        h: funcs_defined(t) for h, t in host_texts.items() if h.endswith(".mq5")}
    # Symbols that exist in exactly one host and in no header: those are the
    # ones a header has no business calling.
    only_in_host: dict[str, list[str]] = {}
    all_header_funcs = set().union(*[funcs_defined(t) for t in hdrs.values()]) \
        if hdrs else set()
    for host, fns in host_funcs.items():
        for f in fns - all_header_funcs:
            only_in_host.setdefault(f, []).append(host)

    bad: list[str] = []
    for host, reachable in sorted(per_host.items()):
        if not reachable:
            continue
        defined_here = set(host_funcs.get(host, ()))
        for h in reachable:
            defined_here |= funcs_defined(hdrs[h])
        for h in sorted(reachable):
            called = funcs_called(hdrs[h]) - funcs_defined(hdrs[h])
            for f in sorted(called & set(only_in_host) - defined_here):
                bad.append("%s calls %s(), defined only in %s; %s has no definition"
                           % (h, f, ", ".join(sorted(only_in_host[f])), host))
    if bad:
        for b in bad[:8]:
            fail("I7 " + b)
        if len(bad) > 8:
            fail("I7 ... and %d more host-only call(s)" % (len(bad) - 8))
    else:
        ok("I7 no header calls a function that only one host defines "
           "(checked %d program(s))" % sum(1 for v in per_host.values() if v))


# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    hdrs = headers()
    if not hdrs:
        print("FAIL MQL5/Include holds no headers - wrong working directory?")
        return 1
    hosts_ = hosts()
    if not hosts_:
        print("FAIL no .mq5 host found - wrong working directory?")
        return 1

    check_resolution(hdrs, hosts_)
    check_acyclic(hdrs)
    check_guards(hdrs)
    per_host = check_reachability(hdrs, hosts_)
    check_context_coupled(hdrs, hosts_)
    check_order(hosts_)
    check_host_only_calls(hdrs, hosts_, per_host)

    if verbose:
        for line in PASSES:
            print("PASS " + line)
        print("")
        for host in sorted(per_host):
            print("  %-46s %2d header(s)" % (host, len(per_host[host])))
        print("")
    for line in FAILS:
        print("FAIL " + line)
    print("\ninclude-graph: %d checks passed, %d failed" % (len(PASSES), len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
