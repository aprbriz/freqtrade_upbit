import asyncio
import logging
import csv
import os
import signal
from datetime import datetime
# CCXT Pro 라이브러리 사용
from ccxt.pro import binance as ccxt_binance
from freqtrade.enums import CandleType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ExchangeWS-Collector")

class ExchangeWS:
    def __init__(self, symbols: list):
        # 2. ccxt.pro.binance 호출 (freqtrade 스타일 참조)
        self._ccxt_object = ccxt_binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        self.symbols = symbols
        self.timeframe = '1m'
        self._background_tasks: set[asyncio.Task] = set()
        self._running = True

    async def _pair_worker(self, symbol: str):
        """
        8. 각 코인 페어별로 독립적인 루프 생성. 
        한쪽에서 에러가 나도 다른 루프는 영향을 받지 않음.
        """
        # 저장 경로 설정: 현재 디렉토리에 페어별 CSV 생성
        file_path = os.path.join(os.getcwd(), f"{symbol.replace('/', '_')}_ohlcv.csv")
        logger.info(f"[{symbol}] 저장 시작 -> {file_path}")

        # CSV 헤더 작성 (파일이 없을 때만)
        if not os.path.exists(file_path):
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['data_time', 'save_time', 'open', 'high', 'low', 'close', 'volume'])

        while self._running:
            try:
                # 3. ccxt.pro websocket으로 데이터 수신
                # 4. 1분봉 확정 전에도 틱이 바뀔 때마다 데이터 수신
                ohlcv = await self._ccxt_object.watch_ohlcv(symbol, self.timeframe)
                
                if ohlcv and len(ohlcv) > 0:
                    candle = ohlcv[-1]  # 가장 최근의 틱 데이터
                    
                    # 5 & 6. 시간 데이터 포맷 설정 (2026/01/11 15:01:03)
                    data_time = datetime.fromtimestamp(candle[0] / 1000).strftime('%Y/%m/%d %H:%M:%S')
                    save_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
                    
                    # 데이터 매핑
                    row = [
                        data_time, 
                        save_time, 
                        candle[1], # Open
                        candle[2], # High
                        candle[3], # Low
                        candle[4], # Close
                        candle[5]  # Volume
                    ]

                    # 실시간 파일 쓰기 (buffer 없이 바로 기록)
                    with open(file_path, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(row)
                    
            except Exception as e:
                logger.error(f"[{symbol}] 루프 에러 발생: {e}")
                await asyncio.sleep(5)  # 에러 발생 시 5초 후 재연결 시도

    async def run(self):
        """모든 페어에 대해 태스크 시작"""
        for symbol in self.symbols:
            task = asyncio.create_task(self._pair_worker(symbol))
            self._background_tasks.add(task)
        
        await asyncio.gather(*self._background_tasks)

    async def cleanup(self):
        """7. 중단 시 안전한 종료"""
        self._running = False
        logger.info("프로그램을 종료하고 연결을 닫는 중...")
        await self._ccxt_object.close()
        for task in self._background_tasks:
            task.cancel()

async def main():
    # 수집할 페어 리스트
    symbols = ['BTC/USDT', 'ETH/USDT']
    collector = ExchangeWS(symbols)

    # ^C 입력 시 cleanup 실행
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(collector.cleanup()))

    try:
        await collector.run()
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
