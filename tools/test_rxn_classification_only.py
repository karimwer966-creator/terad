#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RXN CLASSIFICATION-ONLY - the contract at nadir2.mq5:40185, made checkable.

WHY THIS EXISTS
---------------
The v6.5.0 Reaction Signal Layer opens with a promise:

    // CLASSIFICATION ONLY. RXN never creates, mutates, invalidates, confirms or
    // authorizes a setup, and contains no trading function of any kind.

Before this suite existed, **no offline check contained the string
"CLASSIFICATION ONLY"**. The promise was prose in a 46,847-line file: 65 RXN_*
functions, ~2,826 lines, and nothing that would notice if one of them grew an
OrderSend, or wrote a signal buffer, or started feeding the resolver.

This is the source contract for that promise. It is not a MetaEditor compile and
not a backtest.

WHAT IT CHECKS
--------------
  X1  the contract comment is where it says it is, and still says it.
  X2  no RXN_* body contains a trading, order, position or account API.
  X3  no RXN_* body writes a signal buffer (BufSig*).
  X4  no RXN_* body writes authoritative signal state (g_final_signal,
      g_res_score, SigLog_Buf*, MarkCoreEntry).
  X5  the set of non-RXN functions that touch any g_rxn_* global is EXACTLY the
      enumerated set, with each one's read-site count pinned. A new reader of
      RXN state fails here even if it is harmless, because "harmless" is the
      claim under test.
  X6  g_rxn_extra_zones - the one RXN-named global that reaches a publication
      gate - is filled by ZRE_Update from ZRE-dropped zones, NOT by RXN's own
      classifier. RXN classifies it; RXN does not supply it.
  X7  the one path from RXN classification into a vote is named, weighted, and
      behind a switch that defaults to false; and g_final_signal reaches only
      the journal and the dashboard, never the order path.
  X8  the room leg of the weighted gate is the only place RXN-named state can
      move a publication decision, and the pin says so.
  X9  no g_rxn_* global is reachable from the EA: none of them is exported
      through a buffer the companion reads.

Two of these (X7, X8) exist because the honest answer is not "RXN touches
nothing". It touches two things, both enumerable, and an enumerable exception is
a contract while an unexamined one is a hope.
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "nadir2.mq5")
EA = os.path.join(ROOT, "MQL5", "Experts", "QSMC_AutoTrader.mq5")
DOC = os.path.join(ROOT, "docs", "KLJ_V6.5.0_REACTION_LAYER_AUDIT.md")

COUNT = [0]
FAILURES = []


def check(cond, label, detail=""):
    COUNT[0] += 1
    if cond:
        print("PASS %s" % label)
    else:
        print("FAIL %s%s" % (label, ("  -> " + detail) if detail else ""))
        FAILURES.append(label)


raw = io.open(SRC, encoding="utf-8", newline="").read()
CRLF = "\r\n" in raw
text = raw.replace("\r\n", "\n")
lines = text.split("\n")

# --------------------------------------------------------------- functions
SIG = re.compile(r"^(?!//)(?:[A-Za-z_][\w]*\s+)+?([A-Za-z_]\w*)\s*\(")


def parse_functions():
    """name -> (first_line, last_line, body), brace-matched from the body '{'.

    The signature may span several lines, so the scan walks forward to the '{'
    or the ';' instead of requiring the whole signature on one line. This
    matters for the checks below: a single-line-signature parser found only 65
    of the 85 RXN_* definitions, which means X2/X3/X4 would have declared the
    layer clean while never reading a fifth of it.
    """
    out = {}
    i = 0
    while i < len(lines):
        m = SIG.match(lines[i])
        if m:
            j = i
            opened = None
            # 24, not 8: RXN_Classify's signature runs 9 lines before its '{',
            # and an 8-line window silently dropped it - which would have left
            # the layer's own decision core unscanned by X2, X3 and X4.
            while j < len(lines) and j < i + 24:
                if "{" in lines[j]:
                    opened = j
                    break
                if ";" in lines[j]:
                    break
                j += 1
            if opened is not None:
                depth = 0
                k = opened
                while k < len(lines):
                    depth += lines[k].count("{") - lines[k].count("}")
                    if depth == 0:
                        break
                    k += 1
                out[m.group(1)] = (i + 1, k + 1, "\n".join(lines[i:k + 1]))
                i = k + 1
                continue
        i += 1
    return out


FUNCS = parse_functions()
RXN = {k: v for k, v in FUNCS.items() if k.startswith("RXN_")}

check(len(FUNCS) > 800, "X0 brace-matched %d functions in nadir2.mq5" % len(FUNCS),
      "%d" % len(FUNCS))
check(len(RXN) == 86, "X0 the RXN layer is %d definitions, all of them scanned"
      % len(RXN), "%d - the parser missed a multi-line signature" % len(RXN))
check("RXN_Classify" in RXN,
      "X0 RXN_Classify is in the scanned set - it is the layer's decision core, "
      "so a parser that drops it invalidates every check below")
check(CRLF, "X0 nadir2.mq5 is still CRLF (an edit here must not normalise it)")

# ------------------------------------------------- X1 the contract comment
PIN = 40185
check(PIN <= len(lines), "X1 the pinned line exists", "%d lines" % len(lines))
at = lines[PIN - 1] if PIN <= len(lines) else ""
check("CLASSIFICATION ONLY" in at,
      "X1 nadir2.mq5:%d is the CLASSIFICATION ONLY line" % PIN, repr(at[:90]))
window = "\n".join(lines[PIN - 1:PIN + 2])
for phrase in ("never creates", "mutates", "invalidates", "confirms or",
               "authorizes a setup", "no trading function of any kind"):
    check(phrase in window, "X1 the contract still says %r" % phrase)

# The comment also names the audit doc. That citation must resolve.
check("docs/KLJ_V6.5.0_REACTION_LAYER_AUDIT.md" in "\n".join(lines[PIN - 1:PIN + 6]),
      "X1 the comment cites its audit document")
check(os.path.isfile(DOC), "X1 that audit document exists in the checkout")

# --------------------------------------- X2 no trading API inside RXN_*
TRADE = re.compile(
    r"\b(OrderSend|OrderClose|OrderCloseBy|OrderDelete|OrderModify|OrderCheck|"
    r"PositionClose|PositionCloseBy|PositionModify|PositionOpen|PositionSelect|"
    r"CTrade|trade\s*\.\s*(Buy|Sell|BuyLimit|SellLimit|BuyStop|SellStop|"
    r"PositionClose|PositionModify)|AccountInfoDouble|AccountInfoInteger|"
    r"AccountInfoString|HistoryDeal|GlobalVariableSet)\b")

hits = sorted(k for k, v in RXN.items() if TRADE.search(v[2]))
check(not hits, "X2 no RXN_* function calls a trading/order/position API",
      "%s" % hits[:6])

# ------------------------------------------- X3 no signal-buffer write
BUF = re.compile(r"\bBufSig[A-Za-z0-9_]*\s*(\[[^\]]*\])?\s*=[^=]")
hits = sorted(k for k, v in RXN.items() if BUF.search(v[2]))
check(not hits, "X3 no RXN_* function writes a signal buffer", "%s" % hits[:6])

# any read of a buffer is also out of scope for a classifier
BUFANY = re.compile(r"\bBufSig[A-Za-z0-9_]*\b")
hits = sorted(k for k, v in RXN.items() if BUFANY.search(v[2]))
check(not hits, "X3 no RXN_* function even names a signal buffer", "%s" % hits[:6])

# --------------------------------- X4 no authoritative signal-state write
AUTH = re.compile(
    r"\b(g_final_signal|g_final_why|g_res_score|g_res_why|g_qa_core)\b\s*=[^=]"
    r"|\bMarkCoreEntry\s*\(|\bSigLog_Buf(Write|Class|Chain|Register|Update)\s*\(")
hits = sorted(k for k, v in RXN.items() if AUTH.search(v[2]))
check(not hits, "X4 no RXN_* function writes authoritative signal state",
      "%s" % hits[:6])

# ------------------------------- X5 the exhaustive reader set, pinned
READERS = {
    # function: (expected read sites of any g_rxn_* global, what it is for)
    "ResolveFinalSignal":      (1, "the resolver's reaction vote"),
    "ScenarioRxnForZone":      (2, "scenario tooltip"),
    "ScenarioEvaluateM30M15":  (1, "scenario tooltip"),
    "ScenarioDiscover":        (4, "scenario tooltip"),
    "DrawQuantumDashboard":    (3, "dashboard tooltip"),
    "ZRE_Update":              (3, "PRODUCER of g_rxn_extra_zones, see X6"),
    "AlertOpposingRoomATR":    (2, "the weighted gate's room leg, see X8"),
}
actual = {}
for k, (a, b, body) in FUNCS.items():
    if k.startswith("RXN_"):
        continue
    n = sum(1 for ln in body.split("\n") if "g_rxn_" in ln)
    if n:
        actual[k] = n

check(sorted(actual) == sorted(READERS),
      "X5 the non-RXN functions touching g_rxn_* are exactly the %d enumerated"
      % len(READERS),
      "extra %s / missing %s" % (sorted(set(actual) - set(READERS)),
                                 sorted(set(READERS) - set(actual))))
for fn, (want, why) in sorted(READERS.items()):
    got = actual.get(fn, 0)
    check(got == want, "X5 %s reads g_rxn_* at %d site(s) - %s" % (fn, want, why),
          "%d" % got)

# --------------------- X6 g_rxn_extra_zones comes from ZRE, not from RXN
zu = FUNCS.get("ZRE_Update")
check(zu is not None, "X6 ZRE_Update exists")
if zu:
    body = zu[2]
    check("ArrayResize(g_rxn_extra_zones,nd+nt)" in body,
          "X6 ZRE_Update sizes g_rxn_extra_zones itself")
    check("g_rxn_extra_zones[i]=zre_dropped[i]" in body
          and "g_rxn_extra_zones[nd+i]=zre_tail[i]" in body,
          "X6 and fills it from ZRE-dropped and ZRE-tail zones")
# RXN may REORDER and TRUNCATE that array, but it may not supply a zone. An
# earlier draft of this check asserted "no RXN_* function writes
# g_rxn_extra_zones" and failed on RXN_RankExtra and RXN_Clear, which was the
# check being wrong rather than the source: RXN_RankExtra (:43576) is a pure
# insertion sort over the array ZRE filled, and RXN_Clear (:43997) truncates it
# to zero. So the contract is stated as what it actually is - every element RXN
# assigns must come from the array itself.
EXTRA = "g_rxn_extra_zones"
suppliers = []
for k, (a, b, body) in sorted(RXN.items()):
    for ln in body.split("\n"):
        m = re.search(r"\bg_rxn_extra_zones\s*\[[^\]]*\]\s*=\s*(.+?);", ln)
        if not m:
            continue
        rhs = m.group(1)
        if EXTRA not in rhs and not re.match(r"^key$", rhs.strip()):
            suppliers.append((k, a, ln.strip()[:80]))
check(not suppliers,
      "X6 every g_rxn_extra_zones element RXN assigns comes from the array "
      "itself - RXN re-ranks zones ZRE dropped, it never supplies one",
      "%s" % suppliers[:4])

rank = FUNCS.get("RXN_RankExtra")
check(rank is not None and "RXN_ZoneBefore" in rank[2]
      and "p.max_zone_extra" in rank[2],
      "X6 RXN_RankExtra is the bounded sort that keeps the set capped")
clr = FUNCS.get("RXN_Clear")
check(clr is not None and "ArrayResize(g_rxn_extra_zones,0)" in clr[2],
      "X6 RXN_Clear is the only other writer, and it empties the array")

# ------------- X7 the resolver path: named, weighted, default OFF, inert
rfs = FUNCS.get("ResolveFinalSignal")
check(rfs is not None, "X7 ResolveFinalSignal exists")
if rfs:
    ln = [l for l in rfs[2].split("\n") if "g_rxn_best_buy" in l]
    check(len(ln) == 1, "X7 the resolver reads RXN at exactly one site",
          "%d" % len(ln))
    check("g_rxn_built_time==g_buf_t[closed]" in ln[0]
          and "RXN_LEVEL_REACTION" in ln[0],
          "X7 and only on the same closed bar, at REACTION level or above",
          ln[0].strip()[:100] if ln else "")

decl = [i + 1 for i, l in enumerate(lines)
        if re.match(r"^input\s+bool\s+InpUseFinalResolver\s*=", l)]
check(len(decl) == 1, "X7 InpUseFinalResolver is declared once", "%s" % decl)
if decl:
    check("= false" in lines[decl[0] - 1],
          "X7 InpUseFinalResolver defaults to false at :%d" % decl[0],
          lines[decl[0] - 1].strip()[:90])
wdecl = [i + 1 for i, l in enumerate(lines)
         if re.match(r"^input\s+int\s+InpResWeightReaction\s*=", l)]
check(len(wdecl) == 1 and "= 30" in lines[wdecl[0] - 1],
      "X7 the reaction vote carries weight 30 at :%s" % wdecl,
      "%s" % wdecl)

# g_final_signal must reach the journal and the dashboard, never an order
fsites = [i + 1 for i, l in enumerate(lines) if "g_final_signal" in l]
check(len(fsites) > 0, "X7 g_final_signal is referenced (%d sites)" % len(fsites))
orderish = [n for n in fsites
            if re.search(r"OrderSend|trade\s*\.|PositionOpen|HandleSignal|"
                         r"OpenPosition|PlaceOrder", lines[n - 1])]
check(not orderish,
      "X7 no g_final_signal site sits on an order call", "%s" % orderish[:6])
check(any("r.final_signal=" in lines[n - 1] for n in fsites),
      "X7 g_final_signal reaches the decision journal")
check(any("status=" in lines[n - 1] for n in fsites),
      "X7 g_final_signal reaches the dashboard status text")

# ------------------- X8 the room leg is the only publication-relevant path
aro = FUNCS.get("AlertOpposingRoomATR")
check(aro is not None, "X8 AlertOpposingRoomATR exists")
if aro:
    check("g_rxn_extra_zones" in aro[2],
          "X8 AlertOpposingRoomATR scans g_rxn_extra_zones")
    check("ZRE_RESISTANCE" in aro[2] and "ZRE_SUPPORT" in aro[2],
          "X8 and it reads each zone's ZRE side, not an RXN level")
room = [i + 1 for i, l in enumerate(lines)
        if "c.opposing_room_atr<0.0 || c.opposing_room_atr>=InpWGMinRoomATR" in l]
check(len(room) == 1,
      "X8 the weighted gate's room leg is the single consumer at :%s" % room,
      "%s" % room)
if room:
    check("got+=InpWGWeightRoom" in lines[room[0]],
          "X8 and it awards InpWGWeightRoom points")

# ------------------------- X9 no RXN global is reachable from the EA
ea = io.open(EA, encoding="utf-8", errors="replace").read()
check("g_rxn_" not in ea,
      "X9 QSMC_AutoTrader.mq5 contains no reference to any g_rxn_* global")
macros = sorted(set(re.findall(r"#define\s+(QSMC_BUF_\w+)\s+(\d+)", ea)))
check(len(macros) >= 13, "X9 the EA reads %d buffer macros" % len(macros),
      "%d" % len(macros))
# and none of those buffers is written by RXN
bufnums = set(int(n) for _, n in macros)
check(len(bufnums & {7, 8, 9, 10, 11, 12, 19, 20, 21, 22, 23, 24, 25}) == 13,
      "X9 the EA's buffer macros cover the 13 CORE/classification buffers")

# ------------------------------------------- X10 the doc stub is honest
stub = io.open(DOC, encoding="utf-8", errors="replace").read()
check("test_rxn_classification_only.py" in stub,
      "X10 the audit stub names this suite instead of claiming nothing asserts "
      "the contract")

print("")
print("=" * 74)
print("RXN CLASSIFICATION-ONLY checks: %d   failures: %d"
      % (COUNT[0], len(FAILURES)))
if FAILURES:
    print("")
    print("The RXN layer's promise is a source contract. If one of these moved,")
    print("either RXN grew a capability it must not have, or a new reader of")
    print("g_rxn_* appeared and has to be classified here on purpose.")
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("Source contract only: NOT a MetaEditor compile, NOT a backtest, and no")
print("claim about what RXN would have classified on any real bar.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
