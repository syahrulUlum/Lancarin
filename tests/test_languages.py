"""Daftar bahasa UI harus selalu sinkron dengan kode Deepgram Nova-3.

Jalankan: .venv\\Scripts\\python -m unittest tests.test_languages -v
"""
import unittest

from lancarin import config
from lancarin import stt


class TestLanguages(unittest.TestCase):
    def test_every_language_has_a_code(self):
        missing = [name for name in config.LANGUAGES if name not in config.LANGUAGE_CODES]
        self.assertEqual(missing, [])

    def test_at_least_nova3_multilingual_set(self):
        self.assertGreaterEqual(len(config.LANGUAGES), 55)

    def test_non_latin_languages_build_valid_url(self):
        url = stt.build_url(["Japanese", "Arabic", "Chinese (Mandarin)"], [])
        self.assertIn("language_hint=ja", url)
        self.assertIn("language_hint=ar", url)
        self.assertIn("language_hint=zh", url)


if __name__ == "__main__":
    unittest.main()
