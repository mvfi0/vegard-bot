import asyncio
import os
import random

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
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
}

_FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def _fetch_audio(query: str) -> tuple[str, str]:
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return info["url"], info.get("title", query)


def _load_spotify_tracks() -> list[str]:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError:
        return []

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    playlist_id = os.getenv("SPOTIFY_PLAYLIST_ID")
    if not all([client_id, client_secret, playlist_id]):
        return []

    try:
        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id, client_secret=client_secret
            )
        )
        results = sp.playlist_tracks(playlist_id)
        tracks: list[str] = []
        while results:
            for item in results["items"]:
                track = item.get("track")
                if track and track.get("name"):
                    artists = ", ".join(a["name"] for a in track["artists"])
                    tracks.append(f"{track['name']} {artists}")
            results = sp.next(results) if results.get("next") else None
        print(f"[Music] Loaded {len(tracks)} tracks from Spotify playlist")
        return tracks
    except Exception as exc:
        print(f"[Music] Spotify load failed: {exc}")
        return []


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active: dict[int, bool] = {}
        self._tracks: list[str] = []

    async def cog_load(self) -> None:
        loop = asyncio.get_running_loop()
        self._tracks = await loop.run_in_executor(None, _load_spotify_tracks)

    def _pick_query(self) -> str:
        source = self._tracks if self._tracks else _COMFORT_FALLBACK
        return f"ytsearch:{random.choice(source)}"

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

        # Self-deafen so the bot doesn't receive audio
        await guild.change_voice_state(channel=voice_channel, self_deaf=True)

        if self._active.get(guild.id):
            return

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

        search = query or self._pick_query()
        loop = asyncio.get_running_loop()

        try:
            url, title = await loop.run_in_executor(None, _fetch_audio, search)
        except Exception as exc:
            print(f"[Music] fetch error: {exc}")
            self._active[guild_id] = False
            return

        def after(error: Exception | None) -> None:
            if error:
                print(f"[Music] playback error: {error}")
            if self._active.get(guild_id):
                asyncio.run_coroutine_threadsafe(
                    self._play_next(vc, text_channel), self.bot.loop
                )

        vc.play(discord.FFmpegPCMAudio(url, **_FFMPEG_OPTS), after=after)

    async def stop(self, guild: discord.Guild) -> None:
        self._active[guild.id] = False
        vc = guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
