from __future__ import annotations

import re

from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QCompleter, QTextEdit


class TagTextEdit(QTextEdit):
    """Text editor that completes expression tags and dialogue speakers."""

    def __init__(self, tags: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self._tags = tags
        self._speaker_names: tuple[str, ...] = ()
        self._completion_model = QStringListModel(list(tags), self)
        self._completer = QCompleter(self._completion_model, self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._completer.setWrapAround(False)
        self._completer.activated[str].connect(self._insert_completion)

    def set_speaker_names(self, names: list[str]) -> None:
        self._speaker_names = tuple(dict.fromkeys(name.strip() for name in names if name.strip()))

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
        completion_context = self._completion_context_at_cursor()
        if completion_context is None:
            self._completer.popup().hide()
            return
        prefix, completions = completion_context

        self._completion_model.setStringList(list(completions))
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

    def _speaker_prefix_at_cursor(self) -> str | None:
        if not self._speaker_names:
            return None
        cursor = self.textCursor()
        text_before_cursor = cursor.block().text()[: cursor.positionInBlock()]
        if re.fullmatch(r"[^:\[\]]*", text_before_cursor) is None:
            return None
        return text_before_cursor.strip()

    def _completion_context_at_cursor(self) -> tuple[str, tuple[str, ...]] | None:
        tag_prefix = self._tag_prefix_at_cursor()
        if tag_prefix is not None:
            return tag_prefix, self._tags
        speaker_prefix = self._speaker_prefix_at_cursor()
        if speaker_prefix is not None:
            completions = tuple(f"{name}: " for name in self._speaker_names)
            return speaker_prefix, completions
        return None

    def _insert_completion(self, completion: str) -> None:
        completion_context = self._completion_context_at_cursor()
        if completion_context is None:
            return
        prefix, _completions = completion_context
        cursor = self.textCursor()
        cursor.movePosition(
            QTextCursor.MoveOperation.Left,
            QTextCursor.MoveMode.KeepAnchor,
            len(prefix),
        )
        cursor.insertText(completion)
        self.setTextCursor(cursor)
        self._completer.popup().hide()
