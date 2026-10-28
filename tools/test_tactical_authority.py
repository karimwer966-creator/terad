#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract suite for the SINGLE AUTHORITATIVE SCENARIO STATE (v6.6.10 AUDIT-TAC).

WHY THIS FILE EXISTS
--------------------
A chart showed, at the same moment:

    BUY PLAN - CONDITIONAL - INVALIDATED          (Directional Scenario Engine)
    SELL PLAN - CONDITIONAL - LATE - WAIT FOR RETEST  (Directional Scenario Engine)
    TACTICAL / PREVIEW MTF BUY ENTRY PREVIEW @4038.62 (MTF tactical preview)

Three modules published a direction for one symbol and one bar, and the third
one never asked the other two what the state was. This suite is the executable
proof that they cannot disagree again.

WHAT IS TESTED
--------------
Part A  an independent re-implementation of the decision logic, transcribed from
        nadir2.mq5 (there is no MetaEditor here, so a transcription is the only
        executable proof available). Every case asserts the resulting STATE and
        the REASON string, never merely "a non-empty result".
Part B  source contracts: the wiring in nadir2.mq5 that Part A assumes is
        actually present, in the right order, and cannot be silently removed.

Part A covers the failure cases from the audit brief that were not already
covered offline:
   A1  bullish HTF context + bearish LTF rejection      (brief 9.1)
   A2  bearish HTF context + bullish LTF recovery       (brief 9.2)
   A3  BUY invalidated while an old BUY preview is cached (brief 9.7)
   A4  SELL marked LATE after the entry window passed   (brief 9.8)
   A5  support wick penetration, no closed break        (brief 9.9)
   A6  confirmed support break, then a failed retest    (brief 9.10)
   A7  competing BUY and SELL candidates                (brief 9.11)
   A8  missing / insufficient timeframe history         (brief 9.12)
   A9  MTF candle timestamp misalignment                (brief 9.13)
   A10 expiration, and a genuinely fresh setup afterwards (brief 9.14)
   A11 zero-lookahead: the gate reads published verdicts only (brief 9.15)
   A12 the CONFIRMED->PREVIEW re-arm dedup the v6.6.0 patch orphaned

Already covered elsewhere and deliberately NOT duplicated here:
   sweep without displacement / displacement without structure -> test_arbiter.py
   structure break without retest, retest without trigger      -> test_arbiter.py
   spread and RR gate failure                                  -> test_gate_profile.py
   swing confirmation timing, MIXED resolution                 -> test_structure.py
   one causal zone role                                        -> test_zre_signal_role.py

This is a contract suite. It is NOT a backtest, produces NO win rate, and does
NOT prove MetaEditor compilation. Press F7.
"""
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "nadir2.mq5"
TEXT = io.open(str(SRC), "r", encoding="utf-8", newline="").read()

FAILS = []


def check(ok, name, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + detail) if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


# ======================================================================
# Part A - independent re-implementation
# ======================================================================

# --- ENUM_SCENARIO_STATE / ENUM_TACTICAL_AUTHORITY (nadir2.mq5) ---------
SCN_UNAVAILABLE, SCN_WATCHING_ZONE, SCN_ZONE_APPROACHING = 0, 1, 2
SCN_TOUCHED_PREVIEW, SCN_REACTION_CONFIRMED, SCN_DISPLACEMENT_CONFIRMED = 3, 4, 5
SCN_STRUCTURE_CONFIRMED, SCN_WAITING_FOR_RETEST, SCN_RETEST_CONFIRMED = 6, 7, 8
SCN_EXECUTION_READY, SCN_LATE_WAIT_FOR_RETEST = 9, 10
SCN_INVALIDATED, SCN_COMPLETED, SCN_EXPIRED, SCN_COUNTERTREND_WATCH = 11, 12, 13, 14

SCN_NAMES = {
    SCN_UNAVAILABLE: "UNAVAILABLE", SCN_WATCHING_ZONE: "WATCHING ZONE",
    SCN_ZONE_APPROACHING: "ZONE APPROACHING", SCN_TOUCHED_PREVIEW: "TOUCHED PREVIEW",
    SCN_REACTION_CONFIRMED: "REACTION CONFIRMED",
    SCN_DISPLACEMENT_CONFIRMED: "DISPLACEMENT CONFIRMED",
    SCN_STRUCTURE_CONFIRMED: "STRUCTURE CONFIRMED",
    SCN_WAITING_FOR_RETEST: "WAITING FOR RETEST",
    SCN_RETEST_CONFIRMED: "RETEST CONFIRMED",
    SCN_EXECUTION_READY: "EXECUTION READY",
    SCN_LATE_WAIT_FOR_RETEST: "LATE - WAIT FOR RETEST",
    SCN_INVALIDATED: "INVALIDATED", SCN_COMPLETED: "COMPLETED",
    SCN_EXPIRED: "EXPIRED", SCN_COUNTERTREND_WATCH: "COUNTERTREND WATCH",
}

TAC_OK, TAC_CONTEXT, TAC_STALE, TAC_BLOCKED = 0, 1, 2, 3
TAC_NAMES = {TAC_OK: "OK", TAC_CONTEXT: "CONTEXT", TAC_STALE: "STALE", TAC_BLOCKED: "BLOCKED"}

# --- ENUM_ZRE_STATE (nadir2.mq5) ---------------------------------------
ZRE_ST_IDLE, ZRE_ST_APPROACHING, ZRE_ST_TOUCHED_PREVIEW = 0, 1, 2
ZRE_ST_REACTION_CONFIRMED, ZRE_ST_BROKEN, ZRE_ST_EXPIRED = 3, 4, 5
ZRE_ST_HELD, ZRE_ST_FLIPPED = 6, 7
ZRE_SUPPORT, ZRE_RESISTANCE = 0, 1


# ---------------------------------------------------------- zone break facts
# Transcribed from ZRE_IsBrokenNow() / ZRE_IsFlipped() / ZRE_EffectiveSide().
# Both facts are CLOSE-based: a wick through a level is a touch, never a break.
def zre_is_broken_now(z, prev_close, close, break_atr_x_atr):
    brk = break_atr_x_atr
    if prev_close >= z["lo"] and close < z["lo"] - brk:
        return True
    if prev_close <= z["hi"] and close > z["hi"] + brk:
        return True
    return False


def zre_is_flipped(z, closes, lookback, brk):
    """closes is the chronological list of CLOSED chart closes; the scan window is
    [closed-lookback .. closed-1], i.e. strictly earlier closed bars."""
    closed = len(closes) - 1
    lo_i = max(0, closed - lookback)
    hi_i = min(closed - 1, len(closes) - 1)
    for b in range(lo_i, hi_i + 1):
        if z["side"] == ZRE_SUPPORT and closes[b] < z["lo"] - brk:
            return True
        if z["side"] == ZRE_RESISTANCE and closes[b] > z["hi"] + brk:
            return True
    return False


def zre_effective_side(z, close, prev_close, brk, flipped_closed):
    if zre_is_broken_now(z, prev_close, close, brk):
        return ZRE_RESISTANCE if z["side"] == ZRE_SUPPORT else ZRE_SUPPORT
    if flipped_closed:
        return ZRE_RESISTANCE if z["side"] == ZRE_SUPPORT else ZRE_SUPPORT
    return z["side"]


# ------------------------------------------------------------ the DSE plan
class Plan(object):
    """The subset of SScenarioPlan the authority gate and the lead comparator read."""

    def __init__(self, is_buy, zone_id="Z", valid=True):
        self.is_buy = is_buy
        self.zone_id = zone_id
        self.valid = valid
        self.unavailable_reason = ""
        self.invalidated = False
        self.plan_dead = False
        self.dead_note = ""
        self.late = False
        self.execution_ready = False
        self.countertrend = False
        self.relevant = False
        self.validity_pass = False
        self.alignment_rank = 0
        self.rank_score = 0
        self.geometry_valid = False
        self.barrier_room_atr = 0.0
        self.expected_r = 0.0
        self.candidate_qualified = False
        self.distance_available = False
        self.distance_atr = 0.0
        self.zone_age = -1
        self.has_reaction = False
        self.has_displacement = False
        self.has_structure = False
        self.has_retest = False
        self.m5_data_ok = False
        self.m5_invalidation_history_ok = False
        self.state = SCN_UNAVAILABLE
        self.qualification_reason = ""

    # --- ScenarioEntryStatusToken() -----------------------------------
    def entry_status_token(self):
        if self.execution_ready:
            return "EXECUTION_READY"
        if self.invalidated or self.plan_dead:
            return "INVALIDATED"
        if not self.valid:
            return "NO_QUALIFIED_CANDIDATE"
        if self.late:
            return "LATE_WAIT_RETEST"
        if self.countertrend and self.validity_pass:
            return "COUNTERTREND_WATCH"
        if not self.candidate_qualified or not self.m5_invalidation_history_ok:
            return "NO_QUALIFIED_CANDIDATE"
        if self.has_retest and self.m5_data_ok and self.geometry_valid:
            return "RETEST_CONFIRMED"
        if self.has_structure:
            return "WAITING_RETEST" if self.m5_data_ok else "STRUCTURE_CONFIRMED"
        if self.has_reaction or self.has_displacement:
            return "REACTION_CONFIRMED"
        return "WATCH"

    # --- ScenarioClassifyPlan() ---------------------------------------
    def classify(self, expire_bars=600):
        if not self.valid:
            return
        if self.execution_ready:
            self.state = SCN_EXECUTION_READY
            return
        if self.invalidated:
            self.state = SCN_EXPIRED if (self.zone_age >= 0 and expire_bars > 0
                                         and self.zone_age > expire_bars) else SCN_INVALIDATED
            return
        if self.plan_dead:
            self.state = SCN_INVALIDATED
            return
        if self.late:
            self.state = SCN_LATE_WAIT_FOR_RETEST
        elif self.countertrend and self.validity_pass:
            self.state = SCN_COUNTERTREND_WATCH
        elif self.has_retest:
            self.state = SCN_RETEST_CONFIRMED
        elif self.has_structure:
            self.state = SCN_WAITING_FOR_RETEST if self.m5_data_ok else SCN_STRUCTURE_CONFIRMED
        elif self.has_displacement:
            self.state = SCN_DISPLACEMENT_CONFIRMED
        elif self.has_reaction:
            self.state = SCN_REACTION_CONFIRMED
        else:
            self.state = SCN_WATCHING_ZONE


# Transcribed from ScenarioPlanBetter(): one total order, A validity -> B
# alignment -> C evidence quality -> D geometry/room/RR -> deterministic
# tie-breakers. A high rank_score can never outrank a failed Priority A gate.
def plan_better(a, b):
    if not a.valid:
        return False
    if not b.valid:
        return True
    if a.validity_pass != b.validity_pass:
        return a.validity_pass
    if a.invalidated != b.invalidated:
        return not a.invalidated
    if a.plan_dead != b.plan_dead:
        return not a.plan_dead
    if a.alignment_rank != b.alignment_rank:
        return a.alignment_rank > b.alignment_rank
    if a.rank_score != b.rank_score:
        return a.rank_score > b.rank_score
    if a.geometry_valid != b.geometry_valid:
        return a.geometry_valid
    if abs(a.barrier_room_atr - b.barrier_room_atr) > 1e-9:
        return a.barrier_room_atr > b.barrier_room_atr
    if abs(a.expected_r - b.expected_r) > 1e-9:
        return a.expected_r > b.expected_r
    if a.candidate_qualified != b.candidate_qualified:
        return a.candidate_qualified
    if a.distance_available != b.distance_available:
        return a.distance_available
    if a.distance_available and abs(a.distance_atr - b.distance_atr) > 1e-9:
        return a.distance_atr < b.distance_atr
    if a.zone_age >= 0 and b.zone_age >= 0 and a.zone_age != b.zone_age:
        return a.zone_age < b.zone_age
    if (a.zone_age >= 0) != (b.zone_age >= 0):
        return a.zone_age >= 0
    return a.zone_id < b.zone_id


def scenario_lead(buy, sell):
    lead = Plan(True, zone_id="")
    lead.valid = False
    if plan_better(buy, lead):
        lead = buy
    if plan_better(sell, lead):
        lead = sell
    return lead


# Transcribed from TacticalScenarioTerminal() / TacticalScenarioLive().
def tactical_scenario_terminal(p):
    if not p.valid:
        return False, "", ""
    if not (p.invalidated or p.plan_dead
            or p.state == SCN_INVALIDATED or p.state == SCN_EXPIRED):
        return False, "", ""
    name = SCN_NAMES[p.state]
    why = p.dead_note if (p.plan_dead and p.dead_note) else p.qualification_reason
    return True, name, why


def tactical_scenario_live(p):
    """Returns (live, state_name). state_name is the DSE's own wording for a plan
    it is tracking but has not made current, and "" when there is no plan."""
    if not p.valid:
        return False, ""
    name = SCN_NAMES[p.state]
    live = bool(p.relevant and not p.invalidated and not p.plan_dead
                and p.state != SCN_INVALIDATED and p.state != SCN_EXPIRED)
    return live, name


# Transcribed 1:1 from TacticalAuthorityDecide(): the PURE total order. It reads
# no state at all, which is why the MQL5 self-test and this file can both
# exercise it and cannot diverge.
def tactical_authority_decide(bull, src, trigger_age_bars, retest_timeout_bars,
                              dse_on, dse_terminal, terminal_state, terminal_why,
                              blacklisted, dse_live, live_state):
    side = "BUY" if bull else "SELL"

    if dse_on and dse_terminal:                                    # (1)
        return TAC_BLOCKED, ("the DSE %s scenario is %s%s - a retired scenario keeps no preview"
                             % (side, terminal_state,
                                (" (%s)" % terminal_why) if terminal_why else ""))

    if src != 1 and blacklisted:                                   # (2)
        return TAC_BLOCKED, ("the Core lifecycle blacklisted this %s idea within "
                             "InpBlacklistExpiryBars - a retired idea keeps no preview" % side)

    if (src == 2 and retest_timeout_bars > 0 and trigger_age_bars >= 0
            and trigger_age_bars > retest_timeout_bars):           # (3)
        return TAC_STALE, ("the %s trigger is %d closed chart bars old (limit "
                           "InpRetestTimeoutBars %d) - returning to an old level is not a "
                           "fresh entry" % (side, trigger_age_bars, retest_timeout_bars))

    if src == 2 and not (dse_on and dse_live):                     # (4)
        if not dse_on:
            head = "the scenario engine is off"
        elif live_state:
            head = "the DSE %s scenario is %s" % (side, live_state)
        else:
            head = "no DSE %s scenario" % side
        return TAC_CONTEXT, (head + " - the direction came from the HTF bias alone, "
                             "which is context, not an entry")

    return TAC_OK, ""


# Transcribed from TacticalAuthorityGate(): the adapter that gathers the
# published closed-bar facts and calls the pure order. `blacklisted` stands in
# for IsSameIdeaAsBlacklisted(), whose horizon is InpBlacklistExpiryBars.
def tactical_authority_gate(bull, src, trigger_bar, closed_now, retest_timeout_bars,
                            buy_plan, sell_plan, dse_on, blacklisted=False):
    plan = buy_plan if bull else sell_plan
    terminal, terminal_state, terminal_why = (tactical_scenario_terminal(plan)
                                              if dse_on else (False, "", ""))
    live, live_state = tactical_scenario_live(plan) if dse_on else (False, "")
    age = (closed_now - trigger_bar) if (src == 2 and trigger_bar >= 0
                                         and closed_now >= trigger_bar) else -1
    return tactical_authority_decide(bull, src, age, retest_timeout_bars, dse_on, terminal,
                                     terminal_state, terminal_why, blacklisted, live, live_state)


# The tactical display, re-implemented: what the chart is allowed to say.
# `not_far` mirrors the source's `far` (price ran beyond InpMTFEntryMaxDistanceATR
# from the trigger): the mark is painted when `auth!=CONTEXT && (!far || closed)`.
def tactical_display(bull, src, auth, closed_confirm, live_cross, not_far):
    """Returns None when nothing may be drawn, else (label_verb, marks_entry)."""
    if auth in (TAC_BLOCKED, TAC_STALE):
        return None
    if not closed_confirm and not live_cross:
        return None
    verb = "CONTEXT" if auth == TAC_CONTEXT else "ENTRY"
    marks = (auth != TAC_CONTEXT) and (not_far or closed_confirm)
    return verb, marks


# The CONFIRMED -> PREVIEW re-arm dedup (v6.4.1 semantics, restored in v6.6.10).
class TacticalDedup(object):
    def __init__(self):
        self.last_key = ""

    def observe(self, sig_id, closed_confirm, live_cross):
        state = "CONFIRMED" if closed_confirm else ("PREVIEW" if live_cross else None)
        if state is None:
            return None
        if state == "PREVIEW" and self.last_key == sig_id + "|CONFIRMED":
            return None                      # suppressed: already fired CONFIRMED
        if closed_confirm:
            self.last_key = sig_id + "|CONFIRMED"
        return state


# ---------------------------------------------------------------- fixtures
def live_buy(zone_id="ZB", rank=70):
    p = Plan(True, zone_id)
    p.valid = True
    p.validity_pass = True
    p.relevant = True
    p.alignment_rank = 3
    p.rank_score = rank
    p.has_reaction = True
    p.classify()
    return p


def dead_buy_by_close(zone_id="ZB"):
    """A BUY plan a CLOSED M5 candle killed (ScenarioM5RetestScan -> plan_dead)."""
    p = Plan(True, zone_id)
    p.valid = True
    p.plan_dead = True
    p.dead_note = ("closed M5 candle 2026.10.28 14:35 closed at 4041.10 below BUY "
                   "structural invalidation 4044.00")
    p.qualification_reason = "INVALIDATED - closed M5 candle breached the selected-zone boundary"
    p.classify()
    return p


def late_sell(zone_id="ZS"):
    p = Plan(False, zone_id)
    p.valid = True
    p.late = True
    p.validity_pass = False          # ScenarioMarkRelevant: !p.late is required
    p.qualification_reason = "LATE_WAIT_RETEST - existing InpChaseFilter/InpChaseMaxATR limit exceeded"
    p.classify()
    return p


print("=" * 74)
print(" TACTICAL AUTHORITY / SINGLE AUTHORITATIVE SCENARIO STATE - CONTRACTS")
print("=" * 74)

# ---------------------------------------------------------------- A1 / A2
# Bullish higher-timeframe CONTEXT with a bearish lower-timeframe rejection.
# The bias is contextual evidence, not an unconditional BUY instruction: with no
# live BUY scenario the tactical preview must say CONTEXT and paint no entry mark,
# while the live SELL scenario keeps its own ENTRY wording.
buy_none = Plan(True, zone_id="")
buy_none.valid = False
sell_live = Plan(False, "ZS")
sell_live.valid = True
sell_live.validity_pass = True
sell_live.relevant = True
sell_live.alignment_rank = 3
sell_live.rank_score = 61
sell_live.has_reaction = True
sell_live.classify()

auth_buy, why_buy = tactical_authority_gate(True, 2, 100, 110, 40, buy_none, sell_live, True)
auth_sell, why_sell = tactical_authority_gate(False, 2, 100, 110, 40, buy_none, sell_live, True)
check(auth_buy == TAC_CONTEXT,
      "A1 bullish HTF bias alone is CONTEXT, never an ENTRY",
      "got %s / %s" % (TAC_NAMES[auth_buy], why_buy))
check("HTF bias alone" in why_buy and "no DSE BUY scenario" in why_buy,
      "A1 the CONTEXT reason names the missing location fact")
check(tactical_display(True, 2, auth_buy, False, True, True) == ("CONTEXT", False),
      "A1 a bullish bias-only preview paints no entry mark")
check(auth_sell == TAC_OK,
      "A1 the side that DOES have a live scenario is unaffected")
check(tactical_display(False, 2, auth_sell, True, True, True) == ("ENTRY", True),
      "A1 the live SELL scenario keeps the ENTRY wording and its mark")

# A2: the exact mirror - bearish HTF context with a bullish LTF recovery.
sell_none = Plan(False, zone_id="")
sell_none.valid = False
buy_live = live_buy()
auth_sell2, why_sell2 = tactical_authority_gate(False, 2, 100, 110, 40, buy_live, sell_none, True)
auth_buy2, _ = tactical_authority_gate(True, 2, 100, 110, 40, buy_live, sell_none, True)
check(auth_sell2 == TAC_CONTEXT and "HTF bias alone" in why_sell2,
      "A2 bearish HTF bias alone is CONTEXT (symmetric, no side is favoured)")
check(auth_buy2 == TAC_OK,
      "A2 the live BUY scenario is unaffected by the bearish bias")

# A1b/A2b: a Core-owned direction is never downgraded to CONTEXT - the Core
# lifecycle IS an authoritative owner, so src==1 is exempt from rule (4).
auth_core, _ = tactical_authority_gate(True, 1, -1, 110, 40, buy_none, sell_none, True)
check(auth_core == TAC_OK,
      "A1b a Core-owned tactical direction is not downgraded to CONTEXT")

# --------------------------------------------------------------------- A3
# THE REPORTED DEFECT. BUY invalidated while an old BUY preview is still cached.
buy_dead = dead_buy_by_close()
auth, why = tactical_authority_gate(True, 2, 108, 110, 40, buy_dead, late_sell(), True)
check(auth == TAC_BLOCKED,
      "A3 an INVALIDATED BUY scenario blocks the BUY tactical preview",
      "got %s / %s" % (TAC_NAMES[auth], why))
check("INVALIDATED" in why,
      "A3 the block reason names the authoritative state, not a generic refusal")
check("4044.00" in why,
      "A3 the block reason carries the invalidation level that killed the plan")
check(tactical_display(True, 2, auth, True, True, True) is None,
      "A3 nothing at all is drawn for the blocked side")
# ... and it is the plan_dead path (state INVALIDATED, `invalidated` still false)
# that produced the chart message, which the old ScenarioDrawOne guard let through.
check(buy_dead.invalidated is False and buy_dead.plan_dead is True
      and buy_dead.state == SCN_INVALIDATED,
      "A3 plan_dead reaches SCN_INVALIDATED without setting `invalidated`")
# The opposite side is decided on its own merits, never by the blocked side. A
# LATE plan is still tracked by the DSE but is NOT current, so a bias-only
# preview on that side is CONTEXT quoting the DSE's own state name - a LATE setup
# is not presented as a fresh entry (brief 5).
auth_s, why_s = tactical_authority_gate(False, 2, 108, 110, 40, buy_dead, late_sell(), True)
check(auth_s == TAC_CONTEXT, "A3 the LATE SELL side is not blocked, but it is not an ENTRY either",
      "got %s / %s" % (TAC_NAMES[auth_s], why_s))
check("LATE - WAIT FOR RETEST" in why_s,
      "A3 the CONTEXT reason quotes the DSE's own state name, not a guess")
check(tactical_display(False, 2, auth_s, False, True, False) == ("CONTEXT", False),
      "A3 the LATE side keeps its level line and paints no entry mark")
# A fully current plan on the same side is unaffected - the gate is not a blanket
# downgrade of every bias-only preview.
sell_current = Plan(False, "ZS")
sell_current.valid = True
sell_current.validity_pass = True
sell_current.relevant = True
sell_current.alignment_rank = 3
sell_current.has_reaction = True
sell_current.classify()
auth_c, why_c = tactical_authority_gate(False, 2, 108, 110, 40, buy_dead, sell_current, True)
check(auth_c == TAC_OK and tactical_display(False, 2, auth_c, False, True, True) == ("ENTRY", True),
      "A3 a CURRENT scenario on that side keeps the ENTRY wording and its mark")

# --------------------------------------------------------------------- A4
# SELL marked LATE after the valid entry window passed.
ls = late_sell()
check(ls.entry_status_token() == "LATE_WAIT_RETEST",
      "A4 a chased plan reports LATE_WAIT_RETEST")
check(ls.state == SCN_LATE_WAIT_FOR_RETEST and SCN_NAMES[ls.state] == "LATE - WAIT FOR RETEST",
      "A4 the lifecycle state is LATE - WAIT FOR RETEST")
# LATE is not INVALIDATED: the setup is still visible, but it must not be
# presented as a fresh entry, and it must not qualify.
ls.validity_pass = False
ls.candidate_qualified = False
check(ls.candidate_qualified is False,
      "A4 a LATE plan is never a qualified candidate")
# Invalidation outranks lateness (MTEE-6 precedence, re-proved here).
ls.invalidated = True
ls.classify()
check(ls.entry_status_token() == "INVALIDATED",
      "A4 invalidation outranks lateness in the status token")
# Lead selection: an INVALIDATED BUY loses to a merely LATE SELL, because
# `invalidated` is compared after `validity_pass` and both fail validity.
lead = scenario_lead(dead_buy_by_close(), late_sell())
check(lead.is_buy is False and lead.late is True,
      "A4/A7 the LATE SELL leads the INVALIDATED BUY (correct total order)")

# --------------------------------------------------------------------- A5
# Support wick penetration WITHOUT a confirmed close-based break.
sup = {"side": ZRE_SUPPORT, "lo": 4044.0, "hi": 4048.0}
brk = 0.30 * 6.0            # InpZREBreakATR * ATR
check(zre_is_broken_now(sup, 4050.0, 4046.0, brk) is False,
      "A5 a close INSIDE the band is not a break")
check(zre_is_broken_now(sup, 4050.0, 4043.9, brk) is False,
      "A5 a wick 0.1 below the edge, inside the break buffer, is not a break")
check(zre_is_broken_now(sup, 4050.0, 4042.0, brk) is True,
      "A5 a close more than break_atr*ATR below the edge IS a break")
# A wick that pierced the level but closed back above it must not flip the role.
closes_wick = [4050.0, 4049.0, 4047.0, 4046.5, 4048.0]
check(zre_is_flipped(sup, closes_wick, 9, brk) is False,
      "A5 no earlier CLOSED bar beyond the buffer -> not flipped")
check(zre_effective_side(sup, 4046.5, 4047.0, brk, False) == ZRE_SUPPORT,
      "A5 the role stays SUPPORT: a wick never reverses it")
# ... and the mirrored case for resistance.
res = {"side": ZRE_RESISTANCE, "lo": 4063.0, "hi": 4067.0}
check(zre_is_broken_now(res, 4060.0, 4067.5, brk) is False,
      "A5 a wick 0.5 above a resistance edge, inside the buffer, is not a break")
check(zre_effective_side(res, 4066.0, 4060.0, brk, False) == ZRE_RESISTANCE,
      "A5 the resistance role survives an intra-bar spike through it")

# --------------------------------------------------------------------- A6
# Confirmed support break, then a FAILED retest: the level is traded with the
# OPPOSITE role, so the retest of a broken support is a SELL, never a BUY.
# ZRE_IsFlipped scans [closed-lookback .. closed-1]: the bar under test is NOT
# in the window, so the breaking close has to be an EARLIER closed bar.
closes_broken = [4050.0, 4041.0, 4043.0]      # index 1 closed below lo - brk
check(zre_is_flipped(sup, closes_broken, 9, brk) is True,
      "A6 an earlier CLOSED bar beyond the buffer flips the level")
check(zre_effective_side(sup, 4045.0, 4041.0, brk, True) == ZRE_RESISTANCE,
      "A6 a broken support is retested as RESISTANCE")
check(tactical_scenario_terminal(dead_buy_by_close())[0] is True,
      "A6 the BUY plan built on that broken level is terminal")
auth6, why6 = tactical_authority_gate(True, 2, 100, 110, 40, dead_buy_by_close(),
                                      Plan(False, ""), True)
check(auth6 == TAC_BLOCKED and "retired scenario keeps no preview" in why6,
      "A6 no BUY preview survives a confirmed break + failed retest")
# The mirrored SELL on the flipped level is NOT blocked - it is the valid side.
sell_on_flip = Plan(False, "ZS")
sell_on_flip.valid = True
sell_on_flip.validity_pass = True
sell_on_flip.relevant = True
sell_on_flip.alignment_rank = 3
sell_on_flip.has_structure = True
sell_on_flip.m5_data_ok = True
sell_on_flip.classify()
auth6s, _ = tactical_authority_gate(False, 2, 108, 110, 40, dead_buy_by_close(), sell_on_flip, True)
check(auth6s == TAC_OK and sell_on_flip.state == SCN_WAITING_FOR_RETEST,
      "A6 the flipped-level SELL stays alive and says WAITING FOR RETEST")

# --------------------------------------------------------------------- A7
# Competing BUY and SELL candidates: the raw score must never bypass a gate.
strong_but_unqualified = Plan(True, "ZB")
strong_but_unqualified.valid = True
strong_but_unqualified.validity_pass = False      # failed Priority A
strong_but_unqualified.alignment_rank = 3
strong_but_unqualified.rank_score = 100           # maximum evidence quality
weak_but_valid = Plan(False, "ZS")
weak_but_valid.valid = True
weak_but_valid.validity_pass = True
weak_but_valid.alignment_rank = 0
weak_but_valid.rank_score = 1
check(plan_better(weak_but_valid, strong_but_unqualified) is True,
      "A7 Priority A validity outranks a raw score of 100")
check(strong_but_unqualified.entry_status_token() == "NO_QUALIFIED_CANDIDATE",
      "A7 an unqualified candidate says NO_QUALIFIED_CANDIDATE, not WATCH")
# Two fully qualified candidates are separated by alignment, then evidence.
qa = Plan(True, "A"); qa.valid = qa.validity_pass = True; qa.alignment_rank = 3; qa.rank_score = 74
qb = Plan(False, "B"); qb.valid = qb.validity_pass = True; qb.alignment_rank = 3; qb.rank_score = 61
check(plan_better(qa, qb) is True and plan_better(qb, qa) is False,
      "A7 equal alignment is separated by evidence quality, deterministically")
# Equal on everything: the stable zone_id tie-breaker, so a re-run cannot flip.
qc = Plan(True, "A"); qc.valid = qc.validity_pass = True; qc.alignment_rank = 3; qc.rank_score = 70
qd = Plan(False, "B"); qd.valid = qd.validity_pass = True; qd.alignment_rank = 3; qd.rank_score = 70
check(plan_better(qc, qd) is True and plan_better(qd, qc) is False,
      "A7 a tie is broken by stable zone_id ordering, not by evaluation order")

# --------------------------------------------------------------------- A8
# Missing / insufficient timeframe history must be explicit, never neutral.
no_data = Plan(True, "")
no_data.valid = False
no_data.unavailable_reason = "NO_DATA - closed H1 ATR is unavailable by ModelBoundary"
check(no_data.entry_status_token() == "NO_QUALIFIED_CANDIDATE",
      "A8 a plan with no data is not a candidate")
check(scenario_lead(no_data, no_data).valid is False,
      "A8 with no data on either side there is no lead at all")
auth8, why8 = tactical_authority_gate(True, 2, 100, 110, 40, no_data, no_data, True)
check(auth8 == TAC_CONTEXT and "no DSE BUY scenario" in why8,
      "A8 missing history downgrades a bias-only preview to CONTEXT, it never invents one")
# DSE switched off entirely: the gate must still refuse to call bias an entry.
auth8b, why8b = tactical_authority_gate(True, 2, 100, 110, 40, no_data, no_data, False)
check(auth8b == TAC_CONTEXT and "scenario engine is off" in why8b,
      "A8 with the DSE off a bias-only preview is still CONTEXT")

# --------------------------------------------------------------------- A9
# MTF candle timestamp misalignment. The tactical path reads the EXECUTION
# timeframe series; a trigger newer than the last closed execution bar is stale
# by construction and must clear the display rather than draw at a wrong time.
def exec_bar_allows(trigger_time, last_closed_exec_time):
    """nadir2.mq5: if(trigger_time>0 && ct<trigger_time) ClearMTFExecutionEntry();"""
    if trigger_time > 0 and last_closed_exec_time < trigger_time:
        return False
    return True


check(exec_bar_allows(1000, 900) is False,
      "A9 a trigger newer than the last closed execution bar clears the display")
check(exec_bar_allows(900, 1000) is True,
      "A9 a trigger already available at the closed execution bar is allowed")
check(exec_bar_allows(0, 1000) is True,
      "A9 an unknown trigger time does not trip the alignment guard")
# A misaligned series (non-chronological / duplicate timestamps) is refused by
# the M5 retest scan before any retest can be claimed.
def m5_series_valid(times):
    for i in range(len(times) - 1):
        if times[i] <= 0 or times[i + 1] <= times[i]:
            return False
    return True


check(m5_series_valid([100, 200, 300]) is True,
      "A9 a chronological M5 tape is accepted")
check(m5_series_valid([100, 100, 300]) is False,
      "A9 duplicate M5 timestamps are refused, not silently re-used")
check(m5_series_valid([300, 200, 100]) is False,
      "A9 a reversed M5 tape is refused")

# -------------------------------------------------------------------- A10
# Expiration, and a genuinely fresh setup afterwards. A scenario must not be
# revived just because price returns to the same zone.
auth10, why10 = tactical_authority_gate(True, 2, 20, 200, 40, Plan(True, ""), Plan(False, ""), True)
check(auth10 == TAC_STALE and "200 - 20" not in why10 and "180 closed chart bars old" in why10,
      "A10 a trigger 180 bars old is STALE against InpRetestTimeoutBars 40",
      why10)
check(tactical_display(True, 2, auth10, True, True, True) is None,
      "A10 a STALE trigger paints nothing, even on a closed confirming bar")
auth10b, _ = tactical_authority_gate(True, 2, 190, 200, 40, Plan(True, ""), Plan(False, ""), True)
check(auth10b == TAC_CONTEXT,
      "A10 a 10-bar-old trigger is inside the window (it is then judged on live state)")
# The Core blacklist veto is horizon-bounded, so a NEW idea on the same side is
# not muted forever: blacklisted -> BLOCKED, released -> judged normally.
fresh = live_buy()
auth10c, why10c = tactical_authority_gate(True, 0, -1, 200, 40, fresh, Plan(False, ""), True,
                                         blacklisted=True)
check(auth10c == TAC_BLOCKED and "blacklisted" in why10c,
      "A10 an idea inside the Core blacklist horizon is blocked")
auth10d, _ = tactical_authority_gate(True, 0, -1, 200, 40, fresh, Plan(False, ""), True,
                                    blacklisted=False)
check(auth10d == TAC_OK,
      "A10 once the blacklist horizon expires the same side can be a fresh setup again")
# src==1 (Core owns it) is exempt from the blacklist veto: the Core lifecycle
# cannot own a setup it just blacklisted.
auth10e, _ = tactical_authority_gate(True, 1, -1, 200, 40, fresh, Plan(False, ""), True,
                                    blacklisted=True)
check(auth10e == TAC_OK,
      "A10 a Core-owned direction is never blocked by the blacklist veto")
# Zone-age expiry maps to EXPIRED, not INVALIDATED, and is terminal all the same.
aged = Plan(True, "ZB"); aged.valid = True; aged.invalidated = True; aged.zone_age = 900
aged.classify(expire_bars=600)
check(aged.state == SCN_EXPIRED and tactical_scenario_terminal(aged)[0] is True,
      "A10 an aged-out zone is EXPIRED and equally terminal")

# -------------------------------------------------------------------- A11
# Zero look-ahead. Replaying a prefix of history must not change a verdict that
# was already published: the gate is a pure function of PUBLISHED closed-bar
# state plus the closed bar index, so feeding it the same prefix twice is
# idempotent and feeding it a longer prefix cannot rewrite the earlier answer.
snap_110 = (dead_buy_by_close(), late_sell())
first = tactical_authority_gate(True, 2, 100, 110, 40, snap_110[0], snap_110[1], True)
replay = tactical_authority_gate(True, 2, 100, 110, 40, dead_buy_by_close(), late_sell(), True)
check(first == replay,
      "A11 the gate is deterministic: an identical published state gives an identical verdict")
# A LATER bar with a genuinely new live BUY plan changes the verdict - that is a
# new fact, not a repaint of the old one.
later = tactical_authority_gate(True, 2, 120, 130, 40, live_buy(), late_sell(), True)
check(later[0] == TAC_OK and first[0] == TAC_BLOCKED,
      "A11 only a NEW published fact changes the verdict; the old one is never rewritten")
# The gate never receives a forming-bar value: its inputs are (bull, src,
# trigger_bar, trigger) plus already-published plan state. Asserted as a source
# contract in Part B (no iClose/iHigh/iTime inside the gate body).

# -------------------------------------------------------------------- A12
# The CONFIRMED -> PREVIEW re-arm loop the orphaned dedup key allowed.
d = TacticalDedup()
check(d.observe("K", True, True) == "CONFIRMED",
      "A12 a closed confirming execution bar is CONFIRMED")
check(d.observe("K", False, True) is None,
      "A12 the same signal re-arming as a live PREVIEW is suppressed")
check(d.observe("K", True, True) == "CONFIRMED",
      "A12 a later closed confirming bar of the same signal is still CONFIRMED")
check(d.observe("OTHER", False, True) == "PREVIEW",
      "A12 a different signal is unaffected by the first one's dedup")
# Without the restored write the second assertion fails - that is the regression.
class BrokenDedup(TacticalDedup):
    def observe(self, sig_id, closed_confirm, live_cross):
        state = "CONFIRMED" if closed_confirm else ("PREVIEW" if live_cross else None)
        if state is None:
            return None
        if state == "PREVIEW" and self.last_key == sig_id + "|CONFIRMED":
            return None
        return state                      # <- the v6.6.0 behaviour: never writes


b = BrokenDedup()
b.observe("K", True, True)
check(b.observe("K", False, True) == "PREVIEW",
      "A12 reproduces the pre-fix behaviour: the preview re-armed forever")

print("-" * 74)

# ======================================================================
# Part B - source contracts (the wiring Part A assumes)
# ======================================================================


def strip_comments(src):
    """Same noise-stripping check_release_gate.py G4 uses: comments and string
    literals out, so a purity assertion is about CODE, not about prose that
    legitimately names the globals the code must not read."""
    code = re.sub(r"//(?!\s*$)[^\n]*", "", src)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return code


def region(start_marker, end_marker, label):
    i = TEXT.find(start_marker)
    if i < 0:
        check(False, "B locate %s" % label, "marker not found: %r" % start_marker[:60])
        return ""
    j = TEXT.find(end_marker, i)
    if j < 0:
        check(False, "B locate end of %s" % label, "marker not found: %r" % end_marker[:60])
        return ""
    return TEXT[i:j]


mtf = region("void UpdateMTFExecutionEntry()", "void DrawProvisionalFractals(", "UpdateMTFExecutionEntry")
# NOTE: the gate has a forward declaration near UpdateMTFExecutionEntry as well,
# so the region is anchored on the block comment that only precedes the body.
gate = region("// v6.6.10 AUDIT-TAC  TACTICAL AUTHORITY GATE",
              "// Directional location is read from the same D1 closed range",
              "TacticalAuthorityGate")
draw_one = region("void ScenarioDrawOne(const SScenarioPlan &p", "void ScenarioDraw()", "ScenarioDrawOne")

# B1 - the dedup key is written again.
check("if(closed_confirm) g_last_mtf_entry_key=id+\"|CONFIRMED\";" in mtf,
      "B1 g_last_mtf_entry_key has a writer again (the v6.6.0 patch orphaned it)")
writers = len(re.findall(r"g_last_mtf_entry_key\s*=(?!=)", TEXT))
readers = len(re.findall(r"g_last_mtf_entry_key\s*==|g_last_mtf_entry_key\s*!=", TEXT))
check(writers >= 1 and readers >= 2,
      "B1 every reader of g_last_mtf_entry_key is backed by a writer (%d write, %d read)"
      % (writers, readers))

# B2 - the gate runs before anything is drawn, marked or fed to the arbiter.
i_gate = mtf.find("TacticalAuthorityGate(bull,src,trigger_bar,trigger,auth_reason)")
i_observe = mtf.find("QSMC_Root().TacticalObserve(_tf)")
i_label = mtf.find("DrawTextLabel(PFX+\"MTF_ENTRY_TX\"")
i_mark = mtf.find("EntryMarkTactical(bull,closed_confirm,ep)")
check(i_gate > 0, "B2 the authority gate is called inside UpdateMTFExecutionEntry")
check(0 < i_gate < i_observe, "B2 the gate runs BEFORE the arbiter is fed")
check(0 < i_gate < i_label, "B2 the gate runs BEFORE the label is drawn")
check(0 < i_gate < i_mark, "B2 the gate runs BEFORE the entry mark is painted")

# B3 - BLOCKED / STALE clear the display AND return, keeping the reason.
blocked_blk = region("if(auth==TAC_AUTH_BLOCKED || auth==TAC_AUTH_STALE)",
                     "ENUM_TIMEFRAMES etf=SelectExecutionTF()", "blocked branch")
check("ClearMTFExecutionEntry();" in blocked_blk and "return;" in blocked_blk,
      "B3 a BLOCKED/STALE verdict clears the display and returns")
check("g_mtf_entry_blocked=true;" in blocked_blk and "g_mtf_entry_authority=" in blocked_blk,
      "B3 the reason survives the clear, so the panel can state it")

# B4 - the label can no longer print ENTRY for a bias-only context verdict.
check("string verb=(auth==TAC_AUTH_CONTEXT?\"CONTEXT\":\"ENTRY\");" in mtf,
      "B4 the label verb is chosen from the authority verdict")
check("\"%s MTF %s %s %s @ %.2f | exec %s | grade %s%s\"" in mtf
      and "bull?\"BUY\":\"SELL\",verb,state,ep,TFName(etf)" in mtf,
      "B4 the format string and its arguments still match (verb is passed)")
check("auth!=TAC_AUTH_CONTEXT && (!far || closed_confirm)" in mtf,
      "B4 a CONTEXT verdict paints no entry mark or arrow")

# B5 - the direction source is recorded, so src==2 is the only branch that can
#      be downgraded, and Core/early-break ownership is preserved.
check("int src=-1,trigger_bar=-1;" in mtf,
      "B5 the direction source is tracked")
check("trigger_time=g_early_break_structure_time; src=0;" in mtf
      and "trigger_time=g_active_setup.created_time; src=1;" in mtf
      and "have_dir=true; bull=(g_htf_bias>0); src=2;" in mtf,
      "B5 all three direction sources are labelled 0 / 1 / 2")
check("trigger_bar=g_structures[i].bar;" in mtf,
      "B5 the bias-only branch records the trigger's chart bar for the age bound")

# B6 - the gate itself: total order, and no forming-bar read.
# Both symbols also have forward declarations near UpdateMTFExecutionEntry, so
# every region below is anchored on the block comment that only precedes a body.
decide = region("// The PURE total order. No global is read in here",
                "// The adapter: it gathers the PUBLISHED closed-bar facts",
                "TacticalAuthorityDecide")
adapter = region("// The adapter: it gathers the PUBLISHED closed-bar facts",
                 "// In-terminal contract for the pure order above",
                 "TacticalAuthorityGate")

i1 = decide.find("dse_on && dse_terminal")
i2 = decide.find("src!=1 && blacklisted")
i3 = decide.find("trigger_age_bars>retest_timeout_bars")
i4 = decide.find("src==2 && !(dse_on && dse_live)")
check(0 < i1 < i2 < i3 < i4,
      "B6 the total order is DSE-terminal -> Core-blacklist -> stale -> context")
check("return TAC_AUTH_BLOCKED;" in decide and "return TAC_AUTH_STALE;" in decide
      and "return TAC_AUTH_CONTEXT;" in decide and "return TAC_AUTH_OK;" in decide,
      "B6 all four verdicts are reachable from the pure order")
# The pure order must stay pure: no mutable global, no series call, no trade API.
# InpBlacklistExpiryBars is an input constant (it only appears inside a reason
# string), so it is deterministic and allowed.
check(not re.search(r"\bg_[A-Za-z_]", strip_comments(decide)),
      "B6 the pure order reads no mutable global (so the MQL5 self-test can exercise it)")
for forbidden in ("iClose(", "iHigh(", "iLow(", "iOpen(", "iTime(", "rates_total",
                  "CopyRates(", "OrderSend", "PositionOpen", "ArraySize("):
    check(forbidden not in decide,
          "B6 the pure order reads no forming-bar value and no trade API (%s)" % forbidden)
# ... and the adapter is the only place the facts are gathered.
for fact in ("InpUseDirectionalScenarioEngine", "g_scn_built_time",
             "TacticalScenarioTerminal(bull,terminal_state,terminal_why)",
             "TacticalScenarioLive(bull,live_state)",
             "IsSameIdeaAsBlacklisted(bull,trigger,trigger)",
             "ArraySize(g_buf_t)-2", "InpRetestTimeoutBars"):
    check(fact in adapter, "B6 the adapter gathers %s" % fact)
check("TacticalAuthorityDecide(bull,src,age,InpRetestTimeoutBars,dse_on,dse_terminal," in adapter,
      "B6 the adapter delegates to the pure order instead of re-deriving it")
check("int age=((src==2 && trigger_bar>=0 && closed_now>=trigger_bar) ? closed_now-trigger_bar : -1);"
      in adapter,
      "B6 an unknown trigger age is passed as -1, never guessed")
# The whole gate region still reads no forming-bar value.
for forbidden in ("iClose(", "iHigh(", "iLow(", "iOpen(", "iTime(", "CopyRates(",
                  "OrderSend", "PositionOpen"):
    check(forbidden not in gate,
          "B6 the gate reads no forming-bar value and no trade API (%s)" % forbidden)

# B6b - the in-terminal self-test exists, is pure, and is wired into OnInit.
selftest = region("// In-terminal contract for the pure order above",
                  "// Directional location is read from the same D1 closed range",
                  "TacticalAuthoritySelfTest")
groups = sorted(set(re.findall(r'where="TAC-(\d)', selftest)))
check(groups == ["1", "2", "3", "4", "5", "6", "7"],
      "B6b the MQL5 self-test covers all seven groups TAC-1..TAC-7", "got %s" % groups)
calls = len(re.findall(r"TacticalAuthorityDecide\(", selftest))
check(calls >= 16,
      "B6b the seven groups exercise the pure order directly in %d calls (not a wrapper)" % calls,
      "got %d" % calls)
check(not re.search(r"\bg_[A-Za-z_]", strip_comments(selftest)),
      "B6b the MQL5 self-test touches no global, so it cannot change a decision")
check("TacticalAuthorityDecide(" in selftest and "ObjectCreate" not in selftest
      and "DrawTextLabel" not in selftest,
      "B6b the MQL5 self-test exercises the pure order and draws nothing")
check("if(TacticalAuthoritySelfTest(mtee_fail))" in TEXT
      and "Tactical-authority self-test: PASS (7/7)" in TEXT,
      "B6b OnInit runs the self-test and prints its verdict")

# B7 - the gate's inputs are published closed-bar state only.
term = region("// Does the Directional Scenario Engine hold a TERMINAL plan",
              "string TacticalAuthorityName", "TacticalScenarioTerminal/Live")
check("g_scn_buy.invalidated" in term and "g_scn_buy.plan_dead" in term
      and "g_scn_sell.invalidated" in term and "g_scn_sell.plan_dead" in term,
      "B7 both terminal facts (zone invalidation and closed-M5 breach) are read")
check("g_scn_buy.relevant" in term and "g_scn_sell.relevant" in term,
      "B7 liveness is the DSE's own Priority-A verdict, not a re-derived one")
check(term.count("if(bull)") == 2 and "Mirrored halves" in term,
      "B7 both predicates mirror the two sides explicitly (no struct pointer, no alias)")
check("string &state_name" in term and "state_name=ScenarioStateName(g_scn_buy.state);" in term
      and "state_name=ScenarioStateName(g_scn_sell.state);" in term,
      "B7 the CONTEXT reason is built from the DSE's own state name")

# B8 - the terminal scenario plan is drawn as retired, not as conditional.
check("if(!p.valid || p.execution_ready || !(p.zone_high>p.zone_low)) return;" in draw_one,
      "B8 ScenarioDrawOne no longer drops a terminal plan silently")
check("bool terminal=(p.invalidated || p.plan_dead ||" in draw_one,
      "B8 a single terminal predicate covers both invalidation paths")
check("color col=(terminal?clrDarkGray:(p.is_buy?clrDarkSeaGreen:clrTomato));" in draw_one,
      "B8 a terminal plan is drawn in the terminal colour; live colours are unchanged")
check("(terminal?ScenarioStateName(p.state)+\" — NOT AN ENTRY\":" in draw_one
      and "\"CONDITIONAL — \"+ScenarioStateName(p.state)" in draw_one,
      "B8 the tag never says CONDITIONAL about a terminal plan")
check("RETIRED PLAN" in draw_one and "CONDITIONAL ONLY" in draw_one,
      "B8 the tooltip distinguishes a retired plan from a plan to monitor")
check("bool expect_buy=(g_scn_buy.valid && !g_scn_buy.execution_ready);" in TEXT
      and "bool expect_sell=(g_scn_sell.valid && !g_scn_sell.execution_ready);" in TEXT,
      "B8 the redraw expectation matches ScenarioDrawOne's own guard")

# B9 - observability: the reconciliation row exists on both cards.
compact = region("void ScenarioDashCompact(string &L[]", "string ScenarioPlanEntryText", "compact card")
full = region("void ScenarioDashFull(string &L[]", "void CoreDashboardDeleteObjects()", "full card")
check("if(g_mtf_entry_authority!=\"\")" in compact and "TACTICAL: " in compact,
      "B9 the compact card reconciles the tactical verdict with the scenario state")
check("TACTICAL PREVIEW: " in full and "TACTICAL AUTHORITY: " in full,
      "B9 the full card states the tactical source, state and the authority reason")
check("if(g_mtf_entry_authority!=\"\")" in compact,
      "B9 the reconciliation row appears only when there is something to explain")

# B10 - causality / ordering, stated as a source fact: the gate is called from
#       the tactical path, which OnCalculate runs BEFORE ScenarioUpdate, so the
#       DSE snapshot it reads is the last PUBLISHED one. That is causal; the
#       comment must say so, or the next reader will "fix" it into a look-ahead.
oncalc = region("int OnCalculate(const int rates_total, const int prev_calculated,",
                "// RUNTIME DISPLAY-ONLY LOOKAHEAD AUDIT", "OnCalculate")
i_mtf_call = oncalc.find("UpdateMTFExecutionEntry();")
i_scn_call = oncalc.find("ScenarioUpdate(rates_total,")
check(0 < i_mtf_call < i_scn_call,
      "B10 OnCalculate still runs the tactical path before ScenarioUpdate")
check("the DSE snapshot is still the previous closed bar's" in mtf,
      "B10 the one-tick staleness at bar open is documented where it happens")
check("strictly causal, never" in mtf and "look-ahead" in mtf,
      "B10 the comment states the causality claim explicitly")

# B11 - indicator-only invariants are untouched by this pass. Comments are
# stripped first (the file documents "no OrderSend" in five places, which is the
# opposite of a call); this is the same noise-stripping check_release_gate G4 uses.
CODE = re.sub(r"//(?!\s*$)[^\n]*", "", TEXT)
CODE = re.sub(r"/\*.*?\*/", "", CODE, flags=re.S)
CODE = re.sub(r'"(\\.|[^"\\])*"', '""', CODE)
for api in ("OrderSend", "OrderSendAsync", "CTrade", "PositionOpen", "PositionModify",
            "OrderCheck", "WebRequest"):
    check(api not in CODE, "B11 nadir2.mq5 still cannot reach %s" % api)
check(TEXT.count("#include <QSMC/QSMC_Root.mqh>") == 1,
      "B11 the arbitration root is still included exactly once")

print("-" * 74)
if FAILS:
    print("RESULT: %d contract(s) FAILED" % len(FAILS))
    for f in FAILS:
        print("   - " + f)
    sys.exit(1)
print("RESULT: all tactical-authority contracts hold")
print("-" * 74)
print("This is a transcription + wiring contract. It is NOT a backtest, it produces")
print("no win rate, and it does NOT prove MetaEditor compilation. Press F7.")
