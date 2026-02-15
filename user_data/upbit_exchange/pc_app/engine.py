from __future__ import annotations

import json
import logging
import logging.handlers
import os
import random
import shlex
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Deque, Dict, List, Optional, Tuple


SYMBOLS = ["KRW-XRP", "KRW-BTC", "KRW-ETH"]
DISPLAY_NAMES = {
    "KRW-XRP": "XRP",
    "KRW-BTC": "BTC",
    "KRW-ETH": "ETH",
}

TIMEFRAMES_MS = [
    60_000,  # 1m
    300_000,  # 5m
    900_000,  # 15m
    3_600_000,  # 1h
    14_400_000,  # 4h
    86_400_000,  # 1d
]

DEFAULT_TIMEFRAME_MS = 3_600_000
DEFAULT_NO_TRADE_WARN_SEC = 3.0
DEFAULT_SNAPSHOT_PULL_INTERVAL_SEC = 300
SSH_CONNECT_TIMEOUT_SEC = 3
SSH_TOTAL_TIMEOUT_SEC = 8
RECONNECT_BASE_STEPS = (5.0, 10.0, 20.0, 30.0)
RECONNECT_COOLDOWN_EVERY = 6

DEFAULT_SSH_CONFIG = {
    "enabled": False,
    "host": "152.69.234.80",
    "port": 22,
    "username": "opc",
    "ppk_path": "",
    "use_pageant": True,
    "remote_db_path": "/home/opc/python/ft_userdata_upbit/user_data/upbit_exchange/ohlcv_short.sqlite",
    "remote_snapshot_path": "/tmp/ohlcv_short_snapshot.sqlite",
    "remote_config_path": "/home/opc/python/ft_userdata_upbit/user_data/config.json",
    "pull_interval_sec": DEFAULT_SNAPSHOT_PULL_INTERVAL_SEC,
}


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


def _deep_merge(default: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key, default_value in default.items():
        current_value = current.get(key)
        if isinstance(default_value, dict) and isinstance(current_value, dict):
            merged[key] = _deep_merge(default_value, current_value)
        elif key in current:
            merged[key] = current_value
        else:
            merged[key] = default_value
    for key, value in current.items():
        if key not in merged:
            merged[key] = value
    return merged


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


def _default_config() -> Dict[str, Any]:
    return {
        "symbols": SYMBOLS,
        "default_timeframe_ms": DEFAULT_TIMEFRAME_MS,
        "db_path": "ohlcv_short.sqlite",
        "logo_path": "assets/upbit_logo.png",
        "initial_candles": 600,
        "no_trade_warn_sec": DEFAULT_NO_TRADE_WARN_SEC,
        "window_positions": {
            "window1": {"x": 0, "y": 0, "width": 1920, "height": 1080, "monitor": 0},
            "window2": {"x": 1920, "y": 0, "width": 1920, "height": 1080, "monitor": 1},
        },
        "ssh": dict(DEFAULT_SSH_CONFIG),
        "log_path": None,
    }


def _write_config(config_path: Path, payload: Dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_or_create_config() -> Dict[str, Any]:
    config_path = resolve_config_path()
    default = _default_config()

    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if not isinstance(loaded, dict):
            loaded = {}
        merged = _deep_merge(default, loaded)
        # 운영 시 필드 드리프트를 줄이기 위해 기본 키를 자동 보정해서 저장한다.
        if merged != loaded:
            try:
                _write_config(config_path, merged)
            except OSError:
                pass
        return merged

    try:
        _write_config(config_path, default)
    except OSError:
        appdata_path = get_config_path()
        _write_config(appdata_path, default)
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
            log_path,
            maxBytes=50 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
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
        self.min_bucket_start: Optional[int] = None

    def set_min_bucket_start(self, min_bucket_start: Optional[int]) -> None:
        self.min_bucket_start = min_bucket_start

    def reset(self) -> None:
        self.candles.clear()
        self.current = None
        self.last_ts = None

    def on_trade(self, ts_ms: int, price: float, volume: float) -> Optional[Candle]:
        if self.last_ts is not None and ts_ms < self.last_ts:
            return None
        self.last_ts = ts_ms
        bucket_start = (ts_ms // self.timeframe_ms) * self.timeframe_ms
        if self.min_bucket_start is not None and bucket_start < self.min_bucket_start:
            return None
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
    db_histories: Dict[int, Deque[Candle]]
    cutover_by_tf: Dict[int, Optional[int]]
    tick_aggs: Dict[int, TickAggregator]
    last_price: float = 0.0
    prev_price: float = 0.0
    last_trade_ts: int = 0
    last_trade_wall_ts: float = 0.0
    total_ticks: int = 0
    ws_l1: str = "DISCONNECTED"
    ws_l2: str = "UNKNOWN"
    ws_generation_id: int = 0
    mode: str = "DB_ONLY"
    has_db_seed: bool = False


class DBReader:
    def __init__(self, db_path: str, logger: logging.Logger) -> None:
        self.db_path = db_path
        self.logger = logger
        self._conn: Optional[sqlite3.Connection] = None
        self._conn_lock = threading.Lock()

    def set_db_path(self, db_path: str) -> None:
        with self._conn_lock:
            self._close_unlocked()
            self.db_path = db_path

    def close(self) -> None:
        with self._conn_lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
        self._conn = None

    def _connect(self) -> Optional[sqlite3.Connection]:
        with self._conn_lock:
            if self._conn is not None:
                return self._conn
            if not Path(self.db_path).exists():
                self.logger.warning("db not found: %s", self.db_path)
                return None
            try:
                uri = f"file:{Path(self.db_path).resolve().as_posix()}?mode=ro&immutable=1"
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
        return [
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


class TradeFeedWorker(threading.Thread):
    def __init__(
        self,
        symbols: List[str],
        on_trade,
        on_ws_state,
        stop_event: threading.Event,
        logger: logging.Logger,
        use_mock: bool,
    ) -> None:
        super().__init__(daemon=True)
        self.symbols = symbols
        self.on_trade = on_trade
        self.on_ws_state = on_ws_state
        self.stop_event = stop_event
        self.logger = logger
        self.use_mock = use_mock
        self._ws = None
        self._generation_id = 0
        self._reconnect_failures = 0

    def _emit_ws_state(
        self,
        l1: str,
        l2: str,
        generation_id: int,
        retry_in_sec: float = 0.0,
    ) -> None:
        self.on_ws_state(
            {
                "l1": l1,
                "l2": l2,
                "generation_id": generation_id,
                "retry_in_sec": retry_in_sec,
                "ts": time.time(),
            }
        )

    def _next_reconnect_delay(self) -> float:
        self._reconnect_failures += 1
        step_index = min(self._reconnect_failures - 1, len(RECONNECT_BASE_STEPS) - 1)
        base = RECONNECT_BASE_STEPS[step_index]
        jitter = random.uniform(0.0, base * 0.2)
        delay = min(30.0, base + jitter)
        # 운영에서 재연결 폭주를 막기 위해 주기적으로 cooldown을 강제한다.
        if self._reconnect_failures % RECONNECT_COOLDOWN_EVERY == 0:
            delay = max(delay, 30.0)
        return delay

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

        while not self.stop_event.is_set():
            self._generation_id += 1
            generation_id = self._generation_id
            phase = "CONNECTING" if generation_id == 1 else "RECONNECTING"
            self._emit_ws_state(phase, "UNKNOWN", generation_id=generation_id)

            def on_open(ws):
                self._reconnect_failures = 0
                self._emit_ws_state("CONNECTED", "ALIVE", generation_id=generation_id)
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
                self.on_trade(symbol, ts_ms, price, volume, generation_id)

            def on_error(ws, error):
                self.logger.warning("ws error type=%s", type(error).__name__)
                self._emit_ws_state("CONNECTED", "DEGRADED", generation_id=generation_id)

            def on_pong(ws, data):
                self._emit_ws_state("CONNECTED", "ALIVE", generation_id=generation_id)

            def on_close(ws, status_code, msg):
                self.logger.info("ws closed: %s %s", status_code, msg)
                self._emit_ws_state("DISCONNECTED", "UNKNOWN", generation_id=generation_id)

            self._ws = websocket.WebSocketApp(
                "wss://api.upbit.com/websocket/v1",
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_pong=on_pong,
                on_close=on_close,
            )

            try:
                self._ws.run_forever(ping_interval=20, ping_timeout=8)
            except Exception as exc:
                self.logger.error("ws run failed: %s", exc)
                self._emit_ws_state("DISCONNECTED", "DEGRADED", generation_id=generation_id)

            if self.stop_event.is_set():
                break

            delay = self._next_reconnect_delay()
            self._emit_ws_state(
                "RECONNECT_WAIT",
                "DEGRADED",
                generation_id=generation_id,
                retry_in_sec=delay,
            )
            self.stop_event.wait(delay)

    def _run_mock(self) -> None:
        self._generation_id = 1
        generation_id = self._generation_id
        self._emit_ws_state("CONNECTED", "ALIVE", generation_id=generation_id)
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
                self.on_trade(symbol, now, prices[symbol], volume, generation_id)
            self.stop_event.wait(0.1)

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
        self.no_trade_warn_sec = _safe_float(config.get("no_trade_warn_sec"), DEFAULT_NO_TRADE_WARN_SEC)
        self.initial_candles = max(0, _safe_int(config.get("initial_candles"), 600))
        self.states: Dict[str, SymbolState] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: Optional[TradeFeedWorker] = None
        self._snapshot_pull_lock = threading.Lock()
        self._order_load_lock = threading.Lock()
        self._runtime_passphrase: Optional[str] = None
        self._order_loaded_once = False
        self._order_keys: Optional[Dict[str, str]] = None
        self._fatal_message = ""

        self._ssh_state = {
            "status": "UNCONFIGURED",
            "message": "SSH 미연결(로컬 DB 사용)",
            "last_update_ts": 0.0,
        }
        self._db_snapshot_state = {
            "status": "IDLE",
            "message": "DB 스냅샷 대기",
            "last_update_ts": 0.0,
        }
        self._order_state = {
            "state": "ORDER_LOCKED_DRYRUN",
            "reason": "INIT",
            "dry_run": True,
            "masked_key": "",
            "last_update_ts": 0.0,
        }

        self.db_reader = DBReader(config.get("db_path", "ohlcv_short.sqlite"), logger)
        self._snapshot_pull_interval_sec = self._get_normalized_ssh_settings().get(
            "pull_interval_sec",
            DEFAULT_SNAPSHOT_PULL_INTERVAL_SEC,
        )

        now_wall = time.time()
        for symbol in self.symbols:
            timeframe_aggs = {tf: TimeframeAggregator(tf) for tf in TIMEFRAMES_MS}
            db_histories = {tf: deque(maxlen=1000) for tf in TIMEFRAMES_MS}
            cutover_by_tf = {tf: None for tf in TIMEFRAMES_MS}
            tick_aggs = {3: TickAggregator(3)}
            self.states[symbol] = SymbolState(
                symbol=symbol,
                timeframe_aggs=timeframe_aggs,
                db_histories=db_histories,
                cutover_by_tf=cutover_by_tf,
                tick_aggs=tick_aggs,
                last_trade_wall_ts=now_wall,
            )

    def _update_ssh_state(self, status: str, message: str) -> None:
        self._ssh_state = {
            "status": status,
            "message": message,
            "last_update_ts": time.time(),
        }

    def _update_db_snapshot_state(self, status: str, message: str) -> None:
        self._db_snapshot_state = {
            "status": status,
            "message": message,
            "last_update_ts": time.time(),
        }

    def _set_order_state(
        self,
        state: str,
        reason: str,
        dry_run: bool,
        masked_key: str = "",
    ) -> None:
        self._order_state = {
            "state": state,
            "reason": reason,
            "dry_run": dry_run,
            "masked_key": masked_key,
            "last_update_ts": time.time(),
        }

    def get_ssh_settings(self) -> Dict[str, Any]:
        return dict(self._get_normalized_ssh_settings())

    def get_snapshot_pull_interval_sec(self) -> int:
        interval = _safe_int(self._snapshot_pull_interval_sec, DEFAULT_SNAPSHOT_PULL_INTERVAL_SEC)
        return max(60, interval)

    def set_runtime_passphrase(self, passphrase: Optional[str]) -> None:
        self._runtime_passphrase = passphrase or None

    def apply_ssh_settings(self, settings: Dict[str, Any], passphrase: Optional[str]) -> None:
        normalized = self._normalize_ssh_settings(settings)
        self.config["ssh"] = dict(normalized)
        self._snapshot_pull_interval_sec = normalized.get(
            "pull_interval_sec",
            DEFAULT_SNAPSHOT_PULL_INTERVAL_SEC,
        )
        self._runtime_passphrase = passphrase or None
        self._update_ssh_state("CONFIGURED", "SSH 설정 적용됨")

    def mark_ssh_unavailable(self, reason: str) -> None:
        self._update_ssh_state("FALLBACK", f"SSH 미연결(로컬 DB 사용): {reason}")

    def start(self) -> None:
        use_mock = bool(os.getenv("UPBIT_PCAPP_MOCK"))
        self._seed_from_db()
        self._start_order_gate_load_once("startup")
        self._worker = TradeFeedWorker(
            symbols=self.symbols,
            on_trade=self.on_trade,
            on_ws_state=self._on_ws_state,
            stop_event=self._stop_event,
            logger=self.logger,
            use_mock=use_mock,
        )
        self._worker.start()
        # 운영 정책: 주기 pull은 자동(5분 기본)이지만, 시작 시 1회 시도해 최신 스냅샷 확보를 우선한다.
        self.trigger_periodic_snapshot_pull(reason="startup")

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker:
            self._worker.stop()
            self._worker.join(timeout=5)
        self.db_reader.close()

    def _normalize_ssh_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        merged = _deep_merge(DEFAULT_SSH_CONFIG, settings)
        merged["port"] = _safe_int(merged.get("port"), 22)
        merged["enabled"] = bool(merged.get("enabled"))
        merged["use_pageant"] = bool(merged.get("use_pageant"))
        merged["pull_interval_sec"] = max(
            60,
            _safe_int(merged.get("pull_interval_sec"), DEFAULT_SNAPSHOT_PULL_INTERVAL_SEC),
        )
        merged["host"] = str(merged.get("host", "")).strip()
        merged["username"] = str(merged.get("username", "")).strip()
        merged["ppk_path"] = str(merged.get("ppk_path", "")).strip()
        merged["remote_db_path"] = str(merged.get("remote_db_path", "")).strip()
        merged["remote_snapshot_path"] = str(merged.get("remote_snapshot_path", "")).strip()
        merged["remote_config_path"] = str(merged.get("remote_config_path", "")).strip()
        return merged

    def _get_normalized_ssh_settings(self) -> Dict[str, Any]:
        raw = self.config.get("ssh", {})
        if not isinstance(raw, dict):
            raw = {}
        return self._normalize_ssh_settings(raw)

    def _is_ssh_usable(self, ssh: Optional[Dict[str, Any]] = None) -> bool:
        cfg = ssh or self._get_normalized_ssh_settings()
        if not cfg.get("enabled"):
            return False
        required = ("host", "username", "ppk_path", "remote_db_path", "remote_snapshot_path", "remote_config_path")
        for key in required:
            if not cfg.get(key):
                return False
        return True

    def _seed_from_db(self) -> None:
        if self.initial_candles <= 0:
            return
        with self._lock:
            for symbol, state in self.states.items():
                fallback = self.db_reader.load_recent(
                    symbol=symbol,
                    limit=self.initial_candles,
                    timeframe_ms=None,
                )
                symbol_has_seed = False
                for tf_ms, agg in state.timeframe_aggs.items():
                    candles = self.db_reader.load_recent(
                        symbol=symbol,
                        limit=self.initial_candles,
                        timeframe_ms=tf_ms,
                    )
                    if not candles and fallback:
                        candles = fallback
                    self._apply_db_seed_to_timeframe(state, tf_ms, candles)
                    if candles:
                        symbol_has_seed = True
                state.has_db_seed = symbol_has_seed
                state.mode = "DB_ONLY" if symbol_has_seed else "LIVE_ACTIVE"
                default_tf = self.active_timeframes.get(symbol, self.default_timeframe_ms)
                merged = self._build_merged_candles(state, default_tf)
                if merged:
                    state.last_price = merged[-1].close
                    state.prev_price = merged[-1].open
                    state.last_trade_ts = merged[-1].ts_ms

    def _apply_db_seed_to_timeframe(
        self,
        state: SymbolState,
        tf_ms: int,
        candles: List[Candle],
    ) -> None:
        history = state.db_histories[tf_ms]
        history.clear()
        agg = state.timeframe_aggs[tf_ms]
        agg.reset()
        if not candles:
            state.cutover_by_tf[tf_ms] = None
            agg.set_min_bucket_start(None)
            return

        # SSOT A+ 규칙:
        # - DB 마지막 캔들 1개를 폐기하고
        # - cutover_ts를 "다음 버킷 시작"으로 고정한다.
        last_db_bucket_start = candles[-1].ts_ms
        cutover_ts = last_db_bucket_start + tf_ms
        for candle in candles[:-1]:
            if candle.ts_ms < cutover_ts:
                history.append(candle)
        state.cutover_by_tf[tf_ms] = cutover_ts
        agg.set_min_bucket_start(cutover_ts)

    def _build_merged_candles(self, state: SymbolState, tf_ms: int) -> List[Candle]:
        db_part = list(state.db_histories[tf_ms])
        live_part = state.timeframe_aggs[tf_ms].snapshot()
        cutover_ts = state.cutover_by_tf.get(tf_ms)
        if cutover_ts is not None:
            db_part = [c for c in db_part if c.ts_ms < cutover_ts]
            live_part = [c for c in live_part if c.ts_ms >= cutover_ts]
        merged = db_part + live_part
        max_store = state.timeframe_aggs[tf_ms].max_store
        if len(merged) > max_store:
            merged = merged[-max_store:]
        return merged

    def _on_ws_state(self, ws_state: Dict[str, Any]) -> None:
        l1 = str(ws_state.get("l1", "DISCONNECTED"))
        l2 = str(ws_state.get("l2", "UNKNOWN"))
        generation_id = _safe_int(ws_state.get("generation_id"), 0)
        with self._lock:
            for state in self.states.values():
                # generation_id를 강제로 단조 증가로 유지해서, 재연결 전후 데이터가 섞이는 것을 차단한다.
                if generation_id > 0:
                    state.ws_generation_id = max(state.ws_generation_id, generation_id)
                state.ws_l1 = l1
                state.ws_l2 = l2

    def on_trade(self, symbol: str, ts_ms: int, price: float, volume: float, generation_id: int) -> None:
        if symbol not in self.states:
            return
        with self._lock:
            state = self.states[symbol]
            # 재연결 이전 generation에서 늦게 도착한 데이터는 폐기해서 섞임을 차단한다.
            if state.ws_generation_id and generation_id != state.ws_generation_id:
                return
            state.total_ticks += 1
            state.prev_price = state.last_price or price
            state.last_price = price
            state.last_trade_ts = ts_ms
            state.last_trade_wall_ts = time.time()
            state.ws_l1 = "CONNECTED"
            state.ws_l2 = "ALIVE"
            for agg in state.timeframe_aggs.values():
                agg.on_trade(ts_ms, price, volume)
            for agg in state.tick_aggs.values():
                agg.on_trade(ts_ms, price, volume)
            state.mode = "LIVE_ACTIVE"

    def set_active_timeframe(self, symbol: str, timeframe_ms: int) -> None:
        if symbol not in self.active_timeframes:
            return
        self.active_timeframes[symbol] = timeframe_ms

    def set_symbol_mode(self, symbol: str, mode: str) -> None:
        if symbol not in self.states:
            return
        with self._lock:
            self.states[symbol].mode = mode

    def _calc_last_trade_age(self, state: SymbolState) -> float:
        if state.last_trade_wall_ts <= 0:
            return 0.0
        return max(0.0, time.time() - state.last_trade_wall_ts)

    def _calc_ws_status(self, state: SymbolState) -> str:
        if state.ws_l1 == "CONNECTED" and state.ws_l2 == "ALIVE":
            return "OK"
        return "WARN"

    def get_snapshot(self, symbol: str) -> Dict[str, Any]:
        with self._lock:
            state = self.states.get(symbol)
            if state is None:
                return {}
            tf_ms = self.active_timeframes.get(symbol, self.default_timeframe_ms)
            candles = self._build_merged_candles(state, tf_ms)
            last_price = state.last_price
            if not last_price and candles:
                last_price = candles[-1].close
            prev_price = state.prev_price or last_price
            price_change = last_price - prev_price if last_price else 0.0
            percent_change = 0.0
            if prev_price:
                percent_change = round(price_change / prev_price * 100, 2)
            last_age = self._calc_last_trade_age(state)
            return {
                "symbol": symbol,
                "display_name": DISPLAY_NAMES.get(symbol, symbol),
                "price": last_price,
                "price_change": price_change,
                "percent_change": percent_change,
                "candles": candles,
                "mode": state.mode,
                "ws_status": self._calc_ws_status(state),
                "ws_l1": state.ws_l1,
                "ws_l2": state.ws_l2,
                "burst_status": "NORMAL",
                "last_message_age": last_age,
                "last_trade_age_sec": last_age,
                "no_trade_warn_sec": self.no_trade_warn_sec,
                "no_trade_text": f"거래없음 {int(last_age)}초",
                "last_trade_ts": state.last_trade_ts,
                "timeframe_ms": tf_ms,
                "generation_id": state.ws_generation_id,
                "cutover_ts": state.cutover_by_tf.get(tf_ms),
                "order_state": self._order_state.get("state"),
                "order_reason": self._order_state.get("reason"),
            }

    def get_diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            now_ms = _now_ms()
            diag = {
                "now_ms": now_ms,
                "symbols": {},
                "ssh": dict(self._ssh_state),
                "db_snapshot": dict(self._db_snapshot_state),
                "order": dict(self._order_state),
                "fatal_message": self._fatal_message,
                "no_trade_warn_sec": self.no_trade_warn_sec,
            }
            for symbol, state in self.states.items():
                last_age = self._calc_last_trade_age(state)
                diag["symbols"][symbol] = {
                    "mode": state.mode,
                    "ws": self._calc_ws_status(state),
                    "ws_l1": state.ws_l1,
                    "ws_l2": state.ws_l2,
                    "burst": "NORMAL",
                    "last_trade_ts": state.last_trade_ts,
                    "last_message_age": last_age,
                    "last_trade_age_sec": last_age,
                    "no_trade_text": f"거래없음 {int(last_age)}초",
                    "generation_id": state.ws_generation_id,
                    "total_ticks": state.total_ticks,
                }
            return diag

    def _resolve_putty_binary(self, binary_name: str) -> Optional[str]:
        putty_dir = Path(__file__).resolve().parent / "third_party" / "putty"
        candidate = putty_dir / binary_name
        if candidate.exists():
            return str(candidate)
        which_names = [binary_name]
        if binary_name.lower().endswith(".exe"):
            which_names.append(binary_name[:-4])
        for name in which_names:
            resolved = shutil.which(name)
            if resolved:
                return resolved
        return None

    def _build_putty_common_args(self, ssh: Dict[str, Any], passphrase: Optional[str]) -> List[str]:
        args = [
            "-batch",
            "-P",
            str(_safe_int(ssh.get("port"), 22)),
            "-i",
            str(ssh.get("ppk_path", "")),
            "-timeout",
            str(SSH_CONNECT_TIMEOUT_SEC),
        ]
        if passphrase:
            # Pageant 사용이 안 되는 환경에서만 fallback으로 passphrase를 전달한다.
            args.extend(["-pw", passphrase])
        elif not bool(ssh.get("use_pageant", True)):
            args.append("-noagent")
        return args

    def _short_error(self, text: str) -> str:
        text = (text or "").strip().replace("\n", " ")
        if not text:
            return "UNKNOWN"
        if len(text) > 140:
            return text[:140] + "..."
        return text

    def _run_plink(self, ssh: Dict[str, Any], command: str, passphrase: Optional[str]) -> Tuple[bool, str]:
        plink = self._resolve_putty_binary("plink.exe")
        if not plink:
            return False, "PLINK_NOT_FOUND"
        args = [plink]
        args.extend(self._build_putty_common_args(ssh, passphrase))
        args.extend(["-l", str(ssh.get("username", "")), str(ssh.get("host", "")), command])
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=SSH_TOTAL_TIMEOUT_SEC,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "SSH_TIMEOUT_8S"
        except OSError:
            return False, "SSH_EXEC_FAIL"
        if proc.returncode != 0:
            return False, self._short_error(proc.stderr or proc.stdout)
        return True, "OK"

    def _run_pscp_download(
        self,
        ssh: Dict[str, Any],
        remote_path: str,
        local_path: Path,
        passphrase: Optional[str],
    ) -> Tuple[bool, str]:
        pscp = self._resolve_putty_binary("pscp.exe")
        if not pscp:
            return False, "PSCP_NOT_FOUND"
        args = [pscp]
        args.extend(self._build_putty_common_args(ssh, passphrase))
        args.extend([f"{ssh.get('username')}@{ssh.get('host')}:{remote_path}", str(local_path)])
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=SSH_TOTAL_TIMEOUT_SEC,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "SCP_TIMEOUT_8S"
        except OSError:
            return False, "SCP_EXEC_FAIL"
        if proc.returncode != 0:
            return False, self._short_error(proc.stderr or proc.stdout)
        return True, "OK"

    def test_ssh_settings(self, settings: Dict[str, Any], passphrase: Optional[str]) -> Tuple[bool, str]:
        ssh = self._normalize_ssh_settings(settings)
        if not self._is_ssh_usable(ssh):
            return False, "SSH_SETTINGS_INCOMPLETE"
        if ssh.get("ppk_path") and not Path(str(ssh["ppk_path"])).exists():
            return False, "PPK_NOT_FOUND"
        ok, msg = self._run_plink(ssh, "echo SSH_OK", passphrase=passphrase)
        if ok:
            return True, "연결 성공"
        return False, f"연결 실패: {msg}"

    def trigger_periodic_snapshot_pull(self, reason: str = "periodic") -> bool:
        if not self._snapshot_pull_lock.acquire(blocking=False):
            return False
        thread = threading.Thread(
            target=self._snapshot_pull_worker,
            args=(reason,),
            daemon=True,
        )
        thread.start()
        return True

    def _snapshot_pull_worker(self, reason: str) -> None:
        tmp_path: Optional[Path] = None
        try:
            ssh = self._get_normalized_ssh_settings()
            if not self._is_ssh_usable(ssh):
                self._update_ssh_state("FALLBACK", "SSH 미연결(로컬 DB 사용)")
                self._update_db_snapshot_state("SKIPPED", "SSH 설정 미완료")
                return
            if ssh.get("ppk_path") and not Path(str(ssh["ppk_path"])).exists():
                self._update_ssh_state("FALLBACK", "SSH 키 경로 불일치(검증 필요)")
                self._update_db_snapshot_state("FAILED", "PPK_NOT_FOUND")
                return

            self._update_ssh_state("CONNECTING", f"SSH 연결 시도({reason})")
            self._update_db_snapshot_state("RUNNING", f"원격 스냅샷 생성({reason})")

            # WAL 모드 일관성을 위해 원격 DB 본파일을 직접 복사하지 않고 snapshot 파일을 생성한다.
            # 이 절차를 지키지 않으면 WAL tail이 반영되지 않은 불완전 파일이 내려올 수 있다.
            py_code = (
                "import sqlite3;"
                f"src={ssh.get('remote_db_path')!r};"
                f"dst={ssh.get('remote_snapshot_path')!r};"
                "src_conn=sqlite3.connect(src, timeout=3);"
                "dst_conn=sqlite3.connect(dst);"
                "src_conn.backup(dst_conn);"
                "dst_conn.close();"
                "src_conn.close()"
            )
            remote_cmd = f"python3 -c {shlex.quote(py_code)}"
            ok, msg = self._run_plink(ssh, remote_cmd, passphrase=self._runtime_passphrase)
            if not ok:
                self._update_ssh_state("FAILED", f"SSH 실패: {msg}")
                self._update_db_snapshot_state("FAILED", f"SNAPSHOT_CREATE_FAIL:{msg}")
                return

            with NamedTemporaryFile(prefix="ohlcv_snapshot_", suffix=".sqlite.tmp", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            ok, msg = self._run_pscp_download(
                ssh=ssh,
                remote_path=str(ssh.get("remote_snapshot_path")),
                local_path=tmp_path,
                passphrase=self._runtime_passphrase,
            )
            if not ok:
                self._update_ssh_state("FAILED", f"SCP 실패: {msg}")
                self._update_db_snapshot_state("FAILED", f"SNAPSHOT_PULL_FAIL:{msg}")
                return

            if not self._validate_sqlite_file(tmp_path):
                self._update_db_snapshot_state("FAILED", "SNAPSHOT_VALIDATE_FAIL")
                return

            if not self._swap_local_db_snapshot(tmp_path):
                self._update_db_snapshot_state("FAILED", "SNAPSHOT_SWAP_FAIL")
                return

            tmp_path = None
            self._update_ssh_state("CONNECTED", "SSH 연결 정상")
            self._update_db_snapshot_state("SUCCESS", "DB 스냅샷 갱신 성공")
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            self._snapshot_pull_lock.release()

    def _validate_sqlite_file(self, file_path: Path) -> bool:
        try:
            conn = sqlite3.connect(f"file:{file_path.as_posix()}?mode=ro", uri=True)
            try:
                row = conn.execute("PRAGMA quick_check").fetchone()
                return bool(row and str(row[0]).lower() == "ok")
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    def _swap_local_db_snapshot(self, tmp_path: Path) -> bool:
        target = Path(self.db_reader.db_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        try:
            # Windows 잠금 이슈 대응: Close -> Swap -> Reopen 순서를 강제한다.
            self.db_reader.close()
            os.replace(str(tmp_path), str(target))
            self.db_reader.set_db_path(str(target))
        except OSError as exc:
            self.logger.warning("db swap failed: %s", exc)
            return False
        self._refresh_db_seed_for_db_only_symbols()
        return True

    def _refresh_db_seed_for_db_only_symbols(self) -> None:
        if self.initial_candles <= 0:
            return
        with self._lock:
            targets = [symbol for symbol, st in self.states.items() if st.mode == "DB_ONLY"]
            for symbol in targets:
                state = self.states[symbol]
                fallback = self.db_reader.load_recent(
                    symbol=symbol,
                    limit=self.initial_candles,
                    timeframe_ms=None,
                )
                for tf_ms in TIMEFRAMES_MS:
                    candles = self.db_reader.load_recent(
                        symbol=symbol,
                        limit=self.initial_candles,
                        timeframe_ms=tf_ms,
                    )
                    if not candles and fallback:
                        candles = fallback
                    self._apply_db_seed_to_timeframe(state, tf_ms, candles)

    def _start_order_gate_load_once(self, reason: str) -> None:
        if self._order_loaded_once:
            return
        if not self._order_load_lock.acquire(blocking=False):
            return
        thread = threading.Thread(
            target=self._order_gate_load_worker,
            args=(reason,),
            daemon=True,
        )
        thread.start()

    def _order_gate_load_worker(self, reason: str) -> None:
        try:
            ssh = self._get_normalized_ssh_settings()
            if not self._is_ssh_usable(ssh):
                self._set_order_state("ORDER_LOCKED_DRYRUN", "SSH_UNAVAILABLE", dry_run=True)
                self._order_loaded_once = True
                return
            if ssh.get("ppk_path") and not Path(str(ssh["ppk_path"])).exists():
                self._set_order_state("ORDER_KEYS_ERROR", "PPK_NOT_FOUND", dry_run=True)
                self._order_loaded_once = True
                return

            with NamedTemporaryFile(prefix="ft_cfg_", suffix=".json.tmp", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                ok, msg = self._run_pscp_download(
                    ssh=ssh,
                    remote_path=str(ssh.get("remote_config_path")),
                    local_path=tmp_path,
                    passphrase=self._runtime_passphrase,
                )
                if not ok:
                    self._set_order_state("ORDER_KEYS_ERROR", f"CFG_PULL_FAIL:{msg}", dry_run=True)
                    self._order_loaded_once = True
                    return
                try:
                    with tmp_path.open("r", encoding="utf-8") as f:
                        payload = json.load(f)
                except (OSError, json.JSONDecodeError):
                    self._set_order_state("ORDER_KEYS_ERROR", "CFG_PARSE_FAIL", dry_run=True)
                    self._order_loaded_once = True
                    return
                self._apply_order_policy(payload)
                self._order_loaded_once = True
                self._update_ssh_state("CONNECTED", f"주문키 정책 로드 성공({reason})")
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        finally:
            self._order_load_lock.release()

    def _apply_order_policy(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            self._set_order_state("ORDER_KEYS_ERROR", "CFG_INVALID", dry_run=True)
            return

        # dry_run 필드가 깨졌을 때는 무조건 LOCK으로 내려서 주문 오동작 리스크를 우선 차단한다.
        dry_run_value = payload.get("dry_run")
        dry_run = dry_run_value if isinstance(dry_run_value, bool) else True
        exchange = payload.get("exchange")
        if not isinstance(exchange, dict):
            self._set_order_state("ORDER_KEYS_ERROR", "EXCHANGE_MISSING", dry_run=True)
            return

        exchange_name = str(exchange.get("name", "")).strip().lower()
        if exchange_name and exchange_name != "upbit":
            # SSOT 결정: Upbit 전용 위반은 Fatal로 취급한다.
            self._fatal_message = "이 앱은 Upbit 전용입니다. config.json의 exchange.name을 upbit로 설정하세요."
            self._set_order_state("ORDER_KEYS_ERROR", "EXCHANGE_NOT_UPBIT_FATAL", dry_run=True)
            return
        if not exchange_name:
            self._set_order_state("ORDER_KEYS_ERROR", "EXCHANGE_NAME_MISSING", dry_run=True)
            return

        if dry_run:
            self._order_keys = None
            self._set_order_state("ORDER_LOCKED_DRYRUN", "DRY_RUN_TRUE", dry_run=True)
            return

        access_key = str(exchange.get("key", "")).strip()
        secret_key = str(exchange.get("secret", "")).strip()
        if not access_key or not secret_key:
            self._order_keys = None
            self._set_order_state("ORDER_KEYS_ERROR", "KEY_MISSING", dry_run=False)
            return

        masked = "****" + access_key[-4:] if len(access_key) >= 4 else "****"
        self._order_keys = {"access": access_key, "secret": secret_key}
        self._set_order_state("ORDER_KEYS_READY", "OK", dry_run=False, masked_key=masked)
