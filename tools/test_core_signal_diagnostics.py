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
        hb = between(EA, 'void DiagnosticHeartbeat()', 'void PrintEffectiveVsPreset()')
        for fragment in ('calc<look+1', '0,look+1,hb_dir', 'got<look+1',
                         'for(int i=1;i<=look;i++)', 'ArraySetAsSeries(hb_dir,true)'):
            self.assertIn(fragment, hb)
        self.assertIn('no zero-signal conclusion', hb)

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
