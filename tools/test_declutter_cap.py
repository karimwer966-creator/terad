#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUDIT-D1 contract: the declutter cap prunes the excess, oldest first.

Phase 1 defect D was reported as "chart clutter". Reading the code, the drawing
side is already disciplined - DrawTextLabel routes through
QSMC_DisplayAllowsObject() and QSMC_InVisualDistance(), every family is capped at
draw time, and PrepareDynamicRedraw() rebuilds the dynamic families each new bar.
The defect was in the object cap itself, which contradicted its own comment and
its own input label in four ways: it deleted whole families instead of the excess,
it measured every object on the chart instead of ours, it filtered on
OBJ_RECTANGLE so the STRUCT_ family (drawn as OBJ_TEXT) could never contribute,
and its accounting ended the loop after one family. This suite pins the fix.

  A  the input surface and the cap value are untouched, and no input was added
  B  the two PURE cores line by line: the excess arithmetic and the oldest-slot
     choice, each asserted to read no global and call no terminal function
  C  the owned-object count: enumerates the chart once, filters by our prefix, and
     uses the same idiom QSMC_ApplyVisualPolicy() already uses
  D  the family pruner: at most `want`, oldest first, ANY object type, fixed-size
     arrays filled in a second pass, and an honest removed count
  E  the cap block: owned before excess, excess gates everything, each family gets
     the remaining budget, the leftover is reported, and ObjectsDeleteAll is gone
  F  the evidence that STRUCT_ was dead: structure marks are OBJ_TEXT, each family
     has exactly one creation site, so widening the type cannot catch a bystander
  G  cadence and cost: new bar only, over cap only, no per-tick walk, no growth
     inside a loop
  H  wiring: the self-test hook inside the file's general switch, SmartObjectCleanup
     still called from OnCalculate behind its own flag, PrepareDynamicRedraw intact
  I  the self-test really has eleven numbered deterministic checks
  J  the counts moved only as declared, and nothing pre-existing was weakened
  K  the doc and CI own the same facts

Every number below was measured against nadir2.mq5, not computed from a diff.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "nadir2.mq5")
DOC = os.path.join(ROOT, "docs", "QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md")
WF = os.path.join(ROOT, ".github", "workflows", "qsmc-verify.yml")

RAW = io.open(SRC, encoding="utf-8", newline="").read()
TEXT = RAW.replace("\r\n", "\n")
LINES = TEXT.split("\n")
DOCX = io.open(DOC, encoding="utf-8").read()
WFX = io.open(WF, encoding="utf-8").read()

RESULTS = []


def check(ok, label, detail=""):
    RESULTS.append((bool(ok), label, detail))
    out = ("PASS  " if ok else "FAIL  ") + label
    if detail and not ok:
        out += "  [%s]" % detail
    print(out)


def line_at(n):
    return LINES[n - 1]


def body(a, b):
    return "\n".join(LINES[a - 1:b])


def fn_end(start):
    """Closing-brace line of the function whose signature begins at `start`.

    Depth is ignored until a brace has actually opened, so a multi-line signature
    cannot end the function on line two.
    """
    depth = 0
    opened = False
    for i in range(start - 1, len(LINES)):
        depth += LINES[i].count("{") - LINES[i].count("}")
        if depth > 0:
            opened = True
        if opened and depth <= 0:
            return i + 1
    return len(LINES)


# ---------------------------------------------------- measured anchors
INP_CAP, INP_DECL, INP_SMART = 1285, 1287, 1297
BANNER = 7515
EXCESS, OLDEST, COUNT, DELETE = 7535, 7547, 7564, 7580
SELFTEST, SMART = 7622, 7666
CAPLINE, OWNEDCALL, EXCESSCALL = 7675, 7681, 7682
CUT, FAMCALL, LEFTOVER = 7691, 7694, 7705
FAM_ZONE, FAM_STRUCT, FAM_OB, FAM_FVG = 27257, 27275, 27289, 27322
STRUCT_LABEL_CALL = 27277
GUARD, OBS_HOOK, HOOK_PASS, HOOK_FAIL = 14919, 14959, 14963, 14965
ONCALC, SMART_CALL = 15097, 15570
DISPLAY_ALLOWS, VISUAL_POLICY = 39675, 39686

EXCESS_END, OLDEST_END = fn_end(EXCESS), fn_end(OLDEST)
COUNT_END, DELETE_END = fn_end(COUNT), fn_end(DELETE)
SELFTEST_END, SMART_END = fn_end(SELFTEST), fn_end(SMART)
GUARD_END = fn_end(GUARD)
REGION = body(BANNER, SELFTEST_END)
CB = body(CAPLINE - 2, LEFTOVER + 3)          # the cap block inside SmartObjectCleanup
# The block's own comments name the API it replaced, on purpose, so the next
# reader knows what changed. Assertions about what the CODE does therefore run
# against the block with its comments stripped.
CB_CODE = "\n".join(l.split("//")[0] for l in LINES[CAPLINE - 3:LEFTOVER + 2])

check(EXCESS_END == 7541 and OLDEST_END == 7559 and COUNT_END == 7574
      and DELETE_END == 7617, "A the four new functions close where this suite says",
      "%d %d %d %d" % (EXCESS_END, OLDEST_END, COUNT_END, DELETE_END))
check(SELFTEST_END == 7664 and SMART_END == 7730 and GUARD_END == 14966,
      "A the self-test, SmartObjectCleanup and the hook block close where expected",
      "%d %d %d" % (SELFTEST_END, SMART_END, GUARD_END))

# ------------------------------------------------------- A. inputs untouched
A_EXACT = {
    INP_CAP: "input int    InpMaxChartObjects         = 0;      // hard cap on QSMC_* chart objects per pass (0 = 1200, 900 with Clean)",
    INP_DECL: "input bool   InpDeclutterMode           = true;   // Clean preset: fewer zones, small labels, capped objects",
    INP_SMART: "input bool   InpSmartObjectManagement  = true;",
    CAPLINE: "      int cap=(InpMaxChartObjects>0 ? InpMaxChartObjects : (InpDeclutterMode?900:1200));",
}
for ln, want in sorted(A_EXACT.items()):
    check(line_at(ln) == want, "A L%d is unchanged: %r" % (ln, want.strip()[:66]),
          "got %r" % line_at(ln)[:88])
check(len(re.findall(r"(?m)^input\s", TEXT)) == 583,
      "A the fix adds no input: the count is still 583",
      "got %d" % len(re.findall(r"(?m)^input\s", TEXT)))
check(not re.search(r"(?m)^input .*(OldestSlot|OwnedObjects|DeleteOldest|DeclutterExcess|DeclutterOwn|DeclutterFamily)", TEXT),
      "A and no new declutter input was introduced behind the operator's back "
      "(InpDeclutterMode and InpMaxChartObjects are the pre-existing two)")

# ------------------------------------------------------- B. the pure cores
EX = body(EXCESS, EXCESS_END)
check(line_at(EXCESS) == "int QSMC_DeclutterExcess(const int owned,const int cap)",
      "B the excess core takes two ints and nothing else")
for want in ("   if(cap<=0) return 0;", "   if(owned<=0) return 0;",
             "   if(owned<=cap) return 0;", "   return owned-cap;"):
    check(want in EX, "B the excess core contains %r" % want.strip())
check(EX.find("if(cap<=0)") < EX.find("return owned-cap;"),
      "B a non-positive cap is refused before any subtraction")
check("owned<=cap" in EX and "owned<cap" not in EX,
      "B the cap is inclusive: at the cap nothing is pruned")
for bad in ("g_", "Object", "Print", "ArraySize", "iTime"):
    check(bad not in EX, "B the excess core touches no %s: it is pure" % bad)

OL = body(OLDEST, OLDEST_END)
check(line_at(OLDEST) == "int QSMC_OldestSlot(const datetime &times[],const bool &taken[])",
      "B the oldest-slot core takes two arrays by reference")
for want in ("   int n=ArraySize(times);", "   int m=ArraySize(taken);",
             "   if(m<n) n=m;", "   int best=-1;", "      if(taken[i]) continue;",
             "      if(best<0 || times[i]<times[best]) best=i;", "   return best;"):
    check(want in OL, "B the oldest-slot core contains %r" % want.strip())
check(OL.find("if(m<n) n=m;") < OL.find("for(int i=0;i<n;i++)"),
      "B a shorter mask bounds the scan, so a size mismatch cannot read past either array")
check("times[i]<times[best]" in OL and "times[i]<=times[best]" not in OL,
      "B ties go to the lower index: a strict < keeps one pass reproducible")
check(OL.find("int best=-1;") < OL.find("for(int i=0"),
      "B the answer starts at -1, so an empty or fully taken list returns -1")
for bad in ("g_", "Object", "Print", "datetime t["):
    check(bad not in OL, "B the oldest-slot core touches no %s: it is pure" % bad)

# ------------------------------------------------------- C. counting what is ours
CO = body(COUNT, COUNT_END)
check(line_at(COUNT) == "int QSMC_CountOwnedObjects()", "B the owned count takes no argument")
for want in ("   int total=ObjectsTotal(0,-1,-1);", "   for(int i=total-1;i>=0;i--)",
             "      string name=ObjectName(0,i,-1,-1);",
             '      if(name!="" && StringFind(name,PFX)==0) owned++;', "   return owned;"):
    check(want in CO, "C the owned count contains %r" % want.strip()[:66])
check("ObjectsDelete" not in CO and "ObjectCreate" not in CO,
      "C counting never creates or deletes anything")
check(CO.count("ObjectsTotal(") == 1, "C one enumeration per call, not one per object")
POL = body(VISUAL_POLICY, fn_end(VISUAL_POLICY))
check("ObjectsTotal(0,-1,-1)" in POL and "ObjectName(0,i,-1,-1)" in POL,
      "C QSMC_ApplyVisualPolicy (L%d) already enumerates the chart the same way" % VISUAL_POLICY)
check('StringFind(name,PFX)!=0' in POL,
      "C the policy filters by the same prefix, testing it the other way round")
check("QSMC_DisplayAllowsObject" not in CO,
      "C counting is not display policy: the count must be the truth, not the wish")

# ------------------------------------------------------- D. pruning one family
DE = body(DELETE, DELETE_END)
check(line_at(DELETE) == "int QSMC_DeleteOldestFamily(const string prefix,const int want)",
      "D the family pruner takes a prefix and a budget")
check('if(want<=0 || prefix=="") return 0;' in DE,
      "D a non-positive budget or an empty prefix prunes nothing")
for want in ("   int found=0;", "      if(name!=\"\" && StringFind(name,prefix)==0) found++;",
             "   if(found<=0) return 0;", "   ArrayResize(names,found);",
             "   ArrayResize(times,found);", "   ArrayResize(taken,found);",
             "   int n=MathMin(want,k);", "      int slot=QSMC_OldestSlot(times,taken);",
             "      if(slot<0) break;", "      taken[slot]=true;",
             "      if(ObjectDelete(0,names[slot])) removed++;", "   return removed;"):
    check(want in DE, "D the family pruner contains %r" % want.strip()[:66])
check("OBJ_RECTANGLE" not in DE and "OBJ_TEXT" not in DE and "OBJPROP_TYPE" not in DE,
      "D no type filter: a family drawn as text is pruned like a family drawn as boxes")
check("ObjectsDeleteAll" not in DE, "D the family pruner never deletes a whole family at once")
check(DE.count("ArrayResize(") == 3,
      "D the three arrays are sized once each, outside any loop",
      "got %d" % DE.count("ArrayResize("))
check(DE.find("ArrayResize(names,found);") > DE.find("if(found<=0) return 0;"),
      "D and they are sized after the count is known, so nothing grows inside a loop")
check(DE.count("for(int i=total-1;i>=0;i--)") == 2,
      "D two passes over the object list: one to count, one to fill",
      "got %d" % DE.count("for(int i=total-1;i>=0;i--)"))
check(DE.find("int n=MathMin(want,k);") < DE.find("for(int d=0;d<n;d++)"),
      "D the budget is clamped to what the family actually holds")
check("times[k]=(datetime)ObjectGetInteger(0,name,OBJPROP_TIME,0);" in DE,
      "D age is the object's own anchor time: no price, no history, no symbol assumption")
check(DE.find("taken[slot]=true;") < DE.find("if(ObjectDelete(0,names[slot])) removed++;"),
      "D a slot is marked taken before it is deleted, so it can never be chosen twice")
check("if(ObjectDelete(0,names[slot])) removed++;" in DE,
      "D the count returned is the objects that really went, not the ones attempted")
check("g_" not in DE.replace("g_visual", ""), "D the family pruner reads no global state")

# ------------------------------------------------------- E. the cap block
check(line_at(OWNEDCALL) == "      int owned=QSMC_CountOwnedObjects();",
      "E the cap block measures OUR objects, not the whole chart")
check(line_at(EXCESSCALL) == "      int excess=QSMC_DeclutterExcess(owned,cap);",
      "E and turns that measurement into a budget through the pure core")
check(OWNEDCALL < EXCESSCALL < EXCESSCALL + 2, "E owned is measured before the budget is computed")
check("ObjectsTotal(0,-1,-1)" not in CB_CODE,
      "E the cap block no longer measures with ObjectsTotal: that counted other "
      "indicators' and the operator's own objects against our cap")
check("ObjectsDeleteAll" not in CB_CODE,
      "E the cap block no longer calls ObjectsDeleteAll: that deleted whole families")
check("OBJ_RECTANGLE" not in CB_CODE,
      "E and no longer filters on OBJ_RECTANGLE, which made STRUCT_ unprunable")
check(line_at(CUT) ==
      '         string cut[4]; cut[0]=PFX+"ZONE_"; cut[1]=PFX+"STRUCT_"; '
      'cut[2]=PFX+"OB_"; cut[3]=PFX+"FVG";',
      "E the four families and their priority order are exactly as before")
check(line_at(CUT + 1) == "         for(int c=0;c<4 && excess>0;c++)",
      "E the loop still stops the moment the budget is spent")
check(line_at(FAMCALL) == "            int removed=QSMC_DeleteOldestFamily(cut[c],excess);",
      "E each family is handed the REMAINING budget, so no family can over-delete")
check("               excess-=removed;" in body(FAMCALL, FAMCALL + 6),
      "E and the budget is spent down by what really went")
check(LEFTOVER + 0 > FAMCALL, "E the leftover report comes after the loop")
check(line_at(LEFTOVER) == "         if(excess>0)",
      "E if the decorations cannot cover the excess, that is reported")
check('"[Objects] still ",excess," over the cap "' in line_at(LEFTOVER + 1),
      "E in words an operator can find in the log")
check("entry marks and the dashboard are never pruned" in line_at(LEFTOVER + 2),
      "E and the report states what was deliberately left alone")
check(not re.search(r'PFX\+"(ENTRY|SL|TP1|TP2|TP3|ENTRY_ARROW|CONNECT|CORE_DASH)', CB),
      "E no cap path deletes an entry mark, a trade level or the dashboard")
check('"[Objects] ",removed," ",cut[c],"* objects removed, oldest first (cap ",cap,'
      in body(FAMCALL, FAMCALL + 6),
      "E the per-family log still starts with [Objects] and now says oldest first")
check("drop the oldest ZONE_/STRUCT_/OB_/FVG_ decorations (never entry marks)"
      in body(SMART, CAPLINE),
      "E the v6.4.2 promise is still written above the block - and now the code keeps it")

# ------------------------------------------------------- F. the STRUCT_ evidence
check(line_at(FAM_STRUCT) == '      string name=PFX+"STRUCT_"+IntegerToString(st.bar)+"_"+st.type;',
      "F structure marks are named STRUCT_<bar>_<type> (L%d)" % FAM_STRUCT)
check(line_at(STRUCT_LABEL_CALL).strip().startswith("DrawTextLabel(name,st.time,st.price,st.type"),
      "F and are drawn by DrawTextLabel (L%d), which creates OBJ_TEXT" % STRUCT_LABEL_CALL)
check("ObjectCreate(0,name,OBJ_TEXT,0,tm,price)" in TEXT,
      "F DrawTextLabel's object type is OBJ_TEXT, so the old OBJ_RECTANGLE filter "
      "could never match a structure mark")
for ln, fam in ((FAM_ZONE, "ZONE_"), (FAM_STRUCT, "STRUCT_"), (FAM_OB, "OB_"), (FAM_FVG, "FVG_")):
    hits = [n for n in range(1, len(LINES) + 1)
            if re.search(r'string name=PFX\+"%s"' % fam, LINES[n - 1])]
    check(hits == [ln], "F the %s family has exactly one creation site (L%d)" % (fam, ln),
          "found %s" % hits)
check("ObjectCreate(0,name,OBJ_RECTANGLE,0,t1,p1,t2,p2)" in TEXT,
      "F zone boxes are OBJ_RECTANGLE, so widening the type adds STRUCT_ and no bystander")

# ------------------------------------------------------- G. cadence and cost
check(line_at(SMART + 2) == "   if(!InpSmartObjectManagement) return;",
      "G the whole cleanup still sits behind InpSmartObjectManagement")
check("   if(isNewBar)" in body(SMART, CAPLINE),
      "G the cap runs once per NEW BAR, never per tick")
check(line_at(EXCESSCALL + 1) == "      if(excess>0)",
      "G and the pruning is entered only when the budget is actually over zero",
      "got %r" % line_at(EXCESSCALL + 1)[:60])
check("for(int i=total-1;i>=0;i--)" in CO and "prev_calculated" not in CO,
      "G the enumeration walks the chart's object list, not the price history")
check(not re.search(r"for\([^)]*rates_total", REGION),
      "G nothing in the new region loops over the price series")
check("ChartRedraw" not in REGION, "G the new region forces no redraw of its own")

# ------------------------------------------------------- H. wiring
check(line_at(GUARD) == "   if(InpMTEERunSelfTest)",
      "H the self-test hook lives inside the file's general self-test switch (L%d)" % GUARD)
check(HOOK_PASS < GUARD_END and HOOK_FAIL < GUARD_END,
      "H both hook branches are inside that block, which closes at L%d" % GUARD_END)
check(HOOK_PASS > OBS_HOOK, "H the declutter hook runs after the journal's (L%d)" % OBS_HOOK)
check(line_at(HOOK_PASS - 1) == "      if(QSMC_DeclutterSelfTest(mtee_fail))",
      "H the hook calls QSMC_DeclutterSelfTest with the shared failure string")
check("PASS (11/11)" in line_at(HOOK_PASS),
      "H the pass line states the number of checks it runs", "got %r" % line_at(HOOK_PASS)[:80])
check(line_at(HOOK_FAIL).strip().endswith('self-test: FAIL - ",mtee_fail);'),
      "H the fail line reports the reason, like every other self-test hook here")
check(line_at(SMART_CALL) == "   if(InpSmartObjectManagement) SmartObjectCleanup(is_new_bar);",
      "H OnCalculate still calls SmartObjectCleanup(is_new_bar) at L%d" % SMART_CALL)
check(SMART_CALL > ONCALC, "H that call is inside OnCalculate, which starts at L%d" % ONCALC)
REDRAW = [n for n in range(1, len(LINES) + 1)
          if re.match(r"^void PrepareDynamicRedraw\(\)$", LINES[n - 1])]
check(len(REDRAW) == 1, "H PrepareDynamicRedraw is still defined once", "found %s" % REDRAW)
RD = body(REDRAW[0], fn_end(REDRAW[0]))
for fam in ("ZRE_", "RXN_", "SNIPER_", "SBP3_", "WY_", "STRUCT_", "ZONE_", "PD_", "OB_", "FVG"):
    check('ObjectsDeleteAll(0,PFX+"%s")' % fam in RD,
          "H the rebuild sweep still clears %s wholesale, as it always has" % fam)
check("QSMC_DeleteOldestFamily" not in RD,
      "H the rebuild sweep was not switched to the budgeted pruner: it is a redraw, "
      "not a cap, and those families are rebuilt in the same pass")

# ------------------------------------------------------- I. the self-test
ST = body(SELFTEST, SELFTEST_END)
check(line_at(SELFTEST) == "bool QSMC_DeclutterSelfTest(string &where)",
      "I the self-test reports through the shared where-string")
check('where="";' in ST, "I and clears it first, so a stale reason is never reported")
for i in range(1, 12):
    tag = "DC-%d" % i
    hits = len(re.findall(r"\b%s\b" % tag, ST))
    check(hits == 2, "I %s appears twice: as the comment and as the failure reason" % tag,
          "got %d" % hits)
check(ST.count("return false; }") == 11, "I all eleven checks can fail the self-test",
      "got %d" % ST.count("return false; }"))
check(ST.rstrip().endswith("return true;\n  }"), "I the self-test ends by passing")
for bad in ("Object", "g_", "Print(", "Chart", "iTime(", "Symbol("):
    check(bad not in ST, "I the self-test touches no %s: it is deterministic and chart-free" % bad)
check("QSMC_DeclutterExcess(1201,1200)!=1" in ST,
      "I DC-3 pins the exact defect: one over the cap costs ONE object")
check("QSMC_DeclutterExcess(1500,900)!=600" in ST,
      "I DC-4 pins that the excess is the difference, so the chart lands on the cap")
check("QSMC_DeclutterExcess(5000,0)!=0" in ST,
      "I DC-5 pins that a non-positive cap prunes nothing")
check("t[1]=(datetime)100" in ST and "t[3]=(datetime)100" in ST,
      "I DC-7/DC-8 pin the age order with a deliberate tie")
check("tk[1]=true;" in ST, "I DC-9 pins that a taken slot is skipped")
check("QSMC_OldestSlot(notime,none)!=-1" in ST, "I DC-11 pins the empty list")

# ------------------------------------------------------- J. counts and nothing weakened
check(len(TEXT.split("\n")) - 1 == 43352, "J the file is 43352 lines",
      "got %d" % (len(TEXT.split("\n")) - 1))
check(TEXT.count("{") == TEXT.count("}") == 3593, "J braces balance at 3593",
      "got %d / %d" % (TEXT.count("{"), TEXT.count("}")))
check(len(re.findall(r"(?m)^enum\s+ENUM_", TEXT)) == 44, "J still 44 enums",
      "got %d" % len(re.findall(r"(?m)^enum\s+ENUM_", TEXT)))
check(RAW.replace("\r\n", "").count("\n") == 0, "J every line still ends CRLF")
check(TEXT.count("#include") == 1, "J still exactly one #include")
check(TEXT.count("ObjectsDeleteAll(") == 41,
      "J ObjectsDeleteAll( is at 41: 50 before the purge, minus the 9 calls that lived in dead code, "
      "the two comments that name the old API so the next reader knows what changed",
      "got %d" % TEXT.count("ObjectsDeleteAll("))
check(TEXT.count("DrawTextLabel(") == 32, "J DrawTextLabel( is untouched at 32",
      "got %d" % TEXT.count("DrawTextLabel("))
check(TEXT.count("OBJ_HLINE") == 6, "J OBJ_HLINE is untouched at 6",
      "got %d" % TEXT.count("OBJ_HLINE"))
check(TEXT.count("ObjectCreate(") == 16, "J ObjectCreate( fell 24 -> 16 with the dead renderers",
      "got %d" % TEXT.count("ObjectCreate("))
check(TEXT.count("PA_ZoneAt(") == 11, "J PA_ZoneAt( is untouched at 11",
      "got %d" % TEXT.count("PA_ZoneAt("))
J_EXACT = {
    853: "input bool   InpUseFinalResolver     = false; // ONE verdict for card STATUS, tactical",
    868: "input int    InpWGMinScore           = 60;    // weighted points a candidate needs to be published",
    881: "input int    InpScalpMinScore            = 60;    // weighted points needed to name a scalp",
    889: "input bool   InpEnableDecisionJournal  = false; // record one row per CLOSED bar",
    7713: '      ObjectDelete(0,PFX+"SETUPZONE");',
    7720: '      ObjectDelete(0,PFX+"ENTRY");',
    7728: '      for(int i=0;i<10;i++) ObjectDelete(0,PFX+"TBOX_"+IntegerToString(i));',
    15749: "      OBS_Record(closed,rates_total);",
}
for ln, want in sorted(J_EXACT.items()):
    check(line_at(ln) == want, "J L%d is unchanged: %r" % (ln, want.strip()[:62]),
          "got %r" % line_at(ln)[:80])
for name in ("QSMC_DeclutterExcess", "QSMC_OldestSlot", "QSMC_CountOwnedObjects",
             "QSMC_DeleteOldestFamily", "QSMC_DeclutterSelfTest"):
    defs = len(re.findall(r"(?m)^(?:int|bool) %s\(" % name, TEXT))
    uses = TEXT.count(name + "(")
    check(defs == 1, "J %s is defined exactly once" % name, "got %d" % defs)
    check(uses >= 2, "J %s is used as well as defined (%d occurrences)" % (name, uses),
          "got %d" % uses)

# ------------------------------------------------------- K. doc and CI
for phrase in ("## 11.7 AUDIT-D1", "InpMaxChartObjects", "QSMC_DeclutterExcess",
               "QSMC_OldestSlot", "QSMC_DeleteOldestFamily", "oldest first",
               "ObjectsDeleteAll", "OBJ_RECTANGLE", "STRUCT_",
               "tools/test_declutter_cap.py", "CI step 36", "583",
               "one object over the cap", "never pruned"):
    check(phrase in DOCX, "K the doc states %r" % phrase)
check("L7666" in DOCX, "K the doc cites SmartObjectCleanup's definition line (L7666)")
check("L7535" in DOCX, "K the doc cites the excess core's line (L7535)")
check("L7675" in DOCX, "K the doc cites the cap value's line (L7675)")
check("L1285" in DOCX, "K the doc cites the cap input's line (L1285)")
check(re.search(r"run: python3 tools/test_declutter_cap\.py", WFX),
      "K CI runs tools/test_declutter_cap.py")
check(WFX.count("- name: ") == 36, "K the workflow has 36 named steps",
      "got %d" % WFX.count("- name: "))
check("AUDIT-D1" in WFX, "K the CI step names the audit it enforces")

fails = sum(1 for ok, _, _ in RESULTS if not ok)
print("AUDIT-D1 declutter cap checks: %d   failures: %d" % (len(RESULTS), fails))
sys.exit(1 if fails else 0)
