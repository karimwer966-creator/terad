"""Regression contracts for per-configuration diagnostic identities."""
from pathlib import Path
import subprocess
r=Path(__file__).resolve().parents[1]
s=(r/'nadir2.mq5').read_text();ea=(r/'MQL5/Experts/QSMC_AutoTrader.mq5').read_text()
assert 'QA_InstanceDiagPrefix()' in s,'diagnostics still shared by different input sets'
assert 'QSMC_DefaultDiagPrefix' in ea,'EA diagnostic reader does not bind to default iCustom config'
assert 'iCustom(_Symbol,_Period,InpIndicatorName);' in ea,'buffer instance contract changed'
assert 'INSTANCE MISMATCH' in (r/'MQL5/Include/QSMC/QSMC_InstanceIdentity.mqh').read_text()
subprocess.run(['python',str(r/'tools/generate_input_fingerprint.py'),'--check'],check=True)
print('PASS per-config diagnostics, default-instance binding and exhaustive input manifest')
