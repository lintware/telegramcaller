"""Telegram private-call <-> ElevenLabs Conversational AI bridge (v4).

Architecture:
  * Telethon signs in; pytgcalls auto-accepts incoming calls.
  * Outbound: ExternalMedia.AUDIO + send_frame at 10ms cadence streams the
    agent's PCM (upsampled 16k -> 48k) to the call.
  * Inbound (this is the hard part — on_frames doesn't deliver private-call
    peer audio): we tell ntgcalls to record peer audio to a named-pipe FIFO
    as MP3, then spawn an ffmpeg subprocess that reads the FIFO and emits
    16kHz mono PCM on stdout. A task reads that PCM, base64-encodes it, and
    pushes it to the ElevenLabs Conversational AI websocket.
"""
import asyncio
import audioop
import base64
import json
import logging
import os
import stat
import time

from dotenv import load_dotenv
from pytgcalls import PyTgCalls
from pytgcalls.types import (
    ChatUpdate, Device, ExternalMedia, MediaStream, RecordStream, Update,
)
from pytgcalls.types.raw import AudioParameters
from telethon import TelegramClient
import websockets

load_dotenv()
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION = os.environ.get("TG_SESSION", "telecall")
EL_API_KEY = os.environ["ELEVENLABS_API_KEY"]
EL_AGENT_ID = os.environ.get("EL_AGENT_ID", "agent_7601krt8vj3dfjwrgm5r6jym6zes")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("telecall.bridge")

CALL_RATE = 48000
FRAME_MS = 10
FRAME_BYTES = int(CALL_RATE * 1 * 2 * FRAME_MS / 1000)  # 960 bytes / 10ms mono 48k

sessions: dict[int, dict] = {}


async def el_session(chat_id: int):
    url = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={EL_AGENT_ID}"
    ws = await websockets.connect(url, additional_headers={"xi-api-key": EL_API_KEY})
    await ws.send(json.dumps({"type": "conversation_initiation_client_data"}))
    log.info("EL ws opened chat=%s", chat_id)

    state = {
        "ws": ws,
        "up_state": None,
        "playback_buf": bytearray(),
        "ffmpeg_proc": None,
        "fifo_path": None,
    }
    sessions[chat_id] = state

    async def reader():
        try:
            async for msg in ws:
                d = json.loads(msg)
                t = d.get("type")
                if t == "audio":
                    pcm16k = base64.b64decode(d["audio_event"]["audio_base_64"])
                    pcm48k, state["up_state"] = audioop.ratecv(
                        pcm16k, 2, 1, 16000, 48000, state["up_state"]
                    )
                    state["playback_buf"].extend(pcm48k)
                elif t == "ping":
                    await ws.send(json.dumps({"type": "pong", "event_id": d["ping_event"]["event_id"]}))
                elif t == "interruption":
                    state["playback_buf"].clear()
                elif t == "user_transcript":
                    log.info("USER: %s", d.get("user_transcription_event", {}).get("user_transcript"))
                elif t == "agent_response":
                    log.info("AGENT: %s", d.get("agent_response_event", {}).get("agent_response"))
        except Exception as e:
            log.info("EL reader exit: %s", e)

    state["reader_task"] = asyncio.create_task(reader())
    return state


def start_player(chat_id: int, calls: PyTgCalls):
    state = sessions[chat_id]
    async def player():
        period = FRAME_MS / 1000.0
        next_t = time.monotonic()
        silence = b"\x00" * FRAME_BYTES
        while chat_id in sessions:
            if len(state["playback_buf"]) >= FRAME_BYTES:
                chunk = bytes(state["playback_buf"][:FRAME_BYTES])
                del state["playback_buf"][:FRAME_BYTES]
            else:
                chunk = silence
            try:
                await calls.send_frame(chat_id, Device.MICROPHONE, chunk)
            except Exception:
                await asyncio.sleep(0.05)
                next_t = time.monotonic()
                continue
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_t = time.monotonic()
    state["player_task"] = asyncio.create_task(player())


async def start_inbound_pipe(chat_id: int, calls: PyTgCalls):
    """FIFO -> ntgcalls writes mp3 -> ffmpeg decodes -> raw 16k PCM -> EL ws."""
    state = sessions[chat_id]
    fifo_path = f"/tmp/peer_{chat_id}_{int(time.time())}.mp3"
    try:
        os.unlink(fifo_path)
    except FileNotFoundError:
        pass
    os.mkfifo(fifo_path)
    state["fifo_path"] = fifo_path
    log.info("FIFO created: %s", fifo_path)

    # Spawn ffmpeg reading mp3 from FIFO, emitting 16k mono PCM on stdout.
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "error",
        "-f", "mp3", "-i", fifo_path,
        "-f", "s16le", "-ac", "1", "-ar", "16000",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    state["ffmpeg_proc"] = proc
    log.info("ffmpeg decoder spawned pid=%s", proc.pid)

    # Tell ntgcalls to start recording peer audio into the FIFO.
    # NOTE: this call BLOCKS until something opens the read end (ffmpeg does that).
    await calls.record(
        chat_id,
        RecordStream(audio=fifo_path, audio_parameters=AudioParameters(CALL_RATE, 1)),
    )
    log.info("ntgcalls.record() started -> %s", fifo_path)

    async def reader():
        sent = 0
        try:
            while True:
                chunk = await proc.stdout.read(3200)  # 100ms @ 16k mono PCM16
                if not chunk:
                    break
                sent += len(chunk)
                try:
                    await state["ws"].send(json.dumps({
                        "user_audio_chunk": base64.b64encode(chunk).decode("ascii"),
                    }))
                except Exception as e:
                    log.info("EL send failed: %s", e); break
            log.info("ffmpeg reader exit, %d PCM bytes -> EL", sent)
        except asyncio.CancelledError:
            pass

    state["inbound_task"] = asyncio.create_task(reader())


async def close_session(chat_id: int):
    state = sessions.pop(chat_id, None)
    if not state:
        return
    for k in ("reader_task", "player_task", "inbound_task"):
        t = state.get(k)
        if t:
            t.cancel()
    proc = state.get("ffmpeg_proc")
    if proc and proc.returncode is None:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception:
            try: proc.kill()
            except Exception: pass
    try: await state["ws"].close()
    except Exception: pass
    fifo = state.get("fifo_path")
    if fifo:
        try: os.unlink(fifo)
        except Exception: pass
    log.info("session closed chat=%s", chat_id)


async def main():
    tele = TelegramClient(SESSION, API_ID, API_HASH)
    calls = PyTgCalls(tele)

    @calls.on_update()
    async def on_update(_: PyTgCalls, update: Update):
        if isinstance(update, ChatUpdate):
            if update.status & ChatUpdate.Status.INCOMING_CALL:
                log.info("INCOMING_CALL user=%s", update.chat_id)
                try:
                    await el_session(update.chat_id)
                    await calls.play(
                        update.chat_id,
                        MediaStream(media_path=ExternalMedia.AUDIO,
                                    audio_parameters=AudioParameters(CALL_RATE, 1)),
                    )
                    await start_inbound_pipe(update.chat_id, calls)
                    await asyncio.sleep(0.3)
                    start_player(update.chat_id, calls)
                    log.info("call fully armed (out + in)")
                except Exception as e:
                    log.exception("accept failed: %s", e)
                    await close_session(update.chat_id)
            elif update.status & ChatUpdate.Status.DISCARDED_CALL:
                log.info("DISCARDED_CALL user=%s", update.chat_id)
                await close_session(update.chat_id)

    await calls.start()
    me = await tele.get_me()
    log.info("READY as %s (+%s). Call to test conversation.", me.first_name, me.phone)
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
