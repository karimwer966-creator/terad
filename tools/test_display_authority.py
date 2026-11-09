"""Non-Core wording, expiry-before-cache, shared buffer-derived status contract."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=(r/'nadir2.mq5').read_text();h=(r/'MQL5/Include/QSMC/QSMC_IncidentSafety.mqh').read_text()
assert 'TACTICAL TOUCH (not an entry)' in s,'tactical label still synthesizes ENTRY + CONFIRMED'
assert 'QA_CoreDisplayRefresh(closed)' in s and 'QA_CoreStatus()' in s,'panel not using published buffer snapshot'
assert 'BufSigCoreDir[closed]' in h and 'QA_CoreStatus()' in h,'shared chart/panel state missing'
a=s.index('void RXN_Draw()\n');part=s[a:]
assert part.index('QA_LabelAlive(')<part.index('if(sig==g_rxn_draw_sig'),'expiry bypassed by draw signature cache'
assert 'QA_LabelAlive(trigger,trigger,trigger_time' in s
assert 'REACTION CONFIRMED (not an entry)' in s
print('PASS non-Core vocabulary, shared Core state and advisory expiry wiring')
