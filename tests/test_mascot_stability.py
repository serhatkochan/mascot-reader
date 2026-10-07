import math

import numpy as np
import pytest
from PySide6.QtGui import QImage, QPixmap

from mascot_reader.mascots import load_mascots, sprite_frame
from mascot_reader.window import MascotSprite

DESK_TOPS = {'ember': 302, 'frost': 293, 'fern': 293, 'neko': 292, 'cloud': 294,
            'cosmo': 294, 'panda': 270, 'axolotl': 282, 'dragon': 265, 'raccoon': 277}


def pixels(frame):
    image = frame.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    rows = np.frombuffer(image.constBits().tobytes(), dtype=np.uint8).reshape(
        image.height(), image.bytesPerLine())
    return rows[:, :image.width() * 4].reshape(image.height(), image.width(), 4)


@pytest.mark.parametrize('mascot', load_mascots(), ids=lambda mascot: mascot.id)
def test_desk_pixels_stay_fixed_through_all_animation_frames(qapp, mascot):
    metadata = mascot.metadata()
    sheet = QPixmap(str(mascot.metadata_path.parent / metadata['image']))
    reference = pixels(sprite_frame(metadata, sheet, metadata['animations']['idle'], 0))
    desk_top = DESK_TOPS[mascot.id]
    for name, animation in metadata['animations'].items():
        for column in set(animation['frames']):
            current = pixels(sprite_frame(metadata, sheet, animation, column))
            assert np.array_equal(reference[desk_top:], current[desk_top:]), (
                f'{mascot.id}/{name}/{column}: desk pixels moved or changed')


@pytest.mark.parametrize('mascot', load_mascots(), ids=lambda mascot: mascot.id)
def test_facial_and_typing_animation_remains_live(qapp, mascot):
    metadata = mascot.metadata()
    sheet = QPixmap(str(mascot.metadata_path.parent / metadata['image']))
    for name, animation in metadata['animations'].items():
        frames = {
            pixels(sprite_frame(metadata, sheet, animation, column))[:260].tobytes()
            for column in set(animation['frames'])
        }
        assert len(frames) > 1, f'{mascot.id}/{name}: animation was frozen'


@pytest.mark.parametrize('mascot', load_mascots(), ids=lambda mascot: mascot.id)
def test_visible_desk_stays_fixed_when_animation_state_changes(qtbot, mascot):
    widget = MascotSprite(mascot=mascot)
    qtbot.addWidget(widget)
    widget.timer.stop()
    widget.setFixedWidth(250)
    widget.show()
    first = widget.grab()
    desk_top = math.ceil((DESK_TOPS[mascot.id] * 180 / 362 + 2) * first.devicePixelRatio())
    reference = pixels(first)[desk_top:]
    for name, animation in widget.metadata['animations'].items():
        widget.set_animation(name)
        for column in set(animation['frames']):
            widget.frame = animation['frames'].index(column)
            current = pixels(widget.grab())[desk_top:]
            assert np.array_equal(reference, current), (
                f'{mascot.id}/{name}/{column}: visible desk moved')
