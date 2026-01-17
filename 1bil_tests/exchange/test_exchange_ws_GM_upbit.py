import asyncio
import logging
import csv
import os
import signal
from datetime import datetime
# [변경] CCXT Pro의 업비트 웹소켓 모듈로 변경
from ccxt.pro import upbit as ccxt_upbit 

# Freqtrade의 캔들 타입 Enum (기존 유지)
class CandleType:
    SPOT = "spot"

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UpbitWS-Collector")

class ExchangeWS:
    """ Freqtrade 구조를 참고하여 업비트 웹소켓 데이터 수집 """
    def __init__(self, symbols: list):
        self.symbols = symbols
        self.timeframe = '1m'
        self._background_tasks: set[asyncio.Task] = set()
        self._running = True
        self._ccxt_object = None
        self.klines_last_refresh = {}

    def _init_ccxt(self):
        """ [변경] CCXT 객체를 업비트 설정으로 초기화 """
        return ccxt_upbit({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot', # 업비트는 현물(spot) 거래소임
                'ws': {'heartbeat': 30000}
            }
        })

    async def _pair_worker(self, symbol: str):
        """ 각 심볼별 웹소켓 연결 및 데이터 처리 루프 """
        # [변경] 파일명 생성 시 슬래시(/)와 콜론(:) 등을 언더바(_)로 안전하게 치환
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        file_path = os.path.join(os.getcwd(), f"{safe_symbol}_ohlcv.csv")
        
        if not os.path.exists(file_path):
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['data_time', 'save_time', 'open', 'high', 'low', 'close', 'volume'])

        last_ts = None
        while self._running:
            try:
                # [변경] 업비트 웹소켓을 통해 OHLCV 데이터를 실시간으로 가져옴
                ohlcv = await asyncio.wait_for(
                    self._ccxt_object.watch_ohlcv(symbol, self.timeframe),
                    timeout=60.0 # 업비트 응답 대기 시간 설정
                )
                
                if ohlcv and len(ohlcv) > 0:
                    candle = ohlcv[-1]
                    ts, o, h, l, c, v = candle

                    # 중복 데이터 저장 방지
                    if last_ts is not None and ts <= last_ts:
                        continue
                    
                    data_time = datetime.fromtimestamp(ts / 1000).strftime('%Y/%m/%d %H:%M:%S')
                    save_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
                    
                    row = [data_time, save_time, o, h, l, c, v]
                    with open(file_path, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(row)
                    
                    last_ts = ts
                    self.klines_last_refresh[(symbol, self.timeframe, CandleType.SPOT)] = ts

            except asyncio.TimeoutError:
                logger.warning(f"[{symbol}] 업비트 타임아웃 발생 - 재연결 시도")
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{symbol}] 에러 발생: {e}")
                await asyncio.sleep(5)

    async def run(self):
        """메인 실행 함수"""
        self._ccxt_object = self._init_ccxt()
        for symbol in self.symbols:
            task = asyncio.create_task(self._pair_worker(symbol))
            self._background_tasks.add(task)
        
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

    async def cleanup(self):
        """ 자원 해제 """
        self._running = False
        for task in self._background_tasks:
            task.cancel()
        if self._ccxt_object:
            await self._ccxt_object.close()
        logger.info("업비트 세션 종료.")

async def main():
    # [변경] 업비트 시장에 맞는 심볼로 변경 (BTC/KRW 형태)
    symbols = ['BTC/KRW', 'ETH/KRW', 'XRP/KRW'] 
    collector = ExchangeWS(symbols)
    
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    
    def handle_exit():
        stop_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_exit)

    main_task = asyncio.create_task(collector.run())
    await stop_event.wait()
    await collector.cleanup()
    main_task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
