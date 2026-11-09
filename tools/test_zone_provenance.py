"""Source wiring + native predicate: wrong-scale/out-of-history zones fail closed."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
t=(r/'MQL5/Include/QSMC/QSMC_Types.mqh').read_text()
assert 'QSMC_ZoneRangeReason(' in t,'no symbol-history plausibility gate before zone scoring'
a=t.index('string QSMC_ZoneRangeReason(');b=t.index('// ZONE_RANGE_END',a)
method=t[a:b]
pre='''#include <string>\n#include <cmath>\n#include <cassert>\n#include <limits>\nusing string=std::string;\nconst double EMPTY_VALUE=std::numeric_limits<double>::max();\nbool MathIsValidNumber(double x){return std::isfinite(x);}\ndouble MathMax(double a,double b){return a>b?a:b;}\n'''
checks=r'''
int main(){
assert(QSMC_ZoneRangeReason(25745,25782,77900,76000,85000,500,10,120,12)!="");
assert(QSMC_ZoneRangeReason(78000,78200,77900,76000,85000,500,10,120,12)=="");
assert(QSMC_ZoneRangeReason(84000,84200,77900,76000,85000,100,121,120,12)!="");
assert(QSMC_ZoneRangeReason(84000,84200,77900,76000,85000,100,1,120,12)=="");
assert(QSMC_ZoneRangeReason(EMPTY_VALUE,EMPTY_VALUE,77900,76000,85000,500,1,120,12)!="");
assert(QSMC_ZoneRangeReason(1,2,77900,0,0,500,1,120,12)!="");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'zone.cpp';e=Path(d)/'zone';p.write_text(pre+method+checks)
 subprocess.run(['g++','-std=c++17',str(p),'-o',str(e)],check=True);subprocess.run([str(e)],check=True)
main=(r/'nadir2.mq5').read_text();scanner=(r/'MQL5/Include/QSMC/QSMC_Scanners.mqh').read_text()
assert 'QA_FilterCandidates(cands,ctx)' in main
assert scanner.index('QSMC_ZoneRangeReason(z.lo')<scanner.index('m_react.Evaluate(z,*ch')
print('PASS symbol-history plausibility gate and host/scanner score boundaries')
