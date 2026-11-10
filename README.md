<p align="center">
  <img src="assets/lancarin.png" alt="Lancarin logo" width="112">
</p>

<h1 align="center">Lancarin</h1>

<p align="center">
  <strong>Real-time conversation assistant for Windows.</strong><br>
  Understand the other party in your language and get replies ready to say.
</p>

<p align="center">
  <a href="https://github.com/syahrulUlum/Lancarin/releases/tag/v1.0.0">
    <img src="https://img.shields.io/badge/Download-Lancarin%20v1.0.0-0d9488?style=for-the-badge&logo=windows&logoColor=white" alt="Download Lancarin v1.0.0 for Windows">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0b7285" alt="Windows 10 and 11">
  <img src="https://img.shields.io/badge/speech--to--text-Deepgram%20Nova--3-0d9488" alt="Deepgram Nova-3">
  <img src="https://img.shields.io/badge/languages-55-0d9488" alt="55 languages">
</p>

**Contents:** [How it works](#how-it-works) · [Quick start](#quick-start) · [Features](#features) · [Supported languages](#supported-languages) · [Requirements and privacy](#requirements-and-privacy) · [Tech stack](#tech-stack) · [Development](#development) · [Limitations](#limitations)

## How it works

Lancarin is a desktop app for conversations in another language. It captures the other party's audio from your call, transcribes it live, translates it into your language, and suggests up to three replies in theirs. Click a reply to copy it, then say it or paste it into the chat.

It works with any app that plays audio through your speakers: Zoom, Google Meet, Microsoft Teams, YouTube, and others. Lancarin was built for Indonesian professionals working in English, and it works with any pair of the 55 supported languages.

```text
Other party speaks
   ↓  system audio is captured (WASAPI loopback)
   ↓  live transcription (Deepgram Nova-3, 55 languages)
   ↓  translation grows clause by clause while they are still speaking
   ↓  up to three replies appear: DIRECT, CASUAL, ANOTHER ANGLE
Click a reply to copy it, then say it or paste it into the chat.
```

For non-Latin scripts (Arabic, Chinese, Japanese, Korean, Russian, and others), Lancarin also shows a Latin reading: pinyin, romaji, or romanization. The reading appears for what the other party said, for the translation, and for every reply option.

## Quick start

1. **Install.** Download the installer from the [latest release](https://github.com/syahrulUlum/Lancarin/releases/tag/v1.0.0) and run it. If Windows SmartScreen warns, choose **More info → Run anyway**.

2. **Add two API keys.** Open **Settings**, paste both keys, click **Test Connection** until every line passes, then **Save**.
   - **Deepgram** ([deepgram.com](https://deepgram.com)): speech-to-text.
   - **Brain** ([Groq](https://console.groq.com/docs/models), [OpenAI](https://platform.openai.com/docs/models), [OpenRouter](https://openrouter.ai/models), or [Cerebras](https://www.cerebras.ai/)): translation, reply suggestions, and summaries. Lancarin defaults to Groq.

3. **Start a session.** Pick the other party's language and your language, keep **Mode: Conversation**, then press **Start**. Wear a headset so your microphone does not pick up the call audio again.

## Features

| Feature | What it does |
|---|---|
| **Live transcription** | The other party's words appear while they are still speaking. |
| **Clause-by-clause translation** | Long turns are translated in pieces, so you can follow without waiting for silence. |
| **Three reply options** | DIRECT, CASUAL, and ANOTHER ANGLE, each with a short meaning. Click one to copy it. |
| **Latin reading aid** | Non-Latin scripts also show pinyin, romaji, or romanization. |
| **Two modes** | **Conversation** gives translation plus reply suggestions. **Translate only** gives translation alone. |
| **55 languages** | Any pair from the list below, including switching between Indonesian and English in one call. |
| **Private Speech Check (F9)** | Rehearse your own line. Your speech is translated on screen only, not sent to the call. Keep your call mic muted. |
| **Summary and export** | Ending a session builds a structured summary. Export saves the summary and the full transcript with timestamps as Markdown. |
| **Bring your own provider** | Change the brain endpoint and models in Settings, with no app update. |

## Supported languages

The interface is in English. These are the languages Lancarin can transcribe and translate, for both the other party and yourself.

| Language | Code | Language | Code | Language | Code |
|---|---|---|---|---|---|
| Afrikaans | `af` | Arabic | `ar` | Belarusian | `be` |
| Bengali | `bn` | Bosnian | `bs` | Bulgarian | `bg` |
| Catalan | `ca` | Chinese (Cantonese) | `zh-HK` | Chinese (Mandarin) | `zh` |
| Croatian | `hr` | Czech | `cs` | Danish | `da` |
| Dutch | `nl` | English | `en` | Estonian | `et` |
| Finnish | `fi` | Flemish | `nl-BE` | French | `fr` |
| Galician | `gl` | German | `de` | Greek | `el` |
| Gujarati | `gu` | Hebrew | `he` | Hindi | `hi` |
| Hungarian | `hu` | Indonesian | `id` | Italian | `it` |
| Japanese | `ja` | Kannada | `kn` | Korean | `ko` |
| Latvian | `lv` | Lithuanian | `lt` | Macedonian | `mk` |
| Malay | `ms` | Marathi | `mr` | Norwegian | `no` |
| Persian | `fa` | Polish | `pl` | Portuguese | `pt` |
| Romanian | `ro` | Russian | `ru` | Serbian | `sr` |
| Slovak | `sk` | Slovenian | `sl` | Spanish | `es` |
| Swedish | `sv` | Tagalog | `tl` | Tamil | `ta` |
| Telugu | `te` | Thai | `th` | Turkish | `tr` |
| Ukrainian | `uk` | Vietnamese | `vi` | Xhosa | `xh` |
| Zulu | `zu` | | | | |

Both selected languages are sent to Deepgram as hints, so a conversation can move between them, for example Indonesian and English, without changing settings.

## Requirements and privacy

**You need**

- Windows 10 or 11.
- A headset and a working microphone. System audio is captured through WASAPI loopback.
- A Deepgram API key. Usage is billed by Deepgram; see [pricing](https://deepgram.com/pricing).
- An API key for an OpenAI-compatible provider, billed by that provider.
- An internet connection.

**What leaves your computer**

- Audio is streamed to Deepgram for transcription.
- Transcribed text is sent to the brain provider you configure, for translation, reply suggestions, and summaries.
- Lancarin does not record or store audio.
- API keys are kept in Windows Credential Manager, not in a plain config file.
- The transcript stays in memory and is written to disk only when you export it.

## Tech stack

| Layer | Technology |
|---|---|
| Desktop UI | [PySide6](https://doc.qt.io/qtforpython-6/) |
| Speech-to-text | [Deepgram Nova-3 Multilingual](https://developers.deepgram.com/docs/models-languages-overview) over WebSocket |
| Translation, suggestions, summary | Any [OpenAI-compatible](https://platform.openai.com/docs/api-reference/chat) Chat Completions API |
| Audio capture | [PyAudioWPatch](https://pypi.org/project/PyAudioWPatch/) (WASAPI loopback and microphone) |
| API key storage | [keyring](https://pypi.org/project/keyring/) and Windows Credential Manager |
| Installer | [PyInstaller](https://pyinstaller.org/) and [Inno Setup](https://jrsoftware.org/isinfo.php) |

Suggestion quality depends on the brain model. The defaults, `openai/gpt-oss-120b` for suggestions and `openai/gpt-oss-20b` for translation, use a fast model for translation and a stronger one for replies. Very small models tend to produce repetitive options.

## Development

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
.venv\Scripts\python -m unittest discover -s tests
```

Build the installer:

```powershell
.venv\Scripts\python -m PyInstaller packaging\lancarin.spec --noconfirm
& "C:\Program Files\Inno Setup 7\ISCC.exe" packaging\installer.iss
```

Project layout:

```text
app.py                 main window
lancarin/
  config.py            settings and language list
  audio.py             WASAPI loopback and microphone capture
  stt.py               Deepgram realtime WebSocket
  brain.py             translation, suggestions, summary
  session.py           transcript and Markdown export
  theme.py             stylesheet
  settings_dialog.py   API keys and connection test
tests/                 unit tests
packaging/             PyInstaller spec and Inno Setup script
assets/                logo and icons
```

## Limitations

- Windows only. There are no macOS or Linux builds yet.
- Requires internet access and your own API keys. There is no offline mode.
- Reply quality depends on the brain model you choose.
- The installer is not code-signed, so Windows SmartScreen may warn.

## Links

- [All releases](https://github.com/syahrulUlum/Lancarin/releases)
- [Deepgram documentation](https://developers.deepgram.com/docs)
- [Deepgram pricing](https://deepgram.com/pricing)
