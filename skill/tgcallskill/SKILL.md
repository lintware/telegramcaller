---
name: tgcallskill
description: Auto-answer Telegram private calls with an ElevenLabs Conversational AI agent. Use when the user wants their Telegram phone number to be answered by an AI voice agent, set up a Telegram AI receptionist, or build a Telegram voice-call bot that converses with callers. Triggers on terms like "answer Telegram calls", "AI Telegram phone", "ElevenLabs Telegram", "Telegram voicebot", "auto-pickup Telegram".
---

# tgcallskill — AI receptionist for your Telegram number

This skill sets up a local Python service that:
1. Signs in to a Telegram account via MTProto (Telethon session).
2. Auto-answers every incoming private call to that account.
3. Bridges the call audio to an **ElevenLabs Conversational AI agent** for real-time two-way voice conversation.

## When to use this skill

Trigger this skill when the user asks for any of:
- "answer my Telegram calls with an AI"
- "build a Telegram voicebot / receptionist"
- "hook ElevenLabs agent to Telegram phone calls"
- "Telegram auto-pickup with AI voice"

## Prerequisites the user must provide

Ask the user for these (the setup wizard at https://tele.lintware.com collects them too):

1. **Telegram API credentials** from https://my.telegram.org → API development tools:
   - `api_id` (integer)
   - `api_hash` (hex string)
2. **Phone number** of the Telegram account that will receive calls (with country code, e.g. `+917881174135`).
3. **ElevenLabs API key** (`xi-api-key`) — https://elevenlabs.io → Settings → API Keys.
4. **ElevenLabs Agent ID** — Create a Conversational AI agent at https://elevenlabs.io/app/conversational-ai → copy the `agent_xxx` ID.

When the user runs the bridge for the first time, Telegram will SMS / message the login code; if the account has 2FA, ask for the cloud password too.

## Setup steps

```bash
git clone https://github.com/vasanthsreeram/tgcallskill.git
cd tgcallskill
uv sync
cp .env.example .env  # then fill in the 4 values above
uv run python login.py   # one-time, interactive — enter SMS code + 2FA
uv run python bridge.py  # leave running; auto-answers calls
```

## How the audio plumbing works (so you can debug)

- **Outbound (agent → caller):** ElevenLabs websocket emits 16 kHz PCM → `audioop.ratecv` upsamples to 48 kHz → `pytgcalls.send_frame` pushes 10 ms / 960 B chunks.
- **Inbound (caller → agent):** `pytgcalls.record(RecordStream(audio="/tmp/peer_<id>.mp3"))` makes ntgcalls' ffmpeg pipeline write peer audio as MP3 into a FIFO → a child `ffmpeg` decodes the FIFO to 16 kHz mono PCM on stdout → a reader task forwards base64-encoded chunks as `user_audio_chunk` over the EL websocket.
- The `on_frames` callback is **not** used — ntgcalls doesn't deliver private-call peer PCM that way. The FIFO+ffmpeg detour is the working path.

## Common failure modes

- **"Exchanging encryption keys" forever on the caller side:** you accepted MTProto signaling but didn't start the media plane. Check that `pytgcalls.play(...)` is called inside the `INCOMING_CALL` handler, not just `phone.acceptCall`.
- **Agent can't hear caller:** you didn't call `pytgcalls.record(...)` with a FIFO path. The `on_frames` route is broken for private calls; the FIFO route is the workaround.
- **"Future attached to a different loop":** you instantiated `PyTgCalls(...)` at module level before any asyncio loop existed. Construct it inside your async `main()`.
- **Choppy outbound audio:** you sent variable-size frames. Standardise on 10 ms = 960 B at 48 kHz mono.
- **`payment_required` from ElevenLabs:** the free plan blocks library/premade voices via API. Use a custom voice or upgrade.

## Skill deliverable

When invoked, run through the checklist:
1. Confirm the user has the four credentials above.
2. `git clone` the repo (or scaffold inline if offline).
3. Create `.env` from `.env.example` with the user's values.
4. Run `login.py` and pass the user's OTP / 2FA when prompted.
5. Run `bridge.py` and ask the user to place a test call.
6. If anything fails, consult the "Common failure modes" section.
