"""Start Session crash regression: two simultaneous captures must not kill the process.

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
            self.skipTest("loopback/microphone device unavailable")
        caps = [audio.Capture(loop), audio.Capture(mic)]
        for cap in caps:
            cap.start()
        time.sleep(2)
        # The guarded regression is a crash. WASAPI loopback sends no frames
        # while nothing is playing, so the mic must flow and the loopback
        # thread only has to stay alive.
        alive = [cap._thread.is_alive() for cap in caps]
        for cap in caps:
            cap.stop()
        self.assertTrue(all(alive))
        self.assertGreater(caps[1].frames.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
