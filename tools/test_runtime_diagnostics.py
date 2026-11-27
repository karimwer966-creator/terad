#!/usr/bin/env python3
"""v6.6.20 runtime-log review contracts.

The supplied MT5 excerpt showed startup CopyBuffer waits, duplicate visual/reader
diagnostics and a false chart-object survivor count after a two-bar attach. This
suite checks the wording/ownership fixes without claiming to reproduce MT5 I/O.
Native subsets exercise the actual renderer cleanup methods and copy-status text.
"""
from pathlib import Path
import re
import subprocess
import tempfile

import native_toolchain as NT

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "nadir2.mq5"
TEXT = HOST.read_text(encoding="utf-8")
FAILURES = []


def check(ok, label):
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        FAILURES.append(label)


def code_only(s):
    s = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', s)
    s = re.sub(r"//[^\n]*", "", s)
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


CXX = NT.compiler(sanitizers=True)


def compile_run(source, label):
    if CXX is None:
        NT.skip("native subset: " + label, sanitizers=True)
        return
    with tempfile.TemporaryDirectory() as d:
        cpp = Path(d) / "subset.cpp"
        exe = Path(d) / "subset"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run([CXX, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                        str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("PASS  native subset: " + label)


check(HOST.read_bytes().count(b"\n") == HOST.read_bytes().count(b"\r\n"),
      "canonical host remains pure CRLF")
check('#property version   "6.625"' in TEXT and
      '#define QSMC_VERSION_TEXT "v6.6.25"' in TEXT,
      "host identity is v6.6.25 (v6.6.25 missed-trade fixes release)")
check(TEXT == (ROOT / "MQL5/Indicators/nadir2.mq5").read_text(encoding="utf-8"),
      "deployment copy is synchronized")

init = TEXT[TEXT.index("int OnInit()"):TEXT.index("void OnDeinit(")]
role = init.index("g_qsmc_silent_reader=1")
adapter = init.index('Print("[InstrumentAdapter] ",_Symbol')
root = init.index("QSMC_RootCreate(")
check(role < adapter < root, "reader role is known before the first informational banner/root")
check("g_qsmc_silent_reader=0;   // reinit must not inherit a previous reader role" in init,
      "OnInit resets reader silence before handshake detection")
check("if(!QSMC_IsReaderSilent())\n      Print(\"[InstrumentAdapter] \"" in init.replace("\r\n", "\n"),
      "instrument banner is visual-only")
check('LIVE MARKET | ANALYSIS ONLY (no orders)' in init and
      'BACKTEST | ANALYSIS ONLY (no orders)' in init and
      '"LIVE TRADING"' not in TEXT,
      "startup mode cannot imply the indicator sends orders")
check(len(re.findall(r"\bInpRealTimeZones\b", code_only(TEXT))) == 1 and
      "LEGACY/INERT: not a runtime switch" in TEXT,
      "legacy RealTimeZones input no longer pretends to control runtime authority")
check("Zone/signal authority: CLOSED BARS" in init and
      "Calculation cadence: " in init and "InpUpdateEveryTick ?" in init,
      "startup reports the real closed-bar authority and calculation cadence")
check("void QSMC_InitPass(const string message)" in TEXT and
      'if(!QSMC_IsReaderSilent()) Print(">>> ",QSMC_VERSION_TEXT,message);' in TEXT,
      "PASS helper suppresses only visual duplicate text")
for call in ("MVP_SelfTest()", "TacticalAuthoritySelfTest(mtee_fail)",
             "ZRE_SelfTest()", "RXN_SelfTestRun(rxn_fail)",
             "LegGeometry_SelfTest()", "SigLog_SelfTest()",
             "MTF_SniperZone_SelfTest()"):
    check(call in init, "reader still executes " + call)
check("if(InpSniperRunSelfTest && !QSMC_IsReaderSilent())" not in init,
      "sniper self-test is not skipped merely because the instance is a reader")
flat = init.replace("\r\n", "\n")
check(not re.search(r"if\(!QSMC_IsReaderSilent\(\)\)\s*Print\([^\n]*FAIL", flat),
      "FAIL prints are not hidden by the reader silence guard")
check("if(g_pmi_self_test_failures==0)\n   {\n      if(!QSMC_IsReaderSilent())" in TEXT.replace("\r\n", "\n"),
      "PMI PASS silence cannot turn a successful reader self-test into a FAIL print")

status = TEXT[TEXT.index("// QSMC_COPY_STATUS_BEGIN"):TEXT.index("// QSMC_COPY_STATUS_END")]
compile_run(r'''
#include <string>
#include <cassert>
using string=std::string;
string IntegerToString(int v){return std::to_string(v);}
''' + status + r'''
int main(){
  string a=QSMC_CopyStatus(-1,200,4806,0);
  assert(a.find("not ready")!=string::npos);
  assert(a.find("copied -1/200")!=string::npos);
  assert(a.find("terminal_error 4806")!=string::npos);
  assert(a.find("calculated 0")!=string::npos);
  string b=QSMC_CopyStatus(12,200,0,-1);
  assert(b.find("partial history")!=string::npos);
  assert(b.find("copied 12/200")!=string::npos);
  assert(b.find("calculated")==string::npos);
}
''', "copy status distinguishes failed/not-ready from partial history")
for token in ('QSMC_CopyStatus(copied,count,copy_error,-1)',
              'QSMC_CopyStatus(copied,count,copy_error,BarsCalculated(handle))',
              'IntegerToString(QSMC_IND_COPY_MAX_RETRY)',
              '" update attempts; this update is skipped"',
              '" READY ",copied,"/",count',
              'g_sniper_rates_warned[tf_idx]=false;',
              'warned_flag=false;'):
    check(token in TEXT, "sniper data-health contract: " + token)
check(len(re.findall(r'\[SniperDataHealth\] (?:WARNING )?role=', TEXT)) >= 7,
      "sniper waits/warnings/recoveries identify the instance role")

incident = (ROOT / "MQL5/Include/QSMC/QSMC_IncidentSafety.mqh").read_text(encoding="utf-8")
check('if(!QSMC_IsReaderSilent() &&\n            UD_LogAllows("ZONE_REJECT|"' in incident.replace("\r\n", "\n"),
      "routine zone-rejection log is visual-only; the reject path itself is unchanged")
# ---------------------------------------------- AUD-07 root lifecycle fails closed
# CQuantumRoot::Init() sets m_ready=true only at the very end and returns false
# early on a market-data failure or a failed ConfigureStructure(). Before the fix
# a failed Init() left g_qsmc_root pointing at a half-initialised root, so the
# next QSMC_RootCreate() took the `!=NULL` short circuit and returned true -
# reporting success over a root that had never become ready, and never getting
# another chance to initialise. Every consumer asks QSMC_Root()!=NULL, which a
# half-initialised root satisfies.
root_src = (ROOT / "MQL5/Include/QSMC/QSMC_Root.mqh").read_text(encoding="utf-8")
root_code = code_only(root_src)
_i = root_code.index("bool QSMC_RootCreate(")
_j = root_code.index("void QSMC_RootDestroy()", _i)
_create = root_code[_i:_j]

check("if(g_qsmc_root!=NULL) return true;" not in _create,
      "AUD-07 the create path no longer short-circuits to a bare true")
check("if(g_qsmc_root!=NULL) return g_qsmc_root.Ready();" in _create,
      "AUD-07 an existing root reports Ready(), not merely allocated")
check(re.search(r"bool\s+ok\s*=\s*g_qsmc_root\.Init\(", _create) is not None,
      "AUD-07 Init()'s verdict is captured instead of returned unread")
check("delete g_qsmc_root;" in _create and "g_qsmc_root=NULL;" in _create,
      "AUD-07 a failed Init() destroys the half-initialised root")
check(_create.index("delete g_qsmc_root;") < _create.index("return ok;"),
      "AUD-07 and destroys it before returning, not after")
check("if(!ok)" in _create,
      "AUD-07 the cleanup is conditional on the failure, so a successful Init() "
      "is untouched")
check("root Init() failed" in root_src,
      "AUD-07 the failure is logged, so an arbitration layer that is OFF says so")

# The host must not discard the verdict, and the feed path must not trust a
# non-NULL pointer on its own. Both are in nadir2.mq5 and both are line-count
# neutral edits, so no pinned citation moved.
check("if(!QSMC_RootCreate(SelectExecutionTF(),300,InpATRPeriod))" in TEXT,
      "AUD-07 the host reads QSMC_RootCreate()'s return value")
check("root create FAILED (AUD-07)" in TEXT,
      "AUD-07 and logs when arbitration comes up OFF")
check("if(arb==NULL || !arb.Ready()) return;" in TEXT,
      "AUD-07 the arbiter feed refuses a root that is allocated but not ready")
check(TEXT.count("QSMC_RootCreate(SelectExecutionTF()") == 1,
      "AUD-07 there is exactly one create site to get this right at")

# Every root method the feed path calls must guard m_ready itself, so the
# contract holds even for a caller that forgets the check above. The scan walks
# lines rather than hunting for a closing-brace pattern: the first draft sliced
# to "\n   }" and crashed, because the class body is indented differently at
# each depth and no single closing pattern covers all three methods.
_root_lines = root_src.replace("\r\n", "\n").split("\n")
for _m in ("Refresh", "SetZones", "FinalizeBar"):
    _def = -1
    for _n, _l in enumerate(_root_lines):
        if re.search(r"\b%s\s*\(" % _m, _l) and "m_ready" not in _l \
                and not _l.strip().startswith("//") and not _l.strip().endswith(";"):
            _def = _n
            break
    check(_def >= 0, "AUD-07 %s() is defined in QSMC_Root.mqh" % _m)
    if _def >= 0:
        _win = "\n".join(_root_lines[_def:_def + 8])
        check("m_ready" in _win,
              "AUD-07 %s() guards m_ready internally, not only at its caller" % _m)

# The lifecycle is small enough to execute, so it is executed: a root whose
# Init() fails must leave no root behind, must report false, and must let the
# NEXT call attempt a real Init() again rather than reporting success over the
# corpse. Transcribed from QSMC_Root.mqh; not MetaEditor.
compile_run(r'''
#include <cassert>
#include <cstdio>
struct CQuantumRoot {
  bool ready=false; static int made; static bool fail_next;
  CQuantumRoot(){ made++; }
  bool Init(){ if(fail_next) return false; ready=true; return true; }
  bool Ready() const { return ready; }
};
int CQuantumRoot::made=0; bool CQuantumRoot::fail_next=false;
static CQuantumRoot *g_qsmc_root=NULL;
static int logs=0;

// --- the shipped shape, verbatim in structure -------------------------
static bool QSMC_RootCreate() {
  if(g_qsmc_root!=NULL) return g_qsmc_root->Ready();
  g_qsmc_root=new CQuantumRoot();
  if(g_qsmc_root==NULL) { logs++; return false; }
  bool ok=g_qsmc_root->Init();
  if(!ok) { logs++; delete g_qsmc_root; g_qsmc_root=NULL; }
  return ok;
}
static void QSMC_RootDestroy() {
  if(g_qsmc_root==NULL) return;
  delete g_qsmc_root; g_qsmc_root=NULL;
}
// the OLD shape, kept here so the test proves the difference is real
static bool QSMC_RootCreate_old() {
  if(g_qsmc_root!=NULL) return true;
  g_qsmc_root=new CQuantumRoot();
  return g_qsmc_root->Init();
}

int main() {
  // 1) a failed Init reports false, leaves no root, and logs
  CQuantumRoot::fail_next=true;
  assert(QSMC_RootCreate()==false);
  assert(g_qsmc_root==NULL);
  assert(logs==1);

  // 2) the next call gets a genuine second attempt - the failure is not sticky
  CQuantumRoot::fail_next=false;
  assert(QSMC_RootCreate()==true);
  assert(g_qsmc_root!=NULL && g_qsmc_root->Ready());
  int made_after_recovery=CQuantumRoot::made;
  assert(made_after_recovery==2);            // one failed, one good
  assert(QSMC_RootCreate()==true);           // idempotent once ready
  assert(CQuantumRoot::made==made_after_recovery);   // no second allocation
  QSMC_RootDestroy();
  assert(g_qsmc_root==NULL);

  // 3) the old shape is the bug: a second call reports success over a root
  //    that never became ready, and never retries
  CQuantumRoot::fail_next=true;
  assert(QSMC_RootCreate_old()==false);
  assert(g_qsmc_root!=NULL);                 // half-initialised root survives
  assert(g_qsmc_root->Ready()==false);
  CQuantumRoot::fail_next=false;
  assert(QSMC_RootCreate_old()==true);       // <-- the defect, reproduced
  assert(g_qsmc_root->Ready()==false);       // reporting success, not ready
  QSMC_RootDestroy();
  std::puts("AUD-07 lifecycle: fail-closed, retryable, idempotent");
  return 0;
}
''', "AUD-07 root lifecycle: a failed Init leaves no root, retries, and the old shape is reproduced as the defect")

root_header = (ROOT / "MQL5/Include/QSMC/QSMC_Root.mqh").read_text(encoding="utf-8")
check("int live_chart=m_render.OwnedAlive();" in root_header and
      "m_render.Created()-m_render.Deleted()" not in root_header and
      "owned remaining %d" in root_header,
      "leak verdict uses the post-cleanup owned-object census, not lifetime arithmetic")

renderer = (ROOT / "MQL5/Include/QSMC/QSMC_Renderer.mqh").read_text(encoding="utf-8")
renderer = renderer.replace("#include <QSMC/QSMC_Types.mqh>", "")
renderer = renderer.replace('#define QSMC_ARB_PFX "QSMC_ARB_"', 'static const string QSMC_ARB_PFX="QSMC_ARB_";')
compile_run(r'''
#include <string>
#include <set>
#include <cassert>
using string=std::string;
using datetime=long;
using color=int;
enum ENUM_OBJECT { OBJ_LABEL, OBJ_TEXT, OBJ_ARROW };
enum { OBJPROP_CORNER, OBJPROP_XDISTANCE, OBJPROP_YDISTANCE, OBJPROP_COLOR,
       OBJPROP_FONTSIZE, OBJPROP_FONT, OBJPROP_TEXT, OBJPROP_TOOLTIP,
       OBJPROP_SELECTABLE, OBJPROP_HIDDEN, OBJPROP_BACK, OBJPROP_ARROWCODE,
       OBJPROP_WIDTH, OBJPROP_ANCHOR };
enum { CORNER_RIGHT_UPPER, ANCHOR_TOP, ANCHOR_BOTTOM,
       clrLime, clrTomato, clrOrange, clrAqua, clrSilver, clrDarkGray,
       SIG_CONFIRMED=7, SIG_COUNTER_TREND=5, SIG_TACTICAL_INFO=4 };
struct SReactionFacts { int evidence_mask=0; };
struct SSignalCandidate {
  bool valid=true; int dir=1; datetime bar_time=1; double entry=100,sl=99,tp1=102,rr=2;
  int state=SIG_CONFIRMED; string reason="ok",reject_text="",extra=""; SReactionFacts reaction;
};
struct SGateCtx { double point=0.01; int digits=2; };
static std::set<string> objects;
static bool delete_fails=false;
int ObjectFind(long,const string &n){return objects.count(n)?0:-1;}
bool ObjectCreate(long,const string &n,ENUM_OBJECT,int,datetime,double){return objects.insert(n).second;}
bool ObjectDelete(long,const string &n){if(delete_fails)return false;return objects.erase(n)>0;}
bool ObjectMove(long,const string &,int,datetime,double){return true;}
bool ObjectSetInteger(long,const string &,int,long){return true;}
bool ObjectSetString(long,const string &,int,const string &){return true;}
int StringLen(const string &s){return (int)s.size();}
string StringSubstr(const string &s,int start,int len){return s.substr(start,len);}
string IntegerToString(int v){return std::to_string(v);}
string DoubleToString(double v,int){return std::to_string(v);}
string QSMC_StateName(int){return "CONFIRMED";}
string QSMC_EvidenceList(int){return "test";}
template<class T> T MathMax(T a,T b){return a>b?a:b;}
''' + renderer + r'''
int main(){
  CChartRenderer r;
  r.Init(0,0,true);
  SGateCtx ctx; SSignalCandidate c;
  r.DrawDirection(1,80,"UP");
  r.DrawPrimary(c,ctx,1.0);
  r.DrawSuppressed("later suppression",2,100.0,1.0,0.01,2);
  assert(r.Created()==5 && r.OwnedAlive()==5);
  // Reproduce the host prefix sweep removing the primary trio first.
  objects.erase("QSMC_ARB_PRIMARY_ARROW");
  objects.erase("QSMC_ARB_PRIMARY_L1");
  objects.erase("QSMC_ARB_PRIMARY_L2");
  r.ClearPrimary();
  assert(r.OwnedAlive()==2 && r.Deleted()==0);
  assert(r.Clear()==2 && r.OwnedAlive()==0);
  assert(r.Created()==5 && r.Deleted()==2); // lifetime counters need not match
  // A bystander sharing the prefix is not owned by these five stable slots.
  objects.insert("QSMC_ARB_BYSTANDER");
  r.DrawDirection(0,0,"WAIT");
  assert(r.Clear()==1 && objects.count("QSMC_ARB_BYSTANDER")==1);
  // Failed deletion must remain visible to the census.
  r.DrawSuppressed("still alive",3,100.0,1.0,0.01,2);
  delete_fails=true;
  assert(r.Clear()==0 && r.OwnedAlive()==1);
  delete_fails=false;
  assert(r.Clear()==1 && r.OwnedAlive()==0);
  // A disabled private reader never deletes the visual instance's objects.
  objects.insert("QSMC_ARB_MARKET_DIRECTION");
  CChartReaderProbe: ;
  CChartRenderer reader;
  reader.Init(0,0,false);
  assert(reader.Clear()==0 && reader.OwnedAlive()==0);
  assert(objects.count("QSMC_ARB_MARKET_DIRECTION")==1);
}
'''.replace("  CChartReaderProbe: ;\n", ""), "renderer cleanup, external deletion, failed deletion and reader isolation")

print("=" * 74)
print(f"runtime-diagnostics checks: failures={len(FAILURES)}")
print("This is a source/native-subset contract, not an MT5 runtime or latency measurement.")
raise SystemExit(NT.exit_code(FAILURES))
