#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQL5 *dialect* rules for the QSMC subsystem.

These are the exact mistakes the v6.6.0 release made and MetaEditor rejected.
Every rule below is anchored to a real MetaEditor error message, so a clean
run here still does NOT prove compilation - press F7 - but a clean run does
prove that the whole class of mistake that broke the first build is gone.

  D1 ref-return      `Type &Name()` in the RETURN position.
                     MetaEditor: "reference cannot used".
                     A reference PARAMETER (`void F(Type &x)`) is legal; only
                     the return position is not. Fix: return a pointer built
                     with GetPointer(obj), or copy into a caller-owned object.
  D2 ref-decl        `Struct &r = obj;` as a local: a reference to a struct is
                     only allowed as a function parameter.
  D3 num-suffix      `0xFFu`, `2166136261u`, `10l`: MQL5 has no integer
                     literal suffix. MetaEditor: "'0xFF' - invalid number"
                     and "undeclared identifier 'u'".
  D4 comma-chain     `,` outside a call-argument list or a declaration list,
                     i.e. a Print() argument list pasted into an initializer.
                     `string s="a",IntegerToString(x);` is parsed as a SECOND
                     variable NAMED IntegerToString -> "'IntegerToString' -
                     class type expected", "name expected", and 20 more errors
                     that all come from one comma.
  D5 const-call      a non-const method called through a `const T *` /
                     `const T &` handle.
  D6 class-copy      `a = b;` between two class objects: MQL5 has no
                     assignment operator for classes (structs ARE value types
                     and may be copied).
  D7 fmt-args        StringFormat() whose % specifiers do not match its
                     arguments, or a %d/%s left inside Print(), which does not
                     format at all.
  D8 dyn-array-copy  a struct that OWNS a dynamic array copied by value.
  D9 dup-symbol      the same global function or global variable defined twice
                     inside ONE translation unit (the indicator, the test
                     script and the feeder are three separate units).

  D10 version-drift  the host's `#property version`, QSMC_VERSION_TEXT and the
                     layer banner must be ONE version - in every file of the unit
                     that claims a version at all, including a version that has
                     rotted inside a `#property copyright` string.
  D11 member-chain   `a.b.c` where b or c is neither a member nor a method of the
                     type of `a` (subsystem files only - see LEGACY_HOST).
  D12 ptr-to-struct  MQL5 has pointers only to CLASS objects. `Struct *p`, a
                     function returning `Struct *`, and GetPointer(struct) all
                     look legal next to `Class *Foo()` and D1 cannot see them.
  D13 arrow-op       `p->Member`: MQL5 has no arrow operator. An object pointer
                     is dereferenced with '.', exactly like the object itself.
                     MetaEditor reads `p->Ready()` as `p - > Ready()` and emits
                     "'>' - operand expected", "'Ready' - undeclared identifier",
                     "')' - expression expected" and "expression not boolean" -
                     four errors for one arrow. QSMC_Scanners.mqh carried six
                     of these, and QSMC_ScannerProbe.mq5 carried a seventh.
  D14 mql-datetime   `st.dayofyear` / `st.dayofweek`: MqlDateTime has no such
                     fields. MetaEditor: "undeclared identifier 'dayofyear'".
                     The real names are `day_of_year` and `day_of_week`; every
                     other field (year, mon, day, hour, min, sec) is checked
                     against the same fixed list.

Library use:   from mql5_rules import check_unit
Standalone:    python3 tools/mql5_rules.py [--root DIR] [--quiet]
"""
from __future__ import annotations

import os
import re
import sys
from bisect import bisect_right

NL = chr(10)
BS = chr(92)

# The 40 000-line host indicator is legacy: it re-uses the same short name in
# sibling nested blocks (`SRxnEvidence cand` after `SetupCandidate cand`), which
# no scope-free inference can resolve. The two rules that depend on knowing a
# variable's type (D6 class-copy, D11 member-chain) therefore run on the
# subsystem, the scripts and the feeder - and not on this file.
LEGACY_HOST = {"nadir2.mq5"}

PP_DIR_RE = re.compile(r'#\s*(define|include|import|ifdef|ifndef|else|endif|if|elif|pragma|property)\b')
FMT_SPEC_RE = re.compile(r'%(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|L|z|j|t)?[diufFeEgGxXospc]')
TYPE_BLOCK_RE = re.compile(r'\b(class|struct|interface)\s+([A-Za-z_]\w*)')
MEMBER_CALL_RE = re.compile(r'([A-Za-z_]\w*)(?:\.|->)([A-Za-z_]\w*)\s*\(')
REF_RETURN_RE = re.compile(
    r'(?:^|(?<=[;{}\n]))\s*(?:(?:virtual|static|explicit|const|inline)\s+)*'
    r'([A-Za-z_]\w*)\s*(?:\*\s*)?&\s*~?([A-Za-z_]\w*)\s*\(')
NUM_SUFFIX_RE = re.compile(r'\b(?:0[xX][0-9a-fA-F]+|\d+)([uUlL])(?![0-9A-Za-z_.])')

# MqlDateTime is a BUILT-IN struct, so parse_types never sees it and D11 cannot
# check its members. These are the only legal fields (MQL5 Reference / MqlDateTime).
MQL_DATETIME_FIELDS = {"year", "mon", "day", "hour", "min", "sec",
                       "day_of_week", "day_of_year"}


# --------------------------------------------------------------------------
# masking
# --------------------------------------------------------------------------

def mask(src, blank_strings=True):
    """Length-preserving mask: comments -> spaces and, optionally, the
    CONTENTS of a string/char literal -> 'x'.

    Length is preserved on purpose: an offset found in the mask maps to the
    same offset in the raw text, so rule D7 can read the real format string
    while every structural rule is blind to comment and literal text.

    Single pass, decision made at the opening character: a '//' inside a
    literal ("http://x") is consumed by the literal branch, and a '"' inside a
    comment is consumed by the comment branch. Getting this order wrong
    desynchronises the brace depth for the rest of the file and drowns the
    report in false positives.
    """
    out = list(src)
    n = len(src)

    def eat(quote, frm):
        j = frm + 1
        while j < n and src[j] != quote:
            if src[j] == BS:
                j += 1
            j += 1
        return min(j, n - 1) if n else 0

    def blank(a, b):
        for k in range(max(a, 0), min(b, n)):
            if src[k] != NL:
                out[k] = " "

    i = 0
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find(NL, i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c in ('"', "'"):
            j = eat(c, i)
            if blank_strings:
                for k in range(i + 1, j):
                    if src[k] != NL:
                        out[k] = "x"
            i = j + 1
        elif c == "#" and (i == 0 or src[i - 1] in (NL, " ", chr(9))):
            # A directive line contributes its NAME only: `#define A(x) {,}`
            # must not move the depth counters. A macro body written with
            # backslash continuations is masked the same way, line by line.
            j = src.find(NL, i)
            j = n if j < 0 else j
            head = PP_DIR_RE.match(src[i:j])
            body_end = j
            while body_end + 1 < n and src[body_end - 1] == BS:      # continuation
                k = src.find(NL, body_end + 1)
                body_end = n if k < 0 else k
            blank(i, body_end)
            if head:
                for k, ch in enumerate(head.group(0)):
                    out[i + k] = ch
            i = j + 1
        else:
            i += 1
    return "".join(out)


class ScopeIndex:
    """Lexical scope as the stack of '{' offsets open at a position.

    A declaration is visible to a use only if the block that declares it is the
    use's block or an ANCESTOR of it (class body -> its methods, function body
    -> its loops). Without that rule the same reused short name (`c`, `dt`, `r`)
    in the next function down the file resolves to the wrong type, and every
    member rule starts lying - which is precisely what a file-wide map did.
    """
    __slots__ = ("ev", "off")

    def __init__(self, code):
        ev, stack = [], []
        for i, ch in enumerate(code):
            if ch == "{":
                stack.append(i)
                ev.append((i, tuple(stack)))
            elif ch == "}":
                if stack:
                    stack.pop()
                ev.append((i, tuple(stack)))
        self.ev = ev
        self.off = [e[0] for e in ev]

    def scope_at(self, pos):
        j = bisect_right(self.off, pos)
        return self.ev[j - 1][1] if j else ()

    @staticmethod
    def visible(decl, use):
        if decl is None or use is None:
            return True
        if len(decl) > len(use):
            return False
        return all(decl[k] == use[k] for k in range(len(decl)))


class LineIndex:
    """bisect over the newline offsets - line_of() must be O(log n): a
    code.count() per hit is quadratic on a 40 000 line host file."""
    __slots__ = ("nl",)

    def __init__(self, code):
        self.nl = [m.start() for m in re.finditer(re.escape(NL), code)]

    def line(self, pos):
        return bisect_right(self.nl, max(0, pos)) + 1



def split_top(text):
    """Split on separators that sit at paren/bracket/brace depth 0."""
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


# A '{' opens a BLOCK unless the text right before it makes it an initialiser
# list (`int a[3]={0,0};`, `f({1,2})`). Treating an initialiser brace as a
# boundary would cut `0,0` out as its own statement and invent a comma error.
INIT_BEFORE = ("=", ",", "(", "[", "+", "?", ":")


def statements(code):
    """Yield (offset, text) for every statement.

    A statement ends at ';' - and at the '{' / '}' of a BLOCK - but only when
    no parenthesis and no bracket is open, so a `for(a;b;c)` header is never
    cut in half. An initialiser brace (`int a[2]={0,0};`) is deliberately NOT a
    boundary: splitting there would leave `0,0` as a statement of its own and
    invent a comma-operator error.
    """
    pdepth = bdepth = 0
    blocks = []                       # stack: True = block brace
    start = 0
    for i, ch in enumerate(code):
        if ch == '(':
            pdepth += 1
        elif ch == ')':
            pdepth = max(0, pdepth - 1)
        elif ch == '[':
            bdepth += 1
        elif ch == ']':
            bdepth = max(0, bdepth - 1)
        elif ch == '{':
            head = code[:i].rstrip()
            block = (pdepth == 0 and bdepth == 0 and
                     (not head or not head.endswith(INIT_BEFORE)))
            blocks.append(block)
            if block:
                body = code[start:i]
                if body.strip():
                    yield start, body
                start = i + 1
        elif ch == '}':
            block = blocks.pop() if blocks else True
            if block and pdepth == 0 and bdepth == 0:
                body = code[start:i]
                if body.strip():
                    yield start, body
                start = i + 1
        elif ch == ';' and pdepth == 0 and bdepth == 0:
            body = code[start:i]
            if body.strip():
                yield start, body
            start = i + 1
    body = code[start:]
    if body.strip():
        yield start, body


def match_paren(code, i):
    """i points at '(' - return the index of its ')' or -1."""
    depth = 0
    n = len(code)
    while i < n:
        if code[i] == '(':
            depth += 1
        elif code[i] == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# --------------------------------------------------------------------------
# type model
# --------------------------------------------------------------------------

def block_body(code, brace):
    depth, i, n = 0, brace, len(code)
    while i < n:
        if code[i] == '{':
            depth += 1
        elif code[i] == '}':
            depth -= 1
            if depth == 0:
                return code[brace + 1:i]
        i += 1
    return code[brace + 1:]


# A method head is a sequence of identifiers / cv-qualifiers only. The
# character class is FLAT on purpose: the first version of this rule nested
# `(?:...)*` around an alternation and cost 150 s of backtracking on the host
# file before it was replaced.
HEAD_OK_RE = re.compile(r'[A-Za-z_][\w\s\*&:,<>]*\Z')


_TYPES_CACHE = {}


def parse_types(code, types, origin=None):
    """types: name -> {kind, methods{name:const-ness}, members{name:info}, parents}

    Memoised on the source text: the three translation units of this project
    share 12 of their 13 files, and re-parsing them per unit tripled the run."""
    key = origin
    if key in _TYPES_CACHE:
        for name, info in _TYPES_CACHE[key].items():
            tgt = types.setdefault(name, {"kind": info["kind"], "methods": {},
                                          "members": {}, "parents": [], "origin": info["origin"]})
            tgt["methods"].update(info["methods"])
            tgt["members"].update(info["members"])
            tgt["parents"] = list(set(tgt["parents"]) | set(info["parents"]))
        return
    found = {}
    _parse_types_raw(code, found, origin)
    _TYPES_CACHE[key] = found
    for name, info in found.items():
        tgt = types.setdefault(name, {"kind": info["kind"], "methods": {}, "members": {},
                                      "parents": [], "origin": origin})
        tgt["kind"] = info["kind"]
        tgt["methods"].update(info["methods"])
        tgt["members"].update(info["members"])
        tgt["parents"] = list(set(tgt["parents"]) | set(info["parents"]))


def _parse_types_raw(code, types, origin=None):
    for m in TYPE_BLOCK_RE.finditer(code):
        kind, name = m.group(1), m.group(2)
        brace = code.find('{', m.end())
        if brace < 0:
            continue
        body = block_body(code, brace)
        info = types.setdefault(name, {"kind": kind, "methods": {}, "members": {},
                                       "parents": [], "origin": origin})
        info["kind"] = kind
        if origin:
            info["origin"] = origin
        pm = re.search(r':\s*([^{]*)$', code[m.start():brace].strip())
        if pm:
            info["parents"] = [p for p in re.findall(r'\w+',
                                 re.sub(r'\b(public|private|protected)\b', ' ', pm.group(1)))
                               if p not in ("public", "private", "protected")]
        for raw in body.split(NL):
            line = raw.strip().rstrip(";").strip()
            if not line or line.startswith("#"):
                continue
            mm = re.match(r'^(?:(?:const|static|virtual|extern|input|sinput)\s+)*'
                          r'([A-Za-z_]\w*)\s*(\*{0,2})\s*(&)?\s*'
                          r'([A-Za-z_]\w*)\s*(\[[^\]]*\])?(.*)$', line)
            if mm and mm.group(4) not in ("if", "for", "while", "switch", "return", "case",
                                          "public", "private", "protected"):
                def add(name, arr):
                    info["members"][name] = {
                        "type": mm.group(1),
                        "ptr": bool(mm.group(2)),
                        "ref": bool(mm.group(3)),
                        "arr": bool(arr),
                        "dyn": bool(arr and arr.strip() in ("[]", "[ ]")),
                    }
                # MQL5 allows `double entry,sl,tp1;` - every declarator is a
                # member, not only the first one. Missing the rest is what made
                # a member-existence rule scream about the legacy host file.
                add(mm.group(4), mm.group(5))
                for rest in split_top(mm.group(6)):
                    dm = re.match(r'\s*,?\s*([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*$', rest)
                    if dm:
                        add(dm.group(1), dm.group(2))
        for dm in re.finditer(r'([A-Za-z_]\w*)\s*\(([^;{}()]*(?:\([^()]*\)[^;{}()]*)*)\)\s*'
                              r'(const)?\s*(?:override\s*)?(?:\{|;)', body):
            mname = dm.group(1)
            if mname in ("if", "for", "while", "switch", "return", "catch", "sizeof", "else"):
                continue
            head = body[:dm.start()].rstrip().rsplit(NL, 1)[-1].strip()
            if head.endswith((",", "=", "(", "+", "-", "&&", "||")):
                continue
            if head and not HEAD_OK_RE.match(head):
                continue
            info["methods"].setdefault(mname, bool(dm.group(3)))


def member_types(types, name, seen=None):
    """All member infos of a type, including inherited ones."""
    seen = seen or set()
    if name in seen or name not in types:
        return {}
    seen.add(name)
    out = dict(types[name]["members"])
    for p in types[name]["parents"]:
        out.update(member_types(types, p, seen))
    return out


def method_is_const(types, cls, meth, seen=None):
    seen = seen or set()
    if cls in seen or cls not in types:
        return None
    seen.add(cls)
    info = types[cls]
    if meth in info["methods"]:
        return info["methods"][meth]
    for p in info["parents"]:
        r = method_is_const(types, p, meth, seen)
        if r is not None:
            return r
    return None


# --------------------------------------------------------------------------
# include closure
# --------------------------------------------------------------------------

def closure(path, inc_root, seen=None):
    seen = seen if seen is not None else []
    path = os.path.abspath(path)
    if path in seen or not os.path.isfile(path):
        return seen
    seen.append(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        src = f.read()
    for m in re.finditer(r'^\s*#include\s+[<"]([^">]+)[>]', src, re.M):
        rel = m.group(1).replace("\\", "/")
        for cand in (os.path.join(inc_root, rel),
                     os.path.join(os.path.dirname(path), rel),
                     os.path.join(inc_root, "QSMC", os.path.basename(rel))):
            if os.path.isfile(cand):
                closure(cand, inc_root, seen)
                break
    return seen


# --------------------------------------------------------------------------
# the rules
# --------------------------------------------------------------------------

def bad_name(seg):
    m = re.match(r'^\s*([A-Za-z_]\w*)', seg)
    return m.group(1) if m else seg[:20]


DECL_HEAD_RE = re.compile(r'^(?:(?:const|static|input|sinput|extern)\s+)*(?:unsigned\s+)?'
                         r'(?:ulong|uint|long|int|short|ushort|uchar|char|double|float|bool|'
                         r'string|datetime|color|[A-Za-z_]\w*)\s*(?:\*+|&)?\s+[A-Za-z_]\w*')
DECL_ITEM_RE = re.compile(r'^[A-Za-z_]\w*(?:\s*\[[^\]]*\])?\s*(?:=\s*\S.*)?$')


def check_unit(files, types=None, base=None):
    """files: ordered absolute paths of ONE translation unit.
    Returns (errors, warnings, types)."""
    errs, warns = [], []
    codes, raws, keepcodes = {}, {}, {}
    for p in files:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        raws[p] = raw
        codes[p] = mask(raw, True)        # structural: literal contents blanked
        keepcodes[p] = mask(raw, False)   # text rules: literals readable

    try:
        base = base or os.path.commonpath([os.path.abspath(x) for x in files] or ["."])
    except ValueError:
        base = os.path.dirname(os.path.abspath(files[0])) if files else "."

    def rel(p):
        try:
            return os.path.relpath(os.path.abspath(p), base)
        except ValueError:
            return p

    if types is None:
        types = {}
    for p, code in codes.items():
        parse_types(code, types, rel(p))
    idx = {p: LineIndex(code) for p, code in codes.items()}

    structs_dyn = {n for n, i in types.items()
                   if i["kind"] == "struct" and any(v["dyn"] for v in i["members"].values())}

    # ---- D1 ---------------------------------------------------------------
    for p, code in codes.items():
        for m in REF_RETURN_RE.finditer(code):
            ty, fname = m.group(1), m.group(2)
            if ty in ("return", "if", "while", "for", "switch", "operator", "new", "delete"):
                continue
            if fname in types:                       # `Foo &Bar` naming a type
                continue
            errs.append("%s:%d  D1 ref-return: MQL5 cannot return a reference from %s() "
                        "(MetaEditor: 'reference cannot used'). Return a pointer via "
                        "GetPointer(obj) or copy into a caller-owned variable."
                        % (rel(p), idx[p].line(m.start(1)), fname))

    # ---- D2 ---------------------------------------------------------------
    for p, code in codes.items():
        for m in re.finditer(r'(?:^|(?<=[;{}\n]))\s*(const\s+)?([A-Za-z_]\w*)\s*&\s*([A-Za-z_]\w*)\s*=', code):
            ty = m.group(2)
            if types.get(ty, {}).get("kind") != "struct":
                continue
            head = code[:m.start()].rsplit(NL, 1)[-1]
            if "(" in head and not head.rstrip().endswith((";", "{", "}")):
                continue                              # parameter list of a call
            errs.append("%s:%d  D2 ref-decl: reference variable '%s' to struct %s is legal only "
                        "as a function parameter." % (rel(p), idx[p].line(m.start(2)),
                                                      m.group(3), ty))

    # ---- D3 ---------------------------------------------------------------
    for p, code in codes.items():
        for m in NUM_SUFFIX_RE.finditer(code):
            errs.append("%s:%d  D3 num-suffix: MQL5 has no integer literal suffix '%s' "
                        "(-> 'invalid number' + 'undeclared identifier %s'). Write the value "
                        "as a plain literal (hex when it does not fit an int) and cast."
                        % (rel(p), idx[p].line(m.start()), m.group(1), m.group(1)))
        for m in re.finditer(r'(?<![\w.])(\d{10,})(?![\w.])', code):
            txt = m.group(1)
            if int(txt) > 2147483647:
                warns.append("%s:%d  D3 literal %s does not fit an int; MQL5 picks the first "
                             "type that fits (use the hex form or an explicit cast)."
                             % (rel(p), idx[p].line(m.start()), txt))

    # ---- D4 ---------------------------------------------------------------
    for p, code in codes.items():
        for stmt_start, stmt in statements(code):
            if "," not in stmt:
                continue
            parts = split_top(stmt)
            if len(parts) < 2:
                continue
            first = " ".join(parts[0].split())
            decl = DECL_HEAD_RE.match(first)
            for seg in parts[1:]:
                s = " ".join(seg.split())
                if not s or DECL_ITEM_RE.match(s):
                    continue                            # legal: another declared variable
                if decl:
                    errs.append("%s:%d  D4 comma-chain: after the declarator, MQL5 parses ',' as a "
                                "SECOND variable named '%s' - there is no comma operator. Build text "
                                "with + or StringFormat(); reserve ',' for call arguments."
                                % (rel(p), idx[p].line(stmt_start), bad_name(s)))
                else:
                    errs.append("%s:%d  D4 comma-chain: ',' at statement level is not an operator in "
                                "MQL5 - split this into separate statements."
                                % (rel(p), idx[p].line(stmt_start)))
                break

    # ---- D5 const-correctness through a const handle ----------------------
    #   The declaration that counts is the NEAREST ONE ABOVE the use: the same
    #   short name (`ch`, `ex`, `s`) is reused in many methods of one file, and
    #   a file-wide map reports a false positive as soon as one of those reuses
    #   is const and another is not.
    decl_re = re.compile(r'\b(const\s+)?([A-Za-z_]\w*)\s*(\*{1,2}|&)\s*'
                         r'([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*[;=)]')
    for p, code in codes.items():
        events = {}
        for m in decl_re.finditer(code):
            ty = m.group(2)
            if types.get(ty, {}).get("kind") not in ("class", "struct"):
                continue
            events.setdefault(m.group(4), []).append((m.start(4), ty if m.group(1) else None))
        for e in events.values():
            e.sort()
        scopes = ScopeIndex(code)
        for m in MEMBER_CALL_RE.finditer(code):
            var, meth = m.group(1), m.group(2)
            ev = events.get(var)
            if not ev:
                continue
            use = scopes.scope_at(m.start())
            prior = [k for k in ev if k[0] <= m.start()
                     and ScopeIndex.visible(scopes.scope_at(k[0]), use)]
            if not prior:
                continue
            ty = prior[-1][1]
            if ty is None:
                continue
            if method_is_const(types, ty, meth) is False:
                errs.append("%s:%d  D5 const-call: %s.%s() - %s() is not const, but the handle is "
                            "'const %s' (declared line %d). Mark the method const or drop the "
                            "const from the handle."
                            % (rel(p), idx[p].line(m.start()), var, meth, meth, ty,
                               idx[p].line(prior[-1][0])))

    # ---- D6 class object copied with '=' ------------------------------------
    #   (type-inference based: see LEGACY_HOST)
    #   Structs are value types in MQL5 and may be copied; classes may NOT (no
    #   assignment operator exists), so `Foo a = b;` / `a = b;` is an error.
    for p, code in codes.items():
        if os.path.basename(p) in LEGACY_HOST:
            continue
        own = {}
        for m in re.finditer(r'(?:^|(?<=[;{}\n]))\s*(const\s+)?([A-Za-z_]\w*)(\*{0,2})\s+([A-Za-z_]\w*)\s*'
                            r'(?:\[[^\]]*\])?\s*(?:=[^;{}]*)?[;{]', code):
            ty, stars, name = m.group(2), m.group(3), m.group(4)
            if m.group(1) or stars:
                continue
            if types.get(ty, {}).get("kind") == "class":
                own.setdefault(name, []).append((m.start(4), ty))
        for e in own.values():
            e.sort()
        scopes6 = ScopeIndex(code)
        for m in re.finditer(r'(?:^|(?<=[;{}\n]))\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*;', code):
            lhs, rhs = m.group(1), m.group(2)
            if lhs not in own or rhs not in own:
                continue
            use = scopes6.scope_at(m.start())
            lprior = [x for x in own[lhs] if x[0] <= m.start(1)
                      and ScopeIndex.visible(scopes6.scope_at(x[0]), use)]
            rprior = [x for x in own[rhs] if x[0] <= m.start(2)
                      and ScopeIndex.visible(scopes6.scope_at(x[0]), use)]
            if lprior and rprior and lprior[-1][1] == rprior[-1][1]:
                errs.append("%s:%d  D6 class-copy: '%s = %s' copies a %s object; MQL5 has no "
                            "assignment operator for classes. Use a pointer, or copy field "
                            "by field." % (rel(p), idx[p].line(m.start()), lhs, rhs, lprior[-1][1]))

    # ---- D7 (needs the literal contents -> mask with strings kept) -------
    for p in files:
        raw = raws[p]
        code = keepcodes[p]
        for m in re.finditer(r'\bStringFormat\s*\(', code):
            o = code.find('(', m.end() - 1)
            c = match_paren(code, o)
            if c < 0:
                continue
            args = split_top(code[o + 1:c])
            if not args:
                continue
            lit = args[0].strip()
            mm = re.match(r'^"((?:[^"\\]|\\.)*)"', raw[raw.find('(', m.start()):][:200])
            if not mm:
                continue
            fmt = mm.group(1)
            specs = len(FMT_SPEC_RE.findall(fmt.replace("%%", "@@")))
            given = len([a for a in args[1:] if a.strip()])
            if specs != given:
                errs.append("%s:%d  D7 fmt-args: StringFormat passes %d argument(s) for %d "
                            "specifier(s)." % (rel(p), idx[p].line(m.start()), given, specs))
        for m in re.finditer(r'\bPrint(?:s)?\s*\(\s*"((?:[^"\\]|\\.)*)"', code):
            if FMT_SPEC_RE.search(m.group(1).replace("%%", "@@")):
                errs.append("%s:%d  D7 fmt-args: Print() does NOT format - the %%spec in its first "
                            "argument is printed literally. Concatenate, or wrap the whole line in "
                            "StringFormat()." % (rel(p), idx[p].line(m.start())))

    # ---- D8 ---------------------------------------------------------------
    for p, code in codes.items():
        if not structs_dyn:
            break
        for m in re.finditer(r'(?:^|(?<=[;{}\n]))\s*((?:const\s+)?[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*=\s*'
                             r'([A-Za-z_][\w.\[\]]*)\s*;', code):
            if m.group(1) in structs_dyn:
                warns.append("%s:%d  D8 dyn-array-copy: struct %s owns a dynamic array and is "
                             "copied by value - pass it by reference instead."
                             % (rel(p), idx[p].line(m.start()), m.group(1)))
        for m in re.finditer(r'\breturn\s+([A-Za-z_]\w*)\s*;', code):
            var = m.group(1)
            dm = re.search(r'(?:^|(?<=[;{}\n]))\s*((?:const\s+)?[A-Za-z_]\w*)\s+' + var + r'\s*[;=]', code)
            if dm and dm.group(1) in structs_dyn:
                warns.append("%s:%d  D8 dyn-array-copy: a struct owning a dynamic array "
                             "(%s) is returned by value." % (rel(p), idx[p].line(m.start()),
                                                             dm.group(1)))

    # ---- D9 ---------------------------------------------------------------
    seen_sym = {}
    for p in files:                                     # include order matters
        code = codes[p]
        for m in re.finditer(r'^(?!#)(?:[A-Za-z_]\w*[\*&\s]+)?([A-Za-z_]\w*)\s*\('
                             r'[^;{)]*\)\s*(?:const\s*)?\{', code, re.M):
            name = m.group(1)
            if name in ("if", "for", "while", "switch", "return", "else", "catch", "sizeof"):
                continue
            key = ("fn", name)
            if key in seen_sym and seen_sym[key] != p:
                errs.append("%s:%d  D9 dup-symbol: %s() is also defined in %s - one translation "
                            "unit cannot hold both." % (rel(p), idx[p].line(m.start()), name,
                                                        rel(seen_sym[key])))
            seen_sym.setdefault(key, p)
        for m in re.finditer(r'^(?!#|input|sinput|extern)(?:static\s+)?[A-Za-z_]\w*'
                             r'(?:\s*\*+)?\s+([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?;',
                             code, re.M):
            name = m.group(1)
            if name in types:
                continue
            key = ("var", name)
            if key in seen_sym and seen_sym[key] != p:
                errs.append("%s:%d  D9 dup-symbol: global '%s' is also defined in %s."
                            % (rel(p), idx[p].line(m.start()), name, rel(seen_sym[key])))
            seen_sym.setdefault(key, p)

    # ---- D11 chained member access ----------------------------------------
    #   Resolve the head of the chain from the NEAREST preceding declaration
    #   (local, member field or parameter - all of them are `Type name` lines),
    #   then walk the members. A component followed by '(' is a method: the
    #   return type of a method is not modelled here, so the walk stops there
    #   instead of guessing.
    var_decl_re = re.compile(r'(?:^|(?<=[;{}\n]))\s*(?:(?:const|static|input|sinput|extern|virtual)\s+)*'
                             r'([A-Za-z_][\w:]*)\s*(?:\*+|&)?\s*([A-Za-z_]\w*)\s*'
                             r'(?:\[[^\]]*\])?\s*(?:=[^;{}(]*)?[;{)]')
    param_re = re.compile(r'\(([^()]*?(?:\([^()]*\)[^()]*?)*)\)')
    chain_re = re.compile(r'\b([A-Za-z_]\w*)((?:\s*(?:\.|->)\s*[A-Za-z_]\w*\s*(?:\([^()]*\))?)+)')

    for p, code in codes.items():
        if os.path.basename(p) in LEGACY_HOST:
            continue
        events = {}
        for m in var_decl_re.finditer(code):
            ty, name = m.group(1), m.group(2)
            if ty in types or types.get(ty, {}).get("kind"):
                events.setdefault(name, []).append((m.start(2), ty))
        for m in re.finditer(r'([A-Za-z_]\w*)\s*\(([^()]*)\)\s*(?:const\s*)?\{', code):
            for seg in split_top(m.group(2)):
                pm = re.search(r'([A-Za-z_][\w:]*)\s*(?:\*+|&)?\s*(\[[^\]]*\])?\s*([A-Za-z_]\w*)\s*$',
                               seg.strip())
                if pm and pm.group(1) in types:
                    events.setdefault(pm.group(3), []).append((m.start(), pm.group(1)))
        for k in events:
            events[k].sort()

        scopes11 = ScopeIndex(code)

        def resolve_at(name, pos):
            ev = events.get(name)
            if not ev:
                return None
            use = scopes11.scope_at(pos)
            prior = [x for x in ev if x[0] <= pos
                     and ScopeIndex.visible(scopes11.scope_at(x[0]), use)]
            return prior[-1][1] if prior else None

        for m in chain_re.finditer(code):
            ty = resolve_at(m.group(1), m.start())
            if ty not in types:
                continue
            for sm in re.finditer(r'(?:\.|->)\s*([A-Za-z_]\w*)\s*(\[)?\s*(\()?', m.group(2)):
                pos = m.start() + sm.start(1)
                comp, is_call = sm.group(1), bool(sm.group(3))
                info = types[ty]
                mem = info["members"].get(comp)
                if is_call:
                    if comp not in info["methods"] and mem is None:
                        errs.append("%s:%d  D11 member-chain: %s() is neither a method nor a member "
                                    "of %s" % (rel(p), idx[p].line(pos), comp, ty))
                    break
                if mem is None:
                    names = sorted(info["members"])
                    errs.append("%s:%d  D11 member-chain: '%s' is not a member of %s (known: %s%s)"
                                % (rel(p), idx[p].line(pos), comp, ty,
                                   ", ".join(names[:8]), "…" if len(names) > 8 else ""))
                    break
                ty2 = mem.get("type")
                if ty2 not in types:
                    break                      # builtin, or an unknown type
                ty = ty2

    # ---- D12 pointer to a struct -------------------------------------------
    #   QSMC_Scanners.mqh had `const SSetupRow *Row(int i){ return &m_rows[i]; }`
    #   in three classes. It reads exactly like the legal `CBarSeries *Chart()`,
    #   and because the module had no host nothing ever objected. Reference-out
    #   (`bool Row(int i,SSetupRow &out)`) is what the same file already does for
    #   CZoneRegistry::At() and for a seasonality row, and it is unambiguously
    #   legal - so the conversion is no-regret even if a later build ever did
    #   allow the pointer form.
    ptr_ret_re = re.compile(r'(?:^|(?<=[;{}\n]))\s*(?:(?:const|static|virtual|explicit)\s+)*'
                            r'([A-Za-z_][\w:]*)\s*\*\s*(~?[A-Za-z_]\w*)?\s*\(')
    ptr_decl_re = re.compile(r'(?:^|(?<=[;{}\n]))\s*(?:const\s+)?([A-Za-z_][\w:]*)\s*\*\s*'
                             r'([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?[;{]')
    for pd_, code in codes.items():
        for m in ptr_ret_re.finditer(code):
            if types.get(m.group(1), {}).get("kind") != "struct":
                continue
            name = m.group(2) or "an operator"
            errs.append("%s:%d  D12 ptr-to-struct: %s() returns %s*, but MQL5 has no pointer "
                        "to a structure - only to class objects. Give the caller a reference-out "
                        "instead: bool %s(int i,%s &out)."
                        % (rel(pd_), idx[pd_].line(m.start()), name, m.group(1), name,
                           m.group(1)))
        for m in ptr_decl_re.finditer(code):
            if types.get(m.group(1), {}).get("kind") != "struct":
                continue
            if re.search(r'\breturn\b', code[max(0, m.start()-40):m.start()]):
                continue
            errs.append("%s:%d  D12 ptr-to-struct: '%s *%s' - you cannot take the address of a "
                        "structure in MQL5. Pass it by reference, or copy it."
                        % (rel(pd_), idx[pd_].line(m.start()), m.group(1), m.group(2)))

    # ---- D13 arrow operator ------------------------------------------------
    #   MQL5 does not have '->', not even for class-object pointers: the
    #   pointer is used with '.', exactly like the object. MetaEditor does not
    #   stop at the arrow - it splits it into '-' and '>' and then reports the
    #   member as an undeclared identifier, which is why one typo produced four
    #   errors per line in QSMC_Scanners.mqh and QSMC_ScannerProbe.mq5.
    for p, code in codes.items():
        for m in re.finditer(r'->\s*([A-Za-z_]\w*)', code):
            errs.append("%s:%d  D13 arrow-op: '->' does not exist in MQL5 (MetaEditor: "
                        "'>' - operand expected, then '%s' - undeclared identifier). An "
                        "object pointer is dereferenced with '.': p.%s, not p->%s."
                        % (rel(p), idx[p].line(m.start()), m.group(1),
                           m.group(1), m.group(1)))

    # ---- D14 MqlDateTime member names --------------------------------------
    #   A built-in struct's fields are easy to guess and MQL5 rejects the guess
    #   with a bare "undeclared identifier", which reads like a scoping problem.
    #   QSMC_Scanners.mqh used st.dayofyear; the field is st.day_of_year.
    for p, code in codes.items():
        dt_decls = {}
        for m in re.finditer(r'\bMqlDateTime\s*(?:&\s*)?([A-Za-z_]\w*)', code):
            dt_decls.setdefault(m.group(1), []).append((m.start(1), "MqlDateTime"))
        if not dt_decls:
            continue
        scopes14 = ScopeIndex(code)
        for m in re.finditer(r'\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)', code):
            var, mem = m.group(1), m.group(2)
            ev = dt_decls.get(var)
            if not ev:
                continue
            use = scopes14.scope_at(m.start())
            prior = [k for k in ev if k[0] <= m.start()
                     and ScopeIndex.visible(scopes14.scope_at(k[0]), use)]
            if not prior or mem in MQL_DATETIME_FIELDS:
                continue
            errs.append("%s:%d  D14 mql-datetime: MqlDateTime has no member '%s' "
                        "(MetaEditor: undeclared identifier '%s'). Its fields are %s."
                        % (rel(p), idx[p].line(m.start(2)), mem, mem,
                           ", ".join(sorted(MQL_DATETIME_FIELDS))))

    # ---- D10 version drift -------------------------------------------------
    #   main file first in the closure order, and the layer banner sits in
    #   QSMC_Root.mqh next to it.
    main = files[0] if files else None
    vt = None
    ref = None                                  # the version this unit must print
    if main and main.lower().endswith((".mq5", ".mq4")):
        host = raws[main]
        vt = re.search(r'#define\s+QSMC_VERSION_TEXT\s+"v?(\d+)\.(\d+)\.(\d+)"', host)
        pv = re.search(r'#property\s+version\s+"(\d+)\.(\d+)"', host)
        if vt and pv:
            want = "%s.%s" % (vt.group(1), vt.group(2) + vt.group(3))
            if pv.group(1) + "." + pv.group(2) != want:
                errs.append("%s:%d  D10 version-drift: #property version \"%s.%s\" does not "
                            "match QSMC_VERSION_TEXT \"v%s.%s.%s\" (expected \"%s\")."
                            % (rel(main), line_of_host(host, pv.start()),
                               pv.group(1), pv.group(2),
                               vt.group(1), vt.group(2), vt.group(3), want))
        bv = None
        for p, code in keepcodes.items():
            for m in re.finditer(r'\[QSMC_ARB\]\s+v(\d+)\.(\d+)(?:\.(\d+))?\s+arbitration layer ON',
                                 code):
                got = (m.group(1), m.group(2), m.group(3) or "0")
                if bv is None:
                    bv = got
                if not vt:
                    continue
                if got != (vt.group(1), vt.group(2), vt.group(3)):
                    errs.append("%s:%d  D10 version-drift: the layer banner says v%s.%s.%s but the "
                                "host QSMC_VERSION_TEXT says v%s.%s.%s - one of them is lying about "
                                "what is compiled." % (rel(p), idx[p].line(m.start()),
                                                       got[0], got[1], got[2],
                                                       vt.group(1), vt.group(2), vt.group(3)))
        # A script or an EA that only includes the layer has no host macro to
        # agree with, so the banner it will print alongside is the reference.
        ref = norm_ver(vt.group(1), vt.group(2), vt.group(3)) if vt else bv
        if ref:
            # RAW text, not a mask: mask() blanks preprocessor lines, and every
            # #property in the world begins with '#'. That is why D10a reads
            # raws[main] - and why these two sub-checks must too.
            for pc_, text in raws.items():
                # The host's own #property version is D10a's job (it has a macro
                # to agree with). Every other file - including a companion that
                # is main of its own unit - is compared here.
                if pc_ != main or not vt:
                    for m in re.finditer(
                            r'^\s*#property\s+version\s+"(\d+)\.(\d+)(?:\.(\d+))?"',
                            text, re.M):
                        got = norm_ver(m.group(1), m.group(2), m.group(3))
                        if got == ref:
                            continue
                        warns.append("%s:%d  D10 version-drift: this file calls itself %s.%s.%s "
                                     "while the layer it drives prints v%s.%s.%s - if the two ship "
                                     "together, say so with one number."
                                     % (rel(pc_), line_of_host(text, m.start()),
                                        got[0], got[1], got[2],
                                        ref[0], ref[1], ref[2]))
                for m in re.finditer(r'^\s*#property\s+(copyright|description|link|legend)\s+'
                                     r'"([^"]*)"', text, re.M):
                    vm = re.search(r'v?(\d+)\.(\d+)(?:\.(\d+))?', m.group(2))
                    if not vm or norm_ver(vm.group(1), vm.group(2), vm.group(3)) == ref:
                        continue
                    warns.append("%s:%d  D10 version-drift: `#property %s` hard-codes v%s.%s.%s "
                                 "while this build is v%s.%s.%s. A version inside a prose string "
                                 "cannot be kept in sync - take the number out of it."
                                 % (rel(pc_), line_of_host(text, m.start()), m.group(1),
                                    vm.group(1), vm.group(2), vm.group(3) or "0",
                                    ref[0], ref[1], ref[2]))

    return errs, warns, types


def norm_ver(major, minor, patch=None):
    """One comparable tuple for the two ways MQL5 writes a version.

    `#property version` takes the MT5 form `X.YZ` (patch folded into the minor,
    two components), while the source text uses `vX.Y.Z`. D10a already compares
    them as "%s.%s" % (major, minor + patch); the companion checks need the same
    normalisation or every correctly-numbered file looks stale.
    """
    major, minor = str(major), str(minor)
    patch = str(patch) if patch else ""
    if patch in ("", "0") and len(minor) > 1:
        return (major, minor[0], minor[1:])
    return (major, minor, patch or "0")


def line_of_host(text, pos):
    return text.count(NL, 0, max(0, pos)) + 1


# --------------------------------------------------------------------------
# standalone driver
# --------------------------------------------------------------------------

UNITS = [
    ("nadir2.mq5 (indicator)",            "nadir2.mq5"),
    ("QSMC_ArbiterTest.mq5 (self-test)",  "MQL5/Scripts/QSMC_ArbiterTest.mq5"),
    ("KLJ_DataFeeder.mq5 (companion)",    "MQL5/Experts/KLJ_DataFeeder.mq5"),
    # Since v6.6.3 QSMC_Scanners.mqh has a host (QSMC_ScannerProbe.mq5). The
    # synthetic unit stays anyway: if that host is ever removed, the module must
    # still be linted, because an unincluded header is exactly how this file
    # accumulated four bugs that no build could see.
    ("QSMC_ScannerProbe.mq5 (Phase 7 host)","MQL5/Indicators/QSMC_ScannerProbe.mq5"),
    ("(virtual) QSMC_Scanners.mqh",       "MQL5/Include/QSMC/QSMC_Scanners.mqh"),
]


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "--root" in argv:
        root = os.path.abspath(argv[argv.index("--root") + 1])
    quiet = "--quiet" in argv
    inc = os.path.join(root, "MQL5", "Include")

    total_e = total_w = 0
    types = {}
    reported = set()                                # a shared .mqh is in 2 units
    if not quiet:
        print("=" * 74)
        print(" MQL5 DIALECT RULES D1-D14  root: %s" % root)
        print("=" * 74)
    for label, relp in UNITS:
        path = os.path.join(root, relp)
        if not os.path.isfile(path):
            print("  skip  %-38s (%s missing)" % (label, relp))
            continue
        files = closure(path, inc)
        errs, warns, types = check_unit(files, types, root)
        fresh_e = [e for e in errs if e not in reported]
        fresh_w = [w for w in warns if w not in reported]
        reported.update(fresh_e)
        reported.update(fresh_w)
        if fresh_e or fresh_w or not quiet:
            print("  unit  %-38s %d file(s)" % (label, len(files)))
        for e in fresh_e:
            print("    ERROR " + e)
        for w in fresh_w:
            print("    WARN  " + w)
        total_e += len(fresh_e)
        total_w += len(fresh_w)
    # every .mqh that no unit includes is dead code
    incdir = os.path.join(inc, "QSMC")
    used = set()
    for _, relp in UNITS:
        p = os.path.join(root, relp)
        if os.path.isfile(p):
            used |= {os.path.basename(x) for x in closure(p, inc)}
    if os.path.isdir(incdir):
        for f in sorted(os.listdir(incdir)):
            if f.endswith(".mqh") and f not in used and not quiet:
                print("  WARN  %s is included by nobody - dead module" % f)
    print("-" * 74)
    if total_e:
        print("  %d dialect error(s), %d warning(s)" % (total_e, total_w))
        return 1
    print("  no dialect errors, %d warning(s) - now press F7 in MetaEditor" % total_w)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
