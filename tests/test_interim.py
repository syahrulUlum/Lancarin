"""Latency regression: interim translation appears from the partial transcript,
tanpa menunggu giliran bicara selesai (final).

Jalankan: .venv\\Scripts\\python -m unittest tests.test_interim -v
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import app as appmod


class FakeBrain:
    def __init__(self):
        self.calls = []

    def translate(self, text, src, dst):
        self.calls.append(text)
        return "TERJEMAHAN:" + text


class TestInterim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def test_interim_updates_panel_without_final(self):
        win = appmod.MainWindow()
        win.brain = FakeBrain()
        win._active = True
        win.on_partial("Other", "Hello how are you today my good friend")
        win._interim_at = 0.0
        win.maybe_interim()
        for _ in range(50):
            self.qapp.processEvents()
            if win.panel_translated.text():
                break
            time.sleep(0.1)
        self.assertTrue(win.brain.calls, "interim translate was never called")
        self.assertIn("TERJEMAHAN:", win.panel_translated.text())
        win.stop_streams()


if __name__ == "__main__":
    unittest.main()
