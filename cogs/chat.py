import json
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core.services.ollama_service import OllamaService
from services.search import web_search

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

    def __init__(self, bot: commands.Bot, ai: OllamaService, chat_channel_id: int | None):
        self.bot = bot
        self.ai = ai
        self.chat_channel_id = chat_channel_id
        self._users: dict = _load_users()
        self._context: str | None = _build_context(self._users)

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
        if self.chat_channel_id and message.channel.id == self.chat_channel_id:
            content = _tagged(message.author.display_name, message.content)
            await self._stream_reply(message, str(message.channel.id), content)
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

    async def _stream_reply(self, message: discord.Message, channel_id: str, tagged_content: str) -> None:
        """Stream tokens into a Discord message, editing at most once per second."""
        sent = await message.reply("▌")
        last_edit = time.monotonic()
        final_text = ""

        try:
            async for text in self.ai.stream_chat(channel_id, tagged_content, self._context):
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


async def setup(bot: commands.Bot, ai: OllamaService, chat_channel_id: int | None):
    await bot.add_cog(Chat(bot, ai, chat_channel_id))
