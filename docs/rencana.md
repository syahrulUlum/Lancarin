# Lancarin — Rencana Final (patokan arah, jangan diubah tanpa diskusi)

Status: SEDANG DIEKSEKUSI (mulai 3 Nov 2026). Dokumen ini merangkum seluruh
diskusi sampai 3 Nov 2026 dan menjadi satu-satunya patokan eksekusi.
Lokasi kanonis: `docs/rencana.md` (salinan lama di `.agents/plans/` diabaikan git).

## Goal

Lancarin: aplikasi desktop ringan (Windows, macOS, Linux) untuk profesional,
freelancer, dan kreator Indonesia yang menangkap audio sistem (Zoom, Meet,
YouTube), mentranskripsi + menerjemahkan real-time, memberi saran jawaban yang
nyambung selama percakapan, menutup sesi dengan ringkasan + transkrip lengkap,
dan dibagikan sebagai installer sekali klik (juri tidak perlu Python/terminal).

## Keputusan yang sudah dikunci

1. Bahasa & UI: Python + PySide6 (Qt for Python). Electron DITOLAK: menanam
   Chromium + Node per aplikasi (lebih berat saat jalan), sedangkan loopback
   audio dan fallback Whisper hidup di ekosistem Python; Electron tetap butuh
   sidecar Python sehingga lebih berat dan installer lebih rapuh.
2. Python yang dipakai: versi terbaru resmi. Di mesin ini sudah terpasang
   Python 3.15.2 (C:\Users\Suki\AppData\Local\Programs\Python\Python315),
   terverifikasi `Python 3.15.2` + pip 26.2.2; Python 3.14.7 lama TIDAK dihapus.
   Lingkungan proyek wajib `.venv` di root proyek (dibuat saat eksekusi, belum
   sekarang). Risiko dicatat: wheel PySide6/PyAudioWPatch/ctranslate2 untuk
   3.15 harus dibuktikan di spike; STT utama berbasis cloud sehingga fallback
   lokal boleh menyusul bila wheel-nya belum tersedia.
3. "Ringan" = ringan saat dijalankan (CPU/RAM), dibuktikan dengan anggaran
   terukur saat validasi, bukan klaim. Tanpa model besar yang diunduh di awal.
4. Transkripsi utama: Muse Voice Transcribe via WebSocket
   `wss://api.meta.ai/v1/asr/realtime` (PCM mono 24 kHz, $0,18/jam).
   Penalaran/terjemahan/saran/ringkasan: Muse Spark via Meta Model API.
   Fallback lokal opsional: faster-whisper `small` (hanya diunduh bila mode
   offline dinyalakan).
5. Capture audio sistem per-OS di balik satu antarmuka `audio.py`:
   Windows = WASAPI loopback (PyAudioWPatch, tanpa driver tambahan);
   macOS = BlackHole (diinstal pengguna, dibantu wizard cek perangkat);
   Linux = monitor source PulseAudio/PipeWire (`<sink>.monitor`).
   Urutan: Windows dulu sampai demo jalan, lalu adapter Mac/Linux.
6. Pengaturan wajib ada sebelum fitur: token Meta disimpan via `keyring`
   ke brankas OS (Credential Manager/Keychain/Secret Service), tidak pernah
   polos di berkas; UI hanya menampilkan karakter terakhir token.
   Dropdown model penalaran: `muse-spark-1.3` (default), `muse-spark-1.2`,
   varian `contributor`, `muse-wonder-1.0`. Model transkripsi tetap
   `muse-voice-transcribe-1.0`. Kolaps Lanjutan: `base_url` cadangan
   kompatibel OpenAI. Ganti token/model berlaku mulai sesi berikutnya.
7. Tes Koneksi satu tombol, tiga lapis: (1) token valid + model terakses,
   (2) percakapan mungil + latensi, (3) level meter loopback/mic + 3 detik
   uji transkripsi. Hasil per lapis dengan saran perbaikan. Sesi tidak boleh
   mulai bila token kosong/tes gagal (pesan yang bisa ditindaklanjuti).
8. Layar persiapan sebelum Start: deskripsi konteks OPSIONAL (situasi, peran),
   bahasa lawan + bahasa saya dari 25 bahasa Muse Voice (preset
   Indonesia<->English di atas), kata kunci/nama penting diteruskan sebagai
   `keywords` biasing STT dan masuk system prompt Muse Spark.
9. Dua mode: Terjemahan saja; Percakapan (saran jawaban bahasa target +
   terjemahan, konsisten dengan buffer percakapan; ucapan pengguna sendiri
   tertangkap masuk konteks walau tidak mengikuti saran; deteksi lupa kata
   dari jeda/transkrip parsial). Mode Cek Ucapan menerjemahkan ucapan
   pengguna hanya di dalam Lancarin.
10. Hotkey mute aplikasi call: OPSIONAL, default MATI, bisa diatur per
    aplikasi. Semantik tahan-untuk-privat (kirim keystroke mute saat ditahan,
    unmute saat dilepas), preset awal Zoom `Alt+A` (Win) / `Cmd+Shift+A` (Mac)
    dan semua preset bisa diedit. Mekanisme utama tetap: Lancarin tidak pernah
    meneruskan audio mic; pengguna mute di aplikasi call. Hotkey sintetis
    tidak dijamin (fokus/global shortcut, izin Accessibility macOS, Wayland).
11. Akhiri Sesi: ringkasan terstruktur (topik, poin penting, keputusan,
    tindak lanjut, kosakata baru) hanya dari transkrip sesi + ekspor `.md`
    berisi ringkasan dan transkrip lengkap berlabel Lawan/Saya + timestamp.
    Tidak ada penyimpanan audio; teks hanya lokal.
12. Garis finis = installer lolos uji di mesin bersih, bukan kode jalan di
    laptop pengembang. PyInstaller membundel interpreter; Windows dibungkus
    Inno Setup jadi `Lancarin-Setup.exe` (shortcut + uninstaller). PyInstaller
    bukan cross-compiler: paket macOS `.dmg` dan Linux AppImage dibangun di
    OS masing-masing dari spesifikasi yang sama.
13. Ditolak: membundel token pengembang ke installer; TTS berbicara
    menggantikan pengguna; bot join meeting; ganti model/bahasa di tengah
    sesi; SeamlessM4T untuk MVP; tanda tangan kode berbayar.

## Struktur kode (saat eksekusi nanti)

`app.py` (layar persiapan + overlay), `settings.py` (token/model/tes
koneksi), `audio.py`, `stt.py`, `brain.py`, `session.py`, `config.py`,
`packaging/` (spesifikasi PyInstaller + skrip Inno Setup).

## Langkah eksekusi (belum dimulai)

1. Spike risiko terbesar (±3 jam): buat `.venv` dengan Python 3.15.2,
   buktikan loopback Windows + transkripsi realtime Meta + satu panggilan
   Muse Spark + ketersediaan wheel dependensi di 3.15. Gagal token dari
   Indonesia = berhenti dan lapor.
2. Pengaturan + Tes Koneksi (±2 jam) — sebelum fitur apa pun.
3. Layar persiapan + Mode Terjemahan (±3 jam).
4. Mode Percakapan + hotkey privat opsional + Akhiri Sesi (±4 jam).
5. Kemasan installer + uji mesin bersih tanpa Python (±3 jam):
   instal -> isi token -> tes koneksi -> putar YouTube -> transkrip tampil.
6. Persiapan manual pemilik: token Meta sendiri, headset, perangkat kedua
   untuk uji call, satu mesin bersih untuk uji installer.

## Validasi

- Token salah gagal di lapis 1 Tes Koneksi; token benar hijau tiga lapis.
- Skenario interview 6 pertanyaan dengan konteks "interview marketing":
  saran memakai konteks + riwayat; ringkasan menyebut topik, >=3 poin
  penting, tindak lanjut yang benar-benar dibicarakan (tanpa mengarang).
- Bahasa EN->ID, ID->EN, + satu pasangan lain dari 25 bahasa Meta.
- Mode privat tidak terdengar di perangkat call kedua; video 10 menit
  tanpa crash; fallback aktif saat Wi-Fi mati.
- Anggaran ringan diukur (Task Manager/Activity Monitor): sesi berhenti =
  transkripsi berhenti; angka dicatat di README rilis.

## Risiko utama

- Ketersediaan token Meta Model API dari Indonesia belum terverifikasi
  (gerbang Langkah 1; rencana B `base_url` cadangan).
- Wheel dependensi untuk Python 3.15 bisa belum lengkap (dibuktikan di spike;
  fallback lokal boleh ditunda, jalur cloud tidak terpengaruh).
- Installer tanpa tanda tangan memicu SmartScreen/Gatekeeper: siapkan
  penjelasan "Run anyway" + `.zip` portabel cadangan; nyatakan ke juri.
- Hotkey mute antar-aplikasi tidak 100% andal lintas OS: fitur pendamping,
  jangan jadikan janji utama demo.

## Sumber

- Meta Model API & harga: https://dev.meta.ai/products/meta-model-api/
- ID model Meta: https://dev.meta.ai/docs/models
- STT Meta (WebSocket, 25 bahasa): https://dev.meta.ai/docs/speech-to-text
- Python terbaru (3.15.2): https://www.python.org/downloads/
- Electron (alasan ditolak): https://www.electronjs.org/docs/latest/
- PyInstaller: https://pyinstaller.org/en/stable/
- Inno Setup: https://jrsoftware.org/isinfo.php
- keyring: https://github.com/jaraco/keyring
- PyAudioWPatch: https://github.com/s0d3s/PyAudioWPatch
- BlackHole: https://github.com/ExistentialAudio/BlackHole
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
