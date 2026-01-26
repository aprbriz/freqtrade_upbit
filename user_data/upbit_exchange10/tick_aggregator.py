# tick_aggregator.py
import threading
import logging
from collections import defaultdict

logger = logging.getLogger("tick-aggregator")


class TickAggregator:
    """
    틱 기반 봉 생성기 (예: 3틱봉)
    """
    
    def __init__(self, tick_size: int, writer):
        self.tick_size = tick_size
        self.writer = writer
        self.current = defaultdict(dict)
        self.lock = threading.Lock()
        
        # [개선1] 통계 정보 추가
        self.stats = {
            'total_ticks': 0,
            'total_candles': 0,
        }
    
    def update(self, pair: str, price: float, volume: float, ts_ms: int):
        """
        체결 데이터 1건 처리
        
        [개선2] 에러 처리 및 로깅 추가
        """
        try:
            # [개선3] 데이터 검증
            # 이유: 잘못된 데이터 방지
            if price <= 0 or volume < 0:
                logger.warning(f"[{pair}] 잘못된 데이터 무시: price={price}, volume={volume}")
                return
            
            with self.lock:
                candle = self.current.get(pair)
                
                if not candle:
                    # 새로운 캔들 시작
                    self.current[pair] = {
                        "count": 1,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": volume,
                        "start_ts": ts_ms,
                    }
                    logger.debug(f"[{pair}] 새 틱봉 시작 (1/{self.tick_size})")
                    return
                
                # 기존 캔들 업데이트
                candle["count"] += 1
                candle["high"] = max(candle["high"], price)
                candle["low"] = min(candle["low"], price)
                candle["close"] = price
                candle["volume"] += volume
                
                logger.debug(f"[{pair}] 틱 추가 ({candle['count']}/{self.tick_size})")
                
                # [개선4] tick_size 도달 시 저장
                if candle["count"] >= self.tick_size:
                    try:
                        self.writer.write(
                            pair=pair,
                            ts=candle["start_ts"],
                            timeframe_ms=-self.tick_size,  # 틱봉은 음수
                            candle=candle,
                        )
                        logger.debug(f"[{pair}] {self.tick_size}틱봉 저장 완료")
                        
                        # [개선5] 통계 업데이트
                        self.stats['total_candles'] += 1
                        
                    except Exception as e:
                        logger.error(f"[{pair}] 틱봉 저장 에러: {e}")
                    
                    # 저장 후 제거
                    self.current.pop(pair, None)
                
                # 통계 업데이트
                self.stats['total_ticks'] += 1
                
        except Exception as e:
            logger.error(f"[{pair}] TickAggregator 업데이트 에러: {e}")
    
    def flush_all(self):
        """
        종료 시 남은 틱봉 강제 저장
        
        [개선6] 에러 처리 강화
        """
        logger.info("TickAggregator flush_all 시작...")
        flushed = 0
        
        with self.lock:
            for pair, candle in list(self.current.items()):
                try:
                    # [개선7] count가 0보다 큰 경우만 저장
                    # 이유: 빈 캔들 저장 방지
                    if candle.get("count", 0) > 0:
                        self.writer.write(
                            pair=pair,
                            ts=candle["start_ts"],
                            timeframe_ms=-self.tick_size,
                            candle=candle,
                        )
                        flushed += 1
                        logger.info(f"[{pair}] 미완성 틱봉 저장: {candle['count']}틱")
                        
                except Exception as e:
                    logger.error(f"[{pair}] flush_all 에러: {e}")
            
            # 모두 제거
            self.current.clear()
        
        logger.info(f"TickAggregator flush_all 완료: {flushed}건")
    
    def get_stats(self) -> dict:
        """
        [개선8] 통계 조회 메서드
        이유: 모니터링에 유용
        """
        stats = self.stats.copy()
        stats['pending_pairs'] = len(self.current)
        return stats