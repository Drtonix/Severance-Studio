"""Виджет пиано-ролла: показ, добавление, перемещение, растяжка и удаление нот."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from engine import Note

NOTE_H = 14          # высота полутона, px
PPS = 120.0          # пикселей в секунде при зуме 1.0
GRID = (0.25, 1.0, 4.0)  # доля, такт(условно), 4 такта
KEY_WIDTH = 56

BLACK = {1, 3, 6, 8, 10}


class PianoRoll(QWidget):
    notesChanged = Signal()

    def __init__(self):
        super().__init__()
        self.notes: list[Note] = []
        self.zoom = 1.0
        self.pitch_lo = 21
        self.pitch_hi = 108
        self.playhead = -1.0     # секунды, <0 — скрыта
        self._drag = None        # (index, mode, dx_semis, dt_sec, orig)
        self.setMinimumHeight(420)
        self.setMouseTracking(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------ данные

    def set_notes(self, notes: list[Note]):
        self.notes = notes
        self.playhead = -1.0
        if notes:
            pitches = [n.pitch for n in notes]
            self.pitch_lo = max(0, min(pitches) - 7)
            self.pitch_hi = min(127, max(pitches) + 7)
        self.update()

    def set_playhead(self, sec: float):
        self.playhead = sec
        self.update()

    def fit_content(self):
        """Размер виджета под всю дорожку — для полос прокрутки QScrollArea."""
        end = max((n.start + n.duration for n in self.notes), default=60.0) + 5
        rows = self.pitch_hi - self.pitch_lo + 1
        self.resize(int(self._x(end)), max(420, rows * NOTE_H))

    # ------------------------------------------------------------ геометрия

    def _x(self, sec: float) -> float:
        return KEY_WIDTH + sec * PPS * self.zoom

    def _sec(self, x: float) -> float:
        return max(0.0, (x - KEY_WIDTH) / (PPS * self.zoom))

    def _y(self, pitch: int) -> float:
        return (self.pitch_hi - pitch) * NOTE_H

    def _pitch(self, y: float) -> int:
        return max(0, min(127, int(self.pitch_hi - y / NOTE_H)))

    # ------------------------------------------------------------ отрисовка

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#17171b"))

        # строки тонов
        for pitch in range(self.pitch_lo, self.pitch_hi + 1):
            y = self._y(pitch)
            dark = pitch % 12 in BLACK
            p.fillRect(QRectF(KEY_WIDTH, y, self.width(), NOTE_H),
                       QColor("#1d1d23") if dark else QColor("#22222a"))
            p.setPen(QPen(QColor("#2c2c36")))
            p.drawLine(KEY_WIDTH, y, self.width(), y)
            # подписи клавиш
            if pitch % 12 == 0:
                p.setPen(QColor("#9a9aa5"))
                p.drawText(6, y + NOTE_H - 3, f"C{pitch // 12 - 1}")

        # сетка времени
        end_sec = self._sec(self.width())
        step = GRID[0]
        while PPS * self.zoom * step < 14:
            step *= 2
        t = 0.0
        while t <= end_sec:
            x = self._x(t)
            strong = abs(t % 1.0) < 1e-6
            p.setPen(QPen(QColor("#34343f" if strong else "#26262e")))
            p.drawLine(int(x), 0, int(x), self.height())
            if strong:
                p.setPen(QColor("#7a7a86"))
                p.drawText(int(x) + 3, 12, f"{t:.0f}s")
            t += step

        # ноты
        for n in self.notes:
            rect = QRectF(self._x(n.start), self._y(n.pitch) + 1,
                          max(3.0, n.duration * PPS * self.zoom), NOTE_H - 2)
            color = QColor("#4f9cf9") if n is not getattr(self, "_sel", None) \
                else QColor("#f9a74f")
            p.fillRect(rect, color)
            p.setPen(QPen(QColor("#0e0e12")))
            p.drawRect(rect)

        # плейхед
        if self.playhead >= 0:
            x = self._x(self.playhead)
            p.setPen(QPen(QColor("#ff5c5c"), 2))
            p.drawLine(int(x), 0, int(x), self.height())

        p.setPen(QPen(QColor("#3d3d48")))
        p.drawLine(KEY_WIDTH, 0, KEY_WIDTH, self.height())

    # ------------------------------------------------------------ мышь

    def _note_at(self, pos) -> int:
        """Индекс ноты под курсором или -1. Проверка зоны ресайза — в mousePress."""
        sec, pitch = self._sec(pos.x()), self._pitch(pos.y())
        for i, n in enumerate(self.notes):
            if n.pitch == pitch and n.start - 0.02 <= sec <= n.start + n.duration + 0.02:
                return i
        return -1

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            i = self._note_at(e.position())
            if i >= 0:
                del self.notes[i]
                self._sel = None
                self.notesChanged.emit()
                self.update()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        i = self._note_at(e.position())
        if i >= 0:
            n = self.notes[i]
            self._sel = n
            near_end = self._sec(e.position().x()) > n.start + n.duration - 0.05
            mode = "resize" if near_end else "move"
            self._drag = (i, mode,
                          n.pitch - self._pitch(e.position().y()),
                          n.start - self._sec(e.position().x()),
                          Note(n.start, n.duration, n.pitch, n.velocity))
        else:
            # новая нота: клик — старт, тянем — длина
            n = Note(start=self._sec(e.position().x()), duration=0.0,
                     pitch=self._pitch(e.position().y()), velocity=100)
            self.notes.append(n)
            self._sel = n
            self._drag = (len(self.notes) - 1, "resize", 0, 0, None)
        self.update()

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        i, mode, dp, dt, _orig = self._drag
        n = self.notes[i]
        if mode == "move":
            n.start = max(0.0, self._sec(e.position().x()) + dt)
            n.pitch = max(0, min(127, self._pitch(e.position().y()) + dp))
        else:
            n.duration = max(0.05, self._sec(e.position().x()) - n.start)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag:
            i, _m, _dp, _dt, orig = self._drag
            n = self.notes[i]
            if n.duration < 0.05:      # клик без протяжки — четверть секунды
                n.duration = 0.25
            self.notes.sort(key=lambda x: x.start)
            self._drag = None
            self.notesChanged.emit()
            self.update()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom = max(0.2, min(8.0,
                          self.zoom * (1.15 if e.angleDelta().y() > 0 else 1 / 1.15)))
            self.fit_content()
            self.update()
        else:
            super().wheelEvent(e)
