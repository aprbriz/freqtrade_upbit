from __future__ import annotations

import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from .engine import Candle, DISPLAY_NAMES, TIMEFRAMES_MS
from .qt import QtCore, QtGui, QtWidgets, Signal


TIMEFRAME_LABELS = {
    60_000: "1분",
    300_000: "5분",
    900_000: "15분",
    3_600_000: "1시간",
    14_400_000: "4시간",
    86_400_000: "일봉",
}


THEME_LIGHT = {
    "bg-base": "#FFFFFF",
    "bg-surface": "#F6F7F9",
    "bg-elevated": "#EDEEF1",
    "bg-tile": "#F0F1F4",
    "bg-hover": "#E8E9ED",
    "text-primary": "#1A1D24",
    "text-secondary": "#3D4350",
    "text-tertiary": "#6B7280",
    "text-quaternary": "#9CA3AF",
    "border-subtle": "#E2E4E9",
    "border-muted": "#D0D3DA",
    "chart-up": "#E54040",
    "chart-up-bg": "rgba(229,64,64,0.08)",
    "chart-down": "#3182F6",
    "chart-down-bg": "rgba(49,130,246,0.08)",
    "chart-grid": "#F0F1F4",
    "chart-axis": "#9CA3AF",
    "status-ok": "#0D9F61",
    "status-ok-dim": "rgba(13,159,97,0.08)",
    "status-ok-medium": "rgba(13,159,97,0.15)",
    "status-warn": "#D97706",
    "status-warn-dim": "rgba(217,119,6,0.07)",
    "status-warn-medium": "rgba(217,119,6,0.14)",
    "status-fail": "#C026D3",
    "status-fail-dim": "rgba(192,38,211,0.06)",
    "status-fail-medium": "rgba(192,38,211,0.12)",
    "status-inactive": "#9CA3AF",
}

THEME_DARK = {
    "bg-base": "#0F1115",
    "bg-surface": "#181A20",
    "bg-elevated": "#1E2028",
    "bg-tile": "#22242C",
    "bg-hover": "#282A34",
    "text-primary": "#F0F1F4",
    "text-secondary": "#C2C5CC",
    "text-tertiary": "#818690",
    "text-quaternary": "#555962",
    "border-subtle": "#2A2D38",
    "border-muted": "#363944",
    "chart-up": "#EF5350",
    "chart-up-bg": "rgba(239,83,80,0.10)",
    "chart-down": "#5B9CF6",
    "chart-down-bg": "rgba(91,156,246,0.10)",
    "chart-grid": "#1E2028",
    "chart-axis": "#555962",
    "status-ok": "#2DD882",
    "status-ok-dim": "rgba(45,216,130,0.10)",
    "status-ok-medium": "rgba(45,216,130,0.18)",
    "status-warn": "#F5A623",
    "status-warn-dim": "rgba(245,166,35,0.10)",
    "status-warn-medium": "rgba(245,166,35,0.18)",
    "status-fail": "#D964E7",
    "status-fail-dim": "rgba(217,100,231,0.08)",
    "status-fail-medium": "rgba(217,100,231,0.15)",
    "status-inactive": "#555962",
}


def parse_color(s: str) -> QtGui.QColor:
    if s.startswith("rgba("):
        m = re.match(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", s.replace(" ", ""))
        if m:
            return QtGui.QColor(
                int(m[1]),
                int(m[2]),
                int(m[3]),
                int(float(m[4]) * 255),
            )
    return QtGui.QColor(s)


class ThemeManager:
    _theme = "light"
    _listeners: List[Callable[[], None]] = []

    @classmethod
    def current(cls) -> Dict[str, str]:
        return THEME_LIGHT if cls._theme == "light" else THEME_DARK

    @classmethod
    def mode(cls) -> str:
        return cls._theme

    @classmethod
    def toggle(cls) -> None:
        cls._theme = "dark" if cls._theme == "light" else "light"
        for cb in list(cls._listeners):
            cb()

    @classmethod
    def subscribe(cls, cb: Callable[[], None]) -> None:
        cls._listeners.append(cb)


class EventStore:
    def __init__(self) -> None:
        self.events: Deque[str] = deque(maxlen=50)
        self._last_ws: Dict[str, str] = {}
        self._last_mode: Dict[str, str] = {}

    def _push(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.events.appendleft(f"{stamp} | {text}")

    def update(self, diag: Dict[str, Any], snaps: Dict[str, Dict[str, Any]]) -> None:
        symbols = diag.get("symbols", {})
        for symbol, state in symbols.items():
            ws = str(state.get("ws", "OK"))
            mode = str(state.get("mode", "LIVE"))
            if symbol in self._last_ws and self._last_ws[symbol] != ws:
                self._push(f"{symbol} WS 상태 변경: {self._last_ws[symbol]} -> {ws}")
            if symbol in self._last_mode and self._last_mode[symbol] != mode:
                self._push(f"{symbol} 모드 변경: {self._last_mode[symbol]} -> {mode}")
            self._last_ws[symbol] = ws
            self._last_mode[symbol] = mode

    def recent(self, n: int = 5) -> List[str]:
        return list(self.events)[:n]


class AlertStrip(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.label = QtWidgets.QLabel("")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.addWidget(self.label)
        self.hide()
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(
            f"background:{t['status-warn-dim']}; border-bottom:1px solid {t['status-warn-medium']};"
            f"color:{t['status-warn']};"
        )

    def check_and_update(self, diag: Dict[str, Any]) -> None:
        symbols = diag.get("symbols", {})
        bad = [s for s, st in symbols.items() if st.get("ws") not in ("OK",)]
        if bad:
            self.label.setText(f"경고: WS 상태 불안정 ({', '.join(bad)})")
            self.show()
        else:
            self.hide()


class StatusChip(QtWidgets.QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumHeight(20)
        self.setStyleSheet("padding:0 8px; border-radius:10px; font-size:11px; font-weight:600;")

    def set_kind(self, kind: str) -> None:
        t = ThemeManager.current()
        if kind == "ok":
            bg, fg = t["status-ok-dim"], t["status-ok"]
        elif kind == "warn":
            bg, fg = t["status-warn-dim"], t["status-warn"]
        elif kind == "fail":
            bg, fg = t["status-fail-dim"], t["status-fail"]
        else:
            bg, fg = t["bg-tile"], t["text-tertiary"]
        self.setStyleSheet(
            f"padding:0 8px; border-radius:10px; font-size:11px; font-weight:600;"
            f"background:{bg}; color:{fg};"
        )


class HeaderBar(QtWidgets.QFrame):
    symbol_changed = Signal(str)

    def __init__(self, show_tabs: bool = False, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.show_tabs = show_tabs
        self.logo_label = QtWidgets.QLabel()
        self.monitor_label = QtWidgets.QLabel("Monitor")
        self.live_chip = StatusChip("● LIVE")
        self.ws_chip = StatusChip("● WS 0.0s")
        self.live_chip_right = StatusChip("● LIVE")
        self.ws_chip_right = StatusChip("● WS 0.0s")
        self.theme_label = QtWidgets.QLabel("LIGHT THEME")
        self.theme_btn = QtWidgets.QToolButton()
        self.theme_btn.setText("⚙")
        self.tab_group: Dict[str, QtWidgets.QPushButton] = {}

        self._build_ui()
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()
        self.theme_btn.clicked.connect(ThemeManager.toggle)

    def _load_logo(self) -> Optional[QtGui.QPixmap]:
        logo_path = Path(__file__).resolve().parent / "assets" / "upbit_logo.png"
        if logo_path.exists():
            px = QtGui.QPixmap(str(logo_path))
            if not px.isNull():
                return px.scaledToHeight(20, QtCore.Qt.SmoothTransformation)
        return None

    def _build_ui(self) -> None:
        self.setFixedHeight(48)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        px = self._load_logo()
        if px:
            self.logo_label.setPixmap(px)
        else:
            self.logo_label.setText("UPbit")
            self.logo_label.setStyleSheet("font-weight:700; font-size:14px;")
        self.monitor_label.setStyleSheet("font-size:14px; font-weight:600;")
        layout.addWidget(self.logo_label)
        layout.addWidget(self.monitor_label)
        layout.addWidget(self.live_chip)
        layout.addWidget(self.ws_chip)
        layout.addStretch()
        if not self.show_tabs:
            layout.addWidget(self.live_chip_right)
            layout.addWidget(self.ws_chip_right)

        if self.show_tabs:
            for sym in ("ETH", "XRP", "BTC"):
                btn = QtWidgets.QPushButton(sym)
                btn.setCheckable(True)
                btn.setFixedHeight(24)
                btn.clicked.connect(lambda checked, s=sym: self._on_tab_click(s))
                self.tab_group[sym] = btn
                layout.addWidget(btn)
            self.set_active_tab("XRP")

        layout.addWidget(self.theme_label)
        layout.addWidget(self.theme_btn)

    def _on_tab_click(self, symbol: str) -> None:
        self.set_active_tab(symbol)
        self.symbol_changed.emit(f"KRW-{symbol}")

    def set_active_tab(self, symbol: str) -> None:
        for sym, btn in self.tab_group.items():
            btn.setChecked(sym == symbol)
        self.apply_theme()

    def update_status(self, snaps: Dict[str, Dict[str, Any]]) -> None:
        ordered = [snaps[k] for k in sorted(snaps.keys()) if snaps.get(k)]
        left = ordered[0] if ordered else {}
        right = ordered[1] if len(ordered) > 1 else {}

        def _set_pair(live_chip: StatusChip, ws_chip: StatusChip, snap: Dict[str, Any]) -> None:
            age = float(snap.get("last_message_age", 0.0))
            ws_chip.setText(f"● WS {age:.1f}s")
            ws_chip.set_kind("ok" if age < 2.0 else "warn")
            mode = str(snap.get("mode", "LIVE"))
            live_chip.setText(f"● {mode}")
            live_chip.set_kind("ok" if mode == "LIVE" else "warn")

        _set_pair(self.live_chip, self.ws_chip, left)
        _set_pair(self.live_chip_right, self.ws_chip_right, right if right else left)

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(
            f"background:{t['bg-surface']}; border-bottom:1px solid {t['border-subtle']};"
        )
        self.monitor_label.setStyleSheet(
            f"font-size:14px; font-weight:600; color:{t['text-primary']};"
        )
        self.theme_label.setText(f"{ThemeManager.mode().upper()} THEME")
        self.theme_label.setStyleSheet(f"color:{t['text-tertiary']}; font-size:11px;")
        self.theme_btn.setStyleSheet(
            f"border:none; color:{t['text-tertiary']}; font-size:14px;"
        )
        for sym, btn in self.tab_group.items():
            if btn.isChecked():
                btn.setStyleSheet(
                    f"background:{t['bg-elevated']}; color:{t['text-primary']}; border:1px solid {t['border-muted']};"
                    "border-radius:4px; font-size:11px; font-weight:600;"
                )
            else:
                btn.setStyleSheet(
                    f"background:{t['bg-surface']}; color:{t['text-tertiary']}; border:1px solid transparent;"
                    "border-radius:4px; font-size:11px;"
                )


class CandleChartWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._candles: List[Candle] = []
        self.setMinimumHeight(280)

    def set_candles(self, candles: List[Candle]) -> None:
        self._candles = candles
        self.update()

    def apply_theme(self) -> None:
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        t = ThemeManager.current()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        r = self.rect()
        p.fillRect(r, parse_color(t["bg-base"]))
        if not self._candles:
            p.setPen(parse_color(t["text-quaternary"]))
            p.drawText(r, QtCore.Qt.AlignCenter, "No data")
            return

        right_margin = 52
        bottom_margin = 18
        plot = QtCore.QRect(r.left(), r.top() + 2, r.width() - right_margin, r.height() - bottom_margin)
        candles = self._candles[-max(50, int(plot.width() / 3)) :]
        lows = [c.low for c in candles]
        highs = [c.high for c in candles]
        min_p, max_p = min(lows), max(highs)
        if max_p <= min_p:
            max_p = min_p + 1.0
        pad = (max_p - min_p) * 0.05
        min_p -= pad
        max_p += pad

        def y_for(v: float) -> int:
            ratio = (v - min_p) / (max_p - min_p)
            return plot.bottom() - int(ratio * plot.height())

        p.setPen(parse_color(t["chart-grid"]))
        for i in range(5):
            y = plot.top() + int(i * plot.height() / 4)
            p.drawLine(plot.left(), y, plot.right(), y)
            value = max_p - (max_p - min_p) * i / 4
            p.setPen(parse_color(t["chart-axis"]))
            p.drawText(plot.right() + 4, y + 4, f"{value:,.0f}")
            p.setPen(parse_color(t["chart-grid"]))

        step = plot.width() / max(1, len(candles))
        for i, c in enumerate(candles):
            x = plot.left() + int(i * step)
            up = c.close >= c.open
            color = parse_color(t["chart-up"] if up else t["chart-down"])
            p.setPen(color)
            w = max(1, int(step))
            p.drawLine(x + w // 2, y_for(c.high), x + w // 2, y_for(c.low))
            top = min(y_for(c.open), y_for(c.close))
            h = max(1, abs(y_for(c.close) - y_for(c.open)))
            p.fillRect(QtCore.QRect(x, top, w, h), color)

        p.setPen(parse_color(t["chart-axis"]))
        for i in range(5):
            idx = int(i * (len(candles) - 1) / 4) if len(candles) > 1 else 0
            dt = QtCore.QDateTime.fromMSecsSinceEpoch(candles[idx].ts_ms)
            p.drawText(plot.left() + int(idx * step), r.bottom() - 2, dt.toString("MM/dd HH:mm"))


class VolumeChartWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._candles: List[Candle] = []
        self.setFixedHeight(92)

    def set_candles(self, candles: List[Candle]) -> None:
        self._candles = candles
        self.update()

    def apply_theme(self) -> None:
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        t = ThemeManager.current()
        p = QtGui.QPainter(self)
        r = self.rect()
        p.fillRect(r, parse_color(t["bg-base"]))
        if not self._candles:
            return
        right_margin = 52
        plot = QtCore.QRect(r.left(), r.top() + 2, r.width() - right_margin, r.height() - 4)
        candles = self._candles[-max(50, int(plot.width() / 3)) :]
        amounts = [c.volume * c.close for c in candles]
        max_a = max(amounts) if amounts else 1.0
        max_a = max(max_a, 1.0)
        p.setPen(parse_color(t["chart-grid"]))
        for i in range(3):
            y = plot.top() + int(i * plot.height() / 2)
            p.drawLine(plot.left(), y, plot.right(), y)
            value = max_a * (1 - i / 2)
            p.setPen(parse_color(t["chart-axis"]))
            p.drawText(plot.right() + 4, y + 4, f"{value:,.0f}")
            p.setPen(parse_color(t["chart-grid"]))
        step = plot.width() / max(1, len(candles))
        for i, c in enumerate(candles):
            x = plot.left() + int(i * step)
            amount = c.volume * c.close
            h = int((amount / max_a) * (plot.height() - 2))
            y = plot.bottom() - h
            color = parse_color(t["chart-up"] if c.close >= c.open else t["chart-down"])
            p.fillRect(QtCore.QRect(x, y, max(1, int(step)), h), color)


class ChartArea(QtWidgets.QFrame):
    def __init__(self, engine, symbol: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.symbol = symbol
        self._snapshot: Dict[str, Any] = {}
        self.title = QtWidgets.QLabel()
        self.title2 = QtWidgets.QLabel()
        self.price = QtWidgets.QLabel("-")
        self.change = QtWidgets.QLabel("-")
        self.tf_combo = QtWidgets.QComboBox()
        self.chart = CandleChartWidget()
        self.volume = VolumeChartWidget()
        self._build_ui()
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def _format_symbol(self) -> str:
        q, b = self.symbol.split("-")
        return f"{b} / {q}"

    def _build_ui(self) -> None:
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QtWidgets.QFrame()
        top.setFixedHeight(86)
        top_l = QtWidgets.QVBoxLayout(top)
        top_l.setContentsMargins(10, 6, 10, 6)

        self.title.setText(f"{self._format_symbol()} · 1분봉")
        self.title.setStyleSheet("font-size:11px;")
        top_l.addWidget(self.title)
        self.title2.setText("1분")
        self.title2.setStyleSheet("font-size:10px;")
        top_l.addWidget(self.title2, 0, QtCore.Qt.AlignLeft)

        row = QtWidgets.QHBoxLayout()
        self.price.setStyleSheet("font-size:34px; font-weight:700;")
        self.change.setStyleSheet("font-size:12px;")
        row.addWidget(self.price)
        row.addWidget(self.change)
        row.addStretch()
        top_l.addLayout(row)

        self.tf_combo.setFixedWidth(90)
        for tf in TIMEFRAMES_MS:
            self.tf_combo.addItem(TIMEFRAME_LABELS.get(tf, str(tf)), tf)
        self.tf_combo.currentIndexChanged.connect(self._on_tf_changed)
        top_l.addWidget(self.tf_combo, 0, QtCore.Qt.AlignLeft)

        layout.addWidget(top)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.volume)

    def _on_tf_changed(self) -> None:
        tf_ms = self.tf_combo.currentData()
        if tf_ms:
            self.engine.set_active_timeframe(self.symbol, int(tf_ms))

    def set_symbol(self, symbol: str) -> None:
        self.symbol = symbol
        self.title.setText(f"{self._format_symbol()} · 1분봉")
        self._on_tf_changed()

    def update_snapshot(self, snap: Dict[str, Any]) -> None:
        if not snap:
            return
        self._snapshot = snap
        symbol = snap.get("symbol", self.symbol)
        self.symbol = symbol
        tf_ms = snap.get("timeframe_ms")
        tf_label = TIMEFRAME_LABELS.get(int(tf_ms), str(tf_ms)) if tf_ms else "1분"
        self.title.setText(f"{self._format_symbol()} · {tf_label}")
        self.title2.setText(tf_label)
        price = float(snap.get("price") or 0.0)
        delta = float(snap.get("price_change") or 0.0)
        pct = float(snap.get("percent_change") or 0.0)
        arrow = "▲" if delta >= 0 else "▼"
        self.price.setText(f"{price:,.0f}")
        self.change.setText(f"{delta:,.0f} ({pct:+.2f}%) {arrow}")
        t = ThemeManager.current()
        col = t["chart-up"] if delta >= 0 else t["chart-down"]
        self.price.setStyleSheet(f"font-size:34px; font-weight:700; color:{col};")
        self.change.setStyleSheet(f"font-size:12px; color:{col};")

        candles = snap.get("candles") or []
        self.chart.set_candles(candles)
        self.volume.set_candles(candles)
        if tf_ms:
            for i in range(self.tf_combo.count()):
                if self.tf_combo.itemData(i) == int(tf_ms):
                    self.tf_combo.blockSignals(True)
                    self.tf_combo.setCurrentIndex(i)
                    self.tf_combo.blockSignals(False)
                    break

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(f"background:{t['bg-base']};")
        self.title.setStyleSheet(f"font-size:11px; color:{t['text-secondary']};")
        self.title2.setStyleSheet(f"font-size:10px; color:{t['text-quaternary']};")
        self.tf_combo.setStyleSheet(
            f"background:{t['bg-surface']}; color:{t['text-primary']}; border:1px solid {t['border-subtle']};"
            "border-radius:4px; padding:2px 6px; font-size:11px;"
        )
        self.chart.apply_theme()
        self.volume.apply_theme()


class KpiTile(QtWidgets.QFrame):
    def __init__(self, title: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.title = QtWidgets.QLabel(title)
        self.value = QtWidgets.QLabel("-")
        self.sub = QtWidgets.QLabel("")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.sub)
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def set_data(self, value: str, sub: str = "") -> None:
        self.value.setText(value)
        self.sub.setText(sub)

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(
            f"background:{t['bg-tile']}; border:1px solid {t['border-subtle']}; border-radius:6px;"
        )
        self.title.setStyleSheet(f"font-size:10px; color:{t['text-tertiary']};")
        self.value.setStyleSheet(f"font-size:30px; font-weight:700; color:{t['text-primary']};")
        self.sub.setStyleSheet(f"font-size:10px; color:{t['text-quaternary']};")


class ConnectionSection(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.rows: Dict[str, QtWidgets.QLabel] = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.title = QtWidgets.QLabel("커넥션 상세")
        layout.addWidget(self.title)
        for key in ("WS ETH", "WS XRP", "WS BTC", "DB Write"):
            row = QtWidgets.QHBoxLayout()
            left = QtWidgets.QLabel(key)
            right = QtWidgets.QLabel("-")
            row.addWidget(left)
            row.addStretch()
            row.addWidget(right)
            layout.addLayout(row)
            self.rows[key] = right
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def update_data(self, diag: Dict[str, Any]) -> None:
        syms = diag.get("symbols", {})
        for key, symbol in (("WS ETH", "KRW-ETH"), ("WS XRP", "KRW-XRP"), ("WS BTC", "KRW-BTC")):
            st = syms.get(symbol, {})
            age = float(st.get("last_message_age", 0.0))
            self.rows[key].setText(f"{age:.1f}s")
        self.rows["DB Write"].setText("정상")

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(
            f"background:{t['bg-surface']}; border:1px solid {t['border-subtle']}; border-radius:6px;"
        )
        self.title.setStyleSheet(f"font-size:11px; font-weight:600; color:{t['text-primary']};")
        for w in self.findChildren(QtWidgets.QLabel):
            if w is self.title:
                continue
            w.setStyleSheet(f"font-size:11px; color:{t['text-secondary']};")


class EventTimeline(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.items: List[QtWidgets.QLabel] = []
        self.legend = QtWidgets.QLabel("범례:")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.title = QtWidgets.QLabel("이벤트 타임라인")
        layout.addWidget(self.title)
        for _ in range(5):
            lbl = QtWidgets.QLabel("-")
            self.items.append(lbl)
            layout.addWidget(lbl)
        layout.addSpacing(4)
        legend_row = QtWidgets.QHBoxLayout()
        legend_row.addWidget(self.legend)
        for name, color in (("OK", "status-ok"), ("WARN", "status-warn"), ("FAIL", "status-fail")):
            dot = QtWidgets.QLabel("■")
            dot.setObjectName(f"legend-{color}")
            txt = QtWidgets.QLabel(name)
            txt.setObjectName("legend-text")
            legend_row.addWidget(dot)
            legend_row.addWidget(txt)
        legend_row.addStretch()
        layout.addLayout(legend_row)
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def update_events(self, events: List[str]) -> None:
        for i, lbl in enumerate(self.items):
            lbl.setText(events[i] if i < len(events) else "-")

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(
            f"background:{t['bg-surface']}; border:1px solid {t['border-subtle']}; border-radius:6px;"
        )
        self.title.setStyleSheet(f"font-size:11px; font-weight:600; color:{t['text-primary']};")
        for lbl in self.items:
            lbl.setStyleSheet(f"font-size:11px; color:{t['text-secondary']};")
        self.legend.setStyleSheet(f"font-size:10px; color:{t['text-tertiary']};")
        for w in self.findChildren(QtWidgets.QLabel):
            name = w.objectName()
            if name == "legend-status-ok":
                w.setStyleSheet(f"font-size:11px; color:{t['status-ok']};")
            elif name == "legend-status-warn":
                w.setStyleSheet(f"font-size:11px; color:{t['status-warn']};")
            elif name == "legend-status-fail":
                w.setStyleSheet(f"font-size:11px; color:{t['status-fail']};")
            elif name == "legend-text":
                w.setStyleSheet(f"font-size:10px; color:{t['text-tertiary']};")


class DashboardPanel(QtWidgets.QFrame):
    def __init__(self, event_store: EventStore, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.event_store = event_store
        self.tiles = {
            "ws": KpiTile("WS 연결"),
            "db": KpiTile("DB Write Lag"),
            "recv": KpiTile("수신 지연"),
            "reconnect": KpiTile("Reconnect"),
            "rate": KpiTile("수신율"),
            "err": KpiTile("에러율"),
        }
        self.connection = ConnectionSection()
        self.timeline = EventTimeline()
        self._build_ui()
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        ordered = ["ws", "db", "recv", "reconnect", "rate", "err"]
        for i, key in enumerate(ordered):
            grid.addWidget(self.tiles[key], i // 2, i % 2)
        layout.addLayout(grid)
        layout.addWidget(self.connection)
        layout.addWidget(self.timeline, 1)

    def update_dashboard(self, diag: Dict[str, Any], snaps: Dict[str, Dict[str, Any]]) -> None:
        symbols = diag.get("symbols", {})
        ages = [float(v.get("last_message_age", 0.0)) for v in symbols.values()]
        min_age = min(ages) if ages else 0.0
        ws_ok = all(v.get("ws") == "OK" for v in symbols.values()) if symbols else False
        reconnects = 0
        total_ticks = sum(int(v.get("total_ticks", 0)) for v in symbols.values())
        self.tiles["ws"].set_data("OK" if ws_ok else "WARN", f"{len(symbols)} 심볼")
        self.tiles["db"].set_data(f"{int(min_age*1000)}ms", "기준 100ms")
        self.tiles["recv"].set_data(f"{min_age:.1f}s", "avg")
        self.tiles["reconnect"].set_data(str(reconnects), "최근 1분")
        self.tiles["rate"].set_data(f"{total_ticks}/s", "최근 추정")
        self.tiles["err"].set_data("0.0%", "최근 1분")
        self.connection.update_data(diag)
        self.timeline.update_events(self.event_store.recent(5))

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(f"background:{t['bg-base']};")


class FooterBar(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.label = QtWidgets.QLabel("● Last Tick 0.0s | Reconnects 0 | DB Lag 0ms | Uptime 0s")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(self.label)
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()
        self._boot = time.time()

    def update_status(self, diag: Dict[str, Any], snaps: Dict[str, Dict[str, Any]]) -> None:
        symbols = diag.get("symbols", {})
        ages = [float(v.get("last_message_age", 0.0)) for v in symbols.values()]
        age = min(ages) if ages else 0.0
        db_lag = int(age * 1000)
        uptime = int(time.time() - self._boot)
        mm = uptime // 60
        ss = uptime % 60
        self.label.setText(
            f"● Last Tick {age:.1f}s | Reconnects 0 | DB Lag {db_lag}ms | Uptime {mm}m {ss:02d}s"
        )

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(
            f"background:{t['bg-surface']}; border-top:1px solid {t['border-subtle']};"
        )
        self.label.setStyleSheet(f"font-size:11px; color:{t['text-tertiary']};")


class Window1(QtWidgets.QMainWindow):
    def __init__(self, engine, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.event_store = EventStore()
        self.setWindowTitle("Upbit Monitor - BTC & ETH")
        self.alert = AlertStrip()
        self.header = HeaderBar(show_tabs=False)
        self.btc_area = ChartArea(engine, "KRW-BTC")
        self.eth_area = ChartArea(engine, "KRW-ETH")
        self.footer = FooterBar()

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.alert)
        layout.addWidget(self.header)
        split = QtWidgets.QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(1)
        split.addWidget(self.btc_area, 1)
        split.addWidget(self.eth_area, 1)
        layout.addLayout(split, 1)
        layout.addWidget(self.footer)
        self.setCentralWidget(central)
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.centralWidget().setStyleSheet(f"background:{t['bg-base']};")


class Window2(QtWidgets.QMainWindow):
    def __init__(self, engine, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.event_store = EventStore()
        self.active_symbol = "KRW-XRP"
        self.setWindowTitle("Upbit Monitor - XRP + Dashboard")
        self.alert = AlertStrip()
        self.header = HeaderBar(show_tabs=True)
        self.xrp_area = ChartArea(engine, self.active_symbol)
        self.dashboard = DashboardPanel(self.event_store)
        self.footer = FooterBar()

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.alert)
        layout.addWidget(self.header)
        split = QtWidgets.QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(1)
        split.addWidget(self.xrp_area, 65)
        split.addWidget(self.dashboard, 35)
        layout.addLayout(split, 1)
        layout.addWidget(self.footer)
        self.setCentralWidget(central)

        self.header.symbol_changed.connect(self._on_symbol_change)
        ThemeManager.subscribe(self.apply_theme)
        self.apply_theme()

    def _on_symbol_change(self, symbol: str) -> None:
        self.active_symbol = symbol
        self.xrp_area.set_symbol(symbol)

    def update_dashboard(self, diag: Dict[str, Any], snaps: Dict[str, Dict[str, Any]]) -> None:
        self.event_store.update(diag, snaps)
        self.dashboard.update_dashboard(diag, snaps)

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.centralWidget().setStyleSheet(f"background:{t['bg-base']};")
