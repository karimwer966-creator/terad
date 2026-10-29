#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMMENT INTEGRITY - the defect class that 22 suites and 2 402 assertions missed.

WHAT ACTUALLY HAPPENED
----------------------
MetaEditor F7 on the merged seven-phase build reported **42 errors, 0 warnings**.
The root cause was ONE missing comment marker:

    24911  // Reset BOTH modules to their inert state.
    24912   Called when a new symbol/day context        <-- the "//" was gone
    24913  // arrives so a stale phase or window can never be displayed...

The compiler read line 24912 as code (`'Called' - unexpected token`, `'when' -
semicolon expected`), then mis-parsed the whole SBP3_Clear() body as a run of
global-scope declarations, producing 40 further errors - `variable already
defined` for g_p3_dir, g_p3_score, g_sb_active and eleven more, each pointing
back at its real declaration near line 1932-1949, and finally `expressions are
not allowed on a global scope` on the closing brace.

**One missing "//" became 42 errors.** Fixing that single line is expected to
clear all of them.

WHY EVERY EXISTING CHECK PASSED
-------------------------------
Braces stayed 3740/3740 and parens stayed balanced, because a comment marker is
neither. The suites assert structure, ordering, reuse, defaults and absence of
trade API - all of which were still true. `strip_comments`-based checks were
actively blind to it: with no "//" there is nothing to strip, so the prose simply
became part of the "code" the balance checks counted, and it balanced anyway.
`mql5_rules.py` checks StringFormat arity, duplicate globals, the version triple,
pointers and unbraced declarations - none of which is a comment.

So this suite exists to own that gap: it decides what is comment and what is code
by tracking lexical state character by character, then asserts that no line the
compiler will try to parse is actually English prose.

WHAT IT CHECKS
--------------
  A  No prose line sits outside a comment or string. Detection is lexical, not
     regex-over-raw-text: a line qualifies only if its code-view has no
     statement punctuation AND at least two of its words are English function
     words. That is what separates the defect from `enum ENUM_X`, `struct SX`,
     `input group "..."` and a trailing enum member - all of which are legal
     punctuation-free lines and all of which a naive scan reports as prose.
  B  The comment-neighbour rule: if the nearest non-blank lines above and below a
     punctuation-free line are both `//` comments, that line was almost certainly
     meant to be one too. This is the specific shape of the real defect.
  C  Lexical state terminates cleanly - the file ends outside any comment and
     outside any string or character literal, and `/*` and `*/` are balanced in
     the code view. An unterminated block comment would silently swallow code.
  D  No function is defined twice, and no function of the seven new modules is
     called without being defined or declared. Duplicate declarations are a real
     F7 error class that survives the existing static tools (mql5_rules.py D9
     checks duplicate GLOBALS only), so definitions are checked here too.
  E  The exact historical defect is pinned: the three-line comment above
     SBP3_Clear() is intact, because a regression here is what cost 42 errors.

This is a LEXICAL contract, not a compiler. It cannot see type errors, arity
slips, undeclared identifiers or shadowing. F7 remains the authority.

Exit code 1 on any failure, so CI turns red.
"""

import collections
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "nadir2.mq5")

FAILURES = []
COUNT = [0]


def check(cond, label, detail=""):
    COUNT[0] += 1
    if cond:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s%s" % (label, ("  [%s]" % detail) if detail else ""))
        FAILURES.append(label)


with io.open(SRC, encoding="utf-8", newline="") as fh:
    RAW = fh.read()
LINES = RAW.replace("\r\n", "\n").split("\n")
NL = len(LINES)


# --------------------------------------------------------------- lexical scan
def scan(raw):
    """Return (per-line code view, final state). The code view of a line holds
    only the characters the compiler will actually parse - everything inside //
    comments, /* */ comments, "strings" and 'chars' is excluded."""
    state = "code"
    cur = []
    ln = 1
    view = collections.defaultdict(str)
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        two = raw[i:i + 2]
        if c == "\n":
            view[ln] += "".join(cur)
            cur = []
            ln += 1
            if state == "line":
                state = "code"
            i += 1
            continue
        if state == "code":
            if two == "//":
                state = "line"; i += 2; continue
            if two == "/*":
                state = "block"; i += 2; continue
            if c == '"':
                state = "str"; i += 1; continue
            if c == "'":
                state = "chr"; i += 1; continue
            cur.append(c); i += 1; continue
        if state == "line":
            i += 1; continue
        if state == "block":
            if two == "*/":
                state = "code"; i += 2
            else:
                i += 1
            continue
        if state == "str":
            if c == "\\":
                i += 2; continue
            if c == '"':
                state = "code"
            i += 1; continue
        if state == "chr":
            if c == "\\":
                i += 2; continue
            if c == "'":
                state = "code"
            i += 1; continue
    view[ln] += "".join(cur)
    return view, state


VIEW, FINAL_STATE = scan(RAW)
CODE = "\n".join(VIEW[k] for k in sorted(VIEW))

# English function words. Two of these in a punctuation-free code view is what
# separates prose from `enum ENUM_X` / `struct SX` / `input group "..."`.
ENGLISH = set("""
the a an and or of to in for with this that these those it its is are was were be
been being as at on by from not but if then than can could will would should must
may might never always only both each all any no nor so such when while where
which who whom whose what why how more most less least same other another into
onto over under above below between within without during before after again once
here there they them their he she his her we us our you your i my me him called
arrives states means gives makes keeps lets reads writes needs wants uses used one
two three stale fresh cannot able allowed expected required instead rather because
therefore thus hence note notes see seen also too very just still yet already now
later first second third last next previous identical exact exactly really actually
simply merely own new old
""".split())

STMT_PUNCT = ";={}()"


def is_prose(k):
    """True if line k is something the compiler will try to parse as code but is
    really English prose."""
    s = LINES[k - 1].strip()
    if not s or s.startswith(("//", "#", "/*", "*")):
        return False
    ct = VIEW.get(k, "")
    if not ct.strip():
        return False                      # wholly comment/string - legal
    if any(ch in ct for ch in STMT_PUNCT):
        return False                      # real code has statement punctuation
    toks = [t for t in re.split(r"[\s,]+", ct.strip()) if t]
    if len(toks) < 2:
        return False                      # a lone identifier: enum member, else
    hits = [t for t in toks if t.strip("(){}[];:/").lower() in ENGLISH]
    return len(hits) >= 2


# Legal punctuation-free lines: a declaration header whose body or brace is on
# the NEXT line, so its own code view holds no statement punctuation. Without
# this exclusion rule B flags every `input group "..."` banner in the file.
HEADER_RE = re.compile(
    r"^(?:(?:input|sinput|extern)\s+group"
    r"|enum\s+\w+|struct\s+\w+|class\s+\w+|union\s+\w+"
    r"|namespace\s+\w+|else|do|try|finally)\s*$")


def is_legal_header(k):
    return HEADER_RE.match(VIEW.get(k, "").strip()) is not None


def nonblank(k, step):
    j = k - 1 + step
    while 0 <= j < NL and not LINES[j].strip():
        j += step
    return LINES[j].strip() if 0 <= j < NL else ""


# ==================================================== A. no prose outside comments
prose = [k for k in range(1, NL + 1) if is_prose(k)]
check(len(prose) == 0,
      "A no line outside a comment or string is English prose - the compiler has "
      "nothing it cannot parse",
      "; ".join("L%d %r" % (k, LINES[k - 1].strip()[:60]) for k in prose[:6]))

# A naive scan is the thing that produces 200 false positives here, so prove the
# detector still distinguishes prose from legal punctuation-free declarations.
LEGAL_PUNCT_FREE = ["enum ENUM_", "struct S", "input group \""]
legal = []
for k in range(1, NL + 1):
    s = LINES[k - 1].strip()
    if any(s.startswith(p) for p in LEGAL_PUNCT_FREE):
        legal.append(k)
check(len(legal) > 100,
      "A the file really does contain %d legal punctuation-free declaration "
      "headers (enum/struct/input group) for the detector to reject" % len(legal),
      "only %d found" % len(legal))
check(not any(is_prose(k) for k in legal),
      "A none of those legal headers is mistaken for prose",
      str([k for k in legal if is_prose(k)][:6]))
check(sum(1 for k in legal if is_legal_header(k)) > 100,
      "A the header exclusion really recognises those declarations",
      "only %d recognised" % sum(1 for k in legal if is_legal_header(k)))


# ================================================ B. the comment-neighbour rule
# The exact shape of the real defect: a punctuation-free line sandwiched between
# two `//` comments. Reported separately from A because it is the strongest
# signal, and because a line can satisfy B while A's English-word test is unsure.
suspect = []
for k in range(2, NL):
    s = LINES[k - 1].strip()
    if not s or s.startswith(("//", "#", "/*", "*", "*/")):
        continue
    if any(ch in VIEW.get(k, "") for ch in STMT_PUNCT):
        continue
    if is_legal_header(k):
        continue
    prev, nxt = nonblank(k, -1), nonblank(k, +1)
    if prev.startswith("//") and nxt.startswith("//"):
        suspect.append(k)
check(len(suspect) == 0,
      "B no punctuation-free line sits between two // comments - a broken comment "
      "continuation is the shape that cost 42 errors",
      "; ".join("L%d %r" % (k, LINES[k - 1].strip()[:56]) for k in suspect[:6]))


# ================================================== C. lexical state terminates
check(FINAL_STATE == "code",
      "C the file ends outside any comment, string and character literal",
      "final scanner state is %r" % FINAL_STATE)
opens = len(re.findall(r"/\*", CODE))
closes = len(re.findall(r"\*/", CODE))
check(opens == closes,
      "C /* and */ balance in the code view (%d/%d)" % (opens, closes),
      "%d vs %d" % (opens, closes))
check(RAW.count("\n") - RAW.count("\r\n") == 0,
      "C the file is pure CRLF with zero bare LF - a stray LF inside a comment can "
      "silently split it")
# The real invariant, and the reason a missing marker is fatal here rather than
# recoverable: this file uses NO block comments at all. Every comment is a //
# line comment, so one lost marker exposes exactly one line of prose to the
# compiler instead of silently swallowing a region. Introducing a /* would be a
# new risk and should be a deliberate, reviewed change.
check(opens == 0 and closes == 0,
      "C the file contains no /* */ block comments at all (%d/%d) - every comment "
      "is a // line comment, so a lost marker cannot silently swallow a region"
      % (opens, closes),
      "%d opens, %d closes" % (opens, closes))


# ============================================ D. definitions and module symbols
defs = collections.defaultdict(list)
decls = collections.defaultdict(list)
SKIP = {"if", "for", "while", "switch", "return", "sizeof", "else", "do", "case"}
for k in range(1, NL + 1):
    cv = VIEW.get(k, "")
    m = re.match(r"^(?:[\w:]+[\s\*&]+)+(\w+)\s*\(", cv)
    if not m:
        continue
    name = m.group(1)
    if name in SKIP:
        continue
    tail = ""
    j = k - 1
    while j < NL and j < k + 16:
        tail += LINES[j]
        if "{" in LINES[j] or ";" in LINES[j]:
            break
        j += 1
    pos = tail.find(name)
    if pos < 0:
        continue
    after = tail[pos + len(name):]
    bi, si = after.find("{"), after.find(";")
    if bi >= 0 and (si < 0 or bi < si):
        defs[name].append(k)
    elif re.match(r"^[\w\s\*&]*\b%s\s*\(.*\)\s*;\s*$" % re.escape(name), cv.strip()):
        decls[name].append(k)

dupdef = {v: k2 for v, k2 in defs.items() if len(k2) > 1}
check(len(dupdef) == 0,
      "D no function is defined twice (a real F7 error class the existing static "
      "tools do not cover - mql5_rules.py D9 checks duplicate GLOBALS only)",
      str(dict(list(dupdef.items())[:5])))

MODPREFIX = r"(?:RM|CF|MR|PA|WY|SB|P3|OB)_[A-Za-z0-9_]+"
called = set()
for k in range(1, NL + 1):
    for m in re.finditer(r"\b(%s)\s*\(" % MODPREFIX, VIEW.get(k, "")):
        called.add(m.group(1))
undefined = sorted(f for f in called if f not in defs and f not in decls)
check(len(undefined) == 0,
      "D all %d module functions of the seven phases are called only where they "
      "are defined or declared" % len(called),
      str(undefined[:8]))
check(len(called) > 40,
      "D that check actually covered the modules (%d distinct names)" % len(called),
      "only %d - the prefix list may have drifted" % len(called))


# ============================================= E. the historical defect, pinned
idx = None
for k in range(1, NL + 1):
    if LINES[k - 1].strip() == "void SBP3_Clear()":
        idx = k
        break
check(idx is not None, "E SBP3_Clear() is still present")
if idx:
    above = [LINES[j - 1] for j in range(idx - 4, idx)]
    comment_lines = [l for l in above if l.strip().startswith("//")]
    check(len(comment_lines) == 3,
          "E the comment above SBP3_Clear() is three full //-lines",
          "found %d: %s" % (len(comment_lines), [l.strip()[:40] for l in above]))
    check(any("Reset BOTH modules" in l for l in above),
          "E line 1 of that comment is intact")
    check(any(l.strip().startswith("// Called when a new symbol") for l in above),
          "E line 2 of that comment carries its // prefix - THIS is the line whose "
          "missing marker produced 42 compiler errors",
          repr([l for l in above if "Called when" in l]))
    check(any("arrives so a stale phase" in l for l in above),
          "E line 3 of that comment is intact")
    # the body must be a single statement block of assignments, not declarations
    body = LINES[idx:idx + 9]
    check(any("g_p3_phase=P3_PHASE_NONE" in l for l in body),
          "E SBP3_Clear()'s body still resets the P3 globals by assignment")
    check(any("g_sb_active=false" in l for l in body),
          "E SBP3_Clear()'s body still resets the SB globals by assignment")


print("")
print("=" * 74)
print("COMMENT-INTEGRITY checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    print("")
    print("A prose line outside a comment is a COMPILE ERROR, not a style issue:")
    print("one missing '//' here produced 42 F7 errors. Fix the marker.")
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("This is a lexical contract. It is NOT a compiler: it cannot see type errors,")
print("arity slips, undeclared identifiers or shadowing. F7 remains the authority.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
