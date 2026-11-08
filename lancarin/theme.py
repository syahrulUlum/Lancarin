"""Shared UI theme, settings fingerprint helpers, and card builder."""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


QSS = """
QMainWindow, QDialog { background: #0f141b; }
QLabel { color: #dbe4ee; font-size: 12px; }
QLabel#stepTitle { color: #ffffff; font-size: 14px; font-weight: 600; }
QLabel#hint { color: #8494a7; font-size: 11px; }
QFrame#card { background: #171f2a; border: 1px solid #263242; border-radius: 10px; }
QLineEdit, QPlainTextEdit, QComboBox, QTextEdit {
    background: #101820; color: #e8eef4; border: 1px solid #2b3a4d;
    border-radius: 7px; padding: 5px 8px; font-size: 12px;
}
QComboBox::drop-down { border: none; width: 20px; }
QRadioButton { color: #dbe4ee; font-size: 12px; spacing: 5px; }
QPushButton {
    background: #223146; color: #e8eef4; border: 1px solid #31445e;
    border-radius: 7px; padding: 5px 10px; font-size: 12px;
}
QPushButton:hover { background: #2a3d59; }
QPushButton#primary {
    background: #0d9488; border-color: #0d9488; color: #ffffff;
    font-size: 14px; font-weight: 700; padding: 9px;
}
QPushButton#primary:hover { background: #0fae9f; }
QPushButton#danger {
    background: #b91c1c; border-color: #b91c1c; color: #ffffff;
    font-size: 13px; font-weight: 700; padding: 8px;
}
QPushButton:disabled { background: #131a24; color: #43536a; border: 1px solid #1b2635; }
QPushButton#primary:disabled, QPushButton#danger:disabled { background: #131a24; color: #43536a; border-color: #1b2635; }
QPushButton#privateBtn:checked { background: #92400e; border-color: #d97706; color: #fff7ed; }
QPushButton#compact, QPushButton#privateBtn { padding: 3px 7px; font-size: 11px; }
QLabel#sectionHead { color: #5eead4; font-size: 11px; font-weight: 700; padding-top: 4px; }
QPushButton#suggestionOption {
    background: #2a2103; color: #fde68a; border: 1px solid #6b5410;
    border-radius: 8px; padding: 7px 10px; text-align: left;
}
QPushButton#suggestionOption:hover { background: #3c2f05; }
QProgressBar { background: #101820; border: 1px solid #2b3a4d; border-radius: 5px; height: 10px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #0d9488; border-radius: 4px; }
"""


def test_fingerprint(cfg: dict) -> str:
    return f"{cfg.get('model', '')}|{cfg.get('translate_model', '')}|{cfg.get('base_url', '')}"


def is_tested(cfg: dict) -> bool:
    return bool(cfg.get("tested_ok_for")) and cfg["tested_ok_for"] == test_fingerprint(cfg)


def _card(title: str, hint: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(10, 9, 10, 9)
    lay.setSpacing(6)
    t = QLabel(title)
    t.setObjectName("stepTitle")
    frame.title_label = t
    lay.addWidget(t)
    if hint:
        h = QLabel(hint)
        h.setObjectName("hint")
        h.setWordWrap(True)
        lay.addWidget(h)
    return frame, lay


