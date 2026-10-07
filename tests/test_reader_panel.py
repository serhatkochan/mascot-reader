import json
import wave

import pytest
from PySide6.QtCore import QRect, Qt, QUrl
from PySide6.QtWidgets import QApplication

from mascot_reader.controller import PlaybackController
from mascot_reader.reading import load_audio_document, render_document_html
from mascot_reader.window import MascotWindow

SOURCE = '# Merhaba\n\nBirinci paragraf.\n\n```py\nprint("gizli")\n```\n\nSon bölüm.\n'


def write_cued_audio(path, source=SOURCE):
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b'\x00\x00' * 192000)
    payload = {
        'schema_version': 1, 'sample_rate': 48000, 'source_text': source,
        'cues': [
            {'text': 'Merhaba', 'kind': 'heading', 'line_start': 0, 'line_end': 1,
             'start_frame': 0, 'end_frame': 24000},
            {'text': 'Birinci paragraf.', 'kind': 'paragraph', 'line_start': 2, 'line_end': 3,
             'start_frame': 24000, 'end_frame': 96000},
            {'text': 'Son bölüm.', 'kind': 'paragraph', 'line_start': 8, 'line_end': 9,
             'start_frame': 96000, 'end_frame': 192000},
        ],
    }
    path.with_suffix('.cues.json').write_text(json.dumps(payload), encoding='utf-8')
    return payload


def test_cue_frames_determine_click_times_and_current_segment(tmp_path):
    audio = tmp_path / 'document.wav'
    write_cued_audio(audio)
    document = load_audio_document(audio)
    assert document.source_text == SOURCE
    assert document.cues[1].start_ms == 500
    assert document.cue_at(499) == 0
    assert document.cue_at(500) == 1
    assert document.cue_at(2000) == 2
    assert document.cue_at(4000) == 2


def test_reader_html_preserves_unspoken_code_and_marks_only_spoken_segments(tmp_path):
    audio = tmp_path / 'document.wav'
    write_cued_audio(audio)
    document = load_audio_document(audio)
    html = render_document_html(document, job_id=7)
    assert 'segment:7:1' in html
    assert 'Birinci paragraf.' in html
    assert 'print(' in html
    assert 'gizli' in html
    assert html.count('href="segment:') == 3
    assert '<h1' in html


def test_corrupted_frame_map_is_rejected(tmp_path):
    audio = tmp_path / 'document.wav'
    payload = write_cued_audio(audio)
    payload['cues'][1]['start_frame'] = 100
    audio.with_suffix('.cues.json').write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        load_audio_document(audio)


@pytest.fixture
def cued_reader(qtbot, tmp_path):
    class CuedPreparer:
        def prepare(self, source, output, **kwargs):
            write_cued_audio(output)
            kwargs['progress'](3, 3)
            return output

    controller = PlaybackController(preparer=CuedPreparer(), cache_dir=tmp_path / 'audio')
    source = tmp_path / 'README.md'
    source.write_text(SOURCE, encoding='utf-8')
    controller.open_document(source)
    qtbot.waitUntil(lambda: controller.audio_path is not None, timeout=3000)
    qtbot.waitUntil(lambda: controller.player.isSeekable(), timeout=3000)
    controller.player.pause()
    yield controller
    controller.close()


def test_filename_opens_panel_and_segment_link_seeks_without_starting_audio(cued_reader, qtbot):
    controller = cued_reader
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    assert window.reader_panel.isHidden()
    compact_width = window.width()
    window.status_label.linkActivated.emit('document')
    assert not window.reader_panel.isHidden()
    assert window.width() > compact_width
    assert 'Birinci paragraf.' in window.reader_panel.browser.toPlainText()
    window.reader_panel.browser.anchorClicked.emit(QUrl(f'segment:{controller.job_id}:1'))
    assert controller.player.position() == 500
    assert not controller.playing
    assert window.reader_panel.active_cue == 1
    window.toggle_reader()
    assert window.reader_panel.isHidden()
    assert window.width() == compact_width


def test_reader_uses_prepared_snapshot_even_if_source_file_changes(cued_reader, qtbot):
    controller = cued_reader
    controller.source.write_text('Dışarıda değişmiş içerik.', encoding='utf-8')
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    window.toggle_reader()
    assert 'Birinci paragraf.' in window.reader_panel.browser.toPlainText()
    assert 'Dışarıda değişmiş' not in window.reader_panel.browser.toPlainText()


def test_stale_document_link_does_not_seek_current_audio(cued_reader, qtbot):
    controller = cued_reader
    controller.seek_to(1000)
    window = MascotWindow(controller, persist_settings=False)
    qtbot.addWidget(window)
    window.reader_panel.browser.anchorClicked.emit(QUrl(f'segment:{controller.job_id - 1}:2'))
    assert controller.player.position() == 1000


def test_clicking_visible_markdown_text_uses_the_real_browser_link(cued_reader, qtbot):
    window = MascotWindow(cued_reader, persist_settings=False)
    qtbot.addWidget(window)
    window.show()
    window.toggle_reader()
    browser = window.reader_panel.browser
    cursor = browser.document().find('Birinci paragraf.')
    cursor.setPosition(cursor.selectionStart() + 2)
    browser.setTextCursor(cursor)
    point = browser.cursorRect(cursor).center()
    assert browser.anchorAt(point) == f'segment:{cued_reader.job_id}:1'
    qtbot.mouseClick(browser.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert cued_reader.player.position() == 500
    assert not cued_reader.playing


def test_audio_cleanup_removes_sidecar_and_late_results(cued_reader, tmp_path):
    controller = cued_reader
    stale = tmp_path / 'stale.wav'
    write_cued_audio(stale)
    controller._on_ready(controller.job_id - 1, str(stale))
    assert not stale.exists()
    assert not stale.with_suffix('.cues.json').exists()
    active = controller.audio_path
    controller.close()
    assert not active.exists()
    assert not active.with_suffix('.cues.json').exists()


@pytest.mark.parametrize('width', [600, 350])
def test_open_panel_refits_when_available_screen_shrinks(cued_reader, qtbot, monkeypatch, width):
    class Screen:
        geometry = QRect(0, 0, 800, 700)

        def availableGeometry(self):
            return self.geometry

    screen = Screen()
    window = MascotWindow(cued_reader, persist_settings=False)
    qtbot.addWidget(window)
    monkeypatch.setattr(QApplication, 'screenAt', lambda point: screen)
    window.show()
    window.toggle_reader()
    screen.geometry = QRect(0, 0, width, 500)
    window.ensure_on_screen()
    assert window.width() <= width
    assert window.frameGeometry().right() <= screen.geometry.right()
    assert window.frameGeometry().bottom() <= screen.geometry.bottom()
    assert not window.reader_panel.isHidden()
    assert window.reader_panel.browser.toPlainText()
    window.toggle_reader()
    assert window.width() == window._compact_size.width()
    assert window.frameGeometry().right() <= screen.geometry.right()
