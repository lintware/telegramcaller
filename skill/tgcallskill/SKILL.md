---
name: tgcallskill
description: Auto-answer Telegram private calls with a real-time voice AI agent. Use when the user wants their Telegram phone number to be answered by an AI voice agent — ElevenLabs Conversational AI, OpenAI Realtime, or Gemini Live (xAI Grok stub included). Triggers on terms like "answer Telegram calls", "AI Telegram phone", "Telegram voicebot", "auto-pickup Telegram", "OpenAI Realtime Telegram", "Gemini Live Telegram", "ElevenLabs Telegram".
---

# tgcallskill — AI receptionist for your Telegram number

Local Python service that signs in to a Telegram account via MTProto, auto-answers every incoming private call, and bridges the call audio to a real-time voice-AI provider for two-way conversation.

Supported providers (set via `VOICE_PROVIDER` in `.env`):

| Provider     | Value          | Native PCM in / out |
|--------------|----------------|---------------------|
| ElevenLabs   | `elevenlabs`   | 16 kHz / 16 kHz |
| OpenAI       | `openai`       | 24 kHz / 24 kHz |
| Gemini Live  | `gemini`       | 16 kHz / 24 kHz |
| xAI Grok     | `grok`         | stub — no public realtime API yet |

The bridge handles 48 kHz ↔ provider-rate resampling internally.

## When to use this skill

Trigger when the user asks for any of:
- "answer my Telegram calls with an AI"
- "build a Telegram voicebot / receptionist"
- "hook OpenAI Realtime / Gemini Live / ElevenLabs to Telegram phone calls"
- "Telegram auto-pickup with AI voice"

## Credentials checklist

Always required:
1. **Telegram API id + hash** — https://my.telegram.org → API development tools.
2. **Phone number** (with country code) of the account that will answer.

Provider-specific:
- **ElevenLabs:** `ELEVENLABS_API_KEY` + `EL_AGENT_ID` (create at https://elevenlabs.io/app/conversational-ai).
- **OpenAI:** `OPENAI_API_KEY`. Optional: `OPENAI_REALTIME_MODEL` (default `gpt-4o-realtime-preview`), `OPENAI_REALTIME_VOICE`.
- **Gemini:** `GOOGLE_API_KEY`. Optional: `GEMINI_LIVE_MODEL`, `GEMINI_LIVE_VOICE`.

The hosted setup wizard at https://tele.lintware.com (or https://tgcallskill.pages.dev) collects these and generates the `.env`.

## Credential collection SOP

Ask for credentials one question at a time. Do not present a long form or ask for multiple secrets in one message. Keep the prompts calm, polished, and specific so the user always knows exactly what to paste next.

Use this sequence:

1. **Telegram API ID**

   Ask: "First, please send your Telegram API ID. To find it, open https://my.telegram.org, log in with the Telegram account that should answer calls, choose API development tools, create an app if Telegram asks you to, then copy the numeric App api_id."

   If the user does not have one yet, guide them:
   - Open https://my.telegram.org and log in with the Telegram account.
   - Choose **API development tools**.
   - Create an app if one does not already exist.
   - Copy the numeric **App api_id**.

2. **Telegram API hash**

   Ask: "Now send your Telegram API hash from the same API development tools page. It is shown as App api_hash."

   Remind them that the API hash is a secret and should not be posted publicly.

3. **Telegram phone number**

   Ask: "What Telegram phone number should answer calls? Please include the country code, for example +14155552671."

4. **Voice provider**

   Ask: "Which voice provider should power the call: ElevenLabs, OpenAI, or Gemini?"

5. **Provider credentials**

   Ask only for the credentials needed by the provider they chose:
   - ElevenLabs: first ask for `ELEVENLABS_API_KEY`, then ask for `EL_AGENT_ID`.
   - OpenAI: ask for `OPENAI_API_KEY`. Then ask whether they want to customize `OPENAI_REALTIME_MODEL` or `OPENAI_REALTIME_VOICE`; otherwise use the defaults.
   - Gemini: ask for `GOOGLE_API_KEY`. Then ask whether they want to customize `GEMINI_LIVE_MODEL` or `GEMINI_LIVE_VOICE`; otherwise use the defaults.

6. **Telegram login OTP**

   After `.env` is prepared and `uv run python login.py` is started, ask: "Telegram just sent a login code. Please send me the OTP/code now."

7. **Telegram 2FA password, only if prompted**

   If Telegram asks for two-step verification, ask: "Your account has Telegram two-step verification enabled. Please enter the 2FA password so I can finish the local login."

Do not ask for the next credential until the previous answer is received and validated enough to continue.

## Setup

**Platform note:** runs on macOS and Linux natively. On Windows the user must install **WSL2** first (`wsl --install -d Ubuntu` in an admin PowerShell, then work inside the Ubuntu shell) — the bridge uses Unix named pipes and `/tmp`, so it will not run in native Windows Python.

System dependencies (per OS):
- macOS: `brew install ffmpeg uv python@3.12`
- Debian/Ubuntu (incl. WSL): `sudo apt install -y ffmpeg python3.12 && curl -LsSf https://astral.sh/uv/install.sh | sh`
- Arch: `sudo pacman -S ffmpeg python uv`

Then:

```bash
git clone https://github.com/vasanthsreeram/tgcallskill.git
cd tgcallskill
uv sync
cp .env.example .env  # fill in credentials, pick VOICE_PROVIDER
uv run python login.py   # one-time interactive — enter Telegram OTP and 2FA if set
uv run python bridge.py
```

## How the audio plumbing works

- **Outbound (agent → caller):** provider websocket emits PCM at `provider.output_rate` → `audioop.ratecv` upsamples to 48 kHz → `pytgcalls.send_frame` 10 ms / 960 B chunks.
- **Inbound (caller → agent):** `pytgcalls.record(RecordStream(audio="/tmp/peer_<id>.mp3"))` makes ntgcalls' ffmpeg pipeline write peer audio as MP3 into a FIFO → a child `ffmpeg` decodes the FIFO to PCM at `provider.input_rate` on stdout → a reader task forwards chunks to `provider.send_audio`.
- The `on_frames` callback is **not** used — ntgcalls doesn't deliver private-call peer PCM through it. The FIFO+ffmpeg detour is the workaround.

## Provider interface

To add a new provider, implement `providers/base.Provider` (open / send_audio / recv / close, plus `input_rate` and `output_rate` ints), register it in `providers/__init__.py`, then set `VOICE_PROVIDER=<your-name>` in `.env`.

## Common failure modes

- **"Exchanging encryption keys" forever:** signaling accepted but media plane not started. Ensure `pytgcalls.play(...)` runs inside the `INCOMING_CALL` handler.
- **Agent can't hear caller:** `pytgcalls.record(...)` was not called with a FIFO path. `on_frames` does not work for private calls.
- **`Future attached to a different loop`:** `PyTgCalls(...)` was constructed at module level. Move it inside the async `main()`.
- **Choppy outbound audio:** variable frame sizes. Standardise on 10 ms / 960 B at 48 kHz mono.
- **`payment_required` from ElevenLabs:** free plan blocks premade voices via API; use a custom voice or upgrade.
- **OpenAI Realtime auth error:** verify the `OpenAI-Beta: realtime=v1` header and the bearer token.
- **Gemini Live 4xx on setup:** model name must be `models/gemini-2.0-flash-exp` (or newer); voice must be a valid `prebuilt_voice_config` voice.

## Deliverable when invoked

1. Ask for credentials one by one using the credential collection SOP above.
2. `git clone` the repo.
3. Generate `.env` from `.env.example` using the collected answers.
4. Run `login.py`, feed OTP / 2FA.
5. Run `bridge.py`, ask user to place a test call.
6. On failure, consult the table above.
