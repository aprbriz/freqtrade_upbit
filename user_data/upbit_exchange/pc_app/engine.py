from __future__ import annotations

import json
import logging
import logging.handlers
import os
import random
import sqlite3
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple


SYMBOLS = ["KRW-XRP", "KRW-BTC", "KRW-ETH"]
DISPLAY_NAMES = {
    "KRW-XRP": "XRP",
    "KRW-BTC": "BTC",
    "KRW-ETH": "ETH",
}

TIMEFRAMES_MS = [
    60_000,    # 1m
    300_000,   # 5m
    900_000,   # 15m
    3_600_000, # 1h
    14_400_000, # 4h
    86_400_000, # 1d
]

DEFAULT_TIMEFRAME_MS = 3_600_000


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def get_config_path() -> Path:
    local_path = Path(__file__).with_name("config.json")
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "UpbitRealTimeChart" / "config.json"
    return local_path


def resolve_config_path() -> Path:
    local_path = Path(__file__).with_name("config.json")
    if local_path.exists():
        return local_path
    appdata_path = get_config_path()
    if appdata_path.exists():
        return appdata_path
    return local_path


def load_or_create_config() -> Dict[str, Any]:
    config_path = resolve_config_path()
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    default = {
        "symbols": SYMBOLS,
        "default_timeframe_ms": DEFAULT_TIMEFRAME_MS,
        "db_path": "ohlcv_short.sqlite",
        "logo_path": "assets/upbit_logo.png",
        "initial_candles": 600,
        "window_positions": {
            "window1": {"x": 0, "y": 0, "width": 1920, "height": 1080, "monitor": 0},
            "window2": {"x": 1920, "y": 0, "width": 1920, "height": 1080, "monitor": 1},
        },
        "log_path": None,
    }

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    except OSError:
        appdata_path = get_config_path()
        appdata_path.parent.mkdir(parents=True, exist_ok=True)
        with appdata_path.open("w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    return default


def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    logger = logging.getLogger("pc_app")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    log_path = config.get("log_path")
    if not log_path:
        local_appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if local_appdata:
            log_path = str(Path(local_appdata) / "UpbitRealTimeChart" / "logs" / "app.log")
        else:
            log_path = str(Path(__file__).with_name("app.log"))

    handler: logging.Handler
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
    except OSError:
        handler = logging.StreamHandler()

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("logging initialized at %s", log_path)
    return logger


@dataclass
class Candle:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class TimeframeAggregator:
    def __init__(self, timeframe_ms: int, max_store: int = 1000) -> None:
        self.timeframe_ms = timeframe_ms
        self.max_store = max_store
        self.candles: Deque[Candle] = deque(maxlen=max_store)
        self.current: Optional[Candle] = None
        self.last_ts: Optional[int] = None

    def on_trade(self, ts_ms: int, price: float, volume: float) -> Optional[Candle]:
        if self.last_ts is not None and ts_ms < self.last_ts:
            return None
        self.last_ts = ts_ms
        bucket_start = (ts_ms // self.timeframe_ms) * self.timeframe_ms
        if self.current is None or bucket_start > self.current.ts_ms:
            finalized = self.current
            if finalized is not None:
                self.candles.append(finalized)
            self.current = Candle(
                ts_ms=bucket_start,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
            )
            return finalized
        if bucket_start == self.current.ts_ms:
            self.current.high = max(self.current.high, price)
            self.current.low = min(self.current.low, price)
            self.current.close = price
            self.current.volume += volume
        return None

    def snapshot(self) -> List[Candle]:
        if self.current is None:
            return list(self.candles)
        return list(self.candles) + [self.current]

    def seed(self, candles: List[Candle]) -> None:
        if not candles:
            return
        trimmed = candles[-self.max_store:]
        if len(trimmed) >= 2:
            self.candles = deque(trimmed[:-1], maxlen=self.max_store)
            self.current = trimmed[-1]
        else:
            self.candles = deque([], maxlen=self.max_store)
            self.current = trimmed[-1]
        self.last_ts = self.current.ts_ms if self.current else None


class TickAggregator:
    def __init__(self, tick_size: int, max_store: int = 1000) -> None:
        self.tick_size = tick_size
        self.max_store = max_store
        self.candles: Deque[Candle] = deque(maxlen=max_store)
        self.current_ticks: List[Tuple[int, float, float]] = []

    def on_trade(self, ts_ms: int, price: float, volume: float) -> Optional[Candle]:
        self.current_ticks.append((ts_ms, price, volume))
        if len(self.current_ticks) < self.tick_size:
            return None
        ticks = self.current_ticks
        self.current_ticks = []
        prices = [p for _, p, _ in ticks]
        volumes = [v for _, _, v in ticks]
        candle = Candle(
            ts_ms=ticks[-1][0],
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=sum(volumes),
        )
        self.candles.append(candle)
        return candle

    def snapshot(self) -> List[Candle]:
        return list(self.candles)


@dataclass
class SymbolState:
    symbol: str
    timeframe_aggs: Dict[int, TimeframeAggregator]
    tick_aggs: Dict[int, TickAggregator]
    last_price: float = 0.0
    prev_price: float = 0.0
    last_trade_ts: int = 0
    total_ticks: int = 0


class DBReader:
    def __init__(self, db_path: str, logger: logging.Logger) -> None:
        self.db_path = db_path
        self.logger = logger
        self._conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> Optional[sqlite3.Connection]:
        if self._conn is not None:
            return self._conn
        if not Path(self.db_path).exists():
            self.logger.warning("db not found: %s", self.db_path)
            return None
        try:
            uri = f"file:{Path(self.db_path).as_posix()}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            return self._conn
        except sqlite3.Error as exc:
            self.logger.error("db open failed: %s", exc)
            return None

    def _table_exists(self, table: str) -> bool:
        conn = self._connect()
        if conn is None:
            return False
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    def _table_name(self, symbol: str, timeframe_ms: Optional[int]) -> str:
        base = f"ohlcv_{symbol.replace('-', '_')}"
        if timeframe_ms is None:
            return base
        return f"{base}_tf{timeframe_ms}"

    def load_recent(self, symbol: str, limit: int = 200, timeframe_ms: Optional[int] = None) -> List[Candle]:
        conn = self._connect()
        if conn is None:
            return []
        table = self._table_name(symbol, timeframe_ms)
        if not self._table_exists(table) and timeframe_ms is not None:
            table = self._table_name(symbol, None)
            if not self._table_exists(table):
                self.logger.warning("db table not found: %s", table)
                return []
        query = f"SELECT ts, open, high, low, close, volume FROM {table} ORDER BY ts DESC LIMIT ?"
        try:
            rows = conn.execute(query, (limit,)).fetchall()
        except sqlite3.Error as exc:
            self.logger.error("db query failed: %s", exc)
            return []
        candles = [
            Candle(
                ts_ms=_safe_int(row[0]),
                open=_safe_float(row[1]),
                high=_safe_float(row[2]),
                low=_safe_float(row[3]),
                close=_safe_float(row[4]),
                volume=_safe_float(row[5]),
            )
            for row in reversed(rows)
        ]
        return candles


class TradeFeedWorker(threading.Thread):
    def __init__(
        self,
        symbols: List[str],
        on_trade,
        stop_event: threading.Event,
        logger: logging.Logger,
        use_mock: bool,
    ) -> None:
        super().__init__(daemon=True)
        self.symbols = symbols
        self.on_trade = on_trade
        self.stop_event = stop_event
        self.logger = logger
        self.use_mock = use_mock
        self._ws = None

    def run(self) -> None:
        if self.use_mock:
            self._run_mock()
        else:
            self._run_ws()

    def _run_ws(self) -> None:
        try:
            import websocket
        except ImportError:
            self.logger.warning("websocket-client not available, using mock feed")
            self._run_mock()
            return

        def on_open(ws):
            ticket = f"pcapp-{uuid.uuid4().hex[:8]}"
            payload = [
                {"ticket": ticket},
                {"type": "trade", "codes": self.symbols, "isOnlyRealtime": True},
            ]
            try:
                ws.send(json.dumps(payload))
            except Exception as exc:
                self.logger.error("ws send failed: %s", exc)

        def on_message(ws, message):
            try:
                if isinstance(message, (bytes, bytearray)):
                    message = message.decode("utf-8")
                data = json.loads(message)
            except Exception:
                return
            if data.get("type") != "trade":
                return
            symbol = data.get("code") or data.get("market")
            if not symbol:
                return
            ts_ms = _safe_int(data.get("trade_timestamp") or data.get("timestamp"), _now_ms())
            price = _safe_float(data.get("trade_price"))
            volume = _safe_float(data.get("trade_volume"))
            self.on_trade(symbol, ts_ms, price, volume)

        def on_error(ws, error):
            self.logger.error("ws error: %s", error)

        def on_close(ws, status_code, msg):
            self.logger.info("ws closed: %s %s", status_code, msg)

        self._ws = websocket.WebSocketApp(
            "wss://api.upbit.com/websocket/v1",
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        while not self.stop_event.is_set():
            try:
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as exc:
                self.logger.error("ws run failed: %s", exc)
            if not self.stop_event.is_set():
                time.sleep(1)

    def _run_mock(self) -> None:
        prices = {"KRW-XRP": 2700.0, "KRW-BTC": 130_000_000.0, "KRW-ETH": 4_000_000.0}
        while not self.stop_event.is_set():
            now = _now_ms()
            for symbol in self.symbols:
                drift = random.uniform(-1.5, 1.5)
                if symbol == "KRW-BTC":
                    drift *= 20_000
                elif symbol == "KRW-ETH":
                    drift *= 2_000
                prices[symbol] = max(1.0, prices[symbol] + drift)
                volume = random.uniform(0.01, 5.0)
                self.on_trade(symbol, now, prices[symbol], volume)
            time.sleep(0.1)

    def stop(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass


class MainEngine:
    def __init__(self, config: Dict[str, Any], logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.symbols = config.get("symbols", SYMBOLS)
        self.default_timeframe_ms = config.get("default_timeframe_ms", DEFAULT_TIMEFRAME_MS)
        self.active_timeframes = {symbol: self.default_timeframe_ms for symbol in self.symbols}
        self.states: Dict[str, SymbolState] = {}
        self.last_message_ts: Dict[str, float] = {symbol: 0.0 for symbol in self.symbols}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: Optional[TradeFeedWorker] = None
        self.db_reader = DBReader(config.get("db_path", "ohlcv_short.sqlite"), logger)
        self.initial_candles = int(config.get("initial_candles", 600))
        self.mode_by_symbol = {symbol: "LIVE" for symbol in self.symbols}

        for symbol in self.symbols:
            timeframe_aggs = {
                tf: TimeframeAggregator(tf) for tf in TIMEFRAMES_MS
            }
            tick_aggs = {3: TickAggregator(3)}
            self.states[symbol] = SymbolState(
                symbol=symbol,
                timeframe_aggs=timeframe_aggs,
                tick_aggs=tick_aggs,
            )

    def start(self) -> None:
        use_mock = bool(os.getenv("UPBIT_PCAPP_MOCK"))
        self._seed_from_db()
        self._worker = TradeFeedWorker(
            symbols=self.symbols,
            on_trade=self.on_trade,
            stop_event=self._stop_event,
            logger=self.logger,
            use_mock=use_mock,
        )
        self._worker.start()

    def _seed_from_db(self) -> None:
        if self.initial_candles <= 0:
            return
        for symbol, state in self.states.items():
            fallback = self.db_reader.load_recent(
                symbol=symbol,
                limit=self.initial_candles,
                timeframe_ms=None,
            )
            for tf_ms, agg in state.timeframe_aggs.items():
                candles = self.db_reader.load_recent(
                    symbol=symbol,
                    limit=self.initial_candles,
                    timeframe_ms=tf_ms,
                )
                if not candles and fallback:
                    candles = fallback
                if candles:
                    agg.seed(candles)
            # last_price/prev_price 초기화
            default_tf = self.active_timeframes.get(symbol, self.default_timeframe_ms)
            seed_candles = state.timeframe_aggs[default_tf].snapshot()
            if seed_candles:
                state.last_price = seed_candles[-1].close
                state.prev_price = seed_candles[-1].open
                state.last_trade_ts = seed_candles[-1].ts_ms

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker:
            self._worker.stop()
            self._worker.join(timeout=5)

    def on_trade(self, symbol: str, ts_ms: int, price: float, volume: float) -> None:
        if symbol not in self.states:
            return
        with self._lock:
            state = self.states[symbol]
            state.total_ticks += 1
            state.prev_price = state.last_price or price
            state.last_price = price
            state.last_trade_ts = ts_ms
            self.last_message_ts[symbol] = time.time()
            for agg in state.timeframe_aggs.values():
                agg.on_trade(ts_ms, price, volume)
            for agg in state.tick_aggs.values():
                agg.on_trade(ts_ms, price, volume)

    def set_active_timeframe(self, symbol: str, timeframe_ms: int) -> None:
        if symbol not in self.active_timeframes:
            return
        self.active_timeframes[symbol] = timeframe_ms

    def set_symbol_mode(self, symbol: str, mode: str) -> None:
        if symbol not in self.mode_by_symbol:
            return
        self.mode_by_symbol[symbol] = mode

    def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        with self._lock:
            state = self.states.get(symbol)
            if state is None:
                return {}
            tf_ms = self.active_timeframes.get(symbol, self.default_timeframe_ms)
            candles = state.timeframe_aggs[tf_ms].snapshot()
            last_price = state.last_price
            if not last_price and candles:
                last_price = candles[-1].close
            prev_price = state.prev_price or last_price
            price_change = last_price - prev_price if last_price else 0.0
            percent_change = 0.0
            if prev_price:
                percent_change = round(price_change / prev_price * 100, 2)
            last_age = 0.0
            last_ts = self.last_message_ts.get(symbol)
            if last_ts:
                last_age = max(0.0, time.time() - last_ts)
            return {
                "symbol": symbol,
                "display_name": DISPLAY_NAMES.get(symbol, symbol),
                "price": last_price,
                "price_change": price_change,
                "percent_change": percent_change,
                "candles": candles,
                "mode": self.mode_by_symbol.get(symbol, "LIVE"),
                "ws_status": "OK" if last_age < 5 else "WARN",
                "burst_status": "NORMAL",
                "last_message_age": last_age,
                "last_trade_ts": state.last_trade_ts,
                "timeframe_ms": tf_ms,
            }

    def get_diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            now_ms = _now_ms()
            diag = {
                "now_ms": now_ms,
                "symbols": {},
            }
            for symbol, state in self.states.items():
                last_age = 0.0
                last_ts = self.last_message_ts.get(symbol)
                if last_ts:
                    last_age = max(0.0, time.time() - last_ts)
                diag["symbols"][symbol] = {
                    "mode": self.mode_by_symbol.get(symbol, "LIVE"),
                    "ws": "OK" if last_age < 5 else "WARN",
                    "burst": "NORMAL",
                    "last_trade_ts": state.last_trade_ts,
                    "last_message_age": last_age,
                    "total_ticks": state.total_ticks,
                }
            return diag
