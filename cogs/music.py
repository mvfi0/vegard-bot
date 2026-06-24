import asyncio
import os
import random
from collections import deque

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

_COMFORT_FALLBACK = [
    "lofi hip hop chill beats sad",
    "comfort playlist rainy day acoustic",
    "soft piano music emotional",
    "lofi beats melancholic study",
    "peaceful sad ambient music",
]

_YDL_OPTS = {
    "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "noplaylist": True,
    "source_address": "0.0.0.0",
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
}

_FFMPEG_BEFORE_OPTS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
    "-user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\""
)

_FFMPEG_OPTS = {
    "before_options": _FFMPEG_BEFORE_OPTS,
    "options": "-vn -bufsize 64k",
}


def _fetch_audio(query: str) -> tuple[str, str, str | None]:
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return info["url"], info.get("title", query), info.get("thumbnail")


def _load_spotify_tracks() -> list[str]:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        return []

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    playlist_id = os.getenv("SPOTIFY_PLAYLIST_ID")
    if not all([client_id, client_secret, playlist_id]):
        return []

    cache_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", ".spotify_cache"
    )
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    try:
        sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri="http://127.0.0.1:8000/callback",
                scope="playlist-read-private",
                cache_path=cache_path,
                open_browser=True,
            )
        )
        results = sp.playlist_tracks(playlist_id)
        tracks: list[str] = []
        while results:
            for item in results["items"]:
                track = item.get("track") or item.get("item")
                if track and track.get("name"):
                    artists = ", ".join(a["name"] for a in track["artists"])
                    tracks.append(f"{track['name']} {artists}")
            results = sp.next(results) if results.get("next") else None
        print(f"[Music] Loaded {len(tracks)} tracks from Spotify playlist")
        return tracks
    except Exception as exc:
        print(f"[Music] Spotify load failed: {exc}")
        return []


def _now_playing_embed(title: str, thumbnail: str | None = None) -> discord.Embed:
    embed = discord.Embed(
        description=f"🎵 **{title}**",
        color=discord.Color.from_rgb(30, 215, 96),
    )
    if thumbnail:
        embed.set_image(url=thumbnail)
    return embed


_LOOP_MODES = ("off", "queue", "song")
_LOOP_EMOJI = {"off": "🔁", "queue": "🔁", "song": "🔂"}
_LOOP_STYLE = {
    "off": discord.ButtonStyle.secondary,
    "queue": discord.ButtonStyle.success,
    "song": discord.ButtonStyle.primary,
}


class NowPlayingView(discord.ui.View):
    def __init__(self, cog: "MusicCog", guild: discord.Guild):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.guild.voice_client
        if not vc:
            await interaction.response.defer()
            return
        if vc.is_playing():
            vc.pause()
            button.emoji = "▶"
        elif vc.is_paused():
            vc.resume()
            button.emoji = "⏸"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()  # triggers after() → _play_next
        await interaction.response.defer()

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.cog._loop_mode.get(self.guild.id, "queue")
        next_mode = _LOOP_MODES[(_LOOP_MODES.index(current) + 1) % len(_LOOP_MODES)]
        self.cog._loop_mode[self.guild.id] = next_mode
        button.emoji = _LOOP_EMOJI[next_mode]
        button.style = _LOOP_STYLE[next_mode]
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description="⏹ Stopped.", color=discord.Color.red()),
            view=None,
        )
        await self.cog.stop(self.guild)
        self.stop()


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active: dict[int, bool] = {}
        self._tracks: list[str] = []
        self._queue: dict[int, deque] = {}
        self._np_message: dict[int, discord.Message] = {}
        self._loop_mode: dict[int, str] = {}  # "off" | "queue" | "song"
        self._current: dict[int, tuple[str, str, str | None]] = {}  # (url, title, thumbnail)
        self._current_is_public: dict[int, bool] = {}  # False for Spotify tracks
        self._requests: dict[int, deque] = {}  # songs queued via /play (shown in /queue)
        self._mood_session: dict[int, bool] = {}  # True only when started by mood trigger

    async def cog_load(self) -> None:
        loop = asyncio.get_running_loop()
        self._tracks = await loop.run_in_executor(None, _load_spotify_tracks)

    def _refill_queue(self, guild_id: int) -> None:
        source = list(self._tracks) if self._tracks else list(_COMFORT_FALLBACK)
        random.shuffle(source)
        self._queue[guild_id] = deque(source)

    def _pop_query(self, guild_id: int) -> str:
        if not self._queue.get(guild_id):
            self._refill_queue(guild_id)
        return f"ytsearch:{self._queue[guild_id].popleft()}"

    async def join_and_play(
        self,
        text_channel: discord.TextChannel,
        voice_channel: discord.VoiceChannel,
        query: str | None = None,
    ) -> None:
        guild = text_channel.guild
        vc = guild.voice_client

        if vc:
            await vc.move_to(voice_channel)
        else:
            vc = await voice_channel.connect()

        await guild.change_voice_state(channel=voice_channel, self_deaf=True)

        if self._active.get(guild.id):
            return

        self._refill_queue(guild.id)
        self._active[guild.id] = True
        self._mood_session[guild.id] = (query is None)  # no query = mood trigger started this
        await self._play_next(vc, text_channel, query)

    async def _play_next(
        self,
        vc: discord.VoiceClient,
        text_channel: discord.TextChannel,
        query: str | None = None,
    ) -> None:
        guild_id = vc.guild.id
        if not self._active.get(guild_id) or not vc.is_connected():
            return

        loop_mode = self._loop_mode.get(guild_id, "queue")

        # Song loop: replay the current track without fetching a new one
        is_public = False  # True only for /play songs — those get the now-playing embed
        if loop_mode == "song" and not query and guild_id in self._current:
            url, title, thumbnail = self._current[guild_id]
            is_public = self._current_is_public.get(guild_id, False)
        elif not query and self._requests.get(guild_id):
            # Pre-fetched /play request — no need to call yt-dlp again
            url, title, thumbnail = self._requests[guild_id].popleft()
            self._current[guild_id] = (url, title, thumbnail)
            is_public = True
        else:
            # Stop if: loop is off, no explicit query, AND not a mood session (no Spotify fallback)
            no_spotify = not self._mood_session.get(guild_id)
            if not query and (no_spotify or (loop_mode == "off" and not self._queue.get(guild_id))):
                self._active[guild_id] = False
                return

            search = query or self._pop_query(guild_id)
            loop = asyncio.get_running_loop()

            try:
                url, title, thumbnail = await loop.run_in_executor(None, _fetch_audio, search)
            except Exception as exc:
                print(f"[Music] fetch error: {exc}")
                await text_channel.send(f"Couldn't load track: `{exc}`")
                self._active[guild_id] = False
                return

            self._current[guild_id] = (url, title, thumbnail)
            is_public = bool(query)  # explicit /play query → public; Spotify → private

        self._current_is_public[guild_id] = is_public

        print(f"[Music] Now playing: {title}")

        # Only update the now-playing embed for /play songs — Spotify tracks play silently
        if is_public:
            embed = _now_playing_embed(title, thumbnail)
            view = NowPlayingView(self, vc.guild)
            loop_btn = view.loop_toggle
            loop_btn.emoji = _LOOP_EMOJI[loop_mode]
            loop_btn.style = _LOOP_STYLE[loop_mode]

            existing = self._np_message.get(guild_id)
            if existing:
                try:
                    await existing.edit(embed=embed, view=view)
                except discord.NotFound:
                    existing = None

            if not existing:
                self._np_message[guild_id] = await text_channel.send(embed=embed, view=view)

        def after(error: Exception | None) -> None:
            if error:
                print(f"[Music] playback error for '{title}': {error}")
            if self._active.get(guild_id):
                asyncio.run_coroutine_threadsafe(
                    self._play_next(vc, text_channel), self.bot.loop
                )

        vc.play(discord.FFmpegPCMAudio(url, **_FFMPEG_OPTS), after=after)

    async def stop(self, guild: discord.Guild) -> None:
        self._active[guild.id] = False
        self._queue.pop(guild.id, None)
        self._np_message.pop(guild.id, None)
        self._loop_mode.pop(guild.id, None)
        self._current.pop(guild.id, None)
        self._current_is_public.pop(guild.id, None)
        self._requests.pop(guild.id, None)
        self._mood_session.pop(guild.id, None)
        vc = guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()

    # ── Slash commands ────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song by name or YouTube URL")
    @app_commands.describe(query="Song name or YouTube URL")
    async def slash_play(self, interaction: discord.Interaction, query: str):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)  # only shown to the caller
            return

        await interaction.response.defer(thinking=True)

        search = query if query.startswith("http") else f"ytsearch:{query}"
        guild_id = interaction.guild.id

        if self._active.get(guild_id):
            loop = asyncio.get_running_loop()
            try:
                url, title, thumbnail = await loop.run_in_executor(None, _fetch_audio, search)
            except Exception as exc:
                await interaction.followup.send(f"Couldn't find that track: `{exc}`")
                return
            self._requests.setdefault(guild_id, deque()).append((url, title, thumbnail))
            await interaction.followup.send(f"➕ Added to queue: **{title}**")
        else:
            await self.join_and_play(interaction.channel, member.voice.channel, search)
            await interaction.followup.send("▶ Playing now.")

    @app_commands.command(name="skip", description="Skip to the next track")
    async def slash_skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("Nothing is playing.")
            return
        vc.stop()
        await interaction.response.send_message("⏭ Skipped.")

    @app_commands.command(name="stop", description="Stop music and leave the voice channel")
    async def slash_stop(self, interaction: discord.Interaction):
        await self.stop(interaction.guild)
        await interaction.response.send_message("⏹ Stopped.")

    @app_commands.command(name="loop", description="Cycle loop mode: queue → song → off")
    async def slash_loop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        current = self._loop_mode.get(guild_id, "queue")
        next_mode = _LOOP_MODES[(_LOOP_MODES.index(current) + 1) % len(_LOOP_MODES)]
        self._loop_mode[guild_id] = next_mode
        labels = {"off": "Off", "queue": "Loop queue 🔁", "song": "Loop song 🔂"}
        await interaction.response.send_message(f"Loop mode: **{labels[next_mode]}**")

    @app_commands.command(name="queue", description="Show songs queued via /play")
    async def slash_queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        q = self._requests.get(guild_id)
        if not q:
            await interaction.response.send_message("No songs in the queue. Use `/play` to add one.")
            return

        upcoming = list(q)[:10]
        lines = [f"`{i + 1}.` {title}" for i, (_, title, _) in enumerate(upcoming)]
        remaining = len(q) - len(upcoming)
        if remaining:
            lines.append(f"*...and {remaining} more*")

        embed = discord.Embed(
            title="🎶 Up Next",
            description="\n".join(lines),
            color=discord.Color.from_rgb(30, 215, 96),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
