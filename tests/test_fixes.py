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
    def test_translate_model_cepat_dan_timeout_pendek(self):
        orig = brain_mod.OpenAI
        brain_mod.OpenAI = RecOpenAI
        try:
            b = brain_mod.Brain({"model": "muse-spark-1.3", "translate_model": "muse-spark-1.2",
                                 "base_url": "https://x"}, "tok")
            b.translate("halo", "Indonesian", "English")
            kw = RecOpenAI.last.chat.completions.kwargs
            b.chat("sys", "usr")  # jalur saran/ringkasan tetap model pilihan
            kw_chat = RecOpenAI.last.chat.completions.kwargs
        finally:
            brain_mod.OpenAI = orig
        self.assertEqual(kw.get("timeout"), 15.0)
        self.assertEqual(kw.get("model"), "muse-spark-1.2",
                         "terjemahan harus memakai model terjemahan pilihan pengguna di Pengaturan")
        self.assertEqual(kw_chat.get("model"), "muse-spark-1.3")


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
    """translate cepat, suggest lambat: terjemahan harus tampil duluan."""

    def __init__(self):
        self.calls = []
        self.suggest_calls = []

    def translate(self, *args):
        self.calls.append(args)
        return "Halo terjemahan"

    def suggest(self, *args):
        self.suggest_calls.append(args)
        time.sleep(0.8)
        return "Jawaban saran\nArti saran"


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
        self.assertNotEqual(win.panel_translated.text(), "TERJEMAHAN LAMA")

    def test_log_lolos_dari_html(self):
        win = self._win()
        win.on_translation("halo <b>semua</b>", "<i>terjemahan</i> & salam")
        self.assertIn("<i>terjemahan</i> & salam", win.log.toPlainText())

    def test_stop_membersihkan_panel(self):
        win = self._win()
        win._active = True
        win.on_partial("Lawan", "halo")
        win.stop_streams()
        self.qapp.processEvents()
        self.assertTrue(win.panel_badge.isHidden())

    def test_terjemahan_tampil_sebelum_saran_selesai(self):
        win = self._win()
        win.brain = CombinedBrain()
        win.cfg["mode"] = "conversation"
        win._active = True
        win.on_opponent("Hello there")
        ok = self._pump_until(lambda: win.panel_translated.text() == "Halo terjemahan", timeout=0.5)
        self.assertTrue(ok, "terjemahan tidak tampil duluan (masih menunggu saran)")
        self.assertTrue(self._pump_until(lambda: "Jawaban saran" in win.panel_suggested.text()))
        self.assertEqual(len(win.brain.calls), 1)
        self.assertEqual(len(win.brain.suggest_calls), 1)
        win.stop_streams()

    def test_tidak_ada_overlay_dan_font_panel_bisa_diubah(self):
        win = self._win()
        self.assertFalse(hasattr(win, "overlay"), "overlay harus sudah dihapus")
        font = win._panel_font
        win.btn_font_bigger.click()
        self.assertGreater(win._panel_font, font)
        win.btn_font_smaller.click()
        self.assertEqual(win._panel_font, font)

    def test_menu_pengaturan_sesi_bisa_diciutkan(self):
        win = self._win()
        self.assertTrue(win.settings_panel.isHidden(), "pengaturan sesi harus terlipat secara bawaan")
        win.session_btn.click()
        self.qapp.processEvents()
        self.assertFalse(win.settings_panel.isHidden())
        win.session_btn.click()
        self.assertTrue(win.settings_panel.isHidden())

    def test_akhiri_sesi_ada_indikator_proses(self):
        class SlowBrain:
            def summarize(self, *a):
                time.sleep(1.2)
                return "Ringkasan jadi"

        win = self._win()
        win.show()
        win.session.add("Lawan", "halo dunia")
        win.brain = SlowBrain()
        win.end_session()
        self.assertTrue(win.busy_bar.isVisible(), "tidak ada indikator saat mengakhiri sesi")
        self.assertFalse(win.start_btn.isEnabled(), "tombol Mulai harus terkunci selama ringkasan diproses")
        self.assertIn("Mengakhiri", win.status_pill.text())
        self.assertTrue(self._pump_until(lambda: getattr(win, "_last_summary", "") == "Ringkasan jadi"))
        self.assertFalse(win.busy_bar.isVisible())
        self.assertTrue(win.start_btn.isEnabled())

    def test_interim_tidak_terserial_di_belakang_panggilan_lambat(self):
        class SlowBrain:
            def __init__(self):
                self.calls = []

            def translate(self, text, src, dst):
                self.calls.append(text)
                time.sleep(0.6)
                return "T:" + text

        win = self._win()
        win.brain = SlowBrain()
        win._active = True
        win.on_partial("Lawan", "hello how are")
        win._interim_at = 0.0
        win.maybe_interim()
        win.on_partial("Lawan", "hello how are you doing today my friend")
        win._interim_at = 0.0
        win.maybe_interim()
        self.assertEqual(len(win.brain.calls), 2,
                         "interim kedua harus jalan paralel (latest-wins), bukan menunggu yang pertama")
        self.assertTrue(self._pump_until(
            lambda: win.panel_translated.text() == "T:hello how are you doing today my friend"))
        win.stop_streams()

    def test_panel_terjemahan_teks_panjang_terlihat(self):
        win = self._win()
        win.panel_translated.setText("kata bermakna " * 40)
        win.panel_translated.show()
        self.qapp.processEvents()
        self.assertIn("kata bermakna", win.panel_translated.text())

    def test_interim_awalan_masih_ditampilkan(self):
        win = self._win()
        win._active = True
        win.on_partial("Lawan", "hello how are you doing today")
        win._interim_snapshot = "hello how are"
        win.on_interim("hello how are", "HALO APA KABAR")
        self.assertEqual(win.panel_translated.text(), "HALO APA KABAR")

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
            dlg = _app.SettingsDialog({"model": "muse-spark-1.3", "translate_model": "muse-wonder-1.0",
                                       "base_url": "https://x"}, None)
            dlg.run_test()
            self.assertTrue(self._pump_until(lambda: "✓" in dlg.result.toPlainText()))
            dlg.save()
            self.assertEqual(saved.get("translate_model"), "muse-wonder-1.0")
            self.assertEqual(saved.get("tested_ok_for"), _app.test_fingerprint(
                {"model": "muse-spark-1.3", "translate_model": "muse-wonder-1.0", "base_url": "https://x"}))
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
