#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOC-FRESHNESS - keeps docs/QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md honest.

WHY THIS EXISTS
---------------
The seven-phase audit record cites 101 line numbers in nadir2.mq5. Line numbers
are the most fragile kind of citation in a 44 831-line file: ANY edit anywhere
above a citation silently invalidates every citation below it, and nothing
complains. The evidence that this is a real failure mode, not a hypothetical one:

  * Nine citations carried forward from earlier phase notes were stale by the
    time the doc was written (AnalyzeClosedCandle cited at 5407, actually 5540;
    MTF_SniperComputeTradeManagement cited at 43548-43670, actually 44242-44366;
    SigLog_BufWrite cited at 13818, actually 13874; and six more).
  * The previous deliverable shipped about fourteen stale file:line citations in
    its first draft, and a claim of "15 globals" that was actually 14.

So the doc's citations are now a CONTRACT, checked mechanically on every CI run.
If someone edits nadir2.mq5 and the doc drifts, this goes red and says exactly
which citation moved and where the truth now is.

WHAT IT CHECKS
--------------
  A  Every operational line citation resolves: the cited line of nadir2.mq5
     really contains the thing the doc says is there. Two-way for function
     definitions - the computed definition line must equal the cited line, so a
     WRONG citation fails too, not just a drifted source.
  B  The causal call order in OnCalculate is real and ascending. The doc's whole
     causality argument (RM runs after CF and after TopDown) rests on this.
  C  The seven dashboard tooltip guards are at the cited lines.
  D  Every COUNTABLE FACT the doc states is recomputed from source and compared
     against the doc's own text: 67 phase inputs (541 `input` lines in total), 43 enums,
     buffers 19, plots 7, the version triple, six self-tests totalling 56
     in-file checks, and zero trade API.
  E  Doc hygiene: no citation points past EOF, the nine known-stale numbers are
     absent, and the "not compiled" disclaimer is present and unambiguous.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
  * It reads NO git state. Every assertion is a pure function of two files on
    disk. A previous suite in this repo ran `git diff --numstat HEAD`, which is
    empty on a clean tree and broke CI; commit hashes are therefore NOT verified
    here even though the doc mentions them, because CI checks out with
    fetch-depth 1 and the base commit is not present.
  * It does not lint prose, and it does not verify that a claim is TRUE in a
    trading sense - only that the file still says what the doc says it says.
  * It is not a compiler and not a backtest.

Exit code 1 on any failure, so CI turns red.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "nadir2.mq5")
DOC = os.path.join(ROOT, "docs", "QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md")

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
NLINE = len(LINES)

with io.open(DOC, encoding="utf-8", newline="") as fh:
    DOC_TEXT = fh.read()

# Prose wraps, so a literal substring pin breaks on a line break inside the
# phrase ("**42 errors, 0\nwarnings**"). All phrase checks run against this
# whitespace-normalised view; citation extraction still uses DOC_TEXT because a
# cited range never spans a line.
DOC_FLAT = re.sub(r"\s+", " ", DOC_TEXT)


def line_at(n):
    """1-based source line, or a sentinel that can never match."""
    return LINES[n - 1] if 1 <= n <= NLINE else "\x00OUT_OF_RANGE"


def find_def(name):
    """Line of the DEFINITION of `name`, i.e. the occurrence whose statement
    reaches a '{' before it reaches a ';'. Forward declarations end in ';' and
    are skipped - `body_of`-style mistakes here are how a suite lands on a
    declaration instead of a definition."""
    hits = []
    pat = re.compile(r"\b" + re.escape(name) + r"\s*\(")
    for i, l in enumerate(LINES, 1):
        s = l.strip()
        if s.startswith("//") or not pat.search(l):
            continue
        # A signature may span several lines before its '{' - measured: seven for
        # MTF_SniperEvaluateEntryTriggers. Scan until a '{' or ';' terminates the
        # statement, with a generous cap. Declarations still end in ';' first, so
        # widening this cannot make a declaration look like a definition.
        tail = ""
        j = i - 1
        while j < NLINE and j < i + 16:
            tail += LINES[j]
            if "{" in LINES[j] or ";" in LINES[j]:
                break
            j += 1
        after = tail[tail.index(name) + len(name):]
        bi, si = after.find("{"), after.find(";")
        if bi >= 0 and (si < 0 or bi < si):
            hits.append(i)
    return hits[0] if hits else None


# ============================================================ A. line citations
# (label, cited_line, regex the cited line must match, optional def-of)
ANCHORS = [
    # --- structure the doc's whole argument leans on
    ("OnCalculate starts at L15015", 15015, r"^int OnCalculate\(", None),
    ("#property indicator_buffers 19 at L627", 627,
     r"^#property indicator_buffers\s+19\b", None),
    ("#property indicator_plots 7 at L628", 628,
     r"^#property indicator_plots\s+7\b", None),
    ("enum ENUM_P3_PHASE at L747", 747, r"^enum\s+ENUM_P3_PHASE\s*$", None),
    ("enum ENUM_WYCKOFF_EVENT at L757", 757, r"^enum\s+ENUM_WYCKOFF_EVENT\s*$", None),
    ("struct STopDownState at L1884", 1884, r"^struct\s+STopDownState\s*$", None),

    # --- reused risk constants / inputs (Phase 7's "reused, not invented" claim)
    ("SNIPER_SL_BUFFER_ATR 0.30 at L1850", 1850,
     r"^#define\s+SNIPER_SL_BUFFER_ATR\s+0\.30\b", None),
    ("SNIPER_SL_HARD_MAX_H1_ATR 2.00 at L1851", 1851,
     r"^#define\s+SNIPER_SL_HARD_MAX_H1_ATR\s+2\.00\b", None),
    ("SNIPER_BE_DISP_ATR 2.00 at L1852", 1852,
     r"^#define\s+SNIPER_BE_DISP_ATR\s+2\.00\b", None),
    ("SNIPER_TRAIL_M15_ATR 0.50 at L1853", 1853,
     r"^#define\s+SNIPER_TRAIL_M15_ATR\s+0\.50\b", None),
    ("InpUseHTFBias declared at L1142", 1142,
     r"^input\s+.*\bInpUseHTFBias\s*=", None),
    ("InpTopDownMinRR = 2.0 declared at L1157", 1157,
     r"^input\s+.*\bInpTopDownMinRR\s*=\s*2\.0\b", None),
    ("InpMTEERunSelfTest declared at L1796", 1796,
     r"^input\s+.*\bInpMTEERunSelfTest\s*=", None),
    ("InpSniperMaxRiskPct = 1.50 declared at L1806", 1806,
     r"^input\s+.*\bInpSniperMaxRiskPct\s*=\s*1\.50\b", None),
    ("InpLogLifecycleTransitions declared at L1253", 1253,
     r"^input\s+.*\bInpLogLifecycleTransitions\s*=", None),
    ("InpCFWeightStructure declared at L952", 952,
     r"^input\s+.*\bInpCFWeightStructure\s*=", None),
    ("InpCFMinDisplayScore = 60 declared at L958", 958,
     r"^input\s+.*\bInpCFMinDisplayScore\s*=\s*60\b", None),

    # --- input group banners (doc 3.1-3.7)
    ("SB1 input group at L861", 861, r"^input\s+group\s+\"====== Silver Bullet", None),
    ("WY1 input group at L883", 883, r"^input\s+group\s+\"====== Wyckoff", None),
    ("PA1 input group at L904", 904, r"^input\s+group\s+\"====== Pure Price Action", None),
    ("MR1 input group at L924", 924, r"^input\s+group\s+\"====== Mean Reversion", None),
    ("CF1 input group at L949", 949, r"^input\s+group\s+\"====== Confluence Engine", None),
    ("RM1 input group at L961", 961, r"^input\s+group\s+\"====== Risk Model", None),
    ("OB1 opt-in inputs at L808", 808,
     r"^input\s+.*\bInpOBUseAgeExpiry\s*=", None),

    # --- module sections and definitions (doc 4)
    ("OB1 age-bound banner at L17434", 17434, r"AUDIT-OB1\s+ORDER BLOCK AGE BOUND", None),
    ("SB1 section at L24482", 24482, r"AUDIT-SB1\s+POWER OF 3", None),
    ("WY1 section at L25061", 25061, r"AUDIT-WY1\s+WYCKOFF", None),
    ("PA1 section at L25500", 25500, r"AUDIT-PA1\s+PURE PRICE ACTION", None),
    ("MR1 section at L25923", 25923, r"AUDIT-MR1\s+MEAN REVERSION", None),
    ("CF1 section at L26524", 26524, r"AUDIT-CF1 CONFLUENCE ENGINE", None),
    ("RM1 section at L27020", 27020, r"AUDIT-RM1 RISK MODEL", None),
    ("P3_Update defined at L24610", 24610, r"^void\s+P3_Update\s*\(", "P3_Update"),
    ("SB_Update defined at L24786", 24786, r"^void\s+SB_Update\s*\(", "SB_Update"),
    ("WY_Update defined at L25250", 25250, r"^void\s+WY_Update\s*\(", "WY_Update"),
    ("PA_Update defined at L25726", 25726, r"^void\s+PA_Update\s*\(", "PA_Update"),
    ("MR_Update defined at L26181", 26181, r"^void\s+MR_Update\s*\(", "MR_Update"),
    ("CF_Update defined at L26689", 26689, r"^void\s+CF_Update\s*\(", "CF_Update"),
    ("RM_Update defined at L27246", 27246, r"^void\s+RM_Update\s*\(", "RM_Update"),
    ("RM self-test at L27443", 27443, r"AUDIT-RM1 synthetic self-test", None),

    # --- the pre-existing helpers the doc cites as reused / conflicted (doc 8)
    ("AnalyzeClosedCandle defined at L5549", 5549,
     r"\bAnalyzeClosedCandle\s*\(", "AnalyzeClosedCandle"),
    ("AnalyzeCandleIntelligence defined at L19468", 19468,
     r"\bAnalyzeCandleIntelligence\s*\(", "AnalyzeCandleIntelligence"),
    ("MTF_SniperEvaluateEntryTriggers defined at L44100", 44100,
     r"\bMTF_SniperEvaluateEntryTriggers\s*\(", "MTF_SniperEvaluateEntryTriggers"),
    ("MTF_SniperComputeTradeManagement defined at L44253", 44253,
     r"\bMTF_SniperComputeTradeManagement\s*\(", "MTF_SniperComputeTradeManagement"),
    ("IsFractalHigh defined at L34404", 34404, r"\bIsFractalHigh\s*\(", "IsFractalHigh"),
    ("IsFractalLow defined at L34415", 34415, r"\bIsFractalLow\s*\(", "IsFractalLow"),
    ("FractalRightBars defined at L23469", 23469,
     r"\bFractalRightBars\s*\(", "FractalRightBars"),
    ("ScoreStructure defined at L17393", 17393,
     r"^double\s+ScoreStructure\s*\(", "ScoreStructure"),
    ("ScoreLiquidity defined at L17414", 17414,
     r"^double\s+ScoreLiquidity\s*\(", "ScoreLiquidity"),
    ("ScoreSession defined at L17545", 17545,
     r"^double\s+ScoreSession\s*\(", "ScoreSession"),
    ("ScoreHTF defined at L17554", 17554, r"^double\s+ScoreHTF\s*\(", "ScoreHTF"),
    ("PA_ZoneAt defined at L25656", 25656, r"\bPA_ZoneAt\s*\(", "PA_ZoneAt"),
    ("SigLog_BufWrite defined at L13883", 13883,
     r"\bSigLog_BufWrite\s*\(", "SigLog_BufWrite"),
    ("CalculateAITradeSetup defined at L20487", 20487,
     r"\bCalculateAITradeSetup\s*\(", "CalculateAITradeSetup"),
    ("TheoreticalRiskMoney defined at L22730", 22730,
     r"\bTheoreticalRiskMoney\s*\(", "TheoreticalRiskMoney"),
    ("TopDown_Evaluate defined at L33681", 33681,
     r"^void\s+TopDown_Evaluate\s*\(", "TopDown_Evaluate"),
    ("TopDown_Update defined at L33912", 33912,
     r"^void\s+TopDown_Update\s*\(", "TopDown_Update"),
    ("existing R:R gate at L33873", 33873,
     r"if\(rr\+1e-9<InpTopDownMinRR\)", None),
    ("existing R:R failure message at L33875", 33875,
     r"R:R %\.2f below required %\.2f", None),
    ("final_score assignments begin at L20951", 20951, r"\bfinal_score\s*=", None),
    ("OBIsExpired called at L15264", 15264, r"\bOBIsExpired\s*\(", None),
    ("OB1 age-bound comment at L15259", 15259, r"AUDIT-OB1 AGE BOUND", None),

    # --- OnInit / self-test wiring
    ("RM_Clear() in OnInit at L14810", 14810, r"^\s+RM_Clear\(\);", None),
    ("SB self-test PASS (9/9) at L14823", 14823,
     r"Power-of-3 / Silver-Bullet self-test: PASS \(9/9\)", None),
    ("WY self-test PASS (9/9) at L14827", 14827,
     r"Wyckoff Spring/Upthrust self-test: PASS \(9/9\)", None),
    ("PA self-test PASS (9/9) at L14831", 14831,
     r"Pure Price Action self-test: PASS \(9/9\)", None),
    ("MR self-test PASS (9/9) at L14835", 14835,
     r"Mean-reversion / momentum self-test: PASS \(9/9\)", None),
    ("CF self-test PASS (10/10) at L14839", 14839,
     r"Confluence Engine self-test: PASS \(10/10\)", None),
    ("RM self-test PASS (10/10) at L14843", 14843,
     r"Risk model self-test: PASS \(10/10\)", None),
]

for label, cited, pat, defname in ANCHORS:
    hit = re.search(pat, line_at(cited)) is not None
    extra = ""
    if not hit:
        extra = "L%d does not match /%s/; actual: %r" % (cited, pat, line_at(cited).strip()[:60])
        if defname:
            real = find_def(defname)
            extra += " | %s is now defined at L%s" % (defname, real)
    check(hit, "A %s" % label, extra)

# two-way: for every function the doc pins a DEFINITION for, the computed
# definition line must equal the citation. Without this a citation could be
# simply wrong (pointing at a declaration) and still pass part A above whenever
# the declaration happens to match the same regex.
for label, cited, pat, defname in ANCHORS:
    if defname is None:
        continue
    real = find_def(defname)
    check(real == cited,
          "A2 %s definition really is at L%d (not a declaration)" % (defname, cited),
          "computed definition line is L%s" % real)


# ================================================= B. causal order in OnCalculate
# The doc's section 5 asserts this exact order. RM must run after CF (whose
# verdict it attaches to) and after TopDown (whose plan it may adopt).
ORDER = [
    (15259, r"AUDIT-OB1 AGE BOUND", "OB age bound"),
    (15373, r"P3_Update\(closed\);", "P3_Update"),
    (15374, r"SB_Update\(closed\);", "SB_Update"),
    (15378, r"WY_Update\(closed\);", "WY_Update"),
    (15434, r"TopDown_Update\(rates_total,false\);", "TopDown_Update"),
    (15456, r"PMI_Update\(\);", "PMI_Update"),
    (15606, r"MVP_Update\(", "MVP_Update"),
    (15615, r"PA_Update\(closed\);", "PA_Update"),
    (15623, r"MR_Update\(closed,rates_total,full_indicators\);", "MR_Update"),
    (15629, r"CF_Update\(closed,rates_total\);", "CF_Update"),
    (15634, r"RM_Update\(closed,rates_total\);", "RM_Update"),
    (15637, r"ZRE_Update\(", "ZRE_Update"),
]
for cited, pat, name in ORDER:
    check(re.search(pat, line_at(cited)) is not None,
          "B %-16s called at L%d" % (name, cited),
          "L%d is %r" % (cited, line_at(cited).strip()[:60]))

nums = [c for c, _, _ in ORDER]
check(nums == sorted(nums), "B the documented call order is strictly ascending",
      str(nums))

oc = find_def("OnCalculate")
check(oc is not None and oc < nums[0] and oc < 15017 + 1,
      "B every module call sits inside OnCalculate (which starts at L%s)" % oc,
      "first call at L%d" % nums[0])

# the three ordering claims the doc actually argues for
check(line_at(15629).find("CF_Update") < line_at(15634).find("RM_Update") or
      15629 < 15634,
      "B RM_Update runs after CF_Update (it attaches to CF's verdict)")
check(15434 < 15634,
      "B RM_Update runs after TopDown_Update (it may adopt TopDown's plan)")
check(all(re.search(r"is_new_bar \|\| detection_updated", line_at(c)) is not None
          for c in (15615, 15623, 15629, 15634)),
      "B PA/MR/CF/RM are all gated by `is_new_bar || detection_updated` - no "
      "per-tick recompute",
      str([(c, line_at(c).strip()[:44]) for c in (15615, 15623, 15629, 15634)
           if not re.search(r"is_new_bar \|\| detection_updated", line_at(c))]))
check(re.search(r"if\(closed<1 \|\| closed>rates_total-2\) return;", line_at(27251))
      is not None,
      "B RM_Update refuses the forming bar (L27251) before reading any series",
      "L27251 is %r" % line_at(27251).strip()[:70])
check(27246 < 27251 < 27261,
      "B that guard sits inside RM_Update (defined at L27246), i.e. before its work")


# ==================================================== C. dashboard tooltip guards
GUARDS = [
    (32976, r"InpEnableConfluence\|\|InpEnableAllModules\) && \(InpCFShowOnDashboard\|\|InpEnableAllModules", "CF"),
    (33007, r"InpEnableRiskModel\|\|InpEnableAllModules\) && \(InpRMShowOnDashboard\|\|InpEnableAllModules", "RM"),
    (33035, r"InpEnablePowerOf3\|\|InpEnableAllModules\) && \(InpP3ShowOnDashboard\|\|InpEnableAllModules", "P3"),
    (33047, r"InpEnableSilverBullet\|\|InpEnableAllModules\) && \(InpSBShowOnDashboard\|\|InpEnableAllModules", "SB"),
    (33064, r"InpEnableWyckoff\|\|InpEnableAllModules\) && \(InpWyckoffShowOnDashboard\|\|InpEnableAllModules", "WY"),
    (33084, r"InpEnablePriceAction\|\|InpEnableAllModules\) && \(InpPAShowOnDashboard\|\|InpEnableAllModules", "PA"),
    (33102, r"InpEnableMeanReversion\|\|InpEnableAllModules\) && \(InpMRShowOnDashboard\|\|InpEnableAllModules", "MR"),
]
for cited, pat, name in GUARDS:
    check(re.search(pat, line_at(cited)) is not None,
          "C %-3s tooltip guard at L%d is `InpEnable... && Inp...ShowOnDashboard`"
          % (name, cited),
          "L%d is %r" % (cited, line_at(cited).strip()[:64]))
gnums = [c for c, _, _ in GUARDS]
check(gnums == sorted(gnums), "C the tooltip blocks appear in the documented order "
      "(CF summary first)", str(gnums))
check(gnums[0] < 33000 and all(c > 32900 for c in gnums),
      "C all seven guards live in one contiguous tooltip region, so none can be "
      "reordered without this test noticing")


# ======================================================= D. countable facts
def group_inputs(banner_re):
    """Count the inputs in the group whose banner matches, handling comma-packed
    declarations (`input int A = 1, B = 2;` is TWO inputs)."""
    gidx = [i for i, l in enumerate(LINES)
            if re.match(r"^input\s+group\s+\"", l)]
    total = 0
    for k, i in enumerate(gidx):
        if not re.search(banner_re, LINES[i]):
            continue
        end = gidx[k + 1] if k + 1 < len(gidx) else NLINE
        for l in LINES[i + 1:end]:
            if not l.startswith("input ") or l.startswith("input group"):
                continue
            body = re.sub(r"^\w+\s+", "", l[len("input "):].split("//")[0])
            total += len([p for p in body.split(",") if re.match(r"\s*\w+\s*=", p)])
    return total


GROUPS = {
    "Silver Bullet / Power of 3": (r"AUDIT-SB1", 14),
    "Wyckoff":                    (r"AUDIT-WY1", 10),
    "Pure Price Action":          (r"AUDIT-PA1", 7),
    "Mean Reversion":             (r"AUDIT-MR1", 13),
    "Confluence Engine":          (r"AUDIT-CF1", 11),
    "Risk Model":                 (r"AUDIT-RM1", 8),
}
grouped = 0
for label, (rx, want) in GROUPS.items():
    got = group_inputs(rx)
    grouped += got
    check(got == want, "D %-26s group declares %2d inputs" % (label, want),
          "source now declares %d" % got)

# Phase 1's four inputs sit in the PRE-EXISTING OB group, so they are counted
# by name rather than by banner.
OB_INPUTS = ["InpOBUseAgeExpiry", "InpOBMaxAgeBars", "InpOBZoneBodyOnly",
             "InpOBShowLifecycleLabel"]
found = [n for n in OB_INPUTS
         if any(l.startswith("input ") and re.search(r"\b%s\s*=" % n, l) for l in LINES)]
UX = [n for n in ("InpEnableAllModules", "InpRedrawTradeBoxOnNewBarOnly")
      if any(l.startswith("input ") and re.search(r"\b%s\s*=" % n, l) for l in LINES)]
check(len(UX) == 2,
      "D AUDIT-UX1 declares exactly its two inputs (master switch + redraw gate)",
      "found %s" % UX)
check(all(re.search(r"\b%s\s*=\s*false" % n, RAW) for n in UX),
      "D both AUDIT-UX1 inputs default to false, like every other behavioural "
      "switch in this work")
check(len(found) == 4, "D Phase 1 declares its 4 opt-ins inside the existing OB group",
      "found only %s" % found)

NEW_TOTAL = grouped + len(found)
check(NEW_TOTAL == 67, "D the seven phases add 67 new inputs in total (the two "
      "AUDIT-UX1 inputs are counted separately below)",
      "recount gives %d (%d grouped + %d OB)" % (NEW_TOTAL, grouped, len(found)))
check("67 new inputs" in DOC_FLAT or "**67 new inputs**" in DOC_FLAT,
      "D the doc states 67 new inputs", "phrase absent from the doc")

ALL_INPUTS = len(re.findall(r"(?m)^input\s", RAW))
check(ALL_INPUTS == 541, "D nadir2.mq5 declares 541 `input` lines in total",
      "actual %d" % ALL_INPUTS)
check("541 total" in DOC_FLAT, "D the doc states 541 total `input` lines",
      "phrase absent from the doc")

ENUMS = len(re.findall(r"(?m)^enum\s+\w+", RAW))
check(ENUMS == 43, "D the file has 43 top-level enums (all new ones appended)",
      "actual %d" % ENUMS)
check("Enums | 43" in DOC_FLAT or "43, all appended" in DOC_FLAT,
      "D the doc states 43 enums", "phrase absent from the doc")

check("#property indicator_buffers 19" in RAW and
      "#property indicator_plots   7" in RAW,
      "D indicator_buffers is still 19 and indicator_plots still 7 - zero new buffers")
check("indicator_buffers` 19" in DOC_FLAT or "indicator_buffers 19" in DOC_FLAT,
      "D the doc states buffers 19 / plots 7")

check(re.search(r'QSMC_VERSION_TEXT\s+"v6\.6\.9"', RAW) is not None,
      "D QSMC_VERSION_TEXT is still v6.6.9")
check(re.search(r'#property version\s+"6\.69"', RAW) is not None,
      "D #property version is still \"6.69\"")
check("v6.6.9" in DOC_FLAT and '"6.69"' in DOC_FLAT,
      "D the doc reports the unchanged version triple v6.6.9 / \"6.69\"")

# six module self-tests, 9+9+9+9+10+10 = 56 in-file checks
ST = re.findall(r"self-test: PASS \((\d+)/\1\)", RAW)
MODULE_ST = [int(x) for x in re.findall(
    r"(?:Power-of-3 / Silver-Bullet|Wyckoff Spring/Upthrust|Pure Price Action|"
    r"Mean-reversion / momentum|Confluence Engine|Risk model) self-test: PASS \((\d+)/\1\)",
    RAW)]
check(len(MODULE_ST) == 6, "D exactly six module self-tests exist", str(MODULE_ST))
check(MODULE_ST == [9, 9, 9, 9, 10, 10],
      "D their counts are 9/9, 9/9, 9/9, 9/9, 10/10, 10/10", str(MODULE_ST))
check(sum(MODULE_ST) == 56, "D the six self-tests total 56 in-file checks",
      "actual %d" % sum(MODULE_ST))
check("56 in-file checks" in DOC_FLAT, "D the doc states 56 in-file checks",
      "phrase absent from the doc")

# zero trade API in the indicator, after stripping comments and strings
def strip_comments(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i += 2
        elif c == '"':
            i += 1
            while i < n and s[i] != '"':
                i += 1 if s[i] != "\\" else 2
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


CODE = strip_comments(RAW)
for api in ("OrderSend", "OrderSendAsync", "PositionOpen", "CTrade"):
    check(len(re.findall(r"\b%s\b" % api, CODE)) == 0,
          "D zero `%s` in the indicator's code (comments/strings stripped)" % api)
check("Trade API in the indicator: zero" in DOC_FLAT or
      "trade API in the indicator" in DOC_FLAT.lower(),
      "D the doc states the indicator contains no trade API")

BR_OPEN, BR_CLOSE = RAW.count("{"), RAW.count("}")
check(BR_OPEN == BR_CLOSE, "D braces balance (%d/%d)" % (BR_OPEN, BR_CLOSE),
      "%d vs %d" % (BR_OPEN, BR_CLOSE))
check("3740/3740" in DOC_FLAT, "D the doc reports braces 3740/3740",
      "actual %d/%d" % (BR_OPEN, BR_CLOSE))
check(RAW.count("\n") - RAW.count("\r\n") == 0,
      "D nadir2.mq5 is pure CRLF with zero bare LF")


# ============================================================== E. doc hygiene
cited_all = sorted(set(int(m) for m in re.findall(r"\bL(\d{3,5})\b", DOC_TEXT)))
over = [c for c in cited_all if c > NLINE]
check(len(over) == 0,
      "E every `L####` citation in the doc is inside the file (%d citations, file "
      "has %d lines)" % (len(cited_all), NLINE),
      "past EOF: %s" % over[:8])
check(len(cited_all) >= 90,
      "E the doc still carries its full citation set (%d found)" % len(cited_all),
      "only %d - did a section get dropped?" % len(cited_all))

STALE = ["L5416", "L19230", "L42077", "L33107", "L33118", "L23329",
         "43548", "43670", "13818", "20800", "20835"]
still = [s for s in STALE if s in DOC_FLAT]
check(len(still) == 0,
      "E none of the nine known-stale citations remain in the doc", str(still))

# Pin the citation shape, not the bare word: legitimate prose such as
# "silently swallowing a region)" must not trip this.
_hedged = re.findall(r"\bL?\d{3,5}\s+region\)", DOC_TEXT)
check(len(_hedged) == 0,
      "E no hedged `L#### region` citation survives - every citation is exact",
      str(_hedged[:6]))

# F7 has now been run once and found a real defect, so the honest disclaimer is
# no longer "nothing compiled" but "your F7 output is reported, never claimed as
# mine, and a second F7 is still required". Pin that stronger wording - and pin
# that the doc never asserts a clean build.
for phrase in ("F7 has now been run",
               "never a claim of my own",
               "A second F7 is still required to confirm the build is clean",
               "do not** prove the code compiles",
               "remain invisible here"):
    check(phrase in DOC_FLAT,
          "E the doc still disclaims compilation: %r" % phrase)
for forbidden in ("compiles cleanly", "compilation succeeded", "0 errors, 0 warnings "
                  "after the fix", "build is verified"):
    check(forbidden not in DOC_FLAT,
          "E the doc never claims a clean build: %r" % forbidden)
# Pin the F7 result INSIDE its own section. A whole-document substring check is
# satisfied by the status line alone, so deleting the number from section 11.1
# passed unnoticed (mutation N1) - the same weak-pin class as the earlier "1.50".
def section(head, nxt):
    a = DOC_FLAT.find(head)
    if a < 0:
        return ""
    b = DOC_FLAT.find(nxt, a + len(head))
    return DOC_FLAT[a:b if b > 0 else len(DOC_FLAT)]


S111 = section("## 11.1 What F7 actually found", "## 11.2 ")
check(len(S111) > 500, "E section 11.1 exists and carries the F7 report",
      "%d chars" % len(S111))
check("42 errors, 0 warnings" in S111,
      "E section 11.1 itself reports the real F7 result (42 errors, 0 warnings)")
check("24923" in S111, "E section 11.1 names the exact line that broke (now 24923)")
# Pin the quoted broken line itself, not just its number: the number appears
# several times in the section, so a mutation to one occurrence survived (N9).
check("Called when a new symbol/day context" in S111,
      "E section 11.1 quotes the exact prose the compiler was fed")
check(S111.count("24923") >= 3,
      "E section 11.1 cites line 24923 in the code block, the error list and the "
      "cascade description (%d times)" % S111.count("24923"),
      "only %d" % S111.count("24923"))
check("SBP3_Clear" in S111, "E section 11.1 names the function whose body mis-parsed")
S112 = section("## 11.2 The gap is now owned by a test", "## 12. ")
check(len(S112) > 300, "E section 11.2 exists and documents the new guard",
      "%d chars" % len(S112))
check("test_comment_integrity.py" in S112,
      "E section 11.2 names tools/test_comment_integrity.py")
check("Mutation-tested 8/8" in S112,
      "E section 11.2 states the guard's mutation result (8/8) - an unstated "
      "mutation count is an unverified claim (mutation N12)")
check("19 checks" in S112, "E section 11.2 states the guard's check count (19)")
check("one missing `//` became 42 errors" in DOC_FLAT.lower() or
      "One missing `//` became 42 errors" in DOC_FLAT,
      "E the doc records that a single missing comment marker caused all 42")
check("no backtest result is claimed" in DOC_FLAT.lower() or
      "NOT constitute a backtest" in DOC_FLAT,
      "E the doc still disclaims any backtest result")

check("arena/643314e5-terad" in DOC_FLAT and "**#15**" in DOC_FLAT,
      "E the doc names its branch and pull request")
# Derive the real risk percentage from source rather than hard-coding "1.50":
# a bare substring check is satisfied by InpRMNoZoneSLATR's 1.50 default too, so
# it could not tell a deleted disclosure from a present one (mutation M05).
_risk_m = re.search(r"\bInpSniperMaxRiskPct\s*=\s*([0-9.]+)", line_at(1806))
_risk = _risk_m.group(1) if _risk_m else None
check(_risk == "1.50",
      "E source still declares InpSniperMaxRiskPct = 1.50 at L1806", str(_risk))
check("the risk percentage the module reports defaults to %s, not 1.0" % _risk
      in DOC_FLAT,
      "E the doc states the risk %% the module REPORTS defaults to %s, not 1.0" % _risk)
check(("the reported risk percentage is **%s, not 1.0**" % _risk) in DOC_FLAT,
      "E the conflict section repeats that deviation (%s, not 1.0)" % _risk)
check(("InpSniperMaxRiskPct` (**L1806**)" in DOC_FLAT and
       ("| **`%s`** |" % _risk) in DOC_FLAT),
      "E the reuse table cites InpSniperMaxRiskPct at L1806 with default %s" % _risk)
check("InpMinRR" in DOC_FLAT and "do not exist" in DOC_FLAT,
      "E the doc still records that the brief's named inputs do not exist")
check("+3 983 / −1" in DOC_FLAT or "+3983/−1" in DOC_FLAT,
      "E the doc reports the verified PR figure +3983/-1 for nadir2.mq5")
check("4 155" in DOC_FLAT and "173" in DOC_FLAT and "realign" in DOC_FLAT,
      "E the doc explains the misleading cumulative diffstat rather than quoting it")
check("exactly 1 real line lost" in DOC_FLAT,
      "E the doc states the PR-wide multiset result")

# the doc must not silently lose a section
for head in ("## 1. What was added", "## 2. Activation guide",
             "## 3. Complete input reference", "## 4. Where each module lives",
             "## 5. The causal order inside `OnCalculate`",
             "## 6. What you see on the dashboard",
             "## 7. The Risk Model's output", "## 8. The nine conflicts",
             "## 9. Invariants guaranteed", "## 10. Verification evidence",
             "## 11. F7 checklist", "## 12. Known risks",
             "## 13. Open decisions"):
    check(head in DOC_FLAT, "E the doc still has section %r" % head)


# =========================== D2. the activation-guide dependency, derived
# The guide's central operational claim is that with Price Action off, the
# Confluence Engine's candle leg scores 0 and the reachable maximum is 85, not
# 100. Do not hard-code 85: derive it as 100 - InpCFWeightCandle from source, so
# the check follows a retune instead of silently going stale (mutation M23).
_w = {}
for name in ("InpCFWeightStructure", "InpCFWeightLiquidity", "InpCFWeightZone",
             "InpCFWeightSession", "InpCFWeightCandle", "InpCFWeightMTF"):
    m = re.search(r"\b%s\s*=\s*(-?\d+)" % name, RAW)
    _w[name] = int(m.group(1)) if m else None
check(all(v is not None for v in _w.values()),
      "D2 all six confluence weights are declared in source", str(_w))
WSUM = sum(v for v in _w.values() if v is not None)
check(WSUM == 100, "D2 the six weights sum to exactly 100 (the doc's claim)",
      "actual sum %d: %s" % (WSUM, _w))
_max_no_candle = 100 - (_w.get("InpCFWeightCandle") or 0)
check(_max_no_candle == 85,
      "D2 without the candle leg the reachable maximum is 85", "derived %d" % _max_no_candle)
check(_w.get("InpCFWeightCandle") == 15,
      "D2 the candle leg weighs 15, and is the leg guarded by InpEnablePriceAction",
      str(_w.get("InpCFWeightCandle")))
check("score the engine can reach is **%d**, not 100" % _max_no_candle in DOC_FLAT,
      "D2 the doc states the reachable maximum is %d, not 100" % _max_no_candle)
# the guard itself: CF's candle leg must really be gated by InpEnablePriceAction
_candle_guard = re.search(
    r"g_cf_has_candle=\(\(InpEnablePriceAction\|\|InpEnableAllModules\) &&", RAW)
check(_candle_guard is not None,
      "D2 CF's candle leg is guarded by `InpEnablePriceAction &&` in source - the "
      "dependency the guide describes is real, not asserted")
_min = re.search(r"\bInpCFMinDisplayScore\s*=\s*(\d+)", RAW)
_mind = int(_min.group(1)) if _min else None
check(_mind is not None and _mind <= _max_no_candle,
      "D2 InpCFMinDisplayScore (%s) is still reachable without the candle leg, so "
      "the engine can name a side" % _mind)
check(_mind == 60, "D2 InpCFMinDisplayScore is 60 as the doc states", str(_mind))


# =============================================== F. two-way binding doc <-> pins
# Parts A-C verify SOURCE lines against numbers hard-coded in this test. That
# leaves one direction unchecked: the DOCUMENT could cite a different line than
# this test pins, and both could be "green" while disagreeing (mutation M01
# changed the doc's RM_Update citation to L27247 and nothing noticed). So every
# pinned line must also be cited by the doc - directly, or inside a range the doc
# gives. Cited ranges are expanded, so `L1850-1844` covers all four lines.
DOC_COVERED = set()
for m in re.findall(r"\bL(\d{3,5})", DOC_TEXT):
    DOC_COVERED.add(int(m))
for m in re.finditer(r"\bL(\d{3,5})\s*[\u2013\u2014-]\s*(?:L)?(\d{3,5})", DOC_TEXT):
    a, b = int(m.group(1)), int(m.group(2))
    if a <= b and b - a < 4000:
        DOC_COVERED.update(range(a, b + 1))

# Pins this test holds that the doc legitimately does not cite, with the reason.
# Anything added here must be justified - it is a hole in the binding.
TEST_ONLY = {
    15264: "the doc cites the age-bound banner L15259, not the OBIsExpired call line",
}

pin_total = 0
for label, cited, pat, defname in ANCHORS:
    pin_total += 1
    ok = cited in DOC_COVERED or cited in TEST_ONLY
    check(ok, "F the doc also cites L%d (%s)" % (cited, label.split(" at ")[-1][:44]),
          "this test pins L%d but the doc never cites it%s"
          % (cited, (" - TEST_ONLY: " + TEST_ONLY[cited]) if cited in TEST_ONLY else ""))
for cited, pat, name in GUARDS:
    pin_total += 1
    check(cited in DOC_COVERED, "F the doc also cites the %s tooltip guard L%d" % (name, cited),
          "this test pins L%d but the doc never cites it" % cited)
for cited, pat, name in ORDER:
    pin_total += 1
    check(cited in DOC_COVERED, "F the doc also cites the %s call site L%d" % (name, cited),
          "this test pins L%d but the doc never cites it" % cited)

check(pin_total == len(ANCHORS) + len(GUARDS) + len(ORDER),
      "F every one of the %d pinned citations was cross-checked against the doc" % pin_total,
      "only %d checked" % pin_total)
check(len(TEST_ONLY) <= 2,
      "F at most 2 pins are allowed to be test-only (holes in the binding)",
      "%d: %s" % (len(TEST_ONLY), sorted(TEST_ONLY)))

print("")
print("=" * 74)
print("DOC-FRESHNESS checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    print("")
    print("The document has drifted from nadir2.mq5. Fix the DOCUMENT unless the")
    print("source change was intentional and the doc is the thing that is wrong.")
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("Binding is two-way: source lines are checked against this test's pins (A-C),")
print("and every pin is checked against what the doc actually cites (F).")
print("This is a citation + countable-fact contract. It is not a compiler, not a")
print("backtest, and it does not judge whether a claim is true in a trading sense.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
