import asyncio
import glob
import os
import shutil

import discord

# Ensure FFmpeg is on PATH (winget installs it but VS Code terminals miss the update)
if not shutil.which("ffmpeg"):
    for _d in glob.glob(
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\bin"),
        recursive=True,
    ):
        if os.path.isdir(_d):
            os.environ["PATH"] = _d + ";" + os.environ["PATH"]
            break
from discord.ext import commands
from dotenv import load_dotenv

from cogs.chat import setup as setup_chat
from cogs.voice import setup as setup_voice
from core.services.ollama_service import OllamaService
from core.services.whisper_service import WhisperService
from core.services.tts_service import TTSService

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
os.environ["TAVILY_API_KEY"]  # fail fast if missing
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "vegard:latest")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
_channel_env = os.getenv("CHAT_CHANNEL_ID", "")
CHAT_CHANNEL_ID: int | None = int(_channel_env) if _channel_env.isdigit() else None
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
TTS_VOICE = os.getenv("TTS_VOICE", "id-ID-ArdiNeural")

intents = discord.Intents.default()
intents.message_content = True


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)
        self.ai = OllamaService(model=OLLAMA_MODEL)
        self.whisper = WhisperService(model_size=WHISPER_MODEL)
        self.tts = TTSService(voice=TTS_VOICE)

    async def close(self):
        for vc in self.voice_clients:
            await vc.disconnect(force=True)
        await super().close()

    async def setup_hook(self):
        await setup_chat(self, self.ai, CHAT_CHANNEL_ID)
        await setup_voice(self, self.ai, self.whisper, self.tts)
        await self.tree.sync()
        print("Slash commands synced.")

    async def on_ready(self):
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Slash commands synced to {guild.name}.")
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening, name="/chat or @mention"
            )
        )


async def main():
    async with Bot() as bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
