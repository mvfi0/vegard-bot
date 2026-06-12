import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.chat import setup as setup_chat
from services.odysseus_client import OdysseusClient

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
ODYSSEUS_URL = os.getenv("ODYSSEUS_URL", "http://localhost:8000")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
_channel_env = os.getenv("CHAT_CHANNEL_ID", "")
CHAT_CHANNEL_ID: int | None = int(_channel_env) if _channel_env.isdigit() else None

intents = discord.Intents.default()
intents.message_content = True


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)
        self.odysseus = OdysseusClient(base_url=ODYSSEUS_URL)

    async def setup_hook(self):
        await setup_chat(self, self.odysseus, CHAT_CHANNEL_ID)
        await self.tree.sync()
        print("Slash commands synced.")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening, name="/chat or @mention"
            )
        )

    async def close(self):
        await self.odysseus.aclose()
        await super().close()


async def main():
    async with Bot() as bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
