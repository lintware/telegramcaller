---
name: telegramcaller
description: Auto-answer Telegram private calls with a `gpt-realtime-2` voice agent. Use when the user wants their Telegram phone number answered by an AI voice agent.
---

# telegramcaller - AI receptionist for your Telegram number

Local Python service that signs in to a Telegram account via MTProto, auto-answers every incoming private call, and bridges the call audio to `gpt-realtime-2`.

Default voice stack: `gpt-realtime-2` with `OPENAI_REALTIME_VOICE=alloy`.

When a call is accepted, the local bridge should immediately trigger the voice agent to greet the caller before the caller speaks: `Hi! My name is {Telegram account display name}, how may I help you?`

All calls should be recorded automatically. The bridge saves only the mixed WAV file under `CALL_RECORDINGS_DIR` (default: `recordings/`) when each call session closes.

The bridge handles 48 kHz <-> provider-rate resampling internally.

## When to use this skill

Trigger when the user asks for any of:
- "answer my Telegram calls with an AI"
- "build a Telegram voicebot / receptionist"
- "hook a realtime voice-to-voice model to Telegram phone calls"
- "Telegram auto-pickup with AI voice"
- "gpt-realtime-2 Telegram"

## Credentials Checklist

Always required:
1. **Telegram API id + hash** - https://my.telegram.org -> API development tools.
2. **Phone number** with country code for the account that will answer calls.
3. **Model/voice decision** - use `gpt-realtime-2` and `alloy` unless the user names a specific model or voice.

- Ask for `OPENAI_API_KEY`.
- Use `OPENAI_REALTIME_MODEL=gpt-realtime-2` unless the user names a specific model.
- Use `OPENAI_REALTIME_VOICE=alloy` unless the user names a voice.

Generate `.env` locally from `.env.example`. Do not direct users to hosted credential collection pages.

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

4. **Model and voice**

   Ask exactly one model/voice question: "Which model and voice should power the call? Recommended: `gpt-realtime-2` with the `alloy` voice. You can also name a specific model or voice."

   If the user accepts the recommendation or gives no specific alternative, configure `VOICE_PROVIDER=openai`, `OPENAI_REALTIME_MODEL=gpt-realtime-2`, and `OPENAI_REALTIME_VOICE=alloy`.

5. **Provider credentials**

   Ask for `OPENAI_API_KEY`.

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
git clone https://github.com/vasanthsreeram/telegramcaller.git
cd telegramcaller
uv sync
cp .env.example .env  # fill in credentials; gpt-realtime-2 is the default
uv run python login.py   # one-time interactive - enter Telegram OTP and 2FA if set
uv run python bridge.py
```

## How the audio plumbing works

- **Outbound, agent to caller:** provider websocket emits PCM at `provider.output_rate` -> `audioop.ratecv` upsamples to 48 kHz -> `pytgcalls.send_frame` 10 ms / 960 B chunks.
- **Inbound, caller to agent:** `pytgcalls.record(RecordStream(audio="/tmp/peer_<id>.mp3"))` makes ntgcalls' ffmpeg pipeline write peer audio as MP3 into a FIFO -> a child `ffmpeg` decodes the FIFO to PCM at `provider.input_rate` on stdout -> a reader task forwards chunks to `provider.send_audio`.
- The `on_frames` callback is not used; ntgcalls does not deliver private-call peer PCM through it. The FIFO+ffmpeg detour is the workaround.

## Common Failure Modes

- **"Exchanging encryption keys" forever:** signaling accepted but media plane not started. Ensure `pytgcalls.play(...)` runs inside the `INCOMING_CALL` handler.
- **Agent can't hear caller:** `pytgcalls.record(...)` was not called with a FIFO path. `on_frames` does not work for private calls.
- **`Future attached to a different loop`:** `PyTgCalls(...)` was constructed at module level. Move it inside the async `main()`.
- **Choppy outbound audio:** variable frame sizes. Standardize on 10 ms / 960 B at 48 kHz mono.
- **gpt-realtime-2 auth error:** verify the bearer token and current Realtime API connection requirements.

## Deliverable When Invoked

1. Ask for credentials one by one using the credential collection SOP above.
2. Ask exactly one model/voice question, recommending `gpt-realtime-2` with `alloy`.
3. `git clone` the repo.
4. Generate `.env` from `.env.example` using the collected answers.
5. Run `login.py`, feed OTP / 2FA.
6. Run `bridge.py`, ask user to place a test call.
7. On failure, consult the table above.
