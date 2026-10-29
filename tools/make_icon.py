#!/usr/bin/env python3
"""Draw the Keyboard Studio icon.

Writes `assets/keyboard.png` (window icon, README logo) and
`assets/keyboard.ico` (exe icon, multi-size: 16/24/32/48/64/128/256).

Run:  python tools/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPen,
                           QRadialGradient)

SIZES = (16, 24, 32, 48, 64, 128, 256)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

BG_TOP = QColor("#101b31")
BG_BOTTOM = QColor("#070c16")
KEY = QColor("#1d2c46")
KEY_EDGE = QColor("#2c4368")
LIT_A = QColor("#38bdf8")
LIT_B = QColor("#c084fc")


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = size / 256.0

    def r(*v):
        return QRectF(*(x * s for x in v))

    # rounded body
    body = r(6, 6, 244, 244)
    grad = QLinearGradient(body.topLeft(), body.bottomRight())
    grad.setColorAt(0.0, BG_TOP)
    grad.setColorAt(1.0, BG_BOTTOM)
    p.setPen(QPen(QColor(255, 255, 255, 26), max(1.0, 3 * s)))
    p.setBrush(grad)
    p.drawRoundedRect(body, 56 * s, 56 * s)

    # soft glow behind the lit key
    glow = QRadialGradient(QPointF(96 * s, 92 * s), 120 * s)
    glow.setColorAt(0.0, QColor(56, 189, 248, 90))
    glow.setColorAt(1.0, QColor(56, 189, 248, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(96 * s, 92 * s), 120 * s, 120 * s)

    # keys: three rows of four, plus a spacebar
    kw, kh = 44.0, 34.0
    gap = 9.0
    x0, y0 = 32.0, 66.0
    rad = 9.0
    lit = (1, 1)
    for row in range(3):
        for col in range(4):
            kr = r(x0 + col * (kw + gap), y0 + row * (kh + gap), kw, kh)
            if (col, row) == lit:
                kg = QLinearGradient(kr.topLeft(), kr.bottomRight())
                kg.setColorAt(0.0, LIT_A)
                kg.setColorAt(1.0, LIT_B)
                p.setPen(QPen(QColor(255, 255, 255, 90), max(1.0, 2 * s)))
                p.setBrush(kg)
            else:
                p.setPen(QPen(KEY_EDGE, max(1.0, 1.6 * s)))
                p.setBrush(KEY)
            p.drawRoundedRect(kr, rad * s, rad * s)

    bar_y = y0 + 3 * (kh + gap) + 2.0
    bar = r(32, bar_y, 4 * kw + 3 * gap, 26)
    p.setPen(QPen(KEY_EDGE, max(1.0, 1.6 * s)))
    p.setBrush(KEY)
    p.drawRoundedRect(bar, rad * s, rad * s)

    p.end()
    return img


def write_png(img: QImage, path: str):
    img.save(path, "PNG")


def write_ico(images: dict[int, QImage], path: str):
    """Minimal ICO writer: PNG-compressed frames (Vista+)."""
    blobs = {}
    for size, img in images.items():
        tmp = os.path.join(OUT, f".tmp-{size}.png")
        img.save(tmp, "PNG")
        with open(tmp, "rb") as f:
            blobs[size] = f.read()
        os.remove(tmp)

    count = len(blobs)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries, data = b"", b""
    for size in sorted(blobs):
        blob = blobs[size]
        entries += struct.pack("<BBBBHHII", size % 256, size % 256,
                               0, 0, 1, 32, len(blob), offset)
        data += blob
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(header + entries + data)


def main():
    os.makedirs(OUT, exist_ok=True)
    images = {size: draw(size) for size in SIZES}
    png = os.path.join(OUT, "keyboard.png")
    ico = os.path.join(OUT, "keyboard.ico")
    write_png(images[256], png)
    write_ico(images, ico)
    print("wrote", png)
    print("wrote", ico)
    return 0


if __name__ == "__main__":
    sys.exit(main())
