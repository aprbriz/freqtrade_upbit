# timeframe_aggregator.py
import threading
import logging
from collections import defaultdict

logger = logging.getLogger("timeframe-aggregator")


class TimeframeAggregator:
    """
    시간 기반 OHLCV 봉 생성기
    예)
    - 500ms (0.5초봉)
    - 1000ms (1초봉)
    """
    
    def __init__(self, timeframe_ms: int, writer):
        self.timeframe_ms = timeframe_ms
        self.writer = writer
        
        # pair -> { bucket_ts -> candle }
        self.data = defaultdict(dict)
        self.lock = threading.Lock()
        
        # [개선1] 통계 정보 추가
        self.stats = {
            'total_updates': 0,
            'total_candles': 0,
        }
    
    def _bucket_ts(self, ts_ms: int) -> int:
        """
        체결 시각(ms)을 봉 시작 시각(ms)으로 변환
        """
        return (ts_ms // self.timeframe_ms) * self.timeframe_ms
    
    def update(self, pair: str, price: float, volume: float, ts_ms: int):
        """
        체결 데이터 1건으로 봉 업데이트
        
        [개선2] 에러 처리 및 로깅 추가
        """
        try:
            # [개선3] 데이터 검증
            if price <= 0 or volume < 0:
                logger.warning(f"[{pair}] 잘못된 데이터 무시: price={price}, volume={volume}")
                return
            
            bucket_ts = self._bucket_ts(ts_ms)
            
            with self.lock:
                candle = self.data[pair].get(bucket_ts)
                
                if candle is None:
                    # 새로운 봉 시작
                    self.data[pair][bucket_ts] = {
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": volume,
                    }
                    logger.debug(f"[{pair}] 새 {self.timeframe_ms}ms 봉 시작: ts={bucket_ts}")
                else:
                    # 기존 봉 업데이트
                    candle["high"] = max(candle["high"], price)
                    candle["low"] = min(candle["low"], price)
                    candle["close"] = price
                    candle["volume"] += volume
                
                # [개선4] 통계 업데이트
                self.stats['total_updates'] += 1
                
        except Exception as e:
            logger.error(f"[{pair}] TimeframeAggregator 업데이트 에러 ({self.timeframe_ms}ms): {e}")
    
    def flush_old(self, now_ms: int, max_late_ms: int):
        """
        오래된 봉을 DB에 저장
        
        [개선5] 에러 처리 및 반환값 추가
        """
        flushed = 0
        
        try:
            with self.lock:
                for pair in list(self.data.keys()):
                    for bucket_ts in list(self.data[pair].keys()):
                        # [개선6] 조건 검사 명확화
                        # 이유: max_late_ms보다 오래된 봉만 저장
                        if bucket_ts < now_ms - max_late_ms:
                            candle = self.data[pair].pop(bucket_ts)
                            
                            try:
                                self.writer.write(
                                    pair=pair,
                                    ts=bucket_ts,
                                    timeframe_ms=self.timeframe_ms,
                                    candle=candle,
                                )
                                flushed += 1
                                
                                # [개선7] 통계 업데이트
                                self.stats['total_candles'] += 1
                                
                                logger.debug(
                                    f"[{pair}] {self.timeframe_ms}ms 봉 저장: "
                                    f"ts={bucket_ts}, O={candle['open']:.2f}, "
                                    f"H={candle['high']:.2f}, L={candle['low']:.2f}, "
                                    f"C={candle['close']:.2f}, V={candle['volume']:.4f}"
                                )
                                
                            except Exception as e:
                                logger.error(f"[{pair}] 봉 저장 에러 ({self.timeframe_ms}ms): {e}")
                    
                    # [개선8] 빈 pair 딕셔너리 제거
                    # 이유: 메모리 효율성
                    if not self.data[pair]:
                        del self.data[pair]
                        
        except Exception as e:
            logger.error(f"TimeframeAggregator flush_old 에러 ({self.timeframe_ms}ms): {e}")
        
        return flushed
    
    def get_stats(self) -> dict:
        """
        [개선9] 통계 조회 메서드
        이유: 모니터링에 유용
        """
        stats = self.stats.copy()
        stats['pending_pairs'] = len(self.data)
        
        # 각 pair별 pending 봉 개수
        with self.lock:
            stats['pending_candles'] = {
                pair: len(candles)
                for pair, candles in self.data.items()
            }
        
        return stats