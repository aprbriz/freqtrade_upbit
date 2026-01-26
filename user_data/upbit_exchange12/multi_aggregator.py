# multi_aggregator.py
import time
import logging
from timeframe_aggregator import TimeframeAggregator
from tick_aggregator import TickAggregator

logger = logging.getLogger("multi-aggregator")


class MultiAggregator:
    """
    모든 Aggregator를 한 곳에서 관리
    
    [개선1] 로깅 추가
    이유: 디버깅 및 모니터링 용이
    """
    
    def __init__(self, writer):
        # [개선2] Aggregator 리스트 관리 개선
        # 이유: 유연한 타임프레임 추가/제거
        self.time_aggrs = [
            TimeframeAggregator(500, writer),   # 0.5초봉
            TimeframeAggregator(1000, writer),  # 1초봉
        ]
        self.tick_aggr = TickAggregator(3, writer)
        
        # [개선3] 통계 정보 추가
        self.stats = {
            'total_updates': 0,
            'total_flushes': 0,
            'last_update_time': None,
        }
    
    def update(self, pair: str, price: float, volume: float, ts_ms: int):
        """
        [개선4] 예외 처리 추가
        이유: 한 aggregator 실패가 전체에 영향 주지 않도록
        """
        try:
            # 시간 기반 aggregator 업데이트
            for aggr in self.time_aggrs:
                try:
                    aggr.update(pair, price, volume, ts_ms)
                except Exception as e:
                    logger.error(f"TimeframeAggregator 업데이트 에러 ({aggr.timeframe_ms}ms): {e}")
            
            # 틱 기반 aggregator 업데이트
            try:
                self.tick_aggr.update(pair, price, volume, ts_ms)
            except Exception as e:
                logger.error(f"TickAggregator 업데이트 에러: {e}")
            
            # [개선5] 통계 업데이트
            self.stats['total_updates'] += 1
            self.stats['last_update_time'] = time.time()
            
        except Exception as e:
            logger.error(f"MultiAggregator 업데이트 에러: {e}")
    
    def flush(self, max_late_ms: int):
        """
        [개선6] flush 로직 개선
        이유: 에러 처리 및 통계 추가
        """
        now_ms = int(time.time() * 1000)
        total_flushed = 0
        
        try:
            for aggr in self.time_aggrs:
                try:
                    flushed = aggr.flush_old(now_ms, max_late_ms)
                    total_flushed += flushed
                    
                    # [개선7] flush 결과 로깅 (DEBUG 레벨)
                    if flushed > 0:
                        logger.debug(f"Flushed {flushed} candles from {aggr.timeframe_ms}ms aggregator")
                        
                except Exception as e:
                    logger.error(f"Flush 에러 ({aggr.timeframe_ms}ms): {e}")
            
            # [개선8] 통계 업데이트
            if total_flushed > 0:
                self.stats['total_flushes'] += 1
                logger.debug(f"Total flushed: {total_flushed} candles")
            
        except Exception as e:
            logger.error(f"MultiAggregator flush 에러: {e}")
        
        return total_flushed
    
    def shutdown(self):
        """
        [개선9] 종료 로직 개선
        이유: 모든 데이터 안전하게 저장
        """
        logger.info("MultiAggregator 종료 중...")
        
        try:
            # [개선10] 시간 기반 aggregator 남은 데이터 flush
            # 이유: 원본 코드에서 누락됨
            logger.info("시간 기반 aggregator flush 중...")
            now_ms = int(time.time() * 1000)
            for aggr in self.time_aggrs:
                try:
                    # [개선11] 모든 데이터 강제 flush (max_late_ms=0)
                    flushed = aggr.flush_old(now_ms, max_late_ms=0)
                    logger.info(f"{aggr.timeframe_ms}ms aggregator: {flushed}건 flush")
                except Exception as e:
                    logger.error(f"TimeframeAggregator shutdown 에러: {e}")
            
            # 틱 기반 aggregator flush
            logger.info("틱 기반 aggregator flush 중...")
            self.tick_aggr.flush_all()
            
            logger.info("MultiAggregator 종료 완료")
            
        except Exception as e:
            logger.error(f"MultiAggregator shutdown 에러: {e}")
    
    def get_stats(self) -> dict:
        """
        [개선12] 통계 조회 메서드 추가
        이유: 모니터링에 유용
        """
        return self.stats.copy()