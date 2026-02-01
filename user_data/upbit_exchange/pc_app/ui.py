from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import TIMEFRAMES_MS, Candle, DISPLAY_NAMES
from .qt import QtCore, QtGui, QtWidgets


UPBIT_BLUE = "#0051c7"
CHART_BG = "#0a1929"
UP_COLOR = "#f23645"
DOWN_COLOR = "#2979ff"
TICKER_BG = "#fef9c3"
TICKER_BORDER = "#fef08a"
LIGHT_BG = "#f9fafb"
BORDER_COLOR = "#e5e7eb"
TEXT_MUTED = "#6b7280"


TIMEFRAME_LABELS = {
    60_000: "1분",
    300_000: "5분",
    900_000: "15분",
    3_600_000: "1시간",
    14_400_000: "4시간",
    86_400_000: "일봉",
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
        self.high_label = QtWidgets.QLabel("고가 -")
        self.low_label = QtWidgets.QLabel("저가 -")
        self.volume_label = QtWidgets.QLabel("거래대금(24H) -")

        self.ws_chip = QtWidgets.QLabel("WS:OK(0s)")
        self.mode_chip = QtWidgets.QLabel("LIVE")
        self.burst_chip = QtWidgets.QLabel("NORMAL")
        self.gap_chip = QtWidgets.QLabel("GAP")
        self.gap_chip.setVisible(False)

        self.symbol_combo = QtWidgets.QComboBox()
        self.timeframe_combo = QtWidgets.QComboBox()
        self.tick_checkbox = QtWidgets.QCheckBox("틱 레이어")
        self.chart = CandleChartWidget()
        self.volume = VolumeChartWidget()

        self._build_ui()

    def _load_logo_pixmap(self) -> Optional[QtGui.QPixmap]:
        candidates: List[Path] = []
        logo_path = None
        if hasattr(self.engine, "config"):
            logo_path = self.engine.config.get("logo_path")
        if logo_path:
            path = Path(logo_path)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent / path
            candidates.append(path)
        candidates.append(Path(__file__).resolve().parent / "assets" / "upbit_logo.png")
        for path in candidates:
            if path and path.exists():
                pixmap = QtGui.QPixmap(str(path))
                if not pixmap.isNull():
                    return pixmap
        return None

    def _format_symbol(self, symbol: str) -> str:
        parts = symbol.split("-")
        if len(parts) == 2:
            return f"{parts[1]}/{parts[0]}"
        return symbol.replace("-", "/")

    def _make_chip(self, text: str) -> QtWidgets.QLabel:
        chip = QtWidgets.QLabel(text)
        chip.setAlignment(QtCore.Qt.AlignCenter)
        chip.setStyleSheet(
            "border-radius:10px; padding:2px 6px; font-size:11px; font-weight:bold;"
        )
        return chip

    def _apply_chip_style(self, chip: QtWidgets.QLabel, kind: str, value: str) -> None:
        value_upper = (value or "").upper()
        if kind == "mode":
            if value_upper == "LIVE":
                bg, fg = "#d1fae5", "#047857"
            elif value_upper == "DB":
                bg, fg = "#dbeafe", "#1d4ed8"
            else:
                bg, fg = "#fef3c7", "#92400e"
        elif kind == "ws":
            if value_upper == "OK":
                bg, fg = "#d1fae5", "#047857"
            elif value_upper in {"RECONNECT", "WARN"}:
                bg, fg = "#ffedd5", "#c2410c"
            else:
                bg, fg = "#fee2e2", "#b91c1c"
        else:
            if value_upper == "NORMAL":
                bg, fg = "#f3f4f6", "#374151"
            elif value_upper == "ACTIVE":
                bg, fg = "#fee2e2", "#b91c1c"
            else:
                bg, fg = "#fef3c7", "#92400e"
        chip.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:10px; padding:2px 6px; font-size:11px; font-weight:bold;"
        )

    def _build_ui(self) -> None:
        header = QtWidgets.QFrame()
        header.setStyleSheet(f"background:white; border-bottom:1px solid {BORDER_COLOR};")
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)

        top_row = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QToolButton()
        close_btn.setText("×")
        close_btn.setStyleSheet("color:#6b7280; font-size:14px;")

        logo_label = QtWidgets.QLabel()
        logo_pixmap = self._load_logo_pixmap()
        if logo_pixmap:
            logo_label.setPixmap(logo_pixmap.scaledToHeight(18, QtCore.Qt.SmoothTransformation))
        else:
            logo_label.setText("UPbit")
            logo_label.setStyleSheet(
                f"background:{UPBIT_BLUE}; color:white; padding:2px 6px; font-weight:bold;"
            )

        symbol_name = QtWidgets.QLabel(f"{DISPLAY_NAMES.get(self.symbol, self.symbol)}")
        symbol_name.setStyleSheet("font-weight:bold; font-size:13px;")
        symbol_code = QtWidgets.QLabel(self._format_symbol(self.symbol))
        symbol_code.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        down_label = QtWidgets.QLabel("▼")
        down_label.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px;")

        tabs = QtWidgets.QHBoxLayout()
        tab_price = QtWidgets.QLabel("시세")
        tab_price.setStyleSheet("color:#2563eb; border-bottom:2px solid #2563eb; font-weight:600; font-size:11px;")
        tab_info = QtWidgets.QLabel("정보")
        tab_info.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        tab_insight = QtWidgets.QLabel("마켓 인사이트")
        tab_insight.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        tabs.addWidget(tab_price)
        tabs.addSpacing(12)
        tabs.addWidget(tab_info)
        tabs.addSpacing(12)
        tabs.addWidget(tab_insight)

        top_row.addWidget(close_btn)
        top_row.addSpacing(4)
        top_row.addWidget(logo_label)
        top_row.addSpacing(6)
        top_row.addWidget(symbol_name)
        top_row.addWidget(symbol_code)
        top_row.addWidget(down_label)
        top_row.addStretch()
        top_row.addLayout(tabs)
        header_layout.addLayout(top_row)

        price_row = QtWidgets.QHBoxLayout()
        self.header_price.setStyleSheet("font-size:22px; font-weight:bold;")
        self.header_change.setStyleSheet("font-size:11px;")
        price_row.addWidget(self.header_price)
        krw = QtWidgets.QLabel("KRW")
        krw.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px;")
        price_row.addWidget(krw)
        price_row.addWidget(self.header_change)
        price_row.addStretch()
        for label in (self.high_label, self.low_label, self.volume_label):
            label.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px;")
            price_row.addWidget(label)
            price_row.addSpacing(8)
        header_layout.addLayout(price_row)

        control = QtWidgets.QFrame()
        control.setStyleSheet(f"background:{LIGHT_BG}; border-bottom:1px solid {BORDER_COLOR};")
        control_layout = QtWidgets.QHBoxLayout(control)
        control_layout.setContentsMargins(10, 4, 10, 4)

        self.symbol_combo.addItem(self._format_symbol(self.symbol))
        self.symbol_combo.setEnabled(False)
        self.symbol_combo.setStyleSheet(
            "padding:2px 6px; border:1px solid #d1d5db; border-radius:4px; font-size:11px;"
        )
        control_layout.addWidget(self.symbol_combo)

        for tf in TIMEFRAMES_MS:
            self.timeframe_combo.addItem(TIMEFRAME_LABELS.get(tf, str(tf)), tf)
        self.timeframe_combo.currentIndexChanged.connect(self._on_timeframe_change)
        self.timeframe_combo.setStyleSheet(
            "padding:2px 6px; border:1px solid #d1d5db; border-radius:4px; font-size:11px;"
        )
        control_layout.addWidget(self.timeframe_combo)

        self.tick_checkbox.setChecked(True)
        self.tick_checkbox.setStyleSheet("font-size:11px;")
        control_layout.addWidget(self.tick_checkbox)

        settings_btn = QtWidgets.QPushButton("설정")
        indicator_btn = QtWidgets.QPushButton("지표")
        for btn in (settings_btn, indicator_btn):
            btn.setStyleSheet(
                "padding:2px 6px; border:1px solid #d1d5db; border-radius:4px; font-size:11px;"
            )
        control_layout.addWidget(settings_btn)
        control_layout.addWidget(indicator_btn)
        control_layout.addStretch()

        for chip in (self.mode_chip, self.ws_chip, self.burst_chip, self.gap_chip):
            control_layout.addWidget(chip)
        self._apply_chip_style(self.mode_chip, "mode", self.mode_chip.text())
        self._apply_chip_style(self.ws_chip, "ws", "OK")
        self._apply_chip_style(self.burst_chip, "burst", self.burst_chip.text())

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addWidget(control)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.volume)
        layout.setSpacing(0)

        active_tf = self.engine.active_timeframes.get(self.symbol)
        if active_tf:
            for idx in range(self.timeframe_combo.count()):
                if self.timeframe_combo.itemData(idx) == active_tf:
                    self.timeframe_combo.setCurrentIndex(idx)
                    break

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
        last_age = snapshot.get("last_message_age") or 0.0
        ws_status = snapshot.get("ws_status", "OK")
        mode = snapshot.get("mode", "LIVE")
        burst = snapshot.get("burst_status", "NORMAL")
        self.header_price.setText(f"{price:,.0f}")
        arrow = "▲" if change >= 0 else "▼"
        self.header_change.setText(f"{percent:+.2f}% {arrow}{abs(change):,.0f}")
        color = UP_COLOR if change >= 0 else DOWN_COLOR
        self.header_price.setStyleSheet(f"font-size:22px; font-weight:bold; color:{color};")
        self.header_change.setStyleSheet(f"font-size:11px; color:{color};")
        self.mode_chip.setText(mode)
        self.ws_chip.setText(f"WS:{ws_status}({last_age:.0f}s)")
        self.burst_chip.setText(burst)
        self._apply_chip_style(self.mode_chip, "mode", mode)
        self._apply_chip_style(self.ws_chip, "ws", ws_status)
        self._apply_chip_style(self.burst_chip, "burst", burst)

        candles = snapshot.get("candles") or []
        if candles:
            high = max(c.high for c in candles)
            low = min(c.low for c in candles)
            volume = sum(c.volume for c in candles)
            self.high_label.setText(f"고가 {high:,.0f}")
            self.low_label.setText(f"저가 {low:,.0f}")
            self.volume_label.setText(f"거래대금(24H) {volume:,.0f} KRW")
        else:
            self.high_label.setText("고가 -")
            self.low_label.setText("저가 -")
            self.volume_label.setText("거래대금(24H) -")
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
        layout.setSpacing(8)

        def make_card(title: str) -> QtWidgets.QVBoxLayout:
            card = QtWidgets.QFrame()
            card.setStyleSheet(
                "background:white; border:1px solid #e5e7eb; border-radius:4px;"
            )
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            heading = QtWidgets.QLabel(title)
            heading.setStyleSheet("font-weight:bold; font-size:11px; color:#374151;")
            card_layout.addWidget(heading)
            layout.addWidget(card)
            return card_layout

        def add_row(card_layout: QtWidgets.QVBoxLayout, label: str, key: str) -> None:
            row = QtWidgets.QHBoxLayout()
            left = QtWidgets.QLabel(label)
            left.setStyleSheet("color:#6b7280; font-size:10px;")
            right = QtWidgets.QLabel("-")
            right.setStyleSheet("font-size:10px;")
            row.addWidget(left)
            row.addStretch()
            row.addWidget(right)
            card_layout.addLayout(row)
            self._labels[key] = right

        card = make_card("시스템 상태")
        add_row(card, "심볼/TF:", "sys_symbol")
        add_row(card, "모드:", "sys_mode")
        add_row(card, "WS 상태:", "sys_ws")
        add_row(card, "BURST:", "sys_burst")

        card = make_card("타임스탬프")
        add_row(card, "Now (KST):", "ts_now")
        add_row(card, "Last Tick:", "ts_last")
        add_row(card, "Age:", "ts_age")
        add_row(card, "Cutover TS:", "ts_cutover")

        card = make_card("Overlay 범위")
        add_row(card, "Start:", "overlay_start")
        add_row(card, "End:", "overlay_end")
        add_row(card, "Horizon:", "overlay_horizon")
        add_row(card, "Max Candles:", "overlay_max")

        card = make_card("DB Catch-up")
        add_row(card, "DB Latest:", "db_latest")
        add_row(card, "Overlay Latest:", "db_overlay_latest")
        add_row(card, "상태:", "db_state")

        card = make_card("데이터 품질")
        add_row(card, "Invalid Trades:", "dq_invalid")
        add_row(card, "OOO Corrected:", "dq_corrected")
        add_row(card, "OOO Dropped:", "dq_dropped")

        card = make_card("연결 요약")
        add_row(card, "Connected Since:", "conn_since")
        add_row(card, "Reconnect Attempts:", "conn_reconnect")
        status = QtWidgets.QLabel("✓ 연결 안정")
        status.setStyleSheet("background:#ecfdf3; color:#047857; padding:2px 4px; font-size:10px;")
        card.addWidget(status)
        self._labels["conn_status"] = status

        card = make_card("BURST 지표")
        add_row(card, "Tick Rate:", "burst_tick")
        add_row(card, "Notional Rate:", "burst_notional")
        add_row(card, "Abs Return Rate:", "burst_return")

        card = make_card("최근 갭 이벤트")
        for idx in range(3):
            gap = QtWidgets.QLabel("N/A")
            gap.setStyleSheet("font-size:10px; color:#6b7280; background:#f3f4f6; padding:2px;")
            card.addWidget(gap)
            self._labels[f"gap_{idx}"] = gap

        button_wrap = QtWidgets.QFrame()
        button_wrap.setStyleSheet("background:white; border-top:1px solid #e5e7eb;")
        button_layout = QtWidgets.QVBoxLayout(button_wrap)
        button_layout.setContentsMargins(8, 6, 8, 6)
        for text, color in [
            ("LIVE 시작/유지", "#16a34a"),
            ("DB로 전환 (안정)", "#2563eb"),
            ("BURST 알림 ACK", "#4b5563"),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setStyleSheet(
                f"background:{color}; color:white; padding:6px; border-radius:4px; font-size:11px;"
            )
            button_layout.addWidget(btn)
        layout.addWidget(button_wrap)
        layout.addStretch()

    def update_diagnostics(self, diag: Dict[str, Any], eth_snapshot: Dict[str, Any] | None = None) -> None:
        symbols = diag.get("symbols", {})
        eth_state = symbols.get("KRW-ETH", {})
        now_ms = diag.get("now_ms") or 0
        now_text = datetime.fromtimestamp(now_ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if now_ms else "-"
        last_trade_ts = eth_state.get("last_trade_ts") or 0
        last_trade_text = (
            datetime.fromtimestamp(last_trade_ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if last_trade_ts
            else "-"
        )
        age = eth_state.get("last_message_age", 0.0)
        mode = eth_state.get("mode", "LIVE")
        ws = eth_state.get("ws", "OK")
        burst = eth_state.get("burst", "NORMAL")
        timeframe = "-"
        if eth_snapshot:
            tf_ms = eth_snapshot.get("timeframe_ms")
            if tf_ms:
                timeframe = TIMEFRAME_LABELS.get(int(tf_ms), f"{tf_ms}ms")

        symbol_text = "KRW-ETH"
        if eth_snapshot and eth_snapshot.get("symbol"):
            parts = str(eth_snapshot.get("symbol")).split("-")
            if len(parts) == 2:
                symbol_text = f"{parts[1]}/{parts[0]}"
        self._labels["sys_symbol"].setText(f"{symbol_text} / {timeframe}")
        self._labels["sys_mode"].setText(mode)
        self._labels["sys_ws"].setText(ws)
        self._labels["sys_burst"].setText(burst)

        self._labels["ts_now"].setText(now_text)
        self._labels["ts_last"].setText(last_trade_text)
        self._labels["ts_age"].setText(f"{age:.1f}s")
        self._labels["ts_cutover"].setText("-")

        self._labels["overlay_start"].setText("-")
        self._labels["overlay_end"].setText("-")
        self._labels["overlay_horizon"].setText("-")
        self._labels["overlay_max"].setText("-")

        self._labels["db_latest"].setText("-")
        self._labels["db_overlay_latest"].setText("-")
        self._labels["db_state"].setText("-")

        self._labels["dq_invalid"].setText("0")
        self._labels["dq_corrected"].setText("0")
        self._labels["dq_dropped"].setText("0")

        self._labels["conn_since"].setText("-")
        self._labels["conn_reconnect"].setText("0")

        self._labels["burst_tick"].setText("-")
        self._labels["burst_notional"].setText("-")
        self._labels["burst_return"].setText("-")

        for idx in range(3):
            self._labels[f"gap_{idx}"].setText("N/A")


class TopNavBar(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{UPBIT_BLUE}; color:white;")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)

        nav = QtWidgets.QHBoxLayout()
        for label in ("거래소", "입출금", "투자내역", "코인동향"):
            item = QtWidgets.QLabel(label)
            item.setStyleSheet("font-size:11px;")
            nav.addWidget(item)
            nav.addSpacing(10)
        nav_widget = QtWidgets.QWidget()
        nav_widget.setLayout(nav)
        layout.addWidget(nav_widget)
        layout.addStretch()

        badge = QtWidgets.QLabel("UPbit Biz")
        badge.setStyleSheet(
            "background:white; color:#0051c7; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold;"
        )
        layout.addWidget(badge)


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
        layout.addWidget(TopNavBar())
        body = QtWidgets.QHBoxLayout()
        self.eth_panel = ChartPanel("KRW-ETH", engine)
        self.diagnostic_panel = DiagnosticPanel()
        body.addWidget(self.eth_panel, 4)
        body.addWidget(self.diagnostic_panel, 1)
        layout.addLayout(body, 1)
        self.ticker = ScrollingTicker()
        layout.addWidget(self.ticker)
        self.setCentralWidget(central)
