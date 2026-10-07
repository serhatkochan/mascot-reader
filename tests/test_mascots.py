import wave

import numpy as np
import pytest
from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QDialog, QSystemTrayIcon

from mascot_reader import window as window_module
from mascot_reader.controller import PlaybackController
from mascot_reader.mascots import MascotChooser, load_mascots, mascot_icon, sprite_frame
from mascot_reader.window import MascotWindow


def alpha_values(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = np.frombuffer(image.constBits().tobytes(), dtype=np.uint8)
    rows = pixels.reshape(image.height(), image.bytesPerLine())
    return rows[:, 3 : image.width() * 4 : 4]


def test_catalog_offers_ten_distinct_renderable_characters(qapp):
    mascots = load_mascots()
    assert len(mascots) == 10
    assert len({mascot.id for mascot in mascots}) == 10
    assert len({mascot.name for mascot in mascots}) == 10
    previews = set()
    for mascot in mascots:
        assert mascot.id and mascot.name
        icon = mascot_icon(mascot)
        assert not icon.isNull()
        image = icon.pixmap(QSize(110, 110)).toImage()
        previews.add(image.constBits().tobytes())
    assert len(previews) == 10


@pytest.mark.parametrize("mascot", load_mascots(), ids=lambda mascot: mascot.id)
@pytest.mark.parametrize("animation_name", ["idle", "preparing", "speaking"])
def test_animation_frames_are_in_bounds_visible_and_transparent(qapp, mascot, animation_name):
    metadata = mascot.metadata()
    sheet = QPixmap(str(mascot.metadata_path.parent / metadata["image"]))
    assert not sheet.isNull()
    assert sheet.size() == QSize(metadata["width"], metadata["height"])
    animation = metadata["animations"][animation_name]
    assert animation["frames"]
    assert animation["frame_ms"] > 0
    width, height = metadata["cell_width"], metadata["cell_height"]
    source_y = animation.get("source_y", animation["row"] * height)
    source_height = animation.get("source_height", height)
    destination_y = animation.get("destination_y", 0)
    assert 0 <= source_y < source_y + source_height <= sheet.height()
    assert 0 <= destination_y < destination_y + source_height <= height
    for column in set(animation["frames"]):
        assert 0 <= column * width < (column + 1) * width <= sheet.width()
        frame = sprite_frame(metadata, sheet, animation, column)
        assert frame.size() == QSize(width, height)
        assert frame.hasAlphaChannel()
        alpha = alpha_values(frame)
        assert np.any(alpha > 0), f"{mascot.id}/{animation_name}/{column} is empty"
        assert np.any(alpha == 0), f"{mascot.id}/{animation_name}/{column} lost transparency"
        if 'stationary_desk_y' in metadata:
            dy = animation['frame_offsets'][column][1]
            reference = metadata['animations']['idle']
            reference_start = reference.get('destination_y', 0)
            top = max(0, min(destination_y + dy, reference_start))
            bottom = reference_start + reference.get('source_height', height)
        else:
            top, bottom = destination_y, destination_y + source_height
        assert not alpha[:top].any()
        assert not alpha[bottom:].any()


def test_chooser_emits_clicked_character_and_closes(qtbot):
    mascots = load_mascots()
    chooser = MascotChooser(mascots, mascots[0].id)
    qtbot.addWidget(chooser)
    chooser.show()
    assert chooser.buttons[mascots[0].id].isChecked()
    assert len(chooser.buttons) == 10
    selected = mascots[-1].id
    with qtbot.waitSignal(chooser.mascot_selected, timeout=1000) as signal:
        qtbot.mouseClick(chooser.buttons[selected], Qt.MouseButton.LeftButton)
    assert signal.args == [selected]
    assert chooser.result() == QDialog.DialogCode.Accepted
    assert not chooser.isVisible()


@pytest.fixture
def isolated_settings(monkeypatch, tmp_path):
    path = tmp_path / "mascot-settings.ini"
    monkeypatch.setattr(
        window_module,
        "QSettings",
        lambda *args: QSettings(str(path), QSettings.Format.IniFormat),
    )
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    return path


@pytest.fixture
def prepared_reader(qtbot, tmp_path):
    class Preparer:
        calls = 0

        def prepare(self, source, output, **kwargs):
            self.calls += 1
            with wave.open(str(output), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(b"\x00\x00" * 48000 * 10)
            kwargs["progress"](1, 1)
            return output

    preparer = Preparer()
    controller = PlaybackController(preparer=preparer, cache_dir=tmp_path / "audio")
    source = tmp_path / "document.md"
    source.write_text("Maskot değişirken bu ses korunmalı.", encoding="utf-8")
    controller.open_document(source)
    qtbot.waitUntil(lambda: controller.audio_path is not None, timeout=3000)
    qtbot.waitUntil(controller.player.isSeekable, timeout=3000)
    controller.player.pause()
    controller.seek_to(1200)
    yield controller, preparer
    controller.close()


@pytest.mark.parametrize("playing", [True, False], ids=["playing", "paused"])
def test_changing_character_preserves_prepared_audio_and_playback(
    prepared_reader, qtbot, isolated_settings, playing
):
    controller, preparer = prepared_reader
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    if playing:
        controller.play_pause()
        qtbot.waitUntil(lambda: controller.playing, timeout=1500)
    audio_path, job_id = controller.audio_path, controller.job_id
    media_source = controller.player.source()
    audio_bytes = audio_path.read_bytes()
    previous_frame = window.mascot.current_frame().toImage()
    for mascot in window.mascots[1:]:
        window.select_mascot(mascot.id)
        assert window.mascot.metadata["image"] == f"{mascot.id}.png"
        assert window.mascot.current_frame().toImage() != previous_frame
        assert controller.audio_path == audio_path
        assert controller.job_id == job_id
        assert controller.player.source() == media_source
        expected_state = (
            QMediaPlayer.PlaybackState.PlayingState
            if playing else QMediaPlayer.PlaybackState.PausedState
        )
        assert controller.player.playbackState() == expected_state
        if playing:
            assert controller.player.position() >= 1200
        else:
            assert controller.player.position() == 1200
        assert window.mascot.animation == ("speaking" if playing else "idle")
        previous_frame = window.mascot.current_frame().toImage()
    assert preparer.calls == 1
    assert audio_path.read_bytes() == audio_bytes


def test_selected_character_is_restored_from_isolated_settings(
    qtbot, tmp_path, isolated_settings
):
    first_controller = PlaybackController(cache_dir=tmp_path / "first-audio")
    second_controller = PlaybackController(cache_dir=tmp_path / "second-audio")
    try:
        first = MascotWindow(first_controller, persist_settings=True)
        qtbot.addWidget(first)
        first.select_mascot("frost")
        first.settings.sync()
        saved = QSettings(str(isolated_settings), QSettings.Format.IniFormat)
        assert saved.value("mascot", type=str) == "frost"
        second = MascotWindow(second_controller, persist_settings=True)
        qtbot.addWidget(second)
        assert second.mascot.metadata["image"] == "frost.png"
        assert second.mascot.current_frame().toImage() == first.mascot.current_frame().toImage()
    finally:
        first_controller.close()
        second_controller.close()
