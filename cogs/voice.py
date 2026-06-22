import asyncio
import os
import time

import davey
import discord
from discord import app_commands
from discord.ext import commands, voice_recv
from discord.ext.voice_recv import opus as vr_opus

from core.services.tts_service import TTSService
from core.services.whisper_service import WhisperService

SILENCE_TIMEOUT = 1.2  # seconds of silence before transcribing
MIN_BYTES = int(48000 * 2 * 2 * 0.05)  # ~50 ms minimum (Whisper VAD handles the rest)


def _patch_dave():
    """Monkey-patch voice_recv's PacketDecoder to decrypt DAVE E2EE before Opus decode."""
    original = vr_opus.PacketDecoder._decode_packet

    def _dave_decode(self, packet):
        if packet and self._cached_id and packet.decrypted_data:
            vc = self.sink.voice_client
            dave_session = getattr(getattr(vc, "_connection", None), "dave_session", None)
            if dave_session and not dave_session.can_passthrough(self._cached_id):
                try:
                    packet.decrypted_data = dave_session.decrypt(
                        self._cached_id, davey.MediaType.audio, packet.decrypted_data
                    )
                except Exception:
                    pass  # packet is unencrypted during DAVE transition — original data is valid Opus
        return original(self, packet)

    vr_opus.PacketDecoder._decode_packet = _dave_decode


_patch_dave()


class VoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot, ai, whisper: WhisperService, tts: TTSService):
        self.bot = bot
        self.ai = ai
        self.whisper = whisper
        self.tts = tts
        # per-guild state
        self._text_channels: dict[int, discord.TextChannel] = {}
        self._buffers: dict[int, dict[int, bytearray]] = {}
        self._members: dict[int, dict[int, discord.Member]] = {}
        self._last_audio: dict[int, dict[int, float]] = {}
        self._processing: dict[int, set[int]] = {}
        self._poll_tasks: dict[int, asyncio.Task] = {}
        self._tts_queues: dict[int, asyncio.Queue] = {}
        self._tts_workers: dict[int, asyncio.Task] = {}

    # ── /join ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="join", description="Bot joins your voice channel and listens")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "You need to be in a voice channel first.", ephemeral=True
            )

        guild = interaction.guild
        vc_channel = interaction.user.voice.channel

        if guild.voice_client:
            await guild.voice_client.disconnect(force=True)
            self._cleanup(guild.id)

        vc = await vc_channel.connect(cls=voice_recv.VoiceRecvClient)
        self._text_channels[guild.id] = interaction.channel
        self._buffers[guild.id] = {}
        self._members[guild.id] = {}
        self._last_audio[guild.id] = {}
        self._processing[guild.id] = set()

        # BasicSink callback is synchronous — safe to call from audio thread
        sink = voice_recv.BasicSink(self._make_audio_cb(guild.id))
        vc.listen(sink)
        print(f"[Voice] listening in {vc_channel.name}")

        queue: asyncio.Queue = asyncio.Queue()
        self._tts_queues[guild.id] = queue
        self._poll_tasks[guild.id] = asyncio.create_task(self._poll_silence(guild.id))
        self._tts_workers[guild.id] = asyncio.create_task(self._tts_worker(guild.id))

        await interaction.response.send_message(
            f"Joined **{vc_channel.name}** — listening. I'll transcribe here and speak in voice."
        )

    # ── /leave ────────────────────────────────────────────────────────────────

    @app_commands.command(name="leave", description="Bot leaves the voice channel")
    async def leave(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.voice_client:
            return await interaction.response.send_message(
                "I'm not in a voice channel.", ephemeral=True
            )
        await guild.voice_client.disconnect()
        self._cleanup(guild.id)
        await interaction.response.send_message("Left the voice channel.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _make_audio_cb(self, guild_id: int):
        """Returns a sync callback for BasicSink; called from audio thread."""
        def callback(user, data: voice_recv.VoiceData):
            try:
                if user is None or user.bot or not data.pcm:
                    return
                uid = user.id
                self._buffers[guild_id].setdefault(uid, bytearray()).extend(data.pcm)
                self._members[guild_id][uid] = user
                self._last_audio[guild_id][uid] = time.monotonic()
            except Exception as exc:
                print(f"[Voice] callback error: {exc}")
        return callback

    async def _poll_silence(self, guild_id: int):
        """Background task: detect silence per user and kick off transcription."""
        while True:
            await asyncio.sleep(0.3)
            now = time.monotonic()
            last = self._last_audio.get(guild_id, {})
            processing = self._processing.get(guild_id, set())

            for uid in list(last):
                if now - last[uid] >= SILENCE_TIMEOUT and uid not in processing:
                    buf = bytes(self._buffers[guild_id].pop(uid, bytearray()))
                    user = self._members[guild_id].pop(uid, None)
                    del last[uid]
                    if len(buf) < MIN_BYTES or user is None:
                        continue
                    processing.add(uid)
                    asyncio.create_task(self._process(guild_id, uid, user, buf))

    async def _process(self, guild_id: int, uid: int, user: discord.Member, buf: bytes):
        try:
            channel = self._text_channels.get(guild_id)

            text = await self.whisper.transcribe(buf)
            print(f"[Voice] {user.display_name}: {text!r}")
            if not text:
                return

            if channel:
                await channel.send(f"🎤 **{user.display_name}**: {text}")

            response = await self.ai.chat(f"{guild_id}_voice", text)
            if not response:
                return

            if channel:
                await channel.send(f"🤖 **V.E.G.A.R.D.**: {response}")

            queue = self._tts_queues.get(guild_id)
            if queue:
                await queue.put(response)
        except Exception as exc:
            print(f"[Voice] process error: {exc}")
        finally:
            self._processing.get(guild_id, set()).discard(uid)

    async def _tts_worker(self, guild_id: int):
        queue = self._tts_queues[guild_id]
        while True:
            text = await queue.get()
            guild = self.bot.get_guild(guild_id)
            vc = guild.voice_client if guild else None
            path = None
            try:
                path = await self.tts.synthesize(text)
                if vc and not vc.is_playing():
                    done = asyncio.Event()
                    vc.play(discord.FFmpegPCMAudio(path), after=lambda _: done.set())
                    await done.wait()
            except Exception as exc:
                print(f"[TTS] {exc}")
            finally:
                if path and os.path.exists(path):
                    os.unlink(path)
                queue.task_done()

    def _cleanup(self, guild_id: int):
        for tasks in (self._poll_tasks, self._tts_workers):
            t = tasks.pop(guild_id, None)
            if t:
                t.cancel()
        for d in (self._text_channels, self._buffers, self._members,
                  self._last_audio, self._processing, self._tts_queues):
            d.pop(guild_id, None)


async def setup(bot: commands.Bot, ai, whisper: WhisperService, tts: TTSService):
    await bot.add_cog(VoiceCog(bot, ai, whisper, tts))
