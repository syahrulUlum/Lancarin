"""Settings dialog: Meta token, the two models, and the connection test."""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

from . import audio
from . import brain as brain_mod
from . import config
from .theme import QSS, test_fingerprint


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
        right = QVBoxLayout(); right.addWidget(QLabel("Suggestions and summary:")); right.addWidget(self.model_box)
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


