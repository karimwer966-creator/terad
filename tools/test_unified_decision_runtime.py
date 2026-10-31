"""Actual new header, C++ dialect adapters + MT5 stubs. Not an MQL compile."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'MQL5/Include/QSMC/QSMC_UnifiedDecision.mqh').read_text()
# MQL dynamic arrays are represented by vector; preserve all decision logic.
for typ, name in [('SZREZone', 'out'), ('SZREZone', 'dropped'), ('SZREZone', 'tail'),
                  ('double', 'h'), ('double', 'l'), ('int', 'selected')]:
    source = source.replace(f'{typ} &{name}[]', f'std::vector<{typ}> &{name}')
source = source.replace('SZREZone all[];', 'std::vector<SZREZone> all;')
prelude = r'''
#define QSMC_UD_NATIVE_TEST
#include <string>
#include <vector>
#include <cmath>
#include <cassert>
#include <limits>
#include <iostream>
using string=std::string;using datetime=long long;using ENUM_TIMEFRAMES=int;
int _Period=5;string _Symbol="TEST";
const double EMPTY_VALUE=std::numeric_limits<double>::max();
template<class T> int ArraySize(const std::vector<T>& a){return int(a.size());}
template<class T> int ArrayResize(std::vector<T>& a,int n){a.resize(n);return n;}
double MathMax(double a,double b){return std::max(a,b);}
double MathMin(double a,double b){return std::min(a,b);}
bool MathIsValidNumber(double v){return std::isfinite(v);}
int StringCompare(const string& a,const string& b){return a.compare(b);}
bool InpUnifiedDecision=true,InpUseHTFBias=true;
double InpUnifiedMergeATR=.15,g_atr=1;
int InpMessageCooldownBars=3,g_rates_total=10,g_htf_bias=1,g_res_score=0;
bool g_tac_closed=true;int g_tac_dir=1;
std::vector<datetime> g_buf_t(30);
datetime g_rxn_built_time=0;
const int RXN_LEVEL_REACTION=2;
struct E{bool valid=true;int level=2;};E g_rxn_best_buy,g_rxn_best_sell;
struct SConfirmedSignalJournalEntry{datetime availability_time=0;int confirmation_bar=0,created_bar=0;bool is_buy=true;};
std::vector<SConfirmedSignalJournalEntry> g_confirmed_signal_journal;
struct SZREZone{double lo=0,hi=0;int side=1,age_bars=8,strength=0,touches=0;string id,sources,detail;};
const int ZRE_SUPPORT=1;std::vector<SZREZone> g_zre_zones,g_rxn_extra_zones;
struct SZREContext{double atr=1,close_px=100,touch_tol=0;int closed=8,hist=8,min_score=60,max_zones=1;};
struct Sig{double zone_lo=0,zone_hi=0;bool is_buy=true;};std::vector<Sig> g_zre_sig;
string ZRE_TokenUnion(const string& a,const string& b){return a+"|"+b;}
string ZRE_ZoneId(int s,double l,double h){return std::to_string(s)+":"+std::to_string(l)+":"+std::to_string(h);}
bool ZRE_ZoneBefore(const SZREZone& a,const SZREZone& b,double){
 if(a.strength!=b.strength)return a.strength>b.strength;return a.id<b.id;
}
int ZRE_CountTouchEpisodes(double lo,double hi,double,int first,int last,const std::vector<double>& h,const std::vector<double>& l){
 bool was=false;int n=0;for(int i=first;i<=last;i++){bool touch=h[i]>=lo&&l[i]<=hi;if(touch&&!was)n++;was=touch;}return n;
}
int iBarShift(const string&,int,datetime stamp,bool){
 for(int i=0;i<g_rates_total;i++)if(g_buf_t[i]==stamp)return g_rates_total-1-i;
 return -1;
}
'''
tests = r'''
void clearlog(){for(int i=0;i<UD_LOG_CAP;i++){g_ud_log_times[i]=0;g_ud_log_keys[i]="";}}
int main(){
 for(int i=0;i<30;i++)g_buf_t[i]=1000+i*60;
 for(int a=-1;a<=1;a++)for(int conflict=0;conflict<2;conflict++)
 for(int b=0;b<2;b++)for(int r=0;r<2;r++)for(int t=0;t<2;t++){
  SUnifiedDecision d;UD_Policy(a,conflict,b,r,t,d);
  if(a==0||conflict)assert(d.direction==0&&d.score==0);
  else assert(d.direction==a&&d.score==60+b*10+r*15+t*15);
 }
 UD_Update(8);assert(g_ud.direction==0); // advisory evidence cannot authorize
 g_confirmed_signal_journal={{g_buf_t[9],8,2,true}};g_rxn_built_time=g_buf_t[8];
 UD_Update(8);assert(g_ud.direction==1&&g_ud.score==100);
 assert(UD_AlertAllows(3,1)&&!UD_AlertAllows(2,1)&&!UD_AlertAllows(3,-1));
 g_confirmed_signal_journal.push_back({g_buf_t[9],8,2,false});UD_Update(8);assert(g_ud.direction==0);
 g_confirmed_signal_journal={{g_buf_t[8],7,2,true}};UD_Update(8);assert(g_ud.direction==0);
 string why;assert(UD_Verdict(7,why)==0&&g_res_score==0);
 assert(UD_Near(1,2,1,2.1,3,1,.15));assert(!UD_Near(1,2,1,2.1,3,-1,.15));
 // Transitive union across out/tail/dropped; max strength retained, touches not summed.
 SZREZone a;a.lo=100;a.hi=101;a.strength=70;a.id="a";a.touches=99;
 SZREZone b=a;b.lo=101.1;b.hi=102;b.strength=90;b.id="b";
 SZREZone c=a;c.lo=102.1;c.hi=103;c.strength=50;c.id="c";
 SZREZone opp=a;opp.side=-1;opp.id="opp";opp.strength=65;
 std::vector<SZREZone> out={a},drop={c},tail={opp,b};SZREContext ctx;
 std::vector<double> h(10,101),l(10,100);
 UD_MergeZones(out,drop,tail,ctx,h,l);
 assert(out.size()==1&&out[0].lo==100&&out[0].hi==103&&out[0].strength==90);
 assert(out[0].touches==1&&drop.empty()&&tail.size()==1&&tail[0].side==-1);
 std::vector<SZREZone> o2={b},d2={a},t2={c,opp};UD_MergeZones(o2,d2,t2,ctx,h,l);
 assert(o2[0].id==out[0].id&&o2[0].strength==out[0].strength);
 // Render paths from opposite ends of a merged chain share one display slot.
 g_zre_zones=out;g_zre_sig={{100,101,true},{102.1,103,true},{102.1,103,false}};
 std::vector<int> selected={0};assert(UD_PathDuplicate(1,selected,1)==0);
 assert(UD_PathDuplicate(2,selected,1)==-1);
 // Diagnostic cooldown measured in actual bars, not elapsed wall-clock minutes.
 clearlog();assert(UD_LogAllows("a"));assert(!UD_LogAllows("a"));
 g_rates_total=12;assert(!UD_LogAllows("a")); // two bars later
 g_rates_total=13;assert(UD_LogAllows("a")); // three bars later
 InpMessageCooldownBars=0;assert(UD_LogAllows("a")&&UD_LogAllows("a"));
 InpMessageCooldownBars=3;clearlog();for(int i=0;i<UD_LOG_CAP;i++)assert(UD_LogAllows(std::to_string(i)));
 assert(!UD_LogAllows("overflow")&&!UD_LogAllows("0"));
 g_rates_total=16;assert(UD_LogAllows("overflow"));
 InpUnifiedDecision=false;assert(UD_AlertAllows(2,-1));
 std::cout<<"PASS actual unified header: authority, merges, cooldown, saturation and legacy mode\n";
}
'''
with tempfile.TemporaryDirectory(prefix='qsmc-unified-') as d:
    src=Path(d)/'unified.cpp';binary=Path(d)/'unified'
    src.write_text(prelude+source+tests)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',
                    '-Wno-misleading-indentation','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer',str(src),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
