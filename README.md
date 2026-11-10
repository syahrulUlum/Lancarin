# 🎙️ Lancarin

**Asisten percakapan real-time untuk Windows — versi 1.0.0**

Dengarkan klien di Zoom/Meet, pahami ucapannya dalam bahasa Anda saat itu
juga, dan dapatkan pilihan jawaban yang siap diucapkan.

🔗 **Download:** [Lancarin-Setup-1.0.0.exe](https://github.com/syahrulUlum/Lancarin/releases/tag/v1.0.0)

---

## ✨ Cara kerjanya

```text
🗣️ Klien berbicara
   → 🎧 Ditranskrip langsung (Deepgram Nova-3, 55 bahasa)
   → 🌐 Diterjemahkan per klausa, sambil klien masih berbicara
   → 💡 Muncul maks. 3 pilihan jawaban: DIRECT · CASUAL · ANOTHER ANGLE
   → 👆 Klik pilihan untuk menyalin, lalu ucapkan / tempel ke chat
```

Untuk bahasa beraksara non-Latin (Arab, Mandarin, Jepang, Korea, Rusia, …)
setiap teks dilengkapi **cara baca Latin** (pinyin, romaji, romanisasi) —
di ucapan klien, di terjemahan, dan di setiap pilihan jawaban.

## 🚀 Mulai dalam 3 langkah

1. **⬇️ Install** — unduh installer dari link di atas, jalankan.
   (Peringatan SmartScreen? Pilih *More info → Run anyway*.)
2. **🔑 Isi 2 API key** di menu **Settings**, lalu **Test Connection**
   sampai semua ✓ dan **Save**:
   - **Deepgram** — untuk transkripsi: [deepgram.com](https://deepgram.com)
   - **Brain** (terjemahan & saran) — provider OpenAI-compatible apa pun:
     [Groq](https://console.groq.com/docs/models) ·
     [OpenAI](https://platform.openai.com/docs/models) ·
     [OpenRouter](https://openrouter.ai/models) ·
     [Cerebras](https://www.cerebras.ai/)
3. **▶️ Tekan Start** — pilih bahasa klien & bahasa Anda, pastikan
   **Mode: Conversation** (agar saran muncul), lalu mulai percakapan.

🎧 Gunakan headset agar suara klien tidak terekam ulang oleh mikrofon.

## 🧩 Fitur utama

| | |
|---|---|
| ⚡ **Transkripsi streaming** | Teks muncul saat klien masih berbicara, tanpa menunggu hening |
| 🌐 **Terjemahan bertahap** | Per klausa, tetap bisa mengikuti pembicaraan panjang |
| 💡 **3 pilihan jawaban** | Sikap berbeda-beda, masing-masing dengan artinya; klik untuk menyalin |
| 🔤 **Cara baca** | Transliterasi Latin untuk aksara non-Latin |
| 🌍 **55 bahasa** | Termasuk kode-switching Indonesia–Inggris |
| 🤫 **Private Speech Check (F9)** | Latih ucapan Anda sendiri, lihat terjemahannya, tidak terkirim ke panggilan |
| 📝 **Ringkasan & ekspor** | Ringkasan sesi otomatis + transkrip lengkap dalam Markdown |
| 🔀 **Bebas provider** | Ganti model/provider AI dari Settings, tanpa update aplikasi |

## 🛠️ Teknologi

- 🖥️ **UI:** [PySide6](https://doc.qt.io/qtforpython-6/)
- 🎙️ **Speech-to-text:** [Deepgram Nova-3 Multilingual](https://developers.deepgram.com/docs/models-languages-overview) (WebSocket)
- 🧠 **AI (terjemahan, saran, ringkasan, cara baca):** API Chat Completions
  [OpenAI-compatible](https://platform.openai.com/docs/api-reference/chat)
- 🔊 **Audio:** [PyAudioWPatch](https://pypi.org/project/PyAudioWPatch/) (WASAPI loopback + mikrofon)
- 🔐 **Penyimpanan key:** Windows Credential Manager via
  [keyring](https://pypi.org/project/keyring/)
- 📦 **Installer:** [PyInstaller](https://pyinstaller.org/) +
  [Inno Setup](https://jrsoftware.org/isinfo.php)

💡 *Tips:* model kecil (mis. 3B) sering memberi saran yang mirip-mirip.
Model saran ukuran menengah (mis. `openai/gpt-oss-120b`) jauh lebih baik;
model terjemahan boleh tetap kecil dan cepat.

## 📋 Yang dibutuhkan

- 🪟 Windows 10/11
- 🎧 Headset
- 🔑 API key Deepgram (±$0,35/jam) + API key brain (biasanya beberapa sen per sesi)
- 🌐 Koneksi internet — audio dikirim ke Deepgram, teks ke provider brain;
  tidak ke tempat lain. API key tersimpan aman di Credential Manager.

## 👨‍💻 Untuk developer

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py          # jalankan dari source
.venv\Scripts\python -m unittest discover -s tests   # tes
```

Build installer:

```powershell
.venv\Scripts\python -m PyInstaller packaging\lancarin.spec --noconfirm
& "C:\Program Files\Inno Setup 7\ISCC.exe" packaging\installer.iss
```

Struktur: `app.py` (jendela utama) + paket `lancarin/`
(`config`, `audio`, `stt`, `brain`, `session`, `theme`, `settings_dialog`),
aset di `assets/`, packaging di `packaging/`, tes di `tests/`.

## ⚠️ Batasan

- Hanya Windows (loopback audio WASAPI).
- Kualitas cara baca & saran bergantung model brain yang dipilih.
- Installer belum ditandatangani digital (peringatan SmartScreen wajar).

## 🔗 Tautan

- 📚 [Dokumentasi Deepgram](https://developers.deepgram.com/docs) ·
  [Harga](https://deepgram.com/pricing)
- 📦 [Semua rilis](https://github.com/syahrulUlum/Lancarin/releases)
