"""Lancarin - real-time conversation assistant (transcription, translation, AI suggestions)."""
import html
import sys
import threading
import time
from pathlib import Path

# stt is import-order proof (see lancarin/stt.py); the early import is only for clarity.
from lancarin import audio, config
from lancarin import brain as brain_mod
from lancarin.session import Session
from lancarin.settings_dialog import SettingsDialog
from lancarin.stt import RealtimeSTT
from lancarin.theme import QSS, _card, is_tested, test_fingerprint

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QComboBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QRadioButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

class Bridge(QObject):
    opponent_final = Signal(str)
    mine_final = Signal(str)
    partial = Signal(str, str)  # who, text
    interim_chunk = Signal(str, str)  # source prefix covered, translated chunk
    suggestion = Signal(str)
    translation = Signal(str, str)  # original, translated
    summary_ready = Signal(str)
    status = Signal(str)
    test_done = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lancarin - Conversation Assistant")
        self.setStyleSheet(QSS)
        _base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        logo = _base / "assets" / "lancarin.ico"
        if not logo.exists():
            logo = Path(__file__).parent / "assets" / "lancarin.ico"
        if logo.exists():
            self.setWindowIcon(QIcon(str(logo)))
        self.bridge = Bridge()
        self.cfg = config.load()
        self.session = Session()
        self.brain = None
        self.captures = []
        self.stts = []
        self._panel_font = 22
        self.private_mode = False
        self._gen = 0  # session generation: stale thread results are dropped
        self._keywords = []
        self._active = False
        self._partial = ""
        self._interim_busy = False
        self._interim_at = 0.0
        self._interim_snapshot = ""
        self._interim_done_source = ""
        self._interim_done_text = ""
        self._interim_chunk_busy = False

        header = QLabel("Lancarin")
        header.setStyleSheet("color:#ffffff;font-size:18px;font-weight:700;")
        _tok = config.get_token()
        _awal = (f"Token saved ({config.token_hint(_tok)}) - ready to start" if _tok
                 else "No token yet - open Settings & Test Connection")
        self.status_pill = QLabel("○ " + _awal)
        self.status_pill.setStyleSheet(
            "color:#cbd5e1;background:#1c2939;border:1px solid #2b3f58;"
            "border-radius:12px;padding:5px 12px;font-size:12px;")
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        self.settings_btn = settings_btn
        self.session_btn = QPushButton("Session ▾")
        self.session_btn.setCheckable(True)
        self.session_btn.clicked.connect(self.toggle_settings_panel)
        head_row = QHBoxLayout()
        head_row.addWidget(header)
        head_row.addWidget(self.status_pill)
        head_row.addStretch(1)
        head_row.addWidget(self.session_btn)
        head_row.addWidget(settings_btn)

        self.context_edit = QPlainTextEdit()
        self.context_edit.setPlaceholderText(
            "Context helps the AI suggest relevant replies. Example: Marketing job interview, I am the candidate. Optional.")
        self.context_edit.setMaximumHeight(44)
        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("Names or terms to recognize correctly (optional, comma-separated)")
        self.opp_lang = QComboBox(); self.opp_lang.addItems(config.LANGUAGES)
        self.opp_lang.setCurrentText(self.cfg["opponent_lang"])
        self.my_lang = QComboBox(); self.my_lang.addItems(config.LANGUAGES)
        self.my_lang.setCurrentText(self.cfg["my_lang"])
        self.mode_conversation = QRadioButton("Conversation (translation + reply suggestions)")
        self.mode_translate = QRadioButton("Translation only")
        if self.cfg["mode"] == "conversation":
            self.mode_conversation.setChecked(True)
        else:
            self.mode_translate.setChecked(True)
        card1, lay1 = _card("Session setup", "")
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Other party:"))
        lang_row.addWidget(self.opp_lang, 1)
        swap_btn = QPushButton("⇄ Swap")
        swap_btn.clicked.connect(self.swap_languages)
        lang_row.addWidget(swap_btn)
        lang_row.addWidget(QLabel("Me:"))
        lang_row.addWidget(self.my_lang, 1)
        lay1.addLayout(lang_row)
        self.lang_layout = lang_row
        lay1.addWidget(self.context_edit)
        lay1.addWidget(self.keywords_edit)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_conversation)
        mode_row.addWidget(self.mode_translate)
        mode_row.addStretch(1)
        lay1.addLayout(mode_row)

        self.start_btn = QPushButton("▶ Start Session")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start_session)
        self.stop_btn = QPushButton("■ End and Summarize")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.clicked.connect(self.end_session)
        self.stop_btn.setEnabled(False)
        self.private_btn = QPushButton("Private Speech Check (F9)")
        self.private_btn.setObjectName("privateBtn")
        self.private_btn.setCheckable(True)
        self.private_btn.clicked.connect(self.toggle_private)
        export_btn = QPushButton("Export Transcript (.md)")
        export_btn.clicked.connect(self.export_md)
        self.new_session_btn = QPushButton("New Session")
        self.new_session_btn.clicked.connect(self.new_session)
        self.summary_btn = QPushButton("View Summary")
        self.summary_btn.setEnabled(False)
        self.summary_btn.setToolTip("Available after a session summary has been created")
        self.summary_btn.clicked.connect(lambda: self.summary_card.show())
        self._sess_state = "idle"
        self.session_state = QLabel("")
        self.session_state.setStyleSheet(
            "color:#cbd5e1;background:#1c2939;border:1px solid #2b3f58;"
            "border-radius:9px;padding:4px 10px;font-size:12px;font-weight:600;")
        self._set_session_state("idle")
        action_row = QHBoxLayout()
        action_row.addWidget(self.start_btn, 2)
        action_row.addWidget(self.stop_btn, 2)
        self.action_layout = action_row
        util_row = QHBoxLayout()
        util_row.addWidget(self.private_btn)
        util_row.addWidget(self.new_session_btn)
        util_row.addWidget(self.summary_btn)
        util_row.addWidget(export_btn)
        util_row.addStretch(1)
        self.util_layout = util_row

        self.level_loop = QProgressBar(maximum=100)
        self.level_mic = QProgressBar(maximum=100)
        self.log = QTextEdit(readOnly=True)
        self.log.setPlaceholderText("The session transcript appears here…")
        self.log.document().setMaximumBlockCount(500)  # long sessions stay responsive
        card3, lay3 = _card("Live conversation", "Green bars mean audio is being captured. The panel shows what the other party says, a large translation, and a suggested reply.")
        meter_row = QHBoxLayout()
        meter_row.addWidget(QLabel("Other:"))
        meter_row.addWidget(self.level_loop, 1)
        meter_row.addWidget(QLabel("You:"))
        meter_row.addWidget(self.level_mic, 1)
        lay3.addLayout(meter_row)
        # Live panel (replaces the old overlay): process badge, suggestion, original, translation.
        self.panel_badge = QLabel("")
        self.panel_badge.setStyleSheet(
            "color:#5eead4;font-size:12px;font-weight:700;"
            "background:#0d3c37;padding:3px 9px;border-radius:6px;")
        self.panel_suggested = QLabel("")
        self.panel_suggested.setStyleSheet(
            "color:#fde68a;font-size:15px;background:#3c2a04;"
            "padding:7px 10px;border-radius:8px;")
        self.panel_original = QLabel("")
        self.panel_original.setStyleSheet(
            "color:#aebdd0;font-size:14px;background:#080c12;"
            "padding:6px 10px;border-radius:8px;")
        self.panel_translated = QLabel("")
        for lab in (self.panel_badge, self.panel_suggested, self.panel_original, self.panel_translated):
            lab.setWordWrap(True)
            lab.hide()
        self._apply_panel_font()
        self.btn_font_smaller = QPushButton("A−")
        self.btn_font_smaller.setToolTip("Smaller translation text")
        self.btn_font_smaller.clicked.connect(lambda: self._panel_zoom(-1))
        self.btn_font_bigger = QPushButton("A+")
        self.btn_font_bigger.setToolTip("Larger translation text")
        self.btn_font_bigger.clicked.connect(lambda: self._panel_zoom(1))
        panel_head = QHBoxLayout()
        panel_head.addWidget(self.panel_badge)
        panel_head.addStretch(1)
        panel_head.addWidget(self.btn_font_smaller)
        panel_head.addWidget(self.btn_font_bigger)
        lay3.addLayout(panel_head)
        for caption, lab in (("Original", self.panel_original),
                             ("Translation", self.panel_translated),
                             ("Suggested reply", self.panel_suggested)):
            cap = QLabel(caption)
            cap.setObjectName("hint")
            lay3.addWidget(cap)
            lay3.addWidget(lab)
        self.live_title = card3.title_label
        self.live_layout = lay3
        self.busy_bar = QProgressBar(minimum=0, maximum=0)  # spins while the AI works
        self.busy_bar.hide()
        lay3.addWidget(self.busy_bar)
        lay3.addWidget(self.log, 1)

        # Session summary as an in-app card (replaces the old popup).
        self.summary_card, sum_lay = _card("Session Summary", "")
        self.summary_text = QTextEdit(readOnly=True)
        self.summary_text.setMaximumHeight(260)
        sum_lay.addWidget(self.summary_text)
        sum_btns = QHBoxLayout()
        copy_btn = QPushButton("Copy Summary")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.summary_text.toPlainText()))
        export2_btn = QPushButton("Export Transcript (.md)")
        export2_btn.clicked.connect(self.export_md)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.summary_card.hide)
        sum_btns.addWidget(copy_btn)
        sum_btns.addWidget(export2_btn)
        sum_btns.addStretch(1)
        sum_btns.addWidget(close_btn)
        sum_lay.addLayout(sum_btns)
        self.summary_card.hide()

        # Session setup menu: context + languages + mode, collapsed by default
        # so the conversation panel gets the full space.
        self.settings_panel = QWidget()
        sp_lay = QVBoxLayout(self.settings_panel)
        sp_lay.setContentsMargins(0, 0, 0, 0)
        sp_lay.setSpacing(12)
        sp_lay.addWidget(card1)
        self.settings_panel.hide()

        root = QVBoxLayout()
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(8)
        root.addLayout(head_row)
        root.addWidget(self.session_state)
        root.addLayout(action_row)
        root.addLayout(util_row)
        root.addWidget(self.settings_panel)
        root.addWidget(card3, 1)
        root.addWidget(self.summary_card)
        central = QWidget(); central.setLayout(root)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(central)
        self.setCentralWidget(scroll)
        self.resize(760, 580)
        self.setMinimumSize(440, 460)
        self._wire()

    # ---------- signal wiring and status ----------
    def _wire(self):
        self.bridge.opponent_final.connect(self.on_opponent)
        self.bridge.mine_final.connect(self.on_mine)
        self.bridge.partial.connect(self.on_partial)
        self.bridge.interim_chunk.connect(self.on_interim_chunk)
        self.bridge.suggestion.connect(self.on_suggestion)
        self.bridge.translation.connect(self.on_translation)
        self.bridge.summary_ready.connect(self.on_summary)
        self.bridge.status.connect(self.set_status)
        self.bridge.status.connect(self._busy_watch)
        QShortcut(QKeySequence("F9"), self).activated.connect(self.private_btn.click)
        self.mode_conversation.toggled.connect(lambda _on: self.update_mode_label())
        self.mode_translate.toggled.connect(lambda _on: self.update_mode_label())
        self._meter_timer = QTimer(self)
        self._meter_timer.timeout.connect(self.tick_levels)
        self._meter_timer.start(200)
        self._interim_timer = QTimer(self)
        self._interim_timer.timeout.connect(self.maybe_interim)
        self._interim_timer.start(300)

    def update_mode_label(self):
        conversation = self.mode_conversation.isChecked()
        if hasattr(self, "live_title"):
            self.live_title.setText("Live Conversation" if conversation else "Live Translation")
        mode = ("Conversation (translation + reply suggestions)"
                if conversation else "Translation only")
        prefix = {"idle": "○ Not started", "live": "● LIVE",
                  "ending": "⏳ Ending - building summary"}.get(self._sess_state, "○ Not started")
        color = "#5eead4" if self._sess_state == "live" else "#cbd5e1"
        self.session_state.setStyleSheet(
            f"color:{color};background:#1c2939;border:1px solid #2b3f58;"
            "border-radius:9px;padding:4px 10px;font-size:12px;font-weight:600;")
        self.session_state.setText(f"{prefix}  ·  Mode: {mode}")

    def _set_session_state(self, state: str):
        self._sess_state = state
        locked = state != "idle"
        for w in (self.opp_lang, self.my_lang, self.context_edit, self.keywords_edit,
                  self.mode_conversation, self.mode_translate, self.settings_btn):
            w.setEnabled(not locked)  # changing setup mid-session has no effect; say so
        self.new_session_btn.setEnabled(not locked)
        self.summary_btn.setEnabled(not locked and bool(getattr(self, "_last_summary", "")))
        if state == "live":
            self.start_btn.setEnabled(False)
            self.start_btn.setText("● Session Running")
            self.start_btn.setToolTip("A session is already running")
            self.stop_btn.setEnabled(True)
            self.stop_btn.setToolTip("End the current session and build its summary")
        elif state == "ending":
            self.start_btn.setEnabled(False)
            self.start_btn.setText("⏳ Ending…")
            self.stop_btn.setEnabled(False)
            self.stop_btn.setToolTip("Finishing the summary…")
        else:
            self.start_btn.setEnabled(True)
            self.start_btn.setText("▶ Start Session")
            self.start_btn.setToolTip("")
            self.stop_btn.setEnabled(False)
            self.stop_btn.setToolTip("Start a session first - End is available while a session is running")
        self.update_mode_label()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 680
        arah = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        self.action_layout.setDirection(arah)
        self.util_layout.setDirection(arah)

    def new_session(self):
        if self._active:
            return
        if self.session.turns or getattr(self, "_last_summary", ""):
            answer = QMessageBox.question(
                self, "New Session",
                "Start a new session? The current transcript and summary will be cleared. "
                "Export the transcript first if you need to keep them.")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.session = Session(self.context_edit.toPlainText().strip())
        self._last_summary = ""
        self.summary_text.clear()
        self.summary_card.hide()
        self.summary_btn.setEnabled(False)
        self.log.clear()
        for lab in (self.panel_suggested, self.panel_original, self.panel_translated):
            lab.clear()
            lab.hide()
        self.panel_badge.hide()
        self._reset_interim()
        self._set_session_state("idle")
        self.set_status("Ready - new session. Adjust Session setup or press Start Session.")

    def toggle_settings_panel(self):
        show = self.session_btn.isChecked()
        self.settings_panel.setVisible(show)
        self.session_btn.setText("Session ▴" if show else "Session ▾")

    def swap_languages(self):
        opp, mine = self.opp_lang.currentText(), self.my_lang.currentText()
        self.opp_lang.setCurrentText(mine)
        self.my_lang.setCurrentText(opp)

    def _apply_panel_font(self):
        self.panel_translated.setStyleSheet(
            f"color:#ffffff;font-size:{self._panel_font}px;font-weight:600;"
            "background:#080c12;padding:8px 10px;border-radius:8px;")

    def _panel_zoom(self, arah: int):
        self._panel_font = max(14, min(38, self._panel_font + 2 * arah))
        self._apply_panel_font()

    def _panel_processing(self, text: str):
        self.panel_badge.setText(text)
        self.panel_badge.show()

    def _panel_show(self, label: QLabel, text: str):
        label.setText(text)
        label.setVisible(bool(text))

    def on_suggestion(self, text: str):
        self._panel_show(self.panel_suggested, text)
        self.panel_badge.hide()  # AI work for this turn is done

    def set_busy(self, on: bool, text: str = ""):
        self.busy_bar.setVisible(on)
        if text:
            self.set_status(text)

    def _busy_watch(self, text: str):
        if text.startswith("Summary failed"):
            self.set_busy(False)
            self._set_session_state("idle")

    def set_status(self, text: str):
        live = "live" in text.lower() or "PRIVATE" in text
        color = "#5eead4" if live else "#cbd5e1"
        bg = "#123b36" if live else "#1c2939"
        self.status_pill.setStyleSheet(
            f"color:{color};background:{bg};border:1px solid #2b3f58;"
            "border-radius:12px;padding:5px 12px;font-size:12px;")
        self.status_pill.setText(("● " if live else "○ ") + text)

    def tick_levels(self):
        if len(self.captures) == 2:
            self.level_loop.setValue(min(100, int(self.captures[0].level * 400)))
            self.level_mic.setValue(min(100, int(self.captures[1].level * 400)))

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            self.cfg = config.load()
            tok = config.get_token()
            self.set_status(
                f"Settings saved - token saved ({config.token_hint(tok)}), ready to start"
                if tok else "Settings saved - token is still empty")

    def toggle_private(self):
        self.private_mode = self.private_btn.isChecked()
        if self.private_mode and self._active:
            label_text = "PRIVATE mode is on: your speech is translated only here. Keep your Zoom/Meet mic muted."
        elif self.private_mode:
            label_text = "Private check ready - it applies while a session is live. Keep your Zoom/Meet mic muted."
        else:
            label_text = "Ready - private check off"
        self.set_status(label_text)

    # ---------- interim translation (while the other party is still speaking) ----------
    def _reset_interim(self):
        self._interim_snapshot = ""
        self._interim_done_source = ""
        self._interim_done_text = ""
        self._interim_chunk_busy = False

    @staticmethod
    def _take_chunk(pending: str):
        """Cut the next translatable chunk: a sentence/clause, never the whole transcript."""
        if len(pending) < 24:
            return "", 0
        limit = 140 if len(pending) > 220 else 60
        window = pending[:limit]
        cut = max(window.rfind(mark) for mark in ".?!;,")
        if cut >= 18:
            return pending[:cut + 1].strip(), cut + 1
        if len(pending) <= limit:
            return pending.strip(), len(pending)
        space = window.rfind(" ")
        return (pending[:space].strip(), space) if space >= 18 else ("", 0)

    def maybe_interim(self):
        # Translate only the newest chunk of the cumulative partial and append
        # it. Re-translating the whole partial makes every call slower as the
        # sentence grows, so during continuous speech nothing ever arrives.
        if not self._active or not self.brain or self._interim_chunk_busy:
            return
        text = self._partial.strip()
        if not text:
            return
        if not text.startswith(self._interim_done_source):
            self._interim_done_source, self._interim_done_text = "", ""  # STT revised earlier words
        pending = text[len(self._interim_done_source):].lstrip()
        base = text[:len(text) - len(pending)] if pending else text
        segment, cut = self._take_chunk(pending)
        if not segment:
            return
        self._interim_chunk_busy = True
        self._interim_at = time.time()
        source_upto = text[:len(text) - len(pending) + cut]
        brain, opp, mine = self.brain, self.cfg["opponent_lang"], self.cfg["my_lang"]

        def work():
            try:
                result = brain.translate(segment, opp, mine)
                self.bridge.interim_chunk.emit(source_upto, result)
            except Exception:
                self.bridge.interim_chunk.emit(source_upto, "")  # GUI thread clears the busy flag

        threading.Thread(target=work, daemon=True).start()

    def on_interim_chunk(self, source_upto: str, translated: str):
        self._interim_chunk_busy = False
        if not self._active or not translated.strip():
            return
        if not self._partial.startswith(source_upto):
            return  # stale: the transcript moved on or was revised
        if self._interim_done_source and not source_upto.startswith(self._interim_done_source):
            return  # an older chunk finishing out of order
        self._interim_done_source = source_upto
        self._interim_done_text = (self._interim_done_text + " " + translated.strip()).strip()
        self._panel_show(self.panel_translated, self._interim_done_text)

    # ---------- session lifecycle ----------
    def start_session(self):
        token = config.get_token()
        if not token:
            QMessageBox.warning(self, "Lancarin", "Your Meta token is empty. Open Settings first.")
            return
        if self.opp_lang.currentText() == self.my_lang.currentText():
            QMessageBox.warning(self, "Lancarin",
                                "Both languages are the same, so there is nothing to translate. "
                                "Pick a different pair or use Swap.")
            return
        if not is_tested(self.cfg):
            QMessageBox.warning(self, "Lancarin",
                                "The connection test has not passed for these model settings yet. "
                                "Open Settings, run Test Connection until every line shows a checkmark, then Save.")
            return
        mode = "conversation" if self.mode_conversation.isChecked() else "translate"
        self.cfg.update({"opponent_lang": self.opp_lang.currentText(),
                         "my_lang": self.my_lang.currentText(), "mode": mode})
        config.save(self.cfg)
        self.set_busy(True, "Starting session - connecting audio & transcription…")
        QApplication.processEvents()
        self.brain = brain_mod.Brain(self.cfg, token)
        self.session = Session(self.context_edit.toPlainText().strip())
        keywords = [k.strip() for k in self.keywords_edit.text().split(",") if k.strip()]
        self._keywords = keywords
        loop_i, mic_i, _ = audio.list_devices()
        if loop_i is None or mic_i is None:
            self.set_busy(False)
            QMessageBox.warning(self, "Lancarin", f"Audio devices incomplete: system audio={loop_i}, microphone={mic_i}")
            return
        self._gen += 1
        self.captures = [
            audio.Capture(loop_i, on_error=lambda e: self.bridge.status.emit("System audio problem: " + e)),
            audio.Capture(mic_i, on_error=lambda e: self.bridge.status.emit("Microphone problem: " + e)),
        ]
        for cap in self.captures:
            cap.start()
        opp, mine = self.cfg["opponent_lang"], self.cfg["my_lang"]
        self.stts = [
            RealtimeSTT(token, self.captures[0].frames, [opp, mine], keywords,
                        lambda t: self.bridge.partial.emit("Other", t),
                        lambda t: self.bridge.opponent_final.emit(t),
                        lambda e: self.bridge.status.emit("Other-party transcription problem: " + e)),
            RealtimeSTT(token, self.captures[1].frames, [mine, opp], keywords,
                        lambda t: self.bridge.partial.emit("You", t),
                        lambda t: self.bridge.mine_final.emit(t),
                        lambda e: self.bridge.status.emit("Your transcription problem: " + e)),
        ]
        for s in self.stts:
            s.start()
        self._active = True
        self._partial = ""
        self._reset_interim()
        self._set_session_state("live")
        self.set_busy(False)
        self.set_status(f"Session live - translating {opp} → {mine}")

    def on_partial(self, who, text):
        if not self._active:
            return
        if who == "Other" and text:
            self._partial = text
            self._panel_processing("● OTHER PARTY SPEAKING…")
            self._panel_show(self.panel_original, text)

    def on_opponent(self, text):
        if not self._active:
            return  # late final from a previous session's stream
        self._partial = ""
        self._reset_interim()
        self.panel_badge.hide()
        opp, mine = self.cfg["opponent_lang"], self.cfg["my_lang"]
        turn = self.session.add("Other", text)
        self.log.append(f"<b>Other:</b> {html.escape(text)}")
        self._panel_show(self.panel_original, text)
        brain, session = self.brain, self.session
        gen = self._gen
        mode = self.cfg["mode"]
        history = session.history_text()
        self._panel_processing("⏳ Translating…")

        # Translation and suggestion run in parallel: the translation (fast
        # model) appears first, the suggestion follows. They used to be one
        # combined call, so translation waited for the suggestion (5-10s).
        def work_translate():
            try:
                translated = brain.translate(text, opp, mine)
                if gen != self._gen:
                    return
                turn.translation = translated
                self.bridge.translation.emit(text, translated)
            except Exception as exc:
                if gen == self._gen:
                    self.bridge.status.emit("AI problem: " + str(exc)[:160])

        threading.Thread(target=work_translate, daemon=True).start()
        if mode == "conversation":
            def work_suggest():
                try:
                    suggestion = brain.suggest(session.context_desc, history, text, opp, mine, list(self._keywords))
                    if gen == self._gen and suggestion.strip():
                        self.bridge.suggestion.emit("Suggested reply: " + suggestion.replace("\n", "   ·   "))
                except Exception as exc:
                    if gen == self._gen:
                        self.bridge.status.emit("Suggestion problem: " + str(exc)[:160])

            threading.Thread(target=work_suggest, daemon=True).start()

    def on_mine(self, text):
        if not self._active:
            return
        self.session.add("You", text)
        label = "You (private): " if self.private_mode else "You: "
        self.log.append(f"<b>{label}</b> {html.escape(text)}")
        if self.private_mode and self.brain:
            brain, opp, mine = self.brain, self.cfg["opponent_lang"], self.cfg["my_lang"]
            gen = self._gen

            def work():
                try:
                    result = brain.translate(text, mine, opp)
                    if gen == self._gen:
                        self.bridge.suggestion.emit(f"Your speech in {opp}: " + result)
                except Exception as exc:
                    if gen == self._gen:
                        self.bridge.status.emit("AI problem: " + str(exc)[:160])

            threading.Thread(target=work, daemon=True).start()

    def on_translation(self, original, translated):
        if not translated.strip():
            self.panel_badge.hide()
            self.set_status("The AI returned an empty translation - check the model/token in Settings")
            self.log.append("<i>→ (empty from AI)</i>")
            return
        self._panel_show(self.panel_translated, translated)
        if self.cfg["mode"] == "conversation":
            self._panel_processing("⏳ Translation shown - preparing a suggestion…")
        else:
            self.panel_badge.hide()
        self.log.append(f"<i>→ {html.escape(translated)}</i>")

    def stop_streams(self):
        self._active = False
        self._gen += 1  # every thread result from this session is now stale
        for s in self.stts:
            s.stop()
        for c in self.captures:
            c.stop()
        for s in self.stts:
            s.join(timeout=2)
        for c in self.captures:
            c.wait(timeout=2)
        self.stts, self.captures = [], []
        self.panel_badge.hide()

    def end_session(self):
        # Tell the user first, then work: stopping streams can take seconds
        # and without this the app looks frozen with no explanation.
        self.set_busy(True, "Ending session - stopping audio, then building your summary…")
        self._set_session_state("ending")
        self._panel_processing("⏳ Ending session…")
        QApplication.processEvents()
        self.stop_streams()
        self._end_gen = self._gen
        if not self.brain or not self.session.turns:
            self.set_busy(False)
            self._set_session_state("idle")
            self.set_status("Session ended - no conversation was recorded yet")
            return
        self.set_busy(True, "Ending session - building summary (usually 10-20 seconds)…")
        brain, session, mine = self.brain, self.session, self.cfg["my_lang"]
        end_gen = self._gen

        def work():
            try:
                summary = brain.summarize(session.context_desc, session.transcript_text(), mine)
                if end_gen == self._gen:  # drop before emitting, not after being overwritten
                    self.bridge.summary_ready.emit(summary)
            except Exception as exc:
                if end_gen == self._gen:
                    self.bridge.status.emit("Summary failed: " + str(exc)[:160])

        threading.Thread(target=work, daemon=True).start()

    def on_summary(self, summary):
        if getattr(self, "_end_gen", self._gen) != self._gen:
            return  # summary of an old session; a new one is already running
        self.set_busy(False)
        self._set_session_state("idle")
        if not summary.strip():
            self.set_status("The AI returned an empty summary - your transcript can still be exported")
            QMessageBox.warning(self, "Session Summary",
                                "The AI returned an empty summary. Your full transcript is still "
                                "kept in this session - use Export Transcript (.md).")
            return
        self._last_summary = summary
        self.summary_btn.setEnabled(True)
        self.summary_btn.setToolTip("Show the session summary again")
        # In-app summary card with rendered sections and copy/export actions.
        self.summary_text.setMarkdown(summary)
        self.summary_card.show()
        self.set_status("Summary ready - copy it or export the full transcript below")

    def export_md(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Transcript", "lancarin-session.md", "Markdown (*.md)")
        if path:
            md = self.session.export_md(getattr(self, "_last_summary", ""))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(md)
            self.set_status("Transcript saved: " + path)


def main():
    if sys.platform == "win32":
        # So the taskbar uses the Lancarin logo instead of the generic/python.exe icon.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lancarin.App.1")
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()





