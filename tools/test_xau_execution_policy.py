#!/usr/bin/env python3
"""Native stub harness executing extracted QATS MQL function bodies, not MT5."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'MQL5/Experts/QuantumAutonomousTradingSystem.mq5').read_text()


def function(name):
    m = re.search(r'^(?:bool|int) ' + name + r'\([^;]*?\)\s*\{', SOURCE, re.M | re.S)
    if not m:
        raise AssertionError(name)
    i, depth = m.end(), 1
    while depth:
        depth += (SOURCE[i] == '{') - (SOURCE[i] == '}')
        i += 1
    return SOURCE[m.start():i]


class XauExecutionPolicy(unittest.TestCase):
    def test_native_execution(self):
        cxx = shutil.which('g++')
        if not cxx:
            self.skipTest('g++ unavailable')
        prelude = r'''
#include <cmath>
#include <map>
#include <string>
#include <cstdio>
#include <iostream>
using std::string;
using uint = unsigned int;
using ulong = unsigned long;
using datetime = long;
#define ORDER_TYPE_BUY 0
#define ORDER_TYPE_SELL 1
#define SYMBOL_ASK 0
#define SYMBOL_BID 1
#define ACCOUNT_EQUITY 0
#define ACCOUNT_MARGIN_FREE 1
#define MathAbs std::abs
#define MathFloor std::floor
#define MathRound std::round
#define MathMax std::max
bool MathIsValidNumber(double x){return std::isfinite(x);}
template<class... T> string StringFormat(const char* fmt, T...){return fmt;}
template<class... T> void PrintFormat(const char*, T...){}
void Print(string){}
string DoubleToString(double, int){return "value";}
string _Symbol="XAUUSD";
struct Spec { double point=.01, tickSize=.01, volStep=.01, volMin=.01, volMax=100, volLimit=0; int stopsLevel=20; string profitCcy="USD"; } g_spec;
struct SAnalysis { int dir=1,score=55; datetime signalBar=1, setupTime=0; double entry=2000.1, sl=1990, tp=2020.3, stopDist=10.1; string tpSource="RR"; };
string g_executionReason, g_executionStage, InpTradeComment="QATS";
SAnalysis g_pendingPlan;
int g_statApproved[2], g_statExecuted[2];
#define TIME_DATE 1
#define TIME_MINUTES 2
string TimeToString(datetime, int){return "time";}
string SetupId(int, datetime){return "setup";}
string PriceText(double){return "price";}
string QATS_ClassName(int){return "class";}
int SideIndex(int dir){return dir>0?0:1;}
bool oppositeOpen=false, setupTraded=false;
int setupMarks=0;
bool OppositePositionOpen(int){return oppositeOpen;}
bool SetupAlreadyTraded(int, datetime){return setupTraded;}
void MarkSetupTraded(int, datetime){++setupMarks;}
int InpMinScore=55, InpMinStopPoints=20, InpMaxStopPoints=5000;
double InpMinRR=1.5, InpMaxSpreadFracOfStop=.2, InpMaxMarginUse=.9;
bool InpDryRun=false;
double bid=2000, ask=2000.1, equity=10000, freeMargin=10000;
int sentCount=0, g_tradesToday=0, g_pendingRetries=0, g_pendingDir=0;
uint serverRetcode=10009; bool sendResult=true;
ulong g_pendingRetryAt=0;
double g_pendingEntry=0,g_pendingSL=0,g_pendingTP=0;
std::map<string,double> globals;
string GVKey(string s){return s;}
bool GlobalVariableCheck(string s){return globals.count(s);}
double GlobalVariableGet(string s){return globals[s];}
bool GlobalVariableSetOnCondition(string s,double n,double old){if(globals[s]!=old)return false;globals[s]=n;return true;}
void GlobalVariablesFlush(){}
#define ACCOUNT_TRADE_MODE 2
#define ACCOUNT_TRADE_MODE_REAL 2
long AccountInfoInteger(int){return 0;}
bool IsXAUUSD(){return true;}
bool LoadSymbolSpec(Spec &){return true;}
double SymbolInfoDouble(string,int id){return id==SYMBOL_ASK?ask:bid;}
double AccountInfoDouble(int id){return id==ACCOUNT_EQUITY?equity:freeMargin;}
double EffectiveRiskPercent(){return .5;}
bool OrderCalcProfit(int dir,string,double,double open,double close,double &result){result=(dir==ORDER_TYPE_BUY ? close-open : open-close)*100;return true;}
bool OrderCalcMargin(int,string,double volume,double,double &margin){margin=volume*1000;return volume>0;}
int GetLastError(){return 0;}
bool guard=true;
bool EntriesAllowed(string &r){if(!guard)r="spread or risk guard";return guard;}
int QATS_Classify(double,double){return 0;}
bool QATS_ProfileAllows(int){return false;} // strict profile must not gate XAUUSD
string QATS_ProfileName(int){return "STRICT";}
int InpSignalExecutionProfile=0;
void QATS_Audit(string,int,double,double,string,string){}
void ConfigureTrade(){}
struct Trade { bool Buy(double,string,double,double,double,string){++sentCount;return sendResult;} bool Sell(double,string,double,double,double,string){++sentCount;return sendResult;} uint ResultRetcode(){return serverRetcode;} ulong ResultDeal(){return 1;} ulong ResultOrder(){return 1;} string ResultRetcodeDescription(){return "done";} double ResultVolume(){return .1;} double ResultPrice(){return 2000;} } g_trade;
bool IsSuccessRetcode(uint rc){return rc==10009;}
bool IsTransientRetcode(uint rc){return rc==10012;}
bool VerifyPositionOpened(int,ulong &t){t=1;return true;}
string TodayKey(){return "today";}
void GVSet(string,double){}
datetime TimeTradeServer(){return 1;}
'''
        functions = '\n'.join(function(n) for n in ('QATS_DirectionVeto', 'QATS_ScoreEligible', 'QATS_StopsValid', 'ReserveSignal', 'CalcPositionVolume', 'ExecuteSignal'))
        main = r'''
void check(bool ok,const char* message){if(!ok){std::cerr<<message<<"\n";std::exit(1);}}
void reset(){globals.clear();globals["sig_buy"]=0;globals["sig_sell"]=0;sentCount=0;guard=true;freeMargin=10000;bid=2000;ask=2000.1;InpDryRun=false;serverRetcode=10009;sendResult=true;oppositeOpen=false;setupTraded=false;setupMarks=0;}
SAnalysis plan(int dir,int score){SAnalysis p;p.dir=dir;p.score=score;p.signalBar=10;p.entry=dir>0?ask:bid;p.sl=dir>0?1990:2010.1;p.tp=dir>0?2021:1979;p.stopDist=10.1;return p;}
int main(){
 for(int dir:{1,-1}) {
  check(QATS_DirectionVeto(true,dir,-dir,-dir,true,false)==0,"gold opposing EMA");
  check(QATS_DirectionVeto(true,dir,-dir,dir,true,false)==0,"gold counter D1");
  check(QATS_DirectionVeto(false,dir,-dir,-dir,true,false)==1,"non-gold EMA veto");
  check(QATS_DirectionVeto(false,dir,-dir,dir,true,false)==2,"non-gold D1 veto");
 }
 int scores[]={54,55,56,59,60,69,70,79,80,89,90,100};
 for(int dir: {1,-1}) for(int score:scores){reset(); auto p=plan(dir,score);bool ok=ExecuteSignal(p);check(ok==(score>=55),"score boundary");check(sentCount==(score>=55?1:0),"send count");}
 for(int dir:{1,-1}){
  reset();auto p=plan(dir,55);check(ExecuteSignal(p),"first send");check(!ExecuteSignal(p)&&sentCount==1,"duplicate");
  reset();p=plan(dir,55);p.sl=dir>0?2000:2000.1;check(!ExecuteSignal(p)&&sentCount==0,"bad SL");
  reset();p=plan(dir,55);p.tp=dir>0?1999:2001;check(!ExecuteSignal(p)&&sentCount==0,"bad TP");
  reset();p=plan(dir,55);guard=false;check(!ExecuteSignal(p)&&sentCount==0,"absolute spread / risk guard");
  reset();p=plan(dir,55);freeMargin=0;check(!ExecuteSignal(p)&&sentCount==0,"insufficient margin");
  reset();p=plan(dir,55);InpMaxSpreadFracOfStop=.001;check(!ExecuteSignal(p)&&sentCount==0,"fractional spread");InpMaxSpreadFracOfStop=.2;
  reset();p=plan(dir,55);InpDryRun=true;check(!ExecuteSignal(p)&&sentCount==0&&globals[dir>0?"sig_buy":"sig_sell"]==0,"dry run");
  reset();p=plan(dir,55);serverRetcode=10012;sendResult=false;check(!ExecuteSignal(p)&&!ExecuteSignal(p)&&sentCount==1&&g_pendingRetryAt==0,"timeout cannot retry");
  reset();p=plan(dir,55);p.sl+=.005;check(!ExecuteSignal(p)&&sentCount==0,"tick grid");
  reset();p=plan(dir,55);oppositeOpen=true;check(!ExecuteSignal(p)&&sentCount==0,"never both sides");
  reset();p=plan(dir,55);setupTraded=true;check(!ExecuteSignal(p)&&sentCount==0,"setup already traded");
  reset();p=plan(dir,55);check(ExecuteSignal(p)&&setupMarks==1,"an accepted order spends its setup");
  reset();p=plan(dir,55);serverRetcode=10016;sendResult=false;check(!ExecuteSignal(p)&&setupMarks==0,"a refused order does not spend its setup");
 }
 std::cout<<"24 score/direction, 8 directional veto, and 26 guard/duplicate cases passed\n";
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cpp, exe = Path(tmp)/'test.cpp', Path(tmp)/'test'
            cpp.write_text(prelude + functions + main)
            compile_result = subprocess.run([cxx, '-std=c++17', str(cpp), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            print(result.stdout.strip())

    def test_policy_wiring(self):
        self.assertRegex(SOURCE, r'InpMinScore\s*=\s*55\s*;')
        # v1.20: the directional veto is evaluated for EACH side inside EvaluateSide
        self.assertIn('QATS_DirectionVeto(IsXAUUSD(), dir, d1Bias, h4Bias, InpUseEMAAlignmentVeto, InpAllowCounterBias)', SOURCE)
        self.assertIn('EvaluateSide(+1, r, st, pools, a.d1Bias, a.h4Bias, a.dealPos, pxNow, a.buy);', SOURCE)
        self.assertIn('EvaluateSide(-1, r, st, pools, a.d1Bias, a.h4Bias, a.dealPos, pxNow, a.sell);', SOURCE)
        self.assertIn('!IsXAUUSD() && !QATS_ProfileAllows(plan_cls)', SOURCE)
        self.assertIn('if(IsXAUUSD() && !ReserveSignal(plan, g_executionReason)) return false;', SOURCE)
        self.assertIn('if(IsXAUUSD() || AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL)\n   {\n      g_executionReason = StringFormat("order not confirmed:', SOURCE)
        self.assertIn('LogSignal(raw,', SOURCE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
