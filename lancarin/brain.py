"""Lancarin AI brain: translation, reply suggestions, summaries.

Provider-agnostic: any OpenAI-compatible endpoint (Groq, OpenAI, OpenRouter,
Cerebras, ...) configured via base_url + model names + API key in Settings.
"""
import time

from openai import OpenAI

from . import config

CHUNK_CHARS = 8000


def _parse(raw: str, *labels: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current = None
    for line in raw.splitlines():
        cleaned = line.strip().strip("*").strip()
        hit = next((lb for lb in labels if cleaned.upper().startswith(lb + ":")), None)
        if hit:
            current = hit
            out[hit] = cleaned[len(hit) + 1:].strip().strip("*").strip()
        elif current and line.strip():
            out[current] += "\n" + line.strip()
    return out


class Brain:
    def __init__(self, cfg: dict, token: str):
        self.cfg = cfg
        # timeout per panggilan di chat(): default OpenAI (600 dtk x3) membuat
        # satu panggilan macet membekukan overlay tanpa kabar. Terukur di mesin
        # ini: ping 2-4 dtk, panggilan gabungan pernah >20 dtk.
        self.client = OpenAI(api_key=token, base_url=cfg["base_url"],
                             timeout=60.0, max_retries=1)
        self.model = cfg["model"]
        self.translate_model = cfg.get("translate_model") or cfg["model"]

    def chat(self, system: str, user: str, timeout: float = 60.0, model: str = None) -> str:
        # Tanpa max_tokens: pada model reasoning batas kecil dimakan proses
        # berpikirnya dan konten final kembali kosong.
        r = self.client.chat.completions.create(
            model=model or self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            timeout=timeout,
        )
        return (r.choices[0].message.content or "").strip()

    def translate(self, text: str, src: str, dst: str) -> str:
        if src == dst or not text.strip():
            return text
        return self.chat(
            f"You are a precise live interpreter. Translate from {src} to {dst}. "
            "The text may be an unfinished sentence fragment; translate what is there. "
            "Output ONLY the translation, no quotes, no notes.",
            text, timeout=15.0, model=self.translate_model,
        )

    def suggest(self, context_desc: str, history: str, opponent_text: str,
                opponent_lang: str, my_lang: str, keywords=None) -> list[tuple[str, str]]:
        """Up to 3 reply options as (reply, meaning) pairs, best first."""
        system = (
            "You help a non-native speaker answer live in a conversation. "
            f"The other person speaks {opponent_lang}; the user speaks {my_lang} and must reply in {opponent_lang}. "
            "Use the full history so the replies stay coherent. "
            "Rules for every option:\n"
            "- ANSWER the question or respond to the statement directly. Do not change the topic.\n"
            "- Do NOT invent personal facts about the user: no made-up movie titles, experiences, names, numbers, or opinions they never stated. "
            "When a personal detail is unknown, use an honest general answer anyone could truthfully say "
            "(e.g. \"Not much lately, work has kept me busy\" instead of naming a show).\n"
            "- At most ONE option may end with a short follow-up question, and only after it answers first. "
            "Options that only ask back without answering are wrong.\n"
            "- Make the 3 options genuinely different stances (e.g. positive/direct, brief/casual, answer + follow-up), not rewordings.\n"
            "- Keep each reply to one easy sentence a non-native speaker can say aloud.\n"
            "Output ONLY in exactly this format, no intro text:\n"
            f"REPLY1: <reply in {opponent_lang}>\nMEANING1: <same reply in {my_lang}>\n"
            f"REPLY2: <reply in {opponent_lang}>\nMEANING2: <same reply in {my_lang}>\n"
            f"REPLY3: <reply in {opponent_lang}>\nMEANING3: <same reply in {my_lang}>"
        )
        user = (f"Context: {context_desc or '-'}\nNames/terms: {', '.join(keywords or []) or '-'}\n\n"
                f"History:\n{history or '-'}\n\nOther person just said: {opponent_text}")
        # Saran yang datang setelah 25 detik sudah tidak berguna untuk percakapan
        # langsung; gagal cepat lebih baik daripada panel menggantung seminit.
        raw = self.chat(system, user, timeout=25.0)
        labels = [f"{kind}{i}" for i in (1, 2, 3) for kind in ("REPLY", "MEANING")]
        got = _parse(raw, *labels, "REPLY", "MEANING")
        options = []
        for i in (1, 2, 3):
            reply = got.get(f"REPLY{i}", "").strip()
            if reply:
                options.append((reply, got.get(f"MEANING{i}", "").strip()))
        if not options:  # format lama / model bandel: satu pilihan apa adanya
            reply = (got.get("REPLY") or "").strip()
            if reply:
                options.append((reply, (got.get("MEANING") or "").strip()))
            elif raw.strip():
                options.append((raw.strip().splitlines()[0], ""))
        return options

    def summarize(self, context_desc: str, transcript: str, my_lang: str) -> str:
        system = (
            f"Summarize this conversation ONLY from its transcript, in {my_lang}. "
            "Sections: Topic; Key Points; Decisions; Follow-ups; New Vocabulary. "
            "Never invent facts that are not in the transcript."
        )
        if len(transcript) <= CHUNK_CHARS:
            return self.chat(system, f"Context: {context_desc or '-'}\n\nTranscript:\n{transcript}")
        # Long transcript: summarize chunk by chunk, then combine, so it never
        # exceeds the model context and fails outright.
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
    """Test each selected model separately (translation + suggestions)."""
    if not token:
        return [("Brain API key", False, "Brain API key is empty - add it in Settings first.")]
    steps: list[tuple[str, bool, str]] = []
    targets = [("Translation model", cfg.get("translate_model") or cfg["model"]),
               ("Suggestions and summary model", cfg["model"])]
    seen = set()
    for label, model in targets:
        if model in seen:
            continue
        seen.add(model)
        try:
            brain = Brain({**cfg, "model": model}, token)
            start = time.time()
            reply = brain.chat("Reply with exactly: OK", "ping", timeout=30.0)
            ms = int((time.time() - start) * 1000)
            ok = "OK" in reply.upper()
            steps.append((f"{label} ({model})", ok,
                          f"replied in {ms / 1000:.1f}s" if ok else f"unexpected reply: {reply[:80]}"))
        except Exception as exc:  # actionable cause
            msg = str(exc)
            hint = "Check the API key and selected model." if "401" in msg or "auth" in msg.lower() else "Check your internet connection / Base URL."
            steps.append((f"{label} ({model})", False, f"{msg[:140]} - {hint}"))
    return steps
