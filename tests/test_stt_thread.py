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


async def _executor_probe():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: 42)


class TestSttThread(unittest.TestCase):
    def test_event_loop_reusable_after_close(self):
        # Regresi: executor bersama dimatikan loop.close() pertama, sehingga
        # sesi kedua gagal "cannot schedule new futures after shutdown" dan
        # aplikasi harus direstart. Setiap loop harus punya executor sendiri.
        self.assertEqual(stt.run_event_loop(_executor_probe()), 42)
        self.assertEqual(stt.run_event_loop(_executor_probe()), 42)

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
