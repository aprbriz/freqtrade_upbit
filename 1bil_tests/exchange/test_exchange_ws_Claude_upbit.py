import asyncio
import logging
import signal
from datetime import datetime
from pathlib import Path
from typing import Set
import ccxt.pro as ccxtpro  # ccxt.pro 사용 (Binance와 동일한 방식)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UpbitWSCollector:
    """
    업비트 WebSocket OHLCV 데이터 수집기
    - ccxt.pro를 사용하여 업비트에 연결 (Binance와 동일한 방식)
    - 실시간 틱 데이터를 CSV로 저장
    - data_time과 save_time을 구분하여 기록
    - 페어별 독립적으로 실행되어 에러 발생 시에도 다른 페어에 영향 없음
    """
    
    def __init__(self, markets: list[str], timeframe: str = '1m', data_dir: str = 'upbit_ohlcv_data'):
        """
        Args:
            markets: 마켓 코드 리스트 (예: ['BTC/KRW', 'ETH/KRW'])
                     업비트는 'BTC/KRW' 형식 사용 (Binance의 'BTC/USDT'와 유사)
            timeframe: 캔들 타임프레임 (1m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d, 1w, 1M)
            data_dir: 데이터 저장 디렉토리
        """
        self.markets = markets
        self.timeframe = timeframe
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # ccxt.pro를 사용하여 업비트 거래소 객체 생성 (Binance와 동일한 방식)
        self.exchange = ccxtpro.upbit({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',  # 현물 거래
            }
        })
        
        self._tasks: Set[asyncio.Task] = set()
        self._running = True
        
    def _get_csv_path(self, market: str) -> Path:
        """마켓별 CSV 파일 경로 생성"""
        safe_market = market.replace('/', '_')  # BTC/KRW -> BTC_KRW
        return self.data_dir / f"{safe_market}_{self.timeframe}.csv"
    
    def _format_time(self, timestamp_ms: int) -> str:
        """
        타임스탬프를 요구사항 포맷으로 변환
        timestamp_ms -> "2026/01/11 15:01:03"
        """
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime('%Y/%m/%d %H:%M:%S')
    
    def _init_csv_file(self, market: str):
        """CSV 파일 초기화 (헤더 생성)"""
        csv_path = self._get_csv_path(market)
        if not csv_path.exists():
            with open(csv_path, 'w', encoding='utf-8') as f:
                f.write('data_time,save_time,open,high,low,close,volume\n')
            logger.info(f"CSV 파일 생성: {csv_path}")
    
    def _save_ohlcv(self, market: str, ohlcv: list):
        """
        OHLCV 데이터를 CSV에 저장
        ohlcv 포맷: [timestamp, open, high, low, close, volume]
        """
        try:
            csv_path = self._get_csv_path(market)
            
            # 데이터 시간 (거래소에서 제공한 캔들 타임스탬프)
            data_time = self._format_time(ohlcv[0])
            
            # 저장 시간 (현재 시간)
            save_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
            
            with open(csv_path, 'a', encoding='utf-8') as f:
                line = f"{data_time},{save_time},{ohlcv[1]},{ohlcv[2]},{ohlcv[3]},{ohlcv[4]},{ohlcv[5]}\n"
                f.write(line)
                
            logger.debug(f"[{market}] 저장 완료: {data_time} -> {save_time}")
            
        except Exception as e:
            logger.error(f"[{market}] CSV 저장 중 에러: {e}")
    
    async def _watch_ohlcv_for_market(self, market: str):
        """
        단일 마켓의 OHLCV 데이터를 WebSocket으로 수신 (독립적으로 실행)
        ccxt.pro의 watch_ohlcv 메서드 사용 (Binance와 동일한 방식)
        """
        logger.info(f"[{market}] WebSocket 연결 시작...")
        self._init_csv_file(market)
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._running:
            try:
                # ccxt.pro의 watch_ohlcv 메서드로 실시간 캔들 데이터 수신
                # 이 메서드는 새로운 데이터가 도착할 때마다 즉시 반환됨
                ohlcvs = await self.exchange.watch_ohlcv(market, self.timeframe)
                
                if ohlcvs and len(ohlcvs) > 0:
                    # 최신 캔들 데이터 저장
                    latest_ohlcv = ohlcvs[-1]
                    self._save_ohlcv(market, latest_ohlcv)
                    consecutive_errors = 0  # 성공 시 에러 카운터 초기화
                    
            except asyncio.CancelledError:
                logger.info(f"[{market}] 태스크 취소됨, 종료 중...")
                break
                
            except ccxtpro.NetworkError as e:
                consecutive_errors += 1
                logger.warning(f"[{market}] 네트워크 에러 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"[{market}] 연속 에러 한도 초과, 중단")
                    break
                await asyncio.sleep(5)  # 재연결 대기
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"[{market}] 예상치 못한 에러 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"[{market}] 연속 에러 한도 초과, 중단")
                    break
                await asyncio.sleep(5)
        
        logger.info(f"[{market}] WebSocket 연결 종료")
    
    async def start(self):
        """모든 마켓 감시 시작 - 각 마켓별로 독립적인 태스크 생성"""
        logger.info(f"수집 시작: {len(self.markets)}개 마켓 - {', '.join(self.markets)}")
        
        # 각 마켓별로 독립적인 태스크 생성 (한 마켓 에러가 다른 마켓에 영향 없음)
        for market in self.markets:
            task = asyncio.create_task(self._watch_ohlcv_for_market(market))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        
        # 모든 태스크 완료 대기 (또는 인터럽트될 때까지)
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("모든 태스크 취소됨")
    
    async def stop(self):
        """모든 감시 태스크 중지 및 정리"""
        logger.info("수집기 중지 중...")
        self._running = False
        
        # 모든 실행 중인 태스크 취소
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # 태스크 종료 대기
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Exchange 연결 닫기 (ccxt.pro 권장사항)
        try:
            await self.exchange.close()
            logger.info("거래소 연결 종료 완료")
        except Exception as e:
            logger.error(f"거래소 연결 종료 중 에러: {e}")
    
    def run(self):
        """메인 진입점 - 이벤트 루프 실행"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Ctrl+C 처리
        def signal_handler(sig, frame):
            logger.info("\n인터럽트 신호(Ctrl+C) 수신, 종료 중...")
            loop.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt 수신")
        finally:
            # 정리 작업
            loop.run_until_complete(self.stop())
            loop.close()
            logger.info("수집기 종료 완료")


def main():
    """
    메인 함수
    
    사용법:
        python upbit_ws_collector.py
        
    필수 패키지:
        pip install ccxt
    """
    # 수집할 마켓 설정 (업비트는 BTC/KRW 형식 사용)
    # 주의: 업비트는 역순으로 표기 (KRW가 뒤에 옴)
    markets = [
        'BTC/KRW',   # 비트코인
        'ETH/KRW',   # 이더리움
        'XRP/KRW',   # 리플
    ]
    
    # 수집기 생성 및 설정
    collector = UpbitWSCollector(
        markets=markets,
        timeframe='1m',  # 1분봉 (1m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d, 1w, 1M)
        data_dir='upbit_ohlcv_data'
    )
    
    logger.info("=" * 60)
    logger.info("업비트 WebSocket OHLCV 수집기 (ccxt.pro 사용)")
    logger.info("=" * 60)
    logger.info(f"마켓: {', '.join(markets)}")
    logger.info(f"타임프레임: 1m")
    logger.info(f"저장 디렉토리: upbit_ohlcv_data/")
    logger.info("종료: Ctrl+C")
    logger.info("=" * 60)
    
    # 수집기 실행
    collector.run()


if __name__ == '__main__':
    main()