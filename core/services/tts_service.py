import os
import tempfile

import edge_tts


class TTSService:
    def __init__(self, voice: str = "id-ID-ArdiNeural"):
        self._voice = voice

    async def synthesize(self, text: str) -> str:
        communicate = edge_tts.Communicate(text, self._voice)
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        await communicate.save(path)
        return path
