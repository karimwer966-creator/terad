#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-SC1 contract: the scalping overlay (M1-M5), advisory and display only.

The overlay adds six scalping strategies without adding a second opinion about
anything: every leg reads state the existing modules already published for the
closed bar, the ATR multiples are the numbers QSMC_PRESET_SCALPER already ships,
and the veto ordering is the one AUDIT-GS1 established. This suite pins that.

  A  inputs: the flag, the six weights and that they sum to 100, the geometry,
     and that the geometry is the SCALPER preset's, read from the header
  B  the advisory state: nine globals, each declared once, none of them a verdict
     another layer owns
  C  the pure cores: spread ratio, spread veto, RR, weight sum, side scoring and
     the decide rule (which mirrors the resolver's, so a scalp cannot disagree
     with the engine about what a disagreement means)
  D  the six legs reuse published state - MOM, EDGE, SB, P3, WY, CF - and never
     re-derive a module or scan zones a second time
  E  the four vetoes (no data, spread cost, session, news) are exact, unconditional,
     set the veto flag and all sit ABOVE the first weighted point
  F  the verdict path: conflict, silence, below-minimum, RR refusal, publish
  G  causality and hygiene: closed bar only, no series re-read, no per-tick loop,
     no drawing, no order API, and it writes only g_sc_*
  H  wiring: OnInit refusals, the self-test hook, the OnCalculate call site and
     the tooltip line
  I  the self-test really has ten numbered deterministic checks
  J  nothing pre-existing was weakened, and the counts moved only as declared
  K  the doc and CI own the same facts

Every number was measured against the file.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "nadir2.mq5")
PRESET = os.path.join(ROOT, "MQL5", "Include", "QSMC", "QSMC_Preset.mqh")
DOC = os.path.join(ROOT, "docs", "QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md")
WF = os.path.join(ROOT, ".github", "workflows", "qsmc-verify.yml")

RAW = io.open(SRC, encoding="utf-8", newline="").read()
LINES = RAW.replace("\r\n", "\n").split("\n")
TEXT = "\n".join(LINES)
PRE = io.open(PRESET, encoding="utf-8", newline="").read().replace("\r\n", "\n")
DOCX = io.open(DOC, encoding="utf-8").read()
WFX = io.open(WF, encoding="utf-8").read()

RESULTS = []


def check(cond, label, detail=""):
    RESULTS.append((bool(cond), label, detail))
    if cond:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s  [%s]" % (label, detail))


def line_at(n):
    return LINES[n - 1] if 1 <= n <= len(LINES) else ""


def body(a, b):
    return "\n".join(LINES[a - 1:b])


def fn_end(first):
    """Closing brace of the function starting at `first`. The signature may span
    several lines, so the search only starts looking for the end once a brace has
    actually opened - otherwise it "ends" on the second signature line and every
    body assertion silently reads an empty string."""
    depth = 0
    opened = False
    for i in range(first - 1, len(LINES)):
        depth += LINES[i].count("{") - LINES[i].count("}")
        if depth > 0:
            opened = True
        if opened and depth <= 0:
            return i + 1
    return 0


# ---------------------------------------------------------------- A. inputs
GRP, FLAG, SHOW = 872, 873, 874
W = {"InpScalpWeightMomentum": (20, 875), "InpScalpWeightEdge": (20, 876),
     "InpScalpWeightSilverBullet": (15, 877), "InpScalpWeightPowerOf3": (15, 878),
     "InpScalpWeightWyckoff": (15, 879), "InpScalpWeightConfluence": (15, 880)}
MIN, DISP, STOP, TGT, RR, SPR, SESS = 881, 882, 883, 884, 885, 886, 887

check('input group "====== Scalping Strategies (AUDIT-SC1, M1-M5, display only, '
      'advisory) ======"' in line_at(GRP),
      "A the overlay has its own input group at L%d" % GRP, line_at(GRP).strip()[:70])
check("display only" in line_at(GRP) and "advisory" in line_at(GRP),
      "A the group heading itself says display only and advisory")
check(re.search(r"^input bool\s+InpEnableScalping\s*=\s*false;", line_at(FLAG)),
      "A InpEnableScalping defaults to false at L%d" % FLAG, line_at(FLAG).strip()[:70])
check(re.search(r"^input bool\s+InpScalpShowOnDashboard\s*=\s*false;", line_at(SHOW)),
      "A the display opt-in is separate and also false at L%d" % SHOW,
      line_at(SHOW).strip()[:70])

total = 0
for name, (val, ln) in sorted(W.items(), key=lambda kv: kv[1][1]):
    check(re.search(r"^input int\s+%s\s*=\s*%d;" % (name, val), line_at(ln)),
          "A %s = %d at L%d" % (name, val, ln), line_at(ln).strip()[:70])
    m = re.search(r"(?m)^input int\s+%s\s*=\s*(\d+);" % name, TEXT)
    total += int(m.group(1)) if m else 0
check(total == 100, "A the six shipped weights sum to exactly 100 (%d)" % total,
      "OnInit refuses any other sum")

GEO = (("InpScalpMinScore", 60, MIN, r"^input int\s+InpScalpMinScore\s*=\s*60;"),
       ("InpScalpDispATR", 0.40, DISP, r"^input double\s+InpScalpDispATR\s*=\s*0\.40;"),
       ("InpScalpStopATR", 0.80, STOP, r"^input double\s+InpScalpStopATR\s*=\s*0\.80;"),
       ("InpScalpTargetATR", 1.20, TGT, r"^input double\s+InpScalpTargetATR\s*=\s*1\.20;"),
       ("InpScalpMinRR", 1.20, RR, r"^input double\s+InpScalpMinRR\s*=\s*1\.20;"),
       ("InpScalpMaxSpreadATR", 0.10, SPR, r"^input double\s+InpScalpMaxSpreadATR\s*=\s*0\.10;"))
for name, val, ln, pat in GEO:
    check(re.search(pat, line_at(ln)), "A %s = %s at L%d" % (name, val, ln),
          line_at(ln).strip()[:70])
check(re.search(r"^input bool\s+InpScalpRequireSession\s*=\s*true;", line_at(SESS)),
      "A InpScalpRequireSession defaults to true at L%d: a scalp outside the kill "
      "zones is vetoed unless the operator says otherwise" % SESS,
      line_at(SESS).strip()[:70])
check(all("ATR" in line_at(ln) for _, _, ln, _ in GEO if ln in (DISP, STOP, TGT, SPR)),
      "A every distance is in ATR units - symbol-agnostic, no hard-coded price")

# the geometry is the SCALPER preset's, read from the header, not invented here
# the SCALPER case appears twice in the header (once in EffectiveName, once in
# Build); the profile numbers are the one inside Build().
m = re.search(r"case QSMC_PRESET_SCALPER:\s*\n\s*p_zone_reach=.*?break;", PRE, re.S)
assert m, "SCALPER profile block not found in QSMC_Preset.mqh"
scalper = m.group(0)
check("p_disp=0.40" in scalper,
      "A the 0.40 ATR displacement is QSMC_PRESET_SCALPER's own p_disp", scalper.strip()[:90])
check("p_minrr=1.20" in scalper,
      "A the 1.20 RR floor is QSMC_PRESET_SCALPER's own p_minrr")
check("if(sec<=PeriodSeconds(PERIOD_M5))  m_effective=QSMC_PRESET_SCALPER;" in PRE,
      "A the preset already auto-selects SCALPER on M1-M5, which is the overlay's "
      "target timeframe - so no second timeframe rule was needed")
check(len(re.findall(r"(?m)^input .*InpEnableScalping", TEXT)) == 1,
      "A the overlay flag is declared exactly once")

# --------------------------------------------------------------- B. globals
GL = {"g_sc_dir": 4773, "g_sc_score": 4774, "g_sc_legs": 4775, "g_sc_why": 4776,
      "g_sc_veto": 4777, "g_sc_stop": 4778, "g_sc_target": 4779, "g_sc_rr": 4780,
      "g_sc_bar": 4781}
for name, ln in sorted(GL.items(), key=lambda kv: kv[1]):
    check(re.search(r"^(int|string|bool|double)\s+%s=" % name, line_at(ln)),
          "B %s is declared at L%d" % (name, ln), line_at(ln).strip()[:70])
    check(len(re.findall(r"(?m)^(int|string|bool|double)\s+%s=" % name, TEXT)) == 1,
          "B %s has exactly one declaration" % name)
hdr = body(4770, 4773)
check("Written only by SCALP_Update()" in hdr and "it advises" in hdr,
      "B the ownership comment names the single writer and says it only advises",
      hdr.strip()[:90])
check("NOT a probability" in line_at(4774),
      "B the score's own comment says it is a confluence count, not a probability")
check("never evidence" in line_at(4777),
      "B the veto flag's comment says it is only data/spread/session/news")
check("no repaint" in line_at(4781),
      "B g_sc_bar's comment states the anti-repaint rule")

# ------------------------------------------------------------ C. pure cores
F_RATIO, F_VETO, F_RR, F_SUM = 6216, 6223, 6231, 6238
F_SIDE, F_DEC, F_VOTES, F_UPD, F_ST = 6245, 6265, 6277, 6310, 6408
for name, ln, sig in (("SCALP_SpreadRatio", F_RATIO, r"^double SCALP_SpreadRatio\("),
                      ("SCALP_SpreadVeto", F_VETO, r"^bool SCALP_SpreadVeto\("),
                      ("SCALP_RR", F_RR, r"^double SCALP_RR\("),
                      ("SCALP_WeightsSum", F_SUM, r"^int SCALP_WeightsSum\(\)"),
                      ("SCALP_ScoreSide", F_SIDE, r"^int SCALP_ScoreSide\("),
                      ("SCALP_Decide", F_DEC, r"^int SCALP_Decide\("),
                      ("SCALP_Votes", F_VOTES, r"^void SCALP_Votes\("),
                      ("SCALP_Update", F_UPD, r"^void SCALP_Update\("),
                      ("SCALP_SelfTest", F_ST, r"^bool SCALP_SelfTest\(string &where\)")):
    check(re.search(sig, line_at(ln)), "C %s is defined at L%d" % (name, ln),
          line_at(ln).strip()[:70])
    check(len(re.findall(r"(?m)" + sig, TEXT)) == 1,
          "C %s is defined exactly once" % name)
    if name not in ("SCALP_Votes", "SCALP_Update", "SCALP_SelfTest"):
        fb = body(ln, fn_end(ln))
        check(not re.search(r"\bg_[a-z_0-9]+\s*=", fb),
              "C %s is pure: it writes no global, so the self-test can call it "
              "without a chart" % name, fb.strip()[:80])

rb = body(F_RATIO, fn_end(F_RATIO))
check("if(!(atr>0.0)) return DBL_MAX;" in rb,
      "C no ATR returns DBL_MAX, so missing data vetoes instead of dividing by zero")
check("(spread_pts*_Point)/atr" in rb,
      "C spread cost is spread in price over ATR - a ratio, not a points threshold")
vb = body(F_VETO, fn_end(F_VETO))
check("if(!(max_ratio_atr>0.0)) return true;" in vb,
      "C a non-positive cap vetoes everything rather than allowing everything")
check("SCALP_SpreadRatio(spread_pts,atr)>max_ratio_atr" in vb,
      "C the veto is strictly greater, so the cap itself is allowed (documented boundary)")
rrb = body(F_RR, fn_end(F_RR))
check("if(!(stop_atr>0.0) || !(target_atr>0.0)) return 0.0;" in rrb
      and "return target_atr/stop_atr;" in rrb,
      "C RR is target/stop, and 0 without a usable stop")
sb = body(F_SUM, fn_end(F_SUM))
check(sb.count("InpScalpWeight") == 6,
      "C the weight sum adds exactly the six weight inputs", sb.strip()[:80])
sideb = body(F_SIDE, fn_end(F_SIDE))
check("if(vote[k]==side && side!=0)" in sideb,
      "C a side counts only its own votes, and side 0 can never score")
check('if(have!="") have+="+";' in sideb,
      "C earned legs are named with a separator, so the why-text is readable")
decb = body(F_DEC, fn_end(F_DEC))
check("if(buy>0 && sell>0) return 2;" in decb and "if(buy==0 && sell==0) return 0;" in decb
      and "if(got<min_score) return 0;" in decb,
      "C the decide rule is the resolver's rule: both sides = CONFLICT(2), silence = "
      "WAIT(0), a lone side below the minimum = WAIT(0)")
res = body(6146, fn_end(6146))
check("return 2;" in res and "if(buy==0 && sell==0)" in res,
      "C the resolver it mirrors really does use the same three outcomes")

# ----------------------------------------------------------------- D. legs
votes = body(F_VOTES, fn_end(F_VOTES))
for tag, nm in ((0, "MOM"), (1, "EDGE"), (2, "SB"), (3, "P3"), (4, "WY"), (5, "CF")):
    check('nm[%d]="%s"' % (tag, nm) in votes, "D leg %d is named %s" % (tag, nm))
    check("vote[%d]=" % tag in votes, "D leg %d writes its own vote" % tag)
check("for(int k=0;k<6;k++) vote[k]=0;" in votes,
      "D every vote starts as an abstain, so a missing leg invents nothing")
check("double disp=g_buf_c[closed]-g_buf_c[closed-1];" in votes
      and "MathAbs(disp)>=InpScalpDispATR*atr" in votes,
      "D MOM reads the closed bar's displacement from the mirrored buffer and "
      "compares it in ATR units")
check("closed>=1 && closed<ArraySize(g_buf_c)" in votes,
      "D MOM bounds-checks before reading closed-1")
check("if(g_mr_ext_dir!=0)" in votes and "zd==-g_mr_ext_dir" in votes
      and "vote[1]=-g_mr_ext_dir;" in votes,
      "D EDGE fades a mean-reversion stretch only into a zone whose role opposes "
      "it - both facts come from MR and PA, not from a new rule")
check("PA_ZoneAt(g_buf_c[closed],closed,atr,zn,zt,zb,zd)" in votes,
      "D EDGE reuses PA_ZoneAt, the one zone scan, instead of building a second")
check("vote[2]=(g_sb_active?g_sb_dir:0);" in votes,
      "D SB reads the Silver Bullet module's own resolved window")
check("vote[3]=g_p3_dir;" in votes, "D P3 reads the Power-of-3 Judas verdict")
check("vote[4]=(g_wy_active?g_wy_dir:0);" in votes,
      "D WY reads the Wyckoff spring/upthrust verdict")
check("g_cf_buy_score>=InpCFMinDisplayScore" in votes
      and "g_cf_sell_score>=InpCFMinDisplayScore" in votes,
      "D CF uses the Confluence Engine's own scores at its OWN display threshold - "
      "no second confluence rule and no new number to drift")
for banned in ("SB_Update(", "P3_Update(", "WY_Update(", "MR_Update(", "CF_Update(",
               "PA_Update(", "RXN_Update(", "ZRE_Update("):
    check(banned not in votes,
          "D the overlay never calls %s: it reads published state, it does not "
          "re-run a module" % banned)
check("SCALP_Score(" not in TEXT and "ScalpScore(" not in TEXT,
      "D no second scoring function was added beside the pure cores")

# --------------------------------------------------------------- E. vetoes
UPD_END = fn_end(F_UPD)
UB = body(F_UPD, UPD_END)
V_ATR, V_SPRD, V_SESS, V_NEWS, LEG1 = 6319, 6325, 6334, 6342, 6358
check(line_at(V_ATR).strip() == "if(!(atr>0.0))",
      "E veto 1 is missing ATR - no cost model, no scalp (L%d)" % V_ATR,
      body(V_ATR - 1, V_ATR + 1).strip()[:80])
check("if(SCALP_SpreadVeto((double)g_spread,atr,InpScalpMaxSpreadATR))" in line_at(V_SPRD),
      "E veto 2 is the spread-cost ratio (L%d)" % V_SPRD, line_at(V_SPRD).strip()[:80])
check(line_at(V_SESS).strip() == "if(InpScalpRequireSession &&",
      "E veto 3 is the session window, behind its own input (L%d)" % V_SESS,
      line_at(V_SESS).strip()[:80])
sess = body(V_SESS, V_SESS + 3)
check("IsInSession(g_buf_t[closed],SESSION_LONDON)" in sess
      and "IsInSession(g_buf_t[closed],SESSION_NEWYORK)" in sess,
      "E the session veto REUSES IsInSession on the CLOSED bar's time - one session "
      "rule, no wall clock", sess.strip()[:90])
check(line_at(V_NEWS).strip() == "if(MTF_SniperIsNewsBlackout(g_buf_t[closed]))",
      "E veto 4 REUSES MTF_SniperIsNewsBlackout - one news rule (L%d)" % V_NEWS,
      line_at(V_NEWS).strip()[:80])
for ln, name in ((V_ATR, "no-data"), (V_SPRD, "spread"), (V_SESS, "session"),
                 (V_NEWS, "news")):
    blk = body(ln, ln + 9)
    check("g_sc_veto=true;" in blk and "return;" in blk,
          "E the %s veto sets the veto flag and returns immediately" % name,
          blk.strip()[:70])
    check("HARD VETO:" in blk, "E the %s veto says HARD VETO in the why-text" % name)
check(V_ATR < V_SPRD < V_SESS < V_NEWS < LEG1,
      "E all four vetoes sit above the first verdict line (L%d < L%d < L%d < L%d < "
      "L%d), so no weight can outvote one" % (V_ATR, V_SPRD, V_SESS, V_NEWS, LEG1))
check("SCALP_ScoreSide(" not in body(F_UPD, V_NEWS),
      "E no evidence is scored anywhere above the news veto")
check("the move would pay the broker" in body(V_SPRD, V_SPRD + 8),
      "E the spread veto explains itself in trader terms, not just numbers")
check("TimeCurrent()" not in UB and "TimeLocal()" not in UB,
      "E no wall-clock read: every veto is bound to the closed bar's own time")

# -------------------------------------------------------------- F. verdict
check("g_sc_dir=SCALP_Decide(buy,sell,InpScalpMinScore);" in line_at(LEG1),
      "F the verdict comes from the pure decide rule at L%d" % LEG1,
      line_at(LEG1).strip()[:80])
CONF, WAIT, RRCHK, WHY = 6361, 6368, 6383, 6396
conf = body(CONF, CONF + 8)
check("if(g_sc_dir==2)" in line_at(CONF) and "g_sc_score=0;" in conf
      and "disagreeing scalps mean stand aside" in conf,
      "F a conflict zeroes the score and says stand aside", conf.strip()[:90])
wait = body(WAIT, WAIT + 14)
check("if(g_sc_dir==0)" in line_at(WAIT) and "abstained: " in wait,
      "F a WAIT names the legs that abstained - the observability Phase 1 asked for",
      wait.strip()[:90])
check("no scalping strategy voted" in wait,
      "F total silence is reported differently from a weak side")
rr = body(RRCHK, RRCHK + 9)
check("if(g_sc_rr<InpScalpMinRR)" in line_at(RRCHK) and "g_sc_dir=0;" in rr
      and "REFUSED: advisory RR " in rr,
      "F a scalp whose advisory RR is below the floor is refused, not published "
      "with a bad shape", rr.strip()[:90])
why = body(RRCHK, UPD_END)
check('g_sc_why="SCALP "' in line_at(WHY), "F the published line starts at L%d" % WHY,
      line_at(WHY).strip()[:70])
for frag in ('"/100 from "', '" ATR @ "', '" | RR "',
             '" - a weighted confluence count, not a probability"'):
    check(frag.strip('"') in why, "F the why-text carries %s" % frag)
check("g_sc_stop=(g_sc_dir>0?px-stop_dist:px+stop_dist);" in why
      and "g_sc_target=(g_sc_dir>0?px+tgt_dist:px-tgt_dist);" in why,
      "F stop and target are mirrored by side, in ATR distances from the closed price")
check("g_sc_bar=closed;" in why,
      "F the verdict records the closed bar it belongs to, so it cannot be read as "
      "live on the next tick")
check("InpScalpStopATR*atr" in why and "InpScalpTargetATR*atr" in why,
      "F the geometry is ATR-scaled at publish time, never a fixed price distance")

# --------------------------------------------------- G. causality/hygiene
check("if(closed<1 || closed>rates_total-2 || closed>=ArraySize(g_buf_c)) return;" in UB,
      "G the overlay refuses the forming bar and any index the mirror does not hold")
check(not re.search(r"iClose\(|iTime\(|iHigh\(|iLow\(|CopyClose\(|CopyBuffer\(", UB),
      "G no series re-read: it uses the mirrored arrays the pipeline already filled")
check(not re.search(r"for\(int i=0;i<(rates_total|Bars)", UB),
      "G no full-history loop: bounded work per closed bar")
check("ObjectCreate" not in UB and "Comment(" not in UB and "DrawTradeBox" not in UB,
      "G the overlay draws nothing, so it adds no chart clutter and no object churn")
for bad in ("g_final_signal=", "g_final_why=", "g_alert_primary=", "g_active_setup.",
            "g_trade_setup.", "g_res_score=", "g_wgate_score="):
    check(bad not in UB,
          "G the overlay never writes %s - it advises, another layer decides" % bad)
check("OrderSend" not in UB and "CTrade" not in UB,
      "G no order API in the overlay")
check(all(l.strip().startswith("//") for l in LINES if "OrderSend" in l),
      "G every OrderSend mention in the file is still prose in a comment")
check("g_sc_" in UB and UB.count("g_sc_") >= 12,
      "G the overlay writes its own state (%d g_sc_ references)" % UB.count("g_sc_"))

# ---------------------------------------------------------------- H. wiring
OI_W, OI_G, OI_P, CALL, HOOK, TIP = 15115, 15120, 15127, 16332, 15532, 33681
check("if(InpEnableScalping && SCALP_WeightsSum()!=100)" in line_at(OI_W),
      "H OnInit refuses a weight sum that is not 100 (L%d)" % OI_W,
      line_at(OI_W).strip()[:70])
oiw = body(OI_W, OI_W + 5)
check("return INIT_PARAMETERS_INCORRECT;" in oiw
      and "scalping weights: they must sum to exactly 100" in oiw,
      "H the refusal names the rule instead of renormalising")
oig = body(OI_G, OI_G + 8)
check("InpScalpStopATR<=0.0" in oig and "InpScalpMaxSpreadATR<=0.0" in oig
      and "SCALP_RR(InpScalpStopATR,InpScalpTargetATR)<InpScalpMinRR" in oig
      and "return INIT_PARAMETERS_INCORRECT;" in oig,
      "H OnInit also refuses inconsistent geometry: a non-positive stop or spread "
      "cap, an out-of-range minimum, or a target that cannot clear the RR floor",
      oig.strip()[:90])
check("refuses an inconsistent configuration rather" in body(OI_W - 4, OI_W),
      "H the comment above says why it refuses rather than clamps")
check("Scalping overlay: ON | advisory | display only | " in body(OI_P, OI_P + 4),
      "H enabling the overlay announces itself as advisory and display only")
hook = body(HOOK, HOOK + 4)
check("if(SCALP_SelfTest(mtee_fail))" in line_at(HOOK)
      and "Scalping strategies self-test: PASS (10/10)" in hook
      and "Scalping strategies self-test: FAIL - " in hook,
      "H the self-test is wired into the file's existing InpMTEERunSelfTest block "
      "and reports like the six modules before it", hook.strip()[:90])
check(line_at(CALL).strip().endswith("SCALP_Update(closed,rates_total);")
      and "if(InpEnableScalping && (is_new_bar || detection_updated))" in line_at(CALL),
      "H OnCalculate calls it at L%d, behind the flag and the closed-bar/detection "
      "gate - never per tick" % CALL, line_at(CALL).strip()[:90])
rm = TEXT.index("RM_Update(closed,rates_total);")
check(TEXT.index("SCALP_Update(closed,rates_total);") > rm,
      "H the call sits AFTER the module updates, so it reads state published for "
      "this same closed bar")
check(TEXT.count("SCALP_Update(closed,rates_total);") == 1,
      "H exactly one call site")
tip = body(TIP - 1, TIP + 1)
check('"Scalp: "+(g_sc_why==""?"none":g_sc_why)' in line_at(TIP)
      and "InpEnableScalping?" in tip,
      "H the tooltip line is guarded by the flag, so off means an identical tooltip",
      tip.strip()[:90])

# ------------------------------------------------------------- I. self-test
ST_END = fn_end(F_ST)
ST = body(F_ST, ST_END)
nums = re.findall(r"// SC-(\d+) ", ST)
check(nums == [str(i) for i in range(1, 11)],
      "I the self-test has ten numbered checks SC-1..SC-10", str(nums))
check(ST.count("return false;") == 10 and ST.rstrip().endswith("return true;\n  }"),
      "I each check can fail with its own reason, and success is explicit",
      "%d returns" % ST.count("return false;"))
check('where="SC-' in ST and ST.count('where="SC-') == 10,
      "I every failure sets a `where` message, like MR_SelfTest before it")
check("SCALP_SpreadVeto(" in ST and "SCALP_RR(" in ST and "SCALP_WeightsSum()" in ST
      and "SCALP_ScoreSide(" in ST and "SCALP_Decide(" in ST,
      "I the self-test exercises the pure cores, not the chart state")
check("1000.0*_Point" in ST,
      "I its numbers are relative to _Point, so the same assertions hold on XAUUSD "
      "and on any FX pair")
check("g_buf_" not in ST and "g_sc_" not in ST,
      "I the self-test touches no mirrored series and no overlay state")

# ------------------------------------------------- J. nothing weakened
for pat, label in ((r"(?m)^input int\s+InpRXNMinConfirmedScore\s*=\s*68;", "68"),
                   (r"(?m)^input ENUM_QSMC_GATE_PROFILE InpGateProfile = QSMC_GATE_STRICT;", "STRICT"),
                   (r"(?m)^input int\s+InpAlertCooldownBars\s*=\s*5;", "cooldown 5"),
                   (r"(?m)^input int\s+InpCFMinDisplayScore\s*=\s*60;", "CF 60"),
                   (r"(?m)^input int\s+InpResMinScore\s*=\s*60;", "resolver 60"),
                   (r"(?m)^input int\s+InpWGMinScore\s*=\s*60;", "weighted gate 60"),
                   (r"(?m)^input bool\s+InpUseFinalResolver\s*=\s*false;", "resolver off"),
                   (r"(?m)^input bool\s+InpUseWeightedGates\s*=\s*false;", "weighted gates off")):
    check(re.search(pat, TEXT), "J %s is unchanged" % label)
check("InpEnableAllModules" not in body(GRP, SESS + 1),
      "J the overlay is NOT folded into InpEnableAllModules: that switch is pinned "
      "to the seven strategy modules, and an advisory overlay is not an eighth one")
check(len(re.findall(r"(?m)^input\s", TEXT)) == 583,
      "J 583 input lines (574 + the 9 OBS1 lines)",
      "got %d" % len(re.findall(r"(?m)^input\s", TEXT)))
check(TEXT.count("{") == TEXT.count("}") == 3821, "J braces balance at 3821",
      "%d/%d" % (TEXT.count("{"), TEXT.count("}")))
check(len(RAW.replace("\r\n", "\n").split("\n")) - 1 == 45664,
      "J the file is 45664 lines: insertions only, no scratch rewrite",
      "got %d" % (len(RAW.replace("\r\n", "\n").split("\n")) - 1))
check("\n" not in RAW.replace("\r\n", ""), "J no bare LF: CRLF everywhere")
check(len(re.findall(r"(?m)^enum\s+ENUM_", TEXT)) == 44,
      "J no enum added or removed (still 44)")
check(len(re.findall(r"(?m)^#include", TEXT)) == 1, "J still exactly one #include")
check(len(re.findall(r"(?m)^#property indicator_buffers", TEXT)) == 1,
      "J no buffers added, so no plot index moved (the EA reads 7-12)")
cs = [i + 1 for i, l in enumerate(LINES) if "PA_ZoneAt(" in l
      and not l.strip().startswith("//") and not re.match(r"^bool\s+PA_ZoneAt\(", l)]
check(len(cs) == 5, "J PA_ZoneAt still has 5 call sites (the overlay reuses it)", str(cs))

# --------------------------------------------------------- K. doc and CI
for phrase in ("## 11.5 AUDIT-SC1", "InpEnableScalping", "SCALP_", "MOM", "EDGE",
               "Silver Bullet", "Power of 3", "Wyckoff", "Confluence",
               "20 / 20 / 15 / 15 / 15 / 15 = 100", "HARD VETO",
               "confluence count, not a probability", "tools/test_scalping.py",
               "CI step 34", "583", "QSMC_PRESET_SCALPER"):
    check(phrase in DOCX, "K the doc states %r" % phrase)
check("L6310" in DOCX, "K the doc cites SCALP_Update's definition line (L6310)")
check("L873" in DOCX, "K the doc cites the overlay flag's line (L873)")
check(re.search(r"run: python3 tools/test_scalping\.py", WFX),
      "K CI runs tools/test_scalping.py")
check(WFX.count("- name: ") == 35, "K the workflow has 35 named steps",
      "got %d" % WFX.count("- name: "))
check("AUDIT-SC1" in WFX, "K the CI step names the audit it enforces")

fails = sum(1 for ok, _, _ in RESULTS if not ok)
print("AUDIT-SC1 scalping checks: %d   failures: %d" % (len(RESULTS), fails))
sys.exit(1 if fails else 0)
