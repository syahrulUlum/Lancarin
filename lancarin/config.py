"""Konfigurasi Lancarin: berkas JSON non-rahasia + API key di brankas OS."""
import json
import os
from pathlib import Path

import keyring

SERVICE = "Lancarin"
BRAIN_KEY_USER = "brain-api-key"
DEEPGRAM_KEY_USER = "deepgram-api-key"

STT_MODEL = "nova-3"
# Bahasa yang bisa dipilih di UI (nama tampilan -> kode Deepgram/BCP-47).
LANGUAGES = [
    "Indonesian", "English", "Arabic", "Bengali", "Dutch", "French", "German",
    "Hebrew", "Hindi", "Italian", "Japanese", "Kannada", "Korean", "Malay",
    "Mandarin Chinese", "Marathi", "Polish", "Portuguese", "Spanish",
    "Tagalog", "Tamil", "Telugu", "Thai", "Turkish", "Vietnamese",
]
LANGUAGE_CODES = {
    "Indonesian": "id", "English": "en", "Arabic": "ar", "Bengali": "bn",
    "Dutch": "nl", "French": "fr", "German": "de", "Hebrew": "he",
    "Hindi": "hi", "Italian": "it", "Japanese": "ja", "Kannada": "kn",
    "Korean": "ko", "Malay": "ms", "Mandarin Chinese": "zh", "Marathi": "mr",
    "Polish": "pl", "Portuguese": "pt", "Spanish": "es", "Tagalog": "tl",
    "Tamil": "ta", "Telugu": "te", "Thai": "th", "Turkish": "tr",
    "Vietnamese": "vi",
}

DEFAULTS = {
    # Brain: endpoint OpenAI-compatible apa pun (Groq default: cepat & murah).
    # Ganti base_url + model + key di Settings untuk pindah provider.
    "model": "openai/gpt-oss-120b",
    "translate_model": "openai/gpt-oss-20b",
    "base_url": "https://api.groq.com/openai/v1",
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
    # Migrasi dari provider Meta lama: endpoint/model Muse tidak dipakai lagi.
    if "api.meta.ai" in str(cfg.get("base_url", "")):
        cfg.update({k: DEFAULTS[k] for k in ("model", "translate_model", "base_url")})
        cfg.pop("tested_ok_for", None)
    return cfg


def save(cfg: dict) -> None:
    safe = {k: v for k, v in cfg.items() if "key" not in k and k != "token"}
    config_path().write_text(json.dumps(safe, indent=2), encoding="utf-8")


def _get_key(user: str) -> str:
    try:
        return keyring.get_password(SERVICE, user) or ""
    except Exception:
        return ""


def _set_key(user: str, value: str) -> None:
    if value:
        keyring.set_password(SERVICE, user, value)
    else:
        try:
            keyring.delete_password(SERVICE, user)
        except Exception:
            pass


def get_brain_key() -> str:
    # Token Meta lama sengaja tidak dipakai: hampir pasti ditolak provider baru.
    return _get_key(BRAIN_KEY_USER)


def set_brain_key(value: str) -> None:
    _set_key(BRAIN_KEY_USER, value)


def get_deepgram_key() -> str:
    return _get_key(DEEPGRAM_KEY_USER)


def set_deepgram_key(value: str) -> None:
    _set_key(DEEPGRAM_KEY_USER, value)


# Alias lama (dipakai tes lama): token = brain key.
def get_token() -> str:
    return get_brain_key()


def set_token(token: str) -> None:
    set_brain_key(token)


def token_hint(token: str) -> str:
    return ("••••" + token[-4:]) if len(token) >= 4 else ("saved" if token else "not set")
