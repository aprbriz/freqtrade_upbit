import asyncio
import logging
import csv
import os
import signal
from datetime import datetime
# [변경] CCXT Pro 업비트 모듈 사용
from ccxt.pro import upbit as ccxt_upbit 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UpbitWS-Collector")

class ExchangeWS:
    """ [변경] watch_ohlcv 미지원으로 인해 watch_trades를 사용하여 캔들 생성 """
    def __init__(self, symbols: list):
        self.symbols = symbols
        self.timeframe = '1m'
        self._background_tasks: set[asyncio.Task] = set()
        self._running = True
        self._ccxt_object = None
        # [변경] 실시간 체결 데이터를 캔들로 합치기 위한 저장소
        self.current_candles = {} 

    def _init_ccxt(self):
        return ccxt_upbit({
            'enableRateLimit': True,
            'options': {'ws': {'heartbeat': 30000}}
        })

    async def _pair_worker(self, symbol: str):
        """ 각 심볼별 체결 데이터 수신 및 캔들 연산 """
        safe_symbol = symbol.replace('/', '_')
        file_path = os.path.join(os.getcwd(), f"{safe_symbol}_ohlcv.csv")
        
        if not os.path.exists(file_path):
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['data_time', 'open', 'high', 'low', 'close', 'volume'])

        while self._running:
            try:
                # [변경] 업비트에서 지원하는 watch_trades(실시간 체결) 사용
                trades = await self._ccxt_object.watch_trades(symbol)
                
                for trade in trades:
                    ts = trade['timestamp']
                    price = trade['price']
                    amount = trade['amount']
                    
                    # [변경] 1분 단위 타임스탬프 계산 (60000ms = 1분)
                    candle_ts = (ts // 60000) * 60000
                    
                    if symbol not in self.current_candles:
                        self.current_candles[symbol] = self._create_new_candle(candle_ts, price, amount)
                    
                    candle = self.current_candles[symbol]
                    
                    # [변경] 새로운 분(Minute)이 시작되면 이전 분 데이터 저장
                    if candle_ts > candle['ts']:
                        self._save_to_csv(file_path, candle)
                        self.current_candles[symbol] = self._create_new_candle(candle_ts, price, amount)
                    else:
                        # 같은 분 안에서는 OHLCV 값 업데이트
                        candle['high'] = max(candle['high'], price)
                        candle['low'] = min(candle['low'], price)
                        candle['close'] = price
                        candle['vol'] += amount
                        self._save_to_csv(file_path, candle)

            except Exception as e:
                logger.error(f"[{symbol}] 오류: {e}")
                await asyncio.sleep(5)

    def _create_new_candle(self, ts, price, amount):
        return {'ts': ts, 'open': price, 'high': price, 'low': price, 'close': price, 'vol': amount}

    def _save_to_csv(self, file_path, candle):
        """ [변경] 완성된 1분 캔들을 CSV에 기록 """
        dt = datetime.fromtimestamp(candle['ts'] / 1000).strftime('%Y/%m/%d %H:%M:%S')
        row = [dt, candle['open'], candle['high'], candle['low'], candle['close'], candle['vol']]
        with open(file_path, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(row)
        logger.info(f"캔들 저장 완료: {dt} | 종가: {candle['close']}")

    async def run(self):
        self._ccxt_object = self._init_ccxt()
        for symbol in self.symbols:
            task = asyncio.create_task(self._pair_worker(symbol))
            self._background_tasks.add(task)
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

    async def cleanup(self):
        self._running = False
        for task in self._background_tasks: task.cancel()
        if self._ccxt_object: await self._ccxt_object.close()

async def main():
    # [변경] 업비트용 원화 마켓 심볼
    symbols = ['BTC/KRW', 'ETH/KRW', 'XRP/KRW']
    collector = ExchangeWS(symbols)
    
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: stop_event.set())

    main_task = asyncio.create_task(collector.run())
    await stop_event.wait()
    await collector.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
