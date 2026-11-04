"""Audio capture: system loopback (other party) + microphone (you) -> 24 kHz mono PCM.

Windows memakai WASAPI loopback via PyAudioWPatch. Perangkat non-Windows
(monitor PipeWire/PulseAudio, BlackHole) dipilih dari daftar perangkat yang sama.
"""
import queue
import threading

import numpy as np
import pyaudiowpatch as pyaudio

TARGET_RATE = 24000

_pa_lock = threading.Lock()
_pa_singleton = None


def _get_pa():
    """Satu instance PyAudio bersama: inisialisasi PortAudio serentak dari
    beberapa thread memicu assertion natif yang mematikan proses."""
    global _pa_singleton
    with _pa_lock:
        if _pa_singleton is None:
            _pa_singleton = pyaudio.PyAudio()
        return _pa_singleton


def _to_pcm24(data: bytes, rate: int, channels: int) -> bytes:
    samples = np.frombuffer(data, dtype=np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != TARGET_RATE:
        n = max(1, int(len(samples) * TARGET_RATE / rate))
        samples = np.interp(np.linspace(0, len(samples), n, endpoint=False),
                            np.arange(len(samples)), samples)
    return (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()


def list_devices():
    """Kembalikan (loopback_index, mic_index, daftar nama) untuk UI."""
    pa = _get_pa()
    try:
        loopback = None
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            out_id = wasapi["defaultOutputDevice"]
            speakers = pa.get_device_info_by_index(out_id)
            if speakers.get("isLoopbackDevice"):
                loopback = out_id
            else:
                candidates = list(pa.get_loopback_device_info_generator())
                match = [d for d in candidates if speakers["name"] in d["name"]]
                chosen = (match or candidates or [None])[0]
                loopback = chosen["index"] if chosen else None
        except Exception:
            pass
        mic = None
        try:
            mic = pa.get_default_input_device_info()["index"]
        except Exception:
            pass
        names = []
        for i in range(pa.get_device_count()):
            try:
                names.append(pa.get_device_info_by_index(i)["name"])
            except Exception:
                names.append(f"device {i}")
        return loopback, mic, names
    finally:
        pass  # instance bersama tidak diterminasi per panggilan


class Capture:
    """One device stream -> a queue of 24 kHz PCM chunks (bytes)."""

    def __init__(self, device_index: int, on_error=None):
        self.device_index = device_index
        self.on_error = on_error
        self.frames: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self.level = 0.0
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def wait(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    def _run(self):
        pa = _get_pa()
        stream = None
        try:
            info = pa.get_device_info_by_index(self.device_index)
            rate = int(info["defaultSampleRate"])
            channels = max(1, min(2, int(info["maxInputChannels"]) or 1))
            stream = pa.open(format=pyaudio.paFloat32, channels=channels, rate=rate,
                             input=True, input_device_index=self.device_index,
                             frames_per_buffer=2048)
            while not self._stop.is_set():
                data = stream.read(2048, exception_on_overflow=False)
                arr = np.frombuffer(data, dtype=np.float32)
                self.level = float(np.abs(arr).mean()) if arr.size else 0.0
                try:
                    self.frames.put_nowait(_to_pcm24(data, rate, channels))
                except queue.Full:
                    pass
        except Exception as exc:
            # Jangan raise di thread: exe tanpa konsol menelannya diam-diam.
            if not self._stop.is_set() and self.on_error:
                self.on_error(str(exc)[:200])
        finally:
            if stream:
                stream.close()
