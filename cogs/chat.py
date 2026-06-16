import discord
from discord import app_commands
from discord.ext import commands

from services.odysseus_client import OdysseusClient


class Chat(commands.Cog):
    """Thin Discord interface to the V.E.G.A.R.D. core service."""

    def __init__(self, bot: commands.Bot, odysseus: OdysseusClient, chat_channel_id: int | None):
        self.bot = bot
        self.odysseus = odysseus
        self.chat_channel_id = chat_channel_id  # free-chat channel, no command needed here

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
                    content = f"{message.author.display_name}: {message.content}"
                    reply = await self.odysseus.chat(str(message.channel.id), content)
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
                content = f"{message.author.display_name}: {content}"
                reply = await self.odysseus.chat(str(message.channel.id), content)
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
