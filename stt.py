"""Klien streaming Muse Voice Transcribe (WebSocket realtime Meta)."""
import asyncio
import json
import threading
# Impor langsung dari submodul: memaksa resolusi nyata. Akses atribut
# `concurrent.futures.ThreadPoolExecutor` sesudah PySide6 diimpor (selalu
# terjadi di exe PyInstaller) menghasilkan objek lazy_import yang tidak
# bisa dipanggil dan mematikan DNS asyncio di thread pekerja.
from concurrent.futures.thread import ThreadPoolExecutor

import concurrent.futures as _futures_pkg

# asyncio memeriksa isinstance(executor, concurrent.futures.ThreadPoolExecutor)
# lewat atribut paket yang masih lazy; tanam kelas nyatanya ke paket.
_futures_pkg.ThreadPoolExecutor = ThreadPoolExecutor

import websockets

import config

URL = "wss://api.meta.ai/v1/asr/realtime"

EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lancarin-stt")


def run_event_loop(coro):
    """Jalankan coroutine di loop baru dengan executor bersama di atas."""
    loop = asyncio.new_event_loop()
    loop.set_default_executor(EXECUTOR)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class RealtimeSTT(threading.Thread):
    """Satu sesi transkripsi. Callback: on_partial(str), on_final(str), on_error(str)."""

    def __init__(self, token: str, frames, languages: list[str], keywords: list[str],
                 on_partial, on_final, on_error):
        super().__init__(daemon=True)
        self.token = token
        self.frames = frames  # queue.Queue[bytes] PCM 24 kHz
        self.languages = languages
        self.keywords = keywords
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_error = on_error
        self._stopped = threading.Event()
        self._loop = None
        self._ws = None

    def stop(self):
        self._stopped.set()
        ws, loop = self._ws, self._loop
        if ws is not None and loop is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(ws.close()))

    def run(self):
        # Satu kali reconnect: putus sesaat (termasuk tutup bersih dari server)
        # tidak boleh membunuh sesi diam-diam.
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

    async def _main(self):
        async with websockets.connect(URL, open_timeout=20, max_size=None) as ws:
            self._loop = asyncio.get_running_loop()
            self._ws = ws
            if self._stopped.is_set():
                return  # stop datang saat connect: langsung tutup lewat async with
            handshake = {
                "authorization": {"accessToken": f"Bearer {self.token}"},
                "audioEncoding": "PCM_24KHZ",
                "model": config.STT_MODEL,
                "mode": "ENDPOINTING",
                "partialMode": "CUMULATIVE",
                "emitAudioProgress": False,
                "languageBias": self.languages,
            }
            if self.keywords:
                handshake["keywords"] = self.keywords
            await ws.send(json.dumps(handshake))
            reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            if "sessionId" not in reply:
                raise RuntimeError(f"Handshake gagal: {reply}")

            async def send_audio():
                loop = asyncio.get_running_loop()
                while not self._stopped.is_set():
                    chunk = await loop.run_in_executor(None, self._next_chunk)
                    if chunk:
                        await ws.send(chunk)
                await ws.send(json.dumps({"type": "endStream"}))

            sender = asyncio.create_task(send_audio())
            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        continue
                    event = json.loads(message)
                    kind = event.get("type")
                    if kind == "error":
                        raise RuntimeError(event.get("message", "STT error"))
                    if kind == "transcript" and not event.get("final", True):
                        self.on_partial(event.get("transcript", ""))
                    elif kind == "speechComplete":
                        text = event.get("transcript", "").strip()
                        if text:
                            self.on_final(text)
            finally:
                sender.cancel()

    def _next_chunk(self):
        try:
            return self.frames.get(timeout=0.25)
        except Exception:
            return b""
