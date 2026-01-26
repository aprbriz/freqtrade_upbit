# collector.py
import json
import time
import signal
import websocket
import logging
import threading
from ohlcv_writer import OHLCVWriter
from multi_aggregator import MultiAggregator




# watchdog 관련 logging 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("collector.log"),
        logging.StreamHandler()
    ]
)




logger = logging.getLogger("collector")

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
PAIRS = ["KRW-BTC", "KRW-ETH"]
MAX_LATE_MS = 2000


class UpbitCollector:
    def __init__(self):
        self.writer = OHLCVWriter()
        self.aggregator = MultiAggregator(self.writer)
        self.running = True
        self.ws = None
        
        # [개선1] flush 타이머 추가
        # 이유: 주기적으로 flush하여 데이터 손실 방지
        self.flush_timer = None
        self.flush_interval = 1.0  # 1초마다 flush
        
        # [개선2] 종료 이벤트 추가
        # 이유: 종료 시그널을 명확하게 전달
        self.shutdown_event = threading.Event()
    
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
        # [개선4] 메시지 파싱 예외 처리
        # 이유: 잘못된 메시지로 인한 크래시 방지
        try:
            data = json.loads(message)
            pair = data["code"]
            price = data["trade_price"]
            volume = data["trade_volume"]
            ts_ms = data["trade_timestamp"]
            
            self.aggregator.update(pair, price, volume, ts_ms)
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"메시지 파싱 에러: {e}")
        except Exception as e:
            logger.error(f"메시지 처리 에러: {e}")
    
    def on_error(self, ws, error):
        # [개선5] 에러 핸들러 추가
        # 이유: 에러 상황 모니터링
        logger.error(f"WebSocket 에러: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        # [개선6] 종료 핸들러 추가
        # 이유: 연결 종료 시 정리 작업
        logger.warning(f"WebSocket 연결 종료: code={close_status_code}")
        self._stop_flush_timer()
    
    def _periodic_flush(self):
        """
        [개선7] 주기적 flush 함수
        이유: 체결이 없어도 주기적으로 오래된 캔들 저장
        """
        if not self.running:
            return
        
        try:
            self.aggregator.flush(MAX_LATE_MS)
        except Exception as e:
            logger.error(f"Flush 에러: {e}")
        
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
    
    def run(self):
        """
        [개선8] run 로직 개선
        이유: 무한 루프 대신 이벤트 기반 종료
        """
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
        ws_thread = threading.Thread(
            target=self.ws.run_forever,
            kwargs={'ping_interval': 60, 'ping_timeout': 10},
            daemon=True
        )
        ws_thread.start()
        
        # [개선11] 종료 이벤트 대기 (블로킹하지 않음)
        # 이유: Ctrl+C 시 즉시 반응
        logger.info("수집기 시작됨. 종료하려면 Ctrl+C를 누르세요.")
        
        try:
            # 종료 시그널을 기다림 (타임아웃으로 주기적 체크)
            while self.running and not self.shutdown_event.is_set():
                self.shutdown_event.wait(timeout=1.0)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt 수신")
        
        logger.info("메인 루프 종료")
    
    def stop(self):
        """
        [개선12] 종료 로직 대폭 개선
        이유: 5분 이상 기다려도 종료 안되는 문제 해결
        """
        logger.info("종료 시작...")
        self.running = False
        self.shutdown_event.set()
        
        # [개선13] flush 타이머 즉시 중지
        self._stop_flush_timer()
        
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
        if self.ws:
            try:
                logger.info("WebSocket 연결 종료 중...")
                self.ws.close()
                # [개선16] keep_running을 False로 설정하여 강제 종료
                # 이유: websocket-client 라이브러리의 run_forever 탈출
                if hasattr(self.ws, 'keep_running'):
                    self.ws.keep_running = False
            except Exception as e:
                logger.error(f"WebSocket 종료 에러: {e}")
        
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
        collector.stop()
        # [개선20] 시그널 핸들러에서 exit 호출
        # 이유: 강제 종료 보장 (최대 2초 대기)
        import sys
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    try:
        collector.run()
    except Exception as e:
        logger.error(f"예외 발생: {e}", exc_info=True)
    finally:
        # [개선21] finally 블록에서도 종료 확인
        if collector.running:
            collector.stop()


if __name__ == "__main__":
    main()