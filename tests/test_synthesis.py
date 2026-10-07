import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from mascot_reader.synthesis import AudioPreparer, PreparationCancelled


class FakeModel:
    def __init__(self, chunks=None):
        self.chunks = chunks or [np.array([-2, -1, -0.5, 0, 0.5, 1, 2], dtype=np.float32)]

    def stream(self, text, *, speed, sample_rate):
        if sample_rate != 48000 or not 0.5 <= speed <= 2:
            raise ValueError("Invalid synthesis parameters")
        yield from self.chunks


def document(tmp_path: Path, text: str = "# Merhaba\n\nİkinci bölüm.") -> Path:
    path = tmp_path / "source.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_writes_real_mono_pcm16_wav_and_reports_segment_progress(tmp_path):
    source = document(tmp_path)
    output = tmp_path / "prepared.wav"
    progress = []
    preparer = AudioPreparer(model_factory=FakeModel)
    assert (
        preparer.prepare(
            source,
            output,
            cancel_event=threading.Event(),
            progress=lambda done, total: progress.append((done, total)),
        )
        == output
    )
    with wave.open(str(output), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 48000
        assert wav.getnframes() == 14
        assert np.frombuffer(wav.readframes(14), dtype="<i2").tolist() == [
            -32768,
            -32768,
            -16384,
            0,
            16384,
            32767,
            32767,
            -32768,
            -32768,
            -16384,
            0,
            16384,
            32767,
            32767,
        ]
    assert progress == [(0, 2), (1, 2), (2, 2)]


def test_cancellation_before_start_does_not_load_model_or_create_output(tmp_path):
    cancel = threading.Event()
    cancel.set()

    def forbidden_factory():
        pytest.fail("Cancelled work loaded the model")

    output = tmp_path / "cancelled.wav"
    with pytest.raises(PreparationCancelled):
        AudioPreparer(forbidden_factory).prepare(document(tmp_path), output, cancel_event=cancel)
    assert not output.exists()


def test_midstream_cancellation_closes_iterator_and_removes_partial_wav(tmp_path):
    cancel = threading.Event()
    closed = threading.Event()

    class CancellingModel:
        def stream(self, text, *, speed, sample_rate):
            try:
                yield np.ones(8, dtype=np.float32)
                cancel.set()
                yield np.ones(8, dtype=np.float32)
            finally:
                closed.set()

    output = tmp_path / "partial.wav"
    with pytest.raises(PreparationCancelled):
        AudioPreparer(CancellingModel).prepare(document(tmp_path), output, cancel_event=cancel)
    assert closed.is_set()
    assert not output.exists()


def test_synthesis_failure_removes_partial_wav(tmp_path):
    class BrokenModel:
        def stream(self, text, *, speed, sample_rate):
            yield np.ones(8, dtype=np.float32)
            raise RuntimeError("Model failed")

    output = tmp_path / "failed.wav"
    with pytest.raises(RuntimeError, match="Model failed"):
        AudioPreparer(BrokenModel).prepare(
            document(tmp_path), output, cancel_event=threading.Event()
        )
    assert not output.exists()


def test_rejects_empty_audio_output(tmp_path):
    class EmptyModel:
        def stream(self, text, *, speed, sample_rate):
            return iter(())

    output = tmp_path / "empty.wav"
    with pytest.raises(ValueError):
        AudioPreparer(EmptyModel).prepare(
            document(tmp_path), output, cancel_event=threading.Event()
        )
    assert not output.exists()


def test_rejects_non_finite_audio_and_removes_output(tmp_path):
    output = tmp_path / "nan.wav"
    with pytest.raises(ValueError):
        AudioPreparer(lambda: FakeModel([np.array([np.nan], dtype=np.float32)])).prepare(
            document(tmp_path), output, cancel_event=threading.Event()
        )
    assert not output.exists()


def test_reuses_one_model_across_documents(tmp_path):
    class SingleLoadModel(FakeModel):
        loaded = False

        def __init__(self):
            if self.loaded:
                pytest.fail("Model was loaded more than once")
            SingleLoadModel.loaded = True
            super().__init__()

    preparer = AudioPreparer(SingleLoadModel)
    source = document(tmp_path, "Merhaba.")
    preparer.prepare(source, tmp_path / "first.wav", cancel_event=threading.Event())
    preparer.prepare(source, tmp_path / "second.wav", cancel_event=threading.Event())
    assert (tmp_path / "first.wav").read_bytes() == (tmp_path / "second.wav").read_bytes()


def test_does_not_overwrite_existing_output(tmp_path):
    output = tmp_path / "existing.wav"
    output.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        AudioPreparer(FakeModel).prepare(document(tmp_path), output, cancel_event=threading.Event())
    assert output.read_bytes() == b"keep me"


@pytest.mark.parametrize("speed", [0, 0.49, 2.01, float("nan"), float("inf")])
def test_rejects_speed_outside_ui_range(tmp_path, speed):
    output = tmp_path / "invalid.wav"
    with pytest.raises(ValueError):
        AudioPreparer(FakeModel).prepare(
            document(tmp_path), output, speed=speed, cancel_event=threading.Event()
        )
    assert not output.exists()


def test_cancelled_queued_preparation_can_leave_lock_without_waiting_for_model(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class WaitingModel:
        def stream(self, text, *, speed, sample_rate):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test model timed out")
            yield np.ones(8, dtype=np.float32)

    source = document(tmp_path, "Merhaba.")
    preparer = AudioPreparer(WaitingModel)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            preparer.prepare, source, tmp_path / "first.wav", cancel_event=threading.Event()
        )
        assert entered.wait(2)
        cancel = threading.Event()
        queued = pool.submit(preparer.prepare, source, tmp_path / "second.wav", cancel_event=cancel)
        cancel.set()
        try:
            with pytest.raises(PreparationCancelled):
                queued.result(timeout=2)
        finally:
            release.set()
        assert first.result(timeout=2).exists()
    assert not (tmp_path / "second.wav").exists()


def test_default_factory_caps_cpu_threads_and_requests_cpu_model(tmp_path, monkeypatch):
    import os
    import sys
    from types import SimpleNamespace

    import torch

    class CpuModel(FakeModel):
        def __init__(self, *, device):
            if device != "cpu":
                raise ValueError("Reader must use the CPU")
            super().__init__()

    monkeypatch.setitem(sys.modules, "ema_lightning", SimpleNamespace(EMA=CpuModel))
    original_threads = torch.get_num_threads()
    torch.set_num_threads(8)
    try:
        output = tmp_path / "cpu.wav"
        AudioPreparer().prepare(
            document(tmp_path, "Merhaba."), output, cancel_event=threading.Event()
        )
        assert torch.get_num_threads() == min(4, os.cpu_count() or 1)
        with wave.open(str(output), "rb") as wav:
            assert wav.getnframes() == 7
    finally:
        torch.set_num_threads(original_threads)
