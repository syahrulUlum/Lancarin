"""Lancarin — asisten percakapan real-time (transkripsi, terjemahan, saran AI)."""
import sys
import threading

# Wajib sebelum PySide6: stt membuat ThreadPoolExecutor saat diimpor, dan di
# Python 3.15 impor sesudah PySide6 menghasilkan 'lazy_import' tak terpanggil.
import audio
import brain as brain_mod
import config
from session import Session
from stt import RealtimeSTT

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

class Bridge(QObject):
    opponent_final = Signal(str)
    mine_final = Signal(str)
    partial = Signal(str, str)  # who, text
    suggestion = Signal(str)
    translation = Signal(str, str)  # original, translated
    summary_ready = Signal(str)
    status = Signal(str)
    test_done = Signal(str)


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.setWindowTitle("Pengaturan Lancarin")
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token = config.get_token()
        self.token_edit.setPlaceholderText(config.token_hint(token))
        self.model_box = QComboBox()
        self.model_box.addItems(config.MODELS)
        self.model_box.setCurrentText(cfg["model"])
        self.base_edit = QLineEdit(cfg["base_url"])
        self.result = QTextEdit(readOnly=True)
        test_btn = QPushButton("Tes Koneksi")
        test_btn.clicked.connect(self.run_test)
        save_btn = QPushButton("Simpan")
        save_btn.clicked.connect(self.save)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Token Meta Model API (tersimpan aman di brankas OS):"))
        lay.addWidget(self.token_edit)
        lay.addWidget(QLabel("Model penalaran (Muse Spark):"))
        lay.addWidget(self.model_box)
        lay.addWidget(QLabel("Base URL (lanjutan, kosongkan untuk default Meta):"))
        lay.addWidget(self.base_edit)
        lay.addWidget(test_btn)
        lay.addWidget(self.result)
        lay.addWidget(save_btn)

    def current_cfg(self):
        cfg = dict(self.cfg)
        cfg["model"] = self.model_box.currentText()
        cfg["base_url"] = self.base_edit.text().strip() or config.DEFAULTS["base_url"]
        return cfg

    def run_test(self):
        self.result.setPlainText("Menguji…")
        token = self.token_edit.text().strip() or config.get_token()
        cfg = self.current_cfg()

        def work():
            lines = []
            for name, ok, msg in brain_mod.test_connection(cfg, token):
                lines.append(("✓ " if ok else "✗ ") + name + ": " + msg)
            try:
                loop_i, mic_i, _ = audio.list_devices()
                ok = loop_i is not None and mic_i is not None
                lines.append(("✓ " if ok else "✗ ") + f"Audio: loopback={loop_i}, mic={mic_i}")
            except Exception as exc:
                lines.append("✗ Audio: " + str(exc)[:120])
            self.parent().bridge.test_done.emit("\n".join(lines))

        threading.Thread(target=work, daemon=True).start()

    def save(self):
        token = self.token_edit.text().strip()
        if token:
            config.set_token(token)
        config.save(self.current_cfg())
        self.accept()


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.original = QLabel("")
        self.translated = QLabel("")
        self.suggested = QLabel("")
        for lab, size, color in ((self.original, 15, "#ffffff"),
                                 (self.translated, 15, "#9be7ff"),
                                 (self.suggested, 14, "#ffe89b")):
            lab.setWordWrap(True)
            lab.setStyleSheet(f"font-size:{size}px;color:{color};"
                              "background:rgba(0,0,0,160);padding:4px 8px;border-radius:6px;")
        lay = QVBoxLayout(self)
        lay.addWidget(self.original)
        lay.addWidget(self.translated)
        lay.addWidget(self.suggested)
        self.resize(760, 170)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - 380, screen.bottom() - 210)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lancarin — Asisten Percakapan")
        self.bridge = Bridge()
        self.cfg = config.load()
        self.session = Session()
        self.brain = None
        self.captures = []
        self.stts = []
        self.overlay = Overlay()
        self.private_mode = False

        self.context_edit = QPlainTextEdit()
        self.context_edit.setPlaceholderText(
            "Opsional: deskripsi percakapan ini untuk apa. "
            "Contoh: Interview posisi marketing, saya kandidatnya.")
        self.context_edit.setMaximumHeight(70)
        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("Kata kunci/nama penting, pisahkan koma (opsional)")
        self.opp_lang = QComboBox(); self.opp_lang.addItems(config.LANGUAGES)
        self.opp_lang.setCurrentText(self.cfg["opponent_lang"])
        self.my_lang = QComboBox(); self.my_lang.addItems(config.LANGUAGES)
        self.my_lang.setCurrentText(self.cfg["my_lang"])
        self.mode_box = QComboBox(); self.mode_box.addItems(["conversation", "translate"])
        self.mode_box.setCurrentText(self.cfg["mode"])
        self.log = QTextEdit(readOnly=True)
        self.level_loop = QProgressBar(maximum=100)
        self.level_mic = QProgressBar(maximum=100)
        self.status_label = QLabel("Siap. Isi token lewat Pengaturan, lalu Tes Koneksi.")

        settings_btn = QPushButton("Pengaturan && Tes Koneksi")
        settings_btn.clicked.connect(self.open_settings)
        self.start_btn = QPushButton("Mulai Sesi")
        self.start_btn.clicked.connect(self.start_session)
        self.stop_btn = QPushButton("Akhiri && Ringkasan")
        self.stop_btn.clicked.connect(self.end_session)
        self.stop_btn.setEnabled(False)
        private_btn = QPushButton("Cek Ucapan Saya (F9)")
        private_btn.clicked.connect(self.toggle_private)
        export_btn = QPushButton("Ekspor Transkrip .md")
        export_btn.clicked.connect(self.export_md)

        lay = QVBoxLayout()
        lay.addWidget(QLabel("Deskripsi konteks (opsional):")); lay.addWidget(self.context_edit)
        lay.addWidget(self.keywords_edit)
        row = QHBoxLayout()
        row.addWidget(QLabel("Bahasa lawan:")); row.addWidget(self.opp_lang)
        row.addWidget(QLabel("Bahasa saya:")); row.addWidget(self.my_lang)
        row.addWidget(QLabel("Mode:")); row.addWidget(self.mode_box)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(settings_btn); row2.addWidget(self.start_btn)
        row2.addWidget(self.stop_btn); row2.addWidget(private_btn); row2.addWidget(export_btn)
        lay.addLayout(row2)
        lay.addWidget(QLabel("Level loopback / mic:"))
        lay.addWidget(self.level_loop); lay.addWidget(self.level_mic)
        lay.addWidget(self.log); lay.addWidget(self.status_label)
        central = QWidget(); central.setLayout(lay); self.setCentralWidget(central)
        self.resize(860, 640)

        self.bridge.opponent_final.connect(self.on_opponent)
        self.bridge.mine_final.connect(self.on_mine)
        self.bridge.partial.connect(self.on_partial)
        self.bridge.suggestion.connect(lambda s: self.overlay.suggested.setText(s))
        self.bridge.translation.connect(self.on_translation)
        self.bridge.summary_ready.connect(self.on_summary)
        self.bridge.status.connect(self.status_label.setText)
        self.bridge.test_done.connect(lambda s: QMessageBox.information(self, "Tes Koneksi", s))
        QShortcut(QKeySequence("F9"), self).activated.connect(self.toggle_private)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick_levels)
        self.timer.start(200)

    def tick_levels(self):
        if len(self.captures) == 2:
            self.level_loop.setValue(min(100, int(self.captures[0].level * 400)))
            self.level_mic.setValue(min(100, int(self.captures[1].level * 400)))

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            self.cfg = config.load()
            self.status_label.setText("Pengaturan tersimpan.")

    def toggle_private(self):
        self.private_mode = not self.private_mode
        self.status_label.setText(
            "Mode PRIVAT aktif: ucapanmu hanya diterjemahkan di Lancarin. "
            "Pastikan mic Zoom/Meet dalam keadaan mute." if self.private_mode
            else "Mode privat mati.")

    def start_session(self):
        token = config.get_token()
        if not token:
            QMessageBox.warning(self, "Lancarin", "Token Meta masih kosong. Buka Pengaturan dulu.")
            return
        self.cfg.update({"opponent_lang": self.opp_lang.currentText(),
                         "my_lang": self.my_lang.currentText(),
                         "mode": self.mode_box.currentText()})
        config.save(self.cfg)
        self.brain = brain_mod.Brain(self.cfg, token)
        self.session = Session(self.context_edit.toPlainText().strip())
        keywords = [k.strip() for k in self.keywords_edit.text().split(",") if k.strip()]
        loop_i, mic_i, _ = audio.list_devices()
        if loop_i is None or mic_i is None:
            QMessageBox.warning(self, "Lancarin", f"Perangkat audio tidak lengkap: loopback={loop_i}, mic={mic_i}")
            return
        self.captures = [audio.Capture(loop_i), audio.Capture(mic_i)]
        for cap in self.captures:
            cap.start()
        opp, mine = self.cfg["opponent_lang"], self.cfg["my_lang"]
        self.stts = [
            RealtimeSTT(token, self.captures[0].frames, [opp, mine], keywords,
                        lambda t: self.bridge.partial.emit("Lawan", t),
                        lambda t: self.bridge.opponent_final.emit(t),
                        lambda e: self.bridge.status.emit("STT lawan: " + e)),
            RealtimeSTT(token, self.captures[1].frames, [mine, opp], keywords,
                        lambda t: self.bridge.partial.emit("Saya", t),
                        lambda t: self.bridge.mine_final.emit(t),
                        lambda e: self.bridge.status.emit("STT saya: " + e)),
        ]
        for s in self.stts:
            s.start()
        self.overlay.show()
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.status_label.setText("Sesi berjalan — mendengarkan lawan dan kamu.")

    def on_partial(self, who, text):
        if who == "Lawan":
            self.overlay.original.setText(text)

    def on_opponent(self, text):
        opp, mine = self.cfg["opponent_lang"], self.cfg["my_lang"]
        turn = self.session.add("Lawan", text)
        self.log.append(f"<b>Lawan:</b> {text}")
        self.overlay.original.setText(text)
        brain, session = self.brain, self.session

        def work():
            try:
                translated = brain.translate(text, opp, mine)
                turn.translation = translated
                self.bridge.translation.emit(text, translated)
                if self.cfg["mode"] == "conversation":
                    saran = brain.suggest(session.context_desc, session.history_text(),
                                          text, opp, mine)
                    self.bridge.suggestion.emit("Saran: " + saran.replace("\n", "  |  "))
            except Exception as exc:
                self.bridge.status.emit("AI: " + str(exc)[:160])

        threading.Thread(target=work, daemon=True).start()

    def on_mine(self, text):
        self.session.add("Saya", text)
        label = "Saya (privat): " if self.private_mode else "Saya: "
        self.log.append(f"<b>{label}</b> {text}")
        if self.private_mode and self.brain:
            brain, opp, mine = self.brain, self.cfg["opponent_lang"], self.cfg["my_lang"]

            def work():
                try:
                    hasil = brain.translate(text, mine, opp)
                    self.bridge.suggestion.emit(f"Ucapanmu ({opp}): " + hasil)
                except Exception as exc:
                    self.bridge.status.emit("AI: " + str(exc)[:160])

            threading.Thread(target=work, daemon=True).start()

    def on_translation(self, original, translated):
        self.overlay.translated.setText(translated)
        self.log.append(f"<i>-> {translated}</i>")

    def stop_streams(self):
        for s in self.stts:
            s.stop()
        for c in self.captures:
            c.stop()
        self.stts, self.captures = [], []

    def end_session(self):
        self.stop_streams()
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        if not self.brain or not self.session.turns:
            self.status_label.setText("Sesi berakhir (belum ada percakapan).")
            return
        self.status_label.setText("Menyusun ringkasan…")
        brain, session = self.brain, self.session
        mine = self.cfg["my_lang"]

        def work():
            try:
                summary = brain.summarize(session.context_desc, session.transcript_text(), mine)
                self.bridge.summary_ready.emit(summary)
            except Exception as exc:
                self.bridge.status.emit("Ringkasan gagal: " + str(exc)[:160])

        threading.Thread(target=work, daemon=True).start()

    def on_summary(self, summary):
        self._last_summary = summary
        QMessageBox.information(self, "Ringkasan Sesi", summary)
        self.status_label.setText("Ringkasan selesai. Ekspor .md untuk menyimpan transkrip lengkap.")

    def export_md(self):
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor Transkrip", "lancarin-sesi.md", "Markdown (*.md)")
        if path:
            md = self.session.export_md(getattr(self, "_last_summary", ""))
            open(path, "w", encoding="utf-8").write(md)
            self.status_label.setText("Tersimpan: " + path)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()



