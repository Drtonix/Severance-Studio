"""Значок Severance Studio: расколотый круг (наследие Severance),
а в разрезе между половинами — нота: приложение не только делит,
но и пишет музыку.

Использование:
  drawicon.py out.png          — значок 1024×1024 с фоном
  drawicon.py out.png layer    — только рисунок на прозрачном фоне
"""
import math
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPolygonF)

S = 1024
BACK = QColor("#121216")
STOPS = ((0.0, "#ffb15c"), (0.34, "#ff5a7a"), (0.68, "#8a5cff"), (1.0, "#3cc8f0"))
TILT = math.radians(18)


def gradient(x0, y0, x1, y1):
    g = QLinearGradient(x0, y0, x1, y1)
    for at, c in STOPS:
        g.setColorAt(at, QColor(c))
    return g


def halves(cx, cy, r, gap):
    """Две половины круга, раздвинутые поперёк разреза на gap и сдвинутые вдоль него."""
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


def note_path(cx, cy, h):
    """Восьмая нота: крупная головка снизу, штиль вверх, широкий флажок."""
    path = QPainterPath()
    gw, gh = h * 0.38, h * 0.27          # головка
    sw = h * 0.085                        # толщина штиля
    gx, gy = cx - gw * 0.28, cy + h * 0.30  # центр головки
    stem_x = gx + gw / 2 - sw * 0.9
    top_y = cy - h * 0.46
    # штиль
    path.addRect(QRectF(stem_x, top_y, sw, gy - top_y))
    # флажок: широкая волна от верха штиля вправо и вниз
    flag = QPainterPath()
    flag.moveTo(stem_x + sw, top_y)
    flag.cubicTo(stem_x + sw + h * 0.42, top_y + h * 0.10,
                 stem_x + sw + h * 0.38, top_y + h * 0.38,
                 stem_x + sw + h * 0.06, top_y + h * 0.50)
    flag.cubicTo(stem_x + sw + h * 0.26, top_y + h * 0.40,
                 stem_x + sw + h * 0.28, top_y + h * 0.20,
                 stem_x + sw, top_y + h * 0.13)
    flag.closeSubpath()
    path.addPath(flag)
    # головка — повёрнутый эллипс
    head = QPainterPath()
    head.addEllipse(QPointF(gx, gy), gw / 2, gh / 2)
    from PySide6.QtGui import QTransform
    head = QTransform().translate(gx, gy).rotate(-20).translate(-gx, -gy).map(head)
    path.addPath(head)
    return path


def draw(path, layer=False):
    QGuiApplication.instance() or QGuiApplication([])
    img = QImage(S, S, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    if not layer:
        p.fillRect(img.rect(), QBrush(BACK))
    cx, cy, r = S / 2, S / 2, S * 0.36
    gap = S * 0.055
    # нота — в разрезе, цветом фона (выбита из половин) или градиентом:
    # рисуем половины, потом ноту цветом фона — она «прорезает» их.
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(gradient(cx - r, cy - r, cx + r, cy + r)))
    for half in halves(cx, cy, r, gap):
        p.drawPath(half)
    note = note_path(cx, cy, r * 1.15)
    if layer:
        # на прозрачном слое нота — тёмная, как фон приложения
        p.setBrush(QBrush(BACK))
        p.drawPath(note)
    else:
        p.setBrush(QBrush(BACK))
        p.drawPath(note)
    p.end()
    img.save(path)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "AppIcon-1024.png"
    draw(out, layer=len(sys.argv) > 2 and sys.argv[2] == "layer")
    print("ok", out)
