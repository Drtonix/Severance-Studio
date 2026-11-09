"""Severance Studio — разбор треков, пиано-ролл, вокалоиды, экспорт в Ableton.

Запуск из исходников: uv run python app.py
Оформление — в духе Severance: тёмная тема, фирменный градиент,
цвета дорожек из оригинального приложения.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal, QRectF, QPointF
from PySide6.QtGui import (QColor, QFont, QFontDatabase,
                           QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QDoubleSpinBox, QTabWidget, QVBoxLayout,
    QWidget,
)

import engine
import voices as voice_lab
from engine import Project, Track
from pianoroll import PianoRoll

# ---------------------------------------------------------------- оформление
# Палитра и градиент — те же, что в Severance.
BG = "#101013"
TEXT = "#ededf1"
MUTED = "#8d8d97"
FAINT = "#5b5b65"
SOFT = "#c4c4cc"
POPUP = "#1c1c21"
LINK = "#93a2ff"
DARK = "#16161a"
STOPS = ((0.0, "#ffb15c"), (0.34, "#ff5a7a"), (0.68, "#8a5cff"), (1.0, "#3cc8f0"))
GRADIENT = ("qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #ffb15c, stop:0.34 #ff5a7a, "
            "stop:0.68 #8a5cff, stop:1 #3cc8f0)")

STEM_TITLES = {
    "vocals": "Голос", "drums": "Барабаны", "bass": "Бас",
    "other": "Прочее", "guitar": "Гитара", "piano": "Клавишные",
}
# Цвета дорожек — из оригинального Severance (LANES).
STEM_COLORS = {
    "vocals": "#ff5a7a", "drums": "#a07cff", "bass": "#6f7dff",
    "guitar": "#45b4ff", "piano": "#3fd6d0", "other": "#8098bb",
}
WAVE_TITLES = {"saw": "Пила", "square": "Меандр",
               "triangle": "Треугольная", "sine": "Синус"}


def font_family() -> str:
    have = set(QFontDatabase.families())
    return next((f for f in ("Avenir Next", "Helvetica Neue", "Segoe UI")
                 if f in have), "Arial")


def _arrow_png(up: bool = False) -> str:
    """Маленький треугольник-стрелка для комбобоксов/спинбоксов (кэш в /tmp)."""
    name = "severance_studio_arrow_up.png" if up else "severance_studio_arrow.png"
    path = Path(tempfile.gettempdir()) / name
    if not path.exists():
        pm = QPixmap(10, 7)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(MUTED))
        pts = ([QPointF(0, 7), QPointF(10, 7), QPointF(5, 0)] if up
               else [QPointF(0, 0), QPointF(10, 0), QPointF(5, 7)])
        p.drawPolygon(QPolygonF(pts))
        p.end()
        pm.save(str(path))
    return str(path).replace("\\", "/")


def make_style() -> str:
    return f"""
* {{ outline: none; font-family: "{font_family()}"; }}
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 22px; font-weight: 600; }}
QLabel#sub {{ color: {MUTED}; font-size: 12px; }}
QLabel#h {{ font-size: 15px; font-weight: 600; }}
QLabel#dim {{ color: {MUTED}; }}

QFrame#group {{
    background: rgba(255,255,255,0.045);
    border-radius: 12px;
}}
QFrame#rule {{ background: rgba(255,255,255,0.07); max-height: 1px; }}

QPushButton {{
    background: rgba(255,255,255,0.06);
    border: none; border-radius: 10px;
    padding: 8px 16px;
}}
QPushButton:hover {{ background: rgba(255,255,255,0.10); }}
QPushButton:pressed {{ background: rgba(255,255,255,0.14); }}
QPushButton:disabled {{ color: {FAINT}; background: rgba(255,255,255,0.03); }}
QPushButton#primary {{
    background: {GRADIENT};
    color: {DARK}; font-weight: 600;
    border-radius: 12px; padding: 10px 22px;
}}
QPushButton#primary:hover {{ opacity: 0.92; }}
QPushButton#primary:disabled {{
    background: rgba(255,255,255,0.06); color: {FAINT};
}}

QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar {{ alignment: center; }}
QTabBar::tab {{
    background: transparent; color: {MUTED};
    padding: 8px 18px; margin: 2px;
    border-radius: 9px;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    background: rgba(255,255,255,0.08); color: {TEXT}; font-weight: 600;
}}

QPlainTextEdit, QLineEdit {{
    background: rgba(0,0,0,0.25);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px; padding: 8px;
    selection-background-color: rgba(255,90,122,0.45);
}}
QPlainTextEdit:focus, QLineEdit:focus {{
    border: 1px solid rgba(147,162,255,0.55);
}}
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {POPUP};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px; padding: 5px 10px;
    min-height: 18px;
}}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{
    subcontrol-origin: border; subcontrol-position: center right;
    width: 24px; border: none;
}}
QComboBox::down-arrow {{
    image: url("{_arrow_png()}");
    width: 10px; height: 7px;
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 2px; }}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 16px; border: none;
    background: rgba(255,255,255,0.05);
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-position: top right;
    border-top-right-radius: 7px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-position: bottom right;
    border-bottom-right-radius: 7px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_arrow_png(up=True)}");
    width: 8px; height: 6px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_arrow_png()}");
    width: 8px; height: 6px;
}}
QComboBox QAbstractItemView {{
    background: {POPUP}; border: 1px solid rgba(255,255,255,0.08);
    selection-background-color: rgba(255,255,255,0.10);
}}
QListWidget {{
    background: rgba(0,0,0,0.20);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px; padding: 6px;
}}
QListWidget::item {{
    border-radius: 8px; padding: 8px 10px;
}}
QListWidget::item:selected {{
    background: rgba(138,92,255,0.25);
}}
QListWidget::item:hover {{ background: rgba(255,255,255,0.06); }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.12); border-radius: 3px; min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: rgba(255,255,255,0.12); border-radius: 3px; min-width: 30px;
}}
"""


class OrbWidget(QWidget):
    """Маленький значок-шар в шапке."""

    def __init__(self, d: int = 34):
        super().__init__()
        self.setFixedSize(d, d)
        self._d = d

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = self._d
        grad = QLinearGradient(0, 0, d, d)
        for pos, col in STOPS:
            grad.setColorAt(pos, QColor(col))
        path = QPainterPath()
        path.addEllipse(QRectF(0.5, 0.5, d - 1, d - 1))
        p.setClipPath(path)
        p.fillRect(QRectF(0, 0, d, d), grad)
        p.save()
        p.translate(d / 2, d / 2)
        p.rotate(18)
        p.fillRect(QRectF(-d * 0.05, -d, d * 0.1, 2 * d), QColor(BG))
        p.restore()
        p.end()


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
        super().__init__("Перетащите сюда трек (wav, mp3)\nили нажмите для выбора")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self._normal = (f"border: 1.5px dashed rgba(255,255,255,0.16);"
                        f"border-radius: 12px; color: {MUTED};")
        self._hover = (f"border: 1.5px dashed rgba(147,162,255,0.7);"
                       f"border-radius: 12px; color: {TEXT};"
                       f"background: rgba(138,92,255,0.08);")
        self.setStyleSheet(self._normal)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet(self._hover)

    def dragLeaveEvent(self, _):
        self.setStyleSheet(self._normal)

    def dropEvent(self, e):
        self.setStyleSheet(self._normal)
        url = e.mimeData().urls()[0]
        if url.isLocalFile():
            self.fileDropped.emit(url.toLocalFile())

    def mousePressEvent(self, _):
        f, _ = QFileDialog.getOpenFileName(
            self, "Выбор трека", "", "Аудио (*.wav *.mp3 *.flac *.m4a)")
        if f:
            self.fileDropped.emit(f)


def _group(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(objectName="group")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    if title:
        lay.addWidget(QLabel(title, objectName="h"))
    return frame, lay


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Severance Studio")
        self.resize(1180, 800)
        self.project: Project | None = None
        self.current: Track | None = None
        self.thread: PipelineThread | None = None
        self._preview = Path(tempfile.gettempdir()) / "severance_studio_preview.wav"

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(
            lambda ms: self.roll.set_playhead(ms / 1000))

        root = QWidget(objectName="root")
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(20, 16, 20, 12)
        root_lay.setSpacing(12)

        # Шапка: шар + название.
        head = QHBoxLayout()
        head.addWidget(OrbWidget(34))
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(QLabel("Severance Studio", objectName="title"))
        col.addWidget(QLabel("разбор · пиано-ролл · вокалоиды · Ableton Live",
                             objectName="sub"))
        head.addLayout(col)
        head.addStretch()
        root_lay.addLayout(head)

        tabs = QTabWidget()
        self.tabs = tabs
        tabs.addTab(self._tracks_tab(), "Дорожки")
        tabs.addTab(self._roll_tab(), "Пиано-ролл")
        tabs.addTab(self._voices_tab(), "Голоса")
        tabs.addTab(self._export_tab(), "Экспорт в Ableton")
        root_lay.addWidget(tabs)
        self.setCentralWidget(root)

    # ------------------------------------------------------------ вкладки

    def _tracks_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        lay.setSpacing(12)
        drop = DropLabel()
        drop.fileDropped.connect(self._load_source)
        lay.addWidget(drop)

        frame, flay = _group("Дорожки проекта")
        self.stem_bar = QHBoxLayout()
        self.stem_bar.setSpacing(8)
        self.stem_bar.addStretch()
        flay.addLayout(self.stem_bar)
        lay.addWidget(frame)

        logf, llay = _group("Журнал")
        self.log = QPlainTextEdit(readOnly=True)
        llay.addWidget(self.log)
        lay.addWidget(logf, stretch=1)
        return w

    def _roll_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        lay.setSpacing(12)

        frame = QFrame(objectName="group")
        bar = QHBoxLayout(frame)
        bar.setContentsMargins(16, 10, 16, 10)
        bar.setSpacing(10)
        self.track_combo = QComboBox()
        self.track_combo.setMinimumWidth(220)
        self.track_combo.currentIndexChanged.connect(self._pick_track)
        bar.addWidget(QLabel("Дорожка", objectName="dim"))
        bar.addWidget(self.track_combo)

        self.wave_combo = QComboBox()
        self.wave_combo.addItems(WAVE_TITLES.values())
        bar.addWidget(QLabel("Звук", objectName="dim"))
        bar.addWidget(self.wave_combo)

        self.play_btn = QPushButton("▶  Играть", objectName="primary")
        self.play_btn.clicked.connect(self._play)
        bar.addWidget(self.play_btn)
        stop = QPushButton("■")
        stop.clicked.connect(self._stop)
        bar.addWidget(stop)
        bar.addStretch()
        lay.addWidget(frame)

        tune = QFrame(objectName="group")
        tlay = QHBoxLayout(tune)
        tlay.setContentsMargins(16, 10, 16, 10)
        tlay.setSpacing(10)
        tlay.addWidget(QLabel("Порог", objectName="dim"))
        self.onset_spin = QDoubleSpinBox(minimum=0.1, maximum=0.95,
                                         singleStep=0.05, value=0.6)
        tlay.addWidget(self.onset_spin)
        tlay.addWidget(QLabel("Мин. нота, мс", objectName="dim"))
        self.minlen_spin = QSpinBox(minimum=20, maximum=500, value=90)
        tlay.addWidget(self.minlen_spin)
        refilter = QPushButton("Пересчитать")
        refilter.clicked.connect(self._refilter)
        tlay.addWidget(refilter)
        tlay.addStretch()
        lay.addWidget(tune)

        self.roll = PianoRoll()
        scroll = QScrollArea()
        scroll.setWidget(self.roll)
        lay.addWidget(scroll, stretch=1)
        return w

    def _voices_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        lay.setSpacing(12)

        frame, flay = _group("Мои вокалоиды")
        self.voice_list = QListWidget()
        self._refresh_voices()
        flay.addWidget(self.voice_list)
        row = QHBoxLayout()
        listen = QPushButton("▶  Эталон")
        listen.clicked.connect(self._voice_listen)
        row.addWidget(listen)
        sing = QPushButton("🎤  Спеть вокал трека этим голосом",
                           objectName="primary")
        sing.clicked.connect(self._voice_sing)
        row.addWidget(sing)
        row.addStretch()
        flay.addLayout(row)
        lay.addWidget(frame, stretch=1)

        newf, nlay = _group("Новый вокалоид — опишите голос словами")
        self.voice_name = QLineEdit(placeholderText="Имя (например: Микуру)")
        nlay.addWidget(self.voice_name)
        self.voice_prompt = QPlainTextEdit(placeholderText=(
            "Промпт: «высокий синтетический голос девочки-робота, "
            "звонкий, слегка металлический…»"))
        self.voice_prompt.setMaximumHeight(64)
        nlay.addWidget(self.voice_prompt)
        row2 = QHBoxLayout()
        self.voice_lang = QComboBox()
        self.voice_lang.addItems(["Русский", "English"])
        row2.addWidget(self.voice_lang)
        create = QPushButton("Создать голос", objectName="primary")
        create.clicked.connect(self._voice_create)
        row2.addWidget(create)
        row2.addStretch()
        nlay.addLayout(row2)
        lay.addWidget(newf)
        return w

    def _export_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        lay.setSpacing(12)

        frame, flay = _group("Проект Ableton Live")
        row = QHBoxLayout()
        row.addWidget(QLabel("Темп, BPM", objectName="dim"))
        self.bpm_spin = QDoubleSpinBox(minimum=40, maximum=300,
                                       singleStep=0.5, value=120)
        row.addWidget(self.bpm_spin)
        row.addStretch()
        flay.addLayout(row)
        row2 = QHBoxLayout()
        open_btn = QPushButton("Экспорт и открыть в Ableton",
                               objectName="primary")
        open_btn.clicked.connect(lambda: self._export(open_live=True))
        row2.addWidget(open_btn)
        btn = QPushButton("Только экспорт в папку…")
        btn.clicked.connect(lambda: self._export(open_live=False))
        row2.addWidget(btn)
        row2.addStretch()
        flay.addLayout(row2)
        flay.addWidget(QLabel(
            "Собирается .als: аудиодорожки со стемами, "
            "MIDI-дорожки с нотами, темп проекта.", objectName="dim"))
        lay.addWidget(frame)
        lay.addStretch()
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
        self.tabs.setCurrentIndex(0)   # журнал на первой вкладке
        self.thread.start()

    # ------------------------------------------------------------ логика

    def _stem_chips(self):
        while self.stem_bar.count() > 1:
            item = self.stem_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.project:
            return
        for i, t in enumerate(self.project.tracks):
            color = STEM_COLORS.get(t.stem, "#8098bb")
            b = QPushButton(
                f"{STEM_TITLES.get(t.stem, t.stem)} · {len(t.notes)}")
            b.setStyleSheet(
                f"QPushButton {{ background: rgba(255,255,255,0.05);"
                f" border-left: 3px solid {color}; border-radius: 8px;"
                f" padding: 6px 12px; }}"
                f"QPushButton:hover {{ background: rgba(255,255,255,0.10); }}")
            b.clicked.connect(lambda _=False, idx=i: self._goto_track(idx))
            self.stem_bar.insertWidget(self.stem_bar.count() - 1, b)

    def _goto_track(self, i: int):
        self.track_combo.setCurrentIndex(i)
        self.tabs.setCurrentIndex(1)

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
        self._stem_chips()
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
    app.setStyle("Fusion")  # macOS-стиль игнорирует половину QSS
    app.setStyleSheet(make_style())
    # Иконку окна не ставим вручную: на macOS Dock и Launchpad
    # берут AppIcon.icns из бандла и сами применяют маску-скругление.
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
