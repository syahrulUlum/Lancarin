"""Catatan sesi: giliran bicara berlabel + ekspor Markdown."""
import time
from dataclasses import dataclass, field


@dataclass
class Turn:
    speaker: str  # "Lawan" atau "Saya"
    text: str
    translation: str = ""
    at: float = field(default_factory=time.time)


class Session:
    def __init__(self, context_desc: str = ""):
        self.context_desc = context_desc
        self.turns: list[Turn] = []
        self.started = time.strftime("%Y-%m-%d %H:%M")

    def add(self, speaker: str, text: str, translation: str = "") -> Turn:
        turn = Turn(speaker, text.strip(), translation.strip())
        if turn.text:
            self.turns.append(turn)
        return turn

    def history_text(self, limit: int = 20) -> str:
        lines = []
        for t in self.turns[-limit:]:
            line = f"{t.speaker}: {t.text}"
            if t.translation:
                line += f" ({t.translation})"
            lines.append(line)
        return "\n".join(lines)

    def transcript_text(self) -> str:
        lines = []
        for t in self.turns:
            stamp = time.strftime("%H:%M:%S", time.localtime(t.at))
            line = f"[{stamp}] {t.speaker}: {t.text}"
            if t.translation:
                line += f"\n    -> {t.translation}"
            lines.append(line)
        return "\n".join(lines)

    def export_md(self, summary: str = "") -> str:
        parts = [f"# Lancarin - Session Transcript\n\nStarted: {self.started}\n"]
        if self.context_desc:
            parts.append(f"Context: {self.context_desc}\n")
        if summary:
            parts.append(f"## Summary\n\n{summary}\n")
        parts.append("## Full Transcript\n\n" + (self.transcript_text() or "_(empty)_"))
        return "\n".join(parts)
