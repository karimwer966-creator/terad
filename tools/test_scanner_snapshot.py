"""Regression: rendered table and counters must describe the same completed pass."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'MQL5/Indicators/QSMC_ScannerProbe.mq5'
s=p.read_text().split('void OnTimer()',1)[1]
assert s.index('g_setup.BeginPass();')>s.index('Comment(txt);'), 'completed rows cleared before counters: stale list / zero counters'
print('PASS completed scanner snapshot is rendered before reset')
