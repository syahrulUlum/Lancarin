"""Klien streaming Muse Voice Transcribe (WebSocket realtime Meta)."""
import asyncio
import json
import threading

import websockets

import config

URL = "wss://api.meta.ai/v1/asr/realtime"


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

    def stop(self):
        self._stopped.set()

    def run(self):
        try:
            asyncio.run(self._main())
        except Exception as exc:
            if not self._stopped.is_set():
                self.on_error(str(exc)[:200])

    async def _main(self):
        async with websockets.connect(URL, open_timeout=20, max_size=None) as ws:
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
            reply = json.loads(await ws.recv())
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
