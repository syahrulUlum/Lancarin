"""Deepgram STT: URL building + Results event handling (tanpa jaringan).

Jalankan: .venv\\Scripts\\python -m unittest tests.test_deepgram_stt -v
"""
import unittest

from lancarin import stt


def _results(text, is_final=False, speech_final=False):
    return {"type": "Results", "is_final": is_final, "speech_final": speech_final,
            "channel": {"alternatives": [{"transcript": text}]}}


class TestDeepgramUrl(unittest.TestCase):
    def test_url_is_nova3_multilingual_with_hints(self):
        url = stt.build_url(["English", "Indonesian"], ["Lancarin"])
        self.assertIn("model=nova-3", url)
        self.assertIn("language=multi", url)
        self.assertIn("language_hint=en", url)
        self.assertIn("language_hint=id", url)
        self.assertIn("interim_results=true", url)
        self.assertIn("keyterm=Lancarin", url)
        self.assertIn("sample_rate=24000", url)


class TestDeepgramEvents(unittest.TestCase):
    def test_partial_accumulates_and_speech_final_flushes(self):
        partials, finals, errors = [], [], []
        s = stt.RealtimeSTT("key", None, ["English"], [], partials.append, finals.append, errors.append)
        s._handle_event(_results("hello"))
        s._handle_event(_results("hello how are"))  # interim segmen aktif diganti
        s._handle_event(_results("hello how are you", is_final=True))
        s._handle_event(_results("today", is_final=True, speech_final=True))
        self.assertEqual(partials[0], "hello")
        self.assertEqual(partials[-1], "hello how are you")
        self.assertEqual(finals, ["hello how are you today"])
        self.assertEqual(errors, [])
        # Ucapan berikutnya mulai bersih.
        s._handle_event(_results("next"))
        self.assertEqual(partials[-1], "next")


if __name__ == "__main__":
    unittest.main()
