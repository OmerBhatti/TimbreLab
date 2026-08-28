from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from PyQt6.QtCore import QSettings, QTime, QUrl, Qt
from PyQt6.QtGui import QCloseEvent, QFont, QKeySequence, QShortcut
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QTableWidget,
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
from audio_playground.dialogue import parse_dialogue, voice_instruction_from_preset
from audio_playground.tag_text_edit import TagTextEdit
from audio_playground.voice_presets import VoicePresetStore
from audio_playground.worker_client import WorkerClient


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Audio Playground")
        self.resize(1180, 820)
        self.setMinimumSize(860, 640)
        self.preset_store = VoicePresetStore(QSettings())
        self.preset_store.ensure_defaults()
        self._shutdown_complete = False
        self._shutdown_in_progress = False
        self._session_files_cleaned = False
        self._changing_log_visibility = False
        self._logs_auto_opened = False
        self._preview_kind = "Audio"

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
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)

        title = QLabel("AI Audio Playground")
        title.setObjectName("title")
        subtitle = QLabel(
            "Emotional speech and multi-speaker dialogue with OmniVoice · "
            "Sound effects with AudioLDM"
        )
        subtitle.setObjectName("subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tts_tab(), "  Emotional TTS  ")
        self.tabs.addTab(self._build_dialogue_tab(), "  Dialogue  ")
        self.tabs.addTab(self._build_sfx_tab(), "  SFX && Effects  ")
        saved_tab = int(self.preset_store.settings.value("ui/active_tab", 0))
        if 0 <= saved_tab < self.tabs.count():
            self.tabs.setCurrentIndex(saved_tab)
        self.tabs.currentChanged.connect(
            lambda index: self.preset_store.settings.setValue("ui/active_tab", index)
        )
        outer.addWidget(self.tabs, 1)
        outer.addWidget(self._build_player())
        self.setCentralWidget(root)

        self.generate_shortcuts: list[QShortcut] = []
        for sequence in ("Ctrl+Return", "Meta+Return"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(self._generate_current_tab)
            self.generate_shortcuts.append(shortcut)

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
        layout.setContentsMargins(18, 16, 18, 10)
        layout.setSpacing(10)

        layout.addWidget(
            self._help_label(
                "Text to speak",
                "Enter the words to synthesize. Type [ to autocomplete expression cues inline.",
            )
        )
        self.tts_text = TagTextEdit(ALL_EXPRESSION_TAGS)
        self.tts_text.setPlaceholderText(
            "Use tags wherever delivery changes, for example: [sad] I miss you. [happy] You're home!"
        )
        self.tts_text.setPlainText(
            "[surprised] I can't believe we finally made it. [happy] This is amazing!"
        )
        self.tts_text.setMinimumHeight(110)
        self.tts_text.setMaximumHeight(210)
        self.tts_text.setToolTip(
            "Enter speech text and place expression tags where the delivery should change."
        )
        layout.addWidget(self.tts_text)

        preset_row = QHBoxLayout()
        preset_row.addWidget(
            self._help_label(
                "Voice preset",
                "Load a saved voice configuration or save the current controls under a name.",
            )
        )
        self.voice_preset = QComboBox()
        self.voice_preset.setMinimumWidth(190)
        self.voice_preset.setToolTip(
            "Choose a saved voice configuration to load its settings."
        )
        self.voice_preset.currentIndexChanged.connect(self._apply_selected_voice_preset)
        self.save_voice_preset = QPushButton("Save preset…")
        self.save_voice_preset.clicked.connect(self._save_voice_preset)
        self.delete_voice_preset = QPushButton("Delete")
        self.delete_voice_preset.clicked.connect(self._delete_voice_preset)
        preset_row.addWidget(self.voice_preset)
        preset_row.addWidget(self.save_voice_preset)
        preset_row.addWidget(self.delete_voice_preset)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        tag_row = QHBoxLayout()
        tag_row.addWidget(
            self._help_label(
                "Insert expression",
                "Insert an OmniVoice non-verbal cue at the current text cursor position.",
            )
        )
        self.emotion_tag = QComboBox()
        self.emotion_tag.setToolTip(
            "Choose an expression or non-verbal cue to insert into the speech text."
        )
        for tag in INLINE_EMOTION_TAGS:
            self.emotion_tag.addItem(tag.removeprefix("[").removesuffix("]").title(), tag)
        self.emotion_tag.insertSeparator(self.emotion_tag.count())
        for tag in OMNIVOICE_NONVERBAL_TAGS:
            label = tag.removeprefix("[").removesuffix("]").replace("-", " ").title()
            self.emotion_tag.addItem(label, tag)
        self.insert_emotion_tag = QPushButton("Insert tag")
        self.insert_emotion_tag.clicked.connect(self._insert_emotion_tag)
        tag_hint = QLabel("Tip: type [ in the script to search every expression.")
        tag_hint.setToolTip(
            "The dropdown includes friendly aliases and all native OmniVoice non-verbal cues."
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
        self.tts_seed = QSpinBox()
        self.tts_seed.setRange(0, 2_147_483_647)
        self.tts_seed.setValue(42)
        self._add_help_row(
            form,
            "Voice mode",
            self.tts_mode,
            "Design uses the selected voice attributes. Automatic lets OmniVoice choose a voice.",
        )
        self._add_help_row(
            form,
            "Speaking speed",
            self.speed,
            "Speech-rate multiplier: below 1.0 is slower and above 1.0 is faster.",
        )
        self._add_help_row(
            form,
            "Diffusion steps",
            self.steps,
            "More steps can improve speech quality but increase generation time.",
        )
        self._add_help_row(
            form,
            "Seed",
            self.tts_seed,
            "Random starting value. Reuse the same seed and settings for repeatable speech.",
        )
        controls.addLayout(form, 1)

        self.voice_stack = QStackedWidget()
        self.voice_stack.setMinimumHeight(185)
        self.voice_stack.setMaximumHeight(220)
        self.voice_stack.addWidget(self._build_design_panel())
        self.voice_stack.addWidget(self._build_auto_panel())
        controls.addWidget(self.voice_stack, 2)
        layout.addLayout(controls)
        layout.addStretch(1)

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
        self.tts_generate.setToolTip("Generate speech (Ctrl/Command + Enter)")
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
        self._add_help_row(
            form, "Gender", self.gender, "Guides the perceived gender of the designed voice."
        )
        self._add_help_row(
            form, "Age", self.age, "Guides the perceived age range of the designed voice."
        )
        self._add_help_row(
            form, "Pitch", self.pitch, "Controls the target vocal pitch range."
        )
        self._add_help_row(
            form, "Accent", self.accent, "Selects the requested English accent."
        )
        self._add_help_row(
            form,
            "Style",
            self.voice_style,
            "Normal uses regular delivery; whispering requests a quiet whispered delivery.",
        )
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
        layout.setContentsMargins(18, 16, 18, 10)
        layout.setSpacing(10)
        layout.addWidget(
            self._help_label(
                "Describe the sound",
                "Describe audible events, environment, realism, timing, and whether music is allowed.",
            )
        )
        self.sfx_prompt = QTextEdit()
        self.sfx_prompt.setPlainText(
            "A cinematic thunder crack followed by heavy rain on a metal rooftop, realistic, no music"
        )
        self.sfx_prompt.setPlaceholderText(
            "Example: Fast footsteps in a stone hallway, tense, distant echo, no music"
        )
        self.sfx_prompt.setMinimumHeight(160)
        self.sfx_prompt.setMaximumHeight(280)
        self.sfx_prompt.setToolTip(
            "Describe the sound, setting, timing, and qualities you want AudioLDM to generate."
        )
        layout.addWidget(self.sfx_prompt)

        form = QFormLayout()
        self.duration = QDoubleSpinBox()
        self.duration.setRange(1.0, 30.0)
        self.duration.setValue(5.0)
        self.duration.setSuffix(" seconds")
        self.duration.setToolTip("Longer clips require more memory and generation time.")
        self.guidance = QDoubleSpinBox()
        self.guidance.setRange(1.0, 5.0)
        self.guidance.setSingleStep(0.5)
        self.guidance.setValue(2.5)
        self.guidance.setToolTip(
            "Higher values follow the prompt more strictly; lower values allow more variety."
        )
        self.sfx_steps = QSpinBox()
        self.sfx_steps.setRange(8, 256)
        self.sfx_steps.setSingleStep(8)
        self.sfx_steps.setValue(128)
        self.sfx_steps.setToolTip("More steps can improve detail but take longer to render.")
        self.sfx_seed = QSpinBox()
        self.sfx_seed.setRange(0, 2_147_483_647)
        self.sfx_seed.setValue(42)
        self._add_help_row(
            form,
            "Duration",
            self.duration,
            "Length of the generated clip. Longer audio uses more memory and takes longer.",
        )
        self._add_help_row(
            form,
            "Prompt guidance",
            self.guidance,
            "How strictly AudioLDM follows the prompt. Lower values allow more variation.",
        )
        self._add_help_row(
            form,
            "Diffusion steps",
            self.sfx_steps,
            "Number of denoising passes. More steps may add detail but render more slowly.",
        )
        self._add_help_row(
            form,
            "Seed",
            self.sfx_seed,
            "Random starting value. Reuse the same seed and settings for repeatable effects.",
        )
        layout.addLayout(form)
        layout.addStretch(1)

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
        self.sfx_generate.setToolTip("Generate sound effect (Ctrl/Command + Enter)")
        self.sfx_generate.clicked.connect(self._generate_sfx)
        row.addWidget(self.sfx_generate)
        page_layout.addWidget(footer)
        return page

    def _build_dialogue_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(18, 12, 18, 10)
        page_layout.setSpacing(8)

        page_layout.addWidget(self._section_label("Speakers"))
        speaker_hint = QLabel(
            "Give each speaker a script name and assign one of your saved voice presets."
        )
        speaker_hint.setObjectName("hint")
        page_layout.addWidget(speaker_hint)

        self.dialogue_speakers = QTableWidget(0, 2)
        self.dialogue_speakers.setHorizontalHeaderLabels(["Speaker name", "Voice preset"])
        self.dialogue_speakers.horizontalHeaderItem(0).setToolTip(
            "Name used before the colon on each dialogue line."
        )
        self.dialogue_speakers.horizontalHeaderItem(1).setToolTip(
            "Saved voice configuration used to render this speaker."
        )
        self.dialogue_speakers.verticalHeader().setVisible(False)
        self.dialogue_speakers.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.dialogue_speakers.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        page_layout.addWidget(self.dialogue_speakers)

        speaker_buttons = QHBoxLayout()
        add_speaker = QPushButton("Add speaker")
        add_speaker.clicked.connect(self._add_dialogue_speaker)
        self.remove_dialogue_speaker = QPushButton("Remove selected")
        self.remove_dialogue_speaker.clicked.connect(self._remove_dialogue_speaker)
        speaker_buttons.addWidget(add_speaker)
        speaker_buttons.addWidget(self.remove_dialogue_speaker)
        speaker_buttons.addStretch()
        page_layout.addLayout(speaker_buttons)

        page_layout.addWidget(self._section_label("Dialogue script"))
        script_hint = QLabel(
            "Write one line at a time as Speaker: dialogue. Type [ for expression tags."
        )
        script_hint.setObjectName("hint")
        page_layout.addWidget(script_hint)
        self.dialogue_text = TagTextEdit(ALL_EXPRESSION_TAGS)
        self.dialogue_text.setPlaceholderText(
            "Arthur: [sigh] I wasn't expecting you.\nMaya: [question-en] Should I leave?"
        )
        self.dialogue_text.setPlainText(
            "Emma: Good morning, John. How are you today?\n"
            "John: I'm doing well, Emma. Thanks for asking.\n"
            "Emma: [questioning] Are you ready to begin?\n"
            "John: Absolutely. Let's get started."
        )
        self.dialogue_text.setMinimumHeight(120)
        self.dialogue_text.setToolTip(
            "Use one turn per line as Speaker: dialogue. Press Enter for speaker autocomplete "
            "or type [ for expression autocomplete."
        )
        page_layout.addWidget(self.dialogue_text, 1)

        footer = QHBoxLayout()
        dialogue_note = QLabel(
            "Lines are rendered in order with a short pause and combined into one preview."
        )
        dialogue_note.setObjectName("hint")
        dialogue_note.setWordWrap(True)
        footer.addWidget(dialogue_note, 1)
        footer.addWidget(
            self._help_label(
                "Seed",
                "Random starting value. Reuse the same seed, script, and presets for repeatable dialogue.",
            )
        )
        self.dialogue_seed = QSpinBox()
        self.dialogue_seed.setRange(0, 2_147_483_647)
        self.dialogue_seed.setValue(42)
        self.dialogue_seed.setToolTip(
            "Random starting value. Reuse the same seed, script, and presets for repeatable dialogue."
        )
        self.dialogue_seed.setMaximumWidth(130)
        footer.addWidget(self.dialogue_seed)
        self.dialogue_generate = QPushButton("Generate dialogue")
        self.dialogue_generate.setObjectName("primary")
        self.dialogue_generate.setToolTip("Generate dialogue (Ctrl/Command + Enter)")
        self.dialogue_generate.clicked.connect(self._generate_dialogue)
        footer.addWidget(self.dialogue_generate)
        page_layout.addLayout(footer)

        self._add_dialogue_speaker("Emma", "female-narrator")
        self._add_dialogue_speaker("John", "male-narrator")
        self._sync_dialogue_speaker_controls()
        return page

    def _build_player(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("player")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self.play_button.setEnabled(False)
        self.play_button.setFixedSize(48, 40)
        self.play_button.setToolTip("Play or pause preview")
        self.play_button.clicked.connect(self._toggle_playback)
        self.output_label = QLabel("No audio generated yet")
        self.output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.download_button = QPushButton("Download audio…")
        self.download_button.setEnabled(False)
        self.download_button.setToolTip("Save the temporary preview to a permanent WAV file")
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
        self.log_output.setFixedHeight(105)
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

    @staticmethod
    def _help_label(text: str, help_text: str) -> QLabel:
        label = QLabel(f"{text}  ⓘ")
        label.setObjectName("fieldHelp")
        label.setToolTip(help_text)
        label.setWhatsThis(help_text)
        return label

    @staticmethod
    def _add_help_row(
        form: QFormLayout, text: str, field: QWidget, help_text: str
    ) -> None:
        field.setToolTip(help_text)
        field.setWhatsThis(help_text)
        form.addRow(MainWindow._help_label(text, help_text), field)

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
        self.player.durationChanged.connect(self._duration_changed)

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
            "seed": self.tts_seed.value(),
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
        self._refresh_dialogue_preset_choices()

    def _refresh_dialogue_preset_choices(self) -> None:
        if not hasattr(self, "dialogue_speakers"):
            return
        preset_names = sorted(self.preset_store.all(), key=str.casefold)
        for row in range(self.dialogue_speakers.rowCount()):
            combo = self.dialogue_speakers.cellWidget(row, 1)
            if not isinstance(combo, QComboBox):
                continue
            selected = combo.currentData()
            combo.clear()
            combo.addItem("Select a preset…", None)
            for name in preset_names:
                combo.addItem(name, name)
            selected_index = combo.findData(selected)
            if selected_index >= 0:
                combo.setCurrentIndex(selected_index)

    def _add_dialogue_speaker(self, name: str = "", preset_name: str = "") -> None:
        row = self.dialogue_speakers.rowCount()
        self.dialogue_speakers.insertRow(row)
        name_edit = QLineEdit(name or f"Speaker {row + 1}")
        name_edit.setToolTip(
            "Name used before the colon on dialogue lines, for example Emma: Hello."
        )
        name_edit.textChanged.connect(self._refresh_dialogue_speaker_autocomplete)
        preset_combo = QComboBox()
        preset_combo.setToolTip("Saved voice configuration used to render this speaker.")
        self.dialogue_speakers.setCellWidget(row, 0, name_edit)
        self.dialogue_speakers.setCellWidget(row, 1, preset_combo)
        self.dialogue_speakers.setRowHeight(row, 36)
        self._refresh_dialogue_preset_choices()
        preset_index = preset_combo.findData(preset_name)
        if preset_index >= 0:
            preset_combo.setCurrentIndex(preset_index)
        self._refresh_dialogue_speaker_autocomplete()
        self._sync_dialogue_speaker_controls()

    def _remove_dialogue_speaker(self) -> None:
        if self.dialogue_speakers.rowCount() <= 2:
            self._sync_dialogue_speaker_controls()
            return
        selected_rows = self.dialogue_speakers.selectionModel().selectedRows()
        if selected_rows:
            self.dialogue_speakers.removeRow(selected_rows[0].row())
        elif self.dialogue_speakers.rowCount():
            self.dialogue_speakers.removeRow(self.dialogue_speakers.rowCount() - 1)
        self._refresh_dialogue_speaker_autocomplete()
        self._sync_dialogue_speaker_controls()

    def _refresh_dialogue_speaker_autocomplete(self) -> None:
        if not hasattr(self, "dialogue_text"):
            return
        names: list[str] = []
        for row in range(self.dialogue_speakers.rowCount()):
            name_edit = self.dialogue_speakers.cellWidget(row, 0)
            if isinstance(name_edit, QLineEdit) and name_edit.text().strip():
                names.append(name_edit.text().strip())
        self.dialogue_text.set_speaker_names(names)

    def _sync_dialogue_speaker_controls(self) -> None:
        if hasattr(self, "remove_dialogue_speaker"):
            self.remove_dialogue_speaker.setEnabled(
                self.dialogue_speakers.rowCount() > 2
            )
            visible_rows = min(max(self.dialogue_speakers.rowCount(), 2), 5)
            header_height = max(
                self.dialogue_speakers.horizontalHeader().sizeHint().height(), 28
            )
            self.dialogue_speakers.setFixedHeight(header_height + visible_rows * 36 + 8)

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
        self.tts_seed.setValue(int(config.get("seed", 42)))
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
                "seed": self.tts_seed.value(),
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
                "seed": self.sfx_seed.value(),
                "output_path": str(destination),
            }
        )

    def _generate_dialogue(self) -> None:
        presets = self.preset_store.all()
        speakers: dict[str, tuple[str, dict[str, object]]] = {}
        for row in range(self.dialogue_speakers.rowCount()):
            name_edit = self.dialogue_speakers.cellWidget(row, 0)
            preset_combo = self.dialogue_speakers.cellWidget(row, 1)
            if not isinstance(name_edit, QLineEdit) or not isinstance(preset_combo, QComboBox):
                continue
            name = name_edit.text().strip()
            preset_name = preset_combo.currentData()
            if not name:
                self._show_error(f"Speaker row {row + 1} needs a name.")
                return
            if ":" in name:
                self._show_error("Speaker names cannot contain a colon.")
                return
            if not preset_name or preset_name not in presets:
                self._show_error(f'Select a saved voice preset for "{name}".')
                return
            key = name.casefold()
            if key in speakers:
                self._show_error(f'Speaker name "{name}" is used more than once.')
                return
            speakers[key] = (name, presets[preset_name])

        if len(speakers) < 2:
            self._show_error("Dialogue requires at least two configured speakers.")
            return
        try:
            dialogue_lines = parse_dialogue(self.dialogue_text.toPlainText())
        except ValueError as exc:
            self._show_error(str(exc))
            return

        segments: list[dict[str, object]] = []
        for speaker_name, text in dialogue_lines:
            speaker = speakers.get(speaker_name.casefold())
            if speaker is None:
                self._show_error(
                    f'No speaker named "{speaker_name}" is configured above the script.'
                )
                return
            configured_name, config = speaker
            mode = "design" if config.get("mode") == "clone" else config.get("mode", "design")
            segments.append(
                {
                    "speaker": configured_name,
                    "text": normalize_emotion_tags(text),
                    "mode": mode,
                    "voice_instruction": voice_instruction_from_preset(config),
                    "speed": float(config.get("speed", 1.0)),
                    "steps": int(config.get("steps", 32)),
                }
            )

        destination = output_path(self.session_dir, "dialogue", "multi-speaker")
        self.tts_worker.generate(
            {
                "segments": segments,
                "seed": self.dialogue_seed.value(),
                "output_path": str(destination),
            }
        )

    def _generate_current_tab(self) -> None:
        if self.tts_worker.busy or self.sfx_worker.busy:
            return
        generators = (self._generate_tts, self._generate_dialogue, self._generate_sfx)
        index = self.tabs.currentIndex()
        if 0 <= index < len(generators):
            generators[index]()

    def _tts_busy(self, busy: bool) -> None:
        self._sync_busy_controls()

    def _sfx_busy(self, busy: bool) -> None:
        self._sync_busy_controls()

    def _sync_busy_controls(self) -> None:
        busy = self.tts_worker.busy or self.sfx_worker.busy
        self.tts_generate.setEnabled(not busy)
        self.sfx_generate.setEnabled(not busy)
        self.dialogue_generate.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.stop_button.setVisible(busy)
        if busy and not self.log_toggle.isChecked():
            self._set_logs_checked(True, automatic=True)
        elif not busy and self._logs_auto_opened:
            self._set_logs_checked(False, automatic=True)
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
        if not self._changing_log_visibility:
            self._logs_auto_opened = False
        self.log_output.setVisible(visible)
        self.log_toggle.setText("Hide logs" if visible else "Show logs")

    def _set_logs_checked(self, visible: bool, automatic: bool = False) -> None:
        self._changing_log_visibility = True
        try:
            self._logs_auto_opened = automatic and visible
            self.log_toggle.setChecked(visible)
        finally:
            self._changing_log_visibility = False

    def _append_log(self, message: str) -> None:
        clean_message = message.strip()
        if not clean_message:
            return
        timestamp = QTime.currentTime().toString("HH:mm:ss")
        self.log_output.appendPlainText(f"[{timestamp}] {clean_message}")

    def _audio_ready(self, filename: str) -> None:
        self.current_audio = Path(filename)
        self.player.setSource(QUrl.fromLocalFile(filename))
        prefix = self.current_audio.name.split("-", 1)[0]
        self._preview_kind = {
            "tts": "Speech",
            "dialogue": "Dialogue",
            "sfx": "Sound effect",
        }.get(prefix, "Audio")
        self.output_label.setText(f"{self._preview_kind} preview ready")
        self.output_label.setToolTip(
            f"{self.current_audio.name}\nTemporary preview — use Download audio to keep it."
        )
        self.play_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.status_label.setText("Generated. Preview is temporary until downloaded.")
        self.player.play()

    def _duration_changed(self, duration_ms: int) -> None:
        if self.current_audio is None or duration_ms <= 0:
            return
        self.output_label.setText(
            f"{self._preview_kind} preview · {duration_ms / 1000:.1f} seconds"
        )

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
        try:
            self.shutdown()
        except BaseException:
            # PyQt aborts the entire process when an exception escapes a virtual
            # event handler such as closeEvent, so closing must always contain it.
            traceback.print_exc(file=sys.stderr)
        finally:
            event.accept()

    def shutdown(self) -> None:
        """Release multimedia resources and model workers exactly once."""
        if self._shutdown_complete or self._shutdown_in_progress:
            return
        self._shutdown_in_progress = True
        try:
            self._run_shutdown_step("disabling the window", lambda: self.setEnabled(False))
            self._run_shutdown_step("stopping playback", self.player.stop)
            self._run_shutdown_step("detaching the media source", lambda: self.player.setSource(QUrl()))
            self._run_shutdown_step(
                "detaching the audio output", lambda: self.player.setAudioOutput(None)
            )
            self._stop_worker_for_shutdown("OmniVoice", self.tts_worker)
            self._stop_worker_for_shutdown("AudioLDM", self.sfx_worker)
            self.current_audio = None
        finally:
            self._shutdown_complete = True
            self._shutdown_in_progress = False

    @staticmethod
    def _run_shutdown_step(label: str, action) -> None:
        try:
            action()
        except BaseException:
            print(f"Shutdown warning while {label}:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def _stop_worker_for_shutdown(self, name: str, worker: WorkerClient) -> None:
        try:
            worker.stop()
        except BaseException:
            print(f"Shutdown warning while stopping {name}:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            # Preserve the invariant that no child QProcess is left alive when
            # Qt destroys its parent, even if the higher-level stop path failed.
            self._run_shutdown_step(f"force-stopping {name}", worker.process.kill)
            self._run_shutdown_step(
                f"waiting for {name} to exit",
                lambda: worker.process.waitForFinished(5000),
            )

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
            QLabel#title { font-size: 26px; font-weight: 700; color: #ffffff; }
            QLabel#subtitle, QLabel#hint { color: #929bad; }
            QLabel#fieldHelp { color: #dce2ed; font-weight: 600; }
            QTabWidget::pane { border: 1px solid #2a3140; border-radius: 12px; top: -1px; }
            QTabBar::tab { background: #171c26; color: #9fa8ba; padding: 10px 18px; margin-right: 4px; border-radius: 8px 8px 0 0; }
            QTabBar::tab:selected { background: #242b39; color: #ffffff; }
            QTabBar::tab:hover:!selected { background: #1d2330; color: #d6dbea; }
            QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #171c26; border: 1px solid #30394b; border-radius: 7px;
                padding: 7px; selection-background-color: #7259ff;
            }
            QTextEdit:focus, QLineEdit:focus, QComboBox:focus,
            QSpinBox:focus, QDoubleSpinBox:focus { border-color: #806cff; }
            QTableWidget {
                background: #11151d; border: 1px solid #293244; border-radius: 7px;
                gridline-color: #293244; selection-background-color: #252e40;
            }
            QHeaderView::section {
                background: #171c26; color: #cfd5e2; border: 0;
                border-bottom: 1px solid #30394b; padding: 6px; font-weight: 600;
            }
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
            QScrollBar:vertical {
                background: #11151d; width: 10px; margin: 0; border: 0;
            }
            QScrollBar::handle:vertical {
                background: #384255; min-height: 28px; border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QToolTip { background: #242b39; color: white; border: 1px solid #384255; }
            """
        )
