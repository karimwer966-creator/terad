"""Reproduce the 32 MetaEditor errors caused by comma-separated inputs."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import native_toolchain as NT
r=Path(__file__).resolve().parents[1]
h=(r/'MQL5/Include/QSMC/QSMC_InputFingerprint.mqh').read_text()
ends={'InpAsianEnd':'18','InpLondonEnd':'16','InpNewYorkEnd':'16',
      'InpLondonKillZoneEnd':'10','InpNewYorkKillZoneEnd':'10',
      'InpSBWin1End':'240','InpSBWin2End':'660','InpSBWin3End':'900'}
for name,default in ends.items():
    assert f'QSMC_AddInputHash(a,"{name}",IntegerToString((long)({name})));' in h, f'missing runtime input {name}'
    assert f'QSMC_AddInputHash(d,"{name}",IntegerToString((long)({default})));' in h, f'wrong default {name}'
spec=importlib.util.spec_from_file_location('fingerprint',r/'tools/generate_input_fingerprint.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
fixture='''// input int InpFake=0;
input group "group; input int InpFake2=0;"
input int InpA=9, InpB=18; // comment
input string InpText="a,b; // literal", InpOther="escaped\\\"comma,yes";
/* input int InpFake3=0; */
input double InpNested=Fn(1,2),
             InpNext=(3+4);
input color InpColor=C'1,2,3';
'''
assert m.parse_inputs(fixture)==[
 ('int','InpA','9'),('int','InpB','18'),
 ('string','InpText','"a,b; // literal"'),('string','InpOther','"escaped\\\"comma,yes"'),
 ('double','InpNested','Fn(1,2)'),('double','InpNext','(3+4)'),('color','InpColor',"C'1,2,3'")]
for invalid in ('input int InpA;', 'input int InpA=1,broken;', 'input int InpA=1,;', 'input int InpA=Fn(1,2;'):
    try:m.parse_inputs(invalid)
    except ValueError:pass
    else:raise AssertionError('silently accepted malformed declaration: '+invalid)
subprocess.run([sys.executable,str(r/'tools/generate_input_fingerprint.py'),'--check'],check=True)
print('PASS comma declarations, all eight End inputs, literals, nesting, comments and fail-closed parsing')

# Compile the actual generated function in its C++-compatible subset.
# Enum/color constants are symbolic stubs: this is NOT an MQL/MetaEditor build.
import re
import tempfile
entries=[entry for path in m.paths for entry in m.parse_inputs((r/path).read_text())]
assert len(entries)==576
identifiers=set()
for kind,name,default in entries:
    if kind!='string':
        identifiers.update(re.findall(r'\b[A-Za-z_]\w*\b',default))
identifiers-= {'true','false'}
cpp='''#include <string>
#include <sstream>
#include <iomanip>
#include <cstdint>
#include <cassert>
using string=std::string; using uint=uint32_t;
string IntegerToString(long value){return std::to_string(value);}
string DoubleToString(double value,int digits){std::ostringstream s;s<<std::fixed<<std::setprecision(digits)<<value;return s.str();}
void QSMC_AddInputHash(uint &h,const string &key,const string &value){for(unsigned char c:key+"#"+value+";")h=(h^c)*16777619u;}
'''
cpp+='\n'.join(f'const int {name}={i+1};' for i,name in enumerate(sorted(identifiers)))+'\n'
for kind,name,default in entries:
    cpp+=f'{kind if kind in ("string","double","bool","int") else "int"} {name}={default};\n'
cpp+=h+'\nint main(int argc,char **argv){\n'
for name in ends:
    cpp+=f'if(argc>1 && string(argv[1])=="{name}") ++{name};\n'
cpp+='uint a=0,d=0; QA_InputHashes(a,d); assert((a==d)==(argc==1)); return 0;}\n'
cxx=NT.compiler()
if cxx is None:
    NT.skip('native subset: generated input fingerprint')
else:
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/'fingerprint.cpp';binary=Path(tmp)/'fingerprint'
        source.write_text(cpp)
        subprocess.run([cxx,'-std=c++17','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
        for name in ends:subprocess.run([str(binary),name],check=True)
    print('PASS native generated-function defaults equality and independent sensitivity to all eight End inputs (not MT5 proof)')
raise SystemExit(NT.exit_code([]))
