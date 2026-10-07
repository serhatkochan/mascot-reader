import os
import shutil
import tempfile
import threading
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from .reading import load_audio_document
from .synthesis import AudioPreparer, PreparationCancelled


class PlaybackController(QObject):
    changed = Signal()
    message = Signal(str)
    _progress = Signal(int, int, int)
    _ready = Signal(int, str)
    _failed = Signal(int, str)
    _cancelled = Signal(int)

    def __init__(self, preparer=None, cache_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)
        self.source: Path | None = None
        self.audio_path: Path | None = None
        self.audio_document = None
        self.speed = 1.0
        self.include_code = False
        self.seek_seconds = 10
        self.preparing = False
        self.progress = 0
        self.status = "Markdown seçmek için maskota tıkla"
        self.job_id = 0
        self._closed = False
        self._preparer = preparer or AudioPreparer()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="speech")
        self._cancel_event = threading.Event()
        self._future = None
        self._temporary = tempfile.TemporaryDirectory(prefix="mascot-reader-")
        self._cache_dir = Path(cache_dir) if cache_dir else Path(self._temporary.name)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._progress.connect(self._on_progress)
        self._ready.connect(self._on_ready)
        self._failed.connect(self._on_failed)
        self._cancelled.connect(self._on_cancelled)
        self.player.positionChanged.connect(self.changed)
        self.player.durationChanged.connect(self.changed)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.errorOccurred.connect(self._playback_error)

    @property
    def playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _cancel_pending(self):
        self._cancel_event.set()
        if self._future is not None:
            self._future.cancel()

    def _release_audio(self):
        self.audio_document = None
        self.player.stop()
        self.player.setSource(QUrl())
        if self.audio_path:
            self._remove_audio(self.audio_path)
        self.audio_path = None

    @staticmethod
    def _remove_audio(path: Path):
        for target in (path, path.with_suffix('.cues.json')):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass

    def open_document(self, path: Path):
        if self._closed:
            return
        self._cancel_pending()
        self.job_id += 1
        job = self.job_id
        self._release_audio()
        self.source = Path(path)
        self.preparing = True
        self.progress = 0
        self.status = "Ses hazırlanıyor…"
        self._cancel_event = threading.Event()
        output = self._cache_dir / f"{uuid.uuid4().hex}.wav"
        self._future = self._executor.submit(
            self._prepare, job, self.source, output, self._cancel_event,
            self.speed, self.include_code,
        )
        self.changed.emit()

    def _prepare(self, job, source, output, cancel_event, speed, include_code):
        try:
            path = self._preparer.prepare(
                source, output, speed=speed, include_code=include_code,
                cancel_event=cancel_event,
                progress=lambda done, total: self._progress.emit(job, done, total),
            )
            if cancel_event.is_set() or self._closed:
                self._remove_audio(Path(path))
                self._cancelled.emit(job)
            else:
                self._ready.emit(job, str(path))
        except PreparationCancelled:
            self._cancelled.emit(job)
        except Exception as error:  # noqa: BLE001 -- Report third-party model failures at the UI boundary.
            self._failed.emit(job, str(error))

    @Slot(int, int, int)
    def _on_progress(self, job, done, total):
        if job == self.job_id and self.preparing:
            self.progress = int(done * 100 / max(total, 1))
            self.status = f"Ses hazırlanıyor · %{self.progress}"
            self.changed.emit()

    @Slot(int, str)
    def _on_ready(self, job, path):
        if job != self.job_id or self._closed:
            self._remove_audio(Path(path))
            return
        self.audio_path = Path(path)
        try:
            self.audio_document = load_audio_document(self.audio_path)
        except (OSError, ValueError, KeyError, TypeError, wave.Error) as error:
            self.audio_document = None
            self.message.emit(f'Metnin ses bölüm bilgileri açılamadı: {error}')
        self.preparing = False
        self.status = "Ses açılıyor…"
        self.player.setSource(QUrl.fromLocalFile(str(self.audio_path.resolve())))
        self.player.play()
        self.changed.emit()

    @Slot(int, str)
    def _on_failed(self, job, text):
        if job != self.job_id or self._closed:
            return
        self.preparing = False
        self.status = "Ses hazırlanamadı"
        self.changed.emit()
        self.message.emit(f"Ses hazırlanamadı: {text}")

    @Slot(int)
    def _on_cancelled(self, job):
        if job == self.job_id and not self._closed:
            self.preparing = False
            self.status = "Hazırlama iptal edildi"
            self.changed.emit()

    def _playback_changed(self, state):
        if self.audio_path is not None and not self.preparing:
            self.status = {
                QMediaPlayer.PlaybackState.PlayingState: "Okunuyor",
                QMediaPlayer.PlaybackState.PausedState: "Duraklatıldı",
                QMediaPlayer.PlaybackState.StoppedState: "Hazır",
            }[state]
        self.changed.emit()

    def _media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.status = "Okuma tamamlandı"
        self.changed.emit()

    def _playback_error(self, error, text):
        if error != QMediaPlayer.Error.NoError:
            self.status = "Ses oynatılamadı"
            self.message.emit(f"Ses oynatılamadı. Ses aygıtını kontrol et. {text}")
            self.changed.emit()

    def play_pause(self):
        if self.audio_path is None or self.preparing:
            return
        if self.playing:
            self.player.pause()
        else:
            if self.player.position() >= self.player.duration():
                self.player.setPosition(0)
            self.player.play()

    def stop(self):
        if self.preparing:
            self._cancel_pending()
            self.job_id += 1
            self.preparing = False
            self.status = "Hazırlama iptal edildi"
        else:
            self.player.stop()
            self.player.setPosition(0)
            self.status = "Durduruldu" if self.audio_path else self.status
        self.changed.emit()

    def restart(self):
        if self.audio_path and not self.preparing:
            self.player.setPosition(0)
            self.player.play()

    def seek(self, seconds: int):
        self.seek_to(self.player.position() + seconds * 1000)

    def seek_to(self, milliseconds: int):
        if self.audio_path is None or not self.player.isSeekable() or self.preparing:
            return
        was_playing = self.playing
        position = min(max(0, int(milliseconds)), self.player.duration())
        self.player.setPosition(position)
        if not was_playing and self.playing:
            self.player.pause()

    def set_options(self, *, speed: float | None = None, include_code: bool | None = None):
        changed = False
        if speed is not None and speed != self.speed:
            if not 0.5 <= speed <= 2.0:
                raise ValueError("Okuma hızı 0,5 ile 2 arasında olmalı.")
            self.speed = speed
            changed = True
        if include_code is not None and include_code != self.include_code:
            self.include_code = include_code
            changed = True
        if changed and self.source:
            self.open_document(self.source)

    def seek_segment(self, job_id: int, index: int):
        if (job_id != self.job_id or self.preparing or self.audio_document is None
                or not 0 <= index < len(self.audio_document.cues)):
            return
        self.seek_to(self.audio_document.cues[index].start_ms)

    def export_audio(self, path: Path):
        if self.audio_path is None or self.preparing:
            raise ValueError("Önce bir Markdown dosyasının sesini hazırla.")
        path = Path(path)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as target, self.audio_path.open("rb") as source:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_pending()
        self.job_id += 1
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._release_audio()
        self._temporary.cleanup()

