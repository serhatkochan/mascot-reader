"""Exercise the frozen app's actual decoder and transport without a persistent window."""

import json
import shutil
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QTimer

from .controller import PlaybackController
from .mascots import load_mascots
from .window import MascotWindow


def verify_playback(app, source: Path) -> int:
    controller = PlaybackController()
    source = source.resolve()
    result_path = source.with_suffix(".playback.json")
    result = {"frozen": getattr(sys, "frozen", False)}
    controller.source = source
    copied = controller._cache_dir / f"{uuid.uuid4().hex}.wav"
    shutil.copyfile(source, copied)
    if source.with_suffix('.cues.json').exists():
        shutil.copyfile(source.with_suffix('.cues.json'), copied.with_suffix('.cues.json'))
    controller._on_ready(controller.job_id, str(copied))
    window = MascotWindow(controller, persist_settings=False)
    mascots = load_mascots()
    result['mascots'] = len(mascots)
    for mascot in mascots:
        window.select_mascot(mascot.id)
        if window.mascot.sheet.isNull() or window.mascot.current_frame().isNull():
            raise RuntimeError(f'Missing frozen mascot sprite: {mascot.id}')
    finished = False

    def finish(code, error=None):
        nonlocal finished
        if finished:
            return
        finished = True
        deadline.stop()
        if error:
            result["error"] = str(error)
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        controller.close()
        app.exit(code)

    def after_restart():
        try:
            if not controller.playing:
                raise RuntimeError("Restart did not start playback")
            result["restart"] = True
            controller.stop()
            result["stopped_at_ms"] = controller.player.position()
            if result["stopped_at_ms"] != 0:
                raise RuntimeError("Stop did not rewind")
            finish(0)
        except Exception as error:  # noqa: BLE001 -- Persist a diagnostic for any decoder failure.
            finish(2, error)

    def check_ready():
        if not controller.playing or not controller.player.isSeekable():
            QTimer.singleShot(50, check_ready)
            return
        try:
            result["seekable"] = True
            result["duration_ms"] = controller.player.duration()
            controller.player.pause()
            overshoot = controller.player.duration() // 1000 + 1
            controller.seek(overshoot)
            if controller.player.position() != controller.player.duration() or controller.playing:
                raise RuntimeError("Paused forward seek did not clamp at the end")
            controller.seek(-overshoot)
            if controller.player.position() != 0 or controller.playing:
                raise RuntimeError("Paused backward seek did not clamp at zero")
            document = controller.audio_document
            result['cue_count'] = len(document.cues) if document else 0
            if document:
                window.toggle_reader()
                result['linked_cues'] = len(window.reader_panel._cue_ranges)
                if result['linked_cues'] != len(document.cues):
                    raise RuntimeError('The frozen reader did not link all spoken segments')
                index = min(1, len(document.cues) - 1)
                controller.seek_segment(controller.job_id, index)
                if (controller.player.position() != document.cues[index].start_ms
                        or controller.playing or window.reader_panel.active_cue != index):
                    raise RuntimeError('The frozen text link did not preserve paused segment seeking')
                result['segment_seek'] = True
                result['segment_seek_ms'] = controller.player.position()
            controller.restart()
            QTimer.singleShot(100, after_restart)
        except Exception as error:  # noqa: BLE001 -- Persist a diagnostic for any decoder failure.
            finish(2, error)

    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(lambda: finish(2, "Playback verification timed out"))
    deadline.start(8000)
    QTimer.singleShot(50, check_ready)
    return app.exec()
