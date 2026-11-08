"""Klien streaming Deepgram Nova-3 Multilingual (WebSocket).

Interface sama seperti klien Meta sebelumnya: konstruktor menerima antrean
frame PCM 24 kHz + callback on_partial/on_final/on_error, jadi app.py tidak
perlu tahu provider-nya ganti.
"""
import asyncio
import json
import threading
from urllib.parse import urlencode
# Impor langsung dari submodul: memaksa resolusi nyata. Akses atribut
# `concurrent.futures.ThreadPoolExecutor` sesudah PySide6 diimpor (selalu
# terjadi di exe PyInstaller) menghasilkan objek lazy_import yang tidak
# bisa dipanggil dan mematikan DNS asyncio di thread pekerja.
from concurrent.futures.thread import ThreadPoolExecutor

import concurrent.futures as _futures_pkg

# asyncio memeriksa isinstance(executor, concurrent.futures.ThreadPoolExecutor)
# lewat atribut paket yang masih lazy; tanam kelas nyatanya ke paket.
_futures_pkg.ThreadPoolExecutor = ThreadPoolExecutor

import urllib.error
import urllib.request

import websockets

from . import config

def check_key(key: str) -> tuple[bool, str]:
    """Validasi API key Deepgram tanpa membuka WebSocket (GET /v1/projects)."""
    if not key:
        return False, "empty - add your Deepgram API key above"
    req = urllib.request.Request("https://api.deepgram.com/v1/projects",
                                 headers={"Authorization": f"Token {key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return (resp.status == 200), "Deepgram API key accepted"
    except urllib.error.HTTPError as exc:
        return False, "Deepgram rejected the key (401) - check it at deepgram.com" if exc.code in (401, 403) else f"Deepgram HTTP {exc.code}"
    except Exception as exc:
        return False, f"cannot reach Deepgram: {str(exc)[:100]}"


def run_event_loop(coro):
    """Jalankan coroutine di loop baru dengan executor BARU khusus loop itu.

    Jangan pernah berbagi executor antar-loop: loop.close() mematikan
    default executor-nya, dan loop berikutnya (sesi kedua, reconnect) lalu
    gagal "cannot schedule new futures after shutdown" sampai restart.
    """
    loop = asyncio.new_event_loop()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lancarin-stt")
    loop.set_default_executor(executor)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        executor.shutdown(wait=False)


def build_url(languages: list[str], keywords: list[str]) -> str:
    """URL WebSocket Deepgram: kode-switching multi + hint bahasa sesi ini."""
    params = [
        ("model", config.STT_MODEL),
        ("language", "multi"),
        ("encoding", "linear16"),
        ("sample_rate", "24000"),
        ("channels", "1"),
        ("smart_format", "true"),
        ("punctuate", "true"),
        ("interim_results", "true"),
        # Endpointing berbasis model (bukan hening energi): 300ms jeda
        # menutup ucapan; interim tetap mengalir selama bicara panjang.
        ("endpointing", "300"),
        ("utterance_end_ms", "1000"),
        ("vad_events", "true"),
    ]
    for lang in languages:
        code = config.LANGUAGE_CODES.get(lang)
        if code:
            params.append(("language_hint", code))
    for word in keywords:
        if word.strip():
            params.append(("keyterm", word.strip()))
    return "wss://api.deepgram.com/v1/listen?" + urlencode(params)


class RealtimeSTT(threading.Thread):
    """One transcription session. Callbacks: on_partial(str), on_final(str), on_error(str)."""

    def __init__(self, token: str, frames, languages: list[str], keywords: list[str],
                 on_partial, on_final, on_error):
        super().__init__(daemon=True)
        self.token = token  # Deepgram API key
        self.frames = frames  # queue.Queue[bytes] PCM 24 kHz
        self.languages = languages
        self.keywords = keywords
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_error = on_error
        self._stopped = threading.Event()
        self._loop = None
        self._ws = None
        self._committed: list[str] = []  # segmen is_final dalam ucapan berjalan
        self._current = ""  # interim segmen aktif

    def stop(self):
        self._stopped.set()
        ws, loop = self._ws, self._loop
        if ws is not None and loop is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(ws.close()))

    def run(self):
        # Reconnect once: a brief drop (including a clean server close)
        # must not silently kill the session.
        for attempt in range(2):
            if self._stopped.is_set():
                return
            try:
                run_event_loop(self._main())
                exc = RuntimeError("Koneksi STT ditutup server")
            except Exception as err:
                exc = err
            if self._stopped.is_set():
                return
            if attempt == 1:
                self.on_error(str(exc)[:200])
            else:
                self._stopped.wait(1.0)

    def _partial_text(self) -> str:
        parts = self._committed + ([self._current] if self._current else [])
        return " ".join(parts).strip()

    def _flush_final(self):
        text = self._partial_text()
        self._committed, self._current = [], ""
        if text:
            self.on_final(text)

    def _handle_event(self, event: dict):
        kind = event.get("type")
        if kind == "Error":
            raise RuntimeError(event.get("description") or event.get("message", "STT error"))
        if kind == "UtteranceEnd":
            self._flush_final()
            return
        if kind != "Results":
            return
        try:
            text = event["channel"]["alternatives"][0].get("transcript", "").strip()
        except (KeyError, IndexError, TypeError, AttributeError):
            return
        if event.get("is_final"):
            if text:
                self._committed.append(text)
            self._current = ""
        elif text:
            self._current = text
        if event.get("speech_final"):
            self._flush_final()
        else:
            partial = self._partial_text()
            if partial:
                self.on_partial(partial)

    async def _main(self):
        url = build_url(self.languages, self.keywords)
        headers = {"Authorization": f"Token {self.token}"}
        async with websockets.connect(url, additional_headers=headers,
                                      open_timeout=20, max_size=None) as ws:
            self._loop = asyncio.get_running_loop()
            self._ws = ws
            if self._stopped.is_set():
                return  # stop datang saat connect: langsung tutup lewat async with

            async def send_audio():
                loop = asyncio.get_running_loop()
                while not self._stopped.is_set():
                    chunk = await loop.run_in_executor(None, self._next_chunk)
                    if chunk:
                        await ws.send(chunk)
                try:
                    await ws.send(json.dumps({"type": "CloseStream"}))
                except Exception:
                    pass

            sender = asyncio.create_task(send_audio())
            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        continue
                    self._handle_event(json.loads(message))
            finally:
                sender.cancel()

    def _next_chunk(self):
        try:
            return self.frames.get(timeout=0.25)
        except Exception:
            return b""
