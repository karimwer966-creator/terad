#!/usr/bin/env python3
"""Offline source contracts for CORE diagnostics; these do NOT execute MQL5."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IND = (ROOT / 'nadir2.mq5').read_text(encoding='utf-8')
EA = (ROOT / 'MQL5/Experts/QSMC_AutoTrader.mq5').read_text(encoding='utf-8')


def between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start) + len(start))]


class CoreSourceContracts(unittest.TestCase):
    def test_abi_mapping_and_exact_copy(self):
        names = ['Dir', 'Entry', 'SL', 'TP1', 'TP2', 'TP3']
        ids = ['DIR', 'ENTRY', 'SL', 'TP1', 'TP2', 'TP3']
        for i, (name, ident) in enumerate(zip(names, ids), 7):
            self.assertRegex(IND, rf'SetIndexBuffer\({i},\s*BufSigCore{name},\s*INDICATOR_CALCULATIONS\)')
            self.assertRegex(EA, rf'#define\s+QSMC_BUF_CORE_{ident}\s+{i}\b')
            self.assertIn(f'CopyBuffer(g_handle,QSMC_BUF_CORE_{ident},0,count,', EA)

    def test_closed_bar_lookback_includes_all_requested_shifts(self):
        hb = between(EA, 'void PrintHeartbeatCore(', 'void DiagnosticHeartbeat()')
        for fragment in ('calc<look+1', '0,look+1,hb_dir', 'got<look+1',
                         'for(int i=1;i<=look;i++)', 'ArraySetAsSeries(hb_dir,true)'):
            self.assertIn(fragment, hb)
        self.assertIn('no zero-signal conclusion', hb)

    def test_heartbeat_records_are_independent_of_core_readiness(self):
        hb = between(EA, 'void DiagnosticHeartbeat()', 'void ManageOpenPositions()')
        # An early return in the CORE scan must not skip the verdict/guard or
        # append them to a long CORE message.
        main = hb[hb.index('g_heartbeat_first=false;'):]
        self.assertNotIn('return;', main)
        self.assertEqual(main.count('PrintHeartbeatCore(mode);'), 1)
        self.assertEqual(main.count('PrintIndicatorVerdict();'), 1)
        self.assertIn('string _guard="[QSMC_AT] GUARD day_base="', main)
        self.assertIn('Print(_guard);', main)
        self.assertIn('Print("[QSMC_AT] heartbeat counters: processed "', main)
        self.assertIn('Print("[QSMC_AT] last skip: ",g_last_note);', main)
        summary = between(EA, 'void PrintHeartbeatCore(', 'void DiagnosticHeartbeat()')
        for field in ('indicator verdict:', 'GUARD day_base=', 'processed ', 'g_last_note'):
            self.assertNotIn(field, summary)

    def test_verdict_probe_and_closed_bar_value_are_distinct(self):
        ident = between(EA, 'string IndicatorIdentityLine()', 'string DiagVarName(')
        self.assertIn('VCODE_COPY="+IntegerToString(vcode_n)', ident)
        self.assertIn('BarsCalculated="+IntegerToString(bars_calc)', ident)
        self.assertIn('INDICATOR_BUILD=UNVERIFIED', ident)
        verdict = between(EA, 'double ReadCoreVerdictFromBuffer()', 'string DisciplineSuffix()')
        self.assertIn('CopyBuffer(g_handle,QSMC_BUF_CORE_VCODE,1,1,v)', verdict)
        self.assertIn('Print("[QSMC_AT] indicator verdict: ",DiagCodeText', verdict)
        self.assertIn('Print("[QSMC_AT] indicator verdict: no diagnostic record', verdict)
        self.assertIn('default-input globals; reader not verified', verdict)

    def test_gate_audit_names_the_reader_after_closed_bar_publication(self):
        calc = between(IND, 'int OnCalculate(', '   RunRuntimeDisplayNoLookaheadAudit(closed,g_buf_t);')
        count = 'if(is_new_bar) g_gate_audit.bars++;'
        self.assertEqual(calc.count('g_gate_audit.bars++;'), 1)
        self.assertLess(calc.index(count), calc.index('DiagPublishCoreState(closed);'))
        audit = calc[calc.index('GateProfilePublish(closed);'):]
        self.assertIn('if(is_new_bar && InpGateAuditLogEveryBars>0 &&', audit)
        self.assertIn('g_instance_role==ROLE_EA_READER && g_gate_audit.bars==1', audit)
        self.assertIn('(g_gate_audit.bars%InpGateAuditLogEveryBars)==0', audit)
        for field in ('EnumToString(g_instance_role)', '" inst="+g_instance_id',
                      '" closed_bar="+TimeToString(g_buf_t[closed]'):
            self.assertIn(field, audit)
        self.assertEqual(calc.count('Print("[GateAudit] '), audit.count('Print("[GateAudit] ",audit_origin'))
        self.assertIn('Print("[GateAudit] ",audit_origin," | top blocker: "', audit)
        self.assertIn('Print("[GateLeg] ",audit_origin', audit)

    def test_strategy_tester_declares_default_icustom_dependency(self):
        self.assertRegex(EA, r'(?m)^#property\s+tester_indicator\s+"nadir2\.ex5"\s*$')
        self.assertIn('g_handle=iCustom(_Symbol,_Period,InpIndicatorName);', EA)

    def test_replay_result_names_its_instance(self):
        replay = between(IND, 'if(g_replay_audit_pending && first_run)',
                         'g_replay_audit_pending=false;')
        self.assertIn('" | role="+EnumToString(g_instance_role)+" inst="+g_instance_id', replay)
        for status in ('PASS', 'FAIL'):
            message = replay[replay.index(f'Print("[CausalReplay] {status} '):].split(');', 1)[0]
            self.assertIn('TimeToString(g_buf_t[closed]),replay_origin', message)

    def test_reader_startup_reports_compiled_indicator_identity(self):
        init = between(IND, 'int OnInit()', 'void OnDeinit(')
        identity = init[init.index('Print("[QSMC_INSTANCE] INSTANCE_ID=",g_instance_id,'):]
        for field in ('" | INSTANCE_ROLE=",EnumToString(g_instance_role)',
                      '" | BUILD_VERSION=",QSMC_VERSION_TEXT',
                      '" | COMPILED_AT=",TimeToString(__DATETIME__',
                      '" | CORE_EXPORT=",(InpExportSignalBuffers?"ON":"OFF")'):
            self.assertIn(field, identity)

    def test_observation_preset_disables_entries_and_position_management(self):
        preset = ROOT / 'presets/QSMC_AutoTrader_DIAG_XAUUSD_M15.set'
        overrides = dict(line.split('=', 1) for line in preset.read_text().splitlines()
                         if line and not line.startswith(';'))
        required = {'InpEnableTrading': 'false', 'InpDryRun': 'true',
                    'InpAllowRealTrading': 'false', 'InpRealAccountConfirm': '',
                    'InpRealServerConfirm': '', 'InpResetBreakersAtInit': 'false',
                    'InpCloseOnOpposite': 'false', 'InpUseTPPips': 'false',
                    'InpBreakEvenAtR': '0.0', 'InpPartialCloseAtR': '0.0',
                    'InpOwnExecutionLane': 'false', 'InpPinTimeframeMinutes': '15',
                    'InpIndicatorName': 'nadir2'}
        for key, value in required.items():
            self.assertEqual(overrides.get(key), value, key)
        default_magic = re.search(r'input\s+long\s+InpMagic\s*=\s*(\d+);', EA).group(1)
        self.assertNotEqual(overrides['InpMagic'], default_magic)
        self.assertGreater(int(overrides['InpHeartbeatSeconds']), 0)

    def test_invalid_direction_is_not_a_trade(self):
        poll = between(EA, 'void ProcessSignals()', 'string IndicatorIdentityLine()')
        guard = poll.index('g_dir[shift]!=1.0 && g_dir[shift]!=-1.0')
        self.assertLess(guard, poll.index('HandleSignal(s)'))
        invalid_branch = poll[guard:poll.index('int dir=', guard)]
        self.assertIn('continue;', invalid_branch)
        self.assertIn('g_invalid_buffer_signals++', invalid_branch)
        self.assertNotIn('MarkSeen(', invalid_branch)  # dir=0 maps to SELL in trade dedup
        self.assertNotIn('SeenBefore(', invalid_branch)

    def test_signal_age_and_series_mapping(self):
        poll = between(EA, 'void ProcessSignals()', 'string IndicatorIdentityLine()')
        for part in ('for(int shift=count-1;shift>=1;shift--)',
                     'if(shift>max_age)', 'g_expired++', 's.entry=g_entry[shift]',
                     's.sl=g_sl[shift]', 's.tp=PickTP(shift)'):
            self.assertIn(part, poll)
        for arr in ('g_dir', 'g_entry', 'g_sl', 'g_tp1', 'g_tp2', 'g_tp3'):
            self.assertIn(f'ArraySetAsSeries({arr},true)', EA)

    def test_retention_is_session_scoped(self):
        init = between(IND, 'void SigLog_Init()', 'bool SigLog_SeenHas(')
        self.assertIn('ArrayResize(g_sigbuf_time,0)', init)
        prepare = between(IND, 'void SigLog_PrepareBuffers(', 'string SigLog_FileName()')
        self.assertIn('prev_calculated>0', prepare)
        self.assertIn('ArrayInitialize(BufSigCoreDir,0.0)', prepare)
        self.assertIn('SigLog_FindBar(g_sigbuf_time[i],rates_total)', prepare)
        self.assertIn('SigLog_BufWrite(idx,g_sigbuf_src[i]', prepare)
        collect = between(IND, 'void SigLog_CollectCore(', 'void SigLog_CollectZRE(')
        self.assertIn('availability_time,rates_total)-1', collect)
        self.assertIn('if(InpExportSignalBuffers)', collect)

    def test_gate_source_order_and_reasons(self):
        setup = between(IND, 'void CalculateAITradeSetup(const int total,const double &o[],const double &h[],const double &l[],const double &c[])\n{', 'void ManageSetupLifecycle(')
        gates = ['SelectBestStructureAnchor(', 'TopDown_VetoesDirection(is_buy)',
                 'risk>atr*EffMaxStopATR()', 'conf<EffMinConfidenceScore()',
                 'rr1<EffMinRR1()', 'reliability<EffMinReliability()',
                 'CreateSetupBranchTransactional(']
        offsets = [setup.index(x) for x in gates]
        self.assertEqual(offsets, sorted(offsets))
        for reason in ('chain: structure event missing', 'chain: no displacement event',
                       'chain: no confirmed liquidity sweep', 'chain: no causal OB/FVG',
                       'topdown: ', 'score: confidence', 'score: reliability',
                       'geometry: RR1', 'causal branch rejected/rolled back'):
            self.assertIn(reason, IND)
        self.assertIn('TopDown_BlocksDirection(is_buy) && InpRequireInstitutionalConfirm', IND)

    @unittest.skip('Requires MetaEditor/MT5 and controlled closed-bar market data; source assertions do not prove publication')
    def test_actual_bull_bear_each_gate_publication_and_copybuffer(self):
        pass

    @unittest.skip('Requires MT5 to force partial history, reinitialization, refresh and verify actual buffers')
    def test_actual_readiness_retention_and_expiration(self):
        pass


if __name__ == '__main__':
    unittest.main(verbosity=2)
