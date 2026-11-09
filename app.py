"""Severance Studio — каркас приложения (этап 1).

Вкладки: Дорожки (стемы), Пиано-ролл, Голоса, Экспорт в Ableton.
Запуск из исходников: uv run python app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QPlainTextEdit,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

STYLE = """
QWidget { background: #1b1b1f; color: #e8e8ec; font-size: 14px; }
QPushButton { background: #2d2d35; border: 1px solid #3d3d48;
    border-radius: 8px; padding: 8px 16px; }
QPushButton:hover { background: #3a3a45; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #232329; padding: 8px 20px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #2d2d35; }
QPlainTextEdit { background: #141418; border: 1px solid #2d2d35;
    border-radius: 8px; }
"""


class DropLabel(QLabel):
    """Поле «перетащи трек сюда»."""

    def __init__(self, on_file):
        super().__init__("Перетащите сюда трек или вставьте ссылку")
        self.on_file = on_file
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setStyleSheet("border: 2px dashed #3d3d48; border-radius: 12px;")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        url = e.mimeData().urls()[0]
        self.on_file(url.toLocalFile() if url.isLocalFile() else url.toString())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Severance Studio")
        self.resize(1100, 720)
        self.project = None

        tabs = QTabWidget()
        tabs.addTab(self._tracks_tab(), "Дорожки")
        tabs.addTab(self._pianoroll_tab(), "Пиано-ролл")
        tabs.addTab(self._voices_tab(), "Голоса")
        tabs.addTab(self._export_tab(), "Экспорт в Ableton")
        self.setCentralWidget(tabs)

    def _tracks_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(DropLabel(self._load_source))
        self.log = QPlainTextEdit(readOnly=True)
        lay.addWidget(self.log)
        return w

    def _pianoroll_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Пиано-ролл дорожки появится здесь — этап 2."))
        return w

    def _voices_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(
            "Голосовая лаборатория — этап 4.\n"
            "Промпт → голос → пение на мелодию трека (RU/EN)."))
        return w

    def _export_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        btn = QPushButton("Экспортировать проект для Ableton…")
        btn.clicked.connect(self._export)
        lay.addWidget(btn)
        lay.addStretch()
        return w

    def _load_source(self, src: str):
        self.log.appendPlainText(f"Источник: {src}\n(разбор подключим следом)")

    def _export(self):
        folder = QFileDialog.getExistingDirectory(self, "Куда экспортировать")
        if folder:
            self.log.appendPlainText(f"Экспорт в {folder} — этап 3.")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
