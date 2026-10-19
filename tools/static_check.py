#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static consistency check for the QSMC v6.6.4 arbitration subsystem.

This is NOT a compiler. It cannot replace F7 in MetaEditor. What it does
is catch the classes of mistake a human reviewer makes when writing a
large amount of MQL5 by hand:

  1. brace / parenthesis balance per file
  2. every identifier used in the .mqh files is declared somewhere
  3. every #include resolves to a file that exists
  4. interface methods are implemented by the classes that claim to
  5. struct members referenced with '.' exist on that struct
  6. no MQL5-forbidden constructs (std::, lambda, throw, try, template,
     multiple inheritance, operator overloading, dynamic_cast)
  7. every `new` has a matching `delete` in the same class

Usage:  python3 tools/static_check.py
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INC  = os.path.join(ROOT, "MQL5", "Include", "QSMC")
FILES = sorted(f for f in os.listdir(INC) if f.endswith(".mqh"))

# --- PART C sources outside the include folder (companion EA, scripts, and the
# Phase 7 scanner host added in v6.6.3). These used to be listed and then never
# read, which is the same mistake this whole release is about: a source no check
# touches is a source no check protects.
EXTRA = [
    os.path.join(ROOT, "MQL5", "Scripts", "QSMC_ArbiterTest.mq5"),
    os.path.join(ROOT, "MQL5", "Experts", "KLJ_DataFeeder.mq5"),
    os.path.join(ROOT, "MQL5", "Indicators", "QSMC_ScannerProbe.mq5"),
]
EXTRA = [e for e in EXTRA if os.path.exists(e)]

# ---------------------------------------------------------------- keywords
KEYWORDS = set("""
if else for while do return break continue switch case default
class struct enum interface public private protected virtual const
void bool int uint long ulong short char uchar double float datetime
color string new delete this true false NULL true false
input static extern template typename operator throw try catch
#define #include #ifndef #endif #property
""".split())

# ---------------------------------------------------------------- helpers
def read(p):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def strip_code(src):
    """Remove comments and string literals so we only see real code."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i+1 < n and src[i+1] == '/':
            while i < n and src[i] != '\n': i += 1
        elif c == '/' and i+1 < n and src[i+1] == '*':
            i += 2
            while i+1 < n and not (src[i] == '*' and src[i+1] == '/'): i += 1
            i += 2
        elif c == '"':
            i += 1
            while i < n and src[i] != '"':
                if src[i] == '\\': i += 1
                i += 1
            i += 1
            out.append('""')
        elif c == "'":
            i += 1
            while i < n and src[i] != "'":
                if src[i] == '\\': i += 1
                i += 1
            i += 1
            out.append("''")
        else:
            out.append(c); i += 1
    return "".join(out)

def balance(src, label, errs):
    code = strip_code(src)
    for open_c, close_c, name in (("{","}","braces"), ("(",")","parens"), ("[","]","brackets")):
        d, i, n = 0, 0, len(code)
        while i < n:
            if code[i] == open_c: d += 1
            elif code[i] == close_c:
                d -= 1
                if d < 0:
                    line = code[:i].count("\n")+1
                    errs.append("%s: unbalanced %s (extra '%s' near line %d)"
                                % (label, name, close_c, line)); break
            i += 1
        if d > 0:
            errs.append("%s: unbalanced %s (%d unclosed '%s')" % (label, name, d, open_c))

# ---------------------------------------------------------------- main
def main():
    errs, warns = [], []
    texts = {}
    for f in FILES:
        p = os.path.join(INC, f)
        texts[f] = read(p)

    for e in EXTRA:                      # companion sources join the same checks
        texts[os.path.relpath(e, ROOT)] = read(e)
    all_src = "\n".join(texts.values())
    host = read(os.path.join(ROOT, "nadir2.mq5"))

    # 1) balance -------------------------------------------------------
    for f in FILES:
        balance(texts[f], f, errs)

    # 2) MQL5-forbidden constructs ------------------------------------
    forbidden = [
        (r"\bstd::",                "std:: (no STL in MQL5)"),
        (r"\[\s*&\s*\]\s*\(",       "C++ lambda"),
        (r"\bthrow\b",              "throw (no exceptions in MQL5)"),
        (r"\btry\s*\{",             "try (no exceptions in MQL5)"),
        (r"\bcatch\s*\(",           "catch (no exceptions in MQL5)"),
        (r"\btemplate\s*<",         "template (MQL5 supports templates only for simple cases; none used here)"),
        (r"\bdynamic_cast\b",       "dynamic_cast (no RTTI in MQL5)"),
        (r"\boperator\s*[+\-*/=<>!\[]", "operator overloading"),
        (r"\bclass\s+\w+\s*:\s*[\w_]+\s*,\s*", "multiple inheritance"),
    ]
    for f, t in texts.items():
        code = strip_code(t)
        for rx, why in forbidden:
            for m in re.finditer(rx, code):
                line = code[:m.start()].count("\n")+1
                errs.append("%s:%d  forbidden construct: %s" % (f, line, why))

    # 3) includes resolve ---------------------------------------------
    for f, t in texts.items():
        for m in re.finditer(r'#include\s*<([^>]+)>', t):
            rel = m.group(1).replace("\\", "/")
            p = os.path.join(INC, rel)
            if not os.path.isfile(p):
                p2 = os.path.join(ROOT, "MQL5", "Include", rel)
                if not os.path.isfile(p2):
                    errs.append("%s: #include <%s> does not resolve" % (f, rel))
    # the indicator includes <QSMC/QSMC_Root.mqh>
    if '#include <QSMC/QSMC_Root.mqh>' in host:
        if not os.path.isfile(os.path.join(INC, "QSMC_Root.mqh")):
            errs.append("nadir2.mq5: #include <QSMC/QSMC_Root.mqh> does not resolve")

    # 4) interface implementations ------------------------------------
    # collect interfaces and their method names
    ifaces = {}
    for f, t in texts.items():
        for m in re.finditer(r'interface\s+(\w+)\s*\{', t):
            name = m.group(1)
            # naive brace match
            i = m.end()-1; d = 0
            while i < len(t):
                if t[i] == '{': d += 1
                elif t[i] == '}':
                    d -= 1
                    if d == 0: break
                i += 1
            body = t[m.end():i]
            ifaces[name] = set(re.findall(r'virtual\s+\w+\s+(\w+)\s*\(', body))

    for iname, meths in ifaces.items():
        impls = re.findall(r'class\s+(\w+)\s*:\s*public\s+' + iname + r'\b', all_src)
        if not impls:
            errs.append("interface %s is never implemented" % iname)
        for cls in impls:
            for meth in meths:
                if not re.search(r'virtual\s+\w+\s+' + meth + r'\s*\(', all_src):
                    errs.append("%s does not implement %s::%s" % (cls, iname, meth))

    # 5) struct/class member access, with real type inference ---------
    # Build struct -> members (as before).
    structs = {}
    for f, t in texts.items():
        for m in re.finditer(r'struct\s+(\w+)\s*\{', t):
            name = m.group(1)
            i = m.end()-1; d = 0
            while i < len(t):
                if t[i] == '{': d += 1
                elif t[i] == '}':
                    d -= 1
                    if d == 0: break
                i += 1
            body = strip_code(t[m.end():i])
            members = set()
            for line in body.split("\n"):
                line0 = re.sub(r'//.*$', '', line).strip().rstrip(";")
                line0 = re.sub(r'\[[^\]]*\]', '', line0)   # drop array sizes
                parts = re.split(r'[\s,]+', line0.strip())
                if len(parts) >= 2 and re.match(r'^[A-Za-z_]\w*$', parts[-1]):
                    members.add(parts[-1])
            structs[name] = members

    # Methods of every class we own (so c.Foo() on a class object is ok).
    class_methods = {}
    for f, t in texts.items():
        code = strip_code(t)
        for m in re.finditer(r'class\s+(\w+)', code):
            name = m.group(1)
            i = m.end(); d = 1; j = i
            while j < len(code) and d > 0:
                if code[j] == '{': d += 1
                elif code[j] == '}': d -= 1
                j += 1
            body = code[i:j]
            meths = set(re.findall(r'\b(\w+)\s*\([^;{]*\)\s*(?:const\s*)?\{', body))
            meths |= set(re.findall(r'virtual\s+[\w\s\*&:<>]*?\b(\w+)\s*\(', body))
            meths |= set(re.findall(r'^\s*[\w\s\*&:<>]*?\b(\w+)\s*\([^;]*\)\s*const?\s*;', body, re.M))
            class_methods[name] = meths
    for iname, meths in ifaces.items():
        class_methods.setdefault(iname, set()).update(meths)

    def type_of_decl(decl):
        decl = decl.strip()
        decl = re.sub(r'\b(const|static|virtual|public|private|protected)\b', '', decl)
        decl = decl.replace('*', ' ').replace('&', ' ').strip()
        return decl.split()[0] if decl else None

    for f, t in texts.items():
        code = strip_code(t)
        # Variable -> type, resolved by LINE. The same name is routinely
        # declared with different types in different functions of one file
        # (e.g. `SSeasonRow r` and `SVolatilityRow r`), so the nearest
        # declaration at or before the use line is the right one.
        def line_of(pos):
            return code[:pos].count("\n") + 1

        decls = []   # (line, var, type)
        for m in re.finditer(r'(?:^|[;{}\n])\s*((?:const\s+)?[A-Za-z_]\w*(?:\s*<[^>]*>)?)\s+(\w+)\s*(?:\[\s*\]|=[^;]*)?;', code):
            decls.append((line_of(m.start()), m.group(2), type_of_decl(m.group(1))))
        for m in re.finditer(r'(?:^|[;{}\n])\s*((?:const\s+)?[A-Za-z_]\w*)\s*\*\s*(\w+)\s*(?:=|;|\))', code):
            decls.append((line_of(m.start()), m.group(2), type_of_decl(m.group(1))))
        # function parameters  (Type &name, const Type &name, Type *name)
        for m in re.finditer(r'\(\s*([^)]*)\)\s*(?:const\s*)?\{', code):
            pline = line_of(m.start())
            for param in m.group(1).split(','):
                pm = re.search(r'([A-Za-z_]\w*)\s*[&*]?\s*(\w+)\s*$', param.strip())
                if pm:
                    ty, var = pm.group(1), pm.group(2)
                    if ty in structs or ty in class_methods:
                        decls.append((pline, var, ty))
        decls.sort(key=lambda d: d[0])

        def resolve(var, use_line):
            best = None
            for dline, dvar, dty in decls:
                if dvar == var and dline <= use_line:
                    best = dty
                elif dvar == var and dline > use_line:
                    break
            if best is None:      # fall back: declared later in the file
                for dline, dvar, dty in decls:
                    if dvar == var:
                        best = dty
            return best

        for m in re.finditer(r'\b(\w+)\.(\w+)', code):
            var, mem = m.group(1), m.group(2)
            ty = resolve(var, line_of(m.start()))
            if ty is None: continue
            if ty in structs:
                if mem not in structs[ty]:
                    line = code[:m.start()].count("\n")+1
                    errs.append("%s:%d  unknown member %s.%s (struct %s has: %s)"
                                % (f, line, var, mem, ty,
                                   ", ".join(sorted(structs[ty])[:14])))
            elif ty in class_methods:
                if mem not in class_methods[ty]:
                    line = code[:m.start()].count("\n")+1
                    errs.append("%s:%d  unknown member %s.%s (class %s)"
                                % (f, line, var, mem, ty))

    # 6) new/delete balance per class ---------------------------------
    for f, t in texts.items():
        code = strip_code(t)
        n_new = len(re.findall(r'\bnew\s+[A-Za-z_]\w*', code))
        n_del = len(re.findall(r'\bdelete\s+\w+', code))
        if n_new and not n_del:
            errs.append("%s: %d 'new' and no 'delete' in this file" % (f, n_new))
        elif n_new:
            # every allocation site must be matched by a delete inside a
            # destructor, Shutdown(), Clear() or an explicit counter - and for a
            # program file (EA / indicator / script) the release site is
            # OnDeinit(), which is exactly what QSMC_ScannerProbe.mq5 does.
            if not re.search(r'~\w+\s*\(', code) \
               and not re.search(r'void\s+Shutdown\s*\(', code) \
               and not re.search(r'void\s+OnDeinit\s*\(', code):
                errs.append("%s: 'new' present but no destructor/Shutdown()" % f)
            else:
                warns.append("%s: %d new site(s), %d delete site(s); "
                             "balance is verified at runtime by AllocCalls()/FreeCalls()"
                             % (f, n_new, n_del))

    # 7) identifiers used in the .mqh files but never declared --------
    declared = set()
    for src in list(texts.values()) + [host]:
        code = strip_code(src)
        declared |= set(re.findall(r'\b(?:class|struct|enum|interface)\s+(\w+)', code))
        declared |= set(re.findall(r'^[\w \t\*&:]*?\b(\w+)\s*\([^;]*\)\s*(?:const\s*)?\{', code, re.M))
        declared |= set(re.findall(r'\b(\w+)\s*\(', code))
    # MQL5 builtins we rely on
    builtin = set("""
Print Alert PlaySound SendNotification Comment StringFormat IntegerToString
DoubleToString TimeToString TimeToStruct TimeCurrent MathAbs MathMax MathMin
MathRound MathIsValidNumber MathFloor MathCeil ArrayResize ArraySize
ArraySetAsSeries ArrayInitialize ArrayCopy ObjectCreate ObjectDelete
ObjectFind ObjectMove ObjectSetInteger ObjectSetDouble ObjectSetString
ObjectName ObjectsTotal ObjectsDeleteAll ObjectGetInteger ObjectGetDouble
SymbolInfoDouble SymbolInfoInteger PeriodSeconds iHigh iLow iOpen iClose
iTime CopyRates CopyBuffer GlobalVariableCheck GlobalVariableGet
GlobalVariableSet GlobalVariableDel GlobalVariableName GlobalVariablesTotal
FileOpen FileWrite FileClose FileFlush GetLastError GetMicrosecondCount
GetTickCount IndicatorRelease StringLen StringSubstr StringFind
StringGetCharacter StringCompare StringToUpper EnumToString _Symbol _Period
_Point _Digits DBL_MAX DBL_EPSILON EMPTY_VALUE INVALID_HANDLE CheckPointer
POINTER_DYNAMIC PERIOD_M1 PERIOD_M5 PERIOD_M15 PERIOD_M30 PERIOD_H1 PERIOD_H4
PERIOD_D1 PERIOD_CURRENT MqlRates MqlDateTime STYLE_SOLID STYLE_DASH
OBJ_ARROW OBJ_TEXT OBJ_HLINE OBJPROP_ARROWCODE OBJPROP_COLOR OBJPROP_WIDTH
OBJPROP_ANCHOR OBJPROP_SELECTABLE OBJPROP_HIDDEN OBJPROP_BACK OBJPROP_TEXT
OBJPROP_FONT OBJPROP_FONTSIZE OBJPROP_TYPE OBJPROP_PRICE OBJPROP_STYLE
ANCHOR_TOP ANCHOR_BOTTOM clrLime clrTomato clrAqua clrOrange clrSilver
clrDarkGray clrMagenta clrRed FILE_CSV FILE_WRITE FILE_SHARE_READ FILE_ANSI
TIME_MINUTES TIME_DATE SYMBOL_TRADE_TICK_SIZE SYMBOL_DIGITS
""".split())
    declared |= builtin | KEYWORDS
    missing = {}
    for f, t in texts.items():
        code = strip_code(t)
        for m in re.finditer(r'\b([A-Za-z_]\w*)\s*\(', code):
            name = m.group(1)
            if name in ("if","for","while","switch","return","sizeof","case"): continue
            if name not in declared and not re.search(r'\b'+name+r'\b\s*\(', host):
                missing.setdefault(name, set()).add(f)
    for name, where in sorted(missing.items()):
        errs.append("possibly undeclared function: %s  (used in %s)"
                    % (name, ",".join(sorted(where))))

    # 8) MQL5 dialect rules (D1-D16) - the classes of mistake that made the
    #    v6.6.0 build fail: a returned reference, an integer literal suffix,
    #    a Print()-style comma chain. See tools/mql5_rules.py.
    dialect_e, dialect_w = [], []
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import mql5_rules
        inc_root = os.path.join(ROOT, "MQL5", "Include")
        types = {}
        for label, relp in mql5_rules.UNITS:
            upath = os.path.join(ROOT, relp)
            if not os.path.exists(upath):
                continue
            files = mql5_rules.closure(upath, inc_root)
            de, dw, types = mql5_rules.check_unit(files, types, ROOT)
            dialect_e += de
            dialect_w += dw
        # a .mqh shared by two units would otherwise be reported twice
        def _dedup(seq):
            out, seen = [], set()
            for x in seq:
                if x not in seen:
                    seen.add(x); out.append(x)
            return out
        dialect_e = _dedup(dialect_e)
        dialect_w = _dedup(dialect_w)
    except Exception as exc:                      # the linter must never hide
        dialect_w.append("mql5_rules could not run (%s) - run "
                         "python3 tools/mql5_rules.py separately" % exc)

    # ---------------------------------------------------------------- report
    print("="*72)
    print(" QSMC v6.6.4 - STATIC CONSISTENCY CHECK (not a compiler)")
    print("="*72)
    for f in FILES:
        print("  file: %-26s %6d bytes" % (f, os.path.getsize(os.path.join(INC,f))))
    print("-"*72)
    if dialect_e or dialect_w:
        print("  --- MQL5 dialect rules (D1-D16) " + "-"*28)
    for e in dialect_e:
        print("  ERROR " + e)
    for w in dialect_w:
        print("  WARN  " + w)
    print("  --- own checks " + "-"*55)
    for w in warns:
        print("  WARN  " + w)
    all_e = errs + dialect_e
    all_w = warns + dialect_w
    if all_e:
        for e in errs:
            print("  ERROR " + e)
        print("-"*72)
        print("  %d error(s), %d warning(s)" % (len(all_e), len(all_w)))
        return 1
    print("  no errors, %d warning(s)" % len(all_w))
    print("-"*72)
    print("  This check does NOT prove the code compiles. Press F7.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
