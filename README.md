# Lancarin

A real-time desktop assistant that captures and translates audio from Zoom,
Meet, and YouTube, then suggests English replies that fit the conversation.
Built for Indonesian professionals. Live transcription by Deepgram Nova-3
Multilingual (streaming); translation, reply suggestions, and summaries by
any OpenAI-compatible brain provider configured in Settings (Groq by default).

Full plan: [docs/rencana.md](docs/rencana.md)

Code layout: `app.py` (main window) uses the `lancarin/` package
(`config`, `audio`, `stt`, `brain`, `session`, `theme`, `settings_dialog`).
Logo assets live in `assets/`, packaging in `packaging/`, tests in `tests/`.

## Running (development)

Requirements: Python 3.15 and a headset (prevents echo).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

The application UI is in English by default.

1. Click **Settings**. Section 1: enter your Deepgram API key (from
   deepgram.com) for live transcription. Section 2: enter the brain Base URL,
   API key, translation model, and suggestions/summary model - any
   OpenAI-compatible endpoint works (Groq, OpenAI, OpenRouter, Cerebras);
   model names are free text. Run **Test Connection** - each model is tested
   separately - until every line shows a checkmark, and **Save**. Start
   Session stays locked until the test passes.
2. Open the **Session** menu if needed: add context (optional), pick the
   other party's language and yours, and choose a mode. The menu is
   collapsed by default so the conversation panel stays spacious.
3. **Start Session** - play a video or call; the in-app panel shows the
   transcript, a large translation (A-/A+ buttons), and a suggested reply.
   `F9` toggles Private Speech Check.
4. **End and Summarize** - the summary appears as a card inside the app
   (copyable, reopenable via **View Summary**, exportable), not a popup.
   **New Session** clears the board for the next conversation.

Note: private mode never forwards your audio to the call app; muting your
Zoom/Meet microphone is still up to you. Local STT fallback and macOS/Linux
adapters are tracked in the GitHub backlog issues.

## Measured results (development machine, Nov 2026)

- Connection test passes. Translation uses the selected translation model
  and appears first; the suggested reply follows in parallel from the
  suggestions model. (Historical Meta-provider measurements: ~2.5s
  translation, ~8s total; Deepgram + OpenAI-compatible brain latency still
  to be re-measured.)
- Interim translation now works in chunks: each new sentence fragment is
  translated and appended while the other party keeps speaking, instead
  of re-translating the whole partial transcript.
- Real STT (TTS speech to loopback to WebSocket): partials stream every
  ~0.3s and the final lands exactly when speech ends.
- Idle app: about 123 MB RAM. Six-question interview scenario: suggestions
  stay coherent with the context and history.
- Not yet verified: the installer on a clean machine, a 60-minute
  session, and private mode with a second device (tracked in issue #8).

## Building the Windows installer

```powershell
.venv\Scripts\python -m PyInstaller packaging\lancarin.spec
```

Output lands in `dist\Lancarin\`. Wrap it with Inno Setup using
`packaging\installer.iss` (version 0.1.0).
