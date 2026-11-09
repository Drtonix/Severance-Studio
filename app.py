"""Severance Studio — этап 2: пиано-ролл с редактированием и предпрослушкой.

Запуск из исходников: uv run python app.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QDoubleSpinBox, QTabWidget, QVBoxLayout,
    QWidget,
)

import engine
import voices as voice_lab
from engine import Project, Track
from pianoroll import PianoRoll

STYLE = """
QWidget { background: #1b1b1f; color: #e8e8ec; font-size: 14px; }
QPushButton { background: #2d2d35; border: 1px solid #3d3d48;
    border-radius: 8px; padding: 8px 16px; }
QPushButton:hover { background: #3a3a45; }
QPushButton:disabled { color: #666670; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #232329; padding: 8px 20px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #2d2d35; }
QPlainTextEdit { background: #141418; border: 1px solid #2d2d35;
    border-radius: 8px; }
QComboBox, QSpinBox, QDoubleSpinBox { background: #2d2d35;
    border: 1px solid #3d3d48; border-radius: 6px; padding: 4px 8px; }
"""

STEM_TITLES = {
    "vocals": "Голос", "drums": "Барабаны", "bass": "Бас",
    "other": "Прочее", "guitar": "Гитара", "piano": "Клавишные",
}
WAVE_TITLES = {"saw": "Пила", "square": "Меандр",
               "triangle": "Треугольная", "sine": "Синус"}


class PipelineThread(QThread):
    """Фон: трек → стемы → ноты."""
    progress = Signal(str)
    done = Signal(object)

    def __init__(self, src: Path, work: Path):
        super().__init__()
        self.src, self.work = src, work

    def run(self):
        try:
            self.progress.emit("Разбор на дорожки (demucs-mlx)…")
            stem_files = engine.stems(self.src, self.work / "stems")
            self.progress.emit("Определение темпа (beat-this)…")
            bpm = engine.detect_bpm(next(iter(stem_files.values())))
            project = Project(name=self.src.stem, source=self.src, bpm=bpm)
            self.progress.emit(f"Темп: {bpm} BPM")
            for stem, wav in stem_files.items():
                self.progress.emit(f"Ноты: {STEM_TITLES.get(stem, stem)}…")
                notes = engine.transcribe(wav)
                project.tracks.append(Track(stem=stem, audio=wav, notes=notes))
            self.done.emit(project)
        except Exception as e:  # noqa: BLE001 — показать в логе любой сбой
            self.progress.emit(f"Ошибка: {e}")
            self.done.emit(None)


class VoiceThread(QThread):
    """Фон: создание голоса по промпту или конверсия вокала."""
    progress = Signal(str)
    done = Signal(object)

    def __init__(self, mode: str, **kw):
        super().__init__()
        self.mode, self.kw = mode, kw

    def run(self):
        try:
            if self.mode == "design":
                v = voice_lab.design_voice(
                    self.kw["name"], self.kw["prompt"], self.kw["lang"],
                    progress=self.progress.emit)
                self.done.emit(v)
            else:
                out = voice_lab.convert_voice(
                    self.kw["source"], self.kw["voice"], self.kw["out"],
                    progress=self.progress.emit)
                self.done.emit(out)
        except Exception as e:  # noqa: BLE001
            self.progress.emit(f"Ошибка: {e}")
            self.done.emit(None)


class DropLabel(QLabel):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__("Перетащите сюда трек (wav, mp3) или нажмите для выбора")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self.setStyleSheet("border: 2px dashed #3d3d48; border-radius: 12px;")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        url = e.mimeData().urls()[0]
        if url.isLocalFile():
            self.fileDropped.emit(url.toLocalFile())

    def mousePressEvent(self, _):
        f, _ = QFileDialog.getOpenFileName(
            self, "Выбор трека", "", "Аудио (*.wav *.mp3 *.flac *.m4a)")
        if f:
            self.fileDropped.emit(f)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Severance Studio")
        self.resize(1200, 780)
        self.project: Project | None = None
        self.current: Track | None = None
        self.thread: PipelineThread | None = None
        self._preview = Path(tempfile.gettempdir()) / "severance_studio_preview.wav"

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(
            lambda ms: self.roll.set_playhead(ms / 1000))

        tabs = QTabWidget()
        self.tabs = tabs
        tabs.addTab(self._tracks_tab(), "Дорожки")
        tabs.addTab(self._roll_tab(), "Пиано-ролл")
        tabs.addTab(self._voices_tab(), "Голоса")
        tabs.addTab(self._export_tab(), "Экспорт в Ableton")
        self.setCentralWidget(tabs)

    # ------------------------------------------------------------ вкладки

    def _tracks_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        drop = DropLabel()
        drop.fileDropped.connect(self._load_source)
        lay.addWidget(drop)
        self.stem_bar = QHBoxLayout()
        lay.addLayout(self.stem_bar)
        self.log = QPlainTextEdit(readOnly=True)
        lay.addWidget(self.log)
        return w

    def _roll_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        bar = QHBoxLayout()
        self.track_combo = QComboBox()
        self.track_combo.currentIndexChanged.connect(self._pick_track)
        bar.addWidget(QLabel("Дорожка:"))
        bar.addWidget(self.track_combo)

        self.wave_combo = QComboBox()
        self.wave_combo.addItems(WAVE_TITLES.values())
        bar.addWidget(QLabel("Звук:"))
        bar.addWidget(self.wave_combo)

        self.play_btn = QPushButton("▶ Играть")
        self.play_btn.clicked.connect(self._play)
        bar.addWidget(self.play_btn)
        stop = QPushButton("■")
        stop.clicked.connect(self._stop)
        bar.addWidget(stop)

        bar.addSpacing(20)
        bar.addWidget(QLabel("Порог:"))
        self.onset_spin = QDoubleSpinBox(minimum=0.1, maximum=0.95,
                                         singleStep=0.05, value=0.6)
        bar.addWidget(self.onset_spin)
        bar.addWidget(QLabel("Мин. нота, мс:"))
        self.minlen_spin = QSpinBox(minimum=20, maximum=500, value=90)
        bar.addWidget(self.minlen_spin)
        refilter = QPushButton("Пересчитать")
        refilter.clicked.connect(self._refilter)
        bar.addWidget(refilter)
        bar.addStretch()
        lay.addLayout(bar)

        self.roll = PianoRoll()
        scroll = QScrollArea()
        scroll.setWidget(self.roll)
        lay.addWidget(scroll)
        return w

    def _voices_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        lay.addWidget(QLabel("Мои вокалоиды:"))
        self.voice_list = QListWidget()
        self._refresh_voices()
        lay.addWidget(self.voice_list)

        row = QHBoxLayout()
        listen = QPushButton("▶ Эталон")
        listen.clicked.connect(self._voice_listen)
        row.addWidget(listen)
        sing = QPushButton("🎤 Спеть вокал трека этим голосом")
        sing.clicked.connect(self._voice_sing)
        row.addWidget(sing)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(QLabel("Новый вокалоид — опишите голос словами:"))
        self.voice_name = QLineEdit(placeholderText="Имя (например: Микуру)")
        lay.addWidget(self.voice_name)
        self.voice_prompt = QPlainTextEdit(placeholderText=(
            "Промпт: «высокий синтетический голос девочки-робота, "
            "звонкий, слегка металлический…»"))
        self.voice_prompt.setMaximumHeight(70)
        lay.addWidget(self.voice_prompt)
        row2 = QHBoxLayout()
        self.voice_lang = QComboBox()
        self.voice_lang.addItems(["Русский", "English"])
        row2.addWidget(self.voice_lang)
        create = QPushButton("Создать голос")
        create.clicked.connect(self._voice_create)
        row2.addWidget(create)
        row2.addStretch()
        lay.addLayout(row2)
        return w

    # ------------------------------------------------------------ голоса

    def _refresh_voices(self):
        self.voice_list.clear()
        for v in voice_lab.list_voices():
            self.voice_list.addItem(f"{v.name} — {v.prompt[:50]}…")

    def _selected_voice(self):
        i = self.voice_list.currentRow()
        vs = voice_lab.list_voices()
        return vs[i] if 0 <= i < len(vs) else None

    def _voice_listen(self):
        v = self._selected_voice()
        if v:
            ref = max(v.refs, key=lambda p: p.stat().st_size)
            self.player.setSource(QUrl.fromLocalFile(str(ref)))
            self.player.play()

    def _voice_create(self):
        name = self.voice_name.text().strip()
        prompt = self.voice_prompt.toPlainText().strip()
        if not name or not prompt:
            self.log.appendPlainText("Введите имя и промпт голоса.")
            return
        lang = "ru" if self.voice_lang.currentIndex() == 0 else "en"
        self._run_voice_thread("design", name=name, prompt=prompt, lang=lang)

    def _voice_sing(self):
        v = self._selected_voice()
        if not v:
            self.log.appendPlainText("Выберите голос в списке.")
            return
        if not self.project:
            self.log.appendPlainText("Сначала загрузите трек.")
            return
        vocal = next((t for t in self.project.tracks if t.stem == "vocals"),
                     None)
        if not vocal or not vocal.audio:
            self.log.appendPlainText("В проекте нет дорожки vocals.")
            return
        out = vocal.audio.with_name(
            f"{vocal.audio.stem} — {v.name}.wav")
        self._run_voice_thread("convert", source=vocal.audio, voice=v, out=out)

    def _run_voice_thread(self, mode: str, **kw):
        if self.thread and self.thread.isRunning():
            return
        self.thread = VoiceThread(mode, **kw)
        self.thread.progress.connect(self.log.appendPlainText)

        def finished(result):
            if mode == "design" and result:
                self._refresh_voices()
                self.log.appendPlainText(f"Голос «{result.name}» создан.")
            elif result:
                self.log.appendPlainText(f"Готово: {result}")

        self.thread.done.connect(finished)
        self.tabs.setCurrentIndex(0)   # лог на первой вкладке
        self.thread.start()

    def _export_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("Темп, BPM:"))
        self.bpm_spin = QDoubleSpinBox(minimum=40, maximum=300,
                                       singleStep=0.5, value=120)
        row.addWidget(self.bpm_spin)
        self.open_check = QPushButton("Экспорт и открыть в Ableton")
        self.open_check.clicked.connect(lambda: self._export(open_live=True))
        row.addWidget(self.open_check)
        btn = QPushButton("Только экспорт в папку…")
        btn.clicked.connect(lambda: self._export(open_live=False))
        row.addWidget(btn)
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(QLabel(
            "Собирается .als: аудиодорожки со стемами, MIDI-дорожки "
            "с нотами, темп проекта."))
        lay.addStretch()
        return w

    # ------------------------------------------------------------ логика

    def _load_source(self, src: str):
        if self.thread and self.thread.isRunning():
            return
        self.log.appendPlainText(f"Источник: {src}")
        work = Path("output") / Path(src).stem
        self.thread = PipelineThread(Path(src), work)
        self.thread.progress.connect(self.log.appendPlainText)
        self.thread.done.connect(self._pipeline_done)
        self.thread.start()

    def _pipeline_done(self, project: Project | None):
        if not project:
            return
        self.project = project
        self._pipeline_bpm(project)
        self.track_combo.clear()
        for t in project.tracks:
            self.track_combo.addItem(
                f"{STEM_TITLES.get(t.stem, t.stem)} ({len(t.notes)} нот)")
        self.log.appendPlainText(
            f"Готово: {len(project.tracks)} дорожек. Откройте «Пиано-ролл».")
        self.tabs.setCurrentIndex(1)

    def _pick_track(self, i: int):
        if not self.project or i < 0 or i >= len(self.project.tracks):
            return
        self.current = self.project.tracks[i]
        self.roll.set_notes(self.current.notes)
        self.roll.fit_content()

    def _refilter(self):
        if not self.current:
            return
        t = self.current
        self.log.appendPlainText(f"Пересчёт нот: {STEM_TITLES.get(t.stem)}…")
        t.notes = engine.transcribe(
            t.audio, onset=self.onset_spin.value(),
            min_len_ms=float(self.minlen_spin.value()))
        self.roll.set_notes(t.notes)
        self.roll.fit_content()
        self.log.appendPlainText(f"Нот после фильтров: {len(t.notes)}")

    def _play(self):
        if not self.current or not self.current.notes:
            return
        wave = [k for k, v in WAVE_TITLES.items()
                if v == self.wave_combo.currentText()][0]
        engine.render_preview(self.current.notes, self._preview, waveform=wave)
        self.player.setSource(QUrl.fromLocalFile(str(self._preview)))
        self.player.play()

    def _stop(self):
        self.player.stop()
        self.roll.set_playhead(-1)

    def _export(self, open_live: bool = False):
        if not self.project:
            self.log.appendPlainText("Сначала загрузите трек.")
            return
        self.project.bpm = self.bpm_spin.value()
        folder = QFileDialog.getExistingDirectory(self, "Куда экспортировать")
        if folder:
            als = engine.export_live(
                self.project,
                Path(folder) / f"{self.project.name} — Severance Studio",
                open_live=open_live)
            self.log.appendPlainText(f"Проект Ableton: {als}")

    def _pipeline_bpm(self, project: Project):
        if project.bpm:
            self.bpm_spin.setValue(project.bpm)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
