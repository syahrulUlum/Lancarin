"""Lancarin — asisten percakapan real-time (transkripsi, terjemahan, saran AI)."""
import html
import sys
import threading
import time
from pathlib import Path

# stt kebal urutan impor (lihat stt.py); impor awal di sini hanya kejelasan.
import audio
import brain as brain_mod
import config
from session import Session
from stt import RealtimeSTT

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QRadioButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

QSS = """
QMainWindow, QDialog { background: #0f141b; }
QLabel { color: #dbe4ee; font-size: 13px; }
QLabel#stepTitle { color: #ffffff; font-size: 15px; font-weight: 600; }
QLabel#hint { color: #8494a7; font-size: 12px; }
QFrame#card { background: #171f2a; border: 1px solid #263242; border-radius: 10px; }
QLineEdit, QPlainTextEdit, QComboBox, QTextEdit {
    background: #101820; color: #e8eef4; border: 1px solid #2b3a4d;
    border-radius: 8px; padding: 7px 9px; font-size: 13px;
}
QComboBox::drop-down { border: none; width: 22px; }
QRadioButton { color: #dbe4ee; font-size: 13px; spacing: 6px; }
QPushButton {
    background: #223146; color: #e8eef4; border: 1px solid #31445e;
    border-radius: 8px; padding: 8px 14px; font-size: 13px;
}
QPushButton:hover { background: #2a3d59; }
QPushButton#primary {
    background: #0d9488; border-color: #0d9488; color: #ffffff;
    font-size: 17px; font-weight: 700; padding: 14px;
}
QPushButton#primary:hover { background: #0fae9f; }
QPushButton#danger {
    background: #b91c1c; border-color: #b91c1c; color: #ffffff;
    font-size: 15px; font-weight: 700; padding: 12px;
}
QPushButton:disabled { background: #1a2432; color: #5c6d80; border-color: #223146; }
QPushButton#privateBtn:checked { background: #92400e; border-color: #d97706; color: #fff7ed; }
QProgressBar { background: #101820; border: 1px solid #2b3a4d; border-radius: 5px; height: 10px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #0d9488; border-radius: 4px; }
"""


def test_fingerprint(cfg: dict) -> str:
    return f"{cfg.get('model', '')}|{cfg.get('translate_model', '')}|{cfg.get('base_url', '')}"


def is_tested(cfg: dict) -> bool:
    return bool(cfg.get("tested_ok_for")) and cfg["tested_ok_for"] == test_fingerprint(cfg)


class Bridge(QObject):
    opponent_final = Signal(str)
    mine_final = Signal(str)
    partial = Signal(str, str)  # who, text
    interim = Signal(str, str)  # snapshot asli, terjemahan sementara
    suggestion = Signal(str)
    translation = Signal(str, str)  # original, translated
    summary_ready = Signal(str)
    status = Signal(str)
    test_done = Signal(str)


class SettingsDialog(QDialog):
    result_ready = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.test_ok = False
        self._tested_for = ""
        self._test_ran = False
        self.setWindowTitle("Lancarin Settings")
        self.setStyleSheet(QSS)
        self.resize(480, 420)
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token = config.get_token()
        self.token_edit.setPlaceholderText(config.token_hint(token) + " - paste a new token to replace it")
        self.model_box = QComboBox()
        self.model_box.addItems(config.MODELS)
        self.model_box.setCurrentText(cfg["model"])
        self.translate_model_box = QComboBox()
        self.translate_model_box.addItems(config.MODELS)
        self.translate_model_box.setCurrentText(cfg.get("translate_model") or config.DEFAULTS["translate_model"])
        self.base_edit = QLineEdit(cfg["base_url"])
        self.advanced_check = QCheckBox("Advanced")
        self.advanced_check.toggled.connect(lambda on: self.advanced_box.setVisible(on))
        self.advanced_box = QWidget()
        adv_lay = QVBoxLayout(self.advanced_box)
        adv_lay.setContentsMargins(0, 0, 0, 0)
        adv_lay.addWidget(QLabel("Base URL (leave as the Meta default unless you use a proxy):"))
        adv_lay.addWidget(self.base_edit)
        self.advanced_box.hide()
        self.result = QTextEdit(readOnly=True)
        self.result.setPlaceholderText("Connection test results appear here. Each selected model is tested separately.")
        self.result.setMaximumHeight(120)
        self.result_ready.connect(self.result.setPlainText)
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self.run_test)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self._save_btn = save_btn
        self.result_ready.connect(lambda _t: self._save_btn.setEnabled(True))
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        title = QLabel("Settings"); title.setObjectName("stepTitle")
        lay.addWidget(title)
        lay.addWidget(QLabel("Meta Model API token (stored securely in your OS keychain; get one at dev.meta.ai):"))
        lay.addWidget(self.token_edit)
        models = QHBoxLayout()
        left = QVBoxLayout(); left.addWidget(QLabel("Translation model:")); left.addWidget(self.translate_model_box)
        right = QVBoxLayout(); right.addWidget(QLabel("Suggestions & summary:")); right.addWidget(self.model_box)
        models.addLayout(left, 1); models.addLayout(right, 1)
        lay.addLayout(models)
        hint = QLabel("Translation runs live, so a fast model matters most there (muse-wonder-1.0 measured fastest). Suggestions and summaries benefit from a stronger reasoning model.")
        hint.setObjectName("hint"); hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addWidget(self.advanced_check)
        lay.addWidget(self.advanced_box)
        lay.addWidget(test_btn)
        lay.addWidget(self.result)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1); btn_row.addWidget(cancel_btn); btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)

    def current_cfg(self):
        cfg = dict(self.cfg)
        cfg["model"] = self.model_box.currentText()
        cfg["translate_model"] = self.translate_model_box.currentText()
        cfg["base_url"] = self.base_edit.text().strip() or config.DEFAULTS["base_url"]
        return cfg

    def run_test(self):
        self._save_btn.setEnabled(False)  # do not save while the test is running
        self.result.setPlainText("Testing each model and your audio devices…")
        token = self.token_edit.text().strip() or config.get_token()
        cfg = self.current_cfg()

        def work():
            lines = []
            brain_steps = brain_mod.test_connection(cfg, token)
            self._test_ran = True
            self.test_ok = bool(brain_steps) and all(ok for _, ok, _ in brain_steps)
            self._tested_for = test_fingerprint(cfg) if self.test_ok else ""
            for name, ok, msg in brain_steps:
                lines.append(("✓ " if ok else "✗ ") + name + ": " + msg)
            try:
                loop_i, mic_i, _ = audio.list_devices()
                ok = loop_i is not None and mic_i is not None
                lines.append(("✓ " if ok else "✗ ") + f"Audio devices: system audio (other party)={loop_i}, microphone (you)={mic_i}")
            except Exception as exc:
                lines.append("✗ Audio devices: " + str(exc)[:120])
            self.result_ready.emit("\n".join(lines))

        threading.Thread(target=work, daemon=True).start()

    def save(self):
        token = self.token_edit.text().strip()
        if token:
            config.set_token(token)
        cfg = self.current_cfg()
        if self.test_ok and self._tested_for == test_fingerprint(cfg):
            cfg["tested_ok_for"] = self._tested_for
        elif self._test_ran:
            cfg.pop("tested_ok_for", None)  # tes ulang gagal: gerbang lama hangus
        config.save(cfg)
        self.accept()


def _card(title: str, hint: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    t = QLabel(title)
    t.setObjectName("stepTitle")
    lay.addWidget(t)
    if hint:
        h = QLabel(hint)
        h.setObjectName("hint")
        h.setWordWrap(True)
        lay.addWidget(h)
    return frame, lay


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lancarin - Conversation Assistant")
        self.setStyleSheet(QSS)
        _base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        logo = _base / "assets" / "lancarin.png"
        if not logo.exists():
            logo = Path(__file__).parent / "assets" / "lancarin.png"
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

        header = QLabel("Lancarin")
        header.setStyleSheet("color:#ffffff;font-size:22px;font-weight:700;")
        _tok = config.get_token()
        _awal = (f"Token saved ({config.token_hint(_tok)}) - ready to start" if _tok
                 else "No token yet - open Settings & Test Connection")
        self.status_pill = QLabel("○ " + _awal)
        self.status_pill.setStyleSheet(
            "color:#cbd5e1;background:#1c2939;border:1px solid #2b3f58;"
            "border-radius:12px;padding:5px 12px;font-size:12px;")
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
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
        self.stop_btn = QPushButton("■ End & Summarize")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.clicked.connect(self.end_session)
        self.stop_btn.setEnabled(False)
        self.private_btn = QPushButton("Private Speech Check (F9)")
        self.private_btn.setObjectName("privateBtn")
        self.private_btn.setCheckable(True)
        self.private_btn.clicked.connect(self.toggle_private)
        export_btn = QPushButton("Export Transcript (.md)")
        export_btn.clicked.connect(self.export_md)
        action_row = QHBoxLayout()
        action_row.addWidget(self.start_btn, 2)
        action_row.addWidget(self.stop_btn, 2)
        util_row = QHBoxLayout()
        util_row.addWidget(self.private_btn)
        util_row.addWidget(export_btn)
        util_row.addStretch(1)

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
        # Panel langsung pengganti overlay: lencana proses, saran, asli, terjemahan.
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
        lay3.addWidget(self.panel_suggested)
        lay3.addWidget(self.panel_original)
        lay3.addWidget(self.panel_translated)
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

        # Menu pengaturan sesi: konteks + bahasa + mode, terlipat bawaan agar
        # kotak percakapan mendapat ruang penuh.
        self.settings_panel = QWidget()
        sp_lay = QVBoxLayout(self.settings_panel)
        sp_lay.setContentsMargins(0, 0, 0, 0)
        sp_lay.setSpacing(12)
        sp_lay.addWidget(card1)
        self.settings_panel.hide()

        root = QVBoxLayout()
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)
        root.addLayout(head_row)
        root.addLayout(action_row)
        root.addLayout(util_row)
        root.addWidget(self.settings_panel)
        root.addWidget(card3, 1)
        root.addWidget(self.summary_card)
        central = QWidget(); central.setLayout(root)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(central)
        self.setCentralWidget(scroll)
        self.resize(1080, 880)
        self.setMinimumSize(860, 640)
        self._wire()

    # ---------- kabel sinyal & status ----------
    def _wire(self):
        self.bridge.opponent_final.connect(self.on_opponent)
        self.bridge.mine_final.connect(self.on_mine)
        self.bridge.partial.connect(self.on_partial)
        self.bridge.interim.connect(self.on_interim)
        self.bridge.suggestion.connect(self.on_suggestion)
        self.bridge.translation.connect(self.on_translation)
        self.bridge.summary_ready.connect(self.on_summary)
        self.bridge.status.connect(self.set_status)
        self.bridge.status.connect(self._busy_watch)
        QShortcut(QKeySequence("F9"), self).activated.connect(self.private_btn.click)
        self._meter_timer = QTimer(self)
        self._meter_timer.timeout.connect(self.tick_levels)
        self._meter_timer.start(200)
        self._interim_timer = QTimer(self)
        self._interim_timer.timeout.connect(self.maybe_interim)
        self._interim_timer.start(300)

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
        self.panel_badge.hide()  # proses AI untuk giliran ini selesai

    def set_busy(self, on: bool, text: str = ""):
        self.busy_bar.setVisible(on)
        if text:
            self.set_status(text)

    def _busy_watch(self, text: str):
        if text.startswith("Summary failed"):
            self.set_busy(False)
            self.start_btn.setEnabled(True)

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
            teks = "PRIVATE mode is on: your speech is translated only here. Keep your Zoom/Meet mic muted."
        elif self.private_mode:
            teks = "Private check ready - it applies while a session is live. Keep your Zoom/Meet mic muted."
        else:
            teks = "Ready - private check off"
        self.set_status(teks)

    # ---------- terjemahan interim (sambil lawan masih bicara) ----------
    def maybe_interim(self):
        # Latest-wins: jangan antri di belakang panggilan lambat. Panggilan
        # baru boleh jalan paralel; hanya hasil dari snapshot terakhir yang
        # ditampilkan (lihat on_interim).
        if not self._active or not self.brain:
            return
        text = self._partial.strip()
        if len(text) < 3 or text == self._interim_snapshot:
            return
        if time.time() - self._interim_at < 0.8:
            return
        if len(text) - len(self._interim_snapshot) < 4 and self._interim_snapshot:
            return
        self._interim_at = time.time()
        self._interim_snapshot = text
        brain, opp, mine = self.brain, self.cfg["opponent_lang"], self.cfg["my_lang"]

        def work():
            try:
                hasil = brain.translate(text, opp, mine)
                self.bridge.interim.emit(text, hasil)
            except Exception:
                self.bridge.interim.emit(text, "")  # reset flag lewat thread GUI

        threading.Thread(target=work, daemon=True).start()

    def on_interim(self, snapshot: str, translated: str):
        self._interim_busy = False
        # Hanya snapshot terakhir yang boleh tampil; hasil panggilan lama yang
        # selesai belakangan dibuang agar overlay tidak mundur.
        if snapshot != self._interim_snapshot:
            return
        if snapshot != self._partial and not self._partial.startswith(snapshot):
            return
        if self._active and translated.strip():
            self._panel_show(self.panel_translated, translated)

    # ---------- siklus sesi ----------
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
        self._interim_snapshot = ""
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
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
            return  # final terlambat dari stream sesi lama
        self._partial = ""
        self._interim_snapshot = ""
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

        # Terjemahan dan saran jalan paralel: terjemahan (model cepat) tampil
        # duluan, saran menyusul. Dulu keduanya digabung satu panggilan
        # sehingga terjemahan ikut menunggu saran selesai (5-10 detik).
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
                    saran = brain.suggest(session.context_desc, history, text, opp, mine, list(self._keywords))
                    if gen == self._gen and saran.strip():
                        self.bridge.suggestion.emit("Suggested reply: " + saran.replace("\n", "   ·   "))
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
                    hasil = brain.translate(text, mine, opp)
                    if gen == self._gen:
                        self.bridge.suggestion.emit(f"Your speech in {opp}: " + hasil)
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
        self._gen += 1  # semua hasil thread sesi ini jadi basi
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
        # Kabari dulu, baru bekerja: menghentikan stream bisa makan detik dan
        # tanpa ini aplikasi terlihat membeku tanpa penjelasan.
        self.set_busy(True, "Ending session - stopping audio, then building your summary…")
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self._panel_processing("⏳ Ending session…")
        QApplication.processEvents()
        self.stop_streams()
        self._end_gen = self._gen
        if not self.brain or not self.session.turns:
            self.set_busy(False)
            self.start_btn.setEnabled(True)
            self.set_status("Session ended - no conversation was recorded yet")
            return
        self.set_busy(True, "Ending session - building summary (usually 10-20 seconds)…")
        brain, session, mine = self.brain, self.session, self.cfg["my_lang"]
        end_gen = self._gen

        def work():
            try:
                summary = brain.summarize(session.context_desc, session.transcript_text(), mine)
                if end_gen == self._gen:  # buang sebelum emit, bukan sesudah ditimpa
                    self.bridge.summary_ready.emit(summary)
            except Exception as exc:
                if end_gen == self._gen:
                    self.bridge.status.emit("Summary failed: " + str(exc)[:160])

        threading.Thread(target=work, daemon=True).start()

    def on_summary(self, summary):
        if getattr(self, "_end_gen", self._gen) != self._gen:
            return  # ringkasan sesi lama, sesi baru sudah berjalan
        self.set_busy(False)
        self.start_btn.setEnabled(True)
        if not summary.strip():
            self.set_status("The AI returned an empty summary - your transcript can still be exported")
            QMessageBox.warning(self, "Session Summary",
                                "The AI returned an empty summary. Your full transcript is still "
                                "kept in this session - use Export Transcript (.md).")
            return
        self._last_summary = summary
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
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()





