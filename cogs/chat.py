import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from services.odysseus_client import OdysseusClient

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


class Chat(commands.Cog):
    """Thin Discord interface to the V.E.G.A.R.D. core service."""

    def __init__(self, bot: commands.Bot, odysseus: OdysseusClient, chat_channel_id: int | None):
        self.bot = bot
        self.odysseus = odysseus
        self.chat_channel_id = chat_channel_id
        self._users: dict = _load_users()
        self._context: str | None = _build_context(self._users)

    # ── /chat (optional, works anywhere) ──────────────────────────────────────

    @app_commands.command(name="chat", description="Chat with V.E.G.A.R.D. (works in any channel)")
    @app_commands.describe(message="Your message")
    async def slash_chat(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        try:
            reply = await self.odysseus.chat(interaction.user.id, message)
        except Exception as exc:
            await interaction.followup.send(f"V.E.G.A.R.D. is down: `{exc}`", ephemeral=True)
            return
        embed = discord.Embed(description=reply, color=discord.Color.blurple())
        embed.set_footer(text=f"V.E.G.A.R.D. · {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    # ── /clear ────────────────────────────────────────────────────────────────

    @app_commands.command(name="clear", description="Clear this channel's conversation history with V.E.G.A.R.D.")
    async def slash_clear(self, interaction: discord.Interaction):
        await self.odysseus.clear(str(interaction.channel_id))
        await interaction.response.send_message("History cleared.", ephemeral=True)

    # ── /history ──────────────────────────────────────────────────────────────

    @app_commands.command(name="history", description="Check this channel's conversation history size")
    async def slash_history(self, interaction: discord.Interaction):
        count = await self.odysseus.history_count(str(interaction.channel_id))
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
            async with message.channel.typing():
                try:
                    content = _tagged(message.author.display_name, message.content)
                    reply = await self.odysseus.chat(str(message.channel.id), content, self._context)
                except Exception as exc:
                    await message.reply(f"V.E.G.A.R.D. is down: `{exc}`")
                    return
            await self._send(message, reply)
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

        async with message.channel.typing():
            try:
                content = _tagged(message.author.display_name, content)
                reply = await self.odysseus.chat(str(message.channel.id), content, self._context)
            except Exception as exc:
                await message.reply(f"V.E.G.A.R.D. is down: `{exc}`")
                return

        await self._send(message, reply)

    async def _send(self, message: discord.Message, text: str) -> None:
        """Reply, splitting at 2000 chars if needed."""
        if len(text) <= 2000:
            await message.reply(text)
        else:
            chunks = [text[i:i + 1990] for i in range(0, len(text), 1990)]
            for i, chunk in enumerate(chunks):
                await (message.reply(chunk) if i == 0 else message.channel.send(chunk))


async def setup(bot: commands.Bot, odysseus: OdysseusClient, chat_channel_id: int | None):
    await bot.add_cog(Chat(bot, odysseus, chat_channel_id))
