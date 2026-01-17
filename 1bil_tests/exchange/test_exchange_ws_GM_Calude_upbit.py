import asyncio
import logging
import csv
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, Set
# [변경] CCXT Pro 업비트 모듈 사용
from ccxt.pro import upbit as ccxt_upbit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UpbitWS-Collector")


class ExchangeWS:
    """ [변경] watch_ohlcv 미지원으로 인해 watch_trades를 사용하여 캔들 생성 """
    
    def __init__(self, symbols: list, data_dir: str = 'upbit_data'):
        self.symbols = symbols
        self.timeframe = '1m'
        self._background_tasks: Set[asyncio.Task] = set()
        self._running = True
        self._ccxt_object = None
        
        # [개선1] 데이터 디렉토리 생성
        # 이유: 파일을 현재 디렉토리에 바로 생성하면 지저분해짐
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # [변경] 실시간 체결 데이터를 캔들로 합치기 위한 저장소
        self.current_candles: Dict[str, dict] = {}
        
        # [개선2] 파일 핸들 캐싱으로 성능 향상
        # 이유: 매번 파일을 열고 닫으면 I/O 오버헤드가 큼
        self._file_handles: Dict[str, object] = {}
        self._csv_writers: Dict[str, csv.writer] = {}
    
    def _init_ccxt(self):
        return ccxt_upbit({
            'enableRateLimit': True,
            'options': {'ws': {'heartbeat': 30000}}
        })
    
    def _get_file_path(self, symbol: str) -> Path:
        """
        [개선3] 파일 경로 생성 로직 분리
        이유: 코드 재사용성과 가독성 향상
        """
        safe_symbol = symbol.replace('/', '_')
        return self.data_dir / f"{safe_symbol}_ohlcv.csv"
    
    def _init_csv_file(self, symbol: str):
        """
        [개선4] CSV 파일 초기화 로직 분리
        이유: 파일 핸들을 열어두고 재사용하기 위해
        """
        file_path = self._get_file_path(symbol)
        
        # 파일이 없으면 헤더 작성
        file_exists = file_path.exists()
        
        # [개선5] 파일 핸들을 열어두고 재사용 (buffering=1로 라인 버퍼링)
        # 이유: 매번 열고 닫는 것보다 빠르며, 라인 버퍼링으로 데이터 유실 방지
        f = open(file_path, 'a', newline='', encoding='utf-8', buffering=1)
        writer = csv.writer(f)
        
        if not file_exists:
            # [개선6] save_time 컬럼 추가 (요구사항 반영)
            # 이유: 데이터 수신 시간과 저장 시간을 구분하여 기록
            writer.writerow(['data_time', 'save_time', 'open', 'high', 'low', 'close', 'volume'])
            logger.info(f"CSV 파일 생성: {file_path}")
        
        self._file_handles[symbol] = f
        self._csv_writers[symbol] = writer
    
    async def _pair_worker(self, symbol: str):
        """
        각 심볼별 체결 데이터 수신 및 캔들 연산
        [개선7] 에러 처리 강화 및 재연결 로직 개선
        """
        self._init_csv_file(symbol)
        
        # [개선8] 연속 에러 카운터 추가
        # 이유: 일시적 네트워크 에러는 재시도하되, 지속적 에러는 중단
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._running:
            try:
                # [변경] 업비트에서 지원하는 watch_trades(실시간 체결) 사용
                trades = await self._ccxt_object.watch_trades(symbol)
                
                # [개선9] 연결 성공 시 에러 카운터 리셋
                consecutive_errors = 0
                
                for trade in trades:
                    ts = trade['timestamp']
                    price = trade['price']
                    amount = trade['amount']
                    
                    # [변경] 1분 단위 타임스탬프 계산 (60000ms = 1분)
                    candle_ts = (ts // 60000) * 60000
                    
                    if symbol not in self.current_candles:
                        self.current_candles[symbol] = self._create_new_candle(candle_ts, price, amount)
                    
                    candle = self.current_candles[symbol]
                    
                    # [개선10] 새로운 분이 시작되면 이전 캔들 저장 후 새 캔들 시작
                    # 이유: 1분봉이 완성될 때만 저장 (원래 로직 유지하되 명확성 개선)
                    if candle_ts > candle['ts']:
                        # 이전 캔들 저장 (완성된 1분봉)
                        self._save_to_csv(symbol, candle, is_complete=True)
                        # 새 캔들 시작
                        self.current_candles[symbol] = self._create_new_candle(candle_ts, price, amount)
                    else:
                        # [개선11] 같은 분 안에서는 OHLCV 값만 업데이트 (저장은 하지 않음)
                        # 이유: 불필요한 I/O 줄이기 위해 진행 중인 캔들은 저장하지 않음
                        # 요구사항에서 "틱이 바뀔 때마다 저장"을 원하면 아래 주석 해제
                        candle['high'] = max(candle['high'], price)
                        candle['low'] = min(candle['low'], price)
                        candle['close'] = price
                        candle['vol'] += amount
                        # [선택12] 진행 중인 캔들도 저장하려면 아래 주석 해제
                        self._save_to_csv(symbol, candle, is_complete=False)
                        
            except asyncio.CancelledError:
                # [개선13] 정상 종료 시 현재 진행 중인 캔들도 저장
                # 이유: 프로그램 종료 시 마지막 데이터 유실 방지
                logger.info(f"[{symbol}] 태스크 종료 중...")
                if symbol in self.current_candles:
                    self._save_to_csv(symbol, self.current_candles[symbol], is_complete=False)
                break
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"[{symbol}] 오류 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                # [개선14] 최대 에러 횟수 초과 시 해당 심볼 중단
                # 이유: 무한 재시도보다는 명확한 실패 처리
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"[{symbol}] 연속 에러 한도 초과, 수집 중단")
                    break
                    
                await asyncio.sleep(5)
        
        logger.info(f"[{symbol}] 워커 종료")
    
    def _create_new_candle(self, ts, price, amount):
        """새로운 1분봉 캔들 생성"""
        return {
            'ts': ts,
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'vol': amount
        }
    
    def _save_to_csv(self, symbol: str, candle: dict, is_complete: bool = True):
        """
        [개선15] 완성된 1분 캔들을 CSV에 기록
        이유: is_complete 플래그로 완성/진행중 구분 가능
        """
        # [개선16] data_time과 save_time 구분 (요구사항 반영)
        data_time = datetime.fromtimestamp(candle['ts'] / 1000).strftime('%Y/%m/%d %H:%M:%S')
        save_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
        
        row = [
            data_time,
            save_time,
            candle['open'],
            candle['high'],
            candle['low'],
            candle['close'],
            candle['vol']
        ]
        
        # [개선17] 캐싱된 writer 사용
        writer = self._csv_writers[symbol]
        writer.writerow(row)
        
        # [개선18] 로그 레벨 조정 (완성된 캔들만 INFO, 진행중은 DEBUG)
        # 이유: 로그가 너무 많으면 성능 저하 및 가독성 하락
        if is_complete:
            logger.info(f"[{symbol}] 캔들 저장: {data_time} | 종가: {candle['close']:.2f} | 거래량: {candle['vol']:.4f}")
        else:
            logger.debug(f"[{symbol}] 진행중 캔들: {data_time} | 종가: {candle['close']:.2f}")
    
    async def run(self):
        """메인 실행 로직"""
        self._ccxt_object = self._init_ccxt()
        
        # [개선19] 태스크 생성 시 done_callback 추가
        # 이유: 태스크가 예상치 못하게 종료되면 자동으로 set에서 제거
        for symbol in self.symbols:
            task = asyncio.create_task(self._pair_worker(symbol))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
    
    async def cleanup(self):
        """
        [개선20] 리소스 정리 로직 강화
        이유: 파일 핸들, CCXT 연결 등 모든 리소스를 안전하게 정리
        """
        logger.info("수집기 종료 중...")
        self._running = False
        
        # 모든 태스크 취소
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        # 태스크 종료 대기
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        # [개선21] 열려있는 파일 핸들 모두 닫기
        # 이유: 파일 핸들을 열어두었으므로 명시적으로 닫아야 함
        for symbol, f in self._file_handles.items():
            try:
                f.close()
                logger.debug(f"[{symbol}] 파일 핸들 닫기 완료")
            except Exception as e:
                logger.error(f"[{symbol}] 파일 닫기 실패: {e}")
        
        # CCXT 연결 종료
        if self._ccxt_object:
            try:
                await self._ccxt_object.close()
                logger.info("CCXT 연결 종료 완료")
            except Exception as e:
                logger.error(f"CCXT 연결 종료 실패: {e}")


async def main():
    """
    [개선22] 메인 함수 개선
    이유: 시그널 핸들러를 더 명확하게 처리
    """
    # [변경] 업비트용 원화 마켓 심볼
    symbols = ['BTC/KRW', 'ETH/KRW', 'XRP/KRW']
    
    logger.info("=" * 60)
    logger.info("업비트 WebSocket 데이터 수집기")
    logger.info("=" * 60)
    logger.info(f"수집 심볼: {', '.join(symbols)}")
    logger.info(f"타임프레임: 1분봉 (watch_trades로 집계)")
    logger.info(f"저장 위치: upbit_data/")
    logger.info("종료: Ctrl+C")
    logger.info("=" * 60)
    
    collector = ExchangeWS(symbols, data_dir='upbit_data')
    
    # [개선23] 시그널 핸들러 개선
    # 이유: asyncio.Event를 사용하여 더 명확한 종료 처리
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        logger.info("\n종료 신호 수신 (Ctrl+C)...")
        stop_event.set()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    # 메인 태스크 시작
    main_task = asyncio.create_task(collector.run())
    
    # 종료 신호 대기
    await stop_event.wait()
    
    # 정리 작업
    await collector.cleanup()
    
    logger.info("프로그램 종료 완료")


if __name__ == "__main__":
    asyncio.run(main())