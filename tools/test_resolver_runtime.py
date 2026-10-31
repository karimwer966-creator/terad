"""Run the actual resolver body with platform stubs, not an MQL5 compile.
Pins the two phase-2A defects: live preview voting and BUY-first reactions.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / 'nadir2.mq5').read_text()
start = text.index('int ResolveFinalSignal(const int closed,string &why)\n')
end = text.index('//--------------------------------------------------------------------', start)
# MQL5 implicitly promotes literal-only string expressions; C++ needs a cast.
# This is the only dialect adaptation; decision logic is not reimplemented.
body = text[start:end].replace('(side>0?"BUY":"SELL")', 'string(side>0?"BUY":"SELL")')
prelude = r'''
#include <string>
#include <vector>
#include <cassert>
#include <iostream>
using string=std::string;
template<class T> int ArraySize(const std::vector<T>& v){return int(v.size());}
string IntegerToString(int i){return std::to_string(i);}
std::vector<double> g_buf_c(10,100),g_atr_buf(10,1);
std::vector<long> g_buf_t(10);
int g_rates_total=10,g_res_score=0,g_htf_bias=0,g_tac_dir=0;
int InpResWeightBias=25,InpResWeightZone=25,InpResWeightReaction=30,InpResWeightTactical=20,InpResMinScore=60;
bool InpUseHTFBias=true,g_tac_closed=false,InpUnifiedDecision=false;
int UD_Verdict(int,string&){assert(false);return 0;}
double g_atr=1;
long g_rxn_built_time=0;
const int RXN_LEVEL_REACTION=2;
struct Evidence{bool valid=false;int level=0;};
Evidence g_rxn_best_buy,g_rxn_best_sell;
int zone=0;
bool PA_ZoneAt(double,int,double,string&,double&,double&,int& d){d=zone;return zone!=0;}
'''
tests = r'''
void reset(){g_htf_bias=0;zone=0;g_tac_dir=0;g_tac_closed=false;
 g_rxn_best_buy={false,0};g_rxn_best_sell={false,0};g_rxn_built_time=g_buf_t[8];}
int main(){
 for(int i=0;i<10;i++)g_buf_t[i]=100+i;
 string why;
 reset();assert(ResolveFinalSignal(8,why)==0 && g_res_score==0);
 // Preview would previously supply the 20 points needed to reach 60.
 reset();g_htf_bias=zone=g_tac_dir=1;assert(ResolveFinalSignal(8,why)==0 && g_res_score==50);
 g_tac_closed=true;assert(ResolveFinalSignal(8,why)==1 && g_res_score==70);
 reset();g_htf_bias=zone=g_tac_dir=-1;assert(ResolveFinalSignal(8,why)==0 && g_res_score==50);
 g_tac_closed=true;assert(ResolveFinalSignal(8,why)==-1 && g_res_score==70);
 reset();g_htf_bias=zone=1;g_rxn_best_buy={true,2};g_rxn_best_sell={true,2};
 assert(ResolveFinalSignal(8,why)==2 && why.find("two-sided")!=string::npos);
 reset();g_htf_bias=zone=-1;g_rxn_best_buy={true,2};g_rxn_best_sell={true,2};
 assert(ResolveFinalSignal(8,why)==2);
 reset();g_htf_bias=zone=-1;g_rxn_best_buy={true,1};g_rxn_best_sell={true,2};
 assert(ResolveFinalSignal(8,why)==-1 && g_res_score==80);
 reset();g_htf_bias=zone=1;g_rxn_best_buy={true,2};g_rxn_best_sell={true,1};
 assert(ResolveFinalSignal(8,why)==1 && g_res_score==80);
 g_rxn_built_time--;assert(ResolveFinalSignal(8,why)==0 && g_res_score==50);
 assert(ResolveFinalSignal(9,why)==0 && g_res_score==0); // forming bar
 g_res_score=99;assert(ResolveFinalSignal(-1,why)==0 && g_res_score==0);
 // Exhaustive direction symmetry and all four-layer vote combinations.
 int n=0;
 for(int bias=-1;bias<=1;bias++)for(int z=-1;z<=1;z++)
 for(int tac=-1;tac<=1;tac++)for(int closed=0;closed<=1;closed++)
 for(int buy=0;buy<=1;buy++)for(int sell=0;sell<=1;sell++){
  reset();g_htf_bias=bias;zone=z;g_tac_dir=tac;g_tac_closed=closed;
  g_rxn_best_buy={bool(buy),2};g_rxn_best_sell={bool(sell),2};
  int a=ResolveFinalSignal(8,why),score=g_res_score;
  g_htf_bias=-bias;zone=-z;g_tac_dir=-tac;
  g_rxn_best_buy={bool(sell),2};g_rxn_best_sell={bool(buy),2};
  int b=ResolveFinalSignal(8,why);
  assert(a==2?b==2:b==-a);
  assert(score>=0 && score<=100 && g_res_score>=0 && g_res_score<=100);
  if(buy && sell)assert(a==2);
  n++;
 }
 std::cout<<"PASS resolver runtime: regressions + "<<n<<" exhaustive vote combinations\n";
}
'''
with tempfile.TemporaryDirectory(prefix='qsmc-resolver-') as d:
    src = Path(d) / 'resolver.cpp'
    binary = Path(d) / 'resolver'
    src.write_text(prelude + body + tests)
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
