#!/usr/bin/env python3
"""Keyboard Studio for Windows — lighting effects for the CASUE USB keyboard.

Same 14 effects as the Linux version. The board has one lighting zone and no
colour channel: every effect is a pattern of the single ScrollLock LED bit,
which is what powers the strip. Colour and the wave/twinkle animations come
from the keyboard's own firmware and cannot be driven from software.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import random
import sys
import time
from ctypes import wintypes as wt

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QGridLayout,
                               QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

IS_WINDOWS = sys.platform == "win32"

try:
    import hidwin
except Exception as _exc:                     # non-Windows / import problem
    hidwin = None
    HID_IMPORT_ERROR = _exc
else:
    HID_IMPORT_ERROR = None

try:
    import psutil
except Exception:
    psutil = None

STATE_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"),
                         "KeyboardStudio")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

EFFECTS = [
    ("steady", "Steady", "Always on"),
    ("off", "Off", "Light off"),
    ("slow", "Slow blink", "4 s on / 4 s off"),
    ("pulse", "Pulse", "3.2 s swell"),
    ("breathe", "Breathe", "1.6 s swell"),
    ("aurora", "Aurora", "Drifting, irregular swells"),
    ("heartbeat", "Heartbeat", "Double beat, 1.25 s"),
    ("strobe", "Strobe", "8 Hz flicker - use with care"),
    ("candle", "Candle", "Random soft flicker"),
    ("sos", "SOS", "Morse ... --- ..."),
    ("typing", "Typing", "Lit while you type, 1.2 s tail"),
    ("cpu", "CPU", "Blink duty follows CPU load"),
    ("disk", "Disk", "Flickers with disk activity"),
    ("net", "Net", "Flickers with network activity"),
]

VALID_MODES = {k for k, _, _ in EFFECTS}

# Morse schedule, identical to the Linux engine
_SOS, _t = [], 0.0
for _group in ("short", "long", "short"):
    for _ in range(3):
        _on = 0.15 if _group == "short" else 0.45
        _SOS.append((_t, _t + _on))
        _t += _on + 0.15
    _t += 0.30 if _group != "short" else 0.0
SOS, SOS_LEN = tuple(_SOS), _t + 1.0


# --------------------------------------------------------------------------- #
# Windows system stats (fall back gracefully on other platforms)
# --------------------------------------------------------------------------- #
class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def _ft(v):
    return (v.dwHighDateTime << 32) | v.dwLowDateTime


class Stats:
    def __init__(self):
        self.win = None
        if IS_WINDOWS:
            try:
                self.win = ctypes.WinDLL("kernel32.dll")
                self.user = ctypes.WinDLL("user32.dll")
                self.win.GetSystemTimes.argtypes = [ctypes.POINTER(_FILETIME)] * 3
                self.win.GetSystemTimes.restype = wt.BOOL
                self.win.GetTickCount.restype = wt.DWORD
                self.user.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
                self.user.GetLastInputInfo.restype = wt.BOOL
            except Exception:
                self.win = None
        self._cpu = None
        self._disk = None
        self._net = None
        self.disk_hot = -99.0
        self.net_hot = -99.0

    # CPU ------------------------------------------------------------------
    def cpu(self):
        if psutil is not None:
            return max(0.0, min(1.0, psutil.cpu_percent(interval=None) / 100.0))
        if not self.win:
            return 0.0
        idle, kern, user = _FILETIME(), _FILETIME(), _FILETIME()
        if not self.win.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern),
                                       ctypes.byref(user)):
            return 0.0
        cur = (_ft(idle), _ft(kern), _ft(user))
        if self._cpu is None:
            self._cpu = cur
            return 0.0
        di = cur[0] - self._cpu[0]
        dk = cur[1] - self._cpu[1]
        du = cur[2] - self._cpu[2]
        self._cpu = cur
        total = dk + du
        if total <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - di / total))

    # disk / net -----------------------------------------------------------
    def disk(self, now):
        if psutil is None:
            return
        io = psutil.disk_io_counters()
        if not io:
            return
        total = io.read_bytes + io.write_bytes
        if self._disk is not None and total - self._disk > 65536:
            self.disk_hot = now
        self._disk = total

    def net(self, now):
        if psutil is None:
            return
        io = psutil.net_io_counters()
        if not io:
            return
        total = io.bytes_recv + io.bytes_sent
        if self._net is not None and total - self._net > 4096:
            self.net_hot = now
        self._net = total

    # typing ---------------------------------------------------------------
    def idle_seconds(self):
        if not self.win:
            return 0.0
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if self.user.GetLastInputInfo(ctypes.byref(info)):
            tick = int(self.win.GetTickCount()) & 0xFFFFFFFF
            return max(0.0, ((tick - int(info.dwTime)) & 0xFFFFFFFF) / 1000.0)
        return 0.0


# --------------------------------------------------------------------------- #
# Effects (same formulas as the Linux service)
# --------------------------------------------------------------------------- #
def pattern(mode, t, stats, speed=1.0):
    t *= speed
    if mode == "steady":
        return True
    if mode == "off":
        return False
    if mode == "slow":
        return (t % 8.0) < 4.0
    if mode == "pulse":
        return math.sin(2 * math.pi * t / 3.2) > -0.35
    if mode == "breathe":
        return math.sin(2 * math.pi * t / 1.6) > -0.35
    if mode == "aurora":
        v = (math.sin(2 * math.pi * t / 2.6)
             + 0.60 * math.sin(2 * math.pi * t / 1.27 + 1.1)
             + 0.30 * math.sin(2 * math.pi * t / 0.73 + 2.0))
        return v > -0.10
    if mode == "heartbeat":
        ph = t % 1.25
        return not (ph < 0.09 or 0.24 <= ph < 0.33)
    if mode == "strobe":
        return (t * 8) % 1 < 0.5
    if mode == "candle":
        return random.random() > 0.22
    if mode == "sos":
        ph = t % SOS_LEN
        return any(a <= ph < b for a, b in SOS)
    if mode == "typing":
        return stats.idle_seconds() < 1.2
    if mode == "cpu":
        return (t % 0.6) < (0.10 + 0.50 * stats.cpu())
    if mode == "disk":
        return time.monotonic() - stats.disk_hot < 0.30
    if mode == "net":
        return time.monotonic() - stats.net_hot < 0.30
    return True


# --------------------------------------------------------------------------- #
# Backend wrapper (real HID on Windows, harmless fake elsewhere)
# --------------------------------------------------------------------------- #
class FakeBackend:
    connected = True
    method = "fake"
    error = ""
    path = "fake"

    def connect(self):
        return True

    def disconnect(self):
        pass

    def set_led(self, on, force=False):
        return True

    def diagnose(self):
        return ("Not running on Windows, so the HID layer is a stub.\n"
                "Run this file on Windows to test the real device.")


def make_backend():
    if hidwin is not None:
        return hidwin.Backend()
    return FakeBackend()


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
class Preview(QWidget):
    ROWS = (
        [1] * 13 + [2],
        [1.5] + [1] * 12 + [1.5],
        [1.75] + [1] * 11 + [2.25],
        [2.25] + [1] * 10 + [2.75],
        [1.25] * 4 + [6.25] + [1.25] * 3,
    )
    GRAD = ((0.0, "#38bdf8"), (0.42, "#818cf8"),
            (0.72, "#c084fc"), (1.0, "#f472b6"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.lit = 1.0

    def set_lit(self, lit):
        self.lit = lit
        self.update()

    @classmethod
    def grad_color(cls, f):
        stops = [(p, QColor(c)) for p, c in cls.GRAD]
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if f <= p1:
                k = 0.0 if p1 == p0 else (f - p0) / (p1 - p0)
                return QColor(round(c0.red() + (c1.red() - c0.red()) * k),
                              round(c0.green() + (c1.green() - c0.green()) * k),
                              round(c0.blue() + (c1.blue() - c0.blue()) * k))
        return stops[-1][1]

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(QPen(QColor("#1b2a44"), 1))
        p.setBrush(QColor("#0a1120"))
        p.drawRoundedRect(card, 14, 14)

        pad, gap, units = 18.0, 3.0, 15.0
        area = card.adjusted(pad, pad, -pad, -pad)
        unit_w = (area.width() - gap * (units - 1)) / units
        rows = len(self.ROWS)
        key_h = (area.height() - gap * (rows - 1)) / rows

        lit = max(0.0, min(1.0, self.lit))
        dark = QColor("#111c2e")
        if lit > 0.02:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(129, 140, 248, int(30 * lit)))
            p.drawRoundedRect(card.adjusted(6, 6, -6, -6), 16, 16)

        for ri, row in enumerate(self.ROWS):
            total = sum(row)
            row_w = total * unit_w + gap * (total - 1)
            x = area.left() + (area.width() - row_w) / 2
            y = area.top() + ri * (key_h + gap)
            for u in row:
                w = u * unit_w + gap * (u - 1)
                kr = QRectF(x, y, w, key_h)
                if lit > 0.02:
                    f = (kr.center().x() - area.left()) / max(1.0, area.width())
                    col = self.grad_color(max(0.0, min(1.0, f)))
                    base = QColor(round(dark.red() + (col.red() - dark.red()) * lit),
                                  round(dark.green() + (col.green() - dark.green()) * lit),
                                  round(dark.blue() + (col.blue() - dark.blue()) * lit))
                    p.setPen(QPen(QColor(255, 255, 255, int(46 * lit)), 1))
                    p.setBrush(base)
                else:
                    p.setPen(QPen(QColor("#1d2c44"), 1))
                    p.setBrush(dark)
                p.drawRoundedRect(kr, 3.0, 3.0)
                x += w + gap


class Diagnostics(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Studio - diagnostics")
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        view = QPlainTextEdit(text)
        view.setReadOnly(True)
        view.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        layout.addWidget(view)
        row = QHBoxLayout()
        row.addStretch(1)
        copy = QPushButton("Copy to clipboard")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(text))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addWidget(close_btn)
        layout.addLayout(row)


class Studio(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keyboard Studio")
        self.setWindowIcon(QIcon.fromTheme("input-keyboard"))
        self.resize(720, 800)

        self.stats = Stats()
        self.backend = make_backend()
        self.mode = "steady"
        self.speed = 1.0
        self.t0 = time.monotonic()
        self.lit = 1.0
        self._last_connect = 0.0
        self._led_failing = False
        self.load_state()
        self.backend.connect()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(14)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Keyboard Studio")
        title.setObjectName("title")
        self.subtitle = QLabel("CASUE USB KB  \u00b7  Windows  \u00b7  one lighting zone (on/off)")
        self.subtitle.setObjectName("sub")
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        head.addStretch(1)
        self.chip = QLabel()
        self.chip.setObjectName("chip")
        head.addWidget(self.chip, 0, Qt.AlignTop)
        root.addLayout(head)

        self.preview = Preview(self)
        root.addWidget(self.preview)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for i, (key, name, hint) in enumerate(EFFECTS):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setToolTip(hint)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(50)
            if key in ("disk", "net") and psutil is None:
                b.setEnabled(False)
                b.setToolTip(f"{hint}\nneeds psutil: pip install psutil")
            b.clicked.connect(lambda _=False, k=key: self.pick(k))
            self.group.addButton(b)
            self.buttons[key] = b
            grid.addWidget(b, i // 3, i % 3)
        root.addLayout(grid)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(12)
        self.speed_title = QLabel("Speed")
        self.speed_title.setObjectName("sub")
        speed_row.addWidget(self.speed_title)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(25, 400)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(25)
        self.slider.setValue(int(round(self.speed * 100)))
        self.slider.valueChanged.connect(self.on_speed)
        speed_row.addWidget(self.slider, 1)
        self.speed_label = QLabel(f"{self.speed:.2f}\u00d7")
        self.speed_label.setMinimumWidth(52)
        self.speed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        speed_row.addWidget(self.speed_label)
        reset = QPushButton("Reset")
        reset.setObjectName("small")
        reset.clicked.connect(lambda: self.slider.setValue(100))
        speed_row.addWidget(reset)
        root.addLayout(speed_row)

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("footer")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.diag_btn = QPushButton("Diagnostics")
        self.diag_btn.setObjectName("small")
        self.diag_btn.clicked.connect(self.show_diagnostics)
        bottom.addWidget(self.diag_btn)
        self.reconnect_btn = QPushButton("Reconnect")
        self.reconnect_btn.setObjectName("small")
        self.reconnect_btn.clicked.connect(self.reconnect)
        bottom.addWidget(self.reconnect_btn)
        root.addLayout(bottom)

        self.setStyleSheet("""
            QWidget { background: #070b14; color: #c9d5e6;
                      font-family: 'Segoe UI', sans-serif; font-size: 13px; }
            #title { font-size: 23px; font-weight: 700; color: #eaf2ff; }
            #sub { color: #7c8ba3; font-size: 12px; }
            #chip { background: #10203a; border: 1px solid #1e3a5f; border-radius: 12px;
                    padding: 5px 14px; color: #8fd0ff; font-weight: 600; font-size: 12px; }
            #footer { color: #6b7a92; font-size: 11px; }
            QPushButton { background: #0d1726; border: 1px solid #1b2a42; border-radius: 10px;
                          padding: 10px 8px; color: #b9c7dc; font-size: 13px; }
            QPushButton:hover { background: #14233a; border-color: #2a4a72; color: #e6eefb; }
            QPushButton:pressed { background: #0a1420; }
            QPushButton:checked { background: #12283f; border: 1px solid #38bdf8; color: #eaf7ff; }
            QPushButton:disabled { color: #4b5a70; border-color: #16202f; }
            QPushButton#small { padding: 6px 14px; font-size: 12px; color: #93a3bb; }
            QSlider::groove:horizontal { height: 6px; background: #141f33; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #38bdf8; border-radius: 3px; }
            QSlider::handle:horizontal { width: 16px; margin: -6px 0; border-radius: 8px;
                                         background: #d8ecff; border: 1px solid #38bdf8; }
        """)

        self.subtitle.setMinimumWidth(self.subtitle.sizeHint().width() + 8)
        self.speed_title.setMinimumWidth(self.speed_title.sizeHint().width() + 8)
        self.buttons.get(self.mode, self.buttons["steady"]).setChecked(True)
        self.chip.setText(f"\u25cf  {self.mode_name().upper()}")
        self.sync_status()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    # -- state --------------------------------------------------------------
    def mode_name(self):
        return {k: n for k, n, _ in EFFECTS}.get(self.mode, self.mode)

    def load_state(self):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            if data.get("mode") in VALID_MODES:
                self.mode = data["mode"]
            self.speed = max(0.25, min(4.0, float(data.get("speed", 1.0))))
        except (OSError, ValueError, TypeError):
            pass

    def save_state(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump({"mode": self.mode, "speed": round(self.speed, 3)}, f)
        except OSError:
            pass

    # -- actions ------------------------------------------------------------
    def pick(self, mode):
        self.mode = mode
        self.t0 = time.monotonic()
        self.lit = 1.0 if mode == "steady" else self.lit
        self.chip.setText(f"\u25cf  {self.mode_name().upper()}")
        if not self.backend.connected:
            self.backend.connect()
        self.save_state()
        self.sync_status()

    def on_speed(self, value):
        self.speed = value / 100.0
        self.speed_label.setText(f"{self.speed:.2f}\u00d7")
        self.save_state()

    def reconnect(self):
        self.backend.connect()
        self._last_connect = time.monotonic()
        self.sync_status()

    def sync_status(self):
        if not self.backend.connected:
            self.status.setText(
                "Keyboard not connected. " + (self.backend.error or
                "Check that the CASUE USB KB is plugged in; try running as administrator."))
            return
        extra = ""
        if psutil is None:
            extra = "  Disk/Net need psutil (pip install psutil)."
        method = {"KeyboardInterface": "CASUE keyboard driver"}.get(
            self.backend.method, self.backend.method or "HID")
        self.status.setText(
            f"Connected via {method}  \u00b7  "
            f"effects override the Scroll Lock LED while running.{extra}")

    def tick(self):
        now = time.monotonic()
        if not self.backend.connected and now - self._last_connect > 2.0:
            self._last_connect = now
            self.backend.connect()
            self.sync_status()

        if self.mode == "disk":
            self.stats.disk(now)
        elif self.mode == "net":
            self.stats.net(now)

        on = pattern(self.mode, now - self.t0, self.stats, self.speed)
        accepted = self.backend.set_led(on)
        if not accepted and not self._led_failing:
            self._led_failing = True
            self.status.setText(
                "Windows rejected the LED report. Try running as administrator, "
                "or open Diagnostics.  " + (self.backend.error or ""))
        elif accepted and self._led_failing:
            self._led_failing = False
            self.sync_status()

        target = 1.0 if on else 0.0
        self.lit += (target - self.lit) * 0.55
        if abs(target - self.lit) < 0.01:
            self.lit = target
        self.preview.set_lit(self.lit)

    def closeEvent(self, event):
        self.timer.stop()
        self.backend.disconnect()
        super().closeEvent(event)

    def show_diagnostics(self):
        # The LED timer must not fight the diagnostic toggles.
        self.timer.stop()
        try:
            text = self.backend.diagnose()
        finally:
            self.timer.start(33)
        if HID_IMPORT_ERROR is not None:
            text = f"hidwin import failed: {HID_IMPORT_ERROR}\n\n" + text
        Diagnostics(text, self).exec()


def main():
    if "--diagnose" in sys.argv:
        backend = make_backend()
        backend.connect()
        try:
            print(backend.diagnose())
        finally:
            backend.disconnect()
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("Keyboard Studio")
    win = Studio()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
