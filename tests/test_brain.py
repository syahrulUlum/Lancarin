"""Regresi terjemahan kosong: Brain.chat tidak boleh mengirim max_tokens
(batas kecil dimakan penalaran Muse Spark dan content kembali kosong).

Jalankan: .venv\\Scripts\\python -m unittest tests.test_brain -v
"""
import unittest

import brain as brain_mod


class _Msg:
    content = "Halo, apa kabar?"


class _Choice:
    message = _Msg()


class _Resp:
    choices = [_Choice()]


class _Completions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _Resp()


class _Chat:
    def __init__(self):
        self.completions = _Completions()


class FakeOpenAI:
    last = None

    def __init__(self, **kwargs):
        self.chat = _Chat()
        FakeOpenAI.last = self


class TestBrain(unittest.TestCase):
    def test_chat_tidak_mengirim_max_tokens(self):
        original = brain_mod.OpenAI
        brain_mod.OpenAI = FakeOpenAI
        try:
            b = brain_mod.Brain({"model": "muse-spark-1.3", "base_url": "https://x"}, "tok")
            out = b.translate("Hello, how are you?", "English", "Indonesian")
        finally:
            brain_mod.OpenAI = original
        self.assertEqual(out, "Halo, apa kabar?")
        self.assertNotIn("max_tokens", FakeOpenAI.last.chat.completions.kwargs)


if __name__ == "__main__":
    unittest.main()
