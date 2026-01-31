# collector.py
import os
import sys
import json
import time
import signal
import logging
import threading
import random
import queue
from collections import deque, defaultdict
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Python path에 상위 디렉토리 추가 (common, cloud 모듈 접근용)
PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
BASE_DIR = PARENT_DIR  # cloud/ -> upbit_exchange/

import websocket

from common.constants import *
from common.dedup_cache import DedupCache
from common.reconnect_limiter import GlobalReconnectLimiter
from cloud.ohlcv_writer import OHLCVWriter
from cloud.multi_aggregator import MultiAggregator


# watchdog 관련 logging 설정
LOG_DIR = BASE_DIR / "logs"
LOG_FILE_PATH = LOG_DIR / "collector.log"
LOG_FALLBACK = False
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    LOG_FALLBACK = True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(LOG_FILE_PATH) if not LOG_FALLBACK else "collector.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("collector")
if LOG_FALLBACK:
    logger.warning("logs/ 디렉토리 생성 실패 → collector.log로 폴백")

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


DEFAULT_CONFIG_PATH = BASE_DIR / "config_upbit_exchange.yml"


class CollectorConfig:
    def __init__(
        self,
        name: str,
        pairs: list,
        timeframes_ms: list,
        tick_sizes: list,
        db_path: str,
        derived_timeframes_ms: list,
        max_late_ms: int,
        stats_interval: float,
        queue_high_watermark: int,
        queue_hard_limit: int,
        writer_queue_high_watermark: int,
        writer_queue_hard_limit: int,
        batch_size: int,
    ):
        self.name = name
        self.pairs = pairs
        self.timeframes_ms = timeframes_ms
        self.tick_sizes = tick_sizes
        self.db_path = db_path
        self.derived_timeframes_ms = derived_timeframes_ms
        self.max_late_ms = max_late_ms
        self.stats_interval = stats_interval
        self.queue_high_watermark = queue_high_watermark
        self.queue_hard_limit = queue_hard_limit
        self.writer_queue_high_watermark = writer_queue_high_watermark
        self.writer_queue_hard_limit = writer_queue_hard_limit
        self.batch_size = batch_size


class UpbitCollector:
    def __init__(self, config: CollectorConfig, global_limiter: GlobalReconnectLimiter):
        self.name = config.name
        self.logger = logging.getLogger(f"collector.{self.name}")
        self.pairs = list(config.pairs)
        self.max_late_ms = config.max_late_ms
        self.stats_interval = config.stats_interval
        self.queue_high_watermark = config.queue_high_watermark
        self.queue_hard_limit = config.queue_hard_limit
        self.writer_queue_high_watermark = config.writer_queue_high_watermark
        self.writer_queue_hard_limit = config.writer_queue_hard_limit
        self.backpressure_timeout_seconds = 5.0
        self.global_limiter = global_limiter

        self.writer = OHLCVWriter(
            db_path=config.db_path,
            batch_size=config.batch_size,
            queue_high_watermark=self.writer_queue_high_watermark,
            queue_hard_limit=self.writer_queue_hard_limit,
        )
        self.aggregator = MultiAggregator(
            self.writer,
            timeframes_ms=config.timeframes_ms,
            tick_sizes=config.tick_sizes,
            derived_timeframes_ms=config.derived_timeframes_ms,
            derived_source_timeframe_ms=1000,
            derived_max_store=DEFAULT_DERIVED_MAX_STORE,
        )

        self.trade_queue = queue.Queue(maxsize=self.queue_hard_limit)
        self.dedup = DedupCache(max_size=20000)
        self.last_trade_ts = {}
        self.stats_lock = threading.Lock()
        self.stats = {
            "updates": 0,
            "flushes": 0,
            "invalid_trades": 0,
            "duplicate_trades": 0,
            "out_of_order_trades": 0,
            "parse_errors": 0,
        }
        self.last_message_ts = None
        self.last_flush_ts = None

        self.health_lock = threading.Lock()
        self.health_status = "DOWN"
        self.health_reason = "init"
        self.connected = False
        self.overload_event = threading.Event()
        self.overload_reason = None

        self.running = False
        self.ws = None
        self.ws_thread = None
        self.thread = None
        self.process_thread = None
        self.stats_thread = None
        self.ws_lock = threading.Lock()
        self.ws_close_event = threading.Event()
        self.ws_open_event = threading.Event()
        self.expected_reconnect_event = threading.Event()
        self.shutdown_event = threading.Event()
        self.stop_called = False
        self.reset_lock = threading.Lock()

        # 재연결 정책 (backoff + jitter + 상한/쿨다운)
        self.reconnect_base_delay = RECONNECT_BASE_DELAY
        self.reconnect_max_delay = RECONNECT_MAX_DELAY
        self.reconnect_jitter_max = RECONNECT_JITTER_MAX
        self.reconnect_window_seconds = RECONNECT_WINDOW_SECONDS
        self.reconnect_window_max_attempts = RECONNECT_WINDOW_MAX_ATTEMPTS
        self.reconnect_cooldown_seconds = RECONNECT_COOLDOWN_SECONDS
        self.cooldown_log_interval = 60.0
        self.cooldown_last_log_ts = 0.0
        self.cooldown_active_until = 0.0
        self.reconnect_attempt = 0
        self.reconnect_history = deque()
        self.last_close_info = None

        # 주기적 재연결 (DEC-009)
        self.periodic_reconnect_timer = None
        self.periodic_reconnect_seconds = PERIODIC_RECONNECT_SECONDS
        self.timer_lock = threading.Lock()

        # flush 타이머
        self.flush_lock = threading.Lock()
        self.flush_timer = None
        self.flush_interval = 1.0
        self.flush_enabled = False
        self.flush_idle_event = threading.Event()
        self.flush_idle_event.set()
        self.flush_wait_timeout = 5.0
        self.flush_generation = 0

        # 메시지 파싱/검증 로그 제한
        self.message_parse_error_last_log_ts = 0.0
        self.message_parse_error_log_interval = 60.0
        self.invalid_trade_last_log_ts = 0.0
        self.invalid_trade_log_interval = 60.0
        self.out_of_order_last_log_ts = 0.0
        self.out_of_order_log_interval = 60.0
        self.generation_id = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.process_thread = threading.Thread(
            target=self._process_loop,
            name=f"{self.name}-processor",
            daemon=True,
        )
        self.process_thread.start()
        self.stats_thread = threading.Thread(
            target=self._stats_loop,
            name=f"{self.name}-stats",
            daemon=True,
        )
        self.stats_thread.start()
        self.thread = threading.Thread(
            target=self.run,
            name=f"{self.name}-main",
            daemon=True,
        )
        self.thread.start()

    def join(self, timeout: float = None):
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
        if self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=timeout)
        if self.stats_thread and self.stats_thread.is_alive():
            self.stats_thread.join(timeout=timeout)

    def on_open(self, ws):
        self.logger.info("WebSocket connected")
        self.ws_open_event.set()
        self.ws_close_event.clear()
        self.connected = True
        self._set_health("OK", "connected")
        self.reconnect_attempt = 0
        self.reconnect_history.clear()
        self.overload_event.clear()
        self.overload_reason = None
        self._bump_generation()
        ws.send(json.dumps([
            {"ticket": f"upbit-{self.name}"},
            {
                "type": "trade",
                "codes": self.pairs,
                "isOnlyRealtime": True,
            }
        ]))
        self._start_flush_timer()
        self._start_periodic_reconnect_timer()

    def on_message(self, ws, message):
        self.last_message_ts = time.time()
        try:
            if isinstance(message, (bytes, bytearray)):
                message = message.decode("utf-8", errors="replace")
            data = json.loads(message)
            if not isinstance(data, dict) or data.get("type") != "trade":
                return
            pair = data["code"]
            price = data["trade_price"]
            volume = data["trade_volume"]
            ts_ms = data["trade_timestamp"]

            if price <= 0 or volume < 0:
                self._record_invalid_trade(f"price/volume invalid: price={price}, volume={volume}")
                return

            last_ts = self.last_trade_ts.get(pair)
            if last_ts is not None and ts_ms < last_ts:
                self._record_out_of_order(pair, last_ts, ts_ms)
                return
            self.last_trade_ts[pair] = max(ts_ms, last_ts or ts_ms)

            trade_uuid = data.get("trade_uuid")
            sequential_id = data.get("sequential_id", data.get("sequentialId"))
            ask_bid = data.get("ask_bid")
            if trade_uuid:
                dedup_key = ("uuid", trade_uuid)
            elif sequential_id is not None:
                dedup_key = ("seq", pair, sequential_id)
            else:
                dedup_key = ("fallback", pair, ts_ms, price, volume, ask_bid)
            if self.dedup.add_and_check(pair, dedup_key):
                with self.stats_lock:
                    self.stats["duplicate_trades"] += 1
                return

            self._enqueue_trade(pair, price, volume, ts_ms, self.generation_id)
        except (json.JSONDecodeError, KeyError) as e:
            now = time.time()
            if now - self.message_parse_error_last_log_ts >= self.message_parse_error_log_interval:
                self.logger.error(f"메시지 파싱 에러: {e}")
                self.message_parse_error_last_log_ts = now
            with self.stats_lock:
                self.stats["parse_errors"] += 1
        except Exception as e:
            self.logger.error(f"메시지 처리 에러: {e}")

    def on_error(self, ws, error):
        self.logger.error(f"WebSocket 에러: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        close_info = self._parse_close_info(close_status_code, close_msg)
        self.last_close_info = close_info
        self.connected = False
        try:
            if self.expected_reconnect_event.is_set() or self.overload_event.is_set():
                self.logger.warning(f"WebSocket 연결 종료(의도적): {close_info}")
            else:
                self.logger.warning(f"WebSocket 연결 종료: {close_info}")
            self._stop_flush_timer()
            self._stop_periodic_reconnect_timer()
            if not self.shutdown_event.is_set():
                self._set_health("DOWN", "disconnected")
        except Exception as e:
            self.logger.error(f"on_close 정리 중 에러: {e}")
        finally:
            self.ws_close_event.set()

    def _process_loop(self):
        while True:
            if self.shutdown_event.is_set() and self.trade_queue.empty():
                break
            try:
                item = self.trade_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                self.trade_queue.task_done()
                break
            pair, price, volume, ts_ms, generation_id = item
            if generation_id != self.generation_id:
                self.trade_queue.task_done()
                continue
            try:
                with self.reset_lock:
                    self.aggregator.update(pair, price, volume, ts_ms)
                with self.stats_lock:
                    self.stats["updates"] += 1
            finally:
                self.trade_queue.task_done()

    def _stats_loop(self):
        while not self.shutdown_event.wait(timeout=self.stats_interval):
            self._check_writer_queue_pressure()
            stats = self.get_stats()
            self.logger.info(
                "stats updates=%d flushes=%d invalid=%d dup=%d out_of_order=%d "
                "last_message_age=%s trade_q=%d writer_q=%d last_flush_age=%s status=%s",
                stats["updates"],
                stats["flushes"],
                stats["invalid_trades"],
                stats["duplicate_trades"],
                stats["out_of_order_trades"],
                stats["last_message_age"],
                stats["trade_queue_depth"],
                stats["writer_queue_depth"],
                stats["last_flush_age"],
                stats["status"],
            )

    def _enqueue_trade(self, pair, price, volume, ts_ms, generation_id):
        if self.shutdown_event.is_set():
            return
        backpressure_deadline = time.time() + self.backpressure_timeout_seconds
        while not self.shutdown_event.is_set():
            qsize = self.trade_queue.qsize()
            writer_depth = self.writer.get_queue_depth()
            if qsize >= self.queue_hard_limit:
                self._trigger_overload_disconnect("trade_queue_hard_limit")
                return
            if writer_depth >= self.writer_queue_hard_limit:
                self._trigger_overload_disconnect("writer_queue_hard_limit")
                return
            if qsize >= self.queue_high_watermark:
                self._set_health("DEGRADED", "trade_queue_high")
                if time.time() >= backpressure_deadline:
                    self._trigger_overload_disconnect("backpressure_timeout")
                    return
                if self.shutdown_event.wait(timeout=0.05):
                    return
                continue
            if writer_depth >= self.writer_queue_high_watermark:
                self._set_health("DEGRADED", "writer_queue_high")
                if time.time() >= backpressure_deadline:
                    self._trigger_overload_disconnect("backpressure_timeout")
                    return
                if self.shutdown_event.wait(timeout=0.05):
                    return
                continue
            break

        while not self.shutdown_event.is_set():
            try:
                self.trade_queue.put((pair, price, volume, ts_ms, generation_id), timeout=0.5)
                return
            except queue.Full:
                self._trigger_overload_disconnect("trade_queue_hard_limit")
                if self.shutdown_event.wait(timeout=0.5):
                    return

    def _trigger_overload_disconnect(self, reason: str):
        if self.overload_event.is_set():
            return
        self.overload_event.set()
        self.overload_reason = reason
        self._set_health("DEGRADED", reason)
        self.cooldown_active_until = max(
            self.cooldown_active_until,
            time.time() + self.reconnect_cooldown_seconds,
        )
        self.logger.warning(f"오버로드 보호 동작: {reason} → 연결 종료")
        self._close_ws()

    def _check_writer_queue_pressure(self):
        depth = self.writer.get_queue_depth()
        if depth >= self.writer_queue_hard_limit:
            self._trigger_overload_disconnect("writer_queue_hard_limit")
        elif depth >= self.writer_queue_high_watermark:
            self._set_health("DEGRADED", "writer_queue_high")
        if self.writer.is_degraded():
            self._set_health("DEGRADED", "writer_locked_timeout")

    def _record_invalid_trade(self, reason: str):
        now = time.time()
        if now - self.invalid_trade_last_log_ts >= self.invalid_trade_log_interval:
            self.logger.warning(f"invalid trade: {reason}")
            self.invalid_trade_last_log_ts = now
        with self.stats_lock:
            self.stats["invalid_trades"] += 1

    def _record_out_of_order(self, pair: str, last_ts: int, ts_ms: int):
        now = time.time()
        if now - self.out_of_order_last_log_ts >= self.out_of_order_log_interval:
            self.logger.warning(f"[{pair}] timestamp 역전: last={last_ts}, now={ts_ms}")
            self.out_of_order_last_log_ts = now
        with self.stats_lock:
            self.stats["out_of_order_trades"] += 1

    def _periodic_flush(self, generation: int = None):
        with self.flush_lock:
            if generation is not None and generation != self.flush_generation:
                self.flush_idle_event.set()
                return
            if not self.flush_enabled or not self.running or self.shutdown_event.is_set():
                self.flush_idle_event.set()
                return
            self.flush_idle_event.clear()

        try:
            flushed = self.aggregator.flush(self.max_late_ms)
            if flushed > 0:
                with self.stats_lock:
                    self.stats["flushes"] += 1
                self.last_flush_ts = time.time()
        except Exception as e:
            self.logger.error(f"Flush 에러: {e}")
        finally:
            self.flush_idle_event.set()

        with self.flush_lock:
            if generation is not None and generation != self.flush_generation:
                return
            if self.flush_enabled and self.running and not self.shutdown_event.is_set():
                self._schedule_flush_locked()

    def _start_flush_timer(self):
        with self.flush_lock:
            if self.flush_enabled:
                return
            self.flush_enabled = True
            self.flush_generation += 1
            generation = self.flush_generation
        self._periodic_flush(generation=generation)

    def _stop_flush_timer(self):
        with self.flush_lock:
            self.flush_enabled = False
            self.flush_generation += 1
            if self.flush_timer:
                self.flush_timer.cancel()
                self.flush_timer = None

    def _schedule_flush_locked(self):
        if not self.flush_enabled or not self.running or self.shutdown_event.is_set():
            return
        generation = self.flush_generation
        self.flush_timer = threading.Timer(
            self.flush_interval,
            self._periodic_flush,
            kwargs={"generation": generation},
        )
        self.flush_timer.daemon = True
        self.flush_timer.start()

    def _start_periodic_reconnect_timer(self):
        with self.timer_lock:
            if self.periodic_reconnect_timer:
                self.periodic_reconnect_timer.cancel()
            self.periodic_reconnect_timer = threading.Timer(
                self.periodic_reconnect_seconds,
                self._request_periodic_reconnect
            )
            self.periodic_reconnect_timer.daemon = True
            self.periodic_reconnect_timer.start()
            self.logger.info(f"주기적 재연결 예약됨: {self.periodic_reconnect_seconds}초 후")

    def _stop_periodic_reconnect_timer(self):
        with self.timer_lock:
            if self.periodic_reconnect_timer:
                self.periodic_reconnect_timer.cancel()
                self.periodic_reconnect_timer = None

    def _wait_for_flush_idle(self):
        if not self.flush_idle_event.wait(timeout=self.flush_wait_timeout):
            self.logger.warning(f"flush 종료 대기 타임아웃: {self.flush_wait_timeout}s")

    def _wait_queue_drained(self, q: queue.Queue, timeout: float, label: str) -> bool:
        done = threading.Event()

        def _join_queue():
            try:
                q.join()
            finally:
                done.set()

        thread = threading.Thread(
            target=_join_queue,
            name=f"{label}-join",
            daemon=True,
        )
        thread.start()
        if not done.wait(timeout=timeout):
            self.logger.warning(f"{label} drain 타임아웃 (qsize={q.qsize()}, timeout={timeout:.1f}s)")
            return False
        return True

    def _request_periodic_reconnect(self):
        if not self.running or self.shutdown_event.is_set():
            return
        self.logger.warning("주기적 재연결 시작 (9시간 주기)")
        self.expected_reconnect_event.set()
        try:
            self.aggregator.flush(0)
        except Exception as e:
            self.logger.error(f"주기적 재연결 전 flush 에러: {e}")
        self._close_ws()

    def _parse_close_info(self, close_status_code, close_msg):
        parts = []
        if close_status_code is not None:
            parts.append(f"code={close_status_code}")
        if close_msg is not None:
            try:
                if isinstance(close_msg, bytes):
                    hex_msg = close_msg.hex()
                    parts.append(f"msg_hex=0x{hex_msg}")
                    if len(close_msg) == 2:
                        parts.append(f"msg_int={int.from_bytes(close_msg, 'big')}")
                    else:
                        parts.append(f"msg_bytes_len={len(close_msg)}")
                else:
                    parts.append(f"msg={close_msg}")
            except Exception as e:
                parts.append(f"msg_parse_error={e}")
        if not parts:
            return "code=None, msg=None"
        return ", ".join(parts)

    def _close_ws(self):
        with self.ws_lock:
            if not self.ws:
                return
            try:
                self.ws.close()
                if hasattr(self.ws, 'keep_running'):
                    self.ws.keep_running = False
            except Exception as e:
                self.logger.error(f"WebSocket 종료 에러: {e}")
            finally:
                self.ws = None

    def _compute_reconnect_delay(self):
        now = time.time()
        self.reconnect_history.append(now)
        while self.reconnect_history and now - self.reconnect_history[0] > self.reconnect_window_seconds:
            self.reconnect_history.popleft()

        base_delay = self.reconnect_base_delay * (2 ** min(self.reconnect_attempt, 10))
        base_delay = min(base_delay, self.reconnect_max_delay)
        jitter = random.uniform(0.0, self.reconnect_jitter_max)
        delay = base_delay + jitter

        if len(self.reconnect_history) >= self.reconnect_window_max_attempts:
            delay = max(delay, self.reconnect_cooldown_seconds)
            self.cooldown_active_until = max(self.cooldown_active_until, now + delay)
            if now - self.cooldown_last_log_ts >= self.cooldown_log_interval:
                remaining = max(0, self.cooldown_active_until - now)
                self.logger.warning(
                    f"재연결 시도 과다: {len(self.reconnect_history)}회/{self.reconnect_window_seconds}초 "
                    f"→ 쿨다운 적용, 남은 시간 {remaining:.0f}s"
                )
                self.cooldown_last_log_ts = now

        if now < self.cooldown_active_until:
            delay = max(delay, self.cooldown_active_until - now)

        return delay

    def _cleanup_previous_connection(self):
        self._close_ws()
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)
            if self.ws_thread.is_alive():
                self.logger.warning(
                    "이전 ws_thread 종료 지연 "
                    f"(alive={self.ws_thread.is_alive()}, running={self.running}, "
                    f"shutdown={self.shutdown_event.is_set()})"
                )
                return False
        return True

    def _bump_generation(self):
        self.generation_id += 1
        self.logger.info(f"generation 증가: {self.generation_id}")
        with self.reset_lock:
            self.dedup.reset()
            self.last_trade_ts.clear()
            drained_trades = self._drain_queue(self.trade_queue)
            drained_writes = self.writer.clear_queue()
            self.aggregator.reset_generation()
        if drained_trades or drained_writes:
            self.logger.warning(
                f"세션 전환 드레인: trade={drained_trades}, writer={drained_writes}"
            )

    def _drain_queue(self, q: queue.Queue) -> int:
        drained = 0
        while True:
            try:
                q.get_nowait()
                q.task_done()
                drained += 1
            except queue.Empty:
                break
        return drained

    def run(self):
        self.logger.info("Collector 실행 시작")
        try:
            while self.running and not self.shutdown_event.is_set():
                self.expected_reconnect_event.clear()
                self.ws_close_event.clear()
                self.ws_open_event.clear()

                if not self._cleanup_previous_connection():
                    if self.shutdown_event.wait(timeout=1.0):
                        break
                    continue

                if not self.global_limiter.wait_for_slot(self.shutdown_event):
                    break

                self.ws = websocket.WebSocketApp(
                    UPBIT_WS_URL,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )

                self.ws_thread = threading.Thread(
                    target=self.ws.run_forever,
                    kwargs={'ping_interval': 60, 'ping_timeout': 30},
                    daemon=True
                )
                self.ws_thread.start()

                while self.running and not self.shutdown_event.is_set():
                    if self.ws_close_event.wait(timeout=1.0):
                        break

                if self.shutdown_event.is_set() or not self.running:
                    break

                try:
                    self.aggregator.flush(0)
                except Exception as e:
                    self.logger.error(f"재연결 전 flush 에러: {e}")

                self.reconnect_attempt += 1
                delay = self._compute_reconnect_delay()
                if self.expected_reconnect_event.is_set():
                    delay = min(delay, 1.0)
                self.expected_reconnect_event.clear()
                self.logger.warning(
                    f"재연결 시도 #{self.reconnect_attempt} 예정 "
                    f"(delay={delay:.2f}s, last_close={self.last_close_info})"
                )

                if self.shutdown_event.wait(timeout=delay):
                    break
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt 수신")
        finally:
            self.logger.info("Collector 메인 루프 종료")

    def stop(self):
        if self.stop_called:
            return
        self.stop_called = True
        self.logger.info("Collector 종료 시작...")
        self.running = False
        self.shutdown_event.set()

        self._stop_flush_timer()
        self._stop_periodic_reconnect_timer()
        self._wait_for_flush_idle()

        self._close_ws()
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)

        self._wait_queue_drained(self.trade_queue, timeout=10.0, label="trade_queue")

        try:
            self.logger.info("마지막 flush 실행 중...")
            self.aggregator.flush(0)
            self.aggregator.shutdown()
        except Exception as e:
            self.logger.error(f"종료 중 에러: {e}")

        try:
            self.logger.info("Writer 종료 중...")
            self.writer.close()
        except Exception as e:
            self.logger.error(f"Writer 종료 에러: {e}")

        if self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=2.0)

        self.logger.info("Collector 종료 완료")

    def get_stats(self) -> dict:
        with self.stats_lock:
            stats = self.stats.copy()
        stats["status"] = self.health_status
        stats["last_message_age"] = self._get_last_message_age()
        stats["trade_queue_depth"] = self.trade_queue.qsize()
        stats["writer_queue_depth"] = self.writer.get_queue_depth()
        stats["last_flush_age"] = self._get_last_flush_age()
        stats["generation_id"] = self.generation_id
        return stats

    def get_health(self) -> dict:
        with self.health_lock:
            status = self.health_status
            reason = self.health_reason
        return {
            "status": status,
            "reason": reason,
            "last_message_age": self._get_last_message_age(),
            "trade_queue_depth": self.trade_queue.qsize(),
            "writer_queue_depth": self.writer.get_queue_depth(),
            "generation_id": self.generation_id,
            "connected": self.connected,
        }

    def _get_last_message_age(self):
        if self.last_message_ts is None:
            return None
        return max(0.0, time.time() - self.last_message_ts)

    def _get_last_flush_age(self):
        if self.last_flush_ts is None:
            return None
        return max(0.0, time.time() - self.last_flush_ts)

    def _set_health(self, status: str, reason: str):
        with self.health_lock:
            prev = self.health_status
            if status == prev and reason == self.health_reason:
                return
            self.health_status = status
            self.health_reason = reason
        if status != prev:
            self.logger.info(f"상태 전이: {prev} → {status} ({reason})")


class CollectorManager:
    def __init__(self, configs: list, http_port: int = 0):
        self.collectors = []
        self.http_port = http_port or 0
        self.http_server = None
        self.http_thread = None
        self.shutdown_event = threading.Event()
        self.global_limiter = GlobalReconnectLimiter()
        for config in configs:
            self.collectors.append(UpbitCollector(config, self.global_limiter))

    def start(self):
        for collector in self.collectors:
            collector.start()
        if self.http_port:
            self._start_http_server()

    def stop(self):
        if self.shutdown_event.is_set():
            return
        self.shutdown_event.set()
        if self.http_server:
            self.http_server.shutdown()
            if self.http_thread and self.http_thread.is_alive():
                self.http_thread.join(timeout=2.0)
            self.http_server.server_close()
            self.http_server = None
        for collector in self.collectors:
            collector.stop()

    def join(self):
        for collector in self.collectors:
            collector.join(timeout=2.0)

    def wait(self):
        while not self.shutdown_event.is_set():
            time.sleep(1.0)

    def get_health_snapshot(self) -> dict:
        return {
            "ts": int(time.time()),
            "collectors": {
                collector.name: collector.get_health()
                for collector in self.collectors
            }
        }

    def get_stats_snapshot(self) -> dict:
        return {
            "ts": int(time.time()),
            "collectors": {
                collector.name: collector.get_stats()
                for collector in self.collectors
            }
        }

    def _start_http_server(self):
        handler = self._make_handler()
        self.http_server = HTTPServer(("0.0.0.0", self.http_port), handler)
        self.http_thread = threading.Thread(
            target=self.http_server.serve_forever,
            name="collector-http",
            daemon=True,
        )
        self.http_thread.start()
        logger.info(f"HTTP 서버 시작: port={self.http_port}")

    def _make_handler(self):
        manager = self

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    data = manager.get_health_snapshot()
                    self._write_json(200, data)
                    return
                if self.path == "/stats":
                    data = manager.get_stats_snapshot()
                    self._write_json(200, data)
                    return
                self._write_json(404, {"error": "not_found"})

            def _write_json(self, status_code: int, data: dict):
                payload = json.dumps(data).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):
                return

        return HealthHandler


def _load_config(path: Path) -> dict:
    if not path.exists():
        logger.warning(f"설정 파일 없음: {path}")
        return {}
    try:
        import yaml
    except Exception as e:
        logger.warning(f"yaml 모듈 없음 → 기본값 사용: {e}")
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as e:
        logger.warning(f"설정 파일 로드 실패 → 기본값 사용: {e}")
        return {}


def _parse_pairs(value: str) -> list:
    if not value:
        return []
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts


def _coerce_int_list(value, default_list):
    if isinstance(value, list) and value:
        result = []
        for item in value:
            try:
                result.append(int(item))
            except Exception:
                continue
        if result:
            return result
    return list(default_list)


def _migrate_short_db(base_dir: Path):
    old_db = base_dir / "ohlcv.sqlite"
    short_db = base_dir / "ohlcv_short.sqlite"
    if short_db.exists():
        return
    if not old_db.exists():
        return
    try:
        old_db.rename(short_db)
        logger.warning(f"DB 마이그레이션 완료: {old_db} → {short_db}")
    except Exception as e:
        logger.error(f"DB 마이그레이션 실패: {e}", exc_info=True)
        raise SystemExit(1)


def _build_collector_configs(config: dict, pairs: list) -> list:
    short_timeframes = _coerce_int_list(config.get("short_timeframes_ms"), [500, 1000])
    mid_timeframes = _coerce_int_list(config.get("mid_timeframes_ms"), [10000, 60000])
    long_timeframes = _coerce_int_list(config.get("long_timeframes_ms"), [600000])
    derived_timeframes = _coerce_int_list(
        config.get("derived_timeframes_ms"),
        [5000, 10000, 33000, 57000, 60000],
    )
    derived_enabled = config.get("derived_timeframes_enabled", True)
    max_late_ms = int(config.get("max_late_ms", DEFAULT_MAX_LATE_MS))
    stats_interval = float(config.get("stats_interval", DEFAULT_STATS_INTERVAL))
    batch_size = int(config.get("batch_size", DEFAULT_BATCH_SIZE))

    queue_high = int(config.get("queue_high_watermark", DEFAULT_QUEUE_HIGH_WATERMARK))
    queue_hard = int(config.get("queue_hard_limit", DEFAULT_QUEUE_HARD_LIMIT))
    writer_queue_high = int(
        config.get("writer_queue_high_watermark", DEFAULT_WRITER_QUEUE_HIGH_WATERMARK)
    )
    writer_queue_hard = int(
        config.get("writer_queue_hard_limit", DEFAULT_WRITER_QUEUE_HARD_LIMIT)
    )

    configs = [
        CollectorConfig(
            name="short",
            pairs=pairs,
            timeframes_ms=short_timeframes,
            tick_sizes=[3],
            db_path=str(BASE_DIR / "ohlcv_short.sqlite"),
            derived_timeframes_ms=derived_timeframes if derived_enabled else [],
            max_late_ms=max_late_ms,
            stats_interval=stats_interval,
            queue_high_watermark=queue_high,
            queue_hard_limit=queue_hard,
            writer_queue_high_watermark=writer_queue_high,
            writer_queue_hard_limit=writer_queue_hard,
            batch_size=batch_size,
        ),
        CollectorConfig(
            name="mid",
            pairs=pairs,
            timeframes_ms=mid_timeframes,
            tick_sizes=[],
            db_path=str(BASE_DIR / "ohlcv_10s_1m.sqlite"),
            derived_timeframes_ms=[],
            max_late_ms=max_late_ms,
            stats_interval=stats_interval,
            queue_high_watermark=queue_high,
            queue_hard_limit=queue_hard,
            writer_queue_high_watermark=writer_queue_high,
            writer_queue_hard_limit=writer_queue_hard,
            batch_size=batch_size,
        ),
        CollectorConfig(
            name="long",
            pairs=pairs,
            timeframes_ms=long_timeframes,
            tick_sizes=[],
            db_path=str(BASE_DIR / "ohlcv_10m.sqlite"),
            derived_timeframes_ms=[],
            max_late_ms=max_late_ms,
            stats_interval=stats_interval,
            queue_high_watermark=queue_high,
            queue_hard_limit=queue_hard,
            writer_queue_high_watermark=writer_queue_high,
            writer_queue_hard_limit=writer_queue_hard,
            batch_size=batch_size,
        ),
    ]
    return configs


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Upbit OHLCV Collector (Phase 2 ONLY)")
    parser.add_argument("--pairs", type=str, default=None, help="예: KRW-BTC,KRW-ETH")
    parser.add_argument("--http-port", type=int, default=None, help="HTTP 포트 (0이면 비활성)")
    args = parser.parse_args()

    config = _load_config(DEFAULT_CONFIG_PATH)
    pairs = _parse_pairs(args.pairs) if args.pairs else config.get("pairs", DEFAULT_PAIRS)
    if isinstance(pairs, str):
        pairs = _parse_pairs(pairs)
    if not pairs:
        pairs = DEFAULT_PAIRS

    http_port = args.http_port
    if http_port is None:
        http_enabled = config.get("http_enabled", True)
        http_port = int(config.get("http_port", DEFAULT_HTTP_PORT)) if http_enabled else 0

    _migrate_short_db(BASE_DIR)
    configs = _build_collector_configs(config, pairs)
    manager = CollectorManager(configs, http_port=http_port)

    def shutdown(sig, frame):
        logger.info(f"\n시그널 수신: {sig}")
        manager.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        manager.start()
        manager.wait()
    except Exception as e:
        logger.error(f"예외 발생: {e}", exc_info=True)
    finally:
        manager.stop()
        manager.join()


if __name__ == "__main__":
    main()