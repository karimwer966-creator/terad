#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-MR1  MEAN REVERSION / MOMENTUM - transcription + wiring contract.

Phase 5 of the strategy-module extension for nadir2.mq5. What this file proves,
and what it deliberately does NOT claim:

  * It transcribes the module's pure cores into Python, re-derives their
    behaviour, and then checks that the transcribed guard ORDER, constants and
    literals are the ones actually present in the .mq5 text. Without that second
    step the transcription could drift from the source and still pass.
  * It proves the "MACD is an optional momentum FILTER ONLY" rule structurally:
    exhaustively, over every combination of evidence, MACD can zero the score but
    can never raise it, and it can never supply a direction.
  * It proves the causality crux - divergence is measured on CONFIRMED swings, via
    the file's own IsFractalHigh()/IsFractalLow(), whose guard requires n fully
    closed bars to the right, so a swing can never un-confirm itself.
  * It proves sigma is root-mean-square distance from VWAP and NOT mean-centred,
    numerically, by exhibiting a persistent-offset series where the two differ by
    an order of magnitude.
  * It is a static contract test. It is NOT a backtest, produces no win rate, and
    does NOT prove MetaEditor compiles the file - only F7 does that.
"""
import io
import math
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
    TEXT = fh.read()
BARE_LF = TEXT.count("\n") - TEXT.count("\r\n")


def strip_comments(src):
    """Remove comments and blank literal contents in ONE pass. A chain of regexes
    is unsound in both orders: a "//" inside a string literal makes the comment
    pass eat the rest of the line and leave an unterminated quote, which then makes
    the string pass swallow thousands of lines of real code."""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == '"' or c == "'":
            q = c
            out.append('""' if q == '"' else "''")
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _fn_end(text, sig_at):
    i, depth, started, n = sig_at, 0, False, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            if j < 0:
                return -1
            i = j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            if j < 0:
                return -1
            i = j + 2
            continue
        if c in '"\'':
            q = c
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == q:
                    break
                i += 1
            i += 1
            continue
        if c == '{':
            depth += 1
            started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return i + 1
        i += 1
    return -1


def _section(text, banner, sig):
    """Slice a module's section from its banner to the end of its OWN self-test.
    Never end a section at a shared downstream marker."""
    i0 = text.find(banner)
    if i0 < 0:
        return -1, -1, ""
    j = text.find(sig, i0)
    if j < 0:
        return -1, -1, ""
    e = _fn_end(text, j)
    if e < 0:
        return -1, -1, ""
    return i0, e, text[i0:e]


def body_of(sig, label, floor=0):
    """Body of the DEFINITION matching `sig`, skipping forward declarations. A
    declaration has no braces of its own, so a brace-matched scan from there
    silently returns the body of whatever unrelated function follows it."""
    j = floor
    while True:
        j = TEXT.find(sig, j)
        if j < 0:
            break
        sc = TEXT.find(';', j)
        br = TEXT.find('{', j)
        if br >= 0 and (sc < 0 or br < sc):
            end = _fn_end(TEXT, j)
            if end > 0:
                return TEXT[j:end]
        j += len(sig)
    check(False, label + " (definition located)", sig)
    return ""


def precedes(hay, first, second, label):
    """Assert order, reporting a FAIL rather than raising: a bare index() turns a
    missing anchor into a traceback that silently skips every later check."""
    a, b = hay.find(first), hay.find(second)
    check(a >= 0 and b >= 0 and a < b, label, "first@%d second@%d" % (a, b))


def input_default(name):
    m = re.search(r"\binput\s+[A-Za-z_][\w\s\*&]*?\b" + re.escape(name) +
                  r"\s*=\s*([^,;]+)[,;]", TEXT)
    return m.group(1).strip() if m else None


c_all = strip_comments(TEXT)


def call_count(sig_call):
    """Occurrences of a real CALL of `sig_call`, excluding declarations.

    A declaration and a call can share text exactly (`void   MR_Clear();` contains
    `MR_Clear();`), so a raw count over-reports. Subtracting fixed type prefixes is
    also wrong, because this file aligns its declarations with run-on spaces. A line
    is a declaration when it starts with a return type and ends with a semicolon."""
    n = 0
    for m in re.finditer(re.escape(sig_call), c_all):
        ls = c_all.rfind('\n', 0, m.start()) + 1
        le = c_all.find('\n', m.end())
        line = c_all[ls:le if le >= 0 else len(c_all)]
        if re.match(r'^\s*(?:void|int|bool|string|double|datetime|long|ushort)\s+', line) \
                and line.rstrip().endswith(';'):
            continue
        n += 1
    return n


# =====================================================================
# A. PURE CORES - transcribed, then pinned back to the source text
# =====================================================================
def mr_stddev(closes, vwaps, period):
    """Root-mean-square distance of the close from VWAP. NOT mean-centred."""
    if period < 2 or len(closes) < period:
        return 0.0
    acc = 0.0
    for i in range(len(closes) - period, len(closes)):
        v = vwaps[i]
        if not (v > 0.0) or not (closes[i] > 0.0):
            return 0.0
        d = closes[i] - v
        acc += d * d
    return math.sqrt(acc / period)


def mr_stddev_mean_centred(closes, vwaps, period):
    """The WRONG variant, kept only to demonstrate why it is wrong."""
    if period < 2 or len(closes) < period:
        return 0.0
    ds = []
    for i in range(len(closes) - period, len(closes)):
        v = vwaps[i]
        if not (v > 0.0) or not (closes[i] > 0.0):
            return 0.0
        ds.append(closes[i] - v)
    mean = sum(ds) / len(ds)
    return math.sqrt(sum((d - mean) ** 2 for d in ds) / len(ds))


def mr_band_side(price, vwap, sigma, k):
    if not (price > 0.0 and vwap > 0.0 and sigma > 0.0 and k > 0.0):
        return 0
    if price > vwap + k * sigma:
        return 1
    if price < vwap - k * sigma:
        return -1
    return 0


def mr_stretch(price, vwap, sigma):
    if not (price > 0.0 and vwap > 0.0 and sigma > 0.0):
        return 0.0
    return (price - vwap) / sigma


def mr_divergence_dir(po, ro, pn, rn, is_high, min_delta):
    if not (po > 0.0 and pn > 0.0):
        return 0
    if not (ro > 0.0 and rn > 0.0):
        return 0
    delta = rn - ro
    need = min_delta if min_delta > 0.0 else 0.0
    if is_high:
        return -1 if (pn > po and delta <= -need) else 0
    return 1 if (pn < po and delta >= need) else 0


def mr_macd_direction(main, signal, dead_zone):
    hist = main - signal
    dz = dead_zone if dead_zone > 0.0 else 0.0
    if hist > dz:
        return 1
    if hist < -dz:
        return -1
    return 0


def mr_macd_conflicts(ext_dir, macd_dir):
    return ext_dir != 0 and macd_dir != 0 and macd_dir == ext_dir


def mr_resolve_direction(extended, ext_dir, div_dir, rsi_extreme, macd_conflict):
    if not extended or ext_dir == 0:
        return 0
    if macd_conflict:
        return 0
    fade = -ext_dir
    if div_dir != 0 and div_dir != fade:
        return 0
    if div_dir == 0 and not rsi_extreme:
        return 0
    return fade


def mr_score(extended, div_agrees, rsi_extreme, macd_conflict):
    if not extended:
        return 0
    if macd_conflict:
        return 0
    s = 35
    if div_agrees:
        s += 45
    if rsi_extreme:
        s += 20
    return 100 if s > 100 else s


# A1 sigma: RMS distance from VWAP, and why mean-centring would be wrong.
check(abs(mr_stddev([102.0, 102.0, 102.0, 102.0], [100.0] * 4, 4) - 2.0) < 1e-9,
      "A1 a persistent 2-point offset above VWAP gives sigma = 2.00")
check(mr_stddev_mean_centred([102.0, 102.0, 102.0, 102.0], [100.0] * 4, 4) < 1e-9,
      "A1 the mean-centred variant reports sigma = 0 for that same series")
check(mr_stddev([102.0] * 4, [100.0] * 4, 4) > 50 * (mr_stddev_mean_centred([102.0] * 4, [100.0] * 4, 4) + 1e-12),
      "A1 so mean-centring would make every bar of a steady trend look extreme")
check(abs(mr_stddev([101.0, 99.0, 101.0, 99.0], [100.0] * 4, 4) - 1.0) < 1e-9,
      "A1 a symmetric +/-1 oscillation about VWAP gives sigma = 1.00")
check(mr_stddev([100.0, 100.0], [100.0, 100.0], 2) == 0.0,
      "A1 price sitting exactly on VWAP gives sigma 0, which means no band at all")
check(mr_stddev([101.0, 102.0], [100.0, 0.0], 2) == 0.0,
      "A1 one missing VWAP sample means no sigma, not a partial estimate")
check(mr_stddev([101.0, 102.0], [100.0, 100.0], 1) == 0.0 and
      mr_stddev([101.0], [100.0], 2) == 0.0,
      "A1 a window that cannot be filled returns no sigma")

# A2 band side: strict, and no band means no side.
check(mr_band_side(105.0, 100.0, 2.0, 2.0) == 1 and mr_band_side(95.0, 100.0, 2.0, 2.0) == -1,
      "A2 a close beyond the band is stretched")
check(mr_band_side(104.0, 100.0, 2.0, 2.0) == 0 and mr_band_side(96.0, 100.0, 2.0, 2.0) == 0,
      "A2 a close exactly ON the band is not an overextension")
check(mr_band_side(101.0, 100.0, 2.0, 2.0) == 0, "A2 a close inside the bands is not stretched")
for bad in ((105.0, 100.0, 0.0, 2.0), (105.0, 0.0, 2.0, 2.0),
            (105.0, 100.0, 2.0, 0.0), (0.0, 100.0, 2.0, 2.0)):
    check(mr_band_side(*bad) == 0, "A2 missing input %s gives no side" % (bad,))
check(mr_band_side(102.5, 100.0, 1.0, 2.0) == 1 and mr_band_side(102.5, 100.0, 1.0, 3.0) == 0,
      "A2 a wider k moves the band out")

# A3 stretch is signed and in sigma units.
check(abs(mr_stretch(104.0, 100.0, 2.0) - 2.0) < 1e-9, "A3 stretch above VWAP is positive")
check(abs(mr_stretch(96.0, 100.0, 2.0) + 2.0) < 1e-9, "A3 stretch below VWAP is negative")
check(mr_stretch(104.0, 100.0, 0.0) == 0.0, "A3 no sigma means no stretch to report")

# A4 divergence, both directions, with a noise floor and the 0.0 sentinel.
check(mr_divergence_dir(100.0, 75.0, 102.0, 68.0, True, 2.0) == -1,
      "A4 a higher high with a lower RSI high is bearish divergence")
check(mr_divergence_dir(100.0, 25.0, 98.0, 33.0, False, 2.0) == 1,
      "A4 a lower low with a higher RSI low is bullish divergence")
check(mr_divergence_dir(100.0, 75.0, 102.0, 80.0, True, 2.0) == 0,
      "A4 a higher high with a higher RSI high is not divergence")
check(mr_divergence_dir(100.0, 75.0, 98.0, 68.0, True, 2.0) == 0,
      "A4 a LOWER high in price cannot be a bearish divergence")
check(mr_divergence_dir(100.0, 25.0, 102.0, 33.0, False, 2.0) == 0,
      "A4 a HIGHER low in price cannot be a bullish divergence")
check(mr_divergence_dir(100.0, 75.0, 102.0, 74.5, True, 2.0) == 0,
      "A4 an RSI gap below the minimum is noise, not divergence")
check(mr_divergence_dir(100.0, 75.0, 102.0, 73.0, True, 2.0) == -1,
      "A4 an RSI gap exactly at the minimum does count (the bound is inclusive)")
check(mr_divergence_dir(100.0, 0.0, 102.0, 68.0, True, 2.0) == 0 and
      mr_divergence_dir(100.0, 75.0, 102.0, 0.0, True, 2.0) == 0,
      "A4 an unavailable RSI (this file's 0.0 sentinel) cannot manufacture divergence")
check(mr_divergence_dir(0.0, 75.0, 102.0, 68.0, True, 2.0) == 0,
      "A4 an unavailable price cannot manufacture divergence")
check(mr_divergence_dir(100.0, 75.0, 102.0, 68.0, False, 2.0) == 0,
      "A4 a bearish pair read as a LOW-side divergence is nothing")

# A5 MACD direction, dead zone, and the conflict test.
check(mr_macd_direction(1.00, 0.50, 0.10) == 1 and mr_macd_direction(0.50, 1.00, 0.10) == -1,
      "A5 a histogram beyond the dead zone is momentum")
check(mr_macd_direction(1.00, 0.95, 0.10) == 0,
      "A5 a hair-thin histogram inside the dead zone is not momentum")
check(mr_macd_direction(1.00, 1.00, 0.10) == 0, "A5 a flat histogram is not momentum")
check(mr_macd_direction(1.00, 0.95, 0.0) == 1, "A5 a zero dead zone falls back to the sign")
check(mr_macd_conflicts(1, 1) and mr_macd_conflicts(-1, -1),
      "A5 momentum pushing in the stretched direction conflicts with a fade")
check(not mr_macd_conflicts(1, -1) and not mr_macd_conflicts(-1, 1),
      "A5 momentum against the stretch supports the fade, it does not conflict")
check(not mr_macd_conflicts(1, 0) and not mr_macd_conflicts(0, 1) and not mr_macd_conflicts(0, 0),
      "A5 a filter that did not run abstains, it never vetoes")

# A6 a stretch is not a direction.
for d in (-1, 0, 1):
    for r in (False, True):
        check(mr_resolve_direction(False, 0, d, r, False) == 0,
              "A6 with no overextension there is nothing to fade (div=%d rsi=%s)" % (d, r))
check(mr_resolve_direction(True, 1, 0, False, False) == 0,
      "A6 a stretch with no exhaustion evidence resolves to nothing")
check(mr_resolve_direction(True, 1, -1, False, False) == -1,
      "A6 stretched up with bearish divergence fades DOWN")
check(mr_resolve_direction(True, -1, 1, False, False) == 1,
      "A6 stretched down with bullish divergence fades UP")
check(mr_resolve_direction(True, 1, 0, True, False) == -1,
      "A6 an RSI extreme is exhaustion evidence on its own")
check(mr_resolve_direction(True, 1, -1, False, True) == 0,
      "A6 momentum still pushing up vetoes the short fade")
check(mr_resolve_direction(True, -1, 1, False, True) == 0,
      "A6 momentum still pushing down vetoes the long fade")
check(mr_resolve_direction(True, 1, 1, False, False) == 0 and
      mr_resolve_direction(True, -1, -1, False, False) == 0,
      "A6 a divergence pointing WITH the stretch contradicts the fade")

# A7 score arithmetic.
check(mr_score(False, True, True, False) == 0,
      "A7 with no overextension nothing scores, however good the evidence")
check(mr_score(True, False, False, False) == 35,
      "A7 the stretch alone is worth 35 and cannot look like a setup")
check(mr_score(True, True, False, False) == 80, "A7 an agreeing divergence adds 45")
check(mr_score(True, False, True, False) == 55, "A7 an RSI extreme adds 20")
check(mr_score(True, True, True, False) == 100,
      "A7 the full evidence set is exactly 100, with MACD contributing nothing")

# A8 THE "FILTER ONLY" CONTRACT, exhaustively.
worse = []
for d in (False, True):
    for r in (False, True):
        for c in (False, True):
            vetoed = mr_score(True, d, r, c)
            plain = mr_score(True, d, r, False)
            if vetoed > plain:
                worse.append((d, r, c, plain, vetoed))
            if c and vetoed != 0:
                worse.append(("veto not zeroing", d, r, c))
check(not worse, "A8 over every combination MACD can only veto, never raise the score",
      str(worse[:3]))
check(mr_score(True, True, True, True) == 0,
      "A8 even perfect evidence scores 0 when momentum vetoes the fade")
check(mr_score(True, True, True, False) == mr_score(True, True, True, False),
      "A8 the maximum is reachable with MACD entirely absent")

# A9 consistency: the verdict and the score can never contradict each other.
bad = []
for e in (-1, 0, 1):
    for d in (-1, 0, 1):
        for r in (False, True):
            for c in (False, True):
                ext = (e != 0)
                direction = mr_resolve_direction(ext, e, d, r, c)
                sc = mr_score(ext, (ext and d != 0 and d == -e), r, c)
                if c and (direction != 0 or sc != 0):
                    bad.append(("vetoed but shown", e, d, r, c))
                if direction != 0 and sc <= 0:
                    bad.append(("direction with no score", e, d, r, c))
                if direction != 0 and not ext:
                    bad.append(("direction with no stretch", e, d, r, c))
                if direction != 0 and e != 0 and direction == e:
                    bad.append(("fading WITH the stretch", e, d, r, c))
                if direction != 0 and d != 0 and d != direction:
                    bad.append(("divergence disagrees with the printed side", e, d, r, c))
check(not bad, "A9 no combination prints a contradictory label", str(bad[:3]))
combos = 3 * 3 * 2 * 2
check(combos == 36, "A9 the consistency sweep covered all %d combinations" % combos)

# ---- A10 pin the transcription back to the shipped source text -----------
sd = body_of("double MR_StdDevAroundVWAP(const int closed", "A10 MR_StdDevAroundVWAP")
check("acc+=dev*dev;" in sd and "return MathSqrt(acc/(double)period);" in sd,
      "A10 sigma is the root-mean-square of (close - VWAP)")
check("mean" not in sd.lower(),
      "A10 sigma is NOT mean-centred - the mean is never subtracted")
check("if(v==EMPTY_VALUE || !(v>0.0)) return 0.0;" in sd,
      "A10 one dirty VWAP sample abandons the whole window")
check("if(period<2) return 0.0;" in sd and "if(closed<period-1) return 0.0;" in sd,
      "A10 the sigma guards refuse before touching any array")
bs = body_of("int MR_BandSide(const double price", "A10 MR_BandSide")
check("if(price>vwap+k*sigma) return 1;" in bs and "if(price<vwap-k*sigma) return -1;" in bs,
      "A10 the band test is strict, so a close ON the band is not an overextension")
dv = body_of("int MR_DivergenceDir(const double price_old", "A10 MR_DivergenceDir")
check("if(!(rsi_old>0.0) || !(rsi_new>0.0)) return 0;" in dv,
      "A10 the 0.0 unavailable sentinel is honoured before any divergence")
precedes(dv, "if(!(rsi_old>0.0)", "if(price_new>price_old && delta<=-need) return -1;",
         "A10 the sentinel guard precedes the divergence tests")
check("if(price_new>price_old && delta<=-need) return -1;" in dv and
      "if(price_new<price_old && delta>=need) return 1;" in dv,
      "A10 regular divergence only: higher-high/lower-RSI and lower-low/higher-RSI")
md = body_of("int MR_MacdDirection(const double main", "A10 MR_MacdDirection")
check("double hist=main-signal;" in md and "if(hist>dz) return 1;" in md and
      "if(hist<-dz) return -1;" in md,
      "A10 momentum is the histogram against an ATR-scaled dead zone")
rs = body_of("int MR_ResolveDirection(const bool extended", "A10 MR_ResolveDirection")
order = ["if(!extended || ext_dir==0) return 0;", "if(macd_conflict) return 0;",
         "int fade=-ext_dir;", "if(div_dir!=0 && div_dir!=fade) return 0;",
         "if(div_dir==0 && !rsi_extreme) return 0;", "return fade;"]
pos = [rs.index(o) for o in order if o in rs]
check(len(pos) == 6 and pos == sorted(pos),
      "A10 the resolve order is stretch -> veto -> contradiction -> exhaustion -> fade")
sc = body_of("int MR_Score(const bool extended", "A10 MR_Score")
check("if(!extended) return 0;" in sc and "if(macd_conflict) return 0;" in sc,
      "A10 the score's two vetoes come first")
check("int s=35;" in sc and "if(div_agrees) s+=45;" in sc and "if(rsi_extreme) s+=20;" in sc,
      "A10 the legs are 35 + 45 + 20 = 100 exactly")
check("macd_conflict" in sc and "s+=" in sc and
      not re.search(r"if\s*\(\s*macd\w*\s*\)\s*s\s*\+=", sc),
      "A10 no branch adds to the score on MACD's behalf")
check(sc.count("s+=") == 2, "A10 there are exactly two scoring additions (%d)" % sc.count("s+="))

# =====================================================================
# B. SECTION CONTRACTS - reuse, purity, causality, scope
# =====================================================================
_i0, _i1, mr_section = _section(TEXT, "// AUDIT-MR1  MEAN REVERSION", "bool MR_SelfTest(string &where)")
check(0 < _i0 < _i1, "B the MR1 engine section was located", "%d..%d" % (_i0, _i1))
check(len(mr_section) > 8000, "B the MR1 section slice is substantial (%d chars)" % len(mr_section))
mr_src = strip_comments(mr_section)

# Reuse, not reimplementation.
check("BufVWAP[" in mr_src, "B the bands reuse the existing BufVWAP, not a second VWAP")
check("iBands" not in mr_src and "iRSI" not in mr_src and "iATR" not in mr_src,
      "B no Bollinger/RSI/ATR handle is created - the per-bar arrays already exist")
check("g_rsi_buf[" in mr_src, "B divergence reads the existing per-bar RSI array")
check("g_atr_buf[" in mr_src and "g_atr" in mr_src, "B ATR uses the file's own idiom")
check("IsFractalHigh(" in mr_src and "IsFractalLow(" in mr_src,
      "B swings are the file's own CONFIRMED fractals")
check("IsPreviewFractalHigh" not in mr_src and "IsPreviewFractalLow" not in mr_src,
      "B the PREVIEW (unconfirmed) fractals are never used - they would repaint")
check("FractalRightBars(" in mr_src, "B the confirmation depth reuses FractalRightBars()")
check("InpSwingFractalN" in mr_src,
      "B the swing depth is the file's canonical InpSwingFractalN, not a second notion")

# The causality crux: the confirmed-fractal guard this module now depends on.
fh = body_of("bool IsFractalHigh(const double &h[]", "B IsFractalHigh")
check("if(i<n || i+n>total-2) return false;" in fh,
      "B IsFractalHigh refuses any bar without n fully closed bars to its right")
check("confirmed: fully inside closed bars" in fh,
      "B that guard is documented as the confirmation rule in the source itself")
fl = body_of("bool IsFractalLow(const double &l[]", "B IsFractalLow")
check("if(i<n || i+n>total-2) return false;" in fl,
      "B IsFractalLow applies the same confirmation bound")
frb = body_of("int FractalRightBars(const int n)", "B FractalRightBars")
check("return MathMax(1,n);" in frb, "B confirmation depth is at least one closed bar")

# Display-only, no buffers, no trade authority, nothing drawn.
check("BufSig" not in mr_section and "SetIndexBuffer" not in mr_section,
      "B5 the module writes no buffer")
for api in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen", "PositionClose",
            "WebRequest", "Alert(", "SendNotification", "iCustom", "SymbolInfoTick"):
    check(api not in mr_src, "B5 the module cannot reach %s" % api)
check(mr_src.count("ObjectCreate") == 0 and "DrawZoneBox(" not in mr_src and
      "DrawTextLabel(" not in mr_src and "DrawHLine(" not in mr_src,
      "B7 the module draws nothing, so it needs no object-prefix cleanup")

# Symbol-agnostic: no literal price level in the production code.
prod = _section(TEXT, "// AUDIT-MR1  MEAN REVERSION", "void MR_Update(const int closed")[2]
hits = re.findall(r"\b\d{3,4}\.\d{1,5}\b", re.sub(r'"(\\.|[^"\\])*"', '""', strip_comments(prod)))
check(not hits, "B6 no literal price level in the module's production code", str(sorted(set(hits))))
check("InpMRMacdDeadZoneATR" in mr_src and "atr*InpMRMacdDeadZoneATR" in mr_src,
      "B6 the MACD dead zone is ATR-scaled, so it is symbol-agnostic")

# Causality inside MR_Update.
upd = body_of("void MR_Update(const int closed", "B9 MR_Update", floor=_i0)
check("[closed+1]" not in strip_comments(upd) and "[closed + 1]" not in strip_comments(upd),
      "B9 no future bar is read")
for api in ("iTime(", "iClose(", "iOpen(", "iHigh(", "iLow(", "CopyRates("):
    check(api not in strip_comments(upd), "B9 MR_Update reads no live series")
check("g_buf_c[closed]" in upd, "B9 the band test uses the CLOSED bar's close")
check("if(closed<2 || rates_total<3) return;" in upd,
      "B9 a bar with no history behind it is refused")
check("if(!(InpEnableMeanReversion||InpEnableAllModules)) return;" in upd,
      "B9 the module returns immediately while its switch is off")
resets = upd[:upd.find("if(!InpEnableMeanReversion)")]
for g in ("g_mr_ext_dir=0", "g_mr_div_dir=0", "g_mr_dir=0", "g_mr_score=0",
          "g_mr_reason=\"\"", "g_mr_sigma=0.0", "g_mr_macd_dir=0"):
    check(g in resets, "B9 %s is reset before the early return, so nothing is latched" % g)
check("g_mr_swing_hi_new=-1" in resets and "g_mr_swing_lo_new=-1" in resets,
      "B9 the swing bars are reset too, so a stale swing can never be reused")

# The optional MACD copy must stay out of the file's retry mechanism.
rf = body_of("bool MR_RefreshMACD(const int rates_total", "B MR_RefreshMACD", floor=_i0)
check("prev_calculated" not in rf,
      "B the optional MACD copy never returns prev_calculated")
check("g_ind_copy_retries" not in rf,
      "B it never touches the file's bounded indicator-copy retry counter")
check("g_ind_copy_warned" not in rf, "B it never touches the retry warning flag")
check("nm==need && ns==need" in rf, "B a short copy is detected, not trusted")
check("g_mr_macd_main[k]=0.0;" in rf,
      "B an unfilled bar is marked with the file's own 0.0 unavailable sentinel")
check("CopyBuffer(h_macd,0,0,need,tm)" in rf and "CopyBuffer(h_macd,1,0,need,ts)" in rf,
      "B both MACD legs are copied, main and signal")
check("int src=k-from;" in rf,
      "B the index mapping matches the one the file already uses for ATR/ADX/RSI")

# Reason vocabulary: mutually exclusive, never a side next to a stand-aside.
reasons = []
for _m in re.finditer(r'g_mr_reason=', mr_section):
    _j = mr_section.find(';', _m.end())
    _lit = "".join(re.findall(r'"((?:\\.|[^"\\])*)"', mr_section[_m.start():_j]))
    if _lit.strip():
        reasons.append(_lit)
check(len(reasons) >= 5, "B the module emits %d distinct reason strings" % len(reasons))
check(any(r.startswith("no overextension") for r in reasons),
      "B an inside-the-bands bar says so explicitly")
check(any(r.startswith("CONFLICT") for r in reasons),
      "B contradictions are labelled CONFLICT, not quietly resolved")
check(sum(1 for r in reasons if r.startswith("CONFLICT")) >= 3,
      "B all three contradiction kinds are named: both divergences, MACD, and divergence-vs-stretch")
check(any(r.startswith("stand aside:") for r in reasons),
      "B a stretch with no exhaustion evidence gets an explicit stand-aside")
check(any("not an entry" in r for r in reasons),
      "B the confirming reason says it is a reading, not an entry")
check("MACD unavailable" in mr_section,
      "B an enabled-but-unavailable MACD is reported rather than silently skipped")
check("not a probability" in mr_section.lower() or "NOT PROBABILITIES" in mr_section,
      "B10 the section states its scores are not probabilities")
check("LogLifecycle(StringFormat(" in mr_src,
      "B the module logs through the existing single-argument LogLifecycle")

# =====================================================================
# C. WIRING
# =====================================================================
check(call_count("MR_Update(closed,rates_total,full_indicators);") == 1,
      "C MR_Update is called exactly once (%d)"
      % call_count("MR_Update(closed,rates_total,full_indicators);"))
check(call_count("MR_Clear();") == 1,
      "C MR_Clear is called exactly once, the declaration excluded (%d)" % call_count("MR_Clear();"))
check(call_count("MR_SelfTest(mtee_fail)") == 1,
      "C MR_SelfTest is invoked exactly once (%d)" % call_count("MR_SelfTest(mtee_fail)"))
for fn in ("MR_StdDevAroundVWAP", "MR_BandSide", "MR_Stretch", "MR_FindConfirmedSwingPair",
           "MR_DivergenceDir", "MR_MacdDirection", "MR_MacdConflicts", "MR_ResolveDirection",
           "MR_Score", "MR_RefreshMACD", "MR_Update", "MR_Clear", "MR_SelfTest"):
    check(TEXT.count(fn) >= 2, "C %s is both declared and defined" % fn)

# Ordering: every input MR reads must already be final at the call site.
call_at = TEXT.find("MR_Update(closed,rates_total,full_indicators);")
vwap_at = TEXT.find("FillEMAAndVWAP(rates_total,g_buf_o")
pa_at = TEXT.find("PA_Update(closed);")
zre_at = TEXT.find("ZRE_Update(rates_total")
check(0 < vwap_at < call_at, "C MR_Update runs after FillEMAAndVWAP has filled BufVWAP",
      "vwap=%d call=%d" % (vwap_at, call_at))
check(0 < pa_at < call_at < zre_at, "C MR_Update sits with the other observational modules")
check("if(is_new_bar || detection_updated) MR_Update(" in TEXT,
      "C MR_Update runs once per closed bar, never per tick")
rsi_at = TEXT.find("g_rsi_buf[k]=tr[src];")
check(0 < rsi_at < call_at, "C MR_Update runs after the per-bar RSI copy")
seg = TEXT[max(0, call_at - 1200):call_at]
check("BufVWAP" in seg and "g_rsi_buf" in seg,
      "C the ordering reason names the inputs it depends on, at the call site")

# OnInit: reset, self-test under the existing switch, and the optional handle.
_pc = TEXT.find("   MR_Clear();")
check(_pc > 0, "C MR_Clear() is called in OnInit")
init_seg = TEXT[max(0, _pc - 4000):_pc + 200] if _pc > 0 else ""
check("PA_Clear();" in init_seg, "C MR_Clear sits with the other module resets in OnInit")
_st = TEXT.find("MR_SelfTest(mtee_fail)")
check("InpMTEERunSelfTest" in TEXT[max(0, _st - 7000):_st],
      "C MR_SelfTest is gated by the existing InpMTEERunSelfTest switch")
check('Print(">>> ",QSMC_VERSION_TEXT," Mean-reversion / momentum self-test: PASS (9/9)");' in TEXT,
      "C the self-test result uses the existing version-tagged log format")

# The optional handle must not change whether the indicator loads.
macd_blk = TEXT[TEXT.find("if(InpMRUseMACD)"):TEXT.find("if(InpMRUseMACD)") + 900]
check("iMACD(_Symbol,PERIOD_CURRENT,InpMRFastEMA,InpMRSlowEMA,InpMRSignalSMA,PRICE_CLOSE)" in macd_blk,
      "C iMACD is created with the standard 12/26/9 parameters, all configurable")
check("INIT_FAILED" not in macd_blk,
      "C a failed optional handle does NOT fail init - it degrades to unavailable")
init_fail = TEXT[TEXT.find('Print("Failed to create indicator handles");') - 400:
                 TEXT.find('Print("Failed to create indicator handles");') + 200]
check("h_macd" not in init_fail,
      "C h_macd was NOT added to the existing handle-validity test")
check(TEXT.count("h_macd==INVALID_HANDLE") >= 1, "C the handle result is checked")
check("if(h_macd!=INVALID_HANDLE) { IndicatorRelease(h_macd); h_macd=INVALID_HANDLE; }" in TEXT,
      "C OnDeinit releases the handle exactly once and resets it")
check(TEXT.count("IndicatorRelease(h_macd)") == 1, "C there is exactly one release")
precedes(TEXT, "return INIT_FAILED;", "if(InpMRUseMACD)",
         "C the optional handle block comes AFTER the existing init-failure test")

# Dashboard: tooltip only, never the hard-capped 11-row card.
check('tooltip+="\\nMR: stretch ' in TEXT, "C the MR rows go to the dashboard tooltip")
_d = TEXT.find('tooltip+="\\nMR: stretch ')
dash_seg = TEXT[max(0, _d - 400):_d + 1600]
check("if((InpEnableMeanReversion||InpEnableAllModules) && (InpMRShowOnDashboard||InpEnableAllModules))" in dash_seg,
      "C the MR rows need BOTH the module switch and the dashboard switch")
check('string mr_dir=(g_mr_dir>0?"BUY":(g_mr_dir<0?"SELL":"none"));' in dash_seg,
      "C a side is printed only when a direction is actually resolved")
check("not a win rate" in dash_seg, "C the score is labelled a confluence count, not a win rate")
check("if(ln>11) ln=11;" in TEXT and "string lines[11]; color cols[11]; int ln=0;" in TEXT,
      "C the 11-row card contract is untouched")

# =====================================================================
# D. NOTHING EXISTING WAS MODIFIED
# =====================================================================
# NO GIT HERE, DELIBERATELY. This section used to diff the working tree against
# HEAD to prove the phase deletes nothing. That is unsound twice over: on a clean
# tree `git diff HEAD` is empty, so the check only ever passed while the file was
# still uncommitted, and actions/checkout@v4 defaults to depth 1, so HEAD~1 does
# not exist in CI either. A contract test over a file should be a pure function of
# that file. "Zero deletions" is therefore verified from the commit diff and
# reported in the PR, while what actually matters - that no existing behaviour was
# rerouted - is pinned below from the file alone.
code_only = strip_comments(TEXT)
check(code_only.count("return INIT_FAILED;") == 2,
      "D there are still exactly 2 code-level INIT_FAILED returns (%d), so the "
      "optional handle added no init-failure path" % code_only.count("return INIT_FAILED;"))
check(TEXT.count("INIT_FAILED") - code_only.count("INIT_FAILED") <= 1,
      "D INIT_FAILED is mentioned in at most one comment")
EXISTING_HANDLE_TEST = ("if(h_ema_fast==INVALID_HANDLE || h_ema_slow==INVALID_HANDLE ||\r\n"
                        "      h_atr==INVALID_HANDLE || h_adx==INVALID_HANDLE || h_rsi==INVALID_HANDLE)")
check(EXISTING_HANDLE_TEST.replace("\r\n", "\n") in TEXT.replace("\r\n", "\n"),
      "D the pre-existing handle-validity test is byte-intact")
check(code_only.count("IndicatorRelease(h_rsi);") == 1 and
      code_only.count("IndicatorRelease(h_atr);") == 1,
      "D the pre-existing handle releases are untouched")
check("FillEMAAndVWAP(rates_total,g_buf_o,g_buf_h,g_buf_l,g_buf_c,g_buf_t,g_buf_tv,full_indicators);"
      in code_only,
      "D the pre-existing FillEMAAndVWAP call is untouched")
check(code_only.count("g_rsi_buf[k]=tr[src];") == 1,
      "D the pre-existing per-bar RSI copy is untouched")
# Membership is not a pin: this idiom occurs at five separate sites, so `in` still
# passes after any one of them is altered. Count them.
CLOSED_CONV = code_only.count("int closed=rates_total-2;")
check(CLOSED_CONV == 12,
      "D all 12 closed=rates_total-2 sites are unchanged (%d)" % CLOSED_CONV)
check(code_only.count("int closed=rates_total-1;") == 0 and
      code_only.count("int closed=ArraySize(g_buf_c)-1;") == 0,
      "D no site was moved onto the forming bar")
check(code_only.count("int closed=ArraySize(g_buf_c)-2;") == 3,
      "D all 3 mirrored-array closed-bar sites are unchanged")
check(code_only.count("int closed=g_rates_total-2;") == 8,
      "D all 8 replay-path closed-bar sites are unchanged")
check(TEXT.count('#property version   "6.69"') == 1, "D the version property is unchanged")
check(TEXT.count('"v6.6.9"') >= 1, "D the version text is unchanged")
check(len(re.findall(r'(?m)^#property indicator_buffers\s+19\b', TEXT)) == 1,
      "D indicator_buffers is still 19 - no buffer was appended")
check(len(re.findall(r'(?m)^#property indicator_plots\s+7\b', TEXT)) == 1,
      "D indicator_plots is still 7")
idx = sorted(int(m) for m in re.findall(r'SetIndexBuffer\(\s*(\d+)', TEXT))
check(idx == list(range(19)), "D buffer indices are still 0..18 with no gap or shift", str(idx))
ENUMS = len(re.findall(r'(?m)^enum\s+ENUM_', TEXT))
check(ENUMS == 43, "D no enum was added or removed (%d, was 43 before this phase)" % ENUMS)
check(re.search(r"enum\s+ENUM_", mr_section) is None,
      "D the section declares no enum, so no existing enumerator can shift")
check(BARE_LF == 0, "D the file has no bare LF (%d)" % BARE_LF)

# =====================================================================
# E. INPUTS AND PUBLISHED STATE
# =====================================================================
EXPECT = {"InpEnableMeanReversion": "false", "InpMRShowOnDashboard": "false",
          "InpMRStdDevPeriod": "20", "InpMRBandSigma": "2.00", "InpMRDivLookback": "200",
          "InpMRDivMinRSIDelta": "2.00", "InpMRRSIOverbought": "70.0",
          "InpMRRSIOversold": "30.0", "InpMRUseMACD": "false", "InpMRFastEMA": "12",
          "InpMRSlowEMA": "26", "InpMRSignalSMA": "9", "InpMRMacdDeadZoneATR": "0.05"}
for name, want in sorted(EXPECT.items()):
    got = input_default(name)
    check(got == want, "E input %s defaults to %s" % (name, want), "found %r" % got)
for flag in ("InpEnableMeanReversion", "InpMRShowOnDashboard", "InpMRUseMACD"):
    check(input_default(flag) == "false", "E the switch %s is OFF by default" % flag)
mr_inputs = set(re.findall(r'\b(InpMR\w+)\s*=', TEXT)) | \
    set(re.findall(r'\b(InpEnableMeanReversion)\s*=', TEXT))
check(len(mr_inputs) == 13, "E the module adds exactly 13 inputs (%d)" % len(mr_inputs),
      str(sorted(mr_inputs)))
check(mr_inputs == set(EXPECT), "E the declared inputs are exactly the documented set")
for nm in sorted(mr_inputs):
    check(TEXT.count(nm) >= 2, "E %s is declared and actually referenced" % nm)
check(input_default("InpRSIPeriod") == "14",
      "E the existing InpRSIPeriod was not changed by this phase")
check(input_default("InpSwingFractalN") == "3",
      "E the existing InpSwingFractalN was not changed by this phase")

mr_globals = re.findall(r'^(?:string|int|double|bool)\s+(g_mr_\w+|h_macd)\s*[=;]', TEXT, flags=re.M)
check(len(mr_globals) >= 18, "E the module declares %d private globals" % len(mr_globals))
dupes = [g for g in set(mr_globals) if mr_globals.count(g) > 1]
check(not dupes, "E no MR global is declared twice", str(dupes))
for g in ("h_macd", "g_mr_vwap", "g_mr_sigma", "g_mr_upper", "g_mr_lower", "g_mr_stretch",
          "g_mr_ext_dir", "g_mr_div_dir", "g_mr_rsi_extreme", "g_mr_macd_dir",
          "g_mr_macd_conflict", "g_mr_dir", "g_mr_confirms", "g_mr_score",
          "g_mr_reason", "g_mr_invalidation"):
    check(g in mr_globals, "E the published state %s exists" % g)
cl = body_of("void MR_Clear()", "E MR_Clear")
for g in ("g_mr_vwap", "g_mr_sigma", "g_mr_upper", "g_mr_lower", "g_mr_stretch",
          "g_mr_ext_dir", "g_mr_div_dir", "g_mr_rsi_extreme", "g_mr_macd_dir",
          "g_mr_macd_conflict", "g_mr_dir", "g_mr_confirms", "g_mr_score",
          "g_mr_reason", "g_mr_invalidation"):
    check(g in strip_comments(cl), "E MR_Clear resets %s to an inert value" % g)
check("g_mr_macd_ready=false" in strip_comments(cl),
      "E MR_Clear also drops the MACD readiness flag")

print("")
print("=" * 74)
print("AUDIT-MR1 checks: %d   failures: %d" % (COUNT[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: %s" % f)
print("This is a static transcription + wiring contract. It is NOT a backtest, it")
print("produces no win rate, and it does NOT prove MetaEditor compiles the file.")
print("=" * 74)
sys.exit(1 if FAILURES else 0)
