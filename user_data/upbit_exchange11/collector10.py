# collector.py
import json
import time
import signal
import websocket
import logging
import threading
from ohlcv_writer import OHLCVWriter
from multi_aggregator import MultiAggregator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("collector")

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"

# [수정1] XRP 반드시 포함
PAIRS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]

MAX_LATE_MS = 2000

# [추가1] pair 누락 감지 기준 (초)
PAIR_MISSING_TIMEOUT = 10


class UpbitCollector:
    def __init__(self):
        self.writer = OHLCVWriter()
        self.aggregator = MultiAggregator(self.writer)
        self.running = True
        self.ws = None
        
        # [개선1] flush 타이머 추가
        self.flush_timer = None
        self.flush_interval = 1.0
        
        # [개선2] 종료 이벤트 추가
        self.shutdown_event = threading.Event()

        # [추가2] 각 pair의 마지막 tick 수신 시간 기록
        # 이유: XRP만 조용히 빠지는 상황을 감지하기 위함
        self.last_seen = {pair: 0 for pair in PAIRS}
    
    def on_open(self, ws):
        logger.info("WebSocket connected")
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
    
    def on_message(self, ws, message):
        try:
            data = json.loads(message)

            pair = data["code"]
            price = data["trade_price"]
            volume = data["trade_volume"]
            ts_ms = data["trade_timestamp"]

            # [추가3] 해당 pair의 마지막 수신 시간 갱신
            # 이유: 이 값이 갱신되지 않으면 "누락"으로 판단
            if pair in self.last_seen:
                self.last_seen[pair] = time.time()

            self.aggregator.update(pair, price, volume, ts_ms)

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"메시지 파싱 에러: {e}")
        except Exception as e:
            logger.error(f"메시지 처리 에러: {e}")
    
    def on_error(self, ws, error):
        logger.error(f"WebSocket 에러: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        logger.warning(f"WebSocket 연결 종료: code={close_status_code}")
        self._stop_flush_timer()
    
    def _periodic_flush(self):
        """
        [개선7] 주기적 flush 함수
        """
        if not self.running:
            return
        
        try:
            self.aggregator.flush(MAX_LATE_MS)
        except Exception as e:
            logger.error(f"Flush 에러: {e}")

        # [추가4] pair 누락 감지 로직
        # 이유: XRP만 안 들어오는 "조용한 장애"를 절대 허용하지 않기 위함
        now = time.time()
        missing_pairs = [
            pair for pair, last_ts in self.last_seen.items()
            if last_ts > 0 and (now - last_ts) > PAIR_MISSING_TIMEOUT
        ]

        if missing_pairs:
            logger.error(
                f"❌ WebSocket tick 누락 감지: {missing_pairs} → 재연결 수행"
            )
            # WebSocket 강제 종료 → run_forever 탈출 → 재연결
            if self.ws:
                self.ws.close()

        # 다음 flush 예약
        if self.running:
            self.flush_timer = threading.Timer(
                self.flush_interval,
                self._periodic_flush
            )
            self.flush_timer.daemon = True
            self.flush_timer.start()
    
    def _start_flush_timer(self):
        if self.flush_timer is None or not self.flush_timer.is_alive():
            self._periodic_flush()
    
    def _stop_flush_timer(self):
        if self.flush_timer and self.flush_timer.is_alive():
            self.flush_timer.cancel()
    
    def run(self):
        self.ws = websocket.WebSocketApp(
            UPBIT_WS_URL,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        
        ws_thread = threading.Thread(
            target=self.ws.run_forever,
            kwargs={'ping_interval': 60, 'ping_timeout': 10},
            daemon=True
        )
        ws_thread.start()
        
        logger.info("수집기 시작됨. 종료하려면 Ctrl+C를 누르세요.")
        
        try:
            while self.running and not self.shutdown_event.is_set():
                self.shutdown_event.wait(timeout=1.0)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt 수신")
        
        logger.info("메인 루프 종료")
    
    def stop(self):
        logger.info("종료 시작...")
        self.running = False
        self.shutdown_event.set()
        
        self._stop_flush_timer()
        
        try:
            logger.info("마지막 flush 실행 중...")
            self.aggregator.flush(0)
            self.aggregator.shutdown()
        except Exception as e:
            logger.error(f"종료 중 에러: {e}")
        
        if self.ws:
            try:
                logger.info("WebSocket 연결 종료 중...")
                self.ws.close()
                if hasattr(self.ws, 'keep_running'):
                    self.ws.keep_running = False
            except Exception as e:
                logger.error(f"WebSocket 종료 에러: {e}")
        
        try:
            logger.info("Writer 종료 중...")
            self.writer.close()
        except Exception as e:
            logger.error(f"Writer 종료 에러: {e}")
        
        logger.info("종료 완료")


def main():
    collector = UpbitCollector()
    
    def shutdown(sig, frame):
        logger.info(f"\n시그널 수신: {sig}")
        collector.stop()
        import sys
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    try:
        collector.run()
    except Exception as e:
        logger.error(f"예외 발생: {e}", exc_info=True)
    finally:
        if collector.running:
            collector.stop()


if __name__ == "__main__":
    main()
