#!/usr/bin/env python3
"""Host-execute Sniper update, invalidation, scoring and trade management.

Actual MQL bodies; terminal I/O and zone detection/trigger rules are stubs.
This tests data authorization, not the stubbed trading evidence or MT5 scheduling.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import native_toolchain as NT

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / 'nadir2.mq5').read_text()
assert (ROOT / 'nadir2.mq5').read_bytes() == (ROOT / 'MQL5/Indicators/nadir2.mq5').read_bytes()


def definition(name):
    matches = list(re.finditer(r'^\w+\s+' + re.escape(name) + r'\(', text, re.M))
    for match in matches:
        start = match.start()
        brace = text.index('{', start)
        if ';' in text[start:brace]:
            continue
        i, depth = brace + 1, 1
        while depth:
            depth += (text[i] == '{') - (text[i] == '}')
            i += 1
        return text[start:i]
    raise AssertionError(name)


def adapt(s):
    s = re.sub(r'(\w+) &(\w+)\[\]', r'std::vector<\1> &\2', s)
    # Local array declarations, including each declarator in a comma list.
    s = re.sub(r'\b(MqlRates|double)\s+([^;]+);', lambda m:
               ('std::vector<' + m[1] + '> ' + m[2].replace('[]', '') + ';')
               if '[]' in m[2] else m[0], s)
    return s


structs = text[text.index('struct SMTF_SniperLevel\n'):text.index('int                g_sniper_rates_retries')]
functions = '\n'.join(adapt(definition(n)) for n in (
    'ValidateTargetGeometry', 'MTF_SniperComputeTradeManagement', 'MTF_SniperScoreForDirection',
    'MTF_SniperInvalidateSnapshot', 'MTF_SniperDataStatus', 'MTF_SniperZone_Update'))
prelude = r'''
#include <vector>
#include <string>
#include <cmath>
#include <limits>
#include <cassert>
#include <iostream>
using string=std::string;using datetime=long long;using ENUM_TIMEFRAMES=int;
const int PERIOD_W1=0,PERIOD_D1=1,PERIOD_H4=2,PERIOD_H1=3,PERIOD_M30=4,PERIOD_M15=5,PERIOD_M5=6;
const int SNIPER_TF_COUNT=7,SNIPER_ACTIVE_PER_SIDE=3,SNIPER_BARS_LOAD=30;
const double EMPTY_VALUE=std::numeric_limits<double>::max(),_Point=.01;
const double SNIPER_SL_BUFFER_ATR=.3,SNIPER_SL_HARD_MAX_H1_ATR=2,SNIPER_BE_DISP_ATR=2,SNIPER_TRAIL_M15_ATR=.5;
const int ACCOUNT_EQUITY=0;
bool InpUseSniperZoneEngine=true,InpSniperUseTrailing=true;
double InpSniperMaxRiskPct=1,g_atr=2,g_adx=99;
string _Symbol="XAUUSD";int _Period=PERIOD_M15,g_rates_total=20;
struct MqlRates{datetime time=100;double open=100,high=101,low=99,close=100;};
template<class T> int ArraySize(const std::vector<T>& a){return int(a.size());}
template<class T> int ArrayResize(std::vector<T>& a,int n,int=0){a.resize(n);return n;}
template<class T> void ArrayCopy(std::vector<T>& a,const std::vector<T>& b){a=b;}
double MathMax(double a,double b){return std::max(a,b);}
double MathMin(double a,double b){return std::min(a,b);}
double MathAbs(double a){return std::abs(a);}
bool MathIsValidNumber(double a){return std::isfinite(a);}
double NormalizeDouble(double a,int){return a;}
double AccountInfoDouble(int){return 10000;}
double TheoreticalRiskMoney(double a,double b,double){return std::abs(a-b);}
string EnumToString(int a){return std::to_string(a);}
int log_count=0;
template<class... A> void Print(A...){log_count++;}
'''
globals_and_stubs = r'''
std::vector<SMTF_SniperLevel> g_sniper_raw_levels;
std::vector<SMTF_SniperCluster> g_sniper_raw_meta,g_sniper_merged;
std::vector<SMTF_SniperCluster> g_sniper_active_sup(3),g_sniper_active_res(3);
int g_sniper_active_sup_count=0,g_sniper_active_res_count=0;
SMTF_SniperCluster g_sniper_best{};
int g_sniper_macro_bias=0,g_sniper_w1_bias=0;bool g_sniper_w1_strong=false;
double g_sniper_h1_atr=0,g_sniper_h1_adx=0;
bool g_sniper_data_ready=false;string g_sniper_data_status="";
datetime g_sniper_last_bar_time=0,g_sniper_h1_bar_time=0,g_sniper_m15_bar_time=0;
std::vector<datetime> g_buf_t(20,1000);std::vector<double> g_buf_c(20,100);
int g_sniper_atr_retries[7]={},g_sniper_rsi_retries[7]={},g_sniper_adx_retries=0;
bool g_sniper_atr_warned[7]={},g_sniper_rsi_warned[7]={},g_sniper_adx_warned=false;
int h_sniper_atr[7]={0,1,2,3,4,5,6},h_sniper_rsi[7]={10,11,12,13,14,15,16},h_sniper_adx_h1=20;
int missing_tf=-1,missing_buffer=-1,partial_buffer=-1,stale_tf=-1,rollover_buffer=-1;
int deleted=0,drawn=0,collected=0,trigger_tf=-1;int macro_counts[3]={};
datetime stamps[7]={100,200,300,400,500,600,700};
datetime iTime(string,int tf,int shift){assert(shift==1);return stamps[tf];}
int MTF_SniperTFByIndex(int i){return i;}
void MTF_SniperClusterInit(SMTF_SniperCluster& c){c=SMTF_SniperCluster{};}
void MTF_SniperZone_DeleteObjects(){deleted++;}
void MTF_SniperZone_Draw(){drawn++;}
int MTF_SniperCopyRatesBounded(int,int tf,int count,std::vector<MqlRates>& r){
 if(tf==missing_tf)return 0;
 r.resize(count);for(int i=0;i<count;i++)r[i].time=stamps[tf]-(count-1-i)*10;
 if(tf==stale_tf)r.back().time--;
 return count;
}
int MTF_SniperCopyBufferBounded(int h,int n,std::vector<double>& b,int&,bool&,string){
 if(h==missing_buffer)return 0;
 if(h==partial_buffer)n--;
 b.assign(n,h==20?25:2);
 if(h==rollover_buffer){stamps[PERIOD_H1]++;rollover_buffer=-1;}
 return n;
}
void MTF_SniperCollectTF(int,int,const std::vector<MqlRates>&,int,const std::vector<double>&,int){collected++;}
void MTF_SniperComputeMacroBias(const std::vector<MqlRates>&,int w,const std::vector<MqlRates>&,int d,const std::vector<MqlRates>&,int h){macro_counts[0]=w;macro_counts[1]=d;macro_counts[2]=h;}
void MTF_SniperClusterAndMerge(const std::vector<SMTF_SniperCluster>&,int,double,std::vector<SMTF_SniperCluster>& a,int& n){
 SMTF_SniperCluster c{};c.level.direction=1;c.level.price_low=98;c.level.price_high=100;c.level.strength=.8;
 a={c};n=1;
}
bool MTF_SniperOverlapsNativeOBorFVG(double,double,int,double){return true;}
bool MTF_SniperValidateGates(SMTF_SniperCluster&,double,double,bool,int,int,bool,double,double,double){return true;}
void MTF_SniperEvaluateEntryTriggers(SMTF_SniperCluster& c,const std::vector<MqlRates>& r,int,double,const std::vector<MqlRates>&,int,const std::vector<double>&,int,datetime){
 trigger_tf=(r.back().time==stamps[PERIOD_M5]?PERIOD_M5:PERIOD_M15);c.entry_triggered=true;c.entry_price=100;
}
'''
tests = r'''
void refresh(){g_buf_t[18]++;MTF_SniperZone_Update();}
void unavailable(){assert(!g_sniper_data_ready&&g_sniper_h1_atr==0&&g_sniper_h1_adx==0);
 assert(g_sniper_merged.empty()&&g_sniper_active_sup_count==0&&g_sniper_last_bar_time==0);
 assert(MTF_SniperScoreForDirection(true,100,2)==0);}
int main(){
 MTF_SniperZone_Update();assert(g_sniper_data_ready&&g_sniper_h1_atr==2&&g_sniper_h1_adx==25);
 assert(g_sniper_active_sup_count==1&&MTF_SniperScoreForDirection(true,100,2)>0);
 int old_draw=drawn;MTF_SniperZone_Update();assert(drawn==old_draw); // complete same-bar cache
 for(int handle: {3,5,20}){
  missing_buffer=handle;refresh();unavailable();assert(deleted>0);
  int logs=log_count;MTF_SniperZone_Update();unavailable();assert(log_count==logs);
  missing_buffer=-1;MTF_SniperZone_Update();assert(g_sniper_data_ready); // same chart bar recovers
 }
 for(int tf: {PERIOD_H1,PERIOD_M15}){
  missing_tf=tf;refresh();unavailable();missing_tf=-1;MTF_SniperZone_Update();assert(g_sniper_data_ready);
  stale_tf=tf;refresh();unavailable();stale_tf=-1;MTF_SniperZone_Update();assert(g_sniper_data_ready);
 }
 partial_buffer=3;refresh();unavailable();partial_buffer=-1;MTF_SniperZone_Update();assert(g_sniper_data_ready);
 rollover_buffer=20;refresh();unavailable();MTF_SniperZone_Update();assert(g_sniper_data_ready);
 // Freeze a COMPLETE closed-bar decision: later child-TF evidence cannot
 // rewrite that bar. The next chart bar must refresh, not reuse old H1 data.
 datetime frozen=g_sniper_h1_bar_time;
 missing_buffer=20;stamps[PERIOD_H1]++;MTF_SniperZone_Update();
 assert(g_sniper_data_ready&&g_sniper_h1_bar_time==frozen);
 refresh();unavailable();
 missing_buffer=-1;MTF_SniperZone_Update();assert(g_sniper_data_ready);
 g_atr=0;refresh();unavailable();g_atr=2;MTF_SniperZone_Update();assert(g_sniper_data_ready);
 _Period=PERIOD_M5;missing_tf=PERIOD_M5;refresh();unavailable();
 missing_tf=-1;MTF_SniperZone_Update();assert(g_sniper_data_ready&&trigger_tf==PERIOD_M5);
 // Optional zone sources are not newly made hard requirements in this patch.
 _Period=PERIOD_M15;missing_tf=PERIOD_M30;refresh();assert(g_sniper_data_ready);missing_tf=-1;
 // Losing optional W1 zone ATR must NOT hide measured W1 macro opposition.
 missing_buffer=PERIOD_W1;refresh();assert(g_sniper_data_ready&&macro_counts[0]==SNIPER_BARS_LOAD);
 missing_buffer=-1;
 g_rates_total=1;MTF_SniperZone_Update();unavailable();g_rates_total=20;
 MTF_SniperZone_Update();assert(g_sniper_data_ready);
 InpUseSniperZoneEngine=false;MTF_SniperZone_Update();unavailable();InpUseSniperZoneEngine=true;
 // Actual trade-management body: no chart ATR substitution for either risk TF.
 std::vector<MqlRates> rates(8);g_sniper_merged.clear();
 for(int direction: {1,-1}){
  SMTF_SniperCluster c{};c.level.direction=direction;c.level.price_low=98;c.level.price_high=102;c.entry_price=100;
  c.entry_triggered=true;MTF_SniperComputeTradeManagement(c,2,5,rates,8,2);
  assert(c.sl_hard_max_ok&&c.entry_triggered&&c.rec_lot_size>0);
  double stop=c.sl_price;
  assert(direction==1?stop<100:stop>100);
  assert(direction==1?c.tp1_price>100:c.tp1_price<100);
  for(double bad: {0.0,-1.0,EMPTY_VALUE,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}){
   for(int field=0;field<3;field++){
    c.entry_triggered=true;MTF_SniperComputeTradeManagement(c,field==0?bad:2,field==1?bad:5,rates,8,field==2?bad:2);
    assert(!c.entry_triggered&&!c.sl_hard_max_ok&&c.entry_grade=="DATA_NOT_READY");
    assert(c.sl_price==0&&c.tp1_price==0&&c.rec_lot_size==0&&!c.be_active&&!c.trail_active);
   }
  }
  c.entry_triggered=true;MTF_SniperComputeTradeManagement(c,2,1,rates,8,2);
  assert(!c.entry_triggered&&c.entry_grade=="SKIP_SL_MAX"); // real wide stop, not moved
  assert(c.sl_price==stop);
  MTF_SniperComputeTradeManagement(c,2,5,rates,4,2);assert(c.entry_grade=="DATA_NOT_READY");
  // Opposing structural TP1 beyond 2R must not publish a crossed TP ladder.
  SMTF_SniperCluster opposing{};opposing.level.direction=-direction;
  opposing.level.price_low=(direction==1?110:89);opposing.level.price_high=(direction==1?111:90);opposing.tf_mask=0;
  g_sniper_merged={opposing};c.entry_triggered=true;
  MTF_SniperComputeTradeManagement(c,2,5,rates,8,2);
  assert(!c.entry_triggered&&c.entry_grade=="SKIP_TARGET_GEOMETRY");
  assert(c.tp1_price==0&&c.tp2_price==0&&c.tp3_price==0&&c.rec_lot_size==0);
  assert(c.sl_price==stop); // structural stop unchanged
  g_sniper_merged.clear();
  c.entry_price=(direction==1?90:110);c.entry_triggered=true;
  MTF_SniperComputeTradeManagement(c,2,20,rates,8,2);
  assert(!c.entry_triggered&&c.entry_grade=="SKIP_STOP_GEOMETRY");
 }
 std::cout<<"PASS real Sniper bodies: data loss, stale suffix, partial ATR, rollover, recovery, cache, score/drawing retirement, M5 execution, BUY/SELL volatility guards and stop/target rejection\n";
}
'''
cxx = NT.compiler(sanitizers=True)
if cxx is None:
    raise SystemExit(NT.skip('EL Sniper readiness bodies', sanitizers=True))
with tempfile.TemporaryDirectory(prefix='el-sniper-') as d:
    cpp, exe = Path(d) / 'test.cpp', Path(d) / 'test'
    cpp.write_text(prelude + structs + globals_and_stubs + functions + tests)
    subprocess.run([cxx, '-std=c++17', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('NOT MQL5 compilation, Strategy Tester or live MT5. Zone detection and entry evidence are stubbed.')
