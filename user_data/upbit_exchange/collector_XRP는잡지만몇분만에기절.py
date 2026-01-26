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

# XRP 반드시 포함
PAIRS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]

MAX_LATE_MS = 2000
PAIR_MISSING_TIMEOUT = 10   # 부분 pair 누락 감지 기준 (초)

WS_DEAD_SEC = 10            # 전체 WS 무음 판단 기준
WS_RESTART_COOLDOWN = 5     # 재시작 쿨다운


class WSWatchdog(threading.Thread):
    def __init__(self, get_last_msg_ts, restart_ws):
        super().__init__(daemon=True)
        self.get_last_msg_ts = get_last_msg_ts
        self.restart_ws = restart_ws
        self._last_restart = 0
        self._stop = False

    def run(self):
        logger.warning("[watchdog] WS watchdog started")
        while not self._stop:
            now = time.time()
            last_msg = self.get_last_msg_ts()

            if last_msg:
                silent = now - last_msg
                if silent > WS_DEAD_SEC:
                    if now - self._last_restart > WS_RESTART_COOLDOWN:
                        logger.error(
                            f"[watchdog] WS silent {silent:.1f}s → HARD RESTART"
                        )
                        try:
                            self.restart_ws()
                        except Exception as e:
                            logger.exception(f"[watchdog] restart failed: {e}")
                        self._last_restart = now

            time.sleep(1)

    def stop(self):
        self._stop = True


class UpbitCollector:
    def __init__(self):
        self.writer = OHLCVWriter()
        self.aggregator = MultiAggregator(self.writer)
        self.running = True

        self.ws = None
        self.ws_thread = None
        self.watchdog = None

        self.flush_timer = None
        self.flush_interval = 1.0
        self.shutdown_event = threading.Event()

        # pair별 마지막 tick 수신 시간
        self.last_seen = {pair: 0 for pair in PAIRS}

        # 전체 WS 기준 마지막 메시지 수신 시간
        self.last_ws_msg_ts = 0

        self._ws_lock = threading.Lock()

    # ---------- WebSocket callbacks ----------

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
        self._start_flush_timer()

    def on_message(self, ws, message):
        self.last_ws_msg_ts = time.time()

        try:
            data = json.loads(message)

            pair = data["code"]
            price = data["trade_price"]
            volume = data["trade_volume"]
            ts_ms = data["trade_timestamp"]

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

    # ---------- Flush & pair-missing logic ----------

    def _periodic_flush(self):
        if not self.running:
            return

        try:
            self.aggregator.flush(MAX_LATE_MS)
        except Exception as e:
            logger.error(f"Flush 에러: {e}")

        now = time.time()

        active_pairs = [
            pair for pair, last_ts in self.last_seen.items()
            if last_ts > 0 and (now - last_ts) <= PAIR_MISSING_TIMEOUT
        ]

        missing_pairs = [
            pair for pair, last_ts in self.last_seen.items()
            if last_ts > 0 and (now - last_ts) > PAIR_MISSING_TIMEOUT
        ]

        # 부분 pair만 누락 → WS 재연결 트리거
        if missing_pairs and active_pairs:
            logger.error(
                f"❌ WebSocket tick 누락 감지 (부분 장애): {missing_pairs} → 재연결"
            )
            self.restart_ws()

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

    # ---------- WS lifecycle ----------

    def start_ws(self):
        with self._ws_lock:
            logger.info("Starting WebSocket")

            self.ws = websocket.WebSocketApp(
                UPBIT_WS_URL,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
            )

            self.ws_thread = threading.Thread(
                target=self.ws.run_forever,
                kwargs={'ping_interval': 60, 'ping_timeout': 10},
                daemon=True
            )
            self.ws_thread.start()

            # watchdog는 최초 1회만 생성
            if not self.watchdog:
                self.watchdog = WSWatchdog(
                    get_last_msg_ts=lambda: self.last_ws_msg_ts,
                    restart_ws=self.restart_ws,
                )
                self.watchdog.start()

    def restart_ws(self):
        with self._ws_lock:
            logger.error("[WS] HARD restart initiated")

            try:
                if self.ws:
                    self.ws.close()
            except Exception:
                pass

            self.ws = None
            time.sleep(1)

            # last_seen 초기화 (stale 방지)
            for k in self.last_seen:
                self.last_seen[k] = 0

            self.start_ws()

    # ---------- main loop ----------

    def run(self):
        self.start_ws()
        logger.info("수집기 시작됨. 종료하려면 Ctrl+C")

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

        if self.watchdog:
            self.watchdog.stop()

        if self.ws:
            try:
                logger.info("WebSocket 종료 중...")
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
