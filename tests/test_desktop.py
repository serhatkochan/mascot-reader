import os
import subprocess
import sys
import threading
import wave

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from mascot_reader.controller import PlaybackController
from mascot_reader.window import MascotWindow, clamp_position


def write_audio(path, seconds=3):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\x00\x00" * (48000 * seconds))


class FastPreparer:
    def __init__(self):
        self.calls = 0

    def prepare(self, source, output, **kwargs):
        self.calls += 1
        write_audio(output)
        kwargs["progress"](1, 1)
        return output


@pytest.fixture
def reader(qtbot, tmp_path):
    engine = FastPreparer()
    controller = PlaybackController(preparer=engine, cache_dir=tmp_path / "audio")
    source = tmp_path / "belge.md"
    source.write_text("Merhaba dünya.", encoding="utf-8")
    controller.open_document(source)
    qtbot.waitUntil(lambda: controller.audio_path is not None, timeout=5000)
    qtbot.waitUntil(lambda: controller.player.isSeekable(), timeout=5000)
    controller.player.pause()
    yield controller, engine, source
    controller.close()


@pytest.mark.parametrize("seconds", [5, 10])
def test_seek_clamps_to_document_boundaries_and_stays_paused(reader, qtbot, seconds):
    controller, _, _ = reader
    controller.player.setPosition(1000)
    controller.seek(-seconds)
    assert controller.player.position() == 0
    assert controller.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    controller.seek(seconds)
    assert controller.player.position() == 3000
    assert controller.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState


def test_stop_rewinds_and_restart_reuses_prepared_audio(reader, qtbot):
    controller, engine, _ = reader
    controller.player.setPosition(1000)
    controller.stop()
    assert controller.player.position() == 0
    assert controller.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
    controller.restart()
    qtbot.waitUntil(
        lambda: controller.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    )
    assert engine.calls == 1


def test_export_preserves_wav_and_does_not_synthesize_again(reader, tmp_path):
    controller, engine, _ = reader
    target = tmp_path / "dinle.wav"
    controller.export_audio(target)
    assert target.read_bytes() == controller.audio_path.read_bytes()
    assert engine.calls == 1
    assert not list(tmp_path.glob("*.partial"))


def test_late_result_from_replaced_document_is_deleted(reader, tmp_path):
    controller, _, _ = reader
    active = controller.audio_path
    stale = tmp_path / "old.wav"
    write_audio(stale)
    controller._on_ready(controller.job_id - 1, str(stale))
    assert controller.audio_path == active
    assert not stale.exists()


def test_stop_cancels_preparation_and_late_result_cannot_autoplay(qtbot, tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class SlowPreparer:
        def prepare(self, source, output, **kwargs):
            entered.set()
            release.wait(timeout=5)
            write_audio(output)
            return output

    controller = PlaybackController(preparer=SlowPreparer(), cache_dir=tmp_path / "audio")
    source = tmp_path / "slow.md"
    source.write_text("Merhaba.", encoding="utf-8")
    controller.open_document(source)
    assert entered.wait(timeout=2)
    controller.stop()
    release.set()
    qtbot.waitUntil(lambda: not list((tmp_path / "audio").glob("*.wav")), timeout=3000)
    QTest.qWait(100)
    assert controller.audio_path is None
    assert controller.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
    controller.close()


def test_file_picker_cancellation_preserves_loaded_document(reader, qtbot, monkeypatch):
    controller, _, source = reader
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    old_audio = controller.audio_path
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", ""))
    window.choose_file()
    assert controller.source == source
    assert controller.audio_path == old_audio


def test_mascot_click_opens_picker_but_drag_only_moves_window(qtbot, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (calls.append(True) or "", "")
    )
    controller = PlaybackController(preparer=FastPreparer(), cache_dir=tmp_path / "audio")
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.mouseClick(window.mascot, Qt.MouseButton.LeftButton, pos=QPoint(110, 85))
    assert len(calls) == 1
    before = window.pos()
    qtbot.mousePress(window.mascot, Qt.MouseButton.LeftButton, pos=QPoint(110, 85))
    QTest.mouseMove(window.mascot, QPoint(140, 95), delay=40)
    qtbot.mouseRelease(window.mascot, Qt.MouseButton.LeftButton, pos=QPoint(140, 95))
    assert len(calls) == 1
    assert window.pos() != before
    controller.close()


@pytest.mark.parametrize(
    "point,expected",
    [(QPoint(-500, -500), QPoint(100, 100)), (QPoint(1900, 1000), QPoint(620, 460))],
)
def test_saved_position_is_clamped_inside_current_screen(point, expected):
    assert clamp_position(point, QRect(100, 100, 800, 600), QSize(280, 240)) == expected


def test_final_window_close_exits_without_a_system_tray(tmp_path):
    script = """
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from mascot_reader.controller import PlaybackController
from mascot_reader.window import MascotWindow
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
controller = PlaybackController()
window = MascotWindow(controller, persist_settings=False)
window.show()
QTimer.singleShot(20, window.close)
QTimer.singleShot(300, lambda: app.exit(99))
raise SystemExit(app.exec())
"""
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-c", script], env=environment, timeout=8, check=False
    )
    assert result.returncode == 0


def test_setting_change_reprepares_current_document_once(reader, qtbot):
    controller, engine, _ = reader
    old_audio = controller.audio_path
    controller.set_options(speed=1.5, include_code=True)
    qtbot.waitUntil(lambda: controller.audio_path is not None, timeout=3000)
    assert controller.audio_path != old_audio
    assert not old_audio.exists()
    assert engine.calls == 2
    assert controller.speed == 1.5
    assert controller.include_code is True


def test_media_error_keeps_prepared_audio_available_for_export(reader, tmp_path):
    controller, _, _ = reader
    controller._playback_error(QMediaPlayer.Error.ResourceError, "Device unavailable")
    target = tmp_path / "still-readable.wav"
    controller.export_audio(target)
    assert target.exists()
    assert controller.status == "Ses oynatılamadı"


def test_space_plays_audio_even_when_stop_button_has_focus(reader, qtbot):
    controller, _, _ = reader
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=3000)
    window.stop_button.setFocus()
    qtbot.waitUntil(window.stop_button.hasFocus, timeout=1000)
    QTest.keyClick(window.stop_button, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: controller.playing, timeout=1500)


def test_playback_verification_decodes_and_seeks_a_real_wav(tmp_path):
    audio = tmp_path / "playback.wav"
    write_audio(audio)
    result = subprocess.run(
        [sys.executable, "-m", "mascot_reader", "--verify-playback", str(audio)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        timeout=12,
        check=False,
    )
    assert result.returncode == 0
    import json

    metadata = json.loads(audio.with_suffix(".playback.json").read_text(encoding="utf-8"))
    assert metadata["seekable"] is True
    assert metadata["duration_ms"] == 3000
    assert metadata["restart"] is True
    assert metadata["stopped_at_ms"] == 0


@pytest.mark.parametrize("requested,expected", [(-1000, 0), (1500, 1500), (9000, 3000)])
def test_absolute_seek_preserves_pause_and_reuses_audio(reader, requested, expected):
    controller, engine, _ = reader
    controller.seek_to(requested)
    assert controller.player.position() == expected
    assert not controller.playing
    assert engine.calls == 1


def test_timeline_click_jumps_to_time_and_playback_updates_do_not_seek(reader, qtbot, monkeypatch):
    controller, _, _ = reader
    requests = []
    seek = controller.seek_to

    def record(position):
        requests.append(position)
        seek(position)

    monkeypatch.setattr(controller, "seek_to", record)
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    timeline = window.timeline
    assert timeline.isEnabled()
    assert timeline.maximum() == 3000
    qtbot.mouseClick(timeline, Qt.MouseButton.LeftButton,
                     pos=QPoint(timeline.width() // 2, timeline.height() // 2))
    assert 1450 <= controller.player.position() <= 1550
    assert not controller.playing
    assert len(requests) == 1
    controller.player.setPosition(700)
    assert timeline.value() == 700
    assert len(requests) == 1
    qtbot.mouseClick(timeline, Qt.MouseButton.LeftButton, pos=QPoint(0, timeline.height() // 2))
    assert controller.player.position() == 0
    qtbot.mouseClick(timeline, Qt.MouseButton.LeftButton,
                     pos=QPoint(timeline.width() - 1, timeline.height() // 2))
    assert controller.player.position() == 3000
    assert not controller.playing


def test_timeline_drag_previews_without_player_updates_moving_thumb_and_resumes(reader, qtbot):
    controller, _, _ = reader
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    controller.restart()
    qtbot.waitUntil(lambda: controller.playing, timeout=1500)
    timeline = window.timeline
    middle = QPoint(timeline.width() // 2, timeline.height() // 2)
    qtbot.mousePress(timeline, Qt.MouseButton.LeftButton, pos=middle)
    assert not controller.playing
    QTest.mouseMove(timeline, QPoint(timeline.width() - 1, middle.y()), delay=20)
    assert timeline.sliderPosition() == 3000
    QTest.mouseMove(timeline, middle, delay=20)
    preview = timeline.sliderPosition()
    controller.player.setPosition(500)
    assert timeline.sliderPosition() == preview
    assert "0:01" in window.status_label.text()
    qtbot.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=middle)
    qtbot.waitUntil(lambda: controller.playing, timeout=1500)
    assert 1450 <= controller.player.position() <= 1700


def test_new_preparation_cancels_drag_and_disables_timeline(reader, qtbot):
    controller, _, source = reader
    release = threading.Event()

    class GatedPreparer(FastPreparer):
        def prepare(self, source, output, **kwargs):
            release.wait(timeout=5)
            return super().prepare(source, output, **kwargs)

    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    timeline = window.timeline
    target = QPoint(timeline.width() * 3 // 4, timeline.height() // 2)
    qtbot.mousePress(timeline, Qt.MouseButton.LeftButton, pos=target)
    controller._preparer = GatedPreparer()
    try:
        controller.open_document(source)
        assert not timeline.isEnabled()
        assert not timeline.isSliderDown()
        assert timeline.maximum() == 0
        qtbot.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=target)
        release.set()
        qtbot.waitUntil(lambda: controller.playing, timeout=3000)
        assert controller.player.position() < 500
    finally:
        release.set()


def test_timeline_can_seek_after_stop_without_starting_audio(reader, qtbot):
    controller, _, _ = reader
    controller.stop()
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    timeline = window.timeline
    qtbot.mouseClick(timeline, Qt.MouseButton.LeftButton,
                     pos=QPoint(timeline.width() // 2, timeline.height() // 2))
    assert 1450 <= controller.player.position() <= 1550
    assert not controller.playing


def test_timeline_home_and_end_keys_seek_without_starting_audio(reader, qtbot):
    controller, _, _ = reader
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    QTest.keyClick(window.timeline, Qt.Key.Key_End)
    assert controller.player.position() == 3000
    QTest.keyClick(window.timeline, Qt.Key.Key_Home)
    assert controller.player.position() == 0
    assert not controller.playing


def test_absolute_seek_after_stop_stays_silent_and_play_starts_at_selected_time(tmp_path):
    audio = tmp_path / "stopped.wav"
    write_audio(audio, seconds=4)
    script = """
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from mascot_reader.controller import PlaybackController
app = QApplication([])
controller = PlaybackController()
controller.source = Path(sys.argv[1])
controller._on_ready(controller.job_id, sys.argv[1])
def ready():
    if not controller.playing or not controller.player.isSeekable():
        QTimer.singleShot(20, ready)
        return
    controller.stop()
    controller.seek_to(1500)
    assert not controller.playing
    assert controller.player.position() == 1500
    controller.play_pause()
    QTimer.singleShot(100, finish)
def finish():
    assert controller.playing
    assert 1500 <= controller.player.position() < 1900
    controller.close()
    app.quit()
QTimer.singleShot(20, ready)
QTimer.singleShot(5000, lambda: app.exit(99))
raise SystemExit(app.exec())
"""
    result = subprocess.run([sys.executable, "-c", script, str(audio)],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            timeout=10, check=False)
    assert result.returncode == 0
