from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PyQt6.QtCore import QSettings, QTime, QUrl, Qt
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from audio_playground.audio_utils import (
    ALL_EXPRESSION_TAGS,
    INLINE_EMOTION_TAGS,
    OMNIVOICE_NONVERBAL_TAGS,
    normalize_emotion_tags,
    output_path,
)
from audio_playground.config import OMNIVOICE_PYTHON, OUTPUT_DIR, SFX_PYTHON
from audio_playground.tag_text_edit import TagTextEdit
from audio_playground.voice_presets import VoicePresetStore
from audio_playground.worker_client import WorkerClient


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Audio Playground")
        self.resize(1100, 760)
        self.setMinimumSize(860, 640)
        self.preset_store = VoicePresetStore(QSettings())
        self._shutdown_complete = False
        self._session_files_cleaned = False

        self.session_files = tempfile.TemporaryDirectory(prefix="ai-audio-playground-")
        self.session_dir = Path(self.session_files.name)
        self.tts_worker = WorkerClient(
            OMNIVOICE_PYTHON, "audio_playground.workers.omnivoice_worker", self
        )
        self.sfx_worker = WorkerClient(
            SFX_PYTHON, "audio_playground.workers.audioldm_worker", self
        )
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.current_audio: Path | None = None

        self._build_ui()
        self._connect_workers()
        self._apply_theme()

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel("AI Audio Playground")
        title.setObjectName("title")
        subtitle = QLabel("Emotional speech with OmniVoice · Sound effects with AudioLDM")
        subtitle.setObjectName("subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tts_tab(), "  Emotional TTS  ")
        self.tabs.addTab(self._build_sfx_tab(), "  SFX && Effects  ")
        outer.addWidget(self.tabs, 1)
        outer.addWidget(self._build_player())
        self.setCentralWidget(root)

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _build_tts_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 12)
        layout.setSpacing(14)

        layout.addWidget(self._section_label("Text to speak"))
        self.tts_text = TagTextEdit(ALL_EXPRESSION_TAGS)
        self.tts_text.setPlaceholderText(
            "Use tags wherever delivery changes, for example: [sad] I miss you. [happy] You're home!"
        )
        self.tts_text.setPlainText(
            "[surprised] I can't believe we finally made it. [happy] This is amazing!"
        )
        self.tts_text.setMinimumHeight(130)
        layout.addWidget(self.tts_text, 1)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Voice preset"))
        self.voice_preset = QComboBox()
        self.voice_preset.setMinimumWidth(190)
        self.voice_preset.currentIndexChanged.connect(self._apply_selected_voice_preset)
        self.save_voice_preset = QPushButton("Save current…")
        self.save_voice_preset.clicked.connect(self._save_voice_preset)
        self.delete_voice_preset = QPushButton("Delete")
        self.delete_voice_preset.clicked.connect(self._delete_voice_preset)
        preset_row.addWidget(self.voice_preset)
        preset_row.addWidget(self.save_voice_preset)
        preset_row.addWidget(self.delete_voice_preset)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Insert expression"))
        self.emotion_tag = QComboBox()
        for tag in INLINE_EMOTION_TAGS:
            self.emotion_tag.addItem(tag.removeprefix("[").removesuffix("]").title(), tag)
        self.emotion_tag.insertSeparator(self.emotion_tag.count())
        for tag in OMNIVOICE_NONVERBAL_TAGS:
            label = tag.removeprefix("[").removesuffix("]").replace("-", " ").title()
            self.emotion_tag.addItem(label, tag)
        self.insert_emotion_tag = QPushButton("Insert tag")
        self.insert_emotion_tag.clicked.connect(self._insert_emotion_tag)
        tag_hint = QLabel(
            "Includes friendly emotion aliases and every supported OmniVoice non-verbal cue."
        )
        tag_hint.setObjectName("hint")
        tag_row.addWidget(self.emotion_tag)
        tag_row.addWidget(self.insert_emotion_tag)
        tag_row.addWidget(tag_hint)
        tag_row.addStretch()
        layout.addLayout(tag_row)

        controls = QHBoxLayout()
        form = QFormLayout()
        self.tts_mode = QComboBox()
        self.tts_mode.addItem("Design a voice", "design")
        self.tts_mode.addItem("Automatic voice", "auto")
        self.tts_mode.currentIndexChanged.connect(self._update_tts_mode)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.5, 2.0)
        self.speed.setSingleStep(0.1)
        self.speed.setValue(0.9)
        self.steps = QSpinBox()
        self.steps.setRange(8, 128)
        self.steps.setSingleStep(8)
        self.steps.setValue(64)
        form.addRow("Voice mode", self.tts_mode)
        form.addRow("Speaking speed", self.speed)
        form.addRow("Diffusion steps", self.steps)
        controls.addLayout(form, 1)

        self.voice_stack = QStackedWidget()
        self.voice_stack.setMinimumHeight(210)
        self.voice_stack.addWidget(self._build_design_panel())
        self.voice_stack.addWidget(self._build_auto_panel())
        controls.addWidget(self.voice_stack, 2)
        layout.addLayout(controls)

        page_layout.addWidget(self._scrollable(content), 1)

        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(22, 10, 22, 16)
        hint = QLabel("Tip: Lower Diffusion steps is faster; 64 generally gives better quality.")
        hint.setObjectName("hint")
        row.addWidget(hint)
        row.addStretch()
        self.tts_generate = QPushButton("Generate speech")
        self.tts_generate.setObjectName("primary")
        self.tts_generate.clicked.connect(self._generate_tts)
        row.addWidget(self.tts_generate)
        page_layout.addWidget(footer)
        self._refresh_voice_presets()
        return page

    def _build_design_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        form = QFormLayout(panel)
        self.gender = QComboBox()
        self.gender.addItems(["female", "male"])
        self.age = QComboBox()
        self.age.addItems(["young adult", "middle-aged", "teenager", "child", "elderly"])
        self.pitch = QComboBox()
        self.pitch.addItems(
            ["moderate pitch", "low pitch", "high pitch", "very low pitch", "very high pitch"]
        )
        self.accent = QComboBox()
        self.accent.addItems(
            [
                "american accent",
                "british accent",
                "australian accent",
                "canadian accent",
                "indian accent",
                "chinese accent",
                "japanese accent",
                "korean accent",
                "portuguese accent",
                "russian accent",
            ]
        )
        self.voice_style = QComboBox()
        self.voice_style.addItem("normal", None)
        self.voice_style.addItem("whispering", "whisper")
        self.gender.setCurrentText("male")
        self.age.setCurrentText("elderly")
        self.pitch.setCurrentText("very low pitch")
        self.accent.setCurrentText("british accent")
        form.addRow("Gender", self.gender)
        form.addRow("Age", self.age)
        form.addRow("Pitch", self.pitch)
        form.addRow("Accent", self.accent)
        form.addRow("Style", self.voice_style)
        return panel

    def _build_auto_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        label = QLabel(
            "OmniVoice will choose a voice automatically. This is quick to configure, "
            "but the voice may vary between generations."
        )
        label.setWordWrap(True)
        label.setObjectName("hint")
        layout.addWidget(label)
        layout.addStretch()
        return panel

    def _build_sfx_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 12)
        layout.setSpacing(14)
        layout.addWidget(self._section_label("Describe the sound"))
        self.sfx_prompt = QTextEdit()
        self.sfx_prompt.setPlainText(
            "A cinematic thunder crack followed by heavy rain on a metal rooftop, realistic, no music"
        )
        self.sfx_prompt.setPlaceholderText(
            "Example: Fast footsteps in a stone hallway, tense, distant echo, no music"
        )
        layout.addWidget(self.sfx_prompt, 1)

        form = QFormLayout()
        self.duration = QDoubleSpinBox()
        self.duration.setRange(1.0, 30.0)
        self.duration.setValue(5.0)
        self.duration.setSuffix(" seconds")
        self.guidance = QDoubleSpinBox()
        self.guidance.setRange(1.0, 5.0)
        self.guidance.setSingleStep(0.5)
        self.guidance.setValue(2.5)
        self.sfx_steps = QSpinBox()
        self.sfx_steps.setRange(8, 256)
        self.sfx_steps.setSingleStep(8)
        self.sfx_steps.setValue(128)
        form.addRow("Duration", self.duration)
        form.addRow("Prompt guidance", self.guidance)
        form.addRow("Diffusion steps", self.sfx_steps)
        layout.addLayout(form)

        page_layout.addWidget(self._scrollable(content), 1)

        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(22, 10, 22, 16)
        note = QLabel(
            "AudioLDM Small v2 is a lightweight 421M-parameter SFX model with native "
            "Apple Metal support. The first run downloads about 1.7 GB."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        row.addWidget(note, 1)
        self.sfx_generate = QPushButton("Generate sound effect")
        self.sfx_generate.setObjectName("primary")
        self.sfx_generate.clicked.connect(self._generate_sfx)
        row.addWidget(self.sfx_generate)
        page_layout.addWidget(footer)
        return page

    def _build_player(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("player")
        layout = QVBoxLayout(frame)
        top = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self._toggle_playback)
        self.output_label = QLabel("No audio generated yet")
        self.output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.download_button = QPushButton("Download audio…")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._download_audio)
        top.addWidget(self.play_button)
        top.addWidget(self.output_label, 1)
        top.addWidget(self.download_button)
        layout.addLayout(top)
        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("")
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("hint")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("danger")
        self.stop_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop)
        )
        self.stop_button.setEnabled(False)
        self.stop_button.setVisible(False)
        self.stop_button.setToolTip("Stop the active model download or generation")
        self.stop_button.clicked.connect(self._stop_generation)
        self.log_toggle = QPushButton("Show logs")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_logs)
        bottom.addWidget(self.status_label, 1)
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.log_toggle)
        bottom.addWidget(self.stop_button)
        layout.addLayout(bottom)
        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("logs")
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(120)
        self.log_output.document().setMaximumBlockCount(300)
        self.log_output.setPlaceholderText("Engine activity will appear here.")
        self.log_output.setVisible(False)
        layout.addWidget(self.log_output)
        return frame

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        font = QFont()
        font.setPointSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        label.setFont(font)
        return label

    def _connect_workers(self) -> None:
        for worker in (self.tts_worker, self.sfx_worker):
            worker.status.connect(self.status_label.setText)
            worker.log.connect(self._append_log)
            worker.result.connect(self._audio_ready)
            worker.error.connect(self._show_error)
            worker.progress.connect(self._update_progress)
        self.tts_worker.busy_changed.connect(self._tts_busy)
        self.sfx_worker.busy_changed.connect(self._sfx_busy)
        self.player.playbackStateChanged.connect(self._playback_changed)

    def _update_tts_mode(self) -> None:
        self.voice_stack.setCurrentIndex(self.tts_mode.currentIndex())

    def _voice_configuration(self) -> dict[str, object]:
        return {
            "mode": self.tts_mode.currentData(),
            "gender": self.gender.currentText(),
            "age": self.age.currentText(),
            "pitch": self.pitch.currentText(),
            "accent": self.accent.currentText(),
            "style": self.voice_style.currentText(),
            "speed": self.speed.value(),
            "steps": self.steps.value(),
        }

    def _refresh_voice_presets(self, selected_name: str = "") -> None:
        presets = self.preset_store.all()
        self.voice_preset.blockSignals(True)
        self.voice_preset.clear()
        self.voice_preset.addItem("Select a preset…", None)
        for name in sorted(presets, key=str.casefold):
            self.voice_preset.addItem(name, name)
        if selected_name:
            index = self.voice_preset.findData(selected_name)
            if index >= 0:
                self.voice_preset.setCurrentIndex(index)
        self.voice_preset.blockSignals(False)
        self.delete_voice_preset.setEnabled(self.voice_preset.currentData() is not None)

    def _save_voice_preset(self) -> None:
        current_name = self.voice_preset.currentData() or ""
        name, accepted = QInputDialog.getText(
            self, "Save voice preset", "Preset name:", text=current_name
        )
        name = name.strip()
        if not accepted or not name:
            return
        if name in self.preset_store.all() and name != current_name:
            answer = QMessageBox.question(
                self,
                "Replace voice preset?",
                f'A preset named "{name}" already exists. Replace it?',
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.preset_store.save(name, self._voice_configuration())
        self._refresh_voice_presets(name)
        self.status_label.setText(f'Voice preset "{name}" saved.')

    def _delete_voice_preset(self) -> None:
        name = self.voice_preset.currentData()
        if not name:
            return
        answer = QMessageBox.question(
            self, "Delete voice preset?", f'Delete the voice preset "{name}"?'
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.preset_store.delete(name)
        self._refresh_voice_presets()
        self.status_label.setText(f'Voice preset "{name}" deleted.')

    def _apply_selected_voice_preset(self, _index: int) -> None:
        name = self.voice_preset.currentData()
        self.delete_voice_preset.setEnabled(name is not None)
        if not name:
            return
        config = self.preset_store.all().get(name)
        if not config:
            return
        mode = "design" if config.get("mode") == "clone" else config.get("mode")
        self._set_combo_data(self.tts_mode, mode)
        self._set_combo_text(self.gender, config.get("gender"))
        self._set_combo_text(self.age, config.get("age"))
        self._set_combo_text(self.pitch, config.get("pitch"))
        self._set_combo_text(self.accent, config.get("accent"))
        saved_style = config.get("style")
        style = "whispering" if saved_style == "whisper" else str(saved_style)
        style_index = self.voice_style.findText(style)
        self.voice_style.setCurrentIndex(style_index if style_index >= 0 else 0)
        self.speed.setValue(float(config.get("speed", 1.0)))
        self.steps.setValue(int(config.get("steps", 32)))
        self.status_label.setText(f'Voice preset "{name}" applied.')

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: object) -> None:
        index = combo.findText(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _insert_emotion_tag(self) -> None:
        cursor = self.tts_text.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionStart())
        cursor.insertText(f"{self.emotion_tag.currentData()} ")
        self.tts_text.setTextCursor(cursor)
        self.tts_text.setFocus()

    def _generate_tts(self) -> None:
        text = self.tts_text.toPlainText().strip()
        if not text:
            self._show_error("Enter some text to synthesize.")
            return
        mode = self.tts_mode.currentData()
        style_instruction = self.voice_style.currentData()
        instruction = ", ".join(
            part
            for part in (
                self.gender.currentText(),
                self.age.currentText(),
                self.pitch.currentText(),
                self.accent.currentText(),
                style_instruction or "",
            )
            if part
        )
        destination = output_path(self.session_dir, "tts", "inline-emotions")
        self.tts_worker.generate(
            {
                "text": normalize_emotion_tags(text),
                "mode": mode,
                "voice_instruction": instruction,
                "speed": self.speed.value(),
                "steps": self.steps.value(),
                "output_path": str(destination),
            }
        )

    def _generate_sfx(self) -> None:
        prompt = self.sfx_prompt.toPlainText().strip()
        if not prompt:
            self._show_error("Describe the sound effect you want to generate.")
            return
        destination = output_path(self.session_dir, "sfx", prompt)
        self.sfx_worker.generate(
            {
                "prompt": prompt,
                "duration": self.duration.value(),
                "guidance": self.guidance.value(),
                "inference_steps": self.sfx_steps.value(),
                "output_path": str(destination),
            }
        )

    def _tts_busy(self, busy: bool) -> None:
        self._sync_busy_controls()

    def _sfx_busy(self, busy: bool) -> None:
        self._sync_busy_controls()

    def _sync_busy_controls(self) -> None:
        busy = self.tts_worker.busy or self.sfx_worker.busy
        self.tts_generate.setEnabled(not busy)
        self.sfx_generate.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.stop_button.setVisible(busy)
        if busy and not self.log_toggle.isChecked():
            self.log_toggle.setChecked(True)
        if busy:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Starting…")
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress.setFormat("")

    def _update_progress(self, value: int, label: str) -> None:
        if not (self.tts_worker.busy or self.sfx_worker.busy):
            return
        if value < 0:
            self.progress.setRange(0, 0)
            self.progress.setFormat(f"{label}…")
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(value, 100)))
        self.progress.setFormat(f"{label} · %p%")

    def _stop_generation(self) -> None:
        if self.tts_worker.busy:
            self.tts_worker.cancel()
        if self.sfx_worker.busy:
            self.sfx_worker.cancel()

    def _toggle_logs(self, visible: bool) -> None:
        self.log_output.setVisible(visible)
        self.log_toggle.setText("Hide logs" if visible else "Show logs")
        if visible and self.height() < 1040:
            available_height = self.screen().availableGeometry().height()
            self.resize(self.width(), min(1040, available_height))

    def _append_log(self, message: str) -> None:
        clean_message = message.strip()
        if not clean_message:
            return
        timestamp = QTime.currentTime().toString("HH:mm:ss")
        self.log_output.appendPlainText(f"[{timestamp}] {clean_message}")

    def _audio_ready(self, filename: str) -> None:
        self.current_audio = Path(filename)
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.output_label.setText(self.current_audio.name)
        self.output_label.setToolTip("Temporary preview — use Download audio to keep this file")
        self.play_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.status_label.setText("Generated. Preview is temporary until downloaded.")
        self.player.play()

    def _download_audio(self) -> None:
        if self.current_audio is None or not self.current_audio.is_file():
            self._show_error("Generate audio before downloading it.")
            return
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Download generated audio",
            str(OUTPUT_DIR / self.current_audio.name),
            "WAV audio (*.wav)",
        )
        if not filename:
            return
        destination = Path(filename)
        if not destination.suffix:
            destination = destination.with_suffix(".wav")
        try:
            shutil.copy2(self.current_audio, destination)
        except OSError as exc:
            self.status_label.setText("Download failed")
            QMessageBox.critical(
                self, "AI Audio Playground", f"Could not download audio: {exc}"
            )
            return
        self.status_label.setText(f"Downloaded to {destination}")
        self._append_log(f"Audio downloaded to {destination}")

    def _show_error(self, message: str) -> None:
        self.status_label.setText("Generation failed")
        QMessageBox.critical(self, "AI Audio Playground", message)

    def _toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _playback_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        icon = (
            QStyle.StandardPixmap.SP_MediaPause
            if state == QMediaPlayer.PlaybackState.PlayingState
            else QStyle.StandardPixmap.SP_MediaPlay
        )
        self.play_button.setIcon(self.style().standardIcon(icon))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        event.accept()

    def shutdown(self) -> None:
        """Release multimedia resources and model workers exactly once."""
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        self.setEnabled(False)
        self.player.stop()
        self.player.setSource(QUrl())
        self.player.setAudioOutput(None)
        self.tts_worker.stop()
        self.sfx_worker.stop()
        self.current_audio = None

    def cleanup_session_files(self) -> None:
        """Delete previews after Qt has finished releasing media file handles."""
        if self._session_files_cleaned:
            return
        self._session_files_cleaned = True
        self.session_files.cleanup()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #10131a; color: #e9edf5; }
            QLabel { background: transparent; }
            QLabel#title { font-size: 28px; font-weight: 700; color: #ffffff; }
            QLabel#subtitle, QLabel#hint { color: #929bad; }
            QTabWidget::pane { border: 1px solid #2a3140; border-radius: 12px; top: -1px; }
            QTabBar::tab { background: #171c26; color: #9fa8ba; padding: 11px 22px; margin-right: 4px; border-radius: 8px 8px 0 0; }
            QTabBar::tab:selected { background: #242b39; color: #ffffff; }
            QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #171c26; border: 1px solid #30394b; border-radius: 7px;
                padding: 7px; selection-background-color: #7259ff;
            }
            QTextEdit:focus, QLineEdit:focus, QComboBox:focus { border-color: #806cff; }
            QPlainTextEdit#logs {
                background: #0c0f15; color: #aeb8ca; border: 1px solid #293244;
                border-radius: 7px; padding: 8px; font-family: monospace; font-size: 11px;
            }
            QPushButton { background: #242b39; border: 1px solid #384255; border-radius: 7px; padding: 8px 14px; }
            QPushButton:hover { background: #30394a; }
            QPushButton:disabled { color: #626a78; background: #1a1e27; }
            QPushButton#primary { background: #6d55e8; border: 0; color: white; font-weight: 600; padding: 11px 20px; }
            QPushButton#primary:hover { background: #806cff; }
            QPushButton#danger { background: #3a2229; border-color: #713744; color: #ffb8c3; font-weight: 600; }
            QPushButton#danger:hover { background: #542c36; }
            QFrame#panel, QFrame#player { background: #171c26; border: 1px solid #2a3140; border-radius: 10px; }
            QProgressBar {
                background: #202633; color: #e9edf5; border: 0; border-radius: 5px;
                min-height: 18px; text-align: center; font-size: 11px;
            }
            QProgressBar::chunk { background: #806cff; border-radius: 3px; }
            QToolTip { background: #242b39; color: white; border: 1px solid #384255; }
            """
        )
