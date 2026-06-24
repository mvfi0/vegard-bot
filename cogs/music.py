import asyncio
import os
import random
from collections import deque

import discord
import yt_dlp
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

        search = query or self._pop_query(guild_id)
        loop = asyncio.get_running_loop()

        try:
            url, title, thumbnail = await loop.run_in_executor(None, _fetch_audio, search)
        except Exception as exc:
            print(f"[Music] fetch error: {exc}")
            await text_channel.send(f"Couldn't load track: `{exc}`")
            self._active[guild_id] = False
            return

        print(f"[Music] Now playing: {title}")
        embed = _now_playing_embed(title, thumbnail)
        view = NowPlayingView(self, vc.guild)

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
        vc = guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
