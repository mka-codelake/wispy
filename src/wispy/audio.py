"""Microphone recording via sounddevice -> NumPy array."""

import numpy as np
import sounddevice as sd


class Recorder:
    """Records audio from the microphone into a list of chunks.

    Usage:
        rec = Recorder(sample_rate=16000)
        rec.start()
        # ... user speaks ...
        audio = rec.stop()  # np.ndarray, float32, mono
    """

    def __init__(self, sample_rate: int = 16000, device: int | None = None):
        self.sample_rate = sample_rate
        self.device = device
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"[audio] {status}")
        self._chunks.append(indata.copy())

    def start(self):
        """Open the microphone stream and begin collecting audio."""
        self._chunks.clear()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop recording and return the captured audio as a 1-D float32 array."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._chunks:
            return np.array([], dtype=np.float32)

        audio = np.concatenate(self._chunks, axis=0).flatten()
        self._chunks.clear()
        return audio
