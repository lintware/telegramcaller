<div align="center">

<img src="docs/banner.svg" alt="telegramcaller - AI receptionist for your Telegram number" width="100%" />

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram MTProto](https://img.shields.io/badge/Telegram-MTProto-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/mtproto)
[![gpt-realtime-2](https://img.shields.io/badge/gpt--realtime--2-412991?logo=openai&logoColor=white)](https://platform.openai.com/docs/guides/realtime)
[![Codex](https://img.shields.io/badge/Made_for-Codex-111827)](https://openai.com/codex/)
[![Claude Code](https://img.shields.io/badge/Made_for-Claude_Code-D97706)](https://www.anthropic.com/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e)](#license)

# telegramcaller

### Turn your personal Telegram account into a realtime voice agent.

</div>

telegramcaller skill lets a coding agent turn your Telegram account into a live voice agent using the voice product you choose. Ship with `gpt-realtime-2` by default, or tell your agent which provider you want and let it wire up the rest.

## Installation

```bash
npx skills add lintware/telegramcaller
```

If a required system dependency is missing, ask your coding agent to install it.

## How to use

Text your coding agent:

```text
Use the telegramcaller skill to make my Telegram account a voice agent
```

## What It Will Ask You

| Prompt | What to provide |
| --- | --- |
| Telegram API ID | From <https://my.telegram.org> |
| Telegram API hash | From <https://my.telegram.org> |
| Telegram phone number | Include country code |
| Voice model default | `gpt-realtime-2` |
| Provider API key | For example, `OPENAI_API_KEY` |
| Telegram login code | Sent by Telegram during setup |
| Telegram 2FA password | Only if 2FA is enabled |

By default, the voice model is `gpt-realtime-2` with the `alloy` voice.

Call recordings are saved in `recordings/` as mixed WAV files.

## License

[MIT](LICENSE) - use at your own risk. Be courteous: tell callers when they are talking to an AI.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and PR guidelines.
