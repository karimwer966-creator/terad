#!/usr/bin/env python3
"""Independent contract for the ROLE that the ZRE signal path trades.

The indicator keeps one fact about a zone's role ("is this level support or
resistance right now?") and publishes it in two places that must agree:

  * the signal path            nadir2.mq5: ZRE_ProcessClosedBar() ->
                               ZRE_EffectiveSide() -> GetSignalDirection()
  * the arbiter zone registry  QSMC_Zones.mqh: EffectiveRole(birth, flipped)
                               fed by QSMC_ArbiterFeedAndFinalize()
                               (s.flipped = g_zre_status[i].flipped)

The documented rule is in nadir2.mq5 next to ENUM_ZRE_STATE:

    "FLIPPED = the zone was broken on an EARLIER closed bar and price now
     holds the other side; the level is then traded with the OPPOSITE role."

This file transcribes those functions from the .mq5 source (no MetaEditor here,
so a transcription is the only executable proof available) and asserts the
contract:

  R1. the role used for the direction must be the role the registry publishes;
  R2. a level broken by an earlier closed bar must be traded with the OPPOSITE
      role, symmetrically for BUY and SELL;
  R3. a retest of a broken support must never publish BUY (and the mirror);
  R4. ZRE_ST_FLIPPED must be reachable (it is not, if R1 is violated);
  R5. the chart/alert direction must equal the published direction;
  R6. the published direction must survive the arbiter LOCATION gate's role
      test, which reads the REGISTRY role.

Not a backtest, not a probability. Exit code 1 on any failure.
"""
import pathlib
import sys

SUPPORT, RESISTANCE = 0, 1

ST_IDLE, ST_APPROACHING, ST_TOUCHED_PREVIEW = 0, 1, 2
ST_REACTION_CONFIRMED, ST_BROKEN, ST_EXPIRED = 3, 4, 5
ST_HELD, ST_FLIPPED = 6, 7

FAILS = []
SRC = pathlib.Path(__file__).resolve().parent.parent / "nadir2.mq5"


def check(ok, name):
    print(("PASS" if ok else "FAIL") + "  " + name)
    if not ok:
        FAILS.append(name)


def opposite(side):
    if side == SUPPORT:
        return RESISTANCE
    if side == RESISTANCE:
        return SUPPORT
    return side


# --------------------------------------------------------------- params (test)
class Params:
    def __init__(self, **kw):
        self.approach_atr = 0.5
        self.break_atr = 0.3
        self.expire_bars = 500
        self.max_pen_atr = 0.5
        self.min_wick = 0.30
        self.inside_reclaim = False
        self.min_evidence = 2
        self.vol_support = 1.30
        self.min_score = 0
        self.entry_mode = 0          # ZRE_ENTRY_CLOSE
        self.project_bars = 20
        self.stop_zone_atr = 1.0
        self.conflict_gap = 8.0
        self.fresh_entry_bars = 3
        self.weak_zone = 60
        self.min_rr1 = 1.5
        self.sl_buf_atr = 0.1
        self.max_stop_atr = 3.0
        self.tick = 0.01
        for k, v in kw.items():
            setattr(self, k, v)


class Zone:
    def __init__(self, side, lo, hi, strength=80):
        self.side = side            # BIRTH role, exactly like SZREZone.side
        self.lo = lo
        self.hi = hi
        self.strength = strength
        self.id = ("S" if side == SUPPORT else "R") + "|%.2f|%.2f" % (lo, hi)


class Bar:
    def __init__(self, o, h, l, c):
        self.o, self.h, self.l, self.c = o, h, l, c


class Evidence:
    def __init__(self, engulf=False, displacement=False, volume_ratio=0.0):
        self.engulf = engulf
        self.displacement = displacement
        self.volume_ratio = volume_ratio
        self.volume_valid = volume_ratio > 0.0


# ------------------------------------------------- transcriptions from nadir2
def is_broken_now(z, prev_close, close_px, atr, p):
    """nadir2.mq5 ZRE_IsBrokenNow(): "from the near side, through the far edge"."""
    brk = p.break_atr * atr
    if prev_close >= z.lo and close_px < z.lo - brk:
        return True
    if prev_close <= z.hi and close_px > z.hi + brk:
        return True
    return False


def is_flipped(z, closes, closed, lookback, brk):
    """nadir2.mq5 ZRE_IsFlipped(): any EARLIER closed bar beyond the birth edge.

    Note the range: [closed-lookback .. closed-1]. The current closed bar is
    excluded, which is why this fact is "broken on an EARLIER closed bar".
    """
    first = max(0, closed - lookback)
    last = min(closed - 1, len(closes) - 1)
    for b in range(first, last + 1):
        if z.side == SUPPORT and closes[b] < z.lo - brk:
            return True
        if z.side == RESISTANCE and closes[b] > z.hi + brk:
            return True
    return False


def effective_side(z, close_px, prev_close, atr, p, flipped_closed):
    """nadir2.mq5 ZRE_EffectiveSide() - the role the signal path trades."""
    if is_broken_now(z, prev_close, close_px, atr, p):
        return opposite(z.side)
    if flipped_closed:
        return opposite(z.side)
    return z.side


def registry_role(z, flipped):
    """QSMC_Zones.mqh EffectiveRole(): the role the arbiter publishes."""
    return opposite(z.side) if flipped else z.side


def zone_gap(z, price):
    return max(0.0, max(z.lo - price, price - z.hi))


def classify_state(z, prev_close, close_px, atr, reaction, p):
    """nadir2.mq5 ZRE_ClassifyState() with age_bars = 0 and no live touch."""
    if is_broken_now(z, prev_close, close_px, atr, p) and (
            (z.side == SUPPORT and close_px < z.lo) or
            (z.side == RESISTANCE and close_px > z.hi)):
        return ST_BROKEN
    if reaction:
        return ST_REACTION_CONFIRMED
    if atr > 0.0 and zone_gap(z, close_px) <= p.approach_atr * atr:
        return ST_APPROACHING
    return ST_IDLE


def eval_rejection(z, side, bar, atr, ev, p):
    """nadir2.mq5 ZRE_EvalRejection() - `side` is the role actually traded."""
    if not (atr > 0.0):
        return False, {"reason": "NO ATR"}
    buy = (side == SUPPORT)
    rng = bar.h - bar.l
    if not (rng > 0.0):
        return False, {"reason": "RANGE"}
    body_hi, body_lo = max(bar.o, bar.c), min(bar.o, bar.c)
    wick = (body_lo - bar.l) if buy else (bar.h - body_hi)
    r = {"wick_ratio": wick / rng, "close_loc": (bar.c - bar.l) / rng,
         "touched": False, "reclaimed": False, "accepted": False,
         "sweep_reclaim": False, "penetration_atr": 0.0, "reason": ""}
    mid = (z.lo + z.hi) * 0.5
    if buy:
        level = mid if p.inside_reclaim else z.hi
        r["touched"] = bar.l <= z.hi
        r["penetration_atr"] = (z.lo - bar.l) / atr if bar.l < z.lo else 0.0
        r["reclaimed"] = bar.c >= level
        r["sweep_reclaim"] = bar.l < z.lo and r["reclaimed"]
    else:
        level = mid if p.inside_reclaim else z.lo
        r["touched"] = bar.h >= z.lo
        r["penetration_atr"] = (bar.h - z.hi) / atr if bar.h > z.hi else 0.0
        r["reclaimed"] = bar.c <= level
        r["sweep_reclaim"] = bar.h > z.hi and r["reclaimed"]
    if not r["touched"]:
        r["reason"] = "NO TOUCH"
        return False, r
    if r["penetration_atr"] > p.max_pen_atr + 1e-9:
        r["reason"] = "PENETRATION"
        return False, r
    if not r["reclaimed"]:
        r["accepted"] = True
        r["reason"] = "ACCEPTED"
        return False, r
    r["wick_ok"] = r["wick_ratio"] >= p.min_wick
    groups = (1 if r["wick_ok"] else 0) + (1 if ev.engulf else 0) + \
             (1 if r["sweep_reclaim"] else 0) + \
             (1 if ev.volume_valid and ev.volume_ratio >= p.vol_support else 0) + \
             (1 if ev.displacement else 0)
    r["groups"] = groups
    if not (r["wick_ok"] or ev.engulf or r["sweep_reclaim"]):
        r["reason"] = "NO PATTERN"
        return False, r
    if groups < p.min_evidence:
        r["reason"] = "EVIDENCE"
        return False, r
    r["valid"] = True
    return True, r


def signal_direction(role, state, close_px, lo, hi):
    """nadir2.mq5 GetSignalDirection() - the single source of truth."""
    if state == ST_EXPIRED:
        return 0
    if state == ST_BROKEN:
        if role == SUPPORT and close_px < lo:
            return -1
        if role == RESISTANCE and close_px > hi:
            return 1
        return 0
    if state == ST_FLIPPED:
        return 1 if role == SUPPORT else -1
    if role == SUPPORT:
        return 0 if close_px < lo else 1
    return 0 if close_px > hi else -1


def location_role_allows(direction, role, accepted):
    """QSMC_Gates.mqh CLocationGate 3.4: trade INTO the role is forbidden."""
    want_buy = direction > 0
    if want_buy and role == RESISTANCE and not accepted:
        return False
    if (not want_buy) and role == SUPPORT and not accepted:
        return False
    return True


# ------------------------------------------------------- the closed-bar pass
def closed_bar_pass(z, closes, closed, atr, ev, p, lookback=200):
    """Transcription of the per-zone body of ZRE_ProcessClosedBar()."""
    bar = closes["bar"]
    prev_close = closes["list"][closed - 1]
    flipped = is_flipped(z, closes["list"], closed, lookback, p.break_atr * atr)

    # --- what the code does today: the side is resolved BEFORE `flipped` is
    # --- known, so only a break on this very bar reverses the role.
    side_today = effective_side(z, bar.c, prev_close, atr, p, False)
    ok_today, rj_today = eval_rejection(z, side_today, bar, atr, ev, p)
    dir_today = 0
    if ok_today:
        dir_today = signal_direction(side_today,
                                     classify_state(z, prev_close, bar.c, atr, True, p),
                                     bar.c, z.lo, z.hi)
        if dir_today != (1 if side_today == SUPPORT else -1):
            ok_today, dir_today = False, 0

    # --- the contract: one role, resolved from BOTH closed-bar facts, which is
    # --- exactly what the registry publishes as EffectiveRole().
    side_fixed = effective_side(z, bar.c, prev_close, atr, p, flipped)
    ok_fixed, rj_fixed = eval_rejection(z, side_fixed, bar, atr, ev, p)
    base = classify_state(z, prev_close, bar.c, atr, ok_fixed, p)
    if base not in (ST_EXPIRED, ST_BROKEN, ST_REACTION_CONFIRMED) and \
            rj_fixed.get("touched") and rj_fixed.get("reclaimed") and \
            not rj_fixed.get("accepted"):
        base = ST_HELD
    if side_fixed != z.side and not is_broken_now(z, prev_close, bar.c, atr, p) \
            and base != ST_REACTION_CONFIRMED:
        base = ST_FLIPPED
    dir_fixed = 0
    if ok_fixed:
        dir_fixed = signal_direction(side_fixed, base, bar.c, z.lo, z.hi)
        if dir_fixed != (1 if side_fixed == SUPPORT else -1):
            ok_fixed, dir_fixed = False, 0

    # --- the chart/alert path (ZRE_AlertState) derives its own direction
    chart_dir = (1 if opposite(z.side) == SUPPORT else -1) if flipped else \
                (1 if z.side == SUPPORT else -1)

    return {
        "flipped": flipped,
        "registry_role": registry_role(z, flipped),
        "side_today": side_today, "ok_today": ok_today, "dir_today": dir_today,
        "rj_today": rj_today,
        "side_fixed": side_fixed, "ok_fixed": ok_fixed, "dir_fixed": dir_fixed,
        "rj_fixed": rj_fixed, "state_fixed": base, "chart_dir": chart_dir,
    }


# ------------------------------------------------- the same contract, in source
def body(text, decl):
    """Slice a DEFINITION out of the MQL5 source (skip the prototype first)."""
    i = decl_at = 0
    while True:
        i = text.find(decl, decl_at)
        if i < 0:
            return ""
        decl_at = i + len(decl)
        j = text.find("{", i)
        semi = text.find(";", i)
        if j >= 0 and (semi < 0 or j < semi):
            break                      # a real definition, not a prototype
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[j:k + 1]
    return ""


def source_checks(text):
    """The transcription above is only a claim: these pin the real code."""
    eff = body(text, "ENUM_ZRE_SIDE ZRE_EffectiveSide(")
    check(eff != "", "source: ZRE_EffectiveSide() exists in nadir2.mq5")
    check("ZRE_IsFlipped" in eff or "flipped" in eff,
          "source: ZRE_EffectiveSide() takes the EARLIER-closed-bar flip into account")

    proc = body(text, "void ZRE_ProcessClosedBar(")
    i_flip = proc.find("ZRE_IsFlipped(")
    i_side = proc.find("zeff.side=")
    check(i_flip >= 0 and i_side >= 0 and i_flip < i_side,
          "source: the closed-bar flip is resolved BEFORE the traded side in "
          "ZRE_ProcessClosedBar() (flip@%d side@%d)" % (i_flip, i_side))
    check("st.flipped=flipped_closed" in proc.replace(" ", ""),
          "source: st.flipped reuses that ONE fact, it is not recomputed")

    alert = body(text, "void ZRE_AlertState(")
    check("ZRE_EffectiveSide(" in alert,
          "source: ZRE_AlertState() uses the same resolver, it does not "
          "re-derive the direction from `flipped` on its own")


# ------------------------------------------------------------------ scenarios
ATR = 1.0
P = Params()

# A support 100-101 that an EARLIER closed bar broke DOWN (close 98.2, two bars
# before the one under test - ZRE_IsFlipped excludes the current closed bar).
# Now price comes back up to the band and closes back under it: the classic
# "broken support retested from below" SELL.
FLIP_SUPPORT_CLOSES = [100.6, 100.4, 98.2, 98.6, 99.6]
FLIP_SUPPORT_BAR = Bar(o=98.9, h=101.2, l=98.8, c=99.6)
SELL_EV = Evidence(displacement=True)

# The exact mirror: resistance 100-101 broken UP (close 102.8), price comes back
# down to the band and closes back above it: broken resistance retested = BUY.
FLIP_RES_CLOSES = [100.4, 100.6, 102.8, 102.4, 101.4]
FLIP_RES_BAR = Bar(o=102.1, h=102.2, l=99.8, c=101.4)
BUY_EV = Evidence(displacement=True)

# A broken support with a BULLISH close back above the band (a wick + a
# displacement candle, so the birth-role reading has every group it needs).
FLIP_UP_BAR = Bar(o=100.9, h=101.9, l=100.0, c=101.5)


def main():
    text = SRC.read_text(encoding="utf-8", errors="replace") if SRC.exists() else ""
    check(text != "", "source: nadir2.mq5 is readable next to tools/")
    source_checks(text)

    zs = Zone(SUPPORT, 100.0, 101.0)
    zr = Zone(RESISTANCE, 100.0, 101.0)

    # ---- 1) the direction truth table (role x state)
    check(signal_direction(SUPPORT, ST_REACTION_CONFIRMED, 101.0, 100.0, 101.0) == 1,
          "support rejection -> BUY")
    check(signal_direction(RESISTANCE, ST_REACTION_CONFIRMED, 100.5, 100.0, 101.0) == -1,
          "resistance rejection -> SELL")
    check(signal_direction(SUPPORT, ST_REACTION_CONFIRMED, 99.0, 100.0, 101.0) == 0,
          "a close through a support band is a break, never a buy")
    check(signal_direction(RESISTANCE, ST_REACTION_CONFIRMED, 102.0, 100.0, 101.0) == 0,
          "a close through a resistance band is a break, never a sell")
    check(signal_direction(SUPPORT, ST_FLIPPED, 101.0, 100.0, 101.0) == 1 and
          signal_direction(RESISTANCE, ST_FLIPPED, 100.0, 100.0, 101.0) == -1,
          "FLIPPED trades the CURRENT role, not the birth role")

    # ---- 2) one role: the signal path and the registry must agree
    sell = closed_bar_pass(zs, {"list": FLIP_SUPPORT_CLOSES, "bar": FLIP_SUPPORT_BAR},
                           len(FLIP_SUPPORT_CLOSES) - 1, ATR, SELL_EV, P)
    buy = closed_bar_pass(zr, {"list": FLIP_RES_CLOSES, "bar": FLIP_RES_BAR},
                          len(FLIP_RES_CLOSES) - 1, ATR, BUY_EV, P)
    check(sell["flipped"] and buy["flipped"],
          "both scenarios are genuinely 'broken on an EARLIER closed bar'")
    check(sell["side_fixed"] == sell["registry_role"],
          "SELL scenario: the traded role equals the role the registry publishes")
    check(buy["side_fixed"] == buy["registry_role"],
          "BUY scenario: the traded role equals the role the registry publishes")

    # ---- 3) the retest of a broken level must trade the NEW role, mirrored
    check(sell["ok_fixed"] and sell["dir_fixed"] == -1,
          "R2 SELL: a broken support retested from below publishes SELL (got %s/%d)"
          % (sell["ok_fixed"], sell["dir_fixed"]))
    check(buy["ok_fixed"] and buy["dir_fixed"] == 1,
          "R2 BUY: a broken resistance retested from above publishes BUY (got %s/%d)"
          % (buy["ok_fixed"], buy["dir_fixed"]))
    check(sell["dir_fixed"] == -buy["dir_fixed"],
          "BUY and SELL are exact mirrors of each other")

    # ---- 4) a broken support never publishes BUY on a bullish close
    up = closed_bar_pass(zs, {"list": FLIP_SUPPORT_CLOSES[:-1] + [FLIP_UP_BAR.c],
                              "bar": FLIP_UP_BAR},
                         len(FLIP_SUPPORT_CLOSES) - 1, ATR,
                         Evidence(displacement=True), P)
    check(not (up["ok_fixed"] and up["dir_fixed"] == 1),
          "R3 a BUY is never published at a support that already broke down")

    # ---- 5) FLIPPED must be reachable
    far = Bar(o=97.4, h=97.9, l=97.2, c=97.5)
    away = closed_bar_pass(zs, {"list": FLIP_SUPPORT_CLOSES, "bar": far},
                           len(FLIP_SUPPORT_CLOSES) - 1, ATR, Evidence(), P)
    check(away["state_fixed"] == ST_FLIPPED,
          "R4 ZRE_ST_FLIPPED is reachable on a level broken by an EARLIER bar "
          "(state=%d)" % away["state_fixed"])
    check(sell["side_today"] != sell["side_fixed"],
          "R4b the role is reversed off the break bar "
          "(today=%d fixed=%d)" % (sell["side_today"], sell["side_fixed"]))

    # ---- 6) the chart/alert direction must equal the published direction
    check(sell["chart_dir"] == (sell["dir_fixed"] if sell["ok_fixed"] else 0) and
          buy["chart_dir"] == (buy["dir_fixed"] if buy["ok_fixed"] else 0),
          "R5 the chart/alert direction agrees with the published signal")

    # ---- 7) the arbiter LOCATION gate must allow what the engine publishes
    for tag, s in (("SELL", sell), ("BUY", buy)):
        if not s["ok_fixed"]:
            check(False, "R6 %s: nothing was published to gate" % tag)
            continue
        check(location_role_allows(s["dir_fixed"], s["registry_role"], False),
              "R6 %s: the published direction survives LOCATION gate 3.4" % tag)

    # ---- documentary only (frozen snapshot of the pre-fix path, NOT asserted)
    print("-" * 72)
    print("pre-fix path, for the record (not asserted):")
    for tag, s, z in (("SELL retest", sell, zs), ("BUY retest", buy, zr)):
        print("  %-12s birth role=%d published=%s dir=%+d  | registry role=%d"
              % (tag, z.side, "yes" if s["ok_today"] else "no", s["dir_today"],
                 s["registry_role"]))
    print("  BUY at a broken support: published=%s dir=%+d (a BUY into the "
          "level's underside)" % ("yes" if up["ok_today"] else "no",
                                  up["dir_today"]))
    print("-" * 72)
    if FAILS:
        print("RESULT: %d failed" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        return 1
    print("RESULT: all role/direction contracts hold")
    print("This is a transcription contract, not a backtest and not a win rate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
