"""Otak AI Lancarin: terjemahan, saran jawaban, ringkasan (Muse Spark)."""
import time

from openai import OpenAI

import config

CHUNK_CHARS = 8000


def _parse(raw: str, *labels: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current = None
    for line in raw.splitlines():
        bersih = line.strip().strip("*").strip()
        hit = next((lb for lb in labels if bersih.upper().startswith(lb + ":")), None)
        if hit:
            current = hit
            out[hit] = bersih[len(hit) + 1:].strip().strip("*").strip()
        elif current and line.strip():
            out[current] += "\n" + line.strip()
    return out


class Brain:
    def __init__(self, cfg: dict, token: str):
        self.cfg = cfg
        # timeout pendek + retry terbatas: default OpenAI (600 dtk x3) membuat
        # satu panggilan macet membekukan overlay tanpa kabar.
        self.client = OpenAI(api_key=token, base_url=cfg["base_url"],
                             timeout=20.0, max_retries=1)
        self.model = cfg["model"]

    def chat(self, system: str, user: str) -> str:
        # Tanpa max_tokens: pada Muse Spark batas kecil dimakan proses
        # penalaran model dan content akhir kembali kosong.
        r = self.client.chat.completions.create(
            model=self.model,
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
            text,
        )

    def translate_and_suggest(self, text: str, context_desc: str, history: str,
                              src: str, dst: str, keywords=None) -> tuple[str, str]:
        """Satu panggilan untuk terjemahan + saran: separuh latensi jalur lama."""
        if src == dst:
            return text, ""
        system = (
            f"You are a precise live interpreter and conversation coach. The other person speaks {src}; "
            f"the user speaks {dst} and must reply in {src}. Use the full history so the reply stays coherent. "
            "Output exactly three lines:\n"
            f"TRANSLATION: <translation of the other person's text into {dst}>\n"
            f"REPLY: <natural short reply in {src}>\n"
            f"MEANING: <same reply translated to {dst}>"
        )
        user = (f"Context: {context_desc or '-'}\n"
                f"Names/terms: {', '.join(keywords or []) or '-'}\n\n"
                f"History:\n{history or '-'}\n\nOther person just said: {text}")
        got = _parse(self.chat(system, user), "TRANSLATION", "REPLY", "MEANING")
        saran = "\n".join(x for x in (got.get("REPLY", ""), got.get("MEANING", "")) if x)
        if not got.get("TRANSLATION"):
            return self.translate(text, src, dst), saran
        return got["TRANSLATION"], saran

    def suggest(self, context_desc: str, history: str, opponent_text: str,
                opponent_lang: str, my_lang: str) -> str:
        system = (
            "You help a non-native speaker answer live in a conversation. "
            f"The other person speaks {opponent_lang}; the user speaks {my_lang} and must reply in {opponent_lang}. "
            "Use the full history so the reply stays coherent. "
            "Output exactly two lines:\n"
            f"REPLY: <natural short reply in {opponent_lang}>\n"
            f"MEANING: <same reply translated to {my_lang}>"
        )
        user = f"Context: {context_desc or '-'}\n\nHistory:\n{history or '-'}\n\nOther person just said: {opponent_text}"
        raw = self.chat(system, user)
        got = _parse(raw, "REPLY", "MEANING", "EN", "ID")
        reply = got.get("REPLY") or got.get("EN", "")
        meaning = got.get("MEANING") or got.get("ID", "")
        return f"{reply}\n{meaning}" if reply else raw

    def summarize(self, context_desc: str, transcript: str, my_lang: str) -> str:
        system = (
            f"Summarize this conversation ONLY from its transcript, in {my_lang}. "
            "Sections: Topik; Poin Penting; Keputusan; Tindak Lanjut; Kosakata Baru. "
            "Never invent facts that are not in the transcript."
        )
        if len(transcript) <= CHUNK_CHARS:
            return self.chat(system, f"Context: {context_desc or '-'}\n\nTranscript:\n{transcript}")
        # Transkrip panjang: ringkas per potongan lalu gabungkan, agar tidak
        # melampaui konteks model dan gagal total.
        chunks, buf = [], ""
        lines = [p for line in transcript.splitlines()
                 for p in (line[i:i + CHUNK_CHARS] for i in range(0, max(1, len(line)), CHUNK_CHARS))]
        for line in lines:
            if len(buf) + len(line) + 1 > CHUNK_CHARS and buf:
                chunks.append(buf)
                buf = ""
            buf += line + "\n"
        if buf:
            chunks.append(buf)
        partials = [self.chat(
            f"Summarize this transcript excerpt faithfully in {my_lang}. List facts only, no invention.",
            f"Context: {context_desc or '-'}\n\nTranscript excerpt:\n{c}") for c in chunks]
        joined = "\n\n".join(f"Excerpt {i + 1}:\n{p}" for i, p in enumerate(partials))
        return self.chat(system, f"Context: {context_desc or '-'}\n\nPartial summaries of the full transcript:\n{joined}")


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
