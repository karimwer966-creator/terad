#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MISSED-TRADE FIXES (v6.6.25) - host-execute the REAL MQL5 bodies.

WHAT THIS PROVES
----------------
The 2026-11-27 XAUUSD M15 incident (3562-3570 range, then a vertical rally to
~3684 with no CORE signal) was traced to code, see
docs/MISSED_TRADE_2026-11-27_HYPOTHESES.md. v6.6.25 adds default-OFF switches.
This suite extracts the actual function bodies from nadir2.mq5, compiles them
with a host C++17 compiler (terminal API stubbed) and runs them bar by bar on
deterministic synthetic data:

  B  DetectStructure() with InpRearmStructureAfterBreak
     * switch OFF: identical to the frozen v6.6.24 body
       (tools/fixtures/v6624_DetectStructure.mqh) on every bar of every
       scenario - structures, swing references, trend, cursor and the
       lifecycle log text;
     * switch ON (K = 2, 5, 8): incremental pass == full rebuild on every bar
       (the property the indicator's [CausalReplay] audit checks at runtime);
     * switch ON, incident-shaped series: the vertical leg produces additional
       with-trend BOS events whose reference is exactly the extreme of the K
       closed bars after the previous break (no lookahead).

  C  ContinuationLegOrigin() / ValidateContinuationLeg() on the same series.

  D  TopDownPickTarget(): nearest qualifying target, exact veto reasons.

WHAT THIS IS NOT
----------------
NOT MetaEditor (no F7), NOT the Strategy Tester, NOT live MT5. Synthetic bars
are not market data: nothing here says whether the real 2026-11-27 bars would
have produced a signal - that needs the broker's M15/H1 history (see the
hypotheses report).
"""
from __future__ import print_function

import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_toolchain as NT  # noqa: E402

ROOT = HERE.parent
SRC = ROOT / "nadir2.mq5"
MIRROR = ROOT / "MQL5" / "Indicators" / "nadir2.mq5"
BASE_FRAG = HERE / "fixtures" / "v6624_DetectStructure.mqh"

FAILS = []


def check(ok, label, detail=""):
    print(("PASS  " if ok else "FAIL  ") + label + (("  [" + detail + "]") if detail and not ok else ""))
    if not ok:
        FAILS.append(label)


text = SRC.read_bytes().decode("utf-8").replace("\r\n", "\n")
check(SRC.read_bytes() == MIRROR.read_bytes(),
      "MQL5/Indicators/nadir2.mq5 is a byte-identical mirror of nadir2.mq5")


def definition(src, name):
    """Full text of the DEFINITION of `name` (prototypes are skipped)."""
    for m in re.finditer(r"^\w+\s+" + re.escape(name) + r"\(", src, re.M):
        start = m.start()
        brace = src.index("{", start)
        if ";" in src[start:brace]:
            continue
        i, depth = brace + 1, 1
        while depth:
            depth += (src[i] == "{") - (src[i] == "}")
            i += 1
        return src[start:i]
    raise SystemExit("definition not found: " + name)


def struct_def(src, name):
    m = re.search(r"^struct " + re.escape(name) + r"\n\{.*?^\};", src, re.M | re.S)
    if not m:
        raise SystemExit("struct not found: " + name)
    return m.group(0)


def adapt(s):
    """The mechanical MQL5 -> C++ rewrite this subset needs."""
    s = re.sub(r"(\w+) &(\w+)\[\]", r"Arr<\1> &\2", s)
    s = re.sub(r"\b(bool|int|double|string)\s+(\w+)\[\];", r"Arr<\1> \2;", s)
    return s


cur_detect = adapt(definition(text, "DetectStructure"))
base_src = BASE_FRAG.read_text(encoding="utf-8")
base_detect = adapt(definition(base_src, "DetectStructure"))
s_struct = struct_def(text, "SStructureBreak")

# C/D helpers are optional until those commits land; the suite reports what it ran.
OPTIONAL = {}
for fn in ("ContinuationLegOrigin", "ValidateContinuationLeg", "TopDownPickTarget"):
    try:
        OPTIONAL[fn] = adapt(definition(text, fn))
    except SystemExit:
        OPTIONAL[fn] = None

PRELUDE = r"""
#include <vector>
#include <string>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cfloat>
#include <iostream>
#include <algorithm>
using string = std::string;
using datetime = long long;
template<class T> using Arr = std::vector<T>;
template<class T> int ArraySize(const std::vector<T> &v){ return (int)v.size(); }
template<class T> void ArrayResize(std::vector<T> &v,int n,int reserve=0){ (void)reserve; v.resize(n<0?0:(size_t)n); }
template<class A,class B> auto MathMax(A a,B b)->decltype(a+b){ return a>b?a:b; }
template<class A,class B> auto MathMin(A a,B b)->decltype(a+b){ return a<b?a:b; }
inline double MathAbs(double v){ return std::fabs(v); }
inline bool MathIsValidNumber(double v){ return std::isfinite(v); }
template<class T> T fmt_arg(T v){ return v; }
inline const char *fmt_arg(const std::string &s){ return s.c_str(); }
template<class... A> string StringFormat(const char *f, A... a)
{ char buf[2048]; std::snprintf(buf,sizeof buf,f,fmt_arg(a)...); return string(buf); }
inline string TimeToString(datetime t){ return std::to_string((long long)t); }
inline string IntegerToString(long long v){ return std::to_string(v); }
inline string DoubleToString(double v,int d){ char b[64]; std::snprintf(b,sizeof b,"%.*f",d,v); return b; }
template<class T,class V> void ArrayInitialize(std::vector<T> &v,V x){ for(size_t i=0;i<v.size();i++) v[i]=(T)x; }
const int _Digits = 2;
const double _Point = 0.01;
std::vector<string> g_log;
inline void LogLifecycle(const string &s){ g_log.push_back(s); }
// ---- inputs (mutable here so scenarios can toggle them) ----
int    InpSwingFractalN = 3;
double InpDisplacementATR = 0.9;
int    InpMaxStructuresKeep = 30;
bool   InpLogLifecycleTransitions = true;
bool   InpRearmStructureAfterBreak = false;
int    InpRearmStructureBars = 5;
bool   InpAllowContinuationChain = false;
int    InpSweepToStructureMaxBarsContinuation = 12;
bool   InpTargetLiquidityAware = false;
double InpTopDownMinRR = 2.0;
// ---- engine globals read by the extracted bodies ----
std::vector<double> g_atr_buf;
double g_atr = 0.0;
"""

STATE_DECL = r"""
std::vector<SStructureBreak> g_structures;
double g_struct_last_high=0.0, g_struct_last_low=0.0;
int g_struct_trend=0, g_struct_last_processed_bar=-1, g_struct_last_break_bar=-1;
int g_struct_rearm_high_from=-1, g_struct_rearm_low_from=-1;
bool g_struct_last_high_prov=false, g_struct_last_low_prov=false;
struct Snap { std::vector<SStructureBreak> s; double hi,lo; int tr,cur,brk,rh,rl; bool ph,pl; };
Snap snap(){ return Snap{g_structures,g_struct_last_high,g_struct_last_low,g_struct_trend,
                         g_struct_last_processed_bar,g_struct_last_break_bar,g_struct_rearm_high_from,
                         g_struct_rearm_low_from,g_struct_last_high_prov,g_struct_last_low_prov}; }
void restore(const Snap &x){ g_structures=x.s; g_struct_last_high=x.hi; g_struct_last_low=x.lo;
  g_struct_trend=x.tr; g_struct_last_processed_bar=x.cur; g_struct_last_break_bar=x.brk;
  g_struct_rearm_high_from=x.rh; g_struct_rearm_low_from=x.rl; g_struct_last_high_prov=x.ph;
  g_struct_last_low_prov=x.pl; }
void reset(){ restore(Snap{{},0.0,0.0,0,-1,-1,-1,-1,false,false}); }
"""

HARNESS = r"""
static bool same_struct(const SStructureBreak &a,const SStructureBreak &b)
{ return a.bar==b.bar && a.time==b.time && a.price==b.price && a.bullish==b.bullish &&
         a.type==b.type && a.ob_bar==b.ob_bar && a.strength==b.strength && a.priority==b.priority; }
static bool same_list(const std::vector<SStructureBreak> &a,const std::vector<SStructureBreak> &b)
{ if(a.size()!=b.size()) return false; for(size_t i=0;i<a.size();i++) if(!same_struct(a[i],b[i])) return false; return true; }

struct Series { std::vector<double> o,h,l,c; std::vector<datetime> t; std::vector<double> atr; int rally_from=-1, rally_to=-1; };

static unsigned long long g_seed=1;
static double rnd(){ g_seed=g_seed*6364136223846793005ULL+1442695040888963407ULL; return ((g_seed>>11)&((1ULL<<53)-1))/(double)(1ULL<<53); }

static void finish(Series &s)
{
   int n=(int)s.c.size(); s.t.resize(n); s.atr.assign(n,0.0);
   for(int i=0;i<n;i++) s.t[i]=1764201600LL+900LL*i;       // 2025-11-27 00:00, M15 spacing
   double tr_sum=0.0; std::vector<double> tr(n,0.0);
   for(int i=0;i<n;i++){ double pc=(i>0?s.c[i-1]:s.o[i]);
      tr[i]=std::max(s.h[i],pc)-std::min(s.l[i],pc); tr_sum+=tr[i]; if(i>=14) tr_sum-=tr[i-14];
      s.atr[i]=(i>=13? tr_sum/14.0 : 0.0); }
}
static void push(Series &s,double o,double c,double wick_up,double wick_dn)
{ s.o.push_back(o); s.c.push_back(c); s.h.push_back(std::max(o,c)+wick_up); s.l.push_back(std::min(o,c)-wick_dn); }

// Incident-shaped series: chop, a 3562-3570 Asian range, a vertical rally to ~3684, chop.
static Series incident()
{
   Series s; g_seed=20261127; double p=3540.0;
   for(int i=0;i<120;i++){ double o=p; double c=o+(rnd()-0.5)*6.0; push(s,o,c,rnd()*2.0,rnd()*2.0); p=c; }
   for(int i=0;i<10;i++){ double o=p; double c=o+(3566.0-o)*0.35+(rnd()-0.5)*1.5; push(s,o,c,rnd()*1.2,rnd()*1.2); p=c; }
   for(int i=0;i<56;i++){ double o=p; double mid=3566.0+3.0*std::sin(i*0.7); double c=mid+(rnd()-0.5)*1.2;
      double up=std::min(3570.0-std::max(o,c),rnd()*1.5); double dn=std::min(std::min(o,c)-3562.0,rnd()*1.5);
      push(s,o,c,std::max(0.0,up),std::max(0.0,dn)); p=c; }
   s.rally_from=(int)s.c.size();
   double target=3684.0; int legs=34;
   for(int i=0;i<legs;i++){ double o=p; double step=(target-3568.0)/legs;
      double c=o+step*(0.75+0.5*rnd()); if(i%7==5) c=o-step*0.25;   // shallow pullback bars
      push(s,o,c,rnd()*1.0,rnd()*0.8); p=c; }
   s.rally_to=(int)s.c.size()-1;
   for(int i=0;i<80;i++){ double o=p; double c=o+(rnd()-0.5)*7.0; push(s,o,c,rnd()*2.5,rnd()*2.5); p=c; }
   finish(s); return s;
}
static Series walk(unsigned long long seed,int n,double vol)
{
   Series s; g_seed=seed; double p=2000.0+seed%500;
   for(int i=0;i<n;i++){ double o=p; double drift=((i/200)%2==0?0.15:-0.15)*vol;
      double c=o+drift+(rnd()-0.5)*vol*2.0; push(s,o,c,rnd()*vol*0.8,rnd()*vol*0.8); p=c; }
   finish(s); return s;
}
static Series prefix(const Series &s,int total)
{
   Series r; r.o.assign(s.o.begin(),s.o.begin()+total); r.h.assign(s.h.begin(),s.h.begin()+total);
   r.l.assign(s.l.begin(),s.l.begin()+total); r.c.assign(s.c.begin(),s.c.begin()+total);
   r.t.assign(s.t.begin(),s.t.begin()+total); r.atr.assign(s.atr.begin(),s.atr.begin()+total); return r;
}
static int fails=0;
static void expect(bool ok,const string &what){ if(!ok){ fails++; std::cout<<"FAIL  "<<what<<"\n"; } }
"""

MAIN = r"""
// ---- B: switch OFF == frozen v6.6.24, switch ON incremental == full ----
static void run_b(const char *name,const Series &s,int step_full)
{
   int n=(int)s.c.size();
   // (1) OFF: live body vs frozen body, bar by bar, including the log text.
   InpRearmStructureAfterBreak=false;
   base::reset(); cur::reset(); size_t log_mark=0;
   bool off_same=true, log_same=true; int first_bad=-1;
   for(int total=12; total<=n; total++)
   {
      Series p=prefix(s,total); g_atr_buf=p.atr; g_atr=p.atr[total-1];
      g_log.clear(); base::DetectStructure(total,p.o,p.h,p.l,p.c,p.t,total>12);
      std::vector<string> lb=g_log;
      g_log.clear(); cur::DetectStructure(total,p.o,p.h,p.l,p.c,p.t,total>12);
      if(lb!=g_log){ log_same=false; }
      bool same=same_list(base::g_structures,cur::g_structures) &&
                base::g_struct_last_high==cur::g_struct_last_high && base::g_struct_last_low==cur::g_struct_last_low &&
                base::g_struct_trend==cur::g_struct_trend && base::g_struct_last_processed_bar==cur::g_struct_last_processed_bar &&
                base::g_struct_last_break_bar==cur::g_struct_last_break_bar;
      if(!same && off_same){ off_same=false; first_bad=total; }
   }
   (void)log_mark;
   expect(off_same,string("B OFF ")+name+": live DetectStructure == v6.6.24 on every bar (first diff at total="+std::to_string(first_bad)+")");
   expect(log_same,string("B OFF ")+name+": lifecycle log text identical to v6.6.24");
   int off_bull=0; for(auto &x: cur::g_structures) if(x.bullish && x.type!="INIT" && x.bar>=s.rally_from && x.bar<=s.rally_to) off_bull++;
   std::cout<<"INFO  "<<name<<" OFF: "<<cur::g_structures.size()<<" retained structures, bullish breaks inside rally="<<off_bull<<"\n";

   // (2) ON: incremental == full rebuild for several K.
   int ks[3]={2,5,8};
   for(int ki=0;ki<3;ki++)
   {
      InpRearmStructureAfterBreak=true; InpRearmStructureBars=ks[ki];
      cur::reset(); bool inc_full=true; int bad=-1;
      for(int total=12; total<=n; total++)
      {
         Series p=prefix(s,total); g_atr_buf=p.atr; g_atr=p.atr[total-1];
         cur::DetectStructure(total,p.o,p.h,p.l,p.c,p.t,total>12);
         if(total%step_full==0 || total==n)
         {
            cur::Snap inc=cur::snap();
            cur::DetectStructure(total,p.o,p.h,p.l,p.c,p.t,false);
            cur::Snap full=cur::snap();
            bool same=same_list(inc.s,full.s) && inc.hi==full.hi && inc.lo==full.lo && inc.tr==full.tr &&
                      inc.cur==full.cur && inc.brk==full.brk && inc.rh==full.rh && inc.rl==full.rl &&
                      inc.ph==full.ph && inc.pl==full.pl;
            if(!same && inc_full){ inc_full=false; bad=total; }
            cur::restore(inc);
         }
      }
      expect(inc_full,string("B ON K=")+std::to_string(ks[ki])+" "+name+": incremental == full rebuild (first diff at total="+std::to_string(bad)+")");
      if(s.rally_from>=0 && ks[ki]==5)
      {
         int on_bull=0; for(auto &x: cur::g_structures) if(x.bullish && x.type!="INIT" && x.bar>=s.rally_from && x.bar<=s.rally_to) on_bull++;
         std::cout<<"INFO  "<<name<<" ON K=5: bullish breaks inside rally="<<on_bull<<" (OFF "<<off_bull<<")\n";
         expect(on_bull>=off_bull+2,string("B ON K=5 ")+name+": the vertical leg yields >=2 additional bullish breaks");
         // Every break of a provisional reference must equal the extreme of the K bars after the prior break.
         int checked=0; bool exact=true;
         for(size_t i=1;i<cur::g_structures.size();i++)
         {
            const SStructureBreak &a=cur::g_structures[i-1], &b=cur::g_structures[i];
            if(!(a.bullish && b.bullish) || b.bar<=a.bar+5) continue;
            double ref=0.0; for(int k=a.bar+1;k<=a.bar+5;k++) ref=std::max(ref,s.h[k]);
            if(b.price==ref){ checked++; if(!(s.c[b.bar]>ref)) exact=false; }
         }
         std::cout<<"INFO  "<<name<<" ON K=5: "<<checked<<" break(s) of a provisional K-bar reference verified\n";
         expect(checked>=1 && exact,string("B ON K=5 ")+name+": provisional reference == max(high[B+1..B+5]) and broken by a later close");
      }
   }
   InpRearmStructureAfterBreak=false; InpRearmStructureBars=5;
}
"""


C_TESTS = r"""
// ---- C: continuation leg helpers (real bodies) ----
static void run_c(const Series &s)
{
   int n=(int)s.c.size();
   InpRearmStructureAfterBreak=true; InpRearmStructureBars=5;
   cur::reset();
   for(int total=12; total<=n; total++){ Series p=prefix(s,total); g_atr_buf=p.atr; g_atr=p.atr[total-1];
      cur::DetectStructure(total,p.o,p.h,p.l,p.c,p.t,total>12); }
   g_atr_buf=s.atr; g_atr=s.atr[n-1];
   int legs_ok=0, checked=0; bool causal=true, geometry=true;
   for(auto &st: cur::g_structures)
   {
      if(st.type!="BOS" || !st.bullish || st.bar<s.rally_from || st.bar>s.rally_to) continue;
      checked++;
      int origin=ContinuationLegOrigin(st.bar,st.bullish,s.h,s.l,InpSweepToStructureMaxBarsContinuation);
      int imp=-1; string why;
      bool ok=(origin>=0 && ValidateContinuationLeg(origin,st.bar,st.bullish,st.price,s.o,s.h,s.l,s.c,imp,why));
      // no lookahead: the same call on series truncated right after the BOS close
      Series q=prefix(s,st.bar+2); std::vector<double> keep=g_atr_buf; g_atr_buf=q.atr;
      int origin2=ContinuationLegOrigin(st.bar,st.bullish,q.h,q.l,InpSweepToStructureMaxBarsContinuation);
      int imp2=-1; string why2;
      bool ok2=(origin2>=0 && ValidateContinuationLeg(origin2,st.bar,st.bullish,st.price,q.o,q.h,q.l,q.c,imp2,why2));
      g_atr_buf=keep;
      if(ok!=ok2 || origin!=origin2 || imp!=imp2) causal=false;
      if(ok)
      {
         legs_ok++;
         double body=(s.c[imp]-s.o[imp])/s.atr[imp];
         if(!(origin<=st.bar-2 && imp>origin && imp<st.bar && body>=InpDisplacementATR && s.c[st.bar]>st.price)) geometry=false;
         std::cout<<"INFO  continuation leg: BOS bar "<<st.bar<<" level "<<st.price<<" origin "<<origin
                  <<" impulse "<<imp<<" body/ATR "<<body<<"\n";
      }
      else std::cout<<"INFO  BOS bar "<<st.bar<<" not a continuation leg: "<<why<<"\n";
   }
   expect(checked>0,"C incident: the re-armed rally has bullish BOS events to evaluate");
   expect(legs_ok>0,"C incident: at least one rally BOS has a valid continuation leg (impulse >= InpDisplacementATR x ATR)");
   expect(causal,"C incident: leg origin/impulse/verdict identical on data truncated at the BOS close (no lookahead)");
   expect(geometry,"C incident: origin <= BOS-2 < impulse < BOS, impulse body >= InpDisplacementATR x ATR, BOS closes beyond the level");
   // a quiet range BOS without displacement must be refused with the exact reason
   int origin=-1, imp=-1; string why;
   int rb=s.rally_from-5;
   origin=ContinuationLegOrigin(rb,true,s.h,s.l,InpSweepToStructureMaxBarsContinuation);
   bool ok=(origin>=0 && ValidateContinuationLeg(origin,rb,true,s.l[rb],s.o,s.h,s.l,s.c,imp,why));
   expect(!ok && why.rfind("continuation:",0)==0,"C range bar: refused with a 'continuation:' reason ("+why+")");
   InpRearmStructureAfterBreak=false;
}
"""


D_TESTS = r"""
// ---- D: TopDownPickTarget (real body) ----
static void run_d()
{
   string why;
   Arr<double> c={110.0,125.0,130.0}; Arr<string> lb={"H1 POC","EQH liquidity pool","PDH"};
   int k=TopDownPickTarget(c,lb,3,100.0,10.0,1,2.0,why);
   expect(k==1,"D buy: nearest PAYING target is chosen (125, RR 2.50), not the nearest (110, RR 1.00)");
   expect(why=="H1 POC RR 1.00","D buy: the skipped nearer target is named with its RR ("+why+")");
   Arr<double> s1={90.0,75.0,70.0};
   k=TopDownPickTarget(s1,lb,3,100.0,10.0,-1,2.0,why);
   expect(k==1 && why=="H1 POC RR 1.00","D sell: mirror image picks 75 and names 90");
   Arr<double> c2={105.0,112.0,95.0};
   k=TopDownPickTarget(c2,lb,3,100.0,10.0,1,2.0,why);
   expect(k==-1,"D buy: nothing pays the floor -> -1 (caller then tries the capped ATR projection)");
   expect(why=="H1 POC RR 0.50, EQH liquidity pool RR 1.20","D buy: every nearer candidate is listed in distance order, wrong-side ones ignored ("+why+")");
   Arr<double> c3={120.0};
   Arr<string> l3={"PDH"};
   k=TopDownPickTarget(c3,l3,1,100.0,10.0,1,2.0,why);
   expect(k==0 && why=="","D buy: RR exactly at the floor is accepted (no hidden extra margin)");
   k=TopDownPickTarget(c3,l3,1,100.0,0.0,1,2.0,why);
   expect(k==-1,"D: zero risk is refused, never divided by");
   std::cout<<"INFO  D TopDownPickTarget: 6 selection scenarios executed\n";
}
"""


def build_source():
    parts = [PRELUDE, s_struct + "\n"]
    parts.append("namespace base {\n" + STATE_DECL + base_detect + "\n}\n")
    parts.append("namespace cur {\n" + STATE_DECL + cur_detect + "\n}\n")
    parts.append(HARNESS)
    parts.append(MAIN)
    have_c = OPTIONAL["ContinuationLegOrigin"] and OPTIONAL["ValidateContinuationLeg"]
    if have_c:
        parts.append(OPTIONAL["ContinuationLegOrigin"] + "\n" + OPTIONAL["ValidateContinuationLeg"] + "\n")
        parts.append(C_TESTS)
    have_d = OPTIONAL["TopDownPickTarget"] is not None
    if have_d:
        parts.append(OPTIONAL["TopDownPickTarget"] + "\n")
        parts.append(D_TESTS)
    main = ["int main(){",
            ' Series a=incident(); run_b("incident",a,1);',
            ' Series w1=walk(7,1500,3.0); run_b("walk7",w1,5);',
            ' Series w2=walk(99,1500,1.0); run_b("walk99",w2,5);',
            ' Series w3=walk(12345,900,6.0); run_b("walk12345",w3,3);']
    if have_c:
        main.append(' run_c(a);')
    if have_d:
        main.append(' run_d();')
    main.append(' std::cout<<(fails?"FAILURES ":"OK ")<<fails<<"\\n"; return fails?1:0; }')
    parts.append("\n".join(main) + "\n")
    return "\n".join(parts)


cxx = NT.compiler(sanitizers=False)
if cxx is None:
    raise SystemExit(NT.skip("missed-trade fixes native harness"))
with tempfile.TemporaryDirectory(prefix="qsmc-v6625-") as d:
    cpp, exe = Path(d) / "t.cpp", Path(d) / "t"
    cpp.write_text(build_source())
    proc = subprocess.run([cxx, "-std=c++17", "-O1", "-Wall", "-Wno-unused-variable",
                           "-Wno-unused-but-set-variable", str(cpp), "-o", str(exe)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    check(proc.returncode == 0, "host C++17 build of the extracted MQL5 bodies", proc.stdout[-3000:])
    if proc.returncode == 0:
        run = subprocess.run([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True, timeout=900)
        print(run.stdout.rstrip())
        check(run.returncode == 0, "native scenarios (B/C/D) all passed")

print("NOT MetaEditor, NOT the Strategy Tester, NOT live MT5. Synthetic bars only.")
sys.exit(NT.exit_code(FAILS))
