"""Prepare a complete seekable WAV while keeping model/audio memory bounded."""

import json
import math
import os
import threading
import wave
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .markdown import read_markdown_snapshot


class PreparationCancelled(Exception):
    """The caller cancelled preparation before the WAV was complete."""


def _load_cpu_model():
    import torch
    from ema_lightning import EMA

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    return EMA(device="cpu")


def _check_cancelled(cancel_event: threading.Event) -> None:
    if cancel_event.is_set():
        raise PreparationCancelled("Ses hazırlama iptal edildi.")


class AudioPreparer:
    """Keep one lazy model and serialize calls, including callers queued by the UI."""

    def __init__(self, model_factory: Callable[[], Any] | None = None):
        self._model_factory = model_factory or _load_cpu_model
        self._model = None
        self._lock = threading.Lock()

    def prepare(
        self,
        source: Path,
        output: Path,
        *,
        speed: float = 1.0,
        include_code: bool = False,
        cancel_event: threading.Event,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Write 48 kHz mono PCM16 audio to a new file, removing partial output."""
        _check_cancelled(cancel_event)
        if not math.isfinite(speed) or not 0.5 <= speed <= 2.0:
            raise ValueError("Okuma hızı 0,5 ile 2 arasında olmalı.")
        output = Path(output)
        cue_path = output.with_suffix(".cues.json")
        for target in (output, cue_path):
            if target.exists():
                raise FileExistsError(f"Ses dosyası zaten var: {target}")
        snapshot = read_markdown_snapshot(Path(source), include_code=include_code)
        segments = snapshot.segments
        while not self._lock.acquire(timeout=0.1):
            _check_cancelled(cancel_event)
        created = False
        cues_created = False
        cues = []
        try:
            _check_cancelled(cancel_event)
            if progress:
                progress(0, len(segments))
            if self._model is None:
                self._model = self._model_factory()
            _check_cancelled(cancel_event)
            with output.open("xb") as destination:
                created = True
                with wave.open(destination, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(48000)
                    frame_count = 0
                    for index, segment in enumerate(segments, 1):
                        _check_cancelled(cancel_event)
                        start_frame = frame_count
                        stream = self._model.stream(segment.text, speed=speed, sample_rate=48000)
                        try:
                            for chunk in stream:
                                _check_cancelled(cancel_event)
                                audio = np.asarray(chunk, dtype=np.float32).reshape(-1)
                                if not np.isfinite(audio).all():
                                    raise ValueError("Model geçersiz ses örnekleri üretti.")
                                pcm = np.rint(np.clip(audio, -1.0, 1.0) * 32768.0)
                                pcm = np.clip(pcm, -32768, 32767).astype("<i2")
                                wav.writeframesraw(pcm.tobytes())
                                frame_count += len(pcm)
                        finally:
                            close = getattr(stream, "close", None)
                            if close is not None:
                                close()
                        _check_cancelled(cancel_event)
                        cues.append(
                            {
                                **asdict(segment),
                                "start_frame": start_frame,
                                "end_frame": frame_count,
                            }
                        )
                        if progress:
                            progress(index, len(segments))
                    _check_cancelled(cancel_event)
                    if not frame_count:
                        raise ValueError("Model bu belge için ses üretemedi.")
            with cue_path.open("x", encoding="utf-8") as destination:
                cues_created = True
                json.dump(
                    {
                        "schema_version": 1,
                        "sample_rate": 48000,
                        "source_text": snapshot.source_text,
                        "cues": cues,
                    },
                    destination,
                    ensure_ascii=False,
                    indent=2,
                )
            _check_cancelled(cancel_event)
            return output
        except BaseException:
            if cues_created:
                cue_path.unlink(missing_ok=True)
            if created:
                output.unlink(missing_ok=True)
            raise
        finally:
            self._lock.release()
