# Lancarin

Asisten desktop real-time yang menangkap & menerjemahkan audio Zoom, Meet, dan
YouTube, lalu memberi saran jawaban berbahasa Inggris yang nyambung dengan
konteks percakapan. Untuk profesional Indonesia, didukung Muse Spark &
Muse Voice Transcribe dari Meta Model API.

Rencana lengkap: [docs/rencana.md](docs/rencana.md)

## Menjalankan (pengembangan)

Prasyarat: Python 3.15, headset (mencegah echo).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

1. Klik **Pengaturan & Tes Koneksi**, isi token Meta Model API
   (dari https://dev.meta.ai), pilih model terjemahan dan model
   saran/ringkasan, jalankan Tes Koneksi sampai ✓, lalu **Simpan** —
   Mulai Sesi terkunci sampai tes lolos untuk kombinasi itu.
2. Buka menu **⚙ Pengaturan Sesi** bila perlu: isi deskripsi konteks
   (opsional), pilih bahasa lawan/saya dan mode. Menu ini terlipat
   bawaan agar kotak percakapan lega.
3. **Mulai Sesi** — putar video/panggilan; panel di dalam aplikasi
   menampilkan transkrip, terjemahan besar (tombol A−/A+), dan saran
   jawaban. `F9` = mode Cek Ucapan privat.
4. **Akhiri & Ringkasan** — ringkasan sesi dibuat; ekspor `.md` berisi
   ringkasan + transkrip lengkap.

Catatan: mode privat tidak meneruskan audio ke aplikasi call; mute mic
Zoom/Meet tetap dilakukan pengguna. Fallback STT lokal dan adapter
macOS/Linux mengikuti [rencana](docs/rencana.md).

## Hasil uji di mesin pengembangan (4 Nov 2026)

- Tes Koneksi lolos. Terjemahan memakai model terjemahan pilihan
  (bawaan `muse-wonder-1.0`, terukur tampil ±2,5 detik) dan tampil
  duluan; saran jawaban menyusul paralel dari model saran pilihan
  (total ±8 detik). Streaming tidak membantu: token pertama model
  reasoning baru keluar setelah 5–7 detik.
- STT asli (ucapan TTS → loopback → WebSocket): transkrip parsial mengalir
  tiap ±0,3 detik, final tepat saat ucapan selesai.
- Aplikasi diam: ±123 MB RAM. Skenario interview 6 pertanyaan: saran
  nyambung dengan konteks dan riwayat.
- Belum teruji: installer di mesin bersih, sesi 60 menit, mode privat
  dengan perangkat kedua.

## Kemas installer (Windows)

```powershell
.venv\Scripts\python -m PyInstaller packaging\lancarin.spec
```

Hasil di `dist\Lancarin\`. Bungkus Inno Setup memakai `packaging\installer.iss`.
