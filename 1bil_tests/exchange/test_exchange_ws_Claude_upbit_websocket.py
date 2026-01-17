import asyncio
import json
import logging
import signal
from datetime import datetime
from pathlib import Path
from typing import Set
import websockets  # pip install websockets 필요

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UpbitWSCollector:
    """
    업비트 WebSocket OHLCV 데이터 수집기
    - 업비트 공식 WebSocket API로 연결
    - 실시간 틱 데이터를 CSV로 저장
    - data_time과 save_time을 구분하여 기록
    - 페어별 독립적으로 실행되어 에러 발생 시에도 다른 페어에 영향 없음
    """
    
    # 업비트 WebSocket 엔드포인트 (Binance와 다름)
    UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
    
    def __init__(self, markets: list[str], timeframe: str = '1m', data_dir: str = 'upbit_ohlcv_data'):
        """
        Args:
            markets: 마켓 코드 리스트 (예: ['KRW-BTC', 'KRW-ETH'])
                     업비트는 'KRW-BTC' 형식 사용 (Binance의 'BTC/USDT'와 다름)
            timeframe: 캔들 타임프레임 (1m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d, 1w, 1M)
            data_dir: 데이터 저장 디렉토리
        """
        self.markets = markets
        self.timeframe = timeframe
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self._tasks: Set[asyncio.Task] = set()
        self._running = True
        
        # 업비트 캔들 타입 매핑 (Binance와 다름)
        self.candle_type_map = {
            '1s': 'candle.1s',
            '1m': 'candle.1m',
            '3m': 'candle.3m',
            '5m': 'candle.5m',
            '10m': 'candle.10m',
            '15m': 'candle.15m',
            '30m': 'candle.30m',
            '1h': 'candle.1h',
            '4h': 'candle.4h',
            '1d': 'candle.1d',
            '1w': 'candle.1w',
            '1M': 'candle.1M',
        }
    
    def _get_csv_path(self, market: str) -> Path:
        """마켓별 CSV 파일 경로 생성"""
        safe_market = market.replace('-', '_')  # KRW-BTC -> KRW_BTC
        return self.data_dir / f"{safe_market}_{self.timeframe}.csv"
    
    def _format_time(self, time_str: str) -> str:
        """
        업비트 시간 포맷을 요구사항 포맷으로 변환
        업비트: "2025-01-02T13:28:05" -> 요구사항: "2026/01/11 15:01:03"
        """
        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        return dt.strftime('%Y/%m/%d %H:%M:%S')
    
    def _init_csv_file(self, market: str):
        """CSV 파일 초기화 (헤더 생성)"""
        csv_path = self._get_csv_path(market)
        if not csv_path.exists():
            with open(csv_path, 'w', encoding='utf-8') as f:
                # 업비트 캔들 데이터 구조에 맞춘 헤더
                f.write('data_time,save_time,open,high,low,close,volume,value\n')
            logger.info(f"CSV 파일 생성: {csv_path}")
    
    def _save_candle(self, market: str, candle_data: dict):
        """
        캔들 데이터를 CSV에 저장
        업비트 캔들 데이터 구조:
        - candle_date_time_kst: 한국 시간 캔들 시각
        - opening_price: 시가
        - high_price: 고가
        - low_price: 저가
        - trade_price: 종가
        - candle_acc_trade_volume: 누적 거래량
        - candle_acc_trade_price: 누적 거래대금
        """
        try:
            csv_path = self._get_csv_path(market)
            
            # 데이터 시간 (업비트에서 제공하는 KST 시간 사용)
            data_time = self._format_time(candle_data.get('candle_date_time_kst', ''))
            
            # 저장 시간 (현재 시간)
            save_time = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
            
            # OHLCV 데이터 추출
            open_price = candle_data.get('opening_price', 0)
            high_price = candle_data.get('high_price', 0)
            low_price = candle_data.get('low_price', 0)
            close_price = candle_data.get('trade_price', 0)
            volume = candle_data.get('candle_acc_trade_volume', 0)
            value = candle_data.get('candle_acc_trade_price', 0)
            
            with open(csv_path, 'a', encoding='utf-8') as f:
                line = f"{data_time},{save_time},{open_price},{high_price},{low_price},{close_price},{volume},{value}\n"
                f.write(line)
                
            logger.debug(f"[{market}] 저장 완료: {data_time} -> {save_time}")
            
        except Exception as e:
            logger.error(f"[{market}] CSV 저장 중 에러: {e}")
    
    async def _watch_candle_for_market(self, market: str):
        """
        단일 마켓의 캔들 데이터를 WebSocket으로 수신 (독립적으로 실행)
        업비트 WebSocket 프로토콜:
        1. 연결 후 JSON 형식으로 구독 요청 전송
        2. 바이너리(또는 텍스트) 형식으로 데이터 수신
        """
        logger.info(f"[{market}] WebSocket 연결 시작...")
        self._init_csv_file(market)
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self._running:
            try:
                # 업비트 WebSocket 연결 (Binance와 다른 URL)
                async with websockets.connect(self.UPBIT_WS_URL) as websocket:
                    # 업비트 WebSocket 구독 메시지 생성 (Binance와 완전히 다른 포맷)
                    candle_type = self.candle_type_map.get(self.timeframe, 'candle.1m')
                    subscribe_data = [
                        {"ticket": f"{market}_{self.timeframe}"},  # 고유 티켓
                        {
                            "type": candle_type,  # 캔들 타입
                            "codes": [market]  # 마켓 코드 리스트
                        },
                        {"format": "DEFAULT"}  # 응답 포맷
                    ]
                    
                    # 구독 요청 전송
                    await websocket.send(json.dumps(subscribe_data))
                    logger.info(f"[{market}] 구독 요청 전송 완료: {candle_type}")
                    
                    # 데이터 수신 루프
                    while self._running:
                        try:
                            # 업비트는 바이너리 또는 텍스트로 응답 (Binance와 다름)
                            message = await websocket.recv()
                            
                            # 바이너리 데이터인 경우 디코딩
                            if isinstance(message, bytes):
                                message = message.decode('utf-8')
                            
                            # JSON 파싱
                            candle_data = json.loads(message)
                            
                            # 캔들 데이터 저장
                            self._save_candle(market, candle_data)
                            
                            consecutive_errors = 0  # 성공 시 에러 카운터 초기화
                            
                        except asyncio.CancelledError:
                            logger.info(f"[{market}] 태스크 취소됨")
                            raise
                            
                        except json.JSONDecodeError as e:
                            logger.warning(f"[{market}] JSON 파싱 실패: {e}")
                            continue
                            
                        except Exception as e:
                            logger.error(f"[{market}] 메시지 처리 중 에러: {e}")
                            consecutive_errors += 1
                            if consecutive_errors >= max_consecutive_errors:
                                raise
                            await asyncio.sleep(1)
                            
            except asyncio.CancelledError:
                logger.info(f"[{market}] 태스크 종료 중...")
                break
                
            except websockets.exceptions.WebSocketException as e:
                consecutive_errors += 1
                logger.warning(f"[{market}] WebSocket 에러 ({consecutive_errors}/{max_consecutive_errors}): {e}")
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
            task = asyncio.create_task(self._watch_candle_for_market(market))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        
        # 모든 태스크 완료 대기
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
        
        logger.info("수집기 중지 완료")
    
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
        pip install websockets
    """
    # 수집할 마켓 설정 (업비트는 KRW-BTC 형식 사용)
    markets = [
        'KRW-BTC',   # 비트코인
        'KRW-ETH',   # 이더리움
        'KRW-XRP',   # 리플
    ]
    
    # 수집기 생성 및 설정
    collector = UpbitWSCollector(
        markets=markets,
        timeframe='1m',  # 1분봉 (1s, 1m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d, 1w, 1M 지원)
        data_dir='upbit_ohlcv_data'
    )
    
    logger.info("=" * 60)
    logger.info("업비트 WebSocket OHLCV 수집기")
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