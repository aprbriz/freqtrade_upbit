from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

# pc_app 디렉토리의 부모를 sys.path에 추가 (절대 import 가능하도록)
PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from pc_app.engine import load_or_create_config, resolve_config_path, setup_logging, MainEngine
from pc_app.qt import QtCore, QtWidgets
from pc_app.ui import SshSettingsDialog, Window1, Window2


def _apply_geometry(window: QtWidgets.QWidget, geom: Dict[str, int]) -> None:
    # 운영 중 config 드리프트/누락이 발생해도 KeyError로 앱이 죽지 않도록 기본값으로 방어한다.
    x = int(geom.get("x", 0))
    y = int(geom.get("y", 0))
    width = max(400, int(geom.get("width", 1280)))
    height = max(300, int(geom.get("height", 720)))
    window.setGeometry(x, y, width, height)


def _place_windows(window1: Window1, window2: Window2, config: Dict[str, int]) -> None:
    app = QtWidgets.QApplication.instance()
    screens = app.screens() if app else []
    if len(screens) >= 2:
        _apply_geometry(window1, config.get("window1", {}))
        _apply_geometry(window2, config.get("window2", {}))
        return

    screen = screens[0] if screens else None
    if screen:
        geom = screen.geometry()
        half_height = geom.height() // 2
        window1.setGeometry(geom.x(), geom.y(), geom.width(), half_height)
        window2.setGeometry(geom.x(), geom.y() + half_height, geom.width(), geom.height() - half_height)


def _update_ui(engine: MainEngine, window1: Window1, window2: Window2) -> None:
    snaps = {symbol: engine.get_snapshot(symbol) for symbol in engine.symbols}
    diag = engine.get_diagnostics()

    window1.btc_area.update_snapshot(snaps.get("KRW-BTC", {}))
    window1.eth_area.update_snapshot(snaps.get("KRW-ETH", {}))

    active = window2.active_symbol
    window2.xrp_area.update_snapshot(snaps.get(active, {}))
    window2.update_dashboard(diag, snaps)

    window1.header.update_status({"KRW-BTC": snaps.get("KRW-BTC", {}), "KRW-ETH": snaps.get("KRW-ETH", {})})
    window2.header.update_status(snaps)

    window1.footer.update_status(diag, snaps)
    window2.footer.update_status(diag, snaps)
    window1.header.check_alert(diag)
    window2.header.check_alert(diag)


def _run_ssh_setup_dialog(engine: MainEngine) -> None:
    dialog = SshSettingsDialog(
        initial_settings=engine.get_ssh_settings(),
        test_callback=engine.test_ssh_settings,
    )
    result = dialog.exec()
    if result == QtWidgets.QDialog.Accepted:
        settings, passphrase = dialog.result_payload()
        engine.apply_ssh_settings(settings, passphrase)
    else:
        # 사용자가 취소해도 앱은 중단하지 않고 로컬 DB 폴백으로 계속 실행한다.
        engine.mark_ssh_unavailable("USER_CANCEL")


def main() -> int:
    config = load_or_create_config()
    logger = setup_logging(config)
    engine = MainEngine(config, logger)

    app = QtWidgets.QApplication([])
    _run_ssh_setup_dialog(engine)

    window1 = Window1(engine)
    window2 = Window2(engine)

    _place_windows(window1, window2, config.get("window_positions", {}))

    window1.show()
    window2.show()

    engine.start()

    timer = QtCore.QTimer()
    timer.setInterval(50)
    timer.timeout.connect(lambda: _update_ui(engine, window1, window2))
    timer.start()

    snapshot_timer = QtCore.QTimer()
    snapshot_timer.setInterval(engine.get_snapshot_pull_interval_sec() * 1000)
    snapshot_timer.timeout.connect(lambda: engine.trigger_periodic_snapshot_pull(reason="periodic"))
    snapshot_timer.start()

    def _on_quit() -> None:
        snapshot_timer.stop()
        engine.stop()
        config["window_positions"] = {
            "window1": {
                "x": window1.x(),
                "y": window1.y(),
                "width": window1.width(),
                "height": window1.height(),
                "monitor": 0,
            },
            "window2": {
                "x": window2.x(),
                "y": window2.y(),
                "width": window2.width(),
                "height": window2.height(),
                "monitor": 1,
            },
        }
        config_path = resolve_config_path()
        try:
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except OSError:
            pass

    app.aboutToQuit.connect(_on_quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
