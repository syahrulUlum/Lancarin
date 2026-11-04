"""Konfigurasi Lancarin: berkas JSON non-rahasia + token di brankas OS."""
import json
import os
from pathlib import Path

import keyring

SERVICE = "Lancarin"
TOKEN_USER = "meta-api-token"

MODELS = [
    "muse-spark-1.3",
    "muse-spark-1.2",
    "muse-spark-1.3-contributor",
    "muse-spark-1.2-contributor",
    "muse-wonder-1.0",
]
STT_MODEL = "muse-voice-transcribe-1.0"
# 25 bahasa Muse Voice Transcribe (dokumentasi Speech-to-Text Meta).
LANGUAGES = [
    "Indonesian", "English", "Arabic", "Bengali", "Dutch", "French", "German",
    "Hebrew", "Hindi", "Italian", "Japanese", "Kannada", "Korean", "Malay",
    "Mandarin Chinese", "Marathi", "Polish", "Portuguese", "Spanish",
    "Tagalog", "Tamil", "Telugu", "Thai", "Turkish", "Vietnamese",
]

DEFAULTS = {
    "model": "muse-wonder-1.0",
    "translate_model": "muse-wonder-1.0",
    "base_url": "https://api.meta.ai/v1",
    "opponent_lang": "English",
    "my_lang": "Indonesian",
    "mode": "conversation",
}


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(base) / "Lancarin"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "config.json"


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(config_path().read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save(cfg: dict) -> None:
    safe = {k: v for k, v in cfg.items() if k != "token"}
    config_path().write_text(json.dumps(safe, indent=2), encoding="utf-8")


def get_token() -> str:
    try:
        return keyring.get_password(SERVICE, TOKEN_USER) or ""
    except Exception:
        return ""


def set_token(token: str) -> None:
    if token:
        keyring.set_password(SERVICE, TOKEN_USER, token)
    else:
        try:
            keyring.delete_password(SERVICE, TOKEN_USER)
        except Exception:
            pass


def token_hint(token: str) -> str:
    return ("••••" + token[-4:]) if len(token) >= 4 else ("tersimpan" if token else "belum diisi")
