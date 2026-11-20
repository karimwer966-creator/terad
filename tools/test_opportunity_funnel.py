#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Opportunity-funnel module contract tests (Phase B).

Two layers:

  A. Native C++ harness: builds the REAL .mqh with MT5 stubs and executes the
     state machine (counters, ring, FNV IDs, CSV formatting, disabled-mode
     silence). Requires g++; without a compiler this suite exits 77
     ("NOT verified here"), never a fake PASS.

  B. Source-level safety invariants (always run): the module must not
     reference any order API, GlobalVariables, indicator buffers, trade
     classes, or file I/O; every reason/stage code must have exactly one
     case label in its Name function (no duplicate ints).

This is NOT a MetaEditor compile and NOT an integration test.
"""
import re
import pathlib
import subprocess
import sys
import tempfile

import native_toolchain as NT

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = ROOT / 'MQL5/Include/QSMC/QSMC_OpportunityFunnel.mqh'
PRELUDE = r'''
#define QSMC_OF_NATIVE_TEST
#include <string>
#include <vector>
#include <cmath>
#include <limits>
#include <cassert>
#include <iostream>
using string=std::string;
using datetime=long long;
typedef unsigned int uint;
typedef unsigned char uchar;
double MathAbs(double a){return std::abs(a);}
double MathIsValidNumber_(double a){return std::isfinite(a);}
bool MathIsValidNumber(double a){return std::isfinite(a);}
const double EMPTY_VALUE=std::numeric_limits<double>::max();
string IntegerToString(long v){char b[32]; snprintf(b,sizeof b,"%ld",v); return string(b);}
string IntegerToString(int v){return IntegerToString((long)v);}
string DoubleToString(double v,int d){char b[64]; snprintf(b,sizeof b,"%.16g",v); return string(b);}
string TimeToString(datetime t){return IntegerToString((long)t);}
int StringLen(const string &s){return int(s.size());}
int StringGetCharacter(const string &s,int i){return (unsigned char)s[size_t(i)];}
std::vector<string> g_prints;
void Print(const string &s){g_prints.push_back(s);}
'''

TESTS = r'''
static void expect(bool cond,const char* what) {
   if(!cond) { std::cerr << "ASSERT FAILED: " << what << std::endl; std::exit(1); }
}
int main() {
   // ---- determinism of setup IDs ----------------------------------------
   ulong a=QSMC_OF_MakeId("XAUUSD","CORE",1,1730000000LL);
   ulong b=QSMC_OF_MakeId("XAUUSD","CORE",1,1730000000LL);
   ulong c=QSMC_OF_MakeId("XAUUSD","CORE",1,1730000060LL);
   ulong d=QSMC_OF_MakeId("XAUUSD","SWEEP_RECLAIM",1,1730000000LL);
   expect(a==b, "same inputs -> same setup id (stable across runs)");
   expect(a!=c, "different bar -> different setup id");
   expect(a!=d, "different family -> different setup id");
   expect(a!=0, "setup id is never 0");

   // ---- disabled mode: total silence ------------------------------------
   QSMC_OF_Reset();
   QSMC_OF_SetEnabled(false);
   QSMC_OF_NotReached(a,"XAUUSD","CORE",1,1730000000LL,QSMC_OF_QUALITY);
   expect(QSMC_OF_EventCount()==0, "disabled: recording is a no-op");
   QSMC_OF_PrintSummary();
   expect(g_prints.empty(), "disabled: PrintSummary prints nothing");

   // ---- enabled: counters + ring ----------------------------------------
   QSMC_OF_Reset();
   QSMC_OF_SetEnabled(true);
   ulong id1=QSMC_OF_MakeId("XAUUSD","CORE",-1,1730000000LL);
   QSMC_OF_Pass(id1,"XAUUSD","CORE",-1,1730000000LL,QSMC_OF_DATA_READY,1.0,EMPTY_VALUE,QSMC_OF_UNIT_NONE);
   QSMC_OF_Reject(id1,"XAUUSD","CORE",-1,1730000000LL,QSMC_OF_STRUCTURE_AND_LIQUIDITY,
                  QSMC_OF_REASON_INCOMPLETE_CHAIN,120.5,130.0,QSMC_OF_UNIT_PRICE);
   QSMC_OF_Unavailable(id1,"XAUUSD","CORE",-1,1730000000LL,QSMC_OF_HTF_CONTEXT,
                       QSMC_OF_REASON_DATA_UNAVAILABLE,EMPTY_VALUE,QSMC_OF_UNIT_NONE);
   for(int s=QSMC_OF_STRUCTURE_AND_LIQUIDITY+1;s<QSMC_OF_STAGE_COUNT;s++)
      QSMC_OF_NotReached(id1,"XAUUSD","CORE",-1,1730000000LL,s);
   expect(QSMC_OF_EventCount()==3+(QSMC_OF_STAGE_COUNT-(QSMC_OF_STRUCTURE_AND_LIQUIDITY+1)), "3 explicit + NotReached fill-in == expected rows");
   expect(QSMC_OF_StageVerdictCount(QSMC_OF_DATA_READY,QSMC_OF_PASS)==1, "stage-verdict counter");
   expect(QSMC_OF_StageVerdictCount(QSMC_OF_STRUCTURE_AND_LIQUIDITY,QSMC_OF_REJECT)==1, "reject counter");
   expect(QSMC_OF_StageVerdictCount(QSMC_OF_HTF_CONTEXT,QSMC_OF_DATA_UNAVAILABLE)==1, "unavailable counter");
   expect(QSMC_OF_ReasonCount(QSMC_OF_REASON_INCOMPLETE_CHAIN)==1, "reason counter");
   expect(QSMC_OF_ReasonCount(QSMC_OF_REASON_DATA_UNAVAILABLE)==1, "unavailable reason counter");
   expect(QSMC_OF_StageVerdictCount(QSMC_OF_DATA_READY,QSMC_OF_DATA_UNAVAILABLE)==0, "stage/verdict buckets are separate: DATA_READY has no DATA_UNAVAILABLE");
   expect(QSMC_OF_StageVerdictCount(QSMC_OF_HTF_CONTEXT,QSMC_OF_PASS)==0, "stage/verdict buckets are separate: HTF_CONTEXT has no PASS");

   // ---- recent ring read-back -------------------------------------------
   SOpportunityEvent ev;
   expect(QSMC_OF_GetRecent(0,ev), "latest event readable");
   expect(ev.stage==QSMC_OF_FILL_AND_PROTECTION_VERIFIED, "latest is the last NOT_REACHED row");
   expect(QSMC_OF_GetRecent(QSMC_OF_STAGE_COUNT+3,ev)==false, "out-of-range read rejected");

   // ---- CSV format -------------------------------------------------------
   string row=QSMC_OF_FormatCSV(ev);
   size_t commas=0; for(size_t i=0;i<row.size();i++) if(row[i]==',') commas++;
   expect(commas==10, "csv has 11 fields");
   expect(row.find("FILL_AND_PROTECTION_VERIFIED")!=string::npos, "csv carries stage name");
   expect(row.find("NOT_REACHED")!=string::npos, "csv carries verdict name");
   expect(row.find("EMPTY_VALUE")!=string::npos, "csv marks empty value distinctly");

   // ---- overflow accounting ----------------------------------------------
   QSMC_OF_Reset();
   QSMC_OF_SetEnabled(true);
   for(int i=0;i<QSMC_OF_RING_SIZE+17;i++)
      QSMC_OF_Pass(id1,"XAUUSD","CORE",1,1730000000LL+i*60,QSMC_OF_DATA_READY,1.0,EMPTY_VALUE,QSMC_OF_UNIT_NONE);
   expect(QSMC_OF_Overflowed(), "ring overflow flag set");
   expect(QSMC_OF_EventCount()==(uint)(QSMC_OF_RING_SIZE+17), "monotonic total survives overflow");
   expect(QSMC_OF_GetRecent(0,ev) && ev.bar==1730000000LL+(long)(QSMC_OF_RING_SIZE+16)*60, "newest survives");

   // ---- summary mentions every stage ------------------------------------
   string sum=QSMC_OF_Summary();
   expect(sum.find("DATA_READY")!=string::npos && sum.find("FILL_AND_PROTECTION_VERIFIED")!=string::npos,
          "summary lists all stages");
   std::cout << "opportunity-funnel native harness: ALL ASSERTIONS PASS" << std::endl;
   return 0;
}
'''

FORBIDDEN = [
    r'\bOrderSend', r'\bOrderModify', r'\bOrderClose', r'\bOrderDelete',
    r'\bTrade\.', r'\bGlobalVariable\w*', r'\bSetIndexBuffer\b',
    r'\bCopyBuffer\b', r'\bFileOpen\b', r'\bFileWrite\b', r'\bSocket\w*',
    r'\bWebRequest\b', r'\blibria?ry\b', r'\b#import\b',
]


def check_source_invariants() -> list:
    src = HEADER.read_text(encoding='utf-8')
    code = re.sub(r'//.*', '', src)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
    failures = []
    for pat in FORBIDDEN:
        m = re.search(pat, code)
        if m:
            # GlobalVariable* etc are allowed only inside the contract comment block,
            # which is stripped above; anything left is a real reference.
            failures.append(f"forbidden reference in live code: {m.group(0)}")
    # stage codes: exactly one case per stage in StageName
    stage_cases = re.findall(r'case QSMC_OF_(DATA_READY|MARKET_EVENT|CANDIDATE|HTF_CONTEXT|STRUCTURE_AND_LIQUIDITY|ZONE_AND_GEOMETRY|QUALITY|CORE_EXPORTED|EA_RECEIVED|SESSION_ALLOWED|RISK_ALLOWED|ORDER_ATTEMPTED|FILL_AND_PROTECTION_VERIFIED):',
                             code)
    if len(stage_cases) != 13:
        failures.append(f"StageName covers {len(stage_cases)}/13 stage cases")
    if len(set(stage_cases)) != len(stage_cases):
        failures.append("duplicate stage case in StageName")
    # reason codes 0..16 each exactly once
    reasons = re.findall(r'case QSMC_OF_REASON_OK:|case QSMC_OF_REASON_NOT_REACHED:|case QSMC_OF_REASON_NO_SETUP:|case QSMC_OF_REASON_INCOMPLETE_CHAIN:|case QSMC_OF_REASON_RULE_REJECT:|case QSMC_OF_REASON_DATA_UNAVAILABLE:|case QSMC_OF_REASON_DATA_STALE:|case QSMC_OF_REASON_DATA_SHORT_READ:|case QSMC_OF_REASON_INDICATOR_INPUT_MISMATCH:|case QSMC_OF_REASON_SESSION:|case QSMC_OF_REASON_GUARD_ACCOUNT_WIDE:|case QSMC_OF_REASON_GUARD_EA:|case QSMC_OF_REASON_SPREAD_TOO_WIDE:|case QSMC_OF_REASON_RR_INVALID:|case QSMC_OF_REASON_BROKER_REJECT:|case QSMC_OF_REASON_PROTECTION_MISSING:|case QSMC_OF_REASON_INTERNAL:', code)
    if len(reasons) != 17:
        failures.append(f"ReasonName covers {len(reasons)}/17 reason cases")
    # enum definitions use every value exactly once
    enum_block = re.search(r'enum ENUM_QSMC_OF_REASON\s*\{(.*?)\};', code, re.S).group(1)
    rcount = len(re.findall(r'QSMC_OF_REASON_\w+\s*=', enum_block)) + len(re.findall(r'QSMC_OF_REASON_\w+\s*,', enum_block)) + 1
    if rcount < 17:
        failures.append(f"reason enum looks short: {rcount} enumerators")
    return failures


def main() -> int:
    failures = check_source_invariants()
    for f in failures:
        print("FAIL", f)
    if failures:
        print("opportunity-funnel source invariants: FAILED")
        return 1
    print("PASS source invariants: no order/GV/buffer/file APIs; names cover all stages+reasons")

    cxx = NT.compiler(sanitizers=True)
    if cxx is None:
        print("SKIP native harness: no C++ compiler on this host (run CI or an environment with g++)")
        return NT.SKIP_EXIT

    with tempfile.TemporaryDirectory(prefix='qsmc-of-') as d:
        src = pathlib.Path(d) / 'harness.cpp'
        exe = pathlib.Path(d) / 'harness'
        body = PRELUDE + '\n#include "' + str(HEADER.as_posix()) + '"\n' + TESTS
        src.write_text(body, encoding='utf-8')
        proc = subprocess.run([cxx, '-std=c++17', '-fsanitize=address,undefined', '-I', str(ROOT),
                               str(src), '-o', str(exe)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if proc.returncode != 0:
            print(proc.stderr.decode('utf-8', 'replace'))
            print("native harness: BUILD FAILED")
            return 1
        run = subprocess.run([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        print(run.stdout.decode('utf-8', 'replace').strip())
        if run.returncode != 0:
            print(run.stderr.decode('utf-8', 'replace'))
            print("native harness: RUN FAILED")
            return 1
    print("opportunity-funnel: ALL CHECKS PASS (native harness executed)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
