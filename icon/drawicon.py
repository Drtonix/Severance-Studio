"""Значок Severance Studio — в фирменной ДНК Severance: тот же тёмный
квадрат и градиентный круг, расколотый надвое. В разрезе — три ноты
пиано-ролла: Studio добавляет к разбору ноты и вокал.

Запуск (Qt-плагины находятся в venv оригинального Severance):
    /Users/tonix/Developer/severance/.venv/bin/python drawicon.py
Результат: AppIcon-1024.png, AppIcon.iconset, AppIcon.icns.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPolygonF)

OUT = Path(__file__).parent
BACK = QColor("#121216")
STOPS = ((0.0, "#ffb15c"), (0.34, "#ff5a7a"), (0.68, "#8a5cff"), (1.0, "#3cc8f0"))
TILT = math.radians(18)
NOTE = QColor("#ededf1")


def gradient(x0, y0, x1, y1):
    g = QLinearGradient(x0, y0, x1, y1)
    for at, c in STOPS:
        g.setColorAt(at, QColor(c))
    return g


def halves(cx, cy, r, gap):
    """Две половины круга, раздвинутые поперёк и сдвинутые вдоль разреза."""
    dx, dy = math.sin(TILT), -math.cos(TILT)
    nx, ny = math.cos(TILT), math.sin(TILT)
    big = r * 3
    out = []
    for side in (-1, 1):
        plane = QPolygonF([
            QPointF(cx + dx * big, cy + dy * big),
            QPointF(cx + dx * big + nx * big * side, cy + dy * big + ny * big * side),
            QPointF(cx - dx * big + nx * big * side, cy - dy * big + ny * big * side),
            QPointF(cx - dx * big, cy - dy * big),
        ])
        cut = QPainterPath()
        cut.addPolygon(plane)
        disc = QPainterPath()
        disc.addEllipse(QPointF(cx, cy), r, r)
        half = disc.intersected(cut)
        shift = QPointF(nx * gap * side - dx * gap * 0.55 * side,
                        ny * gap * side - dy * gap * 0.55 * side)
        out.append(half.translated(shift))
    return out


def render(S: int) -> QImage:
    QGuiApplication.instance() or QGuiApplication([])
    img = QImage(S, S, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(QRectF(0, 0, S, S), BACK)

    cx = cy = S / 2
    r = S * 0.30
    gap = S * 0.075          # пошире, чем у оригинала: в разрезе ноты
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gradient(cx - r, cy - r, cx + r, cy + r)))
    for half in halves(cx, cy, r, gap):
        p.drawPath(half)

    # Ноты пиано-ролла в разрезе: три скруглённых бара разной длины,
    # параллельных разрезу. Толщина и радиусы — от S, читаются на 64 px.
    p.save()
    disc = QPainterPath()
    disc.addEllipse(QPointF(cx, cy), r, r)
    p.setClipPath(disc)
    p.translate(cx, cy)
    p.rotate(18)
    bar_w = S * 0.052                      # толщина ноты (поперёк разреза)
    radius = bar_w * 0.5
    p.setBrush(QBrush(NOTE))
    for y0, length in ((-0.220, 0.140), (-0.030, 0.200), (0.220, 0.120)):
        rect = QRectF(-bar_w / 2, S * y0, bar_w, S * length)
        p.drawRoundedRect(rect, radius, radius)
    p.restore()

    p.end()
    return img


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    png = OUT / "AppIcon-1024.png"
    render(1024).save(str(png))
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
