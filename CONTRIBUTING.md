# Contributing to telegramcaller

Thanks for helping improve telegramcaller. Bug fixes, documentation improvements, and provider adapter contributions are welcome.

## Local setup

```bash
git clone https://github.com/vasanthsreeram/telegramcaller.git
cd telegramcaller
uv sync
cp .env.example .env
uv run python login.py
uv run python bridge.py
```

Fill `.env` locally. Do not paste Telegram credentials, API keys, or session data into hosted forms, public chats, issues, or pull requests.

## What to contribute

Good contributions include:

- Fixes for Telegram call setup, media plumbing, reconnects, or logging.
- Documentation that makes local setup clearer.
- New realtime voice-to-voice provider adapters under `providers/`.
- Small reliability improvements with clear before/after behavior.

For larger architecture changes, open an issue first so the scope can be discussed.

## Privacy and safety rules

This project handles live phone-call audio and account credentials. Please keep changes conservative around privacy-sensitive areas.

Never commit or upload:

- `.env` files or API keys.
- Telegram `.session` files.
- OTPs, 2FA passwords, or account identifiers from real users.
- Call recordings, transcripts, or logs containing private conversations.
- Screenshots that expose phone numbers, API credentials, or caller details.

Use fake values in examples and redact sensitive logs before sharing them.

## Pull request expectations

- Keep PRs focused and easy to review.
- Explain user-visible behavior changes.
- For provider changes, document required environment variables and audio sample rates.
- Run a basic sanity check before opening a PR:

```bash
uv sync
python -m compileall .
```

If you tested a live Telegram call, describe the result without sharing private audio or caller details.

## Style notes

- Prefer simple async code and explicit logging over clever abstractions.
- Keep provider-specific logic inside provider adapters when possible.
- Avoid hosted credential collection flows; local `.env` setup is preferred.
