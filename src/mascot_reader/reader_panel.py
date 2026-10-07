from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
)

from .reading import render_document_html


class LocalDocumentBrowser(QTextBrowser):
    def loadResource(self, resource_type, name):
        return None


class ReaderPanel(QFrame):
    close_requested = Signal()
    segment_requested = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('readerPanel')
        self.setStyleSheet("""
            QFrame#readerPanel { background: #1c1b18; border: 1px solid #494137; border-radius: 16px; }
            QLabel { color: #f6e8d0; border: none; font-family: 'Segoe UI'; font-size: 12px; }
            QToolButton { border: none; color: #c5b9a5; background: transparent;
                font-size: 18px; border-radius: 8px; }
            QToolButton:hover { background: #383028; }
            QTextBrowser { border: none; background: transparent; padding: 5px; }
            QScrollBar:vertical { background: #27251f; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #66553e; min-height: 25px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 12)
        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setMinimumWidth(0)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(self.title, 1)
        close = QToolButton()
        close.setText('×')
        close.setToolTip('Markdown panelini kapat')
        close.setAccessibleName(close.toolTip())
        close.setFixedSize(28, 28)
        close.clicked.connect(self.close_requested)
        header.addWidget(close)
        layout.addLayout(header)
        self.browser = LocalDocumentBrowser()
        self.browser.setMinimumSize(0, 0)
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setAccessibleName('Markdown içeriği; ses bölümüne atlamak için metne tıkla')
        self.browser.anchorClicked.connect(self._anchor_clicked)
        layout.addWidget(self.browser)
        self.active_cue = None
        self._document_key = None
        self._cue_ranges = {}

    def _anchor_clicked(self, url):
        parts = url.toString().split(':')
        if len(parts) == 3 and parts[0] == 'segment':
            try:
                job, cue = int(parts[1]), int(parts[2])
            except ValueError:
                return
            self.segment_requested.emit(job, cue)

    def set_document(self, document, job_id, title, preparing=False):
        self.title.setText(self.title.fontMetrics().elidedText(title, Qt.TextElideMode.ElideMiddle, max(30, self.width() - 70)))
        self.title.setToolTip(title)
        key = (job_id, id(document), title, preparing)
        if key == self._document_key:
            return
        self._document_key = key
        self.active_cue = None
        self._cue_ranges.clear()
        self.browser.setExtraSelections([])
        if document is None:
            self.browser.setPlainText('Ses hazırlanıyor…' if preparing else 'Markdown içeriği ses hazırlandıktan sonra burada görünecek.')
            return
        self.browser.setHtml(render_document_html(document, job_id))
        block = self.browser.document().begin()
        while block.isValid():
            fragment_iterator = block.begin()
            while not fragment_iterator.atEnd():
                fragment = fragment_iterator.fragment()
                if fragment.isValid():
                    href = fragment.charFormat().anchorHref()
                    parts = href.split(':')
                    if len(parts) == 3 and parts[0] == 'segment':
                        cue = int(parts[2])
                        start, end = fragment.position(), fragment.position() + fragment.length()
                        if cue in self._cue_ranges:
                            previous = self._cue_ranges[cue]
                            start, end = min(start, previous[0]), max(end, previous[1])
                        self._cue_ranges[cue] = (start, end)
                fragment_iterator += 1
            block = block.next()

    def set_active_cue(self, index):
        if index == self.active_cue:
            return
        self.active_cue = index
        selections = []
        if index in self._cue_ranges:
            start, end = self._cue_ranges[index]
            cursor = QTextCursor(self.browser.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setBackground(QColor('#4b3a25'))
            selection.format.setForeground(QColor('#ffce86'))
            selections.append(selection)
        self.browser.setExtraSelections(selections)
