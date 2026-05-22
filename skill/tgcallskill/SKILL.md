---
name: tgcallskill
description: Auto-answer Telegram private calls with a real-time voice AI agent. Use when the user wants their Telegram phone number to be answered by an AI voice agent, with OpenAI Realtime as the default and other realtime voice-to-voice providers configurable when requested. Triggers on terms like "answer Telegram calls", "AI Telegram phone", "Telegram voicebot", "auto-pickup Telegram", "OpenAI Realtime Telegram", "Gemini Live Telegram", "ElevenLabs Telegram".
---

# tgcallskill - AI receptionist for your Telegram number

Local Python service that signs in to a Telegram account via MTProto, auto-answers every incoming private call, and bridges the call audio to a real-time voice-AI provider for two-way conversation.

Default voice stack: OpenAI Realtime API with `OPENAI_REALTIME_MODEL=gpt-realtime-2` and `OPENAI_REALTIME_VOICE=alloy`.

Runtime adapters currently included in `providers/`:

| Adapter | `VOICE_PROVIDER` value | Native PCM in / out |
|---------|------------------------|---------------------|
| OpenAI Realtime | `openai` | 24 kHz / 24 kHz |
| ElevenLabs Conversational AI | `elevenlabs` | 16 kHz / 16 kHz |
| Gemini Live | `gemini` | 16 kHz / 24 kHz |
| xAI Grok | `grok` | stub - no public realtime voice API yet |

The bridge handles 48 kHz <-> provider-rate resampling internally.

## When to use this skill

Trigger when the user asks for any of:
- "answer my Telegram calls with an AI"
- "build a Telegram voicebot / receptionist"
- "hook a realtime voice-to-voice model to Telegram phone calls"
- "Telegram auto-pickup with AI voice"

## Credentials checklist

Always required:
1. **Telegram API id + hash** - https://my.telegram.org -> API development tools.
2. **Phone number** with country code for the account that will answer calls.
3. **One voice model/provider decision** - recommend OpenAI Realtime API with `gpt-realtime-2`; otherwise let the user name any realtime voice-to-voice model/provider they want.

Provider-specific credentials are collected only after the model/provider decision is known:
- **OpenAI Realtime default:** `OPENAI_API_KEY`. Use `OPENAI_REALTIME_MODEL=gpt-realtime-2` unless the user named a specific OpenAI Realtime model. Use `OPENAI_REALTIME_VOICE=alloy` unless they named a voice.
- **ElevenLabs:** `ELEVENLABS_API_KEY` + `EL_AGENT_ID`. The voice and model are configured inside the ElevenLabs agent referenced by `EL_AGENT_ID`; this repo does not set an ElevenLabs model directly.
- **Gemini:** `GOOGLE_API_KEY`. Use `GEMINI_LIVE_MODEL=models/gemini-3.1-flash-live-preview` unless the user named a specific Gemini Live model. Use `GEMINI_LIVE_VOICE=Aoede` unless they named a voice.
- **Other realtime voice-to-voice model/provider:** collect the provider docs or model/API details, then implement or update a `providers/` adapter before generating `.env`.

The hosted setup wizard at https://tele.lintware.com (or https://tgcallskill.pages.dev) collects these and generates the `.env`.

## Credential Collection SOP

Ask for credentials one question at a time. Do not present a long form or ask for multiple secrets in one message. Keep prompts calm, polished, and specific so the user always knows exactly what to paste next.

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

4. **Voice-to-voice model**

   Ask exactly one model/provider question: "Which realtime voice-to-voice model should power the call? Recommended: OpenAI Realtime API with `gpt-realtime-2`. You can also name a specific realtime voice-to-voice model/provider you want me to configure."

   If the user accepts the recommendation or gives no specific alternative, configure `VOICE_PROVIDER=openai`, `OPENAI_REALTIME_MODEL=gpt-realtime-2`, and `OPENAI_REALTIME_VOICE=alloy`.

5. **Provider credentials**

   Ask only for credentials needed by the selected model/provider:
   - OpenAI Realtime: ask for `OPENAI_API_KEY`.
   - ElevenLabs: ask for `ELEVENLABS_API_KEY`, then `EL_AGENT_ID`. Do not ask for an ElevenLabs model in this repo; the model is configured in the ElevenLabs agent.
   - Gemini Live: ask for `GOOGLE_API_KEY`.
   - Any other provider: inspect its API requirements or ask for the relevant docs, then add a provider adapter if this repo does not already support it.

6. **Telegram login OTP**

   After `.env` is prepared and `uv run python login.py` is started, ask: "Telegram just sent a login code. Please send me the OTP/code now."

7. **Telegram 2FA password, only if prompted**

   If Telegram asks for two-step verification, ask: "Your account has Telegram two-step verification enabled. Please enter the 2FA password so I can finish the local login."

Do not ask for the next credential until the previous answer is received and validated enough to continue.

## Setup

**Platform note:** runs on macOS and Linux natively. On Windows the user must install **WSL2** first (`wsl --install -d Ubuntu` in an admin PowerShell, then work inside the Ubuntu shell) - the bridge uses Unix named pipes and `/tmp`, so it will not run in native Windows Python.

System dependencies by OS:
- macOS: `brew install ffmpeg uv python@3.12`
- Debian/Ubuntu, including WSL: `sudo apt install -y ffmpeg python3.12 && curl -LsSf https://astral.sh/uv/install.sh | sh`
- Arch: `sudo pacman -S ffmpeg python uv`

Then:

```bash
git clone https://github.com/vasanthsreeram/tgcallskill.git
cd tgcallskill
uv sync
cp .env.example .env  # fill in credentials; OpenAI Realtime is the default
uv run python login.py   # one-time interactive - enter Telegram OTP and 2FA if set
uv run python bridge.py
```

## How the audio plumbing works

- **Outbound, agent to caller:** provider websocket emits PCM at `provider.output_rate` -> `audioop.ratecv` upsamples to 48 kHz -> `pytgcalls.send_frame` 10 ms / 960 B chunks.
- **Inbound, caller to agent:** `pytgcalls.record(RecordStream(audio="/tmp/peer_<id>.mp3"))` makes ntgcalls' ffmpeg pipeline write peer audio as MP3 into a FIFO -> a child `ffmpeg` decodes the FIFO to PCM at `provider.input_rate` on stdout -> a reader task forwards chunks to `provider.send_audio`.
- The `on_frames` callback is not used; ntgcalls does not deliver private-call peer PCM through it. The FIFO+ffmpeg detour is the workaround.

## Provider interface

To add a new provider, implement `providers/base.Provider` with `open`, `send_audio`, `recv`, `close`, `input_rate`, and `output_rate`, register it in `providers/__init__.py`, then set `VOICE_PROVIDER=<your-name>` in `.env`.

## Common failure modes

- **"Exchanging encryption keys" forever:** signaling accepted but media plane not started. Ensure `pytgcalls.play(...)` runs inside the `INCOMING_CALL` handler.
- **Agent can't hear caller:** `pytgcalls.record(...)` was not called with a FIFO path. `on_frames` does not work for private calls.
- **`Future attached to a different loop`:** `PyTgCalls(...)` was constructed at module level. Move it inside the async `main()`.
- **Choppy outbound audio:** variable frame sizes. Standardize on 10 ms / 960 B at 48 kHz mono.
- **`payment_required` from ElevenLabs:** free plan blocks premade voices via API; use a custom voice or upgrade.
- **OpenAI Realtime auth error:** verify the bearer token and current Realtime API connection requirements.
- **Gemini Live 4xx on setup:** model name should be `models/gemini-3.1-flash-live-preview` or another current Live API model; voice must be a valid `prebuilt_voice_config` voice.

## Deliverable when invoked

1. Ask for credentials one by one using the credential collection SOP above.
2. Ask exactly one voice-to-voice model/provider question, recommending OpenAI Realtime API with `gpt-realtime-2`.
3. `git clone` the repo.
4. Generate `.env` from `.env.example` using the collected answers.
5. Run `login.py`, feed OTP / 2FA.
6. Run `bridge.py`, ask user to place a test call.
7. On failure, consult the table above.