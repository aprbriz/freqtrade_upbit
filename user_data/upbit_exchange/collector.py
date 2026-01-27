# collector.py
import os
import json
import time
import signal
import websocket
import logging
import threading
import random
from collections import deque
from ohlcv_writer import OHLCVWriter
from multi_aggregator import MultiAggregator




# watchdog 관련 logging 설정
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
LOG_FILE_PATH = os.path.join(LOG_DIR, "collector.log")
LOG_FALLBACK = False
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    LOG_FALLBACK = True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH if not LOG_FALLBACK else "collector.log"),
        logging.StreamHandler()
    ]
)




logger = logging.getLogger("collector")
if LOG_FALLBACK:
    logger.warning("logs/ 디렉토리 생성 실패 → collector.log로 폴백")

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
PAIRS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
MAX_LATE_MS = 2000


class UpbitCollector:
    def __init__(self):
        self.writer = OHLCVWriter()
        self.aggregator = MultiAggregator(self.writer)
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
        self.flush_lock = threading.Lock()
        self.flush_timer = None
        self.flush_interval = 1.0  # 1초마다 flush
        self.flush_enabled = False
        self.flush_idle_event = threading.Event()
        self.flush_idle_event.set()
        self.flush_wait_timeout = 5.0
        
        # [개선2] 종료 이벤트 추가
        # 이유: 종료 시그널을 명확하게 전달
        self.shutdown_event = threading.Event()
        
        # 메시지 파싱 오류 로그 제한
        self.message_parse_error_last_log_ts = 0.0
        self.message_parse_error_log_interval = 60.0
    
    def on_open(self, ws):
        logger.info("WebSocket connected")
        self.ws_open_event.set()
        self.ws_close_event.clear()
        # [개선-재연결] 성공 시 카운터 초기화
        self.reconnect_attempt = 0
        self.reconnect_history.clear()
        ws.send(json.dumps([
            {"ticket": "upbit-collector"},
            {
                "type": "trade",
                "codes": PAIRS,
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
            
            self.aggregator.update(pair, price, volume, ts_ms)
            
        except (json.JSONDecodeError, KeyError) as e:
            now = time.time()
            if now - self.message_parse_error_last_log_ts >= self.message_parse_error_log_interval:
                logger.error(f"메시지 파싱 에러: {e}")
                self.message_parse_error_last_log_ts = now
        except Exception as e:
            logger.error(f"메시지 처리 에러: {e}")
    
    def on_error(self, ws, error):
        # [개선5] 에러 핸들러 추가
        # 이유: 에러 상황 모니터링
        logger.error(f"WebSocket 에러: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        # [개선6] 종료 핸들러 추가
        # 이유: 연결 종료 시 정리 작업
        close_info = self._parse_close_info(close_status_code, close_msg)
        self.last_close_info = close_info
        try:
            if self.expected_reconnect_event.is_set():
                logger.warning(f"WebSocket 연결 종료(의도적): {close_info}")
            else:
                logger.warning(f"WebSocket 연결 종료: {close_info}")
            self._stop_flush_timer()
            self._stop_periodic_reconnect_timer()
        except Exception as e:
            logger.error(f"on_close 정리 중 에러: {e}")
        finally:
            self.ws_close_event.set()
    
    def _periodic_flush(self):
        """
        [개선7] 주기적 flush 함수
        이유: 체결이 없어도 주기적으로 오래된 캔들 저장
        """
        with self.flush_lock:
            if not self.flush_enabled or not self.running or self.shutdown_event.is_set():
                self.flush_idle_event.set()
                return
            self.flush_idle_event.clear()
        
        try:
            self.aggregator.flush(MAX_LATE_MS)
        except Exception as e:
            logger.error(f"Flush 에러: {e}")
        finally:
            self.flush_idle_event.set()
        
        # 다음 flush 예약
        with self.flush_lock:
            if self.flush_enabled and self.running and not self.shutdown_event.is_set():
                self._schedule_flush_locked()
    
    def _start_flush_timer(self):
        """flush 타이머 시작"""
        with self.flush_lock:
            if self.flush_enabled:
                return
            self.flush_enabled = True
        # 첫 flush는 즉시 수행
        self._periodic_flush()
    
    def _stop_flush_timer(self):
        """flush 타이머 중지"""
        with self.flush_lock:
            self.flush_enabled = False
            if self.flush_timer:
                self.flush_timer.cancel()
                self.flush_timer = None

    def _schedule_flush_locked(self):
        """flush 타이머 예약 (flush_lock 필요)"""
        if not self.flush_enabled or not self.running or self.shutdown_event.is_set():
            return
        self.flush_timer = threading.Timer(self.flush_interval, self._periodic_flush)
        self.flush_timer.daemon = True
        self.flush_timer.start()
    
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
            logger.info(f"주기적 재연결 예약됨: {self.periodic_reconnect_seconds}초 후")
    
    def _stop_periodic_reconnect_timer(self):
        """주기적 재연결 타이머 중지"""
        with self.timer_lock:
            if self.periodic_reconnect_timer:
                self.periodic_reconnect_timer.cancel()

    def _wait_for_flush_idle(self):
        """
        flush 콜백 종료 대기 (timeout 포함)
        """
        if not self.flush_idle_event.wait(timeout=self.flush_wait_timeout):
            logger.warning(f"flush 종료 대기 타임아웃: {self.flush_wait_timeout}s")
    
    def _request_periodic_reconnect(self):
        """
        [개선-재연결] 주기적 재연결 요청
        이유: 장기 연결 종료 회피 (DEC-009)
        """
        if not self.running or self.shutdown_event.is_set():
            return
        logger.warning("주기적 재연결 시작 (9시간 주기)")
        self.expected_reconnect_event.set()
        # 재연결 전 데이터 flush
        try:
            self.aggregator.flush(0)
        except Exception as e:
            logger.error(f"주기적 재연결 전 flush 에러: {e}")
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
                logger.error(f"WebSocket 종료 에러: {e}")
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
                    f"재연결 시도 과다: {len(self.reconnect_history)}회/{self.reconnect_window_seconds}초 "
                    f"→ 쿨다운 적용, 남은 시간 {remaining:.0f}s"
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
                    "이전 ws_thread 종료 지연 "
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
        logger.info("수집기 시작됨. 종료하려면 Ctrl+C를 누르세요.")
        
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
                    logger.error(f"재연결 전 flush 에러: {e}")
                
                # 재연결 결정
                self.reconnect_attempt += 1
                delay = self._compute_reconnect_delay()
                if self.expected_reconnect_event.is_set():
                    # 의도적 재연결은 즉시 재연결 우선
                    delay = min(delay, 1.0)
                # 다음 연결을 위해 상태 초기화
                self.expected_reconnect_event.clear()
                logger.warning(
                    f"재연결 시도 #{self.reconnect_attempt} 예정 "
                    f"(delay={delay:.2f}s, last_close={self.last_close_info})"
                )
                
                # 대기 중 종료 요청 확인
                if self.shutdown_event.wait(timeout=delay):
                    break
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt 수신")
        finally:
            logger.info("메인 루프 종료")
    
    def stop(self):
        """
        [개선12] 종료 로직 대폭 개선
        이유: 5분 이상 기다려도 종료 안되는 문제 해결
        """
        logger.info("종료 시작...")
        if self.stop_called:
            return
        self.stop_called = True
        self.running = False
        self.shutdown_event.set()
        
        # [개선13] flush 타이머 즉시 중지
        self._stop_flush_timer()
        self._stop_periodic_reconnect_timer()
        self._wait_for_flush_idle()
        
        # [개선14] 마지막 flush 실행
        # 이유: 남은 데이터 저장
        try:
            logger.info("마지막 flush 실행 중...")
            self.aggregator.flush(0)  # 모든 데이터 flush
            self.aggregator.shutdown()
        except Exception as e:
            logger.error(f"종료 중 에러: {e}")
        
        # [개선15] WebSocket 강제 종료
        # 이유: run_forever가 멈추지 않는 문제 해결
        logger.info("WebSocket 연결 종료 중...")
        self._close_ws()
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)
            if self.ws_thread.is_alive():
                logger.warning(
                    "ws_thread join timeout "
                    f"(alive={self.ws_thread.is_alive()}, running={self.running}, "
                    f"shutdown={self.shutdown_event.is_set()})"
                )
        
        # [개선17] Writer 종료
        try:
            logger.info("Writer 종료 중...")
            self.writer.close()
        except Exception as e:
            logger.error(f"Writer 종료 에러: {e}")
        
        logger.info("종료 완료")


def main():
    """
    [개선18] 메인 함수 개선
    이유: 종료 처리를 더 명확하게
    """
    collector = UpbitCollector()
    
    # [개선19] 시그널 핸들러 개선
    # 이유: 즉시 종료되도록
    def shutdown(sig, frame):
        logger.info(f"\n시그널 수신: {sig}")
        collector.running = False
        collector.shutdown_event.set()
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    try:
        collector.run()
    except Exception as e:
        logger.error(f"예외 발생: {e}", exc_info=True)
    finally:
        # [개선21] finally 블록에서도 종료 확인
        if not collector.stop_called:
            collector.stop()


if __name__ == "__main__":
    main()