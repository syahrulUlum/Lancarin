"""Regresi: DNS asyncio di thread pekerja setelah PySide6 diimpor.

Tanpa executor bersama di stt.py, ini gagal dengan
TypeError: 'lazy_import' object is not callable (Python 3.15 + PySide6).

Jalankan: .venv\\Scripts\\python -m unittest tests.test_stt_thread -v
"""
import asyncio
import threading
import unittest

import stt  # impor sebelum PySide6, sama seperti app.py
import PySide6.QtWidgets  # noqa: F401  (memicu kondisi aslinya)


async def _dns_probe():
    loop = asyncio.get_running_loop()
    return await loop.getaddrinfo("api.meta.ai", 443)


class TestSttThread(unittest.TestCase):
    def test_dns_in_worker_thread(self):
        result = {}

        def work():
            try:
                result["infos"] = stt.run_event_loop(_dns_probe())
            except Exception as exc:  # simpan untuk assertion di bawah
                result["error"] = exc

        t = threading.Thread(target=work)
        t.start()
        t.join(timeout=20)
        self.assertNotIn("error", result, f"DNS gagal: {result.get('error')}")
        self.assertTrue(result["infos"])


if __name__ == "__main__":
    unittest.main()
