"""Turn-based xAI STT -> OpenClaw/Chippy -> xAI TTS provider.

This is intentionally different from the speech-to-speech realtime providers:
caller audio is streamed to xAI STT, final utterance text is sent to an
OpenClaw agent turn, and the final assistant text is synthesized through xAI
TTS before being played back into the Telegram call.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import urllib.error
import urllib.request
from typing import AsyncIterator
from urllib.parse import urlencode

import websockets

from .base import Provider


class XAITurnProvider:
    name = "xai_turn"
    input_rate = int(os.environ.get("XAI_STT_SAMPLE_RATE", "16000"))
    output_rate = int(os.environ.get("XAI_TTS_SAMPLE_RATE", "24000"))

    def __init__(self) -> None:
        self.api_key = os.environ["XAI_API_KEY"]
        self.stt_language = os.environ.get("XAI_STT_LANGUAGE", "en")
        self.stt_endpointing_ms = int(os.environ.get("XAI_STT_ENDPOINTING_MS", "700"))
        self.stt_interim = os.environ.get("XAI_STT_INTERIM_RESULTS", "false").lower() in {"1", "true", "yes"}
        self.tts_voice = os.environ.get("XAI_TTS_VOICE", os.environ.get("GROK_VOICE", "eve"))
        self.tts_language = os.environ.get("XAI_TTS_LANGUAGE", "en")
        self.tts_speed_tag = os.environ.get("XAI_TTS_SPEED_TAG", "fast")
        self.openclaw_session_id = os.environ.get("OPENCLAW_VOICE_SESSION_ID", "tgcallskill-voice")
        self.openclaw_timeout = int(os.environ.get("OPENCLAW_VOICE_TIMEOUT", "180"))
        self.openclaw_model = os.environ.get("OPENCLAW_VOICE_MODEL", "")
        self.max_reply_chars = int(os.environ.get("XAI_TURN_MAX_REPLY_CHARS", "900"))
        self.ws = None
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self._response_lock = asyncio.Lock()
        self._closed = False

    async def open(self) -> None:
        params = {
            "sample_rate": str(self.input_rate),
            "encoding": "pcm",
            "interim_results": "true" if self.stt_interim else "false",
            "endpointing": str(self.stt_endpointing_ms),
            "language": self.stt_language,
        }
        url = "wss://api.x.ai/v1/stt?" + urlencode(params)
        self.ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def send_audio(self, pcm16: bytes) -> None:
        if self.ws and not self._closed:
            await self.ws.send(pcm16)

    async def recv(self) -> AsyncIterator[dict]:
        assert self.ws is not None
        stt_reader = asyncio.create_task(self._read_stt())
        queue_reader = asyncio.create_task(self.queue.get())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {stt_reader, queue_reader},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if stt_reader in done:
                    exc = stt_reader.exception()
                    if exc:
                        raise exc
                    break
                if queue_reader in done:
                    ev = queue_reader.result()
                    yield ev
                    queue_reader = asyncio.create_task(self.queue.get())
        finally:
            stt_reader.cancel()
            queue_reader.cancel()

    async def _read_stt(self) -> None:
        assert self.ws is not None
        async for msg in self.ws:
            d = json.loads(msg) if isinstance(msg, str) else json.loads(msg.decode())
            event = d.get("type") or d.get("event")
            if event == "transcript.created":
                continue
            if event == "transcript.partial":
                text = (d.get("text") or "").strip()
                is_final = bool(d.get("is_final"))
                speech_final = bool(d.get("speech_final"))
                # Only forward complete utterances to Chippy by default; this
                # avoids noisy partials in busy environments.
                if text and is_final and speech_final:
                    await self.queue.put({"type": "user_text", "text": text})
                    asyncio.create_task(self._answer_turn(text))
            elif event == "transcript.done":
                text = (d.get("text") or "").strip()
                if text:
                    await self.queue.put({"type": "user_text", "text": text})
                    asyncio.create_task(self._answer_turn(text))
            elif event == "error":
                raise RuntimeError(f"xAI STT error: {d}")

    async def _answer_turn(self, user_text: str) -> None:
        async with self._response_lock:
            await self.queue.put({"type": "interrupt"})
            reply = await asyncio.to_thread(self._ask_openclaw, user_text)
            reply = self._clean_reply(reply)
            if not reply:
                return
            await self.queue.put({"type": "agent_text", "text": reply})
            pcm = await asyncio.to_thread(self._tts_pcm, reply)
            if pcm:
                await self.queue.put({"type": "audio", "pcm": pcm})

    def _ask_openclaw(self, user_text: str) -> str:
        instruction = os.environ.get(
            "OPENCLAW_VOICE_INSTRUCTION",
            "You are Chippy on a Telegram voice call with Vas. Reply with only the concise, spoken response Vas should hear. No markdown, no tool logs, no internal notes. If you need to use tools, do it, then answer briefly.",
        )
        message = f"{instruction}\n\nVas said: {user_text}"
        cmd = [
            "openclaw", "agent",
            "--session-id", self.openclaw_session_id,
            "--message", message,
            "--json",
            "--timeout", str(self.openclaw_timeout),
        ]
        if self.openclaw_model:
            cmd.extend(["--model", self.openclaw_model])
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=self.openclaw_timeout + 30)
        if proc.returncode != 0:
            return "Sorry, I hit an OpenClaw error while thinking. Try that again?"
        raw = proc.stdout.strip()
        # Plugin warnings can appear after JSON. Parse the leading JSON object.
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(raw)
            payloads = data.get("result", {}).get("payloads", [])
            if payloads:
                return payloads[0].get("text") or ""
        except Exception:
            pass
        return raw.splitlines()[0] if raw else ""

    def _clean_reply(self, text: str) -> str:
        text = (text or "").strip()
        if text == "NO_REPLY":
            return ""
        if len(text) > self.max_reply_chars:
            text = text[: self.max_reply_chars].rsplit(" ", 1)[0] + "…"
        return text

    def _tts_pcm(self, text: str) -> bytes:
        # xAI TTS supports <fast>...</fast>; this is closer to requested speed
        # control than a realtime voice-agent speed knob.
        if self.tts_speed_tag:
            text = f"<{self.tts_speed_tag}>{text}</{self.tts_speed_tag}>"
        body = json.dumps({
            "text": text,
            "voice_id": self.tts_voice,
            "language": self.tts_language,
            "output_format": {"codec": "pcm", "sample_rate": self.output_rate},
            "optimize_streaming_latency": 1,
            "text_normalization": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.x.ai/v1/tts",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"xAI TTS error {e.code}: {detail}") from e

    async def close(self) -> None:
        self._closed = True
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "audio.done"}))
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
