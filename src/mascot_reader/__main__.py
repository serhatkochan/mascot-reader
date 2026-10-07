import argparse
import json
import shutil
import socket
import sys
import threading
import wave
from pathlib import Path

from . import __version__
from .paths import configure_runtime


def main():
    parser = argparse.ArgumentParser(description="Maskotlu Markdown Okuyucu")
    parser.add_argument("--version-file", metavar="JSON", type=Path)
    parser.add_argument("--smoke-test", metavar="WAV", type=Path)
    parser.add_argument("--screenshot", metavar="PNG", type=Path)
    parser.add_argument("--screenshot-gallery", metavar="PNG", type=Path)
    parser.add_argument("--preview-audio", metavar="WAV", type=Path)
    parser.add_argument("--verify-playback", metavar="WAV", type=Path)
    options = parser.parse_args()
    if options.version_file:
        options.version_file.parent.mkdir(parents=True, exist_ok=True)
        options.version_file.write_text(json.dumps({
            'version': __version__, 'frozen': getattr(sys, 'frozen', False),
        }), encoding='utf-8')
        return 0
    if options.preview_audio and not options.screenshot:
        parser.error('--preview-audio requires --screenshot')
    configure_runtime()
    if options.smoke_test:
        import tempfile

        from .synthesis import AudioPreparer

        def deny_connection(*args, **kwargs):
            raise OSError("Offline verification: network access prohibited")

        socket.socket.connect = deny_connection
        output = options.smoke_test.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mascot-smoke-") as directory:
            source = Path(directory) / "test.md"
            source.write_text("# Merhaba\nMarkdown dosyanızı okumaya hazırım.", encoding="utf-8")
            AudioPreparer().prepare(source, output, cancel_event=threading.Event())
        with wave.open(str(output)) as audio:
            result = {"sample_rate": audio.getframerate(), "channels": audio.getnchannels(),
                      "sample_width": audio.getsampwidth(), "frames": audio.getnframes(),
                      "offline": True, "frozen": getattr(sys, "frozen", False)}
        output.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .controller import PlaybackController
    from .window import MascotWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("MascotReader")
    app.setQuitOnLastWindowClosed(False)
    if options.verify_playback:
        from .verification import verify_playback

        return verify_playback(app, options.verify_playback)
    if options.screenshot_gallery:
        from .mascots import MascotChooser, load_mascots

        gallery = MascotChooser(load_mascots(), 'ember')
        gallery.show()
        options.screenshot_gallery.parent.mkdir(parents=True, exist_ok=True)

        def capture_gallery():
            saved = gallery.grab().save(str(options.screenshot_gallery))
            app.exit(0 if saved else 2)

        QTimer.singleShot(500, capture_gallery)
        return app.exec()
    if not options.screenshot:
        from .windows_lifecycle import hold_installation_mutex

        hold_installation_mutex()
    controller = PlaybackController()
    window = MascotWindow(controller, persist_settings=not bool(options.screenshot))
    window.show()
    app.aboutToQuit.connect(controller.close)
    if options.screenshot:
        options.screenshot.parent.mkdir(parents=True, exist_ok=True)

        def capture():
            saved = window.grab().save(str(options.screenshot))
            app.exit(0 if saved else 2)

        if options.preview_audio:
            source = options.preview_audio.resolve()
            copied = controller._cache_dir / 'preview.wav'
            shutil.copyfile(source, copied)
            shutil.copyfile(source.with_suffix('.cues.json'), copied.with_suffix('.cues.json'))
            controller.source = Path('README.md')
            controller._on_ready(controller.job_id, str(copied))
            deadline = QTimer()
            deadline.setSingleShot(True)
            deadline.timeout.connect(lambda: app.exit(2))
            deadline.start(8000)

            def show_document():
                if not controller.player.isSeekable():
                    QTimer.singleShot(50, show_document)
                    return
                deadline.stop()
                controller.player.pause()
                if controller.audio_document and len(controller.audio_document.cues) > 1:
                    controller.seek_segment(controller.job_id, 1)
                window.toggle_reader()
                QTimer.singleShot(500, capture)

            QTimer.singleShot(50, show_document)
        else:
            QTimer.singleShot(800, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
