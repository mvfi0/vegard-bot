import asyncio
import json
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core.services.ollama_service import OllamaService
from services.lyrics import fetch_lyrics, parse_yt_title
from services.rate_limiter import RateLimiter
from services.search import web_search

# Words that suggest the user is emotionally down
_MOOD_TRIGGERS = {
    # English
    "sad", "sadness", "tired", "exhausted", "lonely", "alone", "depressed",
    "depression", "anxious", "anxiety", "stressed", "stress", "upset",
    "unhappy", "miserable", "crying", "cry", "hurt", "lost", "empty",
    "hopeless", "struggling", "rough day", "bad day", "hard day",
    "need someone", "not okay", "not ok", "feeling down", "feel down",
    "broken", "overwhelmed", "burned out", "burn out",
    # Indonesian
    "sedih", "lelah", "capek", "sendirian", "kesepian", "galau",
    "bosen", "sepi", "nangis", "hancur", "gabut", "down",
    "ga semangat", "gak semangat", "pengen nangis", "butuh temen",
}

# Explicit playlist requests — owner asking the bot to play their Spotify playlist
_PLAYLIST_TRIGGERS = {
    "play me my playlist", "play my playlist", "play my comfort playlist",
    "put on my playlist", "start my playlist", "play me something",
    "play some music", "put on some music", "play music for me",
    "play me music", "play me a song", "play me some music",
    # Indonesian
    "puterin playlist", "puterin musik", "putar playlist", "putar musik",
    "play playlist aku", "play musik dong", "play dong", "kasih musik dong",
    "mau dengerin musik", "dengerin musik", "mau denger musik",
}

# Words that mean "stop the music / leave vc"
_STOP_TRIGGERS = {
    "stop the music", "stop music", "leave vc", "leave the vc",
    "disconnect", "keluar vc", "berhenti", "stop playing",
}


def _is_mood_message(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in _MOOD_TRIGGERS)


def _is_playlist_request(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in _PLAYLIST_TRIGGERS)


def _is_stop_music(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in _STOP_TRIGGERS)

_USERS_FILE = Path(__file__).parent.parent / "users.json"

_ID_WORDS = {
    "gue", "lu", "lo", "gak", "ga", "ngga", "nggak", "aja", "sih", "dong",
    "lah", "nih", "tuh", "deh", "kan", "yuk", "udah", "gimana", "kayak",
    "banget", "bgt", "anjir", "gokil", "mantul", "iya", "enggak", "kalo",
    "kalau", "tapi", "karena", "jadi", "mau", "bisa", "sama", "juga",
    "yang", "dan", "ke", "dari", "untuk", "ada", "sudah", "belum",
    "tidak", "bukan", "ini", "itu", "apa", "siapa", "dimana", "bagaimana",
    "makanya", "emang", "tetep", "balik", "lagi", "masih", "beneran",
    "sekarang", "nanti", "habis", "terus", "abis", "pake", "ngapain",
}


def _detect_lang(text: str) -> str:
    words = set(text.lower().split())
    return "Indonesian" if words & _ID_WORDS else "English"


def _tagged(display_name: str, text: str) -> str:
    lang = _detect_lang(text)
    return f"[Reply in {lang} only] {display_name}: {text}"


def _load_users() -> dict:
    if _USERS_FILE.exists():
        return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
    return {}


def _build_context(users: dict) -> str | None:
    if not users:
        return None
    lines = [
        "Background info about people in this server — use this silently as context.",
        "Only reference these details if directly relevant or asked. Do NOT bring them up unprompted.",
    ]
    for profile in users.values():
        name = profile.get("name", "unknown")
        full = profile.get("full_name")
        notes = profile.get("notes", "")
        label = f"{name} ({full})" if full else name
        lines.append(f"- {label}: {notes}" if notes else f"- {label}")
    return "\n".join(lines)


class RegenerateView(discord.ui.View):
    def __init__(self, ai: OllamaService, channel_id: str, tagged_content: str, context: str | None):
        super().__init__(timeout=300)
        self.ai = ai
        self.channel_id = channel_id
        self.tagged_content = tagged_content
        self.context = context

    @discord.ui.button(label="Regenerate", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def regenerate(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        button.label = "Regenerating..."
        await interaction.response.edit_message(content="🔄 *Regenerating...*", view=self)

        self.ai.history.pop_last(self.channel_id, n=2)
        try:
            reply = await self.ai.chat(self.channel_id, self.tagged_content, self.context)
        except Exception as exc:
            button.disabled = False
            button.label = "Regenerate"
            await interaction.message.edit(content=f"Regeneration failed: `{exc}`", view=self)
            return

        button.disabled = False
        button.label = "Regenerate"
        await interaction.message.edit(content=reply[:2000], view=self)


class Chat(commands.Cog):
    """Thin Discord interface to the V.E.G.A.R.D. core service."""

    def __init__(
        self,
        bot: commands.Bot,
        ai: OllamaService,
        chat_channel_ids: set[int],
        owner_id: int | None = None,
    ):
        self.bot = bot
        self.ai = ai
        self.chat_channel_ids = chat_channel_ids
        self._owner_id = owner_id
        self._users: dict = _load_users()
        self._context: str | None = _build_context(self._users)
        self._chat_rl = RateLimiter(cooldown=3.0)
        self._search_rl = RateLimiter(cooldown=15.0)

    # ── /chat (optional, works anywhere) ──────────────────────────────────────

    @app_commands.command(name="chat", description="Chat with V.E.G.A.R.D. (works in any channel)")
    @app_commands.describe(message="Your message")
    async def slash_chat(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            content = _tagged(interaction.user.display_name, message)
            reply = await self.ai.chat(str(interaction.channel_id), content, self._context)
        except Exception as exc:
            await interaction.followup.send(f"V.E.G.A.R.D. is down: `{exc}`", ephemeral=True)
            return
        embed = discord.Embed(description=reply, color=discord.Color.blurple())
        embed.set_footer(text=f"V.E.G.A.R.D. · {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    # ── /search ───────────────────────────────────────────────────────────────

    @app_commands.command(name="search", description="Search the web and get a summarized answer")
    @app_commands.describe(query="What do you want to search for?")
    async def slash_search(self, interaction: discord.Interaction, query: str):
        wait = self._search_rl.check(interaction.user.id)
        if wait:
            await interaction.response.send_message(
                f"Slow down — wait {wait:.1f}s before searching again.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        try:
            loop = __import__("asyncio").get_event_loop()
            search_context = await loop.run_in_executor(None, web_search, query)
        except Exception as exc:
            await interaction.followup.send(f"Search failed: `{exc}`", ephemeral=True)
            return

        tagged = f"[Reply in English only] {interaction.user.display_name}: {query}"
        channel_id = str(interaction.channel_id)

        sent = await interaction.followup.send("▌")
        last_edit = time.monotonic()
        final_text = ""

        try:
            async for text in self.ai.stream_chat(channel_id, tagged, search_context):
                final_text = text
                now = time.monotonic()
                elapsed = now - last_edit
                at_boundary = text and text[-1] in ".?!\n"
                if text.strip() and (elapsed >= 0.6 or (at_boundary and elapsed >= 0.2)):
                    await sent.edit(content=text[:1998] + "▌")
                    last_edit = now
        except Exception as exc:
            await sent.edit(content=f"V.E.G.A.R.D. is down: `{exc}`")
            return

        view = RegenerateView(self.ai, channel_id, tagged, search_context)
        await sent.edit(content=(final_text.strip() or "…")[:2000], view=view)

    # ── /lyrics ───────────────────────────────────────────────────────────────

    @app_commands.command(name="lyrics", description="Fetch lyrics for a song (omit both to use the current track)")
    @app_commands.describe(song="Song title", artist="Artist name")
    async def slash_lyrics(
        self,
        interaction: discord.Interaction,
        song: str = "",
        artist: str = "",
    ):
        await interaction.response.defer(thinking=True)

        display_title = ""

        # No args — try to use the currently playing track
        if not song and not artist:
            music: "MusicCog | None" = self.bot.cogs.get("MusicCog")  # type: ignore[assignment]
            current = music._current.get(interaction.guild.id) if music else None
            if not current:
                await interaction.followup.send(
                    "Nothing is playing right now. Use `/lyrics song:... artist:...` instead."
                )
                return

            _, yt_title, _ = current
            parsed = parse_yt_title(yt_title)
            if not parsed:
                await interaction.followup.send(
                    f"Couldn't parse the current track title **\"{yt_title}\"** into artist/song. "
                    "Try `/lyrics song:... artist:...` manually."
                )
                return

            artist, song = parsed
            display_title = yt_title  # show the raw YT title in the header

        loop = __import__("asyncio").get_event_loop()
        lyrics = await loop.run_in_executor(None, fetch_lyrics, artist, song)

        # lyrics.ovh sometimes needs artist and title swapped — try the other order
        if not lyrics:
            lyrics = await loop.run_in_executor(None, fetch_lyrics, song, artist)
            if lyrics:
                artist, song = song, artist  # swap succeeded

        if not lyrics:
            # lyrics.ovh failed — fall back to Tavily + AI
            search_query = display_title or f"{song} {artist}".strip()
            try:
                search_context = await loop.run_in_executor(
                    None, web_search, f"{search_query} lyrics"
                )
                prompt = (
                    f"The user wants the full lyrics for \"{search_query}\". "
                    "Using the search results below, reproduce the complete lyrics as accurately as possible. "
                    "Output only the lyrics — no intro, no commentary, no links."
                )
                lyrics = await self.ai.chat(
                    str(interaction.channel_id), prompt, search_context
                )
            except Exception as exc:
                await interaction.followup.send(f"Lyrics search failed: `{exc}`")
                return

        label = display_title or f"{song} — {artist}"
        header = f"🎵 **{label}**\n\n"
        full = header + lyrics.strip()

        chunks = [full[i:i + 1990] for i in range(0, len(full), 1990)]
        await interaction.followup.send(chunks[0])
        for chunk in chunks[1:]:
            await interaction.channel.send(chunk)

    # ── /clear ────────────────────────────────────────────────────────────────

    @app_commands.command(name="clear", description="Clear this channel's conversation history with V.E.G.A.R.D.")
    async def slash_clear(self, interaction: discord.Interaction):
        self.ai.clear_history(str(interaction.channel_id))
        await interaction.response.send_message("History cleared.", ephemeral=True)

    # ── /history ──────────────────────────────────────────────────────────────

    @app_commands.command(name="history", description="Check this channel's conversation history size")
    async def slash_history(self, interaction: discord.Interaction):
        count = self.ai.history_count(str(interaction.channel_id))
        await interaction.response.send_message(
            f"**{count}** message(s) in this channel's history.", ephemeral=True
        )

    # ── message handler ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # ── Dedicated chat channel: respond to every message, no command needed ──
        if message.channel.id in self.chat_channel_ids:
            wait = self._chat_rl.check(message.author.id)
            if wait:
                await message.reply(f"Slow down — wait {wait:.1f}s.", delete_after=3)
                return

            # Music feature — owner only
            mood_triggered = False
            if self._owner_id and message.author.id == self._owner_id:
                music = self.bot.cogs.get("MusicCog")
                if music:
                    if _is_stop_music(message.content):
                        asyncio.create_task(music.stop(message.guild))
                    elif (
                        (_is_mood_message(message.content) or _is_playlist_request(message.content))
                        and isinstance(message.author, discord.Member)
                        and message.author.voice
                        and message.author.voice.channel
                    ):
                        mood_triggered = True
                        asyncio.create_task(
                            music.join_and_play(message.channel, message.author.voice.channel)
                        )

            content = _tagged(message.author.display_name, message.content)
            if mood_triggered:
                content += (
                    "\n[System: You are joining the user's voice channel right now and "
                    "playing their comfort playlist. Acknowledge this naturally and briefly "
                    "— something like telling them you'll put on their playlist. Keep it short and casual.]"
                )
            # Mood messages don't need web search — use plain streaming
            await self._stream_reply(message, str(message.channel.id), content,
                                     auto_search=not mood_triggered)
            return

        # ── Other channels: @mention required ─────────────────────────────────
        if self.bot.user not in message.mentions:
            return

        content = message.content
        for mention in [f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"]:
            content = content.replace(mention, "").strip()

        if not content:
            await message.reply("Sup. Ask me anything, use `/chat`, or head to the chat channel.")
            return

        content = _tagged(message.author.display_name, content)
        await self._stream_reply(message, str(message.channel.id), content)

    async def _stream_reply(self, message: discord.Message, channel_id: str, tagged_content: str, auto_search: bool = True) -> None:
        """Stream tokens into a Discord message, editing at most once per second."""
        sent = await message.reply("▌")
        last_edit = time.monotonic()
        final_text = ""

        stream_fn = self.ai.stream_chat_auto if auto_search else self.ai.stream_chat
        try:
            async for text in stream_fn(channel_id, tagged_content, self._context):
                final_text = text
                now = time.monotonic()
                elapsed = now - last_edit
                at_boundary = text and text[-1] in ".?!\n"
                if text.strip() and (elapsed >= 0.6 or (at_boundary and elapsed >= 0.2)):
                    await sent.edit(content=text[:1998] + "▌")
                    last_edit = now
        except Exception as exc:
            await sent.edit(content=f"V.E.G.A.R.D. is down: `{exc}`")
            return

        view = RegenerateView(self.ai, channel_id, tagged_content, self._context)
        await sent.edit(content=(final_text.strip() or "…")[:2000], view=view)

    async def _send(self, message: discord.Message, text: str, view: discord.ui.View | None = None) -> None:
        """Reply, splitting at 2000 chars if needed. View (e.g. Regenerate button) attached to first chunk only."""
        if len(text) <= 2000:
            await message.reply(text, view=view)
        else:
            chunks = [text[i:i + 1990] for i in range(0, len(text), 1990)]
            for i, chunk in enumerate(chunks):
                await (message.reply(chunk, view=view if i == 0 else None) if i == 0 else message.channel.send(chunk))


async def setup(
    bot: commands.Bot,
    ai: OllamaService,
    chat_channel_ids: set[int],
    owner_id: int | None = None,
):
    await bot.add_cog(Chat(bot, ai, chat_channel_ids, owner_id))
