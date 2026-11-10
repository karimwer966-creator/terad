#!/usr/bin/env python3
"""Exercise the actual QATS account guard with native MT5 API stubs; not MT5."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_xau_execution_policy import function, SOURCE

ROOT = Path(__file__).resolve().parents[1]

class QuantumAccountPolicy(unittest.TestCase):
    def test_native_account_gate(self):
        compiler = shutil.which('g++')
        if not compiler:
            self.skipTest('g++ unavailable')
        prefix = r'''
#include <string>
#include <iostream>
#include <cstdlib>
using std::string;
const int ACCOUNT_TRADE_MODE=0, ACCOUNT_LOGIN=1, ACCOUNT_TRADE_ALLOWED=2, ACCOUNT_SERVER=3;
const int ACCOUNT_TRADE_MODE_DEMO=0, ACCOUNT_TRADE_MODE_CONTEST=1, ACCOUNT_TRADE_MODE_REAL=2;
const int TERMINAL_TRADE_ALLOWED=0, MQL_TRADE_ALLOWED=0, SYMBOL_TRADE_MODE_FULL=4;
long mode=0, login=123, g_boundLogin=123, g_boundMode=0;
string server="Broker-Demo", g_boundServer="Broker-Demo", _Symbol="XAUUSD";
bool InpDemoOnly=true, InpAllowRealTrading=false, terminal=true, mql=true, account=true;
string InpRealAccountConfirm="", InpRealServerConfirm="";
struct Spec { long tradeMode=SYMBOL_TRADE_MODE_FULL; } g_spec;
long AccountInfoInteger(int x){return x==ACCOUNT_TRADE_MODE ? mode : (x==ACCOUNT_LOGIN ? login : account);}
string AccountInfoString(int){return server;}
bool TerminalInfoInteger(int){return terminal;}
bool MQLInfoInteger(int){return mql;}
string IntegerToString(long n){return std::to_string(n);}
template<class... T> string StringFormat(const char* fmt,T...){return fmt;}
'''
        main = r'''
void check(bool x,const char* msg){if(!x){std::cerr<<msg<<"\n";std::exit(1);}}
int main(){
 string reason;
 check(VerifyAccountProtection(reason),"demo allowed");
 mode=ACCOUNT_TRADE_MODE_REAL; g_boundMode=mode; server="Broker-Live";g_boundServer=server;
 check(!VerifyAccountProtection(reason),"real default refused");
 InpDemoOnly=false;check(!VerifyAccountProtection(reason),"no opt-in");
 InpAllowRealTrading=true;check(!VerifyAccountProtection(reason),"empty login");
 InpRealAccountConfirm="456";check(!VerifyAccountProtection(reason),"wrong login");
 InpRealAccountConfirm="123";check(!VerifyAccountProtection(reason),"empty server");
 InpRealServerConfirm="Wrong";check(!VerifyAccountProtection(reason),"wrong server");
 InpRealServerConfirm="Broker-Live";check(VerifyAccountProtection(reason),"fully authorized real");
 terminal=false;check(!VerifyAccountProtection(reason),"terminal disabled");terminal=true;
 mql=false;check(!VerifyAccountProtection(reason),"EA permission disabled");mql=true;
 account=false;check(!VerifyAccountProtection(reason),"account permission disabled");account=true;
 g_spec.tradeMode=0;check(!VerifyAccountProtection(reason),"symbol mode disabled");g_spec.tradeMode=4;
 login=456;check(!VerifyAccountProtection(reason),"identity change");login=123;
 server="Other";check(!VerifyAccountProtection(reason),"server change");server="Broker-Live";
 mode=ACCOUNT_TRADE_MODE_CONTEST;g_boundMode=mode;check(!VerifyAccountProtection(reason),"contest blocked");
 mode=42;g_boundMode=mode;check(!VerifyAccountProtection(reason),"unknown mode blocked");
 std::cout<<"16 account and authorization checks passed\n";
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cpp, exe = Path(tmp)/'test.cpp', Path(tmp)/'test'
            cpp.write_text(prefix + function('VerifyAccountProtection') + main)
            built = subprocess.run([compiler, '-std=c++17', str(cpp), '-o', str(exe)], text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(exe)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            print(run.stdout.strip())

    def test_production_preset_matches_source_and_is_safe_by_default(self):
        presets = list((ROOT/'presets').glob('*.set'))
        self.assertEqual([p.name for p in presets], ['Quantum_XAUUSD_PRODUCTION.set'])
        lines = [line for line in presets[0].read_text().splitlines() if line and not line.startswith(';')]
        values = dict(line.split('=', 1) for line in lines)
        declared = re.findall(r'^input\s+\w+\s+(Inp\w+)\s*=', SOURCE, re.M)
        self.assertEqual(len(values), len(lines), 'duplicate preset keys')
        self.assertEqual(set(values), set(declared), 'unknown or missing MT5 inputs')
        for key, expected in {'InpMinScore':'55', 'InpEnableTrading':'true', 'InpDryRun':'false',
                              'InpDemoOnly':'true', 'InpAllowRealTrading':'false',
                              'InpRealAccountConfirm':'', 'InpRealServerConfirm':'',
                              'InpRiskPercent':'0.10', 'InpMaxRiskPercent':'0.10'}.items():
            self.assertEqual(values[key], expected, key)
        self.assertIn('canManage && raw.dir != 0', SOURCE)
        self.assertIn('!g_execBlocked && InpEnableTrading && !InpDryRun && VerifyAccountProtection(managementReason)', SOURCE)

if __name__ == '__main__':
    unittest.main(verbosity=2)
