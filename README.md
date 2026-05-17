# tgcallskill

> Auto-answer Telegram private calls with an ElevenLabs Conversational AI agent.

Your Telegram phone number rings → an AI agent picks up and has a real two-way voice conversation with the caller.

## What it does

- Signs in to a Telegram account via MTProto (Telethon).
- Auto-accepts every incoming voice call to that account.
- Streams the caller's voice into [ElevenLabs Conversational AI](https://elevenlabs.io/app/conversational-ai), gets the agent's reply, and pushes it back through the call.

## Setup (5 min)

You need:

1. **Telegram API id + hash** — https://my.telegram.org → *API development tools*
2. **The phone number** of the Telegram account that will answer
3. **ElevenLabs API key** — https://elevenlabs.io → *Settings → API Keys*
4. **ElevenLabs Agent ID** — create one at https://elevenlabs.io/app/conversational-ai

Then:

```bash
git clone https://github.com/vasanthsreeram/tgcallskill.git
cd tgcallskill
uv sync                # or: pip install -r requirements.txt
cp .env.example .env   # fill in the 4 values above
uv run python login.py # one-time: enter the Telegram SMS code (and 2FA if set)
uv run python bridge.py
```

Now call the number from another Telegram account. The AI picks up.

Or use the hosted setup wizard at **https://tele.lintware.com** — it generates your `.env` and the exact commands to run.

## How it works (the parts that took the longest)

### Signalling (MTProto)
On `updatePhoneCall → phoneCallRequested`, perform DH (`messages.getDhConfig`, `phone.acceptCall` with our `g_b`), receive the caller's `g_a` in the next update, derive the shared key. This is straight Telethon.

### Outbound audio (agent → caller)
`pytgcalls.play(chat_id, MediaStream(media_path=ExternalMedia.AUDIO, audio_parameters=AudioParameters(48000, 1)))` registers our process as the source. A player task ticks every 10 ms and `send_frame`s 960-byte chunks of 48 kHz mono PCM. The audio comes from an ElevenLabs websocket at 16 kHz; `audioop.ratecv` upsamples.

### Inbound audio (caller → agent) — the hard part
`on_frames` does **not** deliver private-call peer audio. Workaround:

```
pytgcalls.record(chat_id, RecordStream(audio="/tmp/peer_<id>.mp3"))
```

ntgcalls' ffmpeg pipeline encodes peer audio to MP3 and writes it to the path. Make that path a FIFO (`os.mkfifo`). Spawn a second ffmpeg that reads the FIFO and decodes to 16 kHz mono PCM on stdout. A reader task base64-encodes each chunk and sends it as `user_audio_chunk` to the EL websocket.

### Loop hygiene
`PyTgCalls(tele)` captures the running asyncio loop on construction — instantiate it **inside** `async def main()`, not at module top level, otherwise you hit `Future attached to a different loop` the first time a call arrives.

## Files

- `login.py` — one-time interactive Telethon login.
- `bridge.py` — the runtime: MTProto auto-accept + EL bridge.
- `.env.example` — credentials template.
- `skill/tgcallskill/SKILL.md` — Claude Code skill metadata.
- `site/` — Cloudflare Pages setup wizard (https://tele.lintware.com).

## License

MIT. Use at your own risk — answering calls automatically can confuse callers; tell them upfront.
