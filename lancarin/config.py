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
# Daftar mengikuti dukungan multilingual Deepgram Nova-3 (55 bahasa);
# setiap nama WAJIB punya kode, dites di tests.test_languages.
LANGUAGES = [
    "Afrikaans", "Arabic", "Belarusian", "Bengali", "Bosnian", "Bulgarian",
    "Catalan", "Chinese (Cantonese)", "Chinese (Mandarin)", "Croatian",
    "Czech", "Danish", "Dutch", "English", "Estonian", "Finnish", "Flemish",
    "French", "Galician", "German", "Greek", "Gujarati", "Hebrew", "Hindi",
    "Hungarian", "Indonesian", "Italian", "Japanese", "Kannada", "Korean",
    "Latvian", "Lithuanian", "Macedonian", "Malay", "Marathi", "Norwegian",
    "Persian", "Polish", "Portuguese", "Romanian", "Russian", "Serbian",
    "Slovak", "Slovenian", "Spanish", "Swedish", "Tagalog", "Tamil",
    "Telugu", "Thai", "Turkish", "Ukrainian", "Vietnamese", "Xhosa", "Zulu",
]
LANGUAGE_CODES = {
    "Afrikaans": "af", "Arabic": "ar", "Belarusian": "be", "Bengali": "bn",
    "Bosnian": "bs", "Bulgarian": "bg", "Catalan": "ca",
    "Chinese (Cantonese)": "zh-HK", "Chinese (Mandarin)": "zh",
    "Mandarin Chinese": "zh",  # nama lama di config pengguna terdahulu
    "Croatian": "hr", "Czech": "cs", "Danish": "da", "Dutch": "nl",
    "English": "en", "Estonian": "et", "Finnish": "fi", "Flemish": "nl-BE",
    "French": "fr", "Galician": "gl", "German": "de", "Greek": "el",
    "Gujarati": "gu", "Hebrew": "he", "Hindi": "hi", "Hungarian": "hu",
    "Indonesian": "id", "Italian": "it", "Japanese": "ja", "Kannada": "kn",
    "Korean": "ko", "Latvian": "lv", "Lithuanian": "lt", "Macedonian": "mk",
    "Malay": "ms", "Marathi": "mr", "Norwegian": "no", "Persian": "fa",
    "Polish": "pl", "Portuguese": "pt", "Romanian": "ro", "Russian": "ru",
    "Serbian": "sr", "Slovak": "sk", "Slovenian": "sl", "Spanish": "es",
    "Swedish": "sv", "Tagalog": "tl", "Tamil": "ta", "Telugu": "te",
    "Thai": "th", "Turkish": "tr", "Ukrainian": "uk", "Vietnamese": "vi",
    "Xhosa": "xh", "Zulu": "zu",
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
    "panel_font": 16,
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
