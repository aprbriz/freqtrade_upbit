# collector.py
import json
import time
import signal
import argparse
import logging
import threading
import random
import http.server
import urllib.parse
from pathlib import Path
from collections import deque
import websocket
from ohlcv_writer import OHLCVWriter
from multi_aggregator import MultiAggregator




# watchdog 관련 logging 설정
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE_PATH = LOG_DIR / "collector.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(LOG_FILE_PATH)),
        logging.StreamHandler()
    ]
)




logger = logging.getLogger("collector")

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
DEFAULT_PAIRS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
DEFAULT_MAX_LATE_MS = 2000
DEFAULT_STATS_INTERVAL = 30.0
DEFAULT_HTTP_PORT = 8000
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config_upbit_exchange.yml"

# Phase 2 기본 타임프레임 설정
SHORT_TIMEFRAMES_MS = [500, 1000]
SHORT_TICK_SIZES = [3]
DERIVED_TIMEFRAMES_MS = [5000, 10000, 33000, 57000, 60000]
MID_TIMEFRAMES_MS = [10000, 60000]
LONG_TIMEFRAMES_MS = [600000]


class CollectorConfig:
    def __init__(
        self,
        name: str,
        pairs: list,
        timeframes_ms: list,
        tick_sizes: list,
        db_path: Path,
        derived_timeframes_ms: list = None,
    ):
        self.name = name
        self.pairs = pairs
        self.timeframes_ms = timeframes_ms
        self.tick_sizes = tick_sizes
        self.db_path = db_path
        self.derived_timeframes_ms = derived_timeframes_ms


class UpbitCollector:
    def __init__(
        self,
        config: CollectorConfig,
        max_late_ms: int = DEFAULT_MAX_LATE_MS,
        stats_interval: float = DEFAULT_STATS_INTERVAL,
    ):
        self.name = config.name
        self.pairs = config.pairs
        self.max_late_ms = max_late_ms
        self.stats_interval = stats_interval
        
        self.writer = OHLCVWriter(db_path=str(config.db_path))
        self.aggregator = MultiAggregator(
            self.writer,
            timeframes_ms=config.timeframes_ms,
            tick_sizes=config.tick_sizes,
            derived_timeframes_ms=config.derived_timeframes_ms,
        )
        self.running = True
        self.ws = None
        self.ws_thread = None
        self.ws_lock = threading.Lock()
        self.ws_close_event = threading.Event()
        self.ws_open_event = threading.Event()
        self.last_close_info = None
        self.expected_reconnect_event = threading.Event()
        self.timer_lock = threading.Lock()
        self.reconnect_attempt = 0
        self.reconnect_history = deque()
        self.stop_called = False
        
        # 데이터 정합성 검증 통계
        self.last_trade_ts = {}
        self.invalid_trade_count = 0
        self.out_of_order_trade_count = 0
        self.last_message_ts = None
        self.invalid_trade_log_interval = 60.0
        self.last_invalid_trade_log_ts = 0.0
        self.out_of_order_log_interval = 60.0
        self.last_out_of_order_log_ts = 0.0
        
        # 재연결 정책 (backoff + jitter + 상한/쿨다운)
        self.reconnect_base_delay = 1.0
        self.reconnect_max_delay = 60.0
        self.reconnect_jitter_ratio = 0.3
        self.reconnect_window_seconds = 300
        self.reconnect_window_max_attempts = 10
        self.reconnect_cooldown_seconds = 300
        self.cooldown_log_interval = 60.0
        self.cooldown_last_log_ts = 0.0
        self.cooldown_active_until = 0.0
        
        # 주기적 재연결 (DEC-009)
        self.periodic_reconnect_timer = None
        self.periodic_reconnect_seconds = 9 * 60 * 60
        
        # [개선1] flush 타이머 추가
        # 이유: 주기적으로 flush하여 데이터 손실 방지
        self.flush_timer = None
        self.flush_interval = 1.0  # 1초마다 flush
        
        # [개선2] 종료 이벤트 추가
        # 이유: 종료 시그널을 명확하게 전달
        self.shutdown_event = threading.Event()
        
        # 메시지 파싱 오류 로그 제한
        self.message_parse_error_last_log_ts = 0.0
        self.message_parse_error_log_interval = 60.0
        
        # 통계 로그 타이머
        self.stats_timer = None
    
    def on_open(self, ws):
        logger.info(f"[{self.name}] WebSocket connected")
        self.ws_open_event.set()
        self.ws_close_event.clear()
        # [개선-재연결] 성공 시 카운터 초기화
        self.reconnect_attempt = 0
        self.reconnect_history.clear()
        ws.send(json.dumps([
            {"ticket": f"upbit-collector-{self.name}"},
            {
                "type": "trade",
                "codes": self.pairs,
                "isOnlyRealtime": True,
            }
        ]))
        
        # [개선3] 연결 성공 시 flush 타이머 시작
        self._start_flush_timer()
        
        # [개선-재연결] 주기적 재연결 타이머 시작
        self._start_periodic_reconnect_timer()
    
    def on_message(self, ws, message):
        # [개선4] 메시지 파싱 예외 처리
        # 이유: 잘못된 메시지로 인한 크래시 방지
        try:
            if isinstance(message, (bytes, bytearray)):
                message = message.decode("utf-8", errors="replace")
            data = json.loads(message)
            pair = data["code"]
            price = data["trade_price"]
            volume = data["trade_volume"]
            ts_ms = data["trade_timestamp"]
            
            # 마지막 메시지 시각 갱신
            self.last_message_ts = time.time()
            
            # 데이터 정합성 검증
            if price <= 0 or volume < 0:
                self.invalid_trade_count += 1
                now = time.time()
                if now - self.last_invalid_trade_log_ts >= self.invalid_trade_log_interval:
                    logger.warning(f"[{self.name}] 잘못된 체결 데이터: price={price}, volume={volume}")
                    self.last_invalid_trade_log_ts = now
                return
            
            last_ts = self.last_trade_ts.get(pair)
            if last_ts is not None and ts_ms < last_ts:
                self.out_of_order_trade_count += 1
                now = time.time()
                if now - self.last_out_of_order_log_ts >= self.out_of_order_log_interval:
                    logger.warning(f"[{self.name}] 체결 타임스탬프 역전: last={last_ts}, now={ts_ms}")
                    self.last_out_of_order_log_ts = now
            self.last_trade_ts[pair] = max(ts_ms, last_ts or ts_ms)
            
            self.aggregator.update(pair, price, volume, ts_ms)
            
        except (json.JSONDecodeError, KeyError) as e:
            now = time.time()
            if now - self.message_parse_error_last_log_ts >= self.message_parse_error_log_interval:
                logger.error(f"[{self.name}] 메시지 파싱 에러: {e}")
                self.message_parse_error_last_log_ts = now
        except Exception as e:
            logger.error(f"[{self.name}] 메시지 처리 에러: {e}")
    
    def on_error(self, ws, error):
        # [개선5] 에러 핸들러 추가
        # 이유: 에러 상황 모니터링
        logger.error(f"[{self.name}] WebSocket 에러: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        # [개선6] 종료 핸들러 추가
        # 이유: 연결 종료 시 정리 작업
        close_info = self._parse_close_info(close_status_code, close_msg)
        self.last_close_info = close_info
        if self.expected_reconnect_event.is_set():
            logger.warning(f"[{self.name}] WebSocket 연결 종료(의도적): {close_info}")
        else:
            logger.warning(f"[{self.name}] WebSocket 연결 종료: {close_info}")
        self._stop_flush_timer()
        self._stop_periodic_reconnect_timer()
        self.ws_close_event.set()
    
    def _periodic_flush(self):
        """
        [개선7] 주기적 flush 함수
        이유: 체결이 없어도 주기적으로 오래된 캔들 저장
        """
        if not self.running:
            return
        
        try:
            self.aggregator.flush(self.max_late_ms)
        except Exception as e:
            logger.error(f"[{self.name}] Flush 에러: {e}")
        
        # 다음 flush 예약
        if self.running:
            self.flush_timer = threading.Timer(self.flush_interval, self._periodic_flush)
            self.flush_timer.daemon = True
            self.flush_timer.start()
    
    def _start_flush_timer(self):
        """flush 타이머 시작"""
        if self.flush_timer is None or not self.flush_timer.is_alive():
            self._periodic_flush()
    
    def _stop_flush_timer(self):
        """flush 타이머 중지"""
        if self.flush_timer and self.flush_timer.is_alive():
            self.flush_timer.cancel()

    def _periodic_stats_log(self):
        """
        통계 로그 출력
        """
        if not self.running or self.shutdown_event.is_set():
            return
        
        try:
            stats = self.get_stats()
            logger.info(
                f"[{self.name}] stats updates={stats['updates']} "
                f"flushes={stats['flushes']} invalid_trades={stats['invalid_trades']} "
                f"out_of_order={stats['out_of_order_trades']} last_msg_age={stats['last_message_age']}"
            )
        except Exception as e:
            logger.error(f"[{self.name}] 통계 로그 에러: {e}")
        
        if self.running:
            self.stats_timer = threading.Timer(self.stats_interval, self._periodic_stats_log)
            self.stats_timer.daemon = True
            self.stats_timer.start()

    def _start_stats_timer(self):
        """통계 타이머 시작"""
        if self.stats_timer is None or not self.stats_timer.is_alive():
            self._periodic_stats_log()

    def _stop_stats_timer(self):
        """통계 타이머 중지"""
        if self.stats_timer and self.stats_timer.is_alive():
            self.stats_timer.cancel()
    
    def _start_periodic_reconnect_timer(self):
        """주기적 재연결 타이머 시작 (중복 방지)"""
        with self.timer_lock:
            if self.periodic_reconnect_timer:
                self.periodic_reconnect_timer.cancel()
            self.periodic_reconnect_timer = threading.Timer(
                self.periodic_reconnect_seconds,
                self._request_periodic_reconnect
            )
            self.periodic_reconnect_timer.daemon = True
            self.periodic_reconnect_timer.start()
            logger.info(f"[{self.name}] 주기적 재연결 예약됨: {self.periodic_reconnect_seconds}초 후")
    
    def _stop_periodic_reconnect_timer(self):
        """주기적 재연결 타이머 중지"""
        with self.timer_lock:
            if self.periodic_reconnect_timer:
                self.periodic_reconnect_timer.cancel()

    def get_stats(self) -> dict:
        """
        통계 정보 조회
        """
        now = time.time()
        last_message_age = None
        if self.last_message_ts is not None:
            last_message_age = round(now - self.last_message_ts, 2)
        aggr_stats = self.aggregator.get_stats()
        
        stats = {
            "name": self.name,
            "updates": aggr_stats.get("total_updates"),
            "flushes": aggr_stats.get("total_flushes"),
            "invalid_trades": self.invalid_trade_count,
            "out_of_order_trades": self.out_of_order_trade_count,
            "last_message_age": last_message_age,
            "reconnect_attempt": self.reconnect_attempt,
            "last_close_info": self.last_close_info,
            "aggregators": aggr_stats,
            "writer": self.writer.get_stats(),
        }
        return stats

    def get_health(self) -> dict:
        """
        헬스체크 정보 조회
        """
        now = time.time()
        last_message_age = None
        if self.last_message_ts is not None:
            last_message_age = now - self.last_message_ts
        
        is_healthy = (
            self.running
            and not self.shutdown_event.is_set()
            and self.ws_open_event.is_set()
            and (last_message_age is None or last_message_age < 30)
        )
        
        return {
            "name": self.name,
            "running": self.running,
            "ws_open": self.ws_open_event.is_set(),
            "shutdown": self.shutdown_event.is_set(),
            "last_message_age": None if last_message_age is None else round(last_message_age, 2),
            "healthy": is_healthy,
        }
    
    def _request_periodic_reconnect(self):
        """
        [개선-재연결] 주기적 재연결 요청
        이유: 장기 연결 종료 회피 (DEC-009)
        """
        if not self.running or self.shutdown_event.is_set():
            return
        logger.warning(f"[{self.name}] 주기적 재연결 시작 (9시간 주기)")
        self.expected_reconnect_event.set()
        # 재연결 전 데이터 flush
        try:
            self.aggregator.flush(0)
        except Exception as e:
            logger.error(f"[{self.name}] 주기적 재연결 전 flush 에러: {e}")
        # WebSocket 종료 요청
        self._close_ws()
    
    def _parse_close_info(self, close_status_code, close_msg):
        """
        [개선-재연결] 종료 코드/메시지 파싱
        이유: b'\\x83\\xe8' 등 원인 파악 가능
        """
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
        """WebSocket 안전 종료 (중복 방지)"""
        with self.ws_lock:
            if not self.ws:
                return
            try:
                self.ws.close()
                if hasattr(self.ws, 'keep_running'):
                    self.ws.keep_running = False
            except Exception as e:
                logger.error(f"[{self.name}] WebSocket 종료 에러: {e}")
            finally:
                self.ws = None
    
    def _compute_reconnect_delay(self):
        """
        [개선-재연결] backoff + jitter + 상한/쿨다운 계산
        """
        now = time.time()
        # 창(window) 내 시도 횟수 제한
        self.reconnect_history.append(now)
        while self.reconnect_history and now - self.reconnect_history[0] > self.reconnect_window_seconds:
            self.reconnect_history.popleft()
        
        # 지수 백오프 계산
        base_delay = self.reconnect_base_delay * (2 ** min(self.reconnect_attempt, 10))
        base_delay = min(base_delay, self.reconnect_max_delay)
        jitter = base_delay * random.uniform(0, self.reconnect_jitter_ratio)
        delay = base_delay + jitter
        
        # 폭주 방지 쿨다운
        if len(self.reconnect_history) > self.reconnect_window_max_attempts:
            delay = max(delay, self.reconnect_cooldown_seconds)
            self.cooldown_active_until = max(self.cooldown_active_until, now + delay)
            if now - self.cooldown_last_log_ts >= self.cooldown_log_interval:
                remaining = max(0, self.cooldown_active_until - now)
                logger.warning(
                    f"[{self.name}] 재연결 시도 과다: {len(self.reconnect_history)}회/"
                    f"{self.reconnect_window_seconds}초 → 쿨다운 적용, 남은 시간 {remaining:.0f}s"
                )
                self.cooldown_last_log_ts = now
        
        return delay
    
    def _cleanup_previous_connection(self):
        """
        [개선-재연결] 이전 연결 정리
        이유: 소켓/스레드 중복 방지
        """
        self._close_ws()
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)
            if self.ws_thread.is_alive():
                logger.warning(
                    f"[{self.name}] 이전 ws_thread 종료 지연 "
                    f"(alive={self.ws_thread.is_alive()}, running={self.running}, "
                    f"shutdown={self.shutdown_event.is_set()})"
                )
                return False
        return True
    
    def run(self):
        """
        [개선8] run 로직 개선
        이유: 무한 루프 대신 이벤트 기반 종료
        """
        # [개선11] 종료 이벤트 대기 (블로킹하지 않음)
        # 이유: Ctrl+C 시 즉시 반응
        logger.info(f"[{self.name}] 수집기 시작됨. 종료하려면 Ctrl+C를 누르세요.")
        self._start_stats_timer()
        
        try:
            while self.running and not self.shutdown_event.is_set():
                self.expected_reconnect_event.clear()
                self.ws_close_event.clear()
                self.ws_open_event.clear()
                
                # 이전 연결 정리 (완료 전에는 새 연결 시작 금지)
                if not self._cleanup_previous_connection():
                    if self.shutdown_event.wait(timeout=1.0):
                        break
                    continue
                
                # [개선9] WebSocket 핸들러 추가
                self.ws = websocket.WebSocketApp(
                    UPBIT_WS_URL,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )
                
                # [개선10] 별도 스레드에서 WebSocket 실행
                # 이유: run_forever가 블로킹되므로 별도 스레드 필요
                self.ws_thread = threading.Thread(
                    target=self.ws.run_forever,
                    kwargs={'ping_interval': 60, 'ping_timeout': 30},
                    daemon=True
                )
                self.ws_thread.start()
                
                # 연결 종료 또는 종료 신호 대기
                while self.running and not self.shutdown_event.is_set():
                    if self.ws_close_event.wait(timeout=1.0):
                        break
                
                if self.shutdown_event.is_set() or not self.running:
                    break
                
                # 재연결 전 데이터 flush
                try:
                    self.aggregator.flush(0)
                except Exception as e:
                    logger.error(f"[{self.name}] 재연결 전 flush 에러: {e}")
                
                # 재연결 결정
                self.reconnect_attempt += 1
                delay = self._compute_reconnect_delay()
                if self.expected_reconnect_event.is_set():
                    # 의도적 재연결은 즉시 재연결 우선
                    delay = min(delay, 1.0)
                # 다음 연결을 위해 상태 초기화
                self.expected_reconnect_event.clear()
                logger.warning(
                    f"[{self.name}] 재연결 시도 #{self.reconnect_attempt} 예정 "
                    f"(delay={delay:.2f}s, last_close={self.last_close_info})"
                )
                
                # 대기 중 종료 요청 확인
                if self.shutdown_event.wait(timeout=delay):
                    break
        except KeyboardInterrupt:
            logger.info(f"[{self.name}] KeyboardInterrupt 수신")
        finally:
            self._stop_stats_timer()
            logger.info(f"[{self.name}] 메인 루프 종료")
    
    def stop(self):
        """
        [개선12] 종료 로직 대폭 개선
        이유: 5분 이상 기다려도 종료 안되는 문제 해결
        """
        logger.info(f"[{self.name}] 종료 시작...")
        if self.stop_called:
            return
        self.stop_called = True
        self.running = False
        self.shutdown_event.set()
        
        # [개선13] flush 타이머 즉시 중지
        self._stop_flush_timer()
        self._stop_periodic_reconnect_timer()
        self._stop_stats_timer()
        
        # [개선14] 마지막 flush 실행
        # 이유: 남은 데이터 저장
        try:
            logger.info(f"[{self.name}] 마지막 flush 실행 중...")
            self.aggregator.flush(0)  # 모든 데이터 flush
            self.aggregator.shutdown()
        except Exception as e:
            logger.error(f"[{self.name}] 종료 중 에러: {e}")
        
        # [개선15] WebSocket 강제 종료
        # 이유: run_forever가 멈추지 않는 문제 해결
        logger.info(f"[{self.name}] WebSocket 연결 종료 중...")
        self._close_ws()
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)
            if self.ws_thread.is_alive():
                logger.warning(
                    f"[{self.name}] ws_thread join timeout "
                    f"(alive={self.ws_thread.is_alive()}, running={self.running}, "
                    f"shutdown={self.shutdown_event.is_set()})"
                )
        
        # [개선17] Writer 종료
        try:
            logger.info(f"[{self.name}] Writer 종료 중...")
            self.writer.close()
        except Exception as e:
            logger.error(f"[{self.name}] Writer 종료 에러: {e}")
        
        logger.info(f"[{self.name}] 종료 완료")


class CollectorManager:
    """
    여러 Collector를 동시에 관리
    """
    
    def __init__(self, collectors: list):
        self.collectors = collectors
        self.threads = []
        self.stop_called = False
    
    def start(self):
        for collector in self.collectors:
            thread = threading.Thread(target=collector.run, daemon=True)
            thread.start()
            self.threads.append(thread)
    
    def stop(self):
        if self.stop_called:
            return
        self.stop_called = True
        for collector in self.collectors:
            collector.stop()
        for thread in self.threads:
            thread.join(timeout=5.0)
    
    def any_thread_stopped(self) -> bool:
        return any(thread and not thread.is_alive() for thread in self.threads)
    
    def get_health(self) -> dict:
        return {collector.name: collector.get_health() for collector in self.collectors}
    
    def get_stats(self) -> dict:
        return {collector.name: collector.get_stats() for collector in self.collectors}


class HealthRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    간단한 헬스체크/통계 HTTP 핸들러
    """
    manager = None
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/health":
            payload = self.manager.get_health()
            self._send_json(payload, 200)
            return
        if path == "/stats":
            payload = self.manager.get_stats()
            self._send_json(payload, 200)
            return
        self._send_json({"error": "not found"}, 404)
    
    def _send_json(self, payload: dict, status: int):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def log_message(self, format, *args):
        # 기본 stdout 로그는 억제
        return


def _start_http_server(port: int, manager: CollectorManager):
    handler = HealthRequestHandler
    handler.manager = manager
    server = http.server.ThreadingHTTPServer(("", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"HTTP 서버 시작: port={port}")
    return server


def _stop_http_server(server):
    if server:
        server.shutdown()
        server.server_close()
        logger.info("HTTP 서버 종료")


def _parse_pairs(raw_pairs):
    if raw_pairs is None:
        return None
    if isinstance(raw_pairs, list):
        return raw_pairs
    return [p.strip() for p in str(raw_pairs).split(",") if p.strip()]


def _parse_timeframes(raw_timeframes):
    if raw_timeframes is None:
        return None
    if isinstance(raw_timeframes, list):
        values = raw_timeframes
    else:
        values = [v.strip() for v in str(raw_timeframes).split(",") if v.strip()]
    result = []
    for value in values:
        try:
            result.append(int(value))
        except Exception:
            logger.warning(f"잘못된 timeframe_ms 무시: {value}")
    return result if result else None


def _load_config(config_path: Path) -> dict:
    if not config_path or not config_path.exists():
        return {}
    try:
        import yaml  # optional
    except Exception:
        logger.warning("config_upbit_exchange.yml 감지됨 (yaml 모듈 없음) → 설정 무시")
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}")
    return {}


def _resolve_short_db_path(base_dir: Path) -> Path:
    short_path = base_dir / "ohlcv_short.sqlite"
    legacy_path = base_dir / "ohlcv.sqlite"
    if short_path.exists():
        return short_path
    if legacy_path.exists():
        logger.warning("legacy DB 발견 → ohlcv.sqlite 사용 (추후 ohlcv_short.sqlite 전환 권장)")
        return legacy_path
    return short_path


def _build_collector_configs(
    pairs: list,
    phase2_enabled: bool,
    derived_enabled: bool,
    short_timeframes: list,
    mid_timeframes: list,
    long_timeframes: list,
    derived_timeframes: list,
) -> list:
    base_dir = Path(__file__).resolve().parent
    short_db = _resolve_short_db_path(base_dir)
    
    if derived_enabled and 1000 not in short_timeframes:
        logger.warning("합성 봉 비활성화됨: 1초봉(1000ms) 미포함")
        derived_enabled = False
    configs = [
        CollectorConfig(
            name="short",
            pairs=pairs,
            timeframes_ms=short_timeframes,
            tick_sizes=SHORT_TICK_SIZES,
            db_path=short_db,
            derived_timeframes_ms=derived_timeframes if derived_enabled else None,
        )
    ]
    
    if phase2_enabled:
        if mid_timeframes:
            configs.append(
                CollectorConfig(
                    name="mid",
                    pairs=pairs,
                    timeframes_ms=mid_timeframes,
                    tick_sizes=[],
                    db_path=base_dir / "ohlcv_10s_1m.sqlite",
                    derived_timeframes_ms=None,
                )
            )
        if long_timeframes:
            configs.append(
                CollectorConfig(
                    name="long",
                    pairs=pairs,
                    timeframes_ms=long_timeframes,
                    tick_sizes=[],
                    db_path=base_dir / "ohlcv_10m.sqlite",
                    derived_timeframes_ms=None,
                )
            )
    return configs


def main():
    """
    [개선18] 메인 함수 개선
    이유: 종료 처리를 더 명확하게
    """
    parser = argparse.ArgumentParser(description="Upbit 실시간 OHLCV 수집기")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--pairs", default=None, help="예: KRW-BTC,KRW-ETH,KRW-XRP")
    parser.add_argument("--short-timeframes-ms", default=None, help="예: 500,1000")
    parser.add_argument("--mid-timeframes-ms", default=None, help="예: 10000,60000")
    parser.add_argument("--long-timeframes-ms", default=None, help="예: 600000")
    parser.add_argument("--derived-timeframes-ms", default=None, help="예: 5000,10000,33000,57000,60000")
    parser.add_argument("--http-port", type=int, default=None)
    parser.add_argument("--disable-http", action="store_true")
    parser.add_argument("--disable-phase2", action="store_true")
    parser.add_argument("--disable-derived", action="store_true")
    parser.add_argument("--stats-interval", type=float, default=None)
    parser.add_argument("--max-late-ms", type=int, default=None)
    args = parser.parse_args()
    
    config = _load_config(Path(args.config))
    pairs = _parse_pairs(args.pairs) or _parse_pairs(config.get("pairs")) or DEFAULT_PAIRS
    stats_interval = args.stats_interval if args.stats_interval is not None else config.get("stats_interval", DEFAULT_STATS_INTERVAL)
    max_late_ms = args.max_late_ms if args.max_late_ms is not None else config.get("max_late_ms", DEFAULT_MAX_LATE_MS)
    
    short_timeframes = _parse_timeframes(args.short_timeframes_ms) or _parse_timeframes(config.get("short_timeframes_ms")) or SHORT_TIMEFRAMES_MS
    mid_timeframes = _parse_timeframes(args.mid_timeframes_ms) or _parse_timeframes(config.get("mid_timeframes_ms")) or MID_TIMEFRAMES_MS
    long_timeframes = _parse_timeframes(args.long_timeframes_ms) or _parse_timeframes(config.get("long_timeframes_ms")) or LONG_TIMEFRAMES_MS
    derived_timeframes = _parse_timeframes(args.derived_timeframes_ms) or _parse_timeframes(config.get("derived_timeframes_ms")) or DERIVED_TIMEFRAMES_MS
    
    phase2_enabled = config.get("phase2_enabled", True)
    if args.disable_phase2:
        phase2_enabled = False
    
    derived_enabled = config.get("derived_timeframes_enabled", True)
    if args.disable_derived:
        derived_enabled = False
    
    http_enabled = config.get("http_enabled", True)
    if args.disable_http:
        http_enabled = False
    http_port = args.http_port if args.http_port is not None else config.get("http_port", DEFAULT_HTTP_PORT)
    
    configs = _build_collector_configs(
        pairs,
        phase2_enabled,
        derived_enabled,
        short_timeframes,
        mid_timeframes,
        long_timeframes,
        derived_timeframes,
    )
    collectors = [
        UpbitCollector(cfg, max_late_ms=max_late_ms, stats_interval=stats_interval)
        for cfg in configs
    ]
    manager = CollectorManager(collectors)
    http_server = None
    
    # [개선19] 시그널 핸들러 개선
    # 이유: 즉시 종료되도록
    def shutdown(sig, frame):
        logger.info(f"\n시그널 수신: {sig}")
        manager.stop()
        _stop_http_server(http_server)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    try:
        manager.start()
        if http_enabled:
            http_server = _start_http_server(http_port, manager)
        
        while True:
            time.sleep(1.0)
            if manager.any_thread_stopped():
                logger.warning("Collector 스레드 중단 감지 → 종료 처리")
                break
    except Exception as e:
        logger.error(f"예외 발생: {e}", exc_info=True)
    finally:
        manager.stop()
        _stop_http_server(http_server)


if __name__ == "__main__":
    main()