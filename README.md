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
   (dari https://dev.meta.ai), pilih model, jalankan Tes Koneksi sampai ✓,
   lalu **Simpan** — Mulai Sesi terkunci sampai tes lolos untuk model itu.
2. Isi deskripsi konteks (opsional), pilih bahasa lawan/saya dan mode.
3. **Mulai Sesi** — putar video/panggilan; overlay menampilkan transkrip,
   terjemahan, dan saran jawaban. `F9` = mode Cek Ucapan privat.
4. **Akhiri & Ringkasan** — ringkasan sesi dibuat; ekspor `.md` berisi
   ringkasan + transkrip lengkap.

Catatan: mode privat tidak meneruskan audio ke aplikasi call; mute mic
Zoom/Meet tetap dilakukan pengguna. Fallback STT lokal dan adapter
macOS/Linux mengikuti [rencana](docs/rencana.md).

## Kemas installer (Windows)

```powershell
.venv\Scripts\python -m PyInstaller packaging\lancarin.spec
```

Hasil di `dist\Lancarin\`. Bungkus Inno Setup memakai `packaging\installer.iss`.
