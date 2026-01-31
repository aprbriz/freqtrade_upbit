from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .engine import TIMEFRAMES_MS, Candle, DISPLAY_NAMES
from .qt import QtCore, QtGui, QtWidgets


UPBIT_BLUE = "#0051c7"
CHART_BG = "#0a1929"
UP_COLOR = "#f23645"
DOWN_COLOR = "#2979ff"
TICKER_BG = "#fef9c3"
TICKER_BORDER = "#fef08a"


TIMEFRAME_LABELS = {
    60_000: "1m",
    300_000: "5m",
    900_000: "15m",
    3_600_000: "1h",
    14_400_000: "4h",
    86_400_000: "1d",
}


class CandleChartWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._candles: List[Candle] = []
        self.setMinimumHeight(300)

    def set_candles(self, candles: List[Candle]) -> None:
        self._candles = candles[-120:]
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor(CHART_BG))

        if not self._candles:
            painter.setPen(QtGui.QColor("#6b7280"))
            painter.drawText(rect, QtCore.Qt.AlignCenter, "No data")
            return

        lows = [c.low for c in self._candles]
        highs = [c.high for c in self._candles]
        min_low = min(lows)
        max_high = max(highs)
        if max_high <= min_low:
            max_high = min_low + 1.0

        chart_width = rect.width()
        chart_height = rect.height() - 10
        candle_width = max(2, int(chart_width / max(1, len(self._candles))))

        def y_for(price: float) -> int:
            ratio = (price - min_low) / (max_high - min_low)
            return rect.bottom() - int(ratio * chart_height) - 5

        for idx, candle in enumerate(self._candles):
            x = rect.left() + idx * candle_width
            open_y = y_for(candle.open)
            close_y = y_for(candle.close)
            high_y = y_for(candle.high)
            low_y = y_for(candle.low)
            color = UP_COLOR if candle.close >= candle.open else DOWN_COLOR
            painter.setPen(QtGui.QColor(color))
            painter.drawLine(x + candle_width // 2, high_y, x + candle_width // 2, low_y)
            top = min(open_y, close_y)
            height = max(1, abs(open_y - close_y))
            painter.fillRect(QtCore.QRect(x, top, candle_width - 1, height), QtGui.QColor(color))


class VolumeChartWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._candles: List[Candle] = []
        self.setFixedHeight(80)

    def set_candles(self, candles: List[Candle]) -> None:
        self._candles = candles[-120:]
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor(CHART_BG))

        if not self._candles:
            return
        max_vol = max(c.volume for c in self._candles) or 1.0
        bar_width = max(2, int(rect.width() / max(1, len(self._candles))))
        for idx, candle in enumerate(self._candles):
            x = rect.left() + idx * bar_width
            height = int((candle.volume / max_vol) * (rect.height() - 8))
            y = rect.bottom() - height
            color = UP_COLOR if candle.close >= candle.open else DOWN_COLOR
            painter.fillRect(QtCore.QRect(x, y, bar_width - 1, height), QtGui.QColor(color))


class ScrollingTicker(QtWidgets.QLabel):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = "System OK | Coalesce: 0 | Tick drop: 0 | Overlay shrink: 0 | DB fallback: 0"
        self._offset = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.setFixedHeight(24)
        self.setStyleSheet(
            f"background:{TICKER_BG}; border-top:1px solid {TICKER_BORDER};"
            "padding-left:6px; font-size:12px;"
        )

    def set_message(self, message: str) -> None:
        self._text = message
        self._offset = 0
        self.update()

    def _tick(self) -> None:
        self._offset = (self._offset + 2) % max(1, len(self._text) * 7)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(TICKER_BG))
        painter.setPen(QtGui.QColor("#a16207"))
        x = self.rect().left() - self._offset
        painter.drawText(x, self.rect().center().y() + 4, self._text)


class ChartPanel(QtWidgets.QWidget):
    def __init__(self, symbol: str, engine, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.symbol = symbol
        self.engine = engine

        self.header_price = QtWidgets.QLabel("0")
        self.header_change = QtWidgets.QLabel("0%")
        self.ws_chip = QtWidgets.QLabel("WS:OK")
        self.mode_chip = QtWidgets.QLabel("LIVE")
        self.burst_chip = QtWidgets.QLabel("NORMAL")
        self.timeframe_combo = QtWidgets.QComboBox()
        self.tick_checkbox = QtWidgets.QCheckBox("Tick")
        self.chart = CandleChartWidget()
        self.volume = VolumeChartWidget()

        self._build_ui()

    def _build_ui(self) -> None:
        header = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        top_row = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QToolButton()
        close_btn.setText("x")
        logo = QtWidgets.QLabel("upbit")
        logo.setStyleSheet(
            f"background:{UPBIT_BLUE}; color:white; padding:2px 6px; font-weight:bold;"
        )
        symbol_label = QtWidgets.QLabel(f"{DISPLAY_NAMES.get(self.symbol, self.symbol)}")
        symbol_code = QtWidgets.QLabel(self.symbol)
        symbol_code.setStyleSheet("color:#6b7280; font-size:11px;")
        top_row.addWidget(close_btn)
        top_row.addWidget(logo)
        top_row.addWidget(symbol_label)
        top_row.addWidget(symbol_code)
        top_row.addStretch()
        header_layout.addLayout(top_row)

        price_row = QtWidgets.QHBoxLayout()
        self.header_price.setStyleSheet("font-size:20px; font-weight:bold;")
        self.header_change.setStyleSheet("font-size:11px;")
        price_row.addWidget(self.header_price)
        price_row.addWidget(QtWidgets.QLabel("KRW"))
        price_row.addWidget(self.header_change)
        price_row.addStretch()
        header_layout.addLayout(price_row)

        control = QtWidgets.QWidget()
        control_layout = QtWidgets.QHBoxLayout(control)
        control_layout.setContentsMargins(8, 4, 8, 4)
        for tf in TIMEFRAMES_MS:
            self.timeframe_combo.addItem(TIMEFRAME_LABELS.get(tf, str(tf)), tf)
        self.timeframe_combo.currentIndexChanged.connect(self._on_timeframe_change)
        control_layout.addWidget(self.timeframe_combo)
        self.tick_checkbox.setChecked(True)
        control_layout.addWidget(self.tick_checkbox)
        control_layout.addStretch()
        for chip in (self.mode_chip, self.ws_chip, self.burst_chip):
            chip.setStyleSheet(
                "background:#e5e7eb; color:#374151; border-radius:10px; padding:2px 6px; font-size:11px;"
            )
            control_layout.addWidget(chip)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addWidget(control)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.volume)
        layout.setSpacing(0)

    def _on_timeframe_change(self) -> None:
        tf_ms = self.timeframe_combo.currentData()
        if tf_ms:
            self.engine.set_active_timeframe(self.symbol, int(tf_ms))

    def update_snapshot(self, snapshot: Dict[str, Any]) -> None:
        if not snapshot:
            return
        price = snapshot.get("price") or 0.0
        change = snapshot.get("price_change") or 0.0
        percent = snapshot.get("percent_change") or 0.0
        self.header_price.setText(f"{price:,.0f}")
        self.header_change.setText(f"{percent:+.2f}%")
        color = UP_COLOR if change >= 0 else DOWN_COLOR
        self.header_price.setStyleSheet(f"font-size:20px; font-weight:bold; color:{color};")
        self.header_change.setStyleSheet(f"font-size:11px; color:{color};")
        self.mode_chip.setText(snapshot.get("mode", "LIVE"))
        self.ws_chip.setText(f"WS:{snapshot.get('ws_status','OK')}")
        self.burst_chip.setText(snapshot.get("burst_status", "NORMAL"))
        candles = snapshot.get("candles") or []
        self.chart.set_candles(candles)
        self.volume.set_candles(candles)


class DiagnosticPanel(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: Dict[str, QtWidgets.QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QtWidgets.QLabel("Diagnostics")
        title.setStyleSheet("font-weight:bold;")
        layout.addWidget(title)
        for symbol in ["KRW-XRP", "KRW-BTC", "KRW-ETH"]:
            lbl = QtWidgets.QLabel(f"{symbol}: LIVE/OK")
            lbl.setStyleSheet("font-size:11px;")
            self._labels[symbol] = lbl
            layout.addWidget(lbl)
        layout.addStretch()

    def update_diagnostics(self, diag: Dict[str, Any]) -> None:
        symbols = diag.get("symbols", {})
        for symbol, state in symbols.items():
            label = self._labels.get(symbol)
            if not label:
                continue
            age = state.get("last_message_age", 0.0)
            label.setText(f"{symbol}: {state.get('mode')} / {state.get('ws')} / age {age:.1f}s")


class Window1(QtWidgets.QMainWindow):
    def __init__(self, engine, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Upbit Monitor - XRP & BTC")
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        charts = QtWidgets.QHBoxLayout()
        self.xrp_panel = ChartPanel("KRW-XRP", engine)
        self.btc_panel = ChartPanel("KRW-BTC", engine)
        charts.addWidget(self.xrp_panel, 1)
        charts.addWidget(self.btc_panel, 1)
        layout.addLayout(charts, 1)
        self.ticker = ScrollingTicker()
        layout.addWidget(self.ticker)
        self.setCentralWidget(central)


class Window2(QtWidgets.QMainWindow):
    def __init__(self, engine, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Upbit Monitor - ETH & Diagnostics")
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        body = QtWidgets.QHBoxLayout()
        self.eth_panel = ChartPanel("KRW-ETH", engine)
        self.diagnostic_panel = DiagnosticPanel()
        body.addWidget(self.eth_panel, 4)
        body.addWidget(self.diagnostic_panel, 1)
        layout.addLayout(body, 1)
        self.ticker = ScrollingTicker()
        layout.addWidget(self.ticker)
        self.setCentralWidget(central)
