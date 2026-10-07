import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .paths import resource_dir


@dataclass(frozen=True)
class MascotDefinition:
    id: str
    name: str
    metadata_path: Path

    def metadata(self):
        return json.loads(self.metadata_path.read_text(encoding='utf-8'))


def load_mascots() -> tuple[MascotDefinition, ...]:
    root = resource_dir()
    catalog = root / 'mascots' / 'catalog.json'
    if not catalog.exists():
        return (MascotDefinition('ember', 'Kıvılcım', root / 'mascot.json'),)
    data = json.loads(catalog.read_text(encoding='utf-8'))
    mascots = tuple(MascotDefinition(item['id'], item['name'], catalog.parent / item['metadata'])
                    for item in data['mascots'])
    if not mascots or len({mascot.id for mascot in mascots}) != len(mascots):
        raise ValueError('Maskot kataloğu boş veya yinelenen kayıtlar içeriyor.')
    return mascots


def mascot_icon(mascot: MascotDefinition, side=110) -> QIcon:
    metadata = mascot.metadata()
    sheet = QPixmap(str(mascot.metadata_path.parent / metadata['image']))
    animation = metadata['animations']['idle']
    frame = sprite_frame(metadata, sheet, animation, 0)
    result = QPixmap(side, side)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    offset = animation['baseline_offset_y'] * side / metadata['cell_height']
    painter.drawPixmap(QRectF(0, offset, side, side), frame, QRectF(frame.rect()))
    painter.end()
    return QIcon(result)


def _source_frame(metadata, sheet, animation, column):
    width, height = metadata['cell_width'], metadata['cell_height']
    source_y = animation.get('source_y', animation['row'] * height)
    source_height = animation.get('source_height', height)
    cropped = sheet.copy(column * width, source_y, width, source_height)
    frame = QPixmap(width, height)
    frame.fill(Qt.GlobalColor.transparent)
    painter = QPainter(frame)
    painter.drawPixmap(0, animation.get('destination_y', 0), cropped)
    painter.end()
    return frame


def sprite_frame(metadata, sheet, animation, column):
    current = _source_frame(metadata, sheet, animation, column)
    desk_top = metadata.get('stationary_desk_y')
    if desk_top is None:
        return current
    reference = _source_frame(metadata, sheet, metadata['animations']['idle'], 0)
    frame = reference.copy()
    dx, dy = animation['frame_offsets'][column]
    painter = QPainter(frame)
    painter.setClipRect(0, 0, metadata['cell_width'], desk_top)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(0, 0, metadata['cell_width'], desk_top, Qt.GlobalColor.transparent)
    painter.drawPixmap(dx, dy, current)
    painter.end()
    return frame


class MascotChooser(QDialog):
    mascot_selected = Signal(str)

    def __init__(self, mascots, selected_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Maskot seç')
        self.setStyleSheet("""
            QDialog, QScrollArea, QWidget#mascotGrid { background: #1c1b18; }
            QLabel { color: #f6e8d0; font-family: 'Segoe UI'; font-size: 14px; }
            QToolButton { color: #d6cabb; background: #28251f; border: 1px solid #494137;
                border-radius: 12px; padding: 6px; font-family: 'Segoe UI'; font-size: 12px; }
            QToolButton:hover { background: #383028; border-color: #ffb44d; }
            QToolButton:checked { background: #3c3022; border: 2px solid #ffb44d; }
            QScrollArea { border: none; }
        """)
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry()
        columns = min(5, max(2, (available.width() - 50) // 128))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Okuma arkadaşını seç'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName('mascotGrid')
        grid = QGridLayout(content)
        grid.setSpacing(10)
        self.buttons = {}
        for index, mascot in enumerate(mascots):
            button = QToolButton()
            button.setIcon(mascot_icon(mascot))
            button.setIconSize(QSize(100, 100))
            button.setText(mascot.name)
            button.setAccessibleName(mascot.name)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setChecked(mascot.id == selected_id)
            button.setFixedSize(118, 140)
            button.clicked.connect(lambda checked=False, choice=mascot.id: self._select(choice))
            grid.addWidget(button, index // columns, index % columns)
            self.buttons[mascot.id] = button
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.resize(min(columns * 128 + 40, available.width() - 24),
                    min(365, available.height() - 24))

    def _select(self, mascot_id):
        self.mascot_selected.emit(mascot_id)
        self.accept()
