"""Regresi: DNS asyncio di thread pekerja setelah PySide6 diimpor.

Without the shared executor in stt.py this fails with
TypeError: 'lazy_import' object is not callable (Python 3.15 + PySide6).

Jalankan: .venv\\Scripts\\python -m unittest tests.test_stt_thread -v
"""
import asyncio
import threading
import unittest

import PySide6.QtWidgets  # noqa: F401  (urutan exe beku: Qt selalu lebih dulu)
from lancarin import stt


async def _dns_probe():
    loop = asyncio.get_running_loop()
    return await loop.getaddrinfo("api.deepgram.com", 443)


class TestSttThread(unittest.TestCase):
    def test_dns_in_worker_thread(self):
        result = {}

        def work():
            try:
                result["infos"] = stt.run_event_loop(_dns_probe())
            except Exception as exc:  # saved for the assertion below
                result["error"] = exc

        t = threading.Thread(target=work)
        t.start()
        t.join(timeout=20)
        self.assertNotIn("error", result, f"DNS gagal: {result.get('error')}")
        self.assertTrue(result["infos"])


if __name__ == "__main__":
    unittest.main()
