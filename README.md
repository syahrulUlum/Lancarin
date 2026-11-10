# Lancarin

**Version 1.0.0** — A real-time desktop conversation assistant for Windows.

Lancarin listens to your Zoom / Google Meet calls (or any audio playing on
your PC, e.g. YouTube), transcribes the other party live, translates what
they say into your language while they are still speaking, and offers up to
**3 suggested replies** — each with its meaning in your language and, for
non-Latin scripts (Arabic, Chinese, Japanese, Korean, Russian, …), a
Latin-alphabet **reading guide** so you can pronounce the reply. Built for
Indonesian professionals who work with international clients.

Full plan (Indonesian): [docs/rencana.md](docs/rencana.md)

## Features

- **Live streaming transcription** — interim text appears while the other
  party is still talking; no waiting for silence.
- **Interim translation in chunks** — each new clause is translated and
  appended, so long speeches stay understandable in near real time.
- **Up to 3 reply suggestions** with different stances — **DIRECT**,
  **CASUAL**, and **ANOTHER ANGLE** — each shown with its meaning; click a
  card to copy the reply into your call chat.
- **Reading guide (transliteration)** — pinyin with tones, romaji, and
  standard romanizations under non-Latin text: the client's words, the
  translation, and every suggested reply.
- **55 languages** from Deepgram Nova-3 Multilingual, with automatic
  code-switching hints for your selected language pair.
- **Private Speech Check (F9)** — practice your own speech and see its
  translation, without sending anything to the call.
- **Session summary & Markdown export** — topic, key points, decisions,
  follow-ups, and new vocabulary, generated at the end of a session.
- **Provider freedom** — the AI brain is any OpenAI-compatible API; switch
  provider or model from Settings without an app update.

## Technology

| Part | Technology |
|---|---|
| Desktop UI | [PySide6](https://doc.qt.io/qtforpython-6/) (Qt for Python) |
| Speech-to-text (streaming) | [Deepgram Nova-3 Multilingual](https://developers.deepgram.com/docs/models-languages-overview) over WebSocket |
| Translation, suggestions, summaries, transliteration | Any [OpenAI-compatible](https://platform.openai.com/docs/api-reference/chat) Chat Completions API via the `openai` Python SDK |
| Audio capture | [PyAudioWPatch](https://pypi.org/project/PyAudioWPatch/) (Windows WASAPI loopback + microphone) |
| Secret storage | [keyring](https://pypi.org/project/keyring/) (Windows Credential Manager) |
| Packaging | [PyInstaller](https://pyinstaller.org/) + [Inno Setup](https://jrsoftware.org/isinfo.php) |

Recommended brain providers (fast inference matters for live use):
[Groq](https://console.groq.com/docs/models) (default),
[OpenAI](https://platform.openai.com/docs/models),
[OpenRouter](https://openrouter.ai/models),
[Cerebras](https://www.cerebras.ai/). Small models (e.g. 3B) often produce
repetitive suggestions; a mid-size suggestion model noticeably improves
reply quality while the translation model can stay small and fast.

## Requirements

- Windows 10/11 (WASAPI loopback is Windows-specific)
- A **headset** (prevents the other party's audio echoing into your mic)
- A **Deepgram API key** — sign up at <https://deepgram.com> (pay-as-you-go,
  about $0.35/hour of streaming)
- A **brain API key** from any OpenAI-compatible provider above
- Internet connection (all transcription and AI calls are cloud APIs)

For development: Python 3.15 and the packages in `requirements.txt`.

## Quick start (end users)

1. Download `Lancarin-Setup-1.0.0.exe` from the
   [v1.0.0 release](https://github.com/syahrulUlum/Lancarin/releases/tag/v1.0.0)
   and run it. Windows SmartScreen may warn about an unsigned installer —
   choose *More info → Run anyway*.
2. Open Lancarin → **Settings**:
   - Section 1: paste your **Deepgram API key**.
   - Section 2: **Base URL**, **Brain API key**, **Translation model**, and
     **Suggestions & summary model** (free text — any model your provider
     offers). Defaults are prefilled for Groq.
   - Run **Test Connection** until every line shows a checkmark, then **Save**.
3. Back on the main window: open **Session** if you want to add context
   (e.g. "Sales call with a new client"), pick the other party's language
   and yours (55 languages), and set **Mode** — *Conversation* enables reply
   suggestions; *Translate only* disables them.
4. Press **Start**. The live panel shows, in order: what the client says,
   its translation (A−/A+ adjusts one shared text size, remembered between
   runs), then your reply options. Click a reply card to copy it.
5. **End** builds the session summary in-app. **Export** saves the full
   transcript as Markdown. **New** clears the board for the next call.

Note: Private Speech Check never forwards your audio to the call app;
muting your Zoom/Meet microphone is still up to you.

## Running from source (development)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Run the test suite:

```powershell
.venv\Scripts\python -m unittest discover -s tests
```

## Building the installer

```powershell
.venv\Scripts\python -m PyInstaller packaging\lancarin.spec --noconfirm
& "C:\Program Files\Inno Setup 7\ISCC.exe" packaging\installer.iss
```

Output: `packaging\Output\Lancarin-Setup-1.0.0.exe` (application version
1.0.0, Start Menu + desktop shortcuts with the Lancarin icon).

## Privacy & costs

- Audio is streamed to Deepgram and conversation text to your chosen brain
  provider; nothing is sent anywhere else. API keys live in the Windows
  Credential Manager, never in config files.
- Typical cost per hour of meeting: Deepgram ≈ $0.35 + your brain
  provider's per-token charges (usually a few cents with small models).

## Known limitations

- Windows only (audio loopback); macOS/Linux adapters are not implemented.
- Latency depends on your network and provider region; the design target
  is under ~1 second from the end of a clause to its translation/suggestion.
- Transliteration quality depends on the brain model; it is a reading aid,
  not a pronunciation guarantee.
- Not yet verified: the installer on a clean machine, a 60-minute session,
  and private mode with a second device.

## Project layout

`app.py` (main window) uses the `lancarin/` package (`config`, `audio`,
`stt`, `brain`, `session`, `theme`, `settings_dialog`). Logo assets live in
`assets/`, packaging in `packaging/`, tests in `tests/`.

## Links

- Deepgram documentation: <https://developers.deepgram.com/docs>
- Deepgram pricing: <https://deepgram.com/pricing>
- Groq models & docs: <https://console.groq.com/docs/models>
- OpenAI API reference: <https://platform.openai.com/docs/api-reference/chat>
- OpenRouter models: <https://openrouter.ai/models>
- Releases: <https://github.com/syahrulUlum/Lancarin/releases>
