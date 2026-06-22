import asyncio

import numpy as np
from faster_whisper import WhisperModel


class WhisperService:
    def __init__(self, model_size: str = "base", language: str | None = None):
        self._language = language
        # device="auto" picks CUDA if available, else CPU
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    async def transcribe(self, pcm_bytes: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_transcribe, pcm_bytes)

    def _sync_transcribe(self, pcm_bytes: bytes) -> str:
        audio = _pcm_to_float(pcm_bytes)
        segments, _ = self._model.transcribe(
            audio, language=self._language, beam_size=1
        )
        return "".join(seg.text for seg in segments).strip()


def _pcm_to_float(pcm_bytes: bytes) -> np.ndarray:
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    # Discord sends stereo 48 kHz — convert to mono 16 kHz for Whisper
    if audio.size >= 2:
        audio = audio.reshape(-1, 2).mean(axis=1)
    return audio[::3]  # 48 kHz → 16 kHz
