#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QATS-NATIVE - build the REAL QuantumAutonomousTradingSystem.mq5 with a host
C++17 compiler against a typed MQL5 API shim, and run it in a simulator.

WHY THIS EXISTS
---------------
There is no MetaEditor on a Linux box, so until now the only things that could
be said offline about the EA were structural (balanced braces, declared
identifiers) plus a handful of function bodies compiled in isolation with
hand-written stubs. That left three gaps:

  * nothing type-checked the WHOLE file (a double property read through
    SymbolInfoInteger, a struct passed by value, an int receiving a double);
  * nothing executed the real analysis / scoring / guard / execution path end to
    end, in BOTH directions, on real price data;
  * nothing could prove direction symmetry.

This module closes them as far as an offline tool can:

  transpile()  a purely MECHANICAL rewrite of the .mq5 text into C++:
                 - `#property` and the Trade.mqh include are blanked,
                 - `input` becomes a plain global (so a test can set it),
                 - `T name[]` / `T &name[]` become MqlArray<T>,
                 - every enum gets a fixed `int` underlying type,
                 - forward declarations are generated (MQL5 needs none, C++ does),
                 - `#line` keeps every diagnostic on its ORIGINAL .mq5 line.
               No logic is touched: the function bodies the simulator runs are
               the bytes MetaEditor compiles.

  build()      g++ -std=c++17 with the strict warning set below, treating the
               EA text - and only the EA text - as warnings-are-errors. The shim
               mirrors MQL5 signatures and typed property enums, so the host
               diagnostics line up with MetaEditor's own classes.

  mql5_lint()  rules for what C++ accepts but MQL5 rejects or warns about
               (struct parameters by value, assignment to an input, C++-only
               syntax, struct member initialisers, reference variables, local
               types, MQL5-only reserved words used as names ...).

  bool_audit() MetaEditor warns "expression not boolean" when an integer is used
               as a condition; C++ converts it silently. Every operand of every
               if / while / for / ?: / && / || is wrapped in a checker that only
               accepts `bool`, and the result is type-checked by the host
               compiler - so the answer comes from real types, not from regexes.

WHAT IT IS NOT
--------------
NOT MetaEditor. A green host build is evidence, never proof, of a clean F7:
MQL5 and C++ differ, and this file says so in its own output. F7 stays the gate.

Exit code convention (see tools/native_toolchain.py): 0 verified, 77 no usable
host compiler here, anything else = verified and failed.
"""
from __future__ import print_function

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EA_SOURCE = os.path.join(ROOT, "MQL5", "Experts", "QuantumAutonomousTradingSystem.mq5")
SIM_DIR = os.path.join(ROOT, "tools", "qats_sim")
SHIM = os.path.join(SIM_DIR, "mql5_shim.h")
DRIVER = os.path.join(SIM_DIR, "qats_driver.inc")
OUT_DIR = os.path.join(ROOT, "out", "qats_native")

SKIP_EXIT = 77

# The warning set applied to the EA text. Each flag stands in for a MetaEditor
# diagnostic class:
#   -Wconversion / -Wfloat-conversion  "possible loss of data due to type conversion"
#   -Wshadow                           "declaration of 'x' hides global/local declaration"
#   -Wunused-variable / -but-set       "variable 'x' not used"
#   -Wreturn-type                      "not all control paths return a value"
#   -Wuninitialized / -Wmaybe-...      "possible use of uninitialized variable"
#   -Wsign-compare                     "sign mismatch"
#   -Wparentheses / -Wempty-body       "expression not boolean" style slips
STRICT_FLAGS = [
    "-Wall", "-Wextra", "-Wconversion", "-Wfloat-conversion", "-Wshadow",
    "-Wsign-compare", "-Wreturn-type", "-Wuninitialized", "-Wmaybe-uninitialized",
    "-Wunused-variable", "-Wunused-but-set-variable", "-Wparentheses", "-Wempty-body",
    "-Wno-unused-parameter", "-Wno-unused-function",
    # MQL5 converts long <-> ulong and int <-> uint silently in assignments and
    # arguments (CTrade::SetExpertMagicNumber(const ulong) fed an `input long`
    # is the documented idiom); the comparison case stays on via -Wsign-compare.
    "-Wno-sign-conversion",
    "-Werror",
]

SCALAR_TYPES = ("int", "uint", "long", "ulong", "short", "ushort", "char", "uchar",
                "bool", "double", "float", "string", "datetime", "color")

# Reserved in MQL5, ordinary identifiers (or contextual keywords) in C++.
MQL5_ONLY_RESERVED = ("input", "sinput", "group", "interface", "import", "export", "pack",
                      "final", "override", "property", "strict", "string", "color", "datetime",
                      "uchar", "ushort", "uint", "ulong")


def find_compiler():
    """Path of a usable C++17 compiler, or None. Honours QSMC_NO_NATIVE=1."""
    if os.environ.get("QSMC_NO_NATIVE"):
        return None
    for name in ("g++", "c++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    return None


def strip_comments_and_strings(text):
    """Blank comments and string/char literals, preserving length and newlines."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and nxt == "*":
            while i < n and text[i:i + 2] != "*/":
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
            continue
        if c in "\"'":
            quote = c
            out.append(quote)
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    out.append("  ")
                    i += 2
                    continue
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            out.append(quote)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


FUNC_RE = re.compile(
    r"^(?P<ret>[A-Za-z_]\w*)[ \t]+(?P<name>[A-Za-z_]\w*)[ \t]*\((?P<params>[^()]*)\)[ \t]*\n\{",
    re.M)
ARRAY_PARAM_RE = re.compile(r"(?P<const>\bconst\s+)?(?P<type>[A-Za-z_]\w*)\s*&\s*(?P<name>[A-Za-z_]\w*)\s*\[\s*\]")
ARRAY_DECL_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<type>[A-Za-z_]\w*)[ \t]+(?P<names>[A-Za-z_]\w*\s*\[\s*\](?:\s*,\s*[A-Za-z_]\w*\s*\[\s*\])*)\s*;",
    re.M)
INPUT_RE = re.compile(
    r"^(?P<kw>s?input)[ \t]+(?P<type>[A-Za-z_]\w*)[ \t]+(?P<name>[A-Za-z_]\w*)[ \t]*=", re.M)
ENUM_RE = re.compile(r"^enum[ \t]+(?P<name>[A-Za-z_]\w*)[ \t]*(?=\n?\{)", re.M)
STRUCT_RE = re.compile(r"^struct[ \t]+(?P<name>[A-Za-z_]\w*)[ \t]*(?=\n?\{)", re.M)


def depth_at(code, pos):
    return code.count("{", 0, pos) - code.count("}", 0, pos)


def parse_functions(src):
    """[(ret, name, params, start_offset)] for every top-level function definition."""
    code = strip_comments_and_strings(src)
    found = []
    for m in FUNC_RE.finditer(code):
        if depth_at(code, m.start()) != 0:
            continue
        if m.group("ret") in ("if", "for", "while", "switch", "else", "return", "struct", "enum", "class"):
            continue
        found.append((m.group("ret"), m.group("name"), src[m.start("params"):m.end("params")], m.start()))
    return found


def parse_inputs(src):
    code = strip_comments_and_strings(src)
    return [(m.group("type"), m.group("name")) for m in INPUT_RE.finditer(code)]


def parse_structs(src):
    code = strip_comments_and_strings(src)
    return [m.group("name") for m in STRUCT_RE.finditer(code) if depth_at(code, m.start()) == 0]


def parse_enums(src):
    code = strip_comments_and_strings(src)
    return [m.group("name") for m in ENUM_RE.finditer(code) if depth_at(code, m.start()) == 0]


def _wrap_string_literals(text):
    """"literal" -> string("literal") outside comments and preprocessor includes.

    In C++ `"text" + 5` is pointer arithmetic and compiles; in MQL5 it is an
    implicit number-to-string conversion (a warning). Typing every literal as a
    string makes the host compiler reject it, like every other string+number mix.
    """
    out = []
    i, n = 0, len(text)
    line_start = 0
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "\n":
            out.append(c)
            i += 1
            line_start = i
            continue
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(text[i:j])
            i = j
            continue
        if c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(text[i:j])
            i = j
            continue
        if c == "'":
            j = i + 1
            while j < n and text[j] != "'":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            literal = text[i:j + 1]
            head = text[line_start:i].lstrip()
            if head.startswith("#include") or head.startswith("#line"):
                out.append(literal)
            else:
                out.append("string(" + literal + ")")
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _rewrite_arrays(text):
    text = ARRAY_PARAM_RE.sub(
        lambda m: "%sMqlArray<%s> &%s" % (m.group("const") or "", m.group("type"), m.group("name")), text)

    def decl(m):
        names = [re.sub(r"\s*\[\s*\]", "", n).strip() for n in m.group("names").split(",")]
        return "%sMqlArray<%s> %s;" % (m.group("indent"), m.group("type"), ", ".join(names))
    return ARRAY_DECL_RE.sub(decl, text)


def _prototype(ret, name, params):
    cleaned = []
    for p in params.split(","):
        p = " ".join(p.split())
        if not p:
            continue
        p = re.sub(r"\s*=\s*[^,]+$", "", p)          # default arguments appear once, on the definition
        cleaned.append(p)
    return "%s %s(%s);" % (ret, name, ", ".join(cleaned))


def transpile(src, source_name="QuantumAutonomousTradingSystem.mq5"):
    """Mechanical MQL5 -> C++ rewrite. Line count and line numbers are preserved."""
    src = src.replace("\r\n", "\n")
    functions = parse_functions(src)
    inputs = parse_inputs(src)
    structs = parse_structs(src)
    enums = parse_enums(src)
    event_handlers = {"OnInit", "OnDeinit", "OnTick", "OnTradeTransaction", "OnTimer", "OnTester"}

    lines = src.split("\n")
    code_lines = strip_comments_and_strings(src).split("\n")
    first_func_line = None
    if functions:
        first_func_line = src.count("\n", 0, functions[0][3])

    out = []
    for idx, line in enumerate(lines):
        bare = code_lines[idx]
        if re.match(r"^\s*#property\b", bare) or re.match(r"^\s*#include\s*<Trade/Trade\.mqh>", line):
            out.append("// [qats_native] " + line)
            continue
        m = re.match(r"^(\s*)s?input(\s+)", bare)
        if m:
            line = line[:m.start(1)] + m.group(1) + line[m.end(2):]
        m = re.match(r"^enum[ \t]+([A-Za-z_]\w*)[ \t]*$", bare)
        if m:
            line = "enum %s : int" % m.group(1)
        out.append(line)
    text = "\n".join(out)
    text = _wrap_string_literals(text)
    text = _rewrite_arrays(text)

    if first_func_line is not None:
        block = ["// [qats_native] generated forward declarations (MQL5 needs none, C++ does)"]
        for e in enums:
            block.append("enum %s : int;" % e)
        for s in structs:
            block.append("struct %s;" % s)
        for ret, name, params, _ in functions:
            if name in event_handlers:
                continue
            block.append(_rewrite_arrays(_prototype(ret, name, params)))
        block.append('#line %d "%s"' % (first_func_line + 1, source_name))
        tl = text.split("\n")
        tl[first_func_line:first_func_line] = block
        text = "\n".join(tl)

    registry = ["", "// [qats_native] generated input registry: lets a test or a backtest set an input by name",
                "static bool QATS_SetInput(const std::string &qn, const std::string &qv)", "{"]
    for typ, name in inputs:
        if typ == "string":
            setter = "%s = qv;" % name
        elif typ == "bool":
            setter = '%s = (qv == "true" || qv == "1");' % name
        elif typ in ("double", "float"):
            setter = "%s = (%s)atof(qv.c_str());" % (name, typ)
        elif typ in SCALAR_TYPES:
            setter = "%s = (%s)atoll(qv.c_str());" % (name, typ)
        else:
            setter = "%s = (%s)atoi(qv.c_str());" % (name, typ)
        registry.append('   if(qn == "%s") { %s return true; }' % (name, setter))
    registry += ["   return false;", "}"]
    names = ", ".join('"%s"' % n for _, n in inputs)
    registry.append("static const char *QATS_INPUT_NAMES[] = {%s};" % names)
    registry.append("static const int QATS_INPUT_COUNT = %d;" % len(inputs))
    return ('#line 1 "%s"\n' % source_name) + text + "\n" + "\n".join(registry) + "\n"


def mql5_lint(src):
    """Problems C++ accepts but MQL5 rejects or warns about. Returns [str]."""
    problems = []
    code = strip_comments_and_strings(src)
    structs = set(parse_structs(src)) | {"MqlTradeRequest", "MqlTradeResult", "MqlTradeTransaction",
                                         "MqlDateTime", "MqlTick", "MqlRates", "CTrade"}
    inputs = [n for _, n in parse_inputs(src)]

    def line_of(pos):
        return code.count("\n", 0, pos) + 1

    # 1. "objects are passed by reference only"
    for ret, name, params, start in parse_functions(src):
        for p in params.split(","):
            p = " ".join(p.split())
            m = re.match(r"^(?:const\s+)?([A-Za-z_]\w*)\b(.*)$", p)
            if m and m.group(1) in structs and "&" not in m.group(2):
                problems.append("line %d: %s(): struct parameter '%s' must be passed by reference (&)"
                                % (line_of(start), name, p))
    # 2. an input is a constant
    for name in inputs:
        for m in re.finditer(r"\b%s\b\s*(?:[-+*/|&]?=(?!=)|\+\+|--)" % re.escape(name), code):
            ls = code.rfind("\n", 0, m.start()) + 1
            if re.match(r"\s*s?input\b", code[ls:m.start()]):
                continue
            problems.append("line %d: input '%s' is assigned (inputs are constants in MQL5)" % (line_of(m.start()), name))
    # 3. C++-only constructs
    for rx, why in ((r"\bauto\b", "`auto` is not MQL5"), (r"\bnullptr\b", "`nullptr` is not MQL5"),
                    (r"\bstd\s*::", "std:: is not MQL5"), (r"\btemplate\s*<\s*class", None),
                    (r"->", "`->` is not valid on MQL5 structs"), (r"\[\s*[&=]?\s*\]\s*\(", "lambda is not MQL5"),
                    (r"\bconstexpr\b", "`constexpr` is not MQL5"), (r"\busing\b", "`using` is not MQL5"),
                    (r"\bnamespace\b", "`namespace` is not used in this EA"),
                    (r"\bsize_t\b", "`size_t` is not MQL5"), (r"\bunsigned\b", "`unsigned` is not MQL5 (use uint/ulong)"),
                    (r"\blong\s+long\b", "`long long` is not MQL5"), (r"\bMqlArray\b", "shim type leaked into the source"),
                    (r"\bsim\s*::", "simulator symbol leaked into the source"),
                    (r"#\s*ifdef\s+__cplusplus", "host-only preprocessor branch in the EA")):
        if why is None:
            continue
        for m in re.finditer(rx, code):
            problems.append("line %d: %s" % (line_of(m.start()), why))
    # 4. free functions cannot be static; struct members cannot carry initialisers
    for m in re.finditer(r"^static\s+\w+\s+\w+\s*\(", code, re.M):
        if depth_at(code, m.start()) == 0:
            problems.append("line %d: a global function cannot be declared static" % line_of(m.start()))
    for m in STRUCT_RE.finditer(code):
        if depth_at(code, m.start()) != 0:
            continue
        open_brace = code.index("{", m.end())
        depth, i = 1, open_brace + 1
        while i < len(code) and depth:
            depth += (code[i] == "{") - (code[i] == "}")
            i += 1
        body = code[open_brace + 1:i - 1]
        if "(" in body:
            continue                      # has methods: not a plain data struct, skip the member rule
        for stmt in body.split(";"):
            if "=" in stmt:
                problems.append("line %d: struct %s: member initialiser '%s' is not valid MQL5"
                                % (line_of(open_brace + 1 + body.find(stmt)), m.group("name"), " ".join(stmt.split())))
    # 5. MQL5 has no reference variables and no local types: both are legal C++
    for m in re.finditer(r"(?m)^[ \t]*(?:const[ \t]+)?[A-Za-z_]\w*[ \t]*&[ \t]*[A-Za-z_]\w*[ \t]*(?:=(?!=)|;)", code):
        if depth_at(code, m.start()) > 0:
            problems.append("line %d: reference variable '%s' (MQL5 has references only as parameters)"
                            % (line_of(m.start()), " ".join(m.group(0).split())))
    for m in re.finditer(r"(?m)^[ \t]*(struct|enum|class)[ \t]+([A-Za-z_]\w*)", code):
        if depth_at(code, m.start()) > 0:
            problems.append("line %d: %s %s is declared inside a function (declare types at file scope)"
                            % (line_of(m.start()), m.group(1), m.group(2)))
    # 6. words MQL5 reserves and C++ does not: legal names for the host compiler,
    #    syntax errors for MetaEditor
    declared = r"\b(?:%s|[A-Z]\w*)[ \t]+&?[ \t]*(%s)\b[ \t]*(?:[=;,\[)]|$)" % (
        "|".join(SCALAR_TYPES), "|".join(MQL5_ONLY_RESERVED))
    for m in re.finditer(declared, code, re.M):
        problems.append("line %d: '%s' is a reserved word in MQL5 and cannot name a variable" % (line_of(m.start()), m.group(1)))
    return problems


# --------------------------------------------------------------------------
# "expression not boolean"
# --------------------------------------------------------------------------
def _match_bracket(code, open_pos):
    """Offset of the bracket closing the one at open_pos, or -1."""
    depth = 0
    for i in range(open_pos, len(code)):
        c = code[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _top_level(code, lo, hi, token):
    """Offsets inside [lo, hi) where `token` occurs outside every bracket."""
    found, depth, i = [], 0, lo
    while i < hi:
        c = code[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and code.startswith(token, i):
            found.append(i)
            i += len(token) - 1
        i += 1
    return found


def _bool_operands(code, lo, hi, out):
    """Collect the leaf operands of the boolean expression code[lo:hi] into `out`.

    The expression is taken apart in C precedence order: ?: first (all three of
    its operands are boolean when the whole is), then ||, then &&. The operand of
    a logical NOT must be boolean as well. MQL5's own reference writes
    `if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))`, but whether a particular
    MetaEditor build stays silent on that is not something this tool can know, so
    the EA casts explicitly - `!(bool)TerminalInfoInteger(...)`, the idiom
    QSMC_AutoTrader.mq5 already uses - and the audit holds it to that.
    """
    while lo < hi and code[lo].isspace():
        lo += 1
    while hi > lo and code[hi - 1].isspace():
        hi -= 1
    if lo >= hi:
        return
    if code[lo] == "(" and _match_bracket(code, lo) == hi - 1:
        _bool_operands(code, lo + 1, hi - 1, out)
        return
    question = _top_level(code, lo, hi, "?")
    if question:
        q = question[0]
        depth, nested, colon, i = 0, 0, -1, q + 1
        while i < hi:
            c = code[i]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif depth == 0 and c == "?":
                nested += 1
            elif depth == 0 and c == ":":
                if nested == 0:
                    colon = i
                    break
                nested -= 1
            i += 1
        if colon > 0:
            _bool_operands(code, lo, q, out)
            _bool_operands(code, q + 1, colon, out)
            _bool_operands(code, colon + 1, hi, out)
            return
    for op in ("||", "&&"):
        cuts = _top_level(code, lo, hi, op)
        if cuts:
            start = lo
            for pos in cuts:
                _bool_operands(code, start, pos, out)
                start = pos + 2
            _bool_operands(code, start, hi, out)
            return
    if code[lo] == "!" and not code.startswith("!=", lo):
        j = lo + 1
        while j < hi and code[j].isspace():
            j += 1
        if j < hi and code[j] == "(" and _match_bracket(code, j) == hi - 1:
            _bool_operands(code, j + 1, hi - 1, out)
        elif j < hi:
            out.add((j, hi))
        return
    out.add((lo, hi))


def bool_context_spans(src):
    """[(start, end)] of every leaf operand that MQL5 requires to be boolean."""
    code = strip_comments_and_strings(src)
    spans = set()
    for m in re.finditer(r"\b(?:if|while)\s*\(", code):
        close = _match_bracket(code, m.end() - 1)
        if close > 0:
            _bool_operands(code, m.end(), close, spans)
    for m in re.finditer(r"\bfor\s*\(", code):
        close = _match_bracket(code, m.end() - 1)
        if close < 0:
            continue
        semis = _top_level(code, m.end(), close, ";")
        if len(semis) == 2:
            _bool_operands(code, semis[0] + 1, semis[1], spans)
    # the condition of every ?: wherever it appears - walk left to where it starts
    for m in re.finditer(r"\?", code):
        q = m.start()
        depth, i, start = 0, q - 1, 0
        while i >= 0:
            c = code[i]
            if c in ")]}":
                depth += 1
            elif c in "([{":
                if depth == 0:
                    start = i + 1
                    break
                depth -= 1
            elif depth == 0:
                if c in ",;?:":
                    start = i + 1
                    break
                if c == "=" and code[i - 1] not in "=!<>" and code[i + 1] != "=":
                    start = i + 1               # an assignment, compound or plain
                    break
                if code.startswith("return", i) and not (code[i - 1].isalnum() or code[i - 1] == "_") \
                        and not (code[i + 6].isalnum() or code[i + 6] == "_"):
                    start = i + 6
                    break
            i -= 1
        _bool_operands(code, start, q, spans)
    return sorted(spans)


def wrap_bool_contexts(src):
    """The source with every boolean operand wrapped in QATS_BOOL( ... ).

    QATS_BOOL (tools/qats_sim/mql5_shim.h) is the identity for a `bool` and a
    compile error for anything else. No line is added or removed, so the
    diagnostics still point at the .mq5 line.
    """
    edits = []
    for lo, hi in bool_context_spans(src):
        edits.append((lo, 1, "QATS_BOOL("))
        edits.append((hi, 0, ")"))
    out = src
    # right to left; at one offset a closing bracket goes in before an opening one
    for pos, _, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:pos] + text + out[pos:]
    return out


def bool_audit(source_path=EA_SOURCE, tag="boolaudit", out_dir=OUT_DIR):
    """Type-check every boolean context. Returns (operand_count, returncode, diagnostics)."""
    if not find_compiler():
        return 0, SKIP_EXIT, "no usable C++17 compiler (g++, c++, clang++) on this host"
    with open(source_path, "r", encoding="utf-8") as fh:
        src = fh.read().replace("\r\n", "\n")
    spans = bool_context_spans(src)
    os.makedirs(out_dir, exist_ok=True)
    audited = os.path.join(out_dir, "boolaudit_" + os.path.basename(source_path))
    with open(audited, "w", encoding="utf-8") as fh:
        fh.write(wrap_bool_contexts(src))
    _, rc, diag = build(audited, tag, strict=False, out_dir=out_dir, syntax_only=True)
    return len(spans), rc, diag


def write_translation_unit(source_path, out_dir, tag, extra_defines=()):
    os.makedirs(out_dir, exist_ok=True)
    with open(source_path, "r", encoding="utf-8") as fh:
        src = fh.read()
    ea_inc = os.path.join(out_dir, "ea_%s.inc" % tag)
    with open(ea_inc, "w", encoding="utf-8") as fh:
        fh.write(transpile(src, os.path.basename(source_path)))
    main_cpp = os.path.join(out_dir, "main_%s.cpp" % tag)
    dual = "QATS_ScoreSide" in src
    with open(main_cpp, "w", encoding="utf-8") as fh:
        fh.write('#include "%s"\n' % SHIM.replace("\\", "/"))
        for d in extra_defines:
            fh.write("#define %s\n" % d)
        if dual:
            fh.write("#define QATS_HAS_DUAL 1\n")
        fh.write('#include "%s"\n' % ea_inc.replace("\\", "/"))
        fh.write('#include "%s"\n' % DRIVER.replace("\\", "/"))
    return main_cpp, ea_inc


def build(source_path=EA_SOURCE, tag="ea", optimize="-O2", strict=True, sanitize=False,
          out_dir=OUT_DIR, extra_flags=(), extra_defines=(), syntax_only=False):
    """Compile the EA + shim + driver. Returns (exe_path or None, returncode, diagnostics).

    syntax_only=True runs the front end only (fast): every type error and every
    warning class except the flow-sensitive -Wmaybe-uninitialized is still reported.
    """
    cxx = find_compiler()
    if not cxx:
        return None, SKIP_EXIT, "no usable C++17 compiler (g++, c++, clang++) on this host"
    main_cpp, _ = write_translation_unit(source_path, out_dir, tag, extra_defines)
    exe = os.path.join(out_dir, "qats_%s" % tag)
    cmd = [cxx, "-std=c++17"]
    cmd += ["-fsyntax-only"] if syntax_only else [optimize, "-g1"]
    if strict:
        cmd += STRICT_FLAGS
    else:
        cmd += ["-w"]
    if sanitize and not syntax_only:
        # float-divide-by-zero is not part of `undefined` (IEEE defines it), but in
        # MQL5 "zero divide" is a critical error that stops the EA - so it is checked.
        cmd += ["-fsanitize=address,undefined,float-divide-by-zero", "-fno-omit-frame-pointer"]
    cmd += list(extra_flags) + [main_cpp]
    if not syntax_only:
        cmd += ["-o", exe]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    ok = proc.returncode == 0
    return (exe if ok and not syntax_only else None), proc.returncode, proc.stdout


def supports_flags(flags):
    """True when the host compiler can build AND link a trivial program with `flags`."""
    cxx = find_compiler()
    if not cxx:
        return False
    os.makedirs(OUT_DIR, exist_ok=True)
    src = os.path.join(OUT_DIR, "probe.cpp")
    exe = os.path.join(OUT_DIR, "probe")
    with open(src, "w") as fh:
        fh.write("int main(){return 0;}\n")
    try:
        proc = subprocess.run([cxx, "-std=c++17"] + list(flags) + [src, "-o", exe],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Build the QATS EA natively against the MQL5 shim.")
    ap.add_argument("--source", default=EA_SOURCE)
    ap.add_argument("--tag", default="ea")
    ap.add_argument("--no-strict", action="store_true")
    ap.add_argument("--sanitize", action="store_true")
    ap.add_argument("-O", dest="opt", default="-O2")
    ap.add_argument("--emit-only", action="store_true", help="write the translation unit, do not compile")
    args = ap.parse_args(argv)
    if args.emit_only:
        main_cpp, ea_inc = write_translation_unit(args.source, OUT_DIR, args.tag)
        print(main_cpp)
        print(ea_inc)
        return 0
    with open(args.source, "r", encoding="utf-8") as fh:
        lint = mql5_lint(fh.read())
    for p in lint:
        print("LINT  " + p)
    exe, rc, diag = build(args.source, args.tag, args.opt, not args.no_strict, args.sanitize)
    if rc == SKIP_EXIT:
        print("SKIP  qats-native: " + diag)
        return SKIP_EXIT
    if diag.strip():
        print(diag.rstrip())
    if rc != 0 or lint:
        print("qats-native: FAILED (host build rc=%d, lint problems=%d)" % (rc, len(lint)))
        return 1
    print("qats-native: host build OK -> %s" % exe)
    print("This is NOT MetaEditor. F7 remains the compile gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
