# telegramcaller

Turn your personal Telegram account into a realtime voice agent.

telegramcaller answers incoming private Telegram calls on your account and connects the live audio to the voice-agent provider you choose. OpenAI Realtime works out of the box.

## Install

```bash
git clone https://github.com/vasanthsreeram/telegramcaller.git
cd telegramcaller
uv sync
```

If a required system dependency is missing, ask your coding agent to install it.

## First Command

Create your local environment file:

```bash
cp .env.example .env
```

Fill in `.env`, then run:

```bash
uv run python login.py
uv run python bridge.py
```

`login.py` signs in to your Telegram account once. `bridge.py` starts the voice agent and answers incoming private Telegram calls.

## What It Will Ask You

- Telegram API ID from <https://my.telegram.org>
- Telegram API hash from <https://my.telegram.org>
- Telegram phone number with country code
- Voice provider choice
- Provider API key, such as `OPENAI_API_KEY`
- Telegram login code
- Telegram 2FA password, only if your account has 2FA enabled

By default, the voice provider is OpenAI Realtime with `gpt-realtime-2` and the `alloy` voice.

Call recordings are saved in `recordings/` as mixed WAV files.
