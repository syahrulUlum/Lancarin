"""Regresi crash Mulai Sesi: dua capture serentak tidak boleh mematikan proses.

Jalankan: .venv\\Scripts\\python -m unittest tests.test_audio -v
"""
import time
import unittest

from lancarin import audio


class TestAudioSingleton(unittest.TestCase):
    def test_single_shared_pyaudio(self):
        self.assertIs(audio._get_pa(), audio._get_pa())

    def test_dual_capture_flows(self):
        loop, mic, _ = audio.list_devices()
        if loop is None or mic is None:
            self.skipTest("perangkat loopback/mic tidak tersedia")
        caps = [audio.Capture(loop), audio.Capture(mic)]
        for cap in caps:
            cap.start()
        time.sleep(2)
        # Regresi yang dijaga: proses tidak crash. Loopback WASAPI tidak
        # mengirim frame saat tidak ada audio diputar, jadi yang wajib
        # mengalir adalah mic; loopback cukup dibuktikan thread-nya hidup.
        alive = [cap._thread.is_alive() for cap in caps]
        for cap in caps:
            cap.stop()
        self.assertTrue(all(alive))
        self.assertGreater(caps[1].frames.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
