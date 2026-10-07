import json
from html import escape
from pathlib import Path

from PySide6.QtCore import (
    QPoint,
    QRect,
    QRectF,
    QSettings,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QActionGroup,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractSlider,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .mascots import MascotChooser, load_mascots, sprite_frame
from .paths import resource_dir
from .reader_panel import ReaderPanel


def clamp_position(point: QPoint, available: QRect, size: QSize) -> QPoint:
    right = max(available.left(), available.right() - size.width() + 1)
    bottom = max(available.top(), available.bottom() - size.height() + 1)
    return QPoint(
        min(max(point.x(), available.left()), right),
        min(max(point.y(), available.top()), bottom),
    )


def clock_time(milliseconds):
    seconds = max(0, milliseconds // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def transport_icon(kind, color="#f6e8d0"):
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(QColor(color))
    if kind == "play":
        from PySide6.QtCore import QPointF
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(9, 5), QPointF(9, 19), QPointF(20, 12)]))
    elif kind == "pause":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(7, 5, 4, 14), 1, 1)
        painter.drawRoundedRect(QRectF(14, 5, 4, 14), 1, 1)
    elif kind == "stop":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(5, 5, 14, 14), 40 * 16, -290 * 16)
        painter.drawLine(5, 4, 5, 10)
        painter.drawLine(5, 10, 11, 10)
    painter.end()
    return QIcon(pixmap)


class SeekSlider(QSlider):
    scrub_started = Signal()
    seek_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setTracking(False)
        self.setSingleStep(1000)
        self.setPageStep(10000)
        self._scrubbing = False
        self.actionTriggered.connect(self._keyboard_seek)

    def _keyboard_seek(self, action):
        if action not in (QAbstractSlider.SliderAction.SliderNoAction.value,
                          QAbstractSlider.SliderAction.SliderMove.value):
            self.seek_requested.emit(self.sliderPosition())

    def _position_at(self, x):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        start = groove.left() + handle.width() / 2
        span = max(1, groove.width() - handle.width())
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), round(x - start), span, option.upsideDown)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._scrubbing = True
            self.setSliderDown(True)
            self.scrub_started.emit()
            self.setSliderPosition(self._position_at(event.position().x()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._scrubbing and event.buttons() & Qt.MouseButton.LeftButton:
            self.setSliderPosition(self._position_at(event.position().x()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._scrubbing:
            position = self._position_at(event.position().x())
            self.setSliderPosition(position)
            self._scrubbing = False
            self.setSliderDown(False)
            self.setValue(position)
            self.seek_requested.emit(position)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def cancel_scrub(self):
        self._scrubbing = False
        self.setSliderDown(False)


class MascotSprite(QWidget):
    clicked = Signal()
    moved = Signal()

    def __init__(self, parent=None, mascot=None):
        super().__init__(parent)
        self.setFixedHeight(182)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Markdown açmak için tıkla · Taşımak için sürükle · Sağ tık: menü")
        self.setAccessibleName("Markdown dosyası seç")
        metadata_path = mascot.metadata_path if mascot else resource_dir() / 'mascot.json'
        self.metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        self.sheet = QPixmap(str(metadata_path.parent / self.metadata['image']))
        self.animation = "idle"
        self.frame = 0
        self._press = None
        self._dragged = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.timer.start(self.metadata["animations"]["idle"]["frame_ms"])

    def set_animation(self, name):
        if name != self.animation:
            self.animation = name
            self.frame = 0
            self.timer.setInterval(self.metadata["animations"][name]["frame_ms"])
            self.update()

    def set_mascot(self, mascot):
        self.metadata = mascot.metadata()
        self.sheet = QPixmap(str(mascot.metadata_path.parent / self.metadata['image']))
        self.frame = 0
        self.timer.setInterval(self.metadata['animations'][self.animation]['frame_ms'])
        self.update()

    def _advance(self):
        frames = self.metadata["animations"][self.animation]["frames"]
        self.frame = (self.frame + 1) % len(frames)
        self.update()

    def current_frame(self):
        animation = self.metadata["animations"][self.animation]
        column = animation["frames"][self.frame]
        return sprite_frame(self.metadata, self.sheet, animation, column)

    def paintEvent(self, event):
        animation = self.metadata["animations"][self.animation]
        side = 180
        offset = animation["baseline_offset_y"] * side / self.metadata["cell_height"]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawPixmap(QRectF((self.width() - side) / 2, offset, side, side),
                           self.current_frame(), QRectF(0, 0, self.metadata["cell_width"],
                                                       self.metadata["cell_height"]))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._start = self.window().pos()
            self._dragged = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._press
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.window().move(self._start + delta)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press is not None:
            self._press = None
            if self._dragged:
                self.moved.emit()
            else:
                self.clicked.emit()
            event.accept()


class MascotWindow(QWidget):
    def __init__(self, controller, *, persist_settings=True):
        super().__init__()
        self.controller = controller
        self._persist = persist_settings
        self.settings = QSettings("Cano", "MascotReader")
        self._exiting = False
        self._always_on_top = True
        self._resume_after_scrub = False
        self.mascots = load_mascots()
        self._selected_mascot_id = 'ember'
        self._panel_shift = QPoint()
        if persist_settings:
            self._always_on_top = self.settings.value("always_on_top", True, type=bool)
            self.controller.speed = self.settings.value("speed", 1.0, type=float)
            self.controller.include_code = self.settings.value("include_code", False, type=bool)
            self.controller.seek_seconds = self.settings.value("seek_seconds", 10, type=int)
            self._selected_mascot_id = self.settings.value('mascot', 'ember', type=str)
        selected = next((mascot for mascot in self.mascots if mascot.id == self._selected_mascot_id), self.mascots[0])
        self._selected_mascot_id = selected.id
        self.setWindowTitle("Maskotlu Markdown Okuyucu")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            (Qt.WindowType.WindowStaysOnTopHint if self._always_on_top else Qt.WindowType.Widget))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(274)
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(10)
        self.mascot_column = QWidget()
        layout = QVBoxLayout(self.mascot_column)
        layout.setContentsMargins(6, 0, 6, 5)
        layout.setSpacing(0)
        self.mascot = MascotSprite(self.mascot_column, mascot=selected)
        self.mascot.clicked.connect(self.choose_file)
        self.mascot.moved.connect(self.save_position)
        layout.addWidget(self.mascot)
        self.bar = QFrame()
        self.bar.setObjectName("controlBar")
        self.bar.setStyleSheet("""
            QFrame#controlBar { background: #171715; border: 1px solid #34302b; border-radius: 20px; }
            QPushButton { color: #f6e8d0; border: none; border-radius: 14px; background: transparent;
                font-family: 'Segoe UI'; font-size: 12px; font-weight: 600; }
            QPushButton:hover { background: #383028; }
            QPushButton:pressed { background: #51402b; }
            QPushButton:disabled { color: #65615b; }
            QPushButton#playButton { background: #ffb44d; border-radius: 19px; }
            QPushButton#playButton:hover { background: #ffca7d; }
            QPushButton#playButton:disabled { background: #66553e; }
            QLabel { border: none; color: #c5b9a5; background: transparent;
                font-family: 'Segoe UI'; font-size: 10px; }
            QSlider::groove:horizontal { height: 3px; background: #51483a; border-radius: 1px; }
            QSlider::sub-page:horizontal { background: #ffb44d; border-radius: 1px; }
            QSlider::handle:horizontal { width: 10px; margin: -4px 0;
                background: #ffb44d; border-radius: 5px; }
            QSlider::handle:horizontal:focus { border: 1px solid #f6e8d0; }
            QSlider::sub-page:horizontal:disabled { background: #66553e; }
            QSlider::handle:horizontal:disabled { background: #65615b; }
        """)
        bar_layout = QVBoxLayout(self.bar)
        bar_layout.setContentsMargins(10, 7, 10, 8)
        bar_layout.setSpacing(4)
        buttons = QHBoxLayout()
        buttons.setSpacing(3)
        self.restart_button = self._button("Baştan başlat", controller.restart, "restart")
        self.back_button = self._button("Geri al", lambda: controller.seek(-controller.seek_seconds))
        self.play_button = self._button("Oynat", controller.play_pause, "play")
        self.play_button.setObjectName("playButton")
        self.play_button.setFixedSize(38, 38)
        self.forward_button = self._button("İleri al", lambda: controller.seek(controller.seek_seconds))
        self.stop_button = self._button("Durdur", self._stop_reading, "stop")
        for button in (self.restart_button, self.back_button, self.play_button,
                       self.forward_button, self.stop_button):
            buttons.addWidget(button)
        bar_layout.addLayout(buttons)
        self.timeline = SeekSlider()
        self.timeline.setFixedHeight(18)
        self.timeline.setAccessibleName("Ses konumu")
        self.timeline.setToolTip("İstediğin zamana gitmek için tıkla veya sürükle")
        self.timeline.scrub_started.connect(self._begin_scrub)
        self.timeline.seek_requested.connect(self._seek_timeline)
        self.timeline.sliderMoved.connect(self.refresh)
        bar_layout.addWidget(self.timeline)
        self.status_label = QLabel()
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse |
                                                  Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        self.status_label.linkActivated.connect(lambda link: self.toggle_reader() if link == 'document' else None)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self.status_label)
        layout.addWidget(self.bar)
        self._compact_size = QSize(274, self.mascot_column.sizeHint().height())
        self.mascot_column.setFixedSize(self._compact_size)
        root_layout.addWidget(self.mascot_column, 0, Qt.AlignmentFlag.AlignBottom)
        self.reader_panel = ReaderPanel(self)
        self.reader_panel.close_requested.connect(self.toggle_reader)
        self.reader_panel.segment_requested.connect(self.controller.seek_segment)
        self.reader_panel.hide()
        root_layout.addWidget(self.reader_panel)
        self.setFixedSize(self._compact_size)
        self.setWindowIcon(QIcon(self.mascot.current_frame()))
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Maskotlu Markdown Okuyucu")
        self.tray.activated.connect(self._tray_activated)
        self.menu = self._build_menu()
        self.tray.setContextMenu(self.menu)
        if QSystemTrayIcon.isSystemTrayAvailable() and persist_settings:
            self.tray.show()
        self.controller.changed.connect(self.refresh)
        self.controller.message.connect(self.notify)
        self._shortcuts = []
        for key, callback in (
            (Qt.Key.Key_Space, controller.play_pause),
            (Qt.Key.Key_Left, lambda: controller.seek(-controller.seek_seconds)),
            (Qt.Key.Key_Right, lambda: controller.seek(controller.seek_seconds)),
            (Qt.Key.Key_Escape, self._stop_reading),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        app = QApplication.instance()
        app.screenAdded.connect(self._screens_changed)
        app.screenRemoved.connect(self._screens_changed)
        for screen in app.screens():
            screen.availableGeometryChanged.connect(self.ensure_on_screen)
        self._restore_position()
        self.refresh()

    def _button(self, label, action, icon=None):
        button = QPushButton()
        button.setFixedSize(42, 34)
        button.setToolTip(label)
        button.setAccessibleName(label)
        if icon:
            button.setIcon(transport_icon(icon))
            button.setIconSize(QSize(22, 22))
        button.clicked.connect(action)
        return button

    def _build_menu(self):
        menu = QMenu(self)
        menu.addAction("Markdown dosyası aç…", self.choose_file)
        self.save_action = menu.addAction("WAV olarak kaydet…", self.save_wav)
        menu.addAction('Maskot seç…', self.choose_mascot)
        menu.addSeparator()
        speed_menu = menu.addMenu("Okuma hızı")
        self.speed_group = QActionGroup(self)
        for speed in (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0):
            label = f"{speed:g}×".replace(".", ",")
            action = speed_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(speed == self.controller.speed)
            self.speed_group.addAction(action)
            action.triggered.connect(lambda checked=False, value=speed: self.change_speed(value))
        self.code_action = menu.addAction("Kod bloklarını oku")
        self.code_action.setCheckable(True)
        self.code_action.setChecked(self.controller.include_code)
        self.code_action.triggered.connect(self.change_code)
        seek_menu = menu.addMenu("Geri / ileri atlama")
        self.seek_group = QActionGroup(self)
        for seconds in (5, 10):
            action = seek_menu.addAction(f"{seconds} saniye")
            action.setCheckable(True)
            action.setChecked(seconds == self.controller.seek_seconds)
            self.seek_group.addAction(action)
            action.triggered.connect(lambda checked=False, value=seconds: self.change_seek(value))
        menu.addSeparator()
        self.top_action = menu.addAction("Her zaman üstte")
        self.top_action.setCheckable(True)
        self.top_action.setChecked(self._always_on_top)
        self.top_action.triggered.connect(self.toggle_top)
        menu.addAction("Maskotu göster", self.show_mascot)
        self.hide_action = menu.addAction("Maskotu gizle", self.hide)
        self.hide_action.setEnabled(QSystemTrayIcon.isSystemTrayAvailable())
        menu.addAction("Çıkış", self.exit_application)
        return menu

    def choose_file(self):
        folder = str(self.controller.source.parent) if self.controller.source else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Seslendirilecek Markdown dosyasını seç", folder,
            "Markdown dosyaları (*.md *.markdown)",
        )
        if path:
            self.controller.open_document(Path(path))

    def choose_mascot(self):
        chooser = MascotChooser(self.mascots, self._selected_mascot_id, self)
        chooser.mascot_selected.connect(self.select_mascot)
        chooser.exec()

    def select_mascot(self, mascot_id):
        selected = next((mascot for mascot in self.mascots if mascot.id == mascot_id), None)
        if selected is None:
            return
        self.mascot.set_mascot(selected)
        self._selected_mascot_id = selected.id
        icon = QIcon(self.mascot.current_frame())
        self.setWindowIcon(icon)
        self.tray.setIcon(icon)
        if self._persist:
            self.settings.setValue('mascot', selected.id)

    def toggle_reader(self):
        if self.reader_panel.isHidden():
            if self.controller.source is None:
                return
            before = self.pos()
            self.reader_panel.show()
            self.ensure_on_screen()
            self._panel_shift = before - self.pos()
        else:
            position = self.pos() + self._panel_shift
            self.reader_panel.hide()
            self.setFixedSize(self._compact_size)
            self.move(position)
            self._panel_shift = QPoint()
            self.ensure_on_screen()
        self.refresh()

    def save_wav(self):
        if self.controller.audio_path is None:
            return
        suggested = self.controller.source.with_suffix(".wav")
        path, _ = QFileDialog.getSaveFileName(self, "Ses dosyasını kaydet", str(suggested), "WAV sesi (*.wav)")
        if path:
            target = Path(path)
            if target.suffix.lower() != ".wav":
                target = target.with_name(target.name + ".wav")
            try:
                self.controller.export_audio(target)
                self.notify(f"Ses kaydedildi: {target.name}")
            except OSError as error:
                self.notify(f"Ses kaydedilemedi: {error}")

    def change_speed(self, speed):
        self.controller.set_options(speed=speed)
        self._save_options()

    def change_code(self, enabled):
        self.controller.set_options(include_code=enabled)
        self._save_options()

    def change_seek(self, seconds):
        self.controller.seek_seconds = seconds
        self._save_options()
        self.refresh()

    def _save_options(self):
        if self._persist:
            self.settings.setValue("speed", self.controller.speed)
            self.settings.setValue("include_code", self.controller.include_code)
            self.settings.setValue("seek_seconds", self.controller.seek_seconds)

    def toggle_top(self, enabled):
        self._always_on_top = enabled
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        if self._persist:
            self.settings.setValue("always_on_top", enabled)

    def _begin_scrub(self):
        self._resume_after_scrub = self.controller.playing
        if self._resume_after_scrub:
            self.controller.play_pause()

    def _stop_reading(self):
        self._resume_after_scrub = False
        self.timeline.cancel_scrub()
        self.controller.stop()

    def _seek_timeline(self, position):
        resume = self._resume_after_scrub
        self._resume_after_scrub = False
        self.controller.seek_to(position)
        if resume and position < self.controller.player.duration() and not self.controller.playing:
            self.controller.play_pause()
        self.refresh()

    def refresh(self):
        controller = self.controller
        ready = controller.audio_path is not None and not controller.preparing
        self.restart_button.setEnabled(ready)
        self.play_button.setEnabled(ready)
        seekable = ready and controller.player.isSeekable()
        if not seekable:
            self._resume_after_scrub = False
            self.timeline.cancel_scrub()
        self.timeline.setEnabled(seekable)
        with QSignalBlocker(self.timeline):
            self.timeline.setRange(0, controller.player.duration() if seekable else 0)
            if not self.timeline.isSliderDown():
                self.timeline.setValue(controller.player.position() if seekable else 0)
        self.back_button.setEnabled(seekable)
        self.forward_button.setEnabled(seekable)
        self.stop_button.setEnabled(ready or controller.preparing)
        self.save_action.setEnabled(ready)
        seconds = controller.seek_seconds
        self.back_button.setText(f"−{seconds}")
        self.forward_button.setText(f"+{seconds}")
        self.back_button.setToolTip(f"{seconds} saniye geri al")
        self.forward_button.setToolTip(f"{seconds} saniye ileri al")
        self.back_button.setAccessibleName(self.back_button.toolTip())
        self.forward_button.setAccessibleName(self.forward_button.toolTip())
        self.play_button.setIcon(transport_icon("pause" if controller.playing else "play", "#24201b"))
        self.play_button.setToolTip("Duraklat" if controller.playing else "Oynat")
        self.play_button.setAccessibleName(self.play_button.toolTip())
        if ready:
            name = self.status_label.fontMetrics().elidedText(controller.source.name, Qt.TextElideMode.ElideMiddle, 140)
            position = self.timeline.sliderPosition() if self.timeline.isSliderDown() else controller.player.position()
            text = f'<a href="document" style="color:#c5b9a5;text-decoration:none">{escape(name)}</a>  ·  {clock_time(position)} / {clock_time(controller.player.duration())}'
        else:
            text = controller.status
        self.status_label.setText(text)
        self.status_label.setToolTip(f"{controller.source or ''}\n{controller.status}")
        self.reader_panel.set_document(controller.audio_document, controller.job_id,
                                       controller.source.name if controller.source else '', controller.preparing)
        current_cue = controller.audio_document.cue_at(controller.player.position()) if ready and controller.audio_document else None
        self.reader_panel.set_active_cue(current_cue)
        self.mascot.set_animation("preparing" if controller.preparing else "speaking" if controller.playing else "idle")

    def notify(self, text):
        self.setToolTip(text)
        self.status_label.setToolTip(text)
        if self.tray.isVisible():
            self.tray.showMessage("Markdown Okuyucu", text, QSystemTrayIcon.MessageIcon.Information, 7000)

    def contextMenuEvent(self, event):
        self.menu.exec(event.globalPos())

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_mascot()

    def show_mascot(self):
        self.ensure_on_screen()
        self.show()
        self.raise_()

    def _restore_position(self):
        screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry()
        position = QPoint(geometry.right() - self.width() - 23, geometry.bottom() - self.height() - 23)
        if self._persist:
            position = self.settings.value("position", position, type=QPoint)
        self.move(position)
        self.ensure_on_screen()

    def _screens_changed(self, screen):
        for available_screen in QApplication.screens():
            available_screen.availableGeometryChanged.connect(self.ensure_on_screen, Qt.ConnectionType.UniqueConnection)
        self.ensure_on_screen()

    def ensure_on_screen(self, *args):
        screens = QApplication.screens()
        if not screens:
            return
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        compact_position = self.pos() + self._panel_shift
        if not self.reader_panel.isHidden():
            width = min(360, max(0, available.width() - self._compact_size.width() - 10))
            height = min(430, max(self._compact_size.height(), available.height() - 24))
            old_height = self.height()
            self.reader_panel.setFixedSize(width, height)
            self.setFixedSize(self._compact_size.width() + width + 10, height)
            self.move(self.x(), self.y() + old_height - height)
        self.move(clamp_position(self.pos(), available, self.size()))
        if not self.reader_panel.isHidden():
            self._panel_shift = compact_position - self.pos()

    def save_position(self):
        self.ensure_on_screen()
        if self._persist:
            self.settings.setValue("position", self.pos() + self._panel_shift)

    def closeEvent(self, event):
        if self._exiting:
            event.accept()
        elif self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.controller.close()
            event.accept()
            QApplication.instance().quit()

    def exit_application(self):
        self._exiting = True
        self.save_position()
        self.controller.close()
        self.tray.hide()
        QApplication.instance().quit()

