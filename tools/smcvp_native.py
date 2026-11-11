#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMCVP-NATIVE - build the REAL QSMC include modules (and the indicator that
hosts them) with a host C++17 compiler against the typed MQL5 shim, so their
logic can be EXECUTED offline: unit checks, a chart-object simulator and a
historical replay.

It reuses tools/qats_native.py (the mechanical MQL5 -> C++ rewrite, the strict
warning set, the MQL5 lint and the boolean-context audit) and adds the one thing
a multi-file program needs: `#include <QSMC/X.mqh>` is resolved against
MQL5/Include and inlined once, with `#line` directives, so every diagnostic
still names the ORIGINAL file and line.

  flatten(host)     the host source with its QSMC includes inlined
  build(...)        host + driver -> executable (strict: warnings are errors)
  lint(paths)       qats_native.mql5_lint over each real source file
  bool_audit(host)  "expression not boolean" checked by the host type system

NOT MetaEditor. A clean host build is evidence, never proof, of a clean F7.
Exit code convention (tools/native_toolchain.py): 0 verified, 77 no usable
compiler on this host, anything else = verified and failed.
"""
from __future__ import print_function

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qats_native as QN  # noqa: E402

ROOT = QN.ROOT
INCLUDE_ROOT = os.path.join(ROOT, "MQL5", "Include")
SIM_DIR = QN.SIM_DIR
SHIM = QN.SHIM
CHART_SHIM = os.path.join(SIM_DIR, "mql5_chart.h")
OUT_DIR = os.path.join(ROOT, "out", "smcvp_native")
SKIP_EXIT = QN.SKIP_EXIT

INCLUDE_RE = re.compile(r'^[ \t]*#include[ \t]*<(QSMC/[A-Za-z0-9_]+\.mqh)>[ \t]*(?://.*)?$')
GROUP_RE = re.compile(r'^([ \t]*)s?input[ \t]+group\b')
FLAT_NAME = "__flat__"


def read_source(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def flatten(host_path):
    """[(text, file_label, line_no)] for the host with its QSMC includes inlined once."""
    seen = set()
    out = []

    def walk(path, label):
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        for no, line in enumerate(read_source(path).split("\n"), 1):
            m = INCLUDE_RE.match(line)
            if m:
                target = os.path.join(INCLUDE_ROOT, *m.group(1).split("/"))
                if not os.path.isfile(target):
                    raise IOError("%s:%d includes a file that does not exist: %s" % (label, no, m.group(1)))
                out.append(("// [smcvp_native] " + line.strip(), label, no))
                walk(target, os.path.basename(target))
                continue
            if GROUP_RE.match(line):
                line = "// [smcvp_native] " + line.strip()
            out.append((line, label, no))

    walk(host_path, os.path.basename(host_path))
    return out


def sources_of(host_path):
    """The real files a host is built from (host first, then each include once)."""
    files, seen = [], set()

    def walk(path):
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        files.append(path)
        for line in read_source(path).split("\n"):
            m = INCLUDE_RE.match(line)
            if m:
                walk(os.path.join(INCLUDE_ROOT, *m.group(1).split("/")))

    walk(host_path)
    return files


def flat_text(host_path):
    """One text with #line markers wherever the origin changes."""
    rows = flatten(host_path)
    lines, origin = [], []
    prev = (None, 0)
    for text, label, no in rows:
        if label != prev[0] or no != prev[1] + 1:
            lines.append('#line %d "%s"' % (no, label))
            origin.append((label, no))
        lines.append(text)
        origin.append((label, no))
        prev = (label, no)
    return "\n".join(lines) + "\n", origin


def transpile(host_path):
    text, origin = flat_text(host_path)
    cpp = QN.transpile(text, FLAT_NAME)
    # qats_native resumes after its forward-declaration block with a #line that
    # names the flat text; point it back at the real file and line instead.
    def fix(m):
        flat_no = int(m.group(1))
        if 1 <= flat_no <= len(origin):
            label, no = origin[flat_no - 1]
            return '#line %d "%s"' % (no, label)
        return m.group(0)
    cpp = re.sub(r'^#line (\d+) "%s"$' % re.escape(FLAT_NAME), fix, cpp, flags=re.M)
    # a driver need not use the generated input registry: that is not a defect of the source
    cpp = cpp.replace("static const char *QATS_INPUT_NAMES[]", "[[maybe_unused]] static const char *QATS_INPUT_NAMES[]")
    cpp = cpp.replace("static const int QATS_INPUT_COUNT", "[[maybe_unused]] static const int QATS_INPUT_COUNT")
    return cpp


def extract(path, start_marker, end_marker, prelude_re=None):
    """A verbatim slice of a real source file: from `start_marker` up to (not
    including) the first `end_marker` after it, optionally preceded by the lines
    matching `prelude_re` (e.g. the #define the slice needs)."""
    src = read_source(path)
    a = src.index(start_marker)
    b = src.index(end_marker, a + len(start_marker))
    head = ""
    if prelude_re:
        head = "\n".join(m.group(0) for m in re.finditer(prelude_re, src, re.M)) + "\n"
    return head + src[a:b]


def legacy_volume_profile():
    """(label, text) of CVolumeProfile exactly as shipped in QSMC_Stats.mqh - the
    profile the existing indicator displays - for the parity check."""
    path = os.path.join(INCLUDE_ROOT, "QSMC", "QSMC_Stats.mqh")
    text = extract(path, "struct SVolumeProfileResult",
                   "//--------------------------------------------------------------------",
                   r"^#define QSMC_VP_MAX_BINS.*$")
    if "class CVolumeProfile" not in text:
        raise ValueError("CVolumeProfile was not found in QSMC_Stats.mqh")
    return ("QSMC_Stats.mqh", text)


def write_unit(host_path, driver_path, tag, defines=(), out_dir=OUT_DIR, text_filter=None, extra_units=()):
    os.makedirs(out_dir, exist_ok=True)
    inc = os.path.join(out_dir, "unit_%s.inc" % tag)
    cpp = transpile(host_path)
    if text_filter:
        cpp = text_filter(cpp)
    with open(inc, "w", encoding="utf-8") as fh:
        fh.write(cpp)
    extras = []
    for k, (label, text) in enumerate(extra_units):
        path = os.path.join(out_dir, "extra_%s_%d.inc" % (tag, k))
        extra_cpp = QN.transpile(text, label)
        # a slice declares no inputs: drop the (empty) generated registry so it
        # cannot collide with the host's
        cut = extra_cpp.find("// [qats_native] generated input registry")
        if cut >= 0:
            extra_cpp = extra_cpp[:cut]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(extra_cpp)
        extras.append(path)
    main_cpp = os.path.join(out_dir, "main_%s.cpp" % tag)
    with open(main_cpp, "w", encoding="utf-8") as fh:
        # defines go FIRST: some of them (QATS_POISON_ARRAYS) are read by the
        # shim itself, the rest by the driver
        for d in defines:
            fh.write("#define %s\n" % d)
        fh.write('#include "%s"\n' % SHIM.replace("\\", "/"))
        fh.write('#include "%s"\n' % CHART_SHIM.replace("\\", "/"))
        fh.write('#include "%s"\n' % inc.replace("\\", "/"))
        for path in extras:
            fh.write('#include "%s"\n' % path.replace("\\", "/"))
        if driver_path:
            fh.write('#include "%s"\n' % os.path.abspath(driver_path).replace("\\", "/"))
    return main_cpp, inc


def build(host_path, driver_path, tag, strict=True, sanitize=False, syntax_only=False,
          defines=(), optimize="-O2", out_dir=OUT_DIR, extra_flags=(), text_filter=None, extra_units=()):
    """Returns (exe or None, returncode, diagnostics)."""
    cxx = QN.find_compiler()
    if not cxx:
        return None, SKIP_EXIT, "no usable C++17 compiler (g++, c++, clang++) on this host"
    main_cpp, _ = write_unit(host_path, driver_path, tag, defines, out_dir, text_filter, extra_units)
    exe = os.path.join(out_dir, "smcvp_%s" % tag)
    cmd = [cxx, "-std=c++17"]
    cmd += ["-fsyntax-only"] if syntax_only else [optimize, "-g1"]
    cmd += QN.STRICT_FLAGS if strict else ["-w"]
    if sanitize and not syntax_only:
        cmd += ["-fsanitize=address,undefined,float-divide-by-zero", "-fno-omit-frame-pointer"]
    cmd += list(extra_flags) + [main_cpp]
    if not syntax_only:
        cmd += ["-o", exe]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    ok = proc.returncode == 0
    return (exe if ok and not syntax_only else None), proc.returncode, proc.stdout


def lint(paths):
    """qats_native's MQL5 lint over each real file. Returns ['file: problem']."""
    problems = []
    for path in paths:
        src = read_source(path)
        src = "\n".join("// " + l if GROUP_RE.match(l) else l for l in src.split("\n"))
        for p in QN.mql5_lint(src):
            problems.append("%s: %s" % (os.path.basename(path), p))
    return problems


# MQL5 sizes: a string is a 12-byte handle, a dynamic array a 52-byte header.
_MQL5_SIZES = {"int": 4, "uint": 4, "double": 8, "long": 8, "ulong": 8, "datetime": 8, "bool": 1, "string": 12,
               "color": 4, "uchar": 1, "char": 1, "short": 2, "ushort": 2, "float": 4}


def stack_estimate(host_path):
    """Estimate the stack the program needs, from its declarations.

    MetaTrader gives an INDICATOR a fixed 1 MB stack (`#property stacksize` is
    ignored for indicators), and overflowing it is a critical error that stops
    the program. A host build has 8 MB and would not notice. This walks every
    function of the flattened source, adds up the local variables it declares
    (structs and fixed arrays by their MQL5 size), and follows the call graph.

    Returns {"functions", "largest": (bytes, name), "deepest": {handler: (bytes, [chain])}, "recursive": [[cycle]]}.
    It is an estimate: parameters, temporaries and return slots are not counted.
    """
    code = "\n".join(QN.strip_comments_and_strings(read_source(p)) for p in sources_of(host_path))
    defines = {m.group(1): int(m.group(2))
               for m in re.finditer(r"^[ \t]*#define[ \t]+([A-Za-z_]\w*)[ \t]+\(?(-?\d+)\)?[ \t]*$", code, re.M)}
    enums = set(re.findall(r"\benum[ \t]+([A-Za-z_]\w*)", code))

    def block(open_end):
        i, depth = open_end, 1
        while depth and i < len(code):
            depth += (code[i] == "{") - (code[i] == "}")
            i += 1
        return code[open_end:i - 1]

    structs = {m.group(1): block(m.end()) for m in re.finditer(r"\bstruct[ \t]+([A-Za-z_]\w*)\s*\{", code)}
    sizes = {}

    def count(dims):
        """(elements, dynamic?) of the [..][..] suffix of a declarator."""
        n, dynamic = 1, False
        for d in re.findall(r"\[([^\]]*)\]", dims):
            try:
                n *= int(eval(d, {"__builtins__": {}}, defines))   # sizes are #define arithmetic
            except Exception:
                dynamic = True
        return n, dynamic

    def known(t):
        return t in _MQL5_SIZES or t in structs or t in enums or t.startswith("ENUM_") or t.startswith("Mql")

    def size_of(t):
        if t in _MQL5_SIZES:
            return _MQL5_SIZES[t]
        if t in sizes:
            return sizes[t]
        if t not in structs:
            return 4 if (t in enums or t.startswith("ENUM_")) else 64      # a terminal struct: generous
        sizes[t] = 0                                                       # guards a self-reference
        sizes[t] = declared(structs[t])
        return sizes[t]

    def declared(body):
        total = 0
        for m in re.finditer(r"(?m)^[ \t]*(static[ \t]+)?(?:const[ \t]+)?([A-Za-z_]\w*)[ \t]+([^;()=]*?(?:=[^;]*)?);", body):
            if m.group(1) or not known(m.group(2)):
                continue                                                   # a static local is not on the stack
            for decl in re.split(r",(?![^\[]*\])(?![^(]*\))", m.group(3)):
                d = re.match(r"^\s*([A-Za-z_]\w*)((?:\[[^\]]*\])*)", decl)
                if d:
                    n, dynamic = count(d.group(2))
                    total += 52 if dynamic else n * size_of(m.group(2))
        return total

    frames, calls = {}, {}
    for _ret, name, _params, start in QN.parse_functions(code):
        body = block(code.index("{", start) + 1)
        frames[name] = declared(body)
        calls[name] = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", body))
    for name in calls:
        calls[name] = set(c for c in calls[name] if c in frames)
    recursive, memo, path = [], {}, []

    def deepest(name):
        if name in memo:
            return memo[name]
        if name in path:
            recursive.append(path[path.index(name):] + [name])
            return 0, []
        path.append(name)
        best = (0, [])
        for callee in sorted(calls[name]):
            d = deepest(callee)
            if d[0] > best[0]:
                best = d
        path.pop()
        memo[name] = (frames[name] + best[0], [name] + best[1])
        return memo[name]

    for name in sorted(frames):                 # every function, so recursion is found wherever it is
        deepest(name)
    handlers = [h for h in ("OnInit", "OnCalculate", "OnTimer", "OnChartEvent", "OnDeinit") if h in frames]
    return {"functions": len(frames),
            "largest": max(((v, k) for k, v in frames.items()), default=(0, "")),
            "deepest": {h: deepest(h) for h in handlers},
            "recursive": recursive}


def bool_audit(host_path, tag="boolaudit", out_dir=OUT_DIR):
    """Every operand of every if / while / for / ?: / && / || must be a real bool.

    Returns (operand_count, returncode, diagnostics)."""
    if not QN.find_compiler():
        return 0, SKIP_EXIT, "no usable C++17 compiler (g++, c++, clang++) on this host"
    total = 0
    for path in sources_of(host_path):
        total += len(QN.bool_context_spans(read_source(path)))

    def wrap(cpp):
        return cpp

    # wrap each real file's text before flattening, so the spans line up with it
    originals = {}
    try:
        os.makedirs(out_dir, exist_ok=True)
        stage = os.path.join(out_dir, "boolaudit_src")
        inc_dir = os.path.join(stage, "MQL5", "Include", "QSMC")
        os.makedirs(inc_dir, exist_ok=True)
        staged_host = None
        for path in sources_of(host_path):
            wrapped = QN.wrap_bool_contexts(read_source(path))
            if os.path.abspath(path) == os.path.abspath(host_path):
                staged_host = os.path.join(stage, os.path.basename(path))
                target = staged_host
            else:
                target = os.path.join(inc_dir, os.path.basename(path))
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(wrapped)
            originals[target] = path
        global INCLUDE_ROOT
        saved = INCLUDE_ROOT
        INCLUDE_ROOT = os.path.join(stage, "MQL5", "Include")
        try:
            _, rc, diag = build(staged_host, None, tag, strict=False, syntax_only=True, out_dir=out_dir,
                                text_filter=wrap)
        finally:
            INCLUDE_ROOT = saved
    except (IOError, OSError) as exc:
        return total, 1, str(exc)
    return total, rc, diag


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Host-build a QSMC module host against the MQL5 shim.")
    ap.add_argument("host")
    ap.add_argument("--driver", default=None)
    ap.add_argument("--tag", default="host")
    ap.add_argument("--sanitize", action="store_true")
    ap.add_argument("--syntax-only", action="store_true")
    args = ap.parse_args(argv)
    problems = lint(sources_of(args.host))
    for p in problems:
        print("LINT  " + p)
    exe, rc, diag = build(args.host, args.driver, args.tag, sanitize=args.sanitize,
                          syntax_only=args.syntax_only or not args.driver)
    if rc == SKIP_EXIT:
        print("SKIP  smcvp-native: " + diag)
        return SKIP_EXIT
    if diag.strip():
        print(diag.rstrip())
    if rc != 0 or problems:
        print("smcvp-native: FAILED (host build rc=%d, lint problems=%d)" % (rc, len(problems)))
        return 1
    print("smcvp-native: host build OK%s" % (" -> " + exe if exe else " (syntax only)"))
    print("This is NOT MetaEditor. F7 remains the compile gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
