"""Execute the actual .mqh state machine as C++ with MT5 I/O stubs.
Not an MQL compiler, integration test, terminal replay or profitability test.
Requires g++; all generated artifacts live in a temporary directory.
"""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = ROOT / 'MQL5/Include/QSMC/QSMC_LiquidityValue.mqh'
PRELUDE = r'''
#define QSMC_LV_NATIVE_TEST
#include <string>
#include <vector>
#include <cmath>
#include <limits>
#include <cassert>
#include <iostream>
using string=std::string;
using datetime=long long;
template<class T> int ArraySize(const std::vector<T>& v) { return int(v.size()); }
double MathMax(double a,double b){return std::max(a,b);}
double MathMin(double a,double b){return std::min(a,b);}
double MathAbs(double a){return std::abs(a);}
bool MathIsValidNumber(double a){return std::isfinite(a);}
const double EMPTY_VALUE=std::numeric_limits<double>::max();
const int OBJ_LABEL=0, OBJPROP_CORNER=1,CORNER_LEFT_LOWER=2,OBJPROP_ANCHOR=3,
ANCHOR_LEFT_LOWER=4,OBJPROP_XDISTANCE=5,OBJPROP_YDISTANCE=6,OBJPROP_FONTSIZE=7,
OBJPROP_COLOR=8,clrSilver=9,OBJPROP_SELECTABLE=10,OBJPROP_TEXT=11,OBJPROP_TOOLTIP=12;
int deletes=0,creates=0,reads=0;
bool object_exists=false;
int ObjectFind(int,const string&){return object_exists?0:-1;}
template<class... T> bool ObjectCreate(T...){creates++;return object_exists=true;}
template<class... T> bool ObjectDelete(T...){deletes++;object_exists=false;return true;}
template<class... T> void ObjectSetInteger(T...){}
template<class... T> void ObjectSetString(T...){}
template<class... T> void Print(T...){}
string TimeToString(datetime t){return std::to_string(t);}
string DoubleToString(double x,int){return std::to_string(x);}
string PFX="TEST_";
int _Digits=2,InpATRPeriod=2,g_rates_total=100;
bool InpEnableLiquidityValue=true,InpUseMasterVolumeProfile=true,InpLVJournal=false,InpArbVerboseLog=false;
double InpTopDownMinRR=1.5,atr_value=1;
std::vector<double> g_buf_o(100,100),g_buf_h(100,101),g_buf_l(100,99),g_buf_c(100,100);
std::vector<datetime> g_buf_t(100);
struct Profile {bool valid=true;double val=100,poc=110,vah=120;};
std::vector<Profile> g_mvp(1);
int g_mvp_count=1,g_mvp_active=0;
datetime g_mvp_built_time=0;
struct Pool {int availability_bar=0,parent_pool_availability_bar=0;
string id,type,parent_pool_id;double parent_level=0;};
std::vector<Pool> g_liquidity;
double PMI_ATRAt(int,int){reads++;return atr_value;}
'''
TESTS = r'''
void bar(int b,double o=100,double h=101,double l=99,double c=100,bool reset=false){
 g_buf_o[b]=o;g_buf_h[b]=h;g_buf_l[b]=l;g_buf_c[b]=c;
 g_mvp_built_time=g_buf_t[b]; LV_Update(b,reset);
}
void fresh(){
 InpEnableLiquidityValue=true;InpUseMasterVolumeProfile=true;InpTopDownMinRR=1.5;
 g_mvp_active=0;g_mvp_count=1;g_mvp.assign(1,Profile());atr_value=1;
 g_rates_total=100;g_liquidity.clear();
 for(int i=0;i<100;i++) {g_buf_t[i]=1000+i*60;g_buf_o[i]=100;g_buf_h[i]=101;g_buf_l[i]=99;g_buf_c[i]=100;}
 bar(2,100,101,99,100,true);assert(g_lv_phase==0 && g_lv_profile);
}
void sweep(bool buy=true){
 Pool p;p.id="P";p.type=buy?"EQL":"EQH";p.availability_bar=1;
 Pool s;s.id="S";s.type=buy?"SSL TAKEN":"BSL TAKEN";s.parent_pool_id="P";
 s.parent_pool_availability_bar=1;s.availability_bar=3;s.parent_level=buy?100:120;
 g_liquidity={p,s};
 if(buy)bar(3,100,101,99,100.5);else bar(3,120,121,119,119.5);
}
int main(){
 fresh();sweep();assert(g_lv_phase==1 && g_lv_dir==1);
 double target=g_lv_target;g_mvp[0].poc=115;
 bar(4,100.5,102,100.4,101.5);assert(g_lv_phase==2 && g_lv_target==target);
 bar(5,101.2,102,101,101.5);assert(g_lv_phase==3 && g_lv_status.find("BUY WATCH")!=string::npos);
 int age=g_lv_age,created=creates;
 bar(5,101.2,102,101,101.5);assert(g_lv_age==age && creates==created);
 bar(6,101.2,102,101,101.5);assert(g_lv_phase==0);
 fresh();sweep(false);assert(g_lv_phase==1 && g_lv_dir==-1);
 bar(4,119.5,119.6,118,118.5);assert(g_lv_phase==2);
 bar(5,118.8,119,118,118.5);assert(g_lv_phase==3 && g_lv_status.find("SELL WATCH")!=string::npos);
 fresh();sweep();bar(4,100,101,98,100);assert(g_lv_status=="INVALIDATED / STOP");
 fresh();sweep();bar(4,100,101,99,99.5);assert(g_lv_status=="INVALIDATED / VALUE LOST");
 fresh();sweep();bar(4,100,111,100,101);assert(g_lv_status=="TARGET REACHED / NO CHASE");
 fresh();sweep();for(int i=4;i<=16;i++)bar(i,100.5,101,100,100.5);
 assert(g_lv_status=="EXPIRED");
 fresh();sweep();bar(5,100.5,102,100,101.5);assert(g_lv_phase==0 && g_lv_profile);
 fresh();sweep();bar(4,100,101,99,100,true);assert(g_lv_phase==0);
 fresh();sweep();g_mvp[0].poc=EMPTY_VALUE;bar(4);assert(g_lv_phase==0 && !g_lv_profile);
 fresh();sweep();g_mvp[0].val=std::nan("");bar(4);assert(g_lv_phase==0 && !g_lv_profile);
 fresh();sweep();g_mvp_active=100;bar(4);assert(g_lv_phase==0 && !g_lv_profile);
 fresh();sweep();g_mvp.clear();bar(4);assert(g_lv_phase==0 && !g_lv_profile);
 fresh();sweep();g_buf_c[2]=EMPTY_VALUE;bar(4);assert(g_lv_phase==0 && !g_lv_profile);
 fresh();sweep();bar(4,105,102,100,101);assert(g_lv_phase==0 && !g_lv_profile);
 fresh();sweep();atr_value=std::numeric_limits<double>::infinity();bar(4);assert(!g_lv_profile && g_lv_phase==0);
 fresh();sweep();g_mvp_built_time=0;LV_Update(4,false);assert(!g_lv_profile && g_lv_phase==0);
 fresh();sweep();InpEnableLiquidityValue=false;int r=reads;
 LV_Update(4,false);int d=deletes;LV_Update(4,false);assert(deletes==d && reads==r && g_lv_phase==0);
 fresh();sweep();InpUseMasterVolumeProfile=false;bar(4);assert(!g_lv_profile && g_lv_phase==0);
 fresh();sweep();InpTopDownMinRR=100;bar(4,100.5,102,100.4,101.5);
 bar(5,101.2,102,101,101.5);assert(g_lv_status=="REJECT / INSUFFICIENT ROOM TO POC");
 fresh();g_lv_last=g_buf_t[2];g_rates_total=4;LV_Update(3,false);assert(!g_lv_profile);
 fresh();g_liquidity.clear();bar(3);assert(g_lv_phase==0);
 fresh();sweep();g_lv_phase=0;g_liquidity[0].type="EQH";
 g_lv_last=g_buf_t[2];bar(3,100,101,99,100.5);assert(g_lv_phase==0);
 std::cout<<"PASS: actual header state-machine runtime scenarios (stubbed MT5 I/O)\n";
}
'''
with tempfile.TemporaryDirectory(prefix='qsmc-lv-') as d:
    source = pathlib.Path(d) / 'runtime.cpp'
    binary = pathlib.Path(d) / 'runtime'
    source.write_text(PRELUDE + '\n#include "' + str(HEADER) + '"\n' + TESTS)
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
