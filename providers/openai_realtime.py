"""OpenAI Realtime provider — pcm16 24 kHz mono both ways.

Docs: https://platform.openai.com/docs/guides/realtime
"""
from __future__ import annotations
import base64
import json
import os
from typing import AsyncIterator

import websockets

from .base import Provider

try:
    from calendar_tools import CALENDAR_TOOL_SCHEMAS, dispatch_tool
except Exception:  # calendar tools are optional
    CALENDAR_TOOL_SCHEMAS = []
    dispatch_tool = None

SYSTEM_PROMPT = os.environ.get(
    "VOICE_SYSTEM_PROMPT",
    "You are answering a Telegram voice call with Vas. Be friendly, concise, and useful. "
    "Speak at a brisk, natural pace unless Vas asks you to slow down. "
    "You may help with Vas's calendar using the available tools. Use Asia/Singapore time. "
    "For calendar writes, only create solo events/reminders/focus blocks; do not invite attendees, "
    "delete events, or modify meetings with attendees. If details are ambiguous, ask a short clarification.",
)


class OpenAIRealtimeProvider:
    name = "openai"
    input_rate = 24000
    output_rate = 24000

    def __init__(self) -> None:
        self.api_key = os.environ["OPENAI_API_KEY"]
        self.model = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2")
        self.voice = os.environ.get("OPENAI_REALTIME_VOICE", "alloy")
        self.ws = None

    async def open(self) -> None:
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        self.ws = await websockets.connect(
            url,
            additional_headers={
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        await self.ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": self.model,
                "output_modalities": ["audio"],
                "instructions": SYSTEM_PROMPT,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": self.input_rate},
                        "turn_detection": {"type": "semantic_vad"},
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": self.output_rate},
                        "voice": self.voice,
                        "speed": float(os.environ.get("OPENAI_REALTIME_SPEED", "1.08")),
                    },
                },
                "tools": CALENDAR_TOOL_SCHEMAS,
                "tool_choice": "auto",
            },
        }))

    async def begin_call(self, account_name: str) -> None:
        if not self.ws:
            return
        if os.environ.get("INITIAL_GREETING_ENABLED", "true").lower() in ("0", "false", "no"):
            return
        display_name = account_name or "ChatGPT"
        template = os.environ.get(
            "INITIAL_GREETING_TEMPLATE",
            "Hi! My name is {name}.",
        )
        greeting = template.format(name=display_name)
        await self.ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "The Telegram call has just connected. Before the caller speaks, "
                            f"say exactly this greeting and nothing else: {greeting!r}"
                        ),
                    }
                ],
            },
        }))
        await self.ws.send(json.dumps({"type": "response.create"}))

    async def send_audio(self, pcm16: bytes) -> None:
        if not self.ws:
            return
        await self.ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm16).decode("ascii"),
        }))

    async def recv(self) -> AsyncIterator[dict]:
        assert self.ws is not None
        tool_calls = {}
        async for msg in self.ws:
            d = json.loads(msg)
            t = d.get("type", "")
            if t in ("response.audio.delta", "response.output_audio.delta"):
                yield {"type": "audio", "pcm": base64.b64decode(d["delta"])}
            elif t == "input_audio_buffer.speech_started":
                yield {"type": "interrupt"}
            elif t == "conversation.item.input_audio_transcription.completed":
                yield {"type": "user_text", "text": d.get("transcript", "")}
            elif t in ("response.audio_transcript.done", "response.output_audio_transcript.done"):
                yield {"type": "agent_text", "text": d.get("transcript", "")}
            elif t in ("response.function_call_arguments.delta", "response.tool_call_arguments.delta"):
                call_id = d.get("call_id") or d.get("item_id")
                if call_id:
                    entry = tool_calls.setdefault(call_id, {"name": d.get("name", ""), "arguments": ""})
                    entry["arguments"] += d.get("delta", "")
            elif t in ("response.function_call_arguments.done", "response.tool_call_arguments.done"):
                call_id = d.get("call_id") or d.get("item_id")
                name = d.get("name") or tool_calls.get(call_id, {}).get("name")
                arguments = d.get("arguments") or tool_calls.get(call_id, {}).get("arguments", "{}")
                if self.ws and call_id and name and dispatch_tool:
                    output = dispatch_tool(name, arguments)
                    await self.ws.send(json.dumps({
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": output,
                        },
                    }))
                    await self.ws.send(json.dumps({"type": "response.create"}))
            elif t == "response.output_item.done":
                item = d.get("item") or {}
                if item.get("type") in ("function_call", "tool_call") and dispatch_tool:
                    call_id = item.get("call_id") or item.get("id")
                    name = item.get("name")
                    arguments = item.get("arguments") or "{}"
                    if self.ws and call_id and name:
                        output = dispatch_tool(name, arguments)
                        await self.ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": output,
                            },
                        }))
                        await self.ws.send(json.dumps({"type": "response.create"}))

    async def close(self) -> None:
        if self.ws:
            try: await self.ws.close()
            except Exception: pass
            self.ws = None
