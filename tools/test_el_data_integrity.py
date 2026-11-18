#!/usr/bin/env python3
"""Execute shipped copy-gate bodies with deterministic terminal stubs, not MT5."""
from pathlib import Path
import subprocess
import tempfile
import native_toolchain as NT

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / 'nadir2.mq5').read_text()
assert (ROOT / 'nadir2.mq5').read_bytes() == (ROOT / 'MQL5/Indicators/nadir2.mq5').read_bytes()


def function(name):
    start = text.index(name + '(')
    # Skip declarations and find the actual definition.
    while ';' in text[start:text.index('{', start)]:
        start = text.index(name + '(', start + len(name))
    end = text.index('{', start)
    depth = 1
    i = end + 1
    while depth:
        depth += (text[i] == '{') - (text[i] == '}')
        i += 1
    return text[start:i]


rates = 'int ' + function('MTF_SniperCopyRatesBounded')
buffer = 'int ' + function('MTF_SniperCopyBufferBounded')
geometry = ('double ' + function('DirectionalRR') + '\n' +
            'bool ' + function('ValidateTargetGeometry'))
for name, typ in [('rates_out', 'MqlRates'), ('buf_out', 'double')]:
    rates = rates.replace(f'{typ} &{name}[]', f'std::vector<{typ}> &{name}')
    buffer = buffer.replace(f'{typ} &{name}[]', f'std::vector<{typ}> &{name}')
start = text.index('   bool indicator_full_copy=')
end = text.index('   // CopyBuffer(,0,0,need,ta)', start)
main_gate = text[start:end].replace('double ta[],td[],tr[];', 'std::vector<double> ta,td,tr;')
prelude = r'''
#include <vector>
#include <string>
#include <limits>
#include <cmath>
#include <cassert>
#include <iostream>
using string=std::string; using ENUM_TIMEFRAMES=int;
struct MqlRates {long time=1; double open=100,high=101,low=99,close=100;};
const int INVALID_HANDLE=-1, SNIPER_TF_COUNT=7, QSMC_IND_COPY_MAX_RETRY=3;
const double EMPTY_VALUE=std::numeric_limits<double>::max();
const double _Point=0.01;
int g_instance_role=0; string _Symbol="XAUUSD";
int g_sniper_rates_retries[7]={}; bool g_sniper_rates_warned[7]={};
int returned=-2, calculated=100, bad=-1, bad_handle=-1;
double bad_value=EMPTY_VALUE;
int g_ind_copy_retries=0, g_last_rates_total=0;
bool g_ind_copy_warned=false;
std::vector<double> g_atr_buf(20),g_adx_buf(20),g_rsi_buf(20);
int h_atr=1,h_adx=2,h_rsi=3;
template<class T> int ArraySize(const std::vector<T>& a){return int(a.size());}
template<class T> int ArrayResize(std::vector<T>& a,int n){a.resize(n);return n;}
template<class T> void ArraySetAsSeries(std::vector<T>&,bool){}
template<class... A> void Print(A... ){}
string EnumToString(int i){return std::to_string(i);}
string IntegerToString(int i){return std::to_string(i);}
void ResetLastError(){} int GetLastError(){return 0;}
int BarsCalculated(int){return calculated;}
double MathMin(double a,double b){return std::fmin(a,b);}
double MathMax(double a,double b){return std::fmax(a,b);}
bool MathIsValidNumber(double x){return std::isfinite(x);}
string QSMC_CopyStatus(int,int,int,int){return "stub";}
int CopyBuffer(int h,int,int shift,int n,std::vector<double>& a){
 assert(shift==0||shift==1);
 int r=(returned==-2||h!=bad_handle ? n:returned);
 a.assign(r>0?r:0,1.0); if(bad>=0&&bad<int(a.size()))a[bad]=bad_value;
 return r;
}
int CopyRates(string,int,int shift,int n,std::vector<MqlRates>& a){
 assert(shift==1); int r=(returned==-2?n:returned);a.resize(r>0?r:0);
 for(int i=0;i<int(a.size());i++)a[i].time=100+i;
 return r;
}
'''
# Return value 999 means execution passed the real mandatory gate; 7 means retry.
main_gate = 'int gate(){int prev_calculated=7,rates_total=20;bool needResize=false,full_detection=false;\n' + main_gate + '\nreturn 999;}'
tests = r'''
int main(){
 assert(ValidateTargetGeometry(true,3952.86,3942.86,3972.86,3982.86,3992.86));
 assert(ValidateTargetGeometry(false,3952.86,3962.86,3932.86,3922.86,3912.86));
 assert(std::abs(DirectionalRR(true,3952.86,3942.86,3972.86)-2.0)<1e-9);
 assert(std::abs(DirectionalRR(false,3952.86,3962.86,3932.86)-2.0)<1e-9);
 assert(!ValidateTargetGeometry(true,100,101,102,103,104));
 assert(!ValidateTargetGeometry(false,100,99,98,97,96));
 assert(!ValidateTargetGeometry(true,100,99,98,103,104));
 assert(!ValidateTargetGeometry(false,100,101,102,97,96));
 assert(DirectionalRR(true,100,100,102)<0); // zero risk
 assert(DirectionalRR(false,100,101,100)<0); // zero reward
 assert(DirectionalRR(true,100,99,98)<0); // wrong-side reward
 // Supplied wide SELL is directional geometry, not evidence of valid structure.
 assert(std::abs(DirectionalRR(false,3952.86,4170.84,3516.91)-1.9999541242)<1e-8);
 std::cout<<"PASS shipped geometry: mirrored BUY/SELL, wrong stops/targets, zero risk/reward, wide SELL RR\n";
 std::vector<double> b; std::vector<MqlRates> r; int retry=0;bool warned=false;
 assert(MTF_SniperCopyBufferBounded(-1,4,b,retry,warned,"ATR_H1")==0);
 for(int calc: {-1,0,4}){calculated=calc;assert(MTF_SniperCopyBufferBounded(1,4,b,retry,warned,"ATR_H1")==0);}
 calculated=100;bad_handle=1;
 for(int result: {-1,0,2}){
  returned=result;
  for(int k=0;k<10;k++)assert(MTF_SniperCopyBufferBounded(1,4,b,retry,warned,"ATR_H1")==0);
 }
 returned=-2;assert(MTF_SniperCopyBufferBounded(1,4,b,retry,warned,"ATR_H1")==4);
 assert(retry==0&&!warned);
 for(double v: {EMPTY_VALUE,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),-1.0}){
  bad=2;bad_value=v;assert(MTF_SniperCopyBufferBounded(1,4,b,retry,warned,"ATR_H1")==0);assert(b.empty());
 }
 bad=-1;assert(MTF_SniperCopyBufferBounded(1,4,b,retry,warned,"ATR_H1")==4);
 assert(!warned);
 for(int tf=0;tf<7;tf++){
  returned=2;for(int k=0;k<10;k++)assert(MTF_SniperCopyRatesBounded(tf,tf,4,r)==0);
  returned=-2;assert(MTF_SniperCopyRatesBounded(tf,tf,4,r)==4);
  assert(g_sniper_rates_retries[tf]==0&&!g_sniper_rates_warned[tf]);
 }
 returned=2;assert(MTF_SniperCopyRatesBounded(-1,1,4,r)==0&&r.empty());
 for(int h: {h_atr,h_adx,h_rsi})for(int result: {-1,0,2}){
  bad_handle=h;returned=result;
  for(int k=0;k<10;k++)assert(gate()==7); // including AFTER retry exhaustion
  returned=-2;assert(gate()==999);assert(g_ind_copy_retries==0&&!g_ind_copy_warned);
 }
 std::cout<<"PASS actual copy gates: exhaustion, invalid handle, calculated bars, partial rates/buffers, invalid numbers, seven TF slots, recovery\n";
}
'''
cxx = NT.compiler(sanitizers=True)
if cxx is None:
    raise SystemExit(NT.skip('EL copy gate bodies', sanitizers=True))
with tempfile.TemporaryDirectory(prefix='el-data-') as d:
    cpp = Path(d) / 'test.cpp'
    exe = Path(d) / 'test'
    cpp.write_text(prelude + rates + buffer + geometry + main_gate + tests)
    subprocess.run([cxx, '-std=c++17', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('NOT an MQL5 compilation, Strategy Tester run, or live-terminal test.')
