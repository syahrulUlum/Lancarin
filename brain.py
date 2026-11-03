"""Otak AI Lancarin: terjemahan, saran jawaban, bantuan kata, ringkasan (Muse Spark)."""
import time

from openai import OpenAI

import config


class Brain:
    def __init__(self, cfg: dict, token: str):
        self.cfg = cfg
        self.client = OpenAI(api_key=token, base_url=cfg["base_url"])
        self.model = cfg["model"]

    def chat(self, system: str, user: str, max_tokens: int = 600) -> str:
        r = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return (r.choices[0].message.content or "").strip()

    def translate(self, text: str, src: str, dst: str) -> str:
        if src == dst or not text.strip():
            return text
        return self.chat(
            f"You are a precise live interpreter. Translate from {src} to {dst}. "
            "The text may be an unfinished sentence fragment; translate what is there. "
            "Output ONLY the translation, no quotes, no notes.",
            text, max_tokens=400,
        )

    def suggest(self, context_desc: str, history: str, opponent_text: str,
                opponent_lang: str, my_lang: str) -> str:
        system = (
            "You help a non-native speaker answer live in a conversation. "
            f"The other person speaks {opponent_lang}; the user speaks {my_lang} and must reply in {opponent_lang}. "
            "Use the full history so the reply stays coherent. "
            "Output exactly two lines:\n"
            f"EN: <natural short reply in {opponent_lang}>\n"
            f"ID: <same reply translated to {my_lang}>"
        )
        user = f"Context: {context_desc or '-'}\n\nHistory:\n{history or '-'}\n\nOther person just said: {opponent_text}"
        raw = self.chat(system, user, max_tokens=300)
        en, trans = "", ""
        for line in raw.splitlines():
            if line.startswith("EN:"):
                en = line[3:].strip()
            elif line.startswith("ID:"):
                trans = line[3:].strip()
        return f"{en}\n{trans}" if en else raw

    def word_help(self, partial: str, opponent_lang: str, my_lang: str) -> str:
        return self.chat(
            "A speaker is stuck mid-sentence. Guess the single most likely short phrase "
            f"they want to say next in {opponent_lang}. Output ONLY that phrase.",
            f"Unfinished sentence ({my_lang} speaker speaking {opponent_lang}): {partial}",
        )

    def summarize(self, context_desc: str, transcript: str, my_lang: str) -> str:
        return self.chat(
            f"Summarize this conversation ONLY from its transcript, in {my_lang}. "
            "Sections: Topik; Poin Penting; Keputusan; Tindak Lanjut; Kosakata Baru. "
            "Never invent facts that are not in the transcript.",
            f"Context: {context_desc or '-'}\n\nTranscript:\n{transcript}",
        )


def test_connection(cfg: dict, token: str) -> list[tuple[str, bool, str]]:
    """Lapis 1-2 Tes Koneksi. Lapis 3 (audio) dijalankan UI."""
    steps: list[tuple[str, bool, str]] = []
    if not token:
        return [("Token", False, "Token kosong — isi token Meta dulu di Pengaturan.")]
    try:
        brain = Brain(cfg, token)
        start = time.time()
        reply = brain.chat("Reply with exactly: OK", "ping")
        ms = int((time.time() - start) * 1000)
        ok = "OK" in reply.upper()
        steps.append(("Model " + cfg["model"], ok, f"Balasan diterima dalam {ms} ms." if ok else f"Balasan tak terduga: {reply[:80]}"))
    except Exception as exc:  # tampilkan penyebab yang bisa ditindaklanjuti
        msg = str(exc)
        hint = "Periksa token dan model terpilih." if "401" in msg or "auth" in msg.lower() else "Periksa internet / base_url."
        steps.append(("Model " + cfg["model"], False, f"{msg[:140]} — {hint}"))
    return steps
