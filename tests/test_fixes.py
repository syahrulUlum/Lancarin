"""Regression tests from the Nov 4 2026 audit: AI latency, overlay removal, session leaks, HTML log.

Jalankan: .venv\\Scripts\\python -m unittest tests.test_fixes -v
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lancarin import audio
from lancarin import brain as brain_mod
from lancarin import stt


class _FakeCompletions:
    def create(self, **kwargs):
        raise AssertionError("unused")


class _FakeChat:
    completions = _FakeCompletions()


class FakeOpenAI:
    last_kwargs = None

    def __init__(self, **kwargs):
        FakeOpenAI.last_kwargs = kwargs
        self.chat = _FakeChat()


class ChatBrain(brain_mod.Brain):
    """Brain with chat() replaced by a recorder; no network."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append((system, user))
        return self.reply


class TestBrainFixes(unittest.TestCase):
    def test_client_timeout_and_limited_retries(self):
        orig = brain_mod.OpenAI
        brain_mod.OpenAI = FakeOpenAI
        try:
            brain_mod.Brain({"model": "m", "base_url": "https://x"}, "tok")
        finally:
            brain_mod.OpenAI = orig
        self.assertEqual(FakeOpenAI.last_kwargs.get("timeout"), 60.0)
        self.assertEqual(FakeOpenAI.last_kwargs.get("max_retries"), 1)

    def test_suggest_generic_labels(self):
        b = ChatBrain("REPLY: Bonjour\nMEANING: Halo")
        out = b.suggest("ctx", "hist", "Salut", "French", "Indonesian")
        self.assertEqual(out, [("Bonjour", "Halo")])

    def test_suggest_up_to_three_options(self):
        b = ChatBrain("REPLY1: Yes, sounds good\nMEANING1: Ya, kedengarannya bagus\n"
                      "REPLY2: Could you repeat that?\nMEANING2: Bisa diulang?\n"
                      "REPLY3: Let me think about it\nMEANING3: Saya pikirkan dulu")
        out = b.suggest("ctx", "hist", "Shall we proceed?", "English", "Indonesian")
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0], ("Yes, sounds good", "Ya, kedengarannya bagus"))
        self.assertEqual(out[2][0], "Let me think about it")

    def test_summarize_long_transcript_in_chunks(self):
        b = ChatBrain("RINGKASAN")
        panjang = "\n".join(f"[{i}] Other: sentence number {i} that is long enough" for i in range(400))
        out = b.summarize("ctx", panjang, "Indonesian")
        self.assertEqual(out, "RINGKASAN")
        self.assertGreater(len(b.calls), 1, "a long transcript must be summarized in chunks, not one giant call")


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
    def test_translate_uses_selected_fast_model_and_short_timeout(self):
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
                         "translation must use the translation model selected by the user in Settings")
        self.assertEqual(kw_chat.get("model"), "muse-spark-1.3")


class TestAudioError(unittest.TestCase):
    def test_capture_error_reaches_callback(self):
        errors = []
        cap = audio.Capture(9999, on_error=errors.append)
        cap.start()
        cap.wait(timeout=5)
        cap.stop()
        self.assertTrue(errors, "device error was not forwarded to the UI")


class TestSttReconnect(unittest.TestCase):
    def test_clean_close_is_reconnected_then_reported(self):
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
        self.assertEqual(attempts["n"], 2, "a clean close must reconnect once")
        self.assertTrue(errors, "a permanent clean close must reach the UI")

    def test_stop_during_backoff_does_not_reconnect(self):
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
        self.assertEqual(attempts["n"], 1, "no new attempt is allowed after stop")

    def test_reconnects_once_after_drop(self):
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
    """fast translate, slow suggest: the translation must appear first."""

    def __init__(self):
        self.calls = []
        self.suggest_calls = []

    def translate(self, *args):
        self.calls.append(args)
        return "Translated hello"

    def suggest(self, *args):
        self.suggest_calls.append(args)
        time.sleep(0.8)
        return [("Suggested answer", "Its meaning")]


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

    def test_interim_chunk_from_stale_source_is_dropped(self):
        win = self._win()
        win._active = True
        win.on_partial("Other", "the newest words being spoken right now")
        win.on_interim_chunk("old source", "STALE TRANSLATION")
        self.assertNotEqual(win.panel_translated.text(), "STALE TRANSLATION")

    def test_log_escapes_html(self):
        win = self._win()
        win.on_translation("hello <b>everyone</b>", "<i>translation</i> & greetings")
        self.assertIn("<i>translation</i> & greetings", win.log.toPlainText())

    def test_stop_keeps_refs_to_threads_still_alive(self):
        class StubStt:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

            def join(self, timeout=None):
                pass

            def is_alive(self):
                return True  # join timeout: koneksi lama belum benar-benar mati

        win = self._win()
        stub = StubStt()
        win.stts = [stub]
        win.stop_streams()
        self.assertEqual(win.stts, [stub],
                         "refs to a still-alive STT thread must be kept so the next start can close it instead of duplicating it")

    def test_stop_clears_panel(self):
        win = self._win()
        win._active = True
        win.on_partial("Other", "halo")
        win.stop_streams()
        self.qapp.processEvents()
        self.assertTrue(win.panel_badge.isHidden())

    def test_translation_appears_before_suggestion(self):
        win = self._win()
        win.brain = CombinedBrain()
        win.cfg["mode"] = "conversation"
        win._active = True
        win.on_opponent("Hello there")
        ok = self._pump_until(lambda: win.panel_translated.text() == "Translated hello", timeout=0.5)
        self.assertTrue(ok, "translation did not appear first (still waiting for the suggestion)")
        self.assertTrue(self._pump_until(lambda: "Suggested answer" in win.suggestion_plain_text()))
        self.assertEqual(len(win.brain.calls), 1)
        self.assertEqual(len(win.brain.suggest_calls), 1)
        win.stop_streams()

    def test_no_overlay_and_panel_font_buttons(self):
        win = self._win()
        self.assertFalse(hasattr(win, "overlay"), "the overlay must be gone")
        font = win._panel_font
        win.btn_font_bigger.click()
        self.assertGreater(win._panel_font, font)
        win.btn_font_smaller.click()
        self.assertEqual(win._panel_font, font)

    def test_session_setup_menu_collapses(self):
        win = self._win()
        self.assertTrue(win.settings_panel.isHidden(), "session setup must be collapsed by default")
        win.session_btn.click()
        self.qapp.processEvents()
        self.assertFalse(win.settings_panel.isHidden())
        win.session_btn.click()
        self.assertTrue(win.settings_panel.isHidden())

    def test_end_session_shows_progress(self):
        class SlowBrain:
            def summarize(self, *a):
                time.sleep(1.2)
                return "Finished summary"

        win = self._win()
        win.show()
        win.session.add("Other", "halo dunia")
        win.brain = SlowBrain()
        win.end_session()
        self.assertTrue(win.busy_bar.isVisible(), "no progress indicator while ending the session")
        self.assertFalse(win.start_btn.isEnabled(), "Start must stay locked while the summary is built")
        self.assertIn("Ending", win.status_pill.text())
        self.assertTrue(self._pump_until(lambda: getattr(win, "_last_summary", "") == "Finished summary"))
        self.assertFalse(win.busy_bar.isVisible())
        self.assertTrue(win.start_btn.isEnabled())

    def test_interim_translates_only_new_chunks(self):
        class ChunkBrain:
            def __init__(self):
                self.calls = []

            def translate(self, text, src, dst):
                self.calls.append(text)
                return "T[" + text + "]"

        win = self._win()
        win.brain = ChunkBrain()
        win._active = True
        win.on_partial("Other", "hello how are you doing today")
        win.maybe_interim()
        self.assertTrue(self._pump_until(lambda: "T[" in win.panel_translated.text()))
        first_call = win.brain.calls[0]
        win.on_partial("Other", "hello how are you doing today, and how is your family")
        win._interim_at = 0.0
        win.maybe_interim()
        self.assertTrue(self._pump_until(lambda: win.panel_translated.text().count("T[") >= 2))
        self.assertEqual(len(win.brain.calls), 2)
        self.assertNotIn(first_call.strip(), win.brain.calls[1],
                         "second interim call must translate only the new chunk, not the whole transcript")
        self.assertIn("family", win.brain.calls[1])
        win.stop_streams()

    def test_new_session_clears_and_summary_can_reopen(self):
        win = self._win()
        win.show()
        win.session.add("Other", "hello")
        win.log.append("<b>Other:</b> hello")
        win.on_summary("A summary worth keeping.")
        self.assertTrue(win.summary_btn.isEnabled())
        win.summary_card.hide()
        win.summary_btn.click()
        self.qapp.processEvents()
        self.assertTrue(win.summary_card.isVisible(), "a closed summary must be reopenable")
        orig_question = appmod.QMessageBox.question
        appmod.QMessageBox.question = staticmethod(lambda *a: appmod.QMessageBox.StandardButton.Yes)
        try:
            win.new_session()
        finally:
            appmod.QMessageBox.question = orig_question
        self.assertEqual(win.session.turns, [])
        self.assertEqual(win.log.toPlainText(), "")
        self.assertTrue(win.summary_card.isHidden())
        self.assertFalse(win.summary_btn.isEnabled())

    def test_late_final_after_stop_is_dropped(self):
        win = self._win()
        win.brain = CombinedBrain()
        win.on_opponent("FINAL TERLAMBAT")
        self.qapp.processEvents()
        self.assertEqual(win.session.turns, [])
        self.assertEqual(win.brain.calls, [])

    def test_old_summary_does_not_overwrite_new(self):
        class SlowBrain:
            def summarize(self, *a):
                time.sleep(0.6)
                return "RINGKASAN LAMA"

        class FastBrain:
            def summarize(self, *a):
                return "RINGKASAN BARU"

        win = self._win()
        win.session.add("Other", "halo")
        win.brain = SlowBrain()
        win.end_session()
        win.brain = FastBrain()
        win.end_session()
        self.assertTrue(self._pump_until(lambda: getattr(win, "_last_summary", "") == "RINGKASAN BARU"))
        time.sleep(0.8)
        self.qapp.processEvents()
        self.assertEqual(win._last_summary, "RINGKASAN BARU")

    def test_settings_dialog_writes_gate_and_start_is_locked(self):
        import app as _app
        saved = {}
        orig_save, orig_test = _app.config.save, _app.brain_mod.test_connection
        orig_dg = _app.config.get_deepgram_key
        orig_check = stt.check_key
        orig_warn = _app.QMessageBox.warning
        _app.config.save = lambda cfg: saved.update(cfg)
        _app.config.get_deepgram_key = lambda: "dg-key"
        stt.check_key = lambda key: (True, "ok")
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
            _app.config.get_deepgram_key = orig_dg
            stt.check_key = orig_check
        # Start terkunci tanpa gerbang
        win = self._win()
        win.cfg.pop("tested_ok_for", None)
        warnings = []
        orig_brain, orig_dg2 = _app.config.get_brain_key, _app.config.get_deepgram_key
        _app.config.get_brain_key = lambda: "tok"
        _app.config.get_deepgram_key = lambda: "dg"
        _app.QMessageBox.warning = staticmethod(lambda *a: warnings.append(a))
        try:
            win.start_session()
        finally:
            _app.config.get_brain_key, _app.config.get_deepgram_key = orig_brain, orig_dg2
            _app.QMessageBox.warning = orig_warn
        self.assertTrue(warnings)
        self.assertFalse(win._active)

    def test_summary_is_an_in_app_card(self):
        win = self._win()
        win.show()
        win.on_summary("Important session summary contents.")
        self.qapp.processEvents()
        self.assertTrue(win.summary_card.isVisible(), "summary must appear as an in-app card, not a popup")
        self.assertIn("Important session summary contents.", win.summary_text.toPlainText())
        self.assertIsNone(getattr(win, "_summary_dialog", None))

    def test_private_translation_is_recorded_not_in_suggestion(self):
        class TranslateBrain:
            def translate(self, text, src, dst):
                return "How was your day?"

        win = self._win()
        win.brain = TranslateBrain()
        win.private_mode = True
        win._active = True
        win.on_mine("Bagaimana harimu?")
        self.assertTrue(self._pump_until(lambda: "How was your day?" in win.log.toPlainText()),
                        "private translation must be written to the transcript log")
        self.assertEqual(win.session.turns[-1].translation, "How was your day?")
        self.assertIn("How was your day?", win.panel_translated.text())
        self.assertNotIn("How was your day?", win.panel_suggested.text())
        win.stop_streams()

    def test_three_suggestion_options_render_and_copy(self):
        win = self._win()
        win.on_suggestion([("Yes, that works", "Ya, bisa"),
                           ("Could you repeat?", "Bisa diulang?"),
                           ("Let me check first", "Saya cek dulu")])
        self.assertEqual(len(win._option_buttons), 3)
        self.assertIn("Could you repeat?", win.suggestion_plain_text())
        self.assertIn("Bisa diulang?", win.suggestion_plain_text())
        win._option_buttons[0].click()
        from PySide6.QtWidgets import QApplication as _QA
        self.assertEqual(_QA.clipboard().text(), "Yes, that works")

    def test_panel_font_is_unified_and_persisted(self):
        saved = {}
        orig_save = appmod.config.save
        appmod.config.save = lambda cfg: saved.update(cfg)
        try:
            win = self._win()
            win.btn_font_bigger.click()
        finally:
            appmod.config.save = orig_save
        self.assertEqual(saved.get("panel_font"), win._panel_font)
        self.assertIn(f"font-size:{win._panel_font}px", win.panel_original.styleSheet())
        self.assertIn(f"font-size:{win._panel_font}px", win.panel_translated.styleSheet())

    def test_suggestion_failure_is_visible_in_panel(self):
        class FailBrain:
            def translate(self, text, src, dst):
                return "Terjemahan"

            def suggest(self, *args):
                raise RuntimeError("429 rate limited")

        win = self._win()
        win.brain = FailBrain()
        win.cfg["mode"] = "conversation"
        win._active = True
        win.on_opponent("How was your day today?")
        self.assertTrue(self._pump_until(lambda: "failed" in win.panel_suggested.text().lower()),
                        "a failed suggestion must be explained in the suggestion panel, not only the status pill")
        win.stop_streams()

    def test_private_status_is_honest_when_idle(self):
        win = self._win()
        win.private_btn.setChecked(True)
        win.toggle_private()
        self.assertNotIn("private check is on:", win.status_pill.text().lower())

    def test_connection_test_gate(self):
        cfg = {"model": "m1", "base_url": "https://x"}
        self.assertFalse(appmod.is_tested(cfg))
        cfg["tested_ok_for"] = appmod.test_fingerprint(cfg)
        self.assertTrue(appmod.is_tested(cfg))
        cfg["model"] = "m2"
        self.assertFalse(appmod.is_tested(cfg), "changing the model must invalidate the old test")


class TestEnglishAndSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def test_main_ui_is_english(self):
        win = appmod.MainWindow()
        self.assertEqual(win.start_btn.text(), "▶ Start")
        self.assertEqual(win.stop_btn.text(), "■ End")
        self.assertNotIn("&", win.stop_btn.text(), "& di Qt membuat garis bawah mnemonic")
        self.assertTrue(win.session_btn.text().startswith("Session"))
        self.assertNotIn("Mulai", win.start_btn.text())

    def test_settings_dialog_shows_deepgram_and_brain_fields(self):
        dlg = appmod.SettingsDialog({"model": "openai/gpt-oss-120b", "translate_model": "openai/gpt-oss-20b",
                                     "base_url": "https://api.groq.com/openai/v1"}, None)
        self.assertEqual(dlg.windowTitle(), "Lancarin Settings")
        # Semua kolom brain tampil langsung: ganti provider/model tidak perlu update aplikasi.
        self.assertEqual(dlg.base_edit.text(), "https://api.groq.com/openai/v1")
        self.assertEqual(dlg.model_edit.text(), "openai/gpt-oss-120b")
        self.assertEqual(dlg.translate_model_edit.text(), "openai/gpt-oss-20b")
        self.assertIsNotNone(dlg.deepgram_edit)
        self.assertIsNotNone(dlg.brain_key_edit)
        cfg = dlg.current_cfg()
        self.assertEqual(cfg["base_url"], "https://api.groq.com/openai/v1")

    def test_connection_test_covers_both_models(self):
        class FakeBrain:
            seen = []

            def __init__(self, cfg, token):
                self.model = cfg["model"]
                FakeBrain.seen.append(self.model)

            def chat(self, system, user, timeout=60.0, model=None):
                return "OK"

        orig = brain_mod.Brain
        brain_mod.Brain = FakeBrain
        try:
            steps = brain_mod.test_connection(
                {"model": "muse-spark-1.3", "translate_model": "muse-wonder-1.0",
                 "base_url": "https://x"}, "tok")
        finally:
            brain_mod.Brain = orig
        names = " | ".join(n for n, _, _ in steps)
        self.assertIn("muse-wonder-1.0", names)
        self.assertIn("muse-spark-1.3", names)
        self.assertTrue(all(ok for _, ok, _ in steps))

    def test_logo_exists_and_is_window_icon(self):
        from pathlib import Path
        aset = Path(appmod.__file__).parent / "assets"
        self.assertTrue((aset / "lancarin.png").exists())
        self.assertTrue((aset / "lancarin.ico").exists())
        win = appmod.MainWindow()
        self.assertFalse(win.windowIcon().isNull(), "the window icon must be the Lancarin logo")


class TestCompactAndState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def test_window_is_compact(self):
        win = appmod.MainWindow()
        self.assertLessEqual(win.width(), 820, "the default window must be compact (<=820px, <50% of a Full HD screen)")
        self.assertLessEqual(win.height(), 620)
        self.assertLessEqual(win.minimumWidth(), 680)

    def test_button_states_and_mode_are_clear(self):
        win = appmod.MainWindow()
        self.assertTrue(win.start_btn.isEnabled())
        self.assertFalse(win.stop_btn.isEnabled())
        self.assertIn("Not started", win.session_state.text())
        win.mode_conversation.setChecked(True)
        win.update_mode_label()
        self.assertIn("Conversation", win.session_state.text())
        win._set_session_state("live")
        self.assertFalse(win.start_btn.isEnabled())
        self.assertIn("Running", win.start_btn.text())
        self.assertTrue(win.stop_btn.isEnabled())
        self.assertIn("LIVE", win.session_state.text())
        win.mode_translate.setChecked(True)
        win.update_mode_label()
        self.assertIn("Translation only", win.session_state.text())
        win._set_session_state("ending")
        self.assertFalse(win.start_btn.isEnabled())
        self.assertFalse(win.stop_btn.isEnabled())
        win._set_session_state("idle")
        self.assertTrue(win.start_btn.isEnabled())
        self.assertEqual(win.start_btn.text(), "▶ Start")


class TestStatePolish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def test_disabled_buttons_explain_themselves(self):
        win = appmod.MainWindow()
        self.assertIn("Start a session first", win.stop_btn.toolTip())
        win._set_session_state("live")
        self.assertIn("End the current session", win.stop_btn.toolTip())
        self.assertIn("already running", win.start_btn.toolTip())

    def test_card_title_follows_mode(self):
        win = appmod.MainWindow()
        win.mode_translate.setChecked(True)
        win.update_mode_label()
        self.assertEqual(win.live_title.text(), "Live Translation")
        win.mode_conversation.setChecked(True)
        win.update_mode_label()
        self.assertEqual(win.live_title.text(), "Live Conversation")

    def test_panel_order_original_translation_suggestion(self):
        win = appmod.MainWindow()
        lay = win.live_layout
        self.assertLess(lay.indexOf(win.panel_original), lay.indexOf(win.panel_translated))
        self.assertLess(lay.indexOf(win.panel_translated), lay.indexOf(win.panel_suggested))

    def test_window_narrows_and_layout_adapts(self):
        win = appmod.MainWindow()
        self.assertLessEqual(win.minimumWidth(), 480)
        win.resize(500, 600)
        win.show()
        self.qapp.processEvents()
        from PySide6.QtWidgets import QBoxLayout
        # Tombol tetap sebaris ramping di jendela sempit, bukan ditumpuk 6 baris.
        self.assertEqual(win.action_layout.direction(), QBoxLayout.Direction.LeftToRight)
        self.assertEqual(win.util_layout.direction(), QBoxLayout.Direction.LeftToRight)
        self.assertTrue(win.mode_conversation.isVisible(),
                        "mode selector must stay visible even with the Session panel collapsed")

    def test_setup_is_locked_while_live(self):
        win = appmod.MainWindow()
        win._set_session_state("live")
        self.assertFalse(win.opp_lang.isEnabled())
        self.assertFalse(win.settings_btn.isEnabled())
        win._set_session_state("idle")
        self.assertTrue(win.opp_lang.isEnabled())


if __name__ == "__main__":
    unittest.main()
