"""Regresi audit 4 Nov 2026: latensi AI, overlay, sesi bocor, HTML log.

Jalankan: .venv\\Scripts\\python -m unittest tests.test_fixes -v
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import audio
import brain as brain_mod
import stt


class _FakeCompletions:
    def create(self, **kwargs):
        raise AssertionError("tidak dipakai")


class _FakeChat:
    completions = _FakeCompletions()


class FakeOpenAI:
    last_kwargs = None

    def __init__(self, **kwargs):
        FakeOpenAI.last_kwargs = kwargs
        self.chat = _FakeChat()


class ChatBrain(brain_mod.Brain):
    """Brain dengan chat() diganti perekam, tanpa jaringan."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, system, user):
        self.calls.append((system, user))
        return self.reply


class TestBrainFixes(unittest.TestCase):
    def test_client_timeout_dan_retry_terbatas(self):
        orig = brain_mod.OpenAI
        brain_mod.OpenAI = FakeOpenAI
        try:
            brain_mod.Brain({"model": "m", "base_url": "https://x"}, "tok")
        finally:
            brain_mod.OpenAI = orig
        self.assertEqual(FakeOpenAI.last_kwargs.get("timeout"), 60.0)
        self.assertEqual(FakeOpenAI.last_kwargs.get("max_retries"), 1)

    def test_translate_and_suggest_satu_panggilan(self):
        b = ChatBrain("TRANSLATION: Halo\nREPLY: Hi, nice to meet you\nMEANING: Halo, senang bertemu")
        hasil, saran = b.translate_and_suggest(
            "Hello", "interview", "Lawan: hi", "English", "Indonesian", ["Budi"])
        self.assertEqual(hasil, "Halo")
        self.assertEqual(saran, "Hi, nice to meet you\nHalo, senang bertemu")
        self.assertEqual(len(b.calls), 1)
        self.assertIn("Budi", b.calls[0][1])

    def test_suggest_label_generik(self):
        b = ChatBrain("REPLY: Bonjour\nMEANING: Halo")
        out = b.suggest("ctx", "hist", "Salut", "French", "Indonesian")
        self.assertEqual(out, "Bonjour\nHalo")

    def test_summarize_transkrip_panjang_bertahap(self):
        b = ChatBrain("RINGKASAN")
        panjang = "\n".join(f"[{i}] Lawan: kalimat nomor {i} yang cukup panjang" for i in range(400))
        out = b.summarize("ctx", panjang, "Indonesian")
        self.assertEqual(out, "RINGKASAN")
        self.assertGreater(len(b.calls), 1, "transkrip panjang harus diringkas bertahap, bukan satu panggilan raksasa")


class _Msg:
    content = "TRANSLATION: x\nREPLY: y\nMEANING: z"


class _Choice:
    message = _Msg()


class _Resp:
    choices = [_Choice()]


class _RecCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _Resp()


class RecOpenAI:
    last = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = type("C", (), {"completions": _RecCompletions()})()
        RecOpenAI.last = self


class TestTimeoutPerPanggilan(unittest.TestCase):
    def test_translate_timeout_pendek_gabungan_panjang(self):
        orig = brain_mod.OpenAI
        brain_mod.OpenAI = RecOpenAI
        try:
            b = brain_mod.Brain({"model": "m", "base_url": "https://x"}, "tok")
            b.translate("halo", "Indonesian", "English")
            kw_translate = RecOpenAI.last.chat.completions.kwargs
            b.translate_and_suggest("halo", "", "", "Indonesian", "English")
            kw_gabungan = RecOpenAI.last.chat.completions.kwargs
        finally:
            brain_mod.OpenAI = orig
        self.assertEqual(kw_translate.get("timeout"), 15.0)
        self.assertEqual(kw_gabungan.get("timeout"), 60.0)


class TestAudioError(unittest.TestCase):
    def test_capture_error_sampai_ke_callback(self):
        errors = []
        cap = audio.Capture(9999, on_error=errors.append)
        cap.start()
        cap.wait(timeout=5)
        cap.stop()
        self.assertTrue(errors, "error perangkat tidak diteruskan ke UI")


class TestSttReconnect(unittest.TestCase):
    def test_koneksi_ditutup_bersih_tetap_dilaporkan(self):
        attempts = {"n": 0}
        orig = stt.run_event_loop

        def clean_close(coro):
            coro.close()
            attempts["n"] += 1

        stt.run_event_loop = clean_close
        try:
            errors = []
            s = stt.RealtimeSTT("tok", None, ["English"], [], lambda t: None, lambda t: None, errors.append)
            s.run()
        finally:
            stt.run_event_loop = orig
        self.assertEqual(attempts["n"], 2, "tutup bersih harus reconnect sekali")
        self.assertTrue(errors, "tutup bersih permanen harus sampai ke UI")

    def test_stop_saat_backoff_tidak_menyambung_lagi(self):
        import threading as _t
        attempts = {"n": 0}
        orig = stt.run_event_loop

        def always_fail(coro):
            coro.close()
            attempts["n"] += 1
            raise RuntimeError("putus")

        stt.run_event_loop = always_fail
        try:
            s = stt.RealtimeSTT("tok", None, ["English"], [], lambda t: None, lambda t: None, lambda e: None)
            th = _t.Thread(target=s.run)
            th.start()
            time.sleep(0.2)
            s.stop()
            th.join(timeout=3)
        finally:
            stt.run_event_loop = orig
        self.assertFalse(th.is_alive())
        self.assertEqual(attempts["n"], 1, "setelah stop tidak boleh ada percobaan baru")

    def test_reconnect_sekali_saat_putus(self):
        attempts = {"n": 0}
        holder = []
        orig = stt.run_event_loop

        def flaky(coro):
            coro.close()
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("putus sesaat")
            holder[0].stop()  # percobaan kedua berjalan sampai pengguna berhenti

        stt.run_event_loop = flaky
        try:
            errors = []
            s = stt.RealtimeSTT("tok", None, ["English"], [], lambda t: None, lambda t: None, errors.append)
            holder.append(s)
            s.run()
        finally:
            stt.run_event_loop = orig
        self.assertEqual(attempts["n"], 2)
        self.assertEqual(errors, [])


# ---------- UI (Qt offscreen) ----------
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402


class CombinedBrain:
    def __init__(self):
        self.calls = []

    def translate_and_suggest(self, *args):
        self.calls.append(args)
        return "Halo terjemahan", "Jawaban saran\nArti saran"

    def translate(self, *args):
        raise AssertionError("mode percakapan tidak boleh memanggil translate terpisah")


class TestAppFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def _win(self):
        return appmod.MainWindow()

    def _pump_until(self, pred, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            self.qapp.processEvents()
            if pred():
                return True
            time.sleep(0.05)
        return pred()

    def test_interim_basi_dibuang(self):
        win = self._win()
        win._active = True
        win.on_partial("Lawan", "teks terbaru yang sedang diucapkan")
        win.on_interim("teks lama", "TERJEMAHAN LAMA")
        self.assertNotEqual(win.overlay.translated.text(), "TERJEMAHAN LAMA")

    def test_log_lolos_dari_html(self):
        win = self._win()
        win.on_translation("halo <b>semua</b>", "<i>terjemahan</i> & salam")
        self.assertIn("<i>terjemahan</i> & salam", win.log.toPlainText())

    def test_stop_menyembunyikan_overlay(self):
        win = self._win()
        win.overlay.show()
        self.qapp.processEvents()
        win.stop_streams()
        self.qapp.processEvents()
        self.assertFalse(win.overlay.isVisible())

    def test_mode_percakapan_satu_panggilan_gabungan(self):
        win = self._win()
        win.brain = CombinedBrain()
        win.cfg["mode"] = "conversation"
        win._active = True
        win.on_opponent("Hello there")
        ok = self._pump_until(lambda: "Jawaban saran" in win.overlay.suggested.text())
        self.assertTrue(ok, "saran gabungan tidak tampil")
        self.assertEqual(len(win.brain.calls), 1)
        self.assertIn("Halo terjemahan", win.log.toPlainText())
        win.stop_streams()

    def test_overlay_tumbuh_untuk_teks_panjang(self):
        ov = appmod.Overlay()
        awal = ov.height()
        ov.show_translated("kata bermakna " * 40)
        self.qapp.processEvents()
        self.assertGreater(ov.height(), awal)
        butuh = ov.translated.heightForWidth(ov.width())
        self.assertGreaterEqual(ov.height(), butuh, "teks panjang masih terpotong di bawah")

    def test_interim_awalan_masih_ditampilkan(self):
        win = self._win()
        win._active = True
        win.on_partial("Lawan", "hello how are you doing today")
        win.on_interim("hello how are", "HALO APA KABAR")
        self.assertEqual(win.overlay.translated.text(), "HALO APA KABAR")

    def test_final_terlambat_setelah_stop_dibuang(self):
        win = self._win()
        win.brain = CombinedBrain()
        win.on_opponent("FINAL TERLAMBAT")
        self.qapp.processEvents()
        self.assertEqual(win.session.turns, [])
        self.assertEqual(win.brain.calls, [])

    def test_ringkasan_lama_tidak_menimpa_yang_baru(self):
        class SlowBrain:
            def summarize(self, *a):
                time.sleep(0.6)
                return "RINGKASAN LAMA"

        class FastBrain:
            def summarize(self, *a):
                return "RINGKASAN BARU"

        win = self._win()
        win.session.add("Lawan", "halo")
        win.brain = SlowBrain()
        win.end_session()
        win.brain = FastBrain()
        win.end_session()
        self.assertTrue(self._pump_until(lambda: getattr(win, "_last_summary", "") == "RINGKASAN BARU"))
        time.sleep(0.8)
        self.qapp.processEvents()
        self.assertEqual(win._last_summary, "RINGKASAN BARU")

    def test_dialog_pengaturan_menulis_gerbang_dan_start_terkunci(self):
        import app as _app
        saved = {}
        orig_save, orig_test = _app.config.save, _app.brain_mod.test_connection
        orig_warn = _app.QMessageBox.warning
        _app.config.save = lambda cfg: saved.update(cfg)
        _app.brain_mod.test_connection = lambda cfg, tok: [("Model", True, "ok")]
        try:
            dlg = _app.SettingsDialog({"model": "muse-spark-1.3", "base_url": "https://x"}, None)
            dlg.run_test()
            self.assertTrue(self._pump_until(lambda: "✓" in dlg.result.toPlainText()))
            dlg.save()
            self.assertEqual(saved.get("tested_ok_for"), _app.test_fingerprint({"model": "muse-spark-1.3", "base_url": "https://x"}))
        finally:
            _app.config.save, _app.brain_mod.test_connection = orig_save, orig_test
        # Start terkunci tanpa gerbang
        win = self._win()
        win.cfg.pop("tested_ok_for", None)
        warnings = []
        orig_tok = _app.config.get_token
        _app.config.get_token = lambda: "tok"
        _app.QMessageBox.warning = staticmethod(lambda *a: warnings.append(a))
        try:
            win.start_session()
        finally:
            _app.config.get_token = orig_tok
            _app.QMessageBox.warning = orig_warn
        self.assertTrue(warnings)
        self.assertFalse(win._active)

    def test_ringkasan_bukan_modal(self):
        win = self._win()
        win.on_summary("Isi ringkasan sesi yang penting.")
        self.qapp.processEvents()
        dlg = getattr(win, "_summary_dialog", None)
        self.assertIsNotNone(dlg)
        self.assertTrue(dlg.isVisible())
        from PySide6.QtWidgets import QTextEdit as _TE
        box = dlg.findChild(_TE)
        self.assertIsNotNone(box)
        self.assertIn("Isi ringkasan sesi yang penting.", box.toPlainText())
        dlg.close()

    def test_status_privat_jujur_saat_sesi_mati(self):
        win = self._win()
        win.private_btn.setChecked(True)
        win.toggle_private()
        self.assertNotIn("mode privat berjalan", win.status_pill.text().lower())

    def test_gerbang_tes_koneksi(self):
        cfg = {"model": "m1", "base_url": "https://x"}
        self.assertFalse(appmod.is_tested(cfg))
        cfg["tested_ok_for"] = appmod.test_fingerprint(cfg)
        self.assertTrue(appmod.is_tested(cfg))
        cfg["model"] = "m2"
        self.assertFalse(appmod.is_tested(cfg), "ganti model harus menghanguskan tes lama")


if __name__ == "__main__":
    unittest.main()
