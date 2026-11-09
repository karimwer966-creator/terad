"""Execute actual percentile method with synthetic chronological ATR samples."""
from pathlib import Path
import subprocess,tempfile
import native_toolchain as NT
root=Path(__file__).resolve().parents[1]
s=(root/'MQL5/Include/QSMC/QSMC_Scanners.mqh').read_text()
a=s.index('   double            Percentile(');b=s.index('\npublic:',a)
method=s[a:b].replace(') const',')')
pre=r'''
#include <vector>
#include <cmath>
#include <limits>
#include <cassert>
#include <iostream>
const double EMPTY_VALUE=std::numeric_limits<double>::max();
bool MathIsValidNumber(double v){return std::isfinite(v);}
double MathMax(double a,double b){return a>b?a:b;}
struct CBarSeries{std::vector<double> v;double ATRAt(int i)const{return i>=0&&i<int(v.size())?v[i]:0;}};
'''
tests=r'''
int main(){CBarSeries b;b.v.resize(301);for(int i=0;i<301;i++)b.v[i]=i+1;
assert(Percentile(b,300,100,b.ATRAt(300))==100); // rising, exclude current
assert(Percentile(b,50,100,b.ATRAt(50))==-1); // partial is not pct100
for(int i=0;i<301;i++)b.v[i]=301-i;
assert(Percentile(b,300,250,b.ATRAt(300))==0); // verified genuine minimum
for(auto& x:b.v)x=5;assert(Percentile(b,300,250,5)==0); // tied minimum
b.v[250]=EMPTY_VALUE;assert(Percentile(b,300,100,5)==-1);
b.v[250]=std::nan("");assert(Percentile(b,300,100,5)==-1);
assert(Percentile(b,300,100,EMPTY_VALUE)==-1);
std::cout<<"PASS full-window causal percentiles: rising/falling/constant/short/invalid\n";}
'''
cxx=NT.compiler()
if cxx is None:
 NT.skip('native subset: causal percentile method')
else:
 with tempfile.TemporaryDirectory() as d:
  p=Path(d)/'test.cpp';exe=Path(d)/'test';p.write_text(pre+method+tests)
  subprocess.run([cxx,'-std=c++17',str(p),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True)
raise SystemExit(NT.exit_code([]))
