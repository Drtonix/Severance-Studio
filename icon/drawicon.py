"""Иконка Severance Studio: фирменный градиент Severance, диагональный
разрез (как на оригинальном значке), внутри разреза — клавиши пианино.

Запуск (Qt-плагины находятся в venv оригинального Severance):
    /Users/tonix/Developer/severance/.venv/bin/python drawicon.py
Результат: AppIcon-1024.png, iconset, AppIcon.icns (если есть iconutil).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath)

OUT = Path(__file__).parent
STOPS = ((0.0, "#ffb15c"), (0.34, "#ff5a7a"), (0.68, "#8a5cff"), (1.0, "#3cc8f0"))
DARK = "#101013"


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size

    # Скруглённый квадрат с фирменным градиентом.
    grad = QLinearGradient(0, 0, s, s)
    for pos, col in STOPS:
        grad.setColorAt(pos, QColor(col))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, s, s), s * 0.225, s * 0.225)
    p.setClipPath(path)
    p.fillRect(QRectF(0, 0, s, s), grad)

    # Диагональный разрез под 18°.
    p.save()
    p.translate(s / 2, s / 2)
    p.rotate(18)
    cut = s * 0.13
    p.fillRect(QRectF(-cut / 2, -s, cut, 2 * s), QColor(DARK))

    # Клавиши внутри разреза: белые и чёрные, как фрагмент пиано-ролла.
    key_w = cut * 0.66
    x0 = -key_w / 2
    y = -s * 0.52
    whites = (0.30, 0.24, 0.34, 0.22, 0.28, 0.26)
    for i, h in enumerate(whites):
        p.fillRect(QRectF(x0, y, key_w, s * h), QColor(237, 237, 241))
        y += s * (h + 0.025)
    # Чёрные клавиши поверх, со сдвигом.
    y = -s * 0.52 + s * 0.20
    for h in (0.16, 0.13, 0.17, 0.12, 0.15):
        p.fillRect(QRectF(x0, y, key_w * 0.62, s * h), QColor(DARK))
        y += s * (h + 0.135)
    p.restore()

    # Тонкая светлая кромка по нижнему краю разреза — «блик».
    p.save()
    p.translate(s / 2, s / 2)
    p.rotate(18)
    p.setClipRect(QRectF(-s, -s, 2 * s, 2 * s))
    pen_col = QColor(255, 255, 255, 46)
    p.fillRect(QRectF(cut / 2, -s, s * 0.012, 2 * s), pen_col)
    p.restore()

    p.end()
    return img


def main() -> None:
    app = QGuiApplication(sys.argv)
    img = render(1024)
    png = OUT / "AppIcon-1024.png"
    img.save(str(png))
    print("png:", png)

    iconset = OUT / "AppIcon.iconset"
    iconset.mkdir(exist_ok=True)
    for side in (16, 32, 64, 128, 256, 512):
        for scale in (1, 2):
            px = side * scale
            if px > 1024:
                continue
            name = (f"icon_{side}x{side}.png" if scale == 1
                    else f"icon_{side}x{side}@2x.png")
            render(px).save(str(iconset / name))
    icns = OUT / "AppIcon.icns"
    r = subprocess.run(["iconutil", "-c", "icns", str(iconset),
                        "-o", str(icns)], capture_output=True, text=True)
    print("icns:", icns if r.returncode == 0 else r.stderr)


if __name__ == "__main__":
    main()
