#!/usr/bin/env python3
"""Regression checks for MetaEditor-reported QATS errors; not an MQL compiler."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "MQL5/Experts/QuantumAutonomousTradingSystem.mq5"
VERIFIER = ROOT / "tools/verify_quantum_ea.py"


class QuantumCompileRegressions(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")

    def verify(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.mq5"
            path.write_text(text, encoding="utf-8")
            return subprocess.run([sys.executable, str(VERIFIER), str(path)],
                                  cwd=ROOT, text=True, capture_output=True)

    def test_current_source_passes(self):
        result = self.verify(self.source)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_free_static_functions_are_rejected(self):
        for name in ("IsTransientRetcode", "IsSuccessRetcode"):
            original = "bool " + name + "("
            self.assertEqual(self.source.count(original), 1)
            result = self.verify(self.source.replace(original, "static " + original))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("global function cannot be declared static", result.stdout)

    def test_integer_accessor_for_volume_limit_is_rejected(self):
        original = "SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT)"
        self.assertEqual(self.source.count(original), 1)
        result = self.verify(self.source.replace(original, "SymbolInfoInteger(_Symbol, SYMBOL_VOLUME_LIMIT)"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SYMBOL_VOLUME_LIMIT must be read with SymbolInfoDouble", result.stdout)

    def test_fractional_limit_remains_double_and_is_used_without_integer_cast(self):
        self.assertIn("double volLimit;", self.source)
        self.assertIn("MathFloor(g_spec.volLimit / g_spec.volStep) * g_spec.volStep", self.source)
        self.assertIn("limit=%.8f", self.source)
        result = self.verify(self.source.replace("double volLimit;", "long   volLimit;"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("volLimit must retain fractional lots as a double", result.stdout)


if __name__ == "__main__":
    unittest.main()
