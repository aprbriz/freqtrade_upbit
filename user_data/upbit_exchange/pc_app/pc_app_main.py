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
from pc_app.ui import Window1, Window2


def _apply_geometry(window: QtWidgets.QWidget, geom: Dict[str, int]) -> None:
    window.setGeometry(geom["x"], geom["y"], geom["width"], geom["height"])


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
    window1.xrp_panel.update_snapshot(engine.get_snapshot("KRW-XRP"))
    window1.btc_panel.update_snapshot(engine.get_snapshot("KRW-BTC"))
    window2.eth_panel.update_snapshot(engine.get_snapshot("KRW-ETH"))
    window2.diagnostic_panel.update_diagnostics(engine.get_diagnostics())


def main() -> int:
    config = load_or_create_config()
    logger = setup_logging(config)
    engine = MainEngine(config, logger)

    app = QtWidgets.QApplication([])
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

    def _on_quit() -> None:
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
