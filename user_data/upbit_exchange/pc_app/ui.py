from __future__ import annotations

import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from .engine import Candle, DEFAULT_SSH_CONFIG, DISPLAY_NAMES, TIMEFRAMES_MS
from .qt import QtCore, QtGui, QtWidgets, Signal


TIMEFRAME_LABELS = {
    60_000: "1분",
    300_000: "5분",
    900_000: "15분",
    3_600_000: "1시간",
    14_400_000: "4시간",
    86_400_000: "일봉",
}

KST_OFFSET_SEC = 9 * 3600


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


def fmt_kst(ms: int, fmt: str = "%m/%d %H:%M:%S") -> str:
    try:
        return time.strftime(fmt, time.gmtime((int(ms) / 1000.0) + KST_OFFSET_SEC))
    except Exception:
        return "-"

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
            mode = str(state.get("mode", "LIVE_ACTIVE"))
            if symbol in self._last_ws and self._last_ws[symbol] != ws:
                self._push(f"{symbol} WS 상태 변경: {self._last_ws[symbol]} -> {ws}")
            if symbol in self._last_mode and self._last_mode[symbol] != mode:
                self._push(f"{symbol} 모드 변경: {self._last_mode[symbol]} -> {mode}")
            self._last_ws[symbol] = ws
            self._last_mode[symbol] = mode

    def recent(self, n: int = 5) -> List[str]:
        return list(self.events)[:n]


class _SshTestBridge(QtCore.QObject):
    finished = Signal(bool, str)


class SshSettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        initial_settings: Dict[str, Any],
        test_callback: Callable[[Dict[str, Any], Optional[str]], tuple],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("SSH 로그인/연결 설정")
        self.setModal(True)
        self.setMinimumWidth(620)
        merged = dict(DEFAULT_SSH_CONFIG)
        merged.update(initial_settings or {})
        self._test_callback = test_callback
        self._bridge = _SshTestBridge()
        self._bridge.finished.connect(self._on_test_finished)
        self._test_passed = False
        self._testing = False
        self._result_settings: Dict[str, Any] = {}
        self._result_passphrase: Optional[str] = None

        self.enable_check = QtWidgets.QCheckBox("SSH 기능 사용")
        self.enable_check.setChecked(bool(merged.get("enabled", False)))
        self.host_edit = QtWidgets.QLineEdit(str(merged.get("host", "")))
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(int(merged.get("port", 22)))
        self.user_edit = QtWidgets.QLineEdit(str(merged.get("username", "")))
        self.ppk_edit = QtWidgets.QLineEdit(str(merged.get("ppk_path", "")))
        self.ppk_browse_btn = QtWidgets.QPushButton("찾기")
        self.use_pageant_check = QtWidgets.QCheckBox("Pageant 우선 사용")
        self.use_pageant_check.setChecked(bool(merged.get("use_pageant", True)))
        self.passphrase_edit = QtWidgets.QLineEdit("")
        self.passphrase_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.remote_db_edit = QtWidgets.QLineEdit(str(merged.get("remote_db_path", "")))
        self.remote_snapshot_edit = QtWidgets.QLineEdit(str(merged.get("remote_snapshot_path", "")))
        self.remote_config_edit = QtWidgets.QLineEdit(str(merged.get("remote_config_path", "")))
        self.pull_interval_spin = QtWidgets.QSpinBox()
        self.pull_interval_spin.setRange(60, 3600)
        self.pull_interval_spin.setValue(int(merged.get("pull_interval_sec", 300)))

        self.status_label = QtWidgets.QLabel("연결 테스트 필요")
        self.status_label.setWordWrap(True)
        self.test_btn = QtWidgets.QPushButton("연결 테스트")
        self.apply_btn = QtWidgets.QPushButton("적용")
        self.cancel_btn = QtWidgets.QPushButton("취소")
        self.apply_btn.setEnabled(False if self.enable_check.isChecked() else True)

        self._build_ui()
        self._connect_signals()
        self._on_enable_toggled(self.enable_check.isChecked())

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(self.enable_check)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addRow("Host", self.host_edit)
        form.addRow("Port", self.port_spin)
        form.addRow("Username", self.user_edit)

        ppk_row = QtWidgets.QHBoxLayout()
        ppk_row.setContentsMargins(0, 0, 0, 0)
        ppk_row.addWidget(self.ppk_edit, 1)
        ppk_row.addWidget(self.ppk_browse_btn)
        ppk_box = QtWidgets.QWidget()
        ppk_box.setLayout(ppk_row)
        form.addRow("PPK 경로", ppk_box)

        form.addRow("", self.use_pageant_check)
        form.addRow("Passphrase(입력 가능)", self.passphrase_edit)
        form.addRow("Remote DB", self.remote_db_edit)
        form.addRow("Remote Snapshot", self.remote_snapshot_edit)
        form.addRow("Remote Config", self.remote_config_edit)
        form.addRow("Pull 주기(초)", self.pull_interval_spin)
        layout.addLayout(form)

        info = QtWidgets.QLabel(
            "보안 정책: passphrase는 디스크/명령줄에 저장·전달하지 않습니다. "
            "SSH 인증은 Pageant에 로드된 키를 기본 경로로 사용합니다."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addWidget(self.status_label)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        self.enable_check.toggled.connect(self._on_enable_toggled)
        self.ppk_browse_btn.clicked.connect(self._on_browse_ppk)
        self.test_btn.clicked.connect(self._on_test_clicked)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.cancel_btn.clicked.connect(self.reject)

        widgets = [
            self.host_edit,
            self.user_edit,
            self.ppk_edit,
            self.passphrase_edit,
            self.remote_db_edit,
            self.remote_snapshot_edit,
            self.remote_config_edit,
        ]
        for w in widgets:
            w.textChanged.connect(self._mark_dirty)
        self.port_spin.valueChanged.connect(self._mark_dirty)
        self.pull_interval_spin.valueChanged.connect(self._mark_dirty)
        self.use_pageant_check.toggled.connect(self._mark_dirty)

    def _on_enable_toggled(self, enabled: bool) -> None:
        for widget in (
            self.host_edit,
            self.port_spin,
            self.user_edit,
            self.ppk_edit,
            self.ppk_browse_btn,
            self.use_pageant_check,
            self.passphrase_edit,
            self.remote_db_edit,
            self.remote_snapshot_edit,
            self.remote_config_edit,
            self.pull_interval_spin,
            self.test_btn,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.status_label.setText("SSH 비활성화: 로컬 DB 폴백으로 실행합니다.")
            self.apply_btn.setEnabled(True)
        else:
            self.status_label.setText("연결 테스트 필요")
            self.apply_btn.setEnabled(self._test_passed)

    def _on_browse_ppk(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "PPK 파일 선택",
            self.ppk_edit.text().strip() or str(Path.home()),
            "PuTTY Private Key (*.ppk);;All Files (*)",
        )
        if path:
            self.ppk_edit.setText(path)

    def _mark_dirty(self, *args: Any) -> None:
        self._test_passed = False
        if self.enable_check.isChecked():
            self.apply_btn.setEnabled(False)
            self.status_label.setText("변경 감지: 연결 테스트를 다시 실행하세요.")

    def _collect_settings(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enable_check.isChecked()),
            "host": self.host_edit.text().strip(),
            "port": int(self.port_spin.value()),
            "username": self.user_edit.text().strip(),
            "ppk_path": self.ppk_edit.text().strip(),
            "use_pageant": bool(self.use_pageant_check.isChecked()),
            "remote_db_path": self.remote_db_edit.text().strip(),
            "remote_snapshot_path": self.remote_snapshot_edit.text().strip(),
            "remote_config_path": self.remote_config_edit.text().strip(),
            "pull_interval_sec": int(self.pull_interval_spin.value()),
        }

    def _on_test_clicked(self) -> None:
        if self._testing:
            return
        settings = self._collect_settings()
        if not settings.get("enabled"):
            self._test_passed = True
            self.apply_btn.setEnabled(True)
            self.status_label.setText("SSH 비활성화 상태입니다. 적용 가능합니다.")
            return

        passphrase = self.passphrase_edit.text()
        self._testing = True
        self.test_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.status_label.setText("연결 테스트 중... (UI 블로킹 없음)")

        def _worker() -> None:
            try:
                ok, msg = self._test_callback(settings, passphrase or None)
            except Exception:
                ok, msg = False, "연결 테스트 중 예외 발생"
            self._bridge.finished.emit(bool(ok), str(msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_finished(self, ok: bool, msg: str) -> None:
        self._testing = False
        self.test_btn.setEnabled(True)
        self._test_passed = ok
        self.apply_btn.setEnabled(ok)
        self.status_label.setText(msg if msg else ("연결 성공" if ok else "연결 실패"))

    def _on_apply_clicked(self) -> None:
        settings = self._collect_settings()
        if settings.get("enabled") and not self._test_passed:
            self.status_label.setText("적용 전 연결 테스트가 필요합니다.")
            return
        self._result_settings = settings
        passphrase = self.passphrase_edit.text().strip()
        # 보안 정책: passphrase는 반환만 하고 파일/설정에는 저장하지 않는다.
        self._result_passphrase = passphrase if passphrase else None
        self.accept()

    def result_payload(self) -> tuple:
        return dict(self._result_settings), self._result_passphrase


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
        self.live_chip = StatusChip("● MODE")
        self.ws_chip = StatusChip("● WS")
        self.fresh_chip = StatusChip("● 거래없음 0초")
        self.order_chip = StatusChip("● ORDER")
        self.live_chip_right = StatusChip("● MODE")
        self.ws_chip_right = StatusChip("● WS")
        self.fresh_chip_right = StatusChip("● 거래없음 0초")
        self.order_chip_right = StatusChip("● ORDER")
        self.alert_label = QtWidgets.QLabel("")
        self.alert_label.hide()
        self.theme_label = QtWidgets.QLabel("LIGHT THEME")
        self.theme_btn = QtWidgets.QToolButton()
        self.theme_btn.setText("⚙")
        self.tab_group: Dict[str, QtWidgets.QPushButton] = {}
        self._alert_started_at: Optional[float] = None

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
        self.setFixedHeight(56)
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
        layout.addWidget(self.fresh_chip)
        layout.addWidget(self.order_chip)
        layout.addStretch()
        layout.addWidget(self.alert_label)
        if not self.show_tabs:
            layout.addWidget(self.live_chip_right)
            layout.addWidget(self.ws_chip_right)
            layout.addWidget(self.fresh_chip_right)
            layout.addWidget(self.order_chip_right)

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

    def _order_reason_code(self, state: str, reason: str) -> str:
        raw = str(reason or "").strip().upper()
        if state == "ORDER_LOCKED_DRYRUN":
            return "DRY_RUN"
        if raw.startswith("CFG_PULL_FAIL"):
            return "KEY_LOAD"
        if raw in ("KEY_MISSING", "EXCHANGE_MISSING", "EXCHANGE_NAME_MISSING"):
            return "NO_KEY"
        if raw in ("PPK_NOT_FOUND",):
            return "KEY_PATH"
        if raw.startswith("EXCHANGE_NOT_UPBIT"):
            return "CONFIG"
        if raw in ("SSH_UNAVAILABLE",):
            return "SSH"
        if raw in ("OK",):
            return "READY"
        return raw[:14] if raw else "UNKNOWN"

    def _render_order_chip(self, order_chip: StatusChip, snap: Dict[str, Any]) -> None:
        state = str(snap.get("order_state", "ORDER_LOCKED_DRYRUN"))
        reason = str(snap.get("order_reason", "INIT"))
        code = self._order_reason_code(state, reason)
        if state == "ORDER_KEYS_READY":
            order_chip.setText("● ORDER: READY")
            order_chip.set_kind("ok")
            return
        if state in ("ORDER_LOCKED_DRYRUN", "ORDER_KEYS_ERROR"):
            order_chip.setText(f"● ORDER: LOCKED ({code})")
            order_chip.set_kind("warn")
            return
        order_chip.setText(f"● ORDER: ERROR ({code})")
        order_chip.set_kind("fail")

    def check_alert(self, diag: Dict[str, Any]) -> None:
        symbols = diag.get("symbols", {})
        bad = []
        for symbol, state in symbols.items():
            l1 = str(state.get("ws_l1", "DISCONNECTED"))
            l2 = str(state.get("ws_l2", "UNKNOWN"))
            if l1 != "CONNECTED" or l2 != "ALIVE":
                bad.append(symbol)
        if bad:
            now_ts = time.time()
            if self._alert_started_at is None:
                self._alert_started_at = now_ts
            # 경고 깜빡임을 막기 위해 3초 디바운싱 후에만 노출한다.
            if now_ts - self._alert_started_at >= 3.0:
                self.alert_label.setText(f"경고: WS 상태 불안정 ({', '.join(bad)})")
                self.alert_label.show()
            t = ThemeManager.current()
            self.alert_label.setStyleSheet(
                f"font-size:11px; font-weight:500; color:{t['status-warn']};"
                f"background:{t['status-warn-dim']}; border:1px solid {t['status-warn-medium']};"
                "border-radius:6px; padding:2px 10px;"
            )
        else:
            self._alert_started_at = None
            self.alert_label.hide()

    def update_status(self, snaps: Dict[str, Dict[str, Any]]) -> None:
        ordered = [snaps[k] for k in sorted(snaps.keys()) if snaps.get(k)]
        left = ordered[0] if ordered else {}
        right = ordered[1] if len(ordered) > 1 else {}

        def _set_pair(
            live_chip: StatusChip,
            ws_chip: StatusChip,
            fresh_chip: StatusChip,
            order_chip: StatusChip,
            snap: Dict[str, Any],
        ) -> None:
            mode = str(snap.get("mode", "DB_ONLY"))
            live_chip.setText(f"● {mode}")
            live_chip.set_kind("ok" if mode == "LIVE_ACTIVE" else "warn")

            ws_l1 = str(snap.get("ws_l1", "DISCONNECTED"))
            ws_l2 = str(snap.get("ws_l2", "UNKNOWN"))
            ws_chip.setText(f"● WS {ws_l1}/{ws_l2}")
            if ws_l1 == "CONNECTED" and ws_l2 == "ALIVE":
                ws_chip.set_kind("ok")
            elif ws_l1 == "CONNECTED" and (ws_l2.startswith("PARTIAL(") or ws_l2 in ("GLOBAL_SILENT", "RATE_LIMITED", "DEGRADED")):
                ws_chip.set_kind("warn")
            elif ws_l1 in ("CONNECTING", "RECONNECTING", "RECONNECT_WAIT"):
                ws_chip.set_kind("warn")
            else:
                ws_chip.set_kind("fail")

            age = float(snap.get("last_trade_age_sec", snap.get("last_message_age", 0.0)))
            fresh_chip.setText(f"● 거래없음 {int(age)}초")
            fresh_chip.set_kind("neutral")

            self._render_order_chip(order_chip, snap)

        _set_pair(self.live_chip, self.ws_chip, self.fresh_chip, self.order_chip, left)
        _set_pair(
            self.live_chip_right,
            self.ws_chip_right,
            self.fresh_chip_right,
            self.order_chip_right,
            right if right else left,
        )

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
        self._cutover_ts: Optional[int] = None
        self._timeframe_ms: Optional[int] = None
        self.setMinimumHeight(280)

    def set_candles(self, candles: List[Candle]) -> None:
        self._candles = candles
        self.update()

    def set_markers(self, cutover_ts: Optional[int], timeframe_ms: Optional[int]) -> None:
        self._cutover_ts = int(cutover_ts) if cutover_ts else None
        self._timeframe_ms = int(timeframe_ms) if timeframe_ms else None
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

        # 장애 시에는 보간하지 않고 "갭"만 시각화해서 데이터 무결성 판단을 돕는다.
        if self._timeframe_ms and len(candles) >= 2:
            gap_threshold = float(self._timeframe_ms) * 1.5
            gap_brush = parse_color(t["status-warn-dim"])
            gap_pen = parse_color(t["status-warn"])
            for i in range(1, len(candles)):
                gap = candles[i].ts_ms - candles[i - 1].ts_ms
                if gap <= gap_threshold:
                    continue
                x_prev = plot.left() + int((i - 1) * step)
                x_curr = plot.left() + int(i * step)
                left = min(x_prev, x_curr)
                width = max(2, abs(x_curr - x_prev))
                p.fillRect(QtCore.QRect(left, plot.top(), width, plot.height()), gap_brush)
                p.setPen(gap_pen)
                p.drawText(left + 2, plot.top() + 12, "GAP")

        if self._cutover_ts is not None:
            marker_index: Optional[int] = None
            for i, candle in enumerate(candles):
                if candle.ts_ms >= self._cutover_ts:
                    marker_index = i
                    break
            if marker_index is not None:
                x = plot.left() + int(marker_index * step)
                p.setPen(parse_color(t["status-ok"]))
                p.drawLine(x, plot.top(), x, plot.bottom())
                p.drawText(x + 4, plot.top() + 12, f"LIVE 시작 {fmt_kst(self._cutover_ts, '%H:%M:%S')}")

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
        top.setFixedHeight(60)
        top_l = QtWidgets.QVBoxLayout(top)
        top_l.setContentsMargins(10, 6, 10, 6)
        top_l.setSpacing(4)

        title_row = QtWidgets.QHBoxLayout()
        self.title.setText(self._format_symbol())
        self.title.setStyleSheet("font-size:13px; font-weight:600;")
        title_row.addWidget(self.title)
        title_row.addStretch()
        self.tf_combo.setFixedWidth(90)
        for tf in TIMEFRAMES_MS:
            self.tf_combo.addItem(TIMEFRAME_LABELS.get(tf, str(tf)), tf)
        self.tf_combo.currentIndexChanged.connect(self._on_tf_changed)
        title_row.addWidget(self.tf_combo)
        top_l.addLayout(title_row)

        price_row = QtWidgets.QHBoxLayout()
        self.price.setStyleSheet("font-size:28px; font-weight:700;")
        self.change.setStyleSheet("font-size:12px;")
        price_row.addWidget(self.price)
        price_row.addWidget(self.change)
        price_row.addStretch()
        top_l.addLayout(price_row)

        layout.addWidget(top)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.volume)

    def _on_tf_changed(self) -> None:
        tf_ms = self.tf_combo.currentData()
        if tf_ms:
            self.engine.set_active_timeframe(self.symbol, int(tf_ms))

    def set_symbol(self, symbol: str) -> None:
        self.symbol = symbol
        self.title.setText(self._format_symbol())
        self._on_tf_changed()

    def update_snapshot(self, snap: Dict[str, Any]) -> None:
        if not snap:
            return
        self._snapshot = snap
        symbol = snap.get("symbol", self.symbol)
        self.symbol = symbol
        tf_ms = snap.get("timeframe_ms")
        self.title.setText(self._format_symbol())
        price = float(snap.get("price") or 0.0)
        delta = float(snap.get("price_change") or 0.0)
        pct = float(snap.get("percent_change") or 0.0)
        arrow = "▲" if delta >= 0 else "▼"
        self.price.setText(f"{price:,.0f}")
        self.change.setText(f"{delta:,.0f} ({pct:+.2f}%) {arrow}")
        t = ThemeManager.current()
        col = t["chart-up"] if delta >= 0 else t["chart-down"]
        self.price.setStyleSheet(f"font-size:28px; font-weight:700; color:{col};")
        self.change.setStyleSheet(f"font-size:12px; color:{col};")

        candles = snap.get("candles") or []
        self.chart.set_candles(candles)
        self.chart.set_markers(
            cutover_ts=snap.get("cutover_ts"),
            timeframe_ms=int(tf_ms) if tf_ms else None,
        )
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
        self.title.setStyleSheet(f"font-size:13px; font-weight:600; color:{t['text-secondary']};")
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
        for key in ("WS ETH", "WS XRP", "WS BTC", "DB Snapshot", "SSH"):
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
            l1 = str(st.get("ws_l1", "DISCONNECTED"))
            l2 = str(st.get("ws_l2", "UNKNOWN"))
            age = float(st.get("last_trade_age_sec", st.get("last_message_age", 0.0)))
            self.rows[key].setText(f"{l1}/{l2} | 거래없음 {int(age)}초")
        db_state = diag.get("db_snapshot", {})
        ssh_state = diag.get("ssh", {})
        self.rows["DB Snapshot"].setText(str(db_state.get("status", "IDLE")))
        self.rows["SSH"].setText(str(ssh_state.get("status", "UNCONFIGURED")))

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
        layout.setSpacing(1)
        for _ in range(5):
            lbl = QtWidgets.QLabel("-")
            lbl.setContentsMargins(0, 0, 0, 0)
            self.items.append(lbl)
            layout.addWidget(lbl)
        layout.addSpacing(2)
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
    def __init__(self, event_store: EventStore, engine, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.event_store = event_store
        self.engine = engine
        self.tiles = {
            "ws": KpiTile("WS 연결"),
            "db": KpiTile("DB Write Lag"),
            "recv": KpiTile("수신 지연"),
            "reconnect": KpiTile("Reconnect"),
            "rate": KpiTile("수신율"),
            "err": KpiTile("에러율"),
        }
        self.control_box = QtWidgets.QFrame()
        self.control_symbol = QtWidgets.QComboBox()
        self.live_btn = QtWidgets.QPushButton("LIVE 시작/유지")
        self.db_btn = QtWidgets.QPushButton("DB로 전환(안정)")
        self.ack_btn = QtWidgets.QPushButton("BURST 알림 ACK")
        self.control_hint = QtWidgets.QLabel("-")
        self.connection = ConnectionSection()
        self.timeline = EventTimeline()
        self._build_ui()
        self._connect_signals()
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
        control_layout = QtWidgets.QVBoxLayout(self.control_box)
        control_layout.setContentsMargins(10, 8, 10, 8)
        control_layout.setSpacing(6)
        head = QtWidgets.QLabel("운영 수동 제어")
        control_layout.addWidget(head)
        self.control_symbol.clear()
        for symbol in ("KRW-BTC", "KRW-ETH", "KRW-XRP"):
            self.control_symbol.addItem(DISPLAY_NAMES.get(symbol, symbol), symbol)
        control_layout.addWidget(self.control_symbol)
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(self.live_btn)
        row1.addWidget(self.db_btn)
        control_layout.addLayout(row1)
        control_layout.addWidget(self.ack_btn)
        self.control_hint.setWordWrap(True)
        control_layout.addWidget(self.control_hint)
        self.control_box.setProperty("box-title", head)
        layout.addWidget(self.control_box)
        layout.addWidget(self.connection)
        layout.addWidget(self.timeline, 1)

    def _connect_signals(self) -> None:
        self.live_btn.clicked.connect(self._on_live_clicked)
        self.db_btn.clicked.connect(self._on_db_clicked)
        self.ack_btn.clicked.connect(self._on_ack_clicked)

    def _selected_symbol(self) -> str:
        symbol = self.control_symbol.currentData()
        return str(symbol) if symbol else "KRW-XRP"

    def _on_live_clicked(self) -> None:
        self.engine.set_symbol_mode(self._selected_symbol(), "LIVE_ACTIVE")

    def _on_db_clicked(self) -> None:
        self.engine.set_symbol_mode(self._selected_symbol(), "DB_ONLY")

    def _on_ack_clicked(self) -> None:
        self.engine.acknowledge_burst_alert()

    def _control_reason_text(self, reason: str) -> str:
        mapping = {
            "OK": "제어 가능",
            "DB_SNAPSHOT_RUNNING": "DB 동기화 중에는 버튼이 잠깁니다.",
            "WS_RECOVERING": "WS 복구 중에는 일부 버튼이 잠깁니다.",
            "SYMBOL_NOT_FOUND": "심볼 상태를 찾을 수 없습니다.",
        }
        return mapping.get(reason, reason)

    def update_dashboard(self, diag: Dict[str, Any], snaps: Dict[str, Dict[str, Any]]) -> None:
        symbols = diag.get("symbols", {})
        ages = [float(v.get("last_trade_age_sec", v.get("last_message_age", 0.0))) for v in symbols.values()]
        max_age = max(ages) if ages else 0.0
        ws_ok = all(
            str(v.get("ws_l1", "")) == "CONNECTED" and str(v.get("ws_l2", "")) == "ALIVE"
            for v in symbols.values()
        ) if symbols else False
        reconnects = sum(
            1 for v in symbols.values() if str(v.get("ws_l1", "")) in ("RECONNECTING", "RECONNECT_WAIT")
        )
        db_state = diag.get("db_snapshot", {})
        ssh_state = diag.get("ssh", {})
        ws_rate_limit = diag.get("ws_rate_limit", {}) or {}
        self.tiles["ws"].set_data("OK" if ws_ok else "WARN", f"{len(symbols)} 심볼")
        self.tiles["db"].set_data(str(db_state.get("status", "IDLE")), "DB snapshot")
        self.tiles["recv"].set_data(f"{max_age:.1f}s", "max 거래없음")
        self.tiles["reconnect"].set_data(str(reconnects), "최근 상태")
        self.tiles["rate"].set_data(
            f"{ws_rate_limit.get('subscribe_window_1s', 0)}/s",
            f"sub {ws_rate_limit.get('subscribe_window_1m', 0)}/m",
        )
        self.tiles["err"].set_data(str(ssh_state.get("status", "UNCONFIGURED")), "SSH")
        state = self.engine.get_manual_control_state(self._selected_symbol())
        can_live = bool(state.get("can_live", False))
        can_db = bool(state.get("can_db", False))
        reason = str(state.get("reason", "OK"))
        self.live_btn.setEnabled(can_live)
        self.db_btn.setEnabled(can_db)
        self.ack_btn.setEnabled(bool(state.get("can_ack", True)))
        hint = self._control_reason_text(reason)
        self.control_hint.setText(hint)
        self.live_btn.setToolTip(hint if not can_live else "")
        self.db_btn.setToolTip(hint if not can_db else "")
        self.connection.update_data(diag)
        self.timeline.update_events(self.event_store.recent(5))

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.setStyleSheet(f"background:{t['bg-base']};")
        self.control_box.setStyleSheet(
            f"background:{t['bg-surface']}; border:1px solid {t['border-subtle']}; border-radius:6px;"
        )
        title = self.control_box.property("box-title")
        if isinstance(title, QtWidgets.QLabel):
            title.setStyleSheet(f"font-size:11px; font-weight:600; color:{t['text-primary']};")
        self.control_symbol.setStyleSheet(
            f"background:{t['bg-base']}; color:{t['text-primary']}; border:1px solid {t['border-subtle']}; border-radius:4px; padding:3px 6px;"
        )
        btn_style = (
            f"QPushButton{{background:{t['bg-elevated']}; color:{t['text-primary']}; border:1px solid {t['border-subtle']};"
            "border-radius:4px; padding:4px 8px; font-size:11px; font-weight:600;}"
            f"QPushButton:disabled{{color:{t['text-quaternary']}; background:{t['bg-surface']};}}"
        )
        self.live_btn.setStyleSheet(btn_style)
        self.db_btn.setStyleSheet(btn_style)
        self.ack_btn.setStyleSheet(btn_style)
        self.control_hint.setStyleSheet(f"font-size:10px; color:{t['text-tertiary']};")


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
        ages = [float(v.get("last_trade_age_sec", v.get("last_message_age", 0.0))) for v in symbols.values()]
        age = max(ages) if ages else 0.0
        db_state = diag.get("db_snapshot", {})
        reconnects = sum(
            1 for v in symbols.values() if str(v.get("ws_l1", "")) in ("RECONNECTING", "RECONNECT_WAIT")
        )
        uptime = int(time.time() - self._boot)
        mm = uptime // 60
        ss = uptime % 60
        control_events = diag.get("control_events", [])
        latest_event = ""
        if control_events:
            first = str(control_events[0])
            latest_event = first.split("|", 1)[1].strip() if "|" in first else first
        self.label.setText(
            f"● 거래없음 최대 {age:.1f}s | Reconnects {reconnects} | DB {db_state.get('status', 'IDLE')} | "
            f"표시정책 최신 스냅샷 우선 | Uptime {mm}m {ss:02d}s"
            + (f" | {latest_event}" if latest_event else "")
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
        self.header = HeaderBar(show_tabs=False)
        self.btc_area = ChartArea(engine, "KRW-BTC")
        self.eth_area = ChartArea(engine, "KRW-ETH")
        self.footer = FooterBar()

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
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
        self.header = HeaderBar(show_tabs=True)
        self.xrp_area = ChartArea(engine, self.active_symbol)
        self.dashboard = DashboardPanel(self.event_store, engine)
        self.footer = FooterBar()

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
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
        combo = self.dashboard.control_symbol
        for i in range(combo.count()):
            if combo.itemData(i) == symbol:
                combo.setCurrentIndex(i)
                break

    def update_dashboard(self, diag: Dict[str, Any], snaps: Dict[str, Dict[str, Any]]) -> None:
        self.event_store.update(diag, snaps)
        self.dashboard.update_dashboard(diag, snaps)

    def apply_theme(self) -> None:
        t = ThemeManager.current()
        self.centralWidget().setStyleSheet(f"background:{t['bg-base']};")
