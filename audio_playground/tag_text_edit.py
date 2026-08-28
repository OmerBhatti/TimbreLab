from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QCompleter, QTextEdit


class TagTextEdit(QTextEdit):
    """Text editor that completes bracketed expression tags at the cursor."""

    def __init__(self, tags: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self._completer = QCompleter(tags, self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._completer.setWrapAround(False)
        self._completer.activated[str].connect(self._insert_completion)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        popup = self._completer.popup()
        if popup.isVisible():
            if event.key() in {Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab}:
                completion = popup.currentIndex().data(Qt.ItemDataRole.DisplayRole)
                if completion:
                    self._insert_completion(str(completion))
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                popup.hide()
                event.accept()
                return
            if event.key() in {Qt.Key.Key_Up, Qt.Key.Key_Down}:
                model = popup.model()
                row = popup.currentIndex().row()
                offset = -1 if event.key() == Qt.Key.Key_Up else 1
                row = max(0, min(row + offset, model.rowCount() - 1))
                popup.setCurrentIndex(model.index(row, 0))
                event.accept()
                return

        super().keyPressEvent(event)
        prefix = self._tag_prefix_at_cursor()
        if prefix is None:
            self._completer.popup().hide()
            return

        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            self._completer.popup().hide()
            return

        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(
            max(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width(), 240)
        )
        self._completer.complete(rect)

    def _tag_prefix_at_cursor(self) -> str | None:
        cursor = self.textCursor()
        text_before_cursor = cursor.block().text()[: cursor.positionInBlock()]
        match = re.search(r"\[[^\[\]\s]*$", text_before_cursor)
        return match.group(0) if match else None

    def _insert_completion(self, completion: str) -> None:
        prefix = self._tag_prefix_at_cursor()
        if prefix is None:
            return
        cursor = self.textCursor()
        cursor.movePosition(
            QTextCursor.MoveOperation.Left,
            QTextCursor.MoveMode.KeepAnchor,
            len(prefix),
        )
        cursor.insertText(completion)
        self.setTextCursor(cursor)
        self._completer.popup().hide()
