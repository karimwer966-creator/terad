#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BUFFER CONTRACT - the indicator and the EA agree about what a buffer means.

WHY THIS FILE EXISTS
--------------------
`nadir2.mq5` and `MQL5/Experts/QSMC_AutoTrader.mq5` share almost no code. What
they share is 27 `double` arrays addressed by integer index. The contract
between the two products is therefore a list of numbers, and it lived in three
places that nothing compared:

  * `SetIndexBuffer(i, BufName, KIND)` in the indicator's OnInit
  * `#define QSMC_BUF_<NAME> <i>` in the EA
  * prose, in whichever document happened to mention it

Renumbering a buffer, or adding one in the middle, produces no compile error on
either side. The EA simply reads a different number and trades it. `iCustom`
hands back a handle; `CopyBuffer` hands back doubles; nothing anywhere says
"index 9 used to be the stop and is now the first target".

`docs/BUFFER_CONTRACT.md` is the written contract. This suite is the reason it
stays true: it parses the source on both sides and the document in the middle,
and fails if any two of the three disagree - in either direction. A source
change without a table change fails; a table change without a source change
fails too.

WHAT IT CHECKS
--------------
  B1  the indicator declares `indicator_buffers N` and really calls
      SetIndexBuffer for 0..N-1, once each, no gaps and no duplicates.
  B2  the shipped mirror `MQL5/Indicators/nadir2.mq5` declares the same block.
  B3  the document has exactly one row per index 0..N-1, and each row names the
      same buffer array the source binds to that index.
  B4  the document's plot column matches `indicator_plots` (0..P-1 plotted, the
      rest hidden).
  B5  the set of indices the document marks "EA reads" is exactly the set of
      `#define QSMC_BUF_*` numbers in the EA, and each row names the real macro.
  B6  every EA macro points at an index that exists, and no macro is duplicated
      or orphaned.
  B7  the two facts that are easy to get wrong are stated: buffers 13-18 are
      never executed (the EA never trades ZRE), and buffer 26 is a label, not a
      gate - a CONTINUATION signal executes through buffer 7.
  B8  the zeroing path covers the newest buffer, so a purged bar cannot keep a
      stale value.

This is a source contract. It is not a MetaEditor compile and not a backtest.
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NADIR = os.path.join(ROOT, "nadir2.mq5")
MIRROR = os.path.join(ROOT, "MQL5", "Indicators", "nadir2.mq5")
EA = os.path.join(ROOT, "MQL5", "Experts", "QSMC_AutoTrader.mq5")
DOC = os.path.join(ROOT, "docs", "BUFFER_CONTRACT.md")

CHECKS = [0]
FAILURES = []


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("PASS  " + label)
    else:
        print("FAIL  " + label)
        FAILURES.append(label)


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


# ---------------------------------------------------------------- source side
def parse_setindexbuffer(text):
    """index -> (array name, kind), in file order."""
    out = {}
    order = []
    for m in re.finditer(r"SetIndexBuffer\(\s*(\d+)\s*,\s*([A-Za-z_]\w*)\s*,\s*([A-Z_]+)\s*\)",
                         text):
        i = int(m.group(1))
        out[i] = (m.group(2), m.group(3))
        order.append(i)
    return out, order


def parse_property(text, key):
    m = re.search(r"#property\s+%s\s+(\d+)" % re.escape(key), text)
    return int(m.group(1)) if m else None


src = read(NADIR)
bufs, order = parse_setindexbuffer(src)
declared = parse_property(src, "indicator_buffers")
plots = parse_property(src, "indicator_plots")

check(declared is not None, "B1 the indicator declares #property indicator_buffers")
check(plots is not None, "B1 the indicator declares #property indicator_plots")

check(len(order) == len(bufs),
      "B1 no index is bound twice (%d calls, %d distinct indices)" % (len(order), len(bufs)))
check(declared is not None and len(bufs) == declared,
      "B1 SetIndexBuffer is called for exactly indicator_buffers=%s indices (found %d)"
      % (declared, len(bufs)))
check(declared is not None and sorted(bufs) == list(range(declared)),
      "B1 indices are contiguous 0..%s with no gap" % ((declared - 1) if declared else "?"))

kinds = {i: k for i, (_, k) in bufs.items()}
plotted = [i for i in sorted(bufs) if kinds[i] == "INDICATOR_DATA"]
calc = [i for i in sorted(bufs) if kinds[i] == "INDICATOR_CALCULATIONS"]
check(len(plotted) == (plots or -1),
      "B1 exactly indicator_plots=%s buffers are INDICATOR_DATA (found %d)" % (plots, len(plotted)))
check(plotted == list(range(len(plotted))),
      "B1 the plotted buffers are the first %d indices" % len(plotted))

# ------------------------------------------------------------------- mirror
if os.path.isfile(MIRROR):
    mbufs, _ = parse_setindexbuffer(read(MIRROR))
    check(mbufs == bufs,
          "B2 the shipped mirror binds the same %d indices to the same arrays" % len(bufs))
    check(parse_property(read(MIRROR), "indicator_buffers") == declared,
          "B2 the mirror declares the same indicator_buffers")
else:
    check(False, "B2 the shipped mirror MQL5/Indicators/nadir2.mq5 exists")

# ----------------------------------------------------------------- EA side
ea = read(EA)
defines = {}
for m in re.finditer(r"#define\s+(QSMC_BUF_[A-Z0-9_]+)\s+(\d+)\b", ea):
    defines[m.group(1)] = int(m.group(2))

check(len(defines) > 0, "B6 the EA declares QSMC_BUF_* macros (%d found)" % len(defines))
nums = sorted(defines.values())
check(len(nums) == len(set(nums)),
      "B6 no two QSMC_BUF_* macros point at the same index")
bad = [n for n, i in defines.items() if i not in bufs]
check(not bad,
      "B6 every QSMC_BUF_* macro points at an index the indicator binds (%s)"
      % (", ".join(bad) if bad else "all %d resolve" % len(defines)))
by_index = {}
for n, i in defines.items():
    by_index[i] = n

# --------------------------------------------------------------- doc side
doc = read(DOC)
rows = {}
for line in doc.split("\n"):
    if not line.startswith("| "):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 6 or not re.fullmatch(r"\d+", cells[0]):
        continue
    idx = int(cells[0])
    array = cells[1].strip("`")
    plotcell = cells[2]
    eacell = cells[3]
    rows[idx] = {"array": array, "plot": plotcell, "ea": eacell}

check(len(rows) > 0, "B3 the document has a parseable buffer table (%d rows)" % len(rows))
check(set(rows) == set(bufs),
      "B3 the table covers exactly indices 0..%d, once each" % (max(bufs) if bufs else -1))

mismatch = [i for i in sorted(set(rows) & set(bufs)) if rows[i]["array"] != bufs[i][0]]
check(not mismatch,
      "B3 every row names the array the source binds to that index (%s)"
      % (", ".join("idx %d says %s, source says %s" % (i, rows[i]["array"], bufs[i][0])
                   for i in mismatch) if mismatch else "all %d agree" % len(rows)))

for i in sorted(set(rows) & set(bufs)):
    plotted_row = not rows[i]["plot"].startswith("\u2014")
    check(plotted_row == (kinds[i] == "INDICATOR_DATA"),
          "B4 index %d plot column matches %s" % (i, kinds[i]))

# B5 - the EA-read column is exactly the macro set, both directions
doc_read = set()
doc_macro = {}
for i, r in rows.items():
    m = re.search(r"`(QSMC_BUF_[A-Z0-9_]+)`", r["ea"])
    if m:
        doc_read.add(i)
        doc_macro[i] = m.group(1)
    else:
        check(not r["ea"].lower().startswith("yes"),
              "B5 index %d is marked 'EA reads' and names the macro it reads" % i)

check(doc_read == set(by_index),
      "B5 the table's EA-read set equals the EA's QSMC_BUF_* set (doc %s / source %s)"
      % (sorted(doc_read), sorted(by_index)))
wrong_macro = [i for i in doc_read if doc_macro.get(i) != by_index.get(i)]
check(not wrong_macro,
      "B5 each EA-read row names the macro the EA actually defines (%s)"
      % (", ".join("idx %d: doc %s, source %s" % (i, doc_macro.get(i), by_index.get(i))
                   for i in wrong_macro) if wrong_macro else "all %d agree" % len(doc_read)))

# B7 - the two facts that are easy to get wrong
zre = [i for i in sorted(bufs) if bufs[i][0].startswith("BufSigZRE")
       and bufs[i][0] != "BufSigZREVerdict"]
check(all(i not in by_index for i in zre),
      "B7 the EA reads none of the ZRE trade buffers %s (it never executes ZRE)" % zre)
chain = [i for i in sorted(bufs) if bufs[i][0] == "BufSigCoreChain"]
check(len(chain) == 1, "B7 exactly one chain-kind buffer exists (%s)" % chain)
if chain:
    ci = chain[0]
    check(ci not in by_index,
          "B7 buffer %d (BufSigCoreChain) is NOT read by the EA - it is a label, not a gate" % ci)
    check("label, not a gate" in doc,
          "B7 the document states buffer %d is a label, not a gate" % ci)
    check("CONTINUATION" in doc and "BufSigCoreDir" in doc,
          "B7 the document says a CONTINUATION signal executes through the CORE direction buffer")

# B8 - the purge path zeroes every calculation buffer's array
zero_body = ""
m = re.search(r"void\s+SigLog_BufZero\s*\([^)]*\)\s*\{", src)
if m:
    k = src.find("{", m.start())
    depth = 0
    for p in range(k, len(src)):
        if src[p] == "{":
            depth += 1
        elif src[p] == "}":
            depth -= 1
            if depth == 0:
                zero_body = src[k:p + 1]
                break
check(zero_body != "", "B8 SigLog_BufZero() exists")
for fn, what in (("SigLog_BufWrite(", "7-18"), ("SigLog_BufWriteClass(", "21-25"),
                 ("SigLog_BufWriteChain(", "26")):
    check(fn in zero_body,
          "B8 the purge path zeroes buffers %s via %s" % (what, fn.rstrip("(")))
newest = max(bufs)
check(bufs[newest][0] in zero_body or "SigLog_BufWriteChain(" in zero_body,
      "B8 the newest buffer (%d, %s) is covered by the purge path"
      % (newest, bufs[newest][0]))

print("=" * 60)
print("buffer-contract checks: %d checks, failures: %d" % (CHECKS[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  failed: " + f)
    raise SystemExit(1)
print("docs/BUFFER_CONTRACT.md and the source agree on all %d buffers." % len(bufs))
print("Source contract only: NOT a MetaEditor compile, NOT a backtest.")
