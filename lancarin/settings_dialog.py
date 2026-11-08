"""Settings dialog: Deepgram STT key + OpenAI-compatible brain, connection test."""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QTextEdit, QVBoxLayout)

from . import audio
from . import brain as brain_mod
from . import config
from . import stt as stt_mod
from .theme import QSS, test_fingerprint


def _section(title: str) -> QLabel:
    label = QLabel(title)
    label.setObjectName("stepTitle")
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


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
        self.resize(520, 560)

        # --- Speech-to-text (Deepgram) ---
        self.deepgram_edit = QLineEdit()
        self.deepgram_edit.setEchoMode(QLineEdit.EchoMode.Password)
        dg_key = config.get_deepgram_key()
        self.deepgram_edit.setPlaceholderText(
            config.token_hint(dg_key) + " - paste a new key to replace it")

        # --- Brain (OpenAI-compatible) ---
        self.brain_key_edit = QLineEdit()
        self.brain_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        brain_key = config.get_brain_key()
        self.brain_key_edit.setPlaceholderText(
            config.token_hint(brain_key) + " - paste a new key to replace it")
        self.base_edit = QLineEdit(cfg.get("base_url") or config.DEFAULTS["base_url"])
        self.base_edit.setPlaceholderText("https://api.groq.com/openai/v1")
        self.translate_model_edit = QLineEdit(
            cfg.get("translate_model") or cfg.get("model") or config.DEFAULTS["translate_model"])
        self.translate_model_edit.setPlaceholderText("openai/gpt-oss-20b")
        self.model_edit = QLineEdit(cfg.get("model") or config.DEFAULTS["model"])
        self.model_edit.setPlaceholderText("openai/gpt-oss-120b")

        self.result = QTextEdit(readOnly=True)
        self.result.setPlaceholderText(
            "Connection test results appear here. Each brain model is tested separately.")
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
        title = QLabel("Settings")
        title.setObjectName("stepTitle")
        lay.addWidget(title)

        lay.addWidget(_section("1 · Speech-to-text — Deepgram"))
        lay.addWidget(QLabel(f"Model: Deepgram {config.STT_MODEL} Multilingual (streaming, fixed)"))
        lay.addWidget(QLabel("Deepgram API key (stored securely in your OS keychain; get one at deepgram.com):"))
        lay.addWidget(self.deepgram_edit)
        lay.addWidget(_hint(
            "Handles live transcription only. Interim text streams while the other party "
            "speaks; no audio is sent anywhere else."))

        lay.addWidget(_section("2 · Brain — translation, suggestions, summary"))
        lay.addWidget(QLabel("Base URL (OpenAI-compatible endpoint):"))
        lay.addWidget(self.base_edit)
        lay.addWidget(QLabel("Brain API key for that endpoint (stored securely in your OS keychain):"))
        lay.addWidget(self.brain_key_edit)
        models = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Translation model (fast):"))
        left.addWidget(self.translate_model_edit)
        right = QVBoxLayout()
        right.addWidget(QLabel("Suggestions & summary model:"))
        right.addWidget(self.model_edit)
        models.addLayout(left, 1)
        models.addLayout(right, 1)
        lay.addLayout(models)
        lay.addWidget(_hint(
            "OpenAI-compatible providers only: the endpoint must support the OpenAI "
            "Chat Completions API (/v1/chat/completions) — e.g. Groq "
            "(https://api.groq.com/openai/v1), OpenAI (https://api.openai.com/v1), "
            "OpenRouter, or Cerebras. Type any model name the provider offers; "
            "translation runs live, so pick a fast model there. Model names are free "
            "text, so changing models later needs no app update."))

        lay.addWidget(test_btn)
        lay.addWidget(self.result)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)

    def current_cfg(self):
        cfg = dict(self.cfg)
        cfg["model"] = self.model_edit.text().strip() or config.DEFAULTS["model"]
        cfg["translate_model"] = (self.translate_model_edit.text().strip()
                                  or config.DEFAULTS["translate_model"])
        cfg["base_url"] = self.base_edit.text().strip() or config.DEFAULTS["base_url"]
        return cfg

    def run_test(self):
        self._save_btn.setEnabled(False)  # do not save while the test is running
        self.result.setPlainText("Testing each model, Deepgram, and your audio devices…")
        brain_key = self.brain_key_edit.text().strip() or config.get_brain_key()
        dg_key = self.deepgram_edit.text().strip() or config.get_deepgram_key()
        cfg = self.current_cfg()

        def work():
            lines = []
            brain_steps = brain_mod.test_connection(cfg, brain_key)
            dg_ok, dg_msg = stt_mod.check_key(dg_key)
            lines.append(("✓ " if dg_ok else "✗ ") + "Deepgram API key: " + dg_msg)
            self._test_ran = True
            self.test_ok = dg_ok and bool(brain_steps) and all(ok for _, ok, _ in brain_steps)
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
        brain_key = self.brain_key_edit.text().strip()
        if brain_key:
            config.set_brain_key(brain_key)
        dg_key = self.deepgram_edit.text().strip()
        if dg_key:
            config.set_deepgram_key(dg_key)
        cfg = self.current_cfg()
        if self.test_ok and self._tested_for == test_fingerprint(cfg):
            cfg["tested_ok_for"] = self._tested_for
        elif self._test_ran:
            cfg.pop("tested_ok_for", None)  # tes ulang gagal: gerbang lama hangus
        config.save(cfg)
        self.accept()
