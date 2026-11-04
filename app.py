"""Lancarin — asisten percakapan real-time (transkripsi, terjemahan, saran AI)."""
import html
import sys
import threading
import time

# stt kebal urutan impor (lihat stt.py); impor awal di sini hanya kejelasan.
import audio
import brain as brain_mod
import config
from session import Session
from stt import RealtimeSTT

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
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
    return f"{cfg.get('model', '')}|{cfg.get('base_url', '')}"


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
        self.setWindowTitle("Pengaturan Lancarin")
        self.setStyleSheet(QSS)
        self.resize(520, 430)
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token = config.get_token()
        self.token_edit.setPlaceholderText(config.token_hint(token) + " — tempel token baru untuk mengganti")
        self.model_box = QComboBox()
        self.model_box.addItems(config.MODELS)
        self.model_box.setCurrentText(cfg["model"])
        self.base_edit = QLineEdit(cfg["base_url"])
        self.result = QTextEdit(readOnly=True)
        self.result.setPlaceholderText("Hasil Tes Koneksi muncul di sini.")
        self.result_ready.connect(self.result.setPlainText)
        test_btn = QPushButton("Tes Koneksi")
        test_btn.clicked.connect(self.run_test)
        save_btn = QPushButton("Simpan")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save)
        self._save_btn = save_btn
        self.result_ready.connect(lambda _t: self._save_btn.setEnabled(True))
        lay = QVBoxLayout(self)
        title = QLabel("Token & Model Meta"); title.setObjectName("stepTitle")
        lay.addWidget(title)
        lay.addWidget(QLabel("Token Meta Model API (tersimpan aman di brankas OS, dapatkan di dev.meta.ai):"))
        lay.addWidget(self.token_edit)
        lay.addWidget(QLabel("Model penalaran (Muse Spark):"))
        lay.addWidget(self.model_box)
        _mh = QLabel("Terjemahan langsung selalu memakai muse-wonder-1.0 (terukur tercepat); model ini dipakai untuk saran & ringkasan.")
        _mh.setObjectName("hint"); _mh.setWordWrap(True)
        lay.addWidget(_mh)
        lay.addWidget(QLabel("Base URL (lanjutan, biarkan default Meta):"))
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
        self._save_btn.setEnabled(False)  # jangan simpan di tengah tes berjalan
        self.result.setPlainText("Menguji…")
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
                lines.append(("✓ " if ok else "✗ ") + f"Audio: loopback={loop_i}, mic={mic_i}")
            except Exception as exc:
                lines.append("✗ Audio: " + str(exc)[:120])
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


class Overlay(QWidget):
    """Bar subtitle lebar di bawah layar: saran, asli, terjemahan besar."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.badge = QLabel("")
        self.suggested = QLabel("")
        self.original = QLabel("")
        self.translated = QLabel("")
        self.badge.setStyleSheet(
            "color:#5eead4;font-size:11px;font-weight:700;"
            "background:rgba(13,60,55,200);padding:2px 8px;border-radius:6px;")
        self.suggested.setStyleSheet(
            "color:#fde68a;font-size:15px;background:rgba(60,42,4,205);"
            "padding:6px 10px;border-radius:8px;")
        self.original.setStyleSheet(
            "color:#aebdd0;font-size:14px;background:rgba(8,12,18,190);"
            "padding:5px 10px;border-radius:8px;")
        self.translated.setStyleSheet(
            "color:#ffffff;font-size:22px;font-weight:600;"
            "background:rgba(8,12,18,215);padding:7px 10px;border-radius:8px;")
        for lab in (self.badge, self.suggested, self.original, self.translated):
            lab.setWordWrap(True)
            lab.hide()
        self._font = 22
        # Kontrol yang bisa diklik langsung di overlay (tanpa hafal F7/F8).
        ctl_style = ("QPushButton{background:rgba(20,30,44,215);color:#dbe4ee;"
                     "border:1px solid #31445e;border-radius:6px;padding:3px 9px;font-size:12px;}"
                     "QPushButton:hover{background:rgba(42,61,89,230);}")
        self.btn_smaller = QPushButton("A− Kecilkan")
        self.btn_bigger = QPushButton("A+ Besarkan")
        self.btn_hide = QPushButton("✕ Sembunyikan")
        for b in (self.btn_smaller, self.btn_bigger, self.btn_hide):
            b.setStyleSheet(ctl_style)
        self.btn_hide.clicked.connect(self.hide)
        self.btn_bigger.clicked.connect(lambda: self._zoom(1))
        self.btn_smaller.clicked.connect(lambda: self._zoom(-1))
        ctl_row = QHBoxLayout()
        ctl_row.setContentsMargins(0, 0, 0, 0)
        ctl_row.addStretch(1)
        ctl_row.addWidget(self.btn_smaller)
        ctl_row.addWidget(self.btn_bigger)
        ctl_row.addWidget(self.btn_hide)
        self._controls = QWidget()
        self._controls.setLayout(ctl_row)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        lay.addWidget(self._controls)
        lay.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.suggested)
        lay.addWidget(self.original)
        lay.addWidget(self.translated)
        screen = QApplication.primaryScreen().availableGeometry()
        width = min(1120, screen.width() - 80)
        self._width = width
        self.resize(width, 190)
        self.move(screen.center().x() - width // 2, screen.bottom() - 215)

    def _fit(self):
        """Tinggi mengikuti isi pada lebar aktual (sizeHint meremehkan label
        word-wrap, jadi teks panjang tetap terpotong bila memakainya)."""
        bottom = self.y() + self.height()
        labs = [lab for lab in (self.badge, self.suggested, self.original, self.translated)
                if not lab.isHidden()]
        total = (self._controls.sizeHint().height()
                 + sum(lab.heightForWidth(self._width) for lab in labs)
                 + 5 * max(0, len(labs)))
        screen = QApplication.primaryScreen()
        cap = screen.availableGeometry().height() if screen else total
        self.resize(self._width, min(max(40, total), cap))
        if screen:
            geo = screen.availableGeometry()
            self.move(self.x(), max(geo.top(), min(bottom - self.height(), geo.bottom() - self.height())))

    def _apply_font(self):
        self.translated.setStyleSheet(
            f"color:#ffffff;font-size:{self._font}px;font-weight:600;"
            "background:rgba(8,12,18,215);padding:7px 10px;border-radius:8px;")

    def _zoom(self, arah: int):
        self._font = max(14, min(38, self._font + 2 * arah))
        self._width = max(520, min(1600, self._width + 70 * arah))
        self._apply_font()
        self._fit()

    def show_processing(self, text: str):
        self.badge.setText(text)
        self.badge.show()
        self._fit()

    def toggle_click_through(self) -> bool:
        on = not self.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on)
        return on

    def show_live(self, who: str):
        self.badge.setText("● " + who.upper() + " BERBICARA…")
        self.badge.show()
        self._fit()

    def show_suggestion(self, text: str):
        self.suggested.setText(text)
        self.suggested.setVisible(bool(text))
        self._fit()

    def show_original(self, text: str):
        self.original.setText(text)
        self.original.setVisible(bool(text))
        self._fit()

    def show_translated(self, text: str):
        self.translated.setText(text)
        self.translated.setVisible(bool(text))
        self._fit()

    def clear_live(self):
        self.badge.hide()

    # Seret untuk memindah, roda mouse untuk memperbesar/kecil, F8 sembunyi.
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_offset", None) is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def wheelEvent(self, event):
        step = 60 if event.angleDelta().y() > 0 else -60
        width = max(560, min(1500, self.width() + step))
        self._width = width
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(width, self.height())
        self.move(max(screen.left(), min(self.x(), screen.right() - width)), self.y())
        self._font = max(15, min(34, int(width / 50)))
        self._apply_font()
        self._fit()
        event.accept()


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
        self.setWindowTitle("Lancarin — Asisten Percakapan")
        self.setStyleSheet(QSS)
        self.bridge = Bridge()
        self.cfg = config.load()
        self.session = Session()
        self.brain = None
        self.captures = []
        self.stts = []
        self.overlay = Overlay()
        self.private_mode = False
        self._gen = 0  # nomor generasi sesi: hasil thread sesi lama dibuang
        self._keywords = []
        self._summary_dialog = None
        self._active = False
        self._partial = ""
        self._interim_busy = False
        self._interim_at = 0.0
        self._interim_snapshot = ""

        header = QLabel("Lancarin")
        header.setStyleSheet("color:#ffffff;font-size:22px;font-weight:700;")
        _tok = config.get_token()
        _awal = (f"Token sudah terisi ({config.token_hint(_tok)}) — siap dimulai" if _tok
                 else "Token belum diisi — klik Pengaturan & Tes Koneksi")
        self.status_pill = QLabel("○ " + _awal)
        self.status_pill.setStyleSheet(
            "color:#cbd5e1;background:#1c2939;border:1px solid #2b3f58;"
            "border-radius:12px;padding:5px 12px;font-size:12px;")
        settings_btn = QPushButton("Pengaturan & Tes Koneksi")
        settings_btn.clicked.connect(self.open_settings)
        head_row = QHBoxLayout()
        head_row.addWidget(header)
        head_row.addWidget(self.status_pill)
        head_row.addStretch(1)
        head_row.addWidget(settings_btn)

        self.context_edit = QPlainTextEdit()
        self.context_edit.setPlaceholderText(
            "Contoh: Interview posisi marketing, saya kandidatnya. Boleh dikosongkan.")
        self.context_edit.setMaximumHeight(64)
        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("Nama orang/perusahaan agar dikenali benar (opsional, pisahkan koma)")
        card1, lay1 = _card("1 · Siapkan sesi", "Deskripsi konteks membantu AI memberi saran yang nyambung.")
        lay1.addWidget(self.context_edit)
        lay1.addWidget(self.keywords_edit)

        self.opp_lang = QComboBox(); self.opp_lang.addItems(config.LANGUAGES)
        self.opp_lang.setCurrentText(self.cfg["opponent_lang"])
        self.my_lang = QComboBox(); self.my_lang.addItems(config.LANGUAGES)
        self.my_lang.setCurrentText(self.cfg["my_lang"])
        self.mode_conversation = QRadioButton("Percakapan (terjemahan + saran jawaban)")
        self.mode_translate = QRadioButton("Terjemahan saja")
        if self.cfg["mode"] == "conversation":
            self.mode_conversation.setChecked(True)
        else:
            self.mode_translate.setChecked(True)
        card2, lay2 = _card("2 · Bahasa & mode", "")
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Bahasa lawan:"))
        lang_row.addWidget(self.opp_lang, 1)
        lang_row.addWidget(QLabel("Bahasa saya:"))
        lang_row.addWidget(self.my_lang, 1)
        lay2.addLayout(lang_row)
        preset_row = QHBoxLayout()
        preset_en_id = QPushButton("Preset: Inggris → Indonesia")
        preset_en_id.clicked.connect(lambda: (self.opp_lang.setCurrentText("English"),
                                              self.my_lang.setCurrentText("Indonesian")))
        preset_id_en = QPushButton("Preset: Indonesia → Inggris")
        preset_id_en.clicked.connect(lambda: (self.opp_lang.setCurrentText("Indonesian"),
                                              self.my_lang.setCurrentText("English")))
        preset_row.addWidget(preset_en_id)
        preset_row.addWidget(preset_id_en)
        preset_row.addStretch(1)
        lay2.addLayout(preset_row)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_conversation)
        mode_row.addWidget(self.mode_translate)
        mode_row.addStretch(1)
        lay2.addLayout(mode_row)

        self.start_btn = QPushButton("▶  Mulai Sesi")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start_session)
        self.stop_btn = QPushButton("■  Akhiri & Buat Ringkasan")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.clicked.connect(self.end_session)
        self.stop_btn.setEnabled(False)
        self.private_btn = QPushButton("Cek Ucapan Saya saja (F9)")
        self.private_btn.setObjectName("privateBtn")
        self.private_btn.setCheckable(True)
        self.private_btn.clicked.connect(self.toggle_private)
        export_btn = QPushButton("Ekspor transkrip .md")
        export_btn.clicked.connect(self.export_md)
        self.overlay_btn = QPushButton("Sembunyikan Overlay (F8)")
        self.overlay_btn.clicked.connect(self.toggle_overlay)
        action_row = QHBoxLayout()
        action_row.addWidget(self.start_btn, 2)
        action_row.addWidget(self.stop_btn, 2)
        util_row = QHBoxLayout()
        util_row.addWidget(self.private_btn)
        util_row.addWidget(self.overlay_btn)
        util_row.addWidget(export_btn)
        util_row.addStretch(1)

        self.level_loop = QProgressBar(maximum=100)
        self.level_mic = QProgressBar(maximum=100)
        self.log = QTextEdit(readOnly=True)
        self.log.setPlaceholderText("Transkrip sesi tampil di sini…")
        self.log.document().setMaximumBlockCount(500)  # sesi panjang tidak makin lambat
        card3, lay3 = _card("3 · Percakapan langsung", "Bar hijau = suara tertangkap. Overlay subtitle: seret untuk memindah, roda mouse untuk mengubah ukuran, F8 sembunyikan/tampilkan, F7 tembus-klik (klik menembus ke Zoom/Meet).")
        meter_row = QHBoxLayout()
        meter_row.addWidget(QLabel("Lawan:"))
        meter_row.addWidget(self.level_loop, 1)
        meter_row.addWidget(QLabel("Kamu:"))
        meter_row.addWidget(self.level_mic, 1)
        lay3.addLayout(meter_row)
        self.busy_bar = QProgressBar(minimum=0, maximum=0)  # berputar selama proses AI
        self.busy_bar.hide()
        lay3.addWidget(self.busy_bar)
        lay3.addWidget(self.log)

        root = QVBoxLayout()
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)
        root.addLayout(head_row)
        root.addWidget(card1)
        root.addWidget(card2)
        root.addLayout(action_row)
        root.addLayout(util_row)
        root.addWidget(card3, 1)
        central = QWidget(); central.setLayout(root)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(central)
        self.setCentralWidget(scroll)
        self.resize(920, 720)
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
        QShortcut(QKeySequence("F8"), self).activated.connect(self.toggle_overlay)
        QShortcut(QKeySequence("F7"), self).activated.connect(self.toggle_click_through)
        self._meter_timer = QTimer(self)
        self._meter_timer.timeout.connect(self.tick_levels)
        self._meter_timer.start(200)
        self._interim_timer = QTimer(self)
        self._interim_timer.timeout.connect(self.maybe_interim)
        self._interim_timer.start(300)

    def toggle_overlay(self):
        tampil = not self.overlay.isVisible()
        self.overlay.setVisible(tampil)
        self.overlay_btn.setText("Sembunyikan Overlay (F8)" if tampil else "Tampilkan Overlay (F8)")

    def on_suggestion(self, text: str):
        self.overlay.show_suggestion(text)
        self.overlay.clear_live()  # proses AI untuk giliran ini selesai

    def set_busy(self, on: bool, text: str = ""):
        self.busy_bar.setVisible(on)
        if text:
            self.set_status(text)

    def _busy_watch(self, text: str):
        if text.startswith("Ringkasan gagal"):
            self.set_busy(False)
            self.start_btn.setEnabled(True)

    def set_status(self, text: str):
        live = "berjalan" in text or "PRIVAT" in text
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
                f"Pengaturan tersimpan — token terisi ({config.token_hint(tok)}), siap dimulai"
                if tok else "Pengaturan tersimpan — token masih kosong")

    def toggle_click_through(self):
        on = self.overlay.toggle_click_through()
        self.set_status("Overlay tembus-klik aktif (F7 untuk mematikan)"
                        if on else "Overlay tembus-klik mati (F7 untuk menyalakan)")

    def toggle_private(self):
        self.private_mode = self.private_btn.isChecked()
        if self.private_mode and self._active:
            teks = "Mode PRIVAT berjalan: ucapanmu hanya diterjemahkan di sini. Pastikan mic Zoom/Meet mute."
        elif self.private_mode:
            teks = "Mode privat siap — berlaku saat sesi berjalan. Pastikan mic Zoom/Meet mute."
        else:
            teks = "Siap — mode privat mati"
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
            self.overlay.show_translated(translated)

    # ---------- siklus sesi ----------
    def start_session(self):
        token = config.get_token()
        if not token:
            QMessageBox.warning(self, "Lancarin", "Token Meta masih kosong. Klik Pengaturan & Tes Koneksi dulu.")
            return
        if self.opp_lang.currentText() == self.my_lang.currentText():
            QMessageBox.warning(self, "Lancarin",
                                "Bahasa lawan dan Bahasa saya sama, jadi tidak ada yang "
                                "diterjemahkan. Pilih pasangan berbeda atau pakai tombol Preset.")
            return
        if not is_tested(self.cfg):
            QMessageBox.warning(self, "Lancarin",
                                "Tes Koneksi belum lolos untuk model/base URL ini. "
                                "Klik Pengaturan & Tes Koneksi, jalankan Tes Koneksi sampai ✓, lalu Simpan.")
            return
        mode = "conversation" if self.mode_conversation.isChecked() else "translate"
        self.cfg.update({"opponent_lang": self.opp_lang.currentText(),
                         "my_lang": self.my_lang.currentText(), "mode": mode})
        config.save(self.cfg)
        self.set_busy(True, "Memulai sesi — menghubungkan audio & transkripsi…")
        QApplication.processEvents()
        self.brain = brain_mod.Brain(self.cfg, token)
        self.session = Session(self.context_edit.toPlainText().strip())
        keywords = [k.strip() for k in self.keywords_edit.text().split(",") if k.strip()]
        self._keywords = keywords
        loop_i, mic_i, _ = audio.list_devices()
        if loop_i is None or mic_i is None:
            self.set_busy(False)
            QMessageBox.warning(self, "Lancarin", f"Perangkat audio tidak lengkap: loopback={loop_i}, mic={mic_i}")
            return
        self._gen += 1
        self.captures = [
            audio.Capture(loop_i, on_error=lambda e: self.bridge.status.emit("Audio lawan bermasalah: " + e)),
            audio.Capture(mic_i, on_error=lambda e: self.bridge.status.emit("Audio mic bermasalah: " + e)),
        ]
        for cap in self.captures:
            cap.start()
        opp, mine = self.cfg["opponent_lang"], self.cfg["my_lang"]
        self.stts = [
            RealtimeSTT(token, self.captures[0].frames, [opp, mine], keywords,
                        lambda t: self.bridge.partial.emit("Lawan", t),
                        lambda t: self.bridge.opponent_final.emit(t),
                        lambda e: self.bridge.status.emit("STT lawan bermasalah: " + e)),
            RealtimeSTT(token, self.captures[1].frames, [mine, opp], keywords,
                        lambda t: self.bridge.partial.emit("Saya", t),
                        lambda t: self.bridge.mine_final.emit(t),
                        lambda e: self.bridge.status.emit("STT kamu bermasalah: " + e)),
        ]
        for s in self.stts:
            s.start()
        self._active = True
        self._partial = ""
        self._interim_snapshot = ""
        self.overlay.show()
        self.overlay_btn.setText("Sembunyikan Overlay (F8)")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.set_busy(False)
        self.set_status(f"Sesi berjalan — menerjemahkan {opp} → {mine} secara langsung")

    def on_partial(self, who, text):
        if not self._active:
            return
        if who == "Lawan" and text:
            self._partial = text
            self.overlay.show_live("Lawan")
            self.overlay.show_original(text)

    def on_opponent(self, text):
        if not self._active:
            return  # final terlambat dari stream sesi lama
        self._partial = ""
        self._interim_snapshot = ""
        self.overlay.clear_live()
        opp, mine = self.cfg["opponent_lang"], self.cfg["my_lang"]
        turn = self.session.add("Lawan", text)
        self.log.append(f"<b>Lawan:</b> {html.escape(text)}")
        self.overlay.show_original(text)
        brain, session = self.brain, self.session
        gen = self._gen
        mode = self.cfg["mode"]
        history = session.history_text()
        self.overlay.show_processing("⏳ Menerjemahkan…")

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
                    self.bridge.status.emit("AI bermasalah: " + str(exc)[:160])

        threading.Thread(target=work_translate, daemon=True).start()
        if mode == "conversation":
            def work_suggest():
                try:
                    saran = brain.suggest(session.context_desc, history, text, opp, mine, list(self._keywords))
                    if gen == self._gen and saran.strip():
                        self.bridge.suggestion.emit("Saran jawab: " + saran.replace("\n", "   ·   "))
                except Exception as exc:
                    if gen == self._gen:
                        self.bridge.status.emit("Saran bermasalah: " + str(exc)[:160])

            threading.Thread(target=work_suggest, daemon=True).start()

    def on_mine(self, text):
        if not self._active:
            return
        self.session.add("Saya", text)
        label = "Saya (privat): " if self.private_mode else "Saya: "
        self.log.append(f"<b>{label}</b> {html.escape(text)}")
        if self.private_mode and self.brain:
            brain, opp, mine = self.brain, self.cfg["opponent_lang"], self.cfg["my_lang"]
            gen = self._gen

            def work():
                try:
                    hasil = brain.translate(text, mine, opp)
                    if gen == self._gen:
                        self.bridge.suggestion.emit(f"Ucapanmu dalam {opp}: " + hasil)
                except Exception as exc:
                    if gen == self._gen:
                        self.bridge.status.emit("AI bermasalah: " + str(exc)[:160])

            threading.Thread(target=work, daemon=True).start()

    def on_translation(self, original, translated):
        if not translated.strip():
            self.overlay.clear_live()
            self.set_status("Terjemahan kembali kosong dari AI — periksa model/token di Pengaturan")
            self.log.append("<i>→ (kosong dari AI)</i>")
            return
        self.overlay.show_translated(translated)
        if self.cfg["mode"] == "conversation":
            self.overlay.show_processing("⏳ Terjemahan tampil — menyusun saran…")
        else:
            self.overlay.clear_live()
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
        self.overlay.clear_live()
        self.overlay.hide()

    def end_session(self):
        # Kabari dulu, baru bekerja: menghentikan stream bisa makan detik dan
        # tanpa ini aplikasi terlihat membeku tanpa penjelasan.
        self.set_busy(True, "Mengakhiri sesi — menghentikan audio, lalu menyusun ringkasan…")
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.overlay.show_processing("⏳ Mengakhiri sesi…")
        QApplication.processEvents()
        self.stop_streams()
        self._end_gen = self._gen
        if not self.brain or not self.session.turns:
            self.set_busy(False)
            self.start_btn.setEnabled(True)
            self.set_status("Sesi berakhir — belum ada percakapan terekam")
            return
        self.set_busy(True, "Mengakhiri sesi — menyusun ringkasan (biasanya belasan detik)…")
        brain, session, mine = self.brain, self.session, self.cfg["my_lang"]
        end_gen = self._gen

        def work():
            try:
                summary = brain.summarize(session.context_desc, session.transcript_text(), mine)
                if end_gen == self._gen:  # buang sebelum emit, bukan sesudah ditimpa
                    self.bridge.summary_ready.emit(summary)
            except Exception as exc:
                if end_gen == self._gen:
                    self.bridge.status.emit("Ringkasan gagal: " + str(exc)[:160])

        threading.Thread(target=work, daemon=True).start()

    def on_summary(self, summary):
        if getattr(self, "_end_gen", self._gen) != self._gen:
            return  # ringkasan sesi lama, sesi baru sudah berjalan
        self.set_busy(False)
        self.start_btn.setEnabled(True)
        if not summary.strip():
            self.set_status("Ringkasan kembali kosong dari AI — transkrip tetap bisa diekspor")
            QMessageBox.warning(self, "Ringkasan Sesi",
                                "AI mengembalikan ringkasan kosong. Transkrip lengkap tetap "
                                "tersimpan di sesi ini — gunakan Ekspor transkrip .md.")
            return
        self._last_summary = summary
        # Panel non-modal yang bisa di-scroll/di-copy (dulu QMessageBox raksasa).
        dlg = QDialog(self)
        dlg.setWindowTitle("Ringkasan Sesi")
        dlg.setStyleSheet(QSS)
        dlg.resize(640, 480)
        box = QTextEdit(readOnly=True)
        box.setPlainText(summary)
        lay = QVBoxLayout(dlg)
        lay.addWidget(box)
        tutup = QPushButton("Tutup")
        tutup.clicked.connect(dlg.close)
        lay.addWidget(tutup)
        self._summary_dialog = dlg
        dlg.show()
        self.set_status("Ringkasan selesai — ekspor .md untuk menyimpan transkrip lengkap")

    def export_md(self):
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor Transkrip", "lancarin-sesi.md", "Markdown (*.md)")
        if path:
            md = self.session.export_md(getattr(self, "_last_summary", ""))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(md)
            self.set_status("Transkrip tersimpan: " + path)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()





