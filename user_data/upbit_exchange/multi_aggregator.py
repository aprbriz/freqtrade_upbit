# multi_aggregator.py
import time
import logging
import threading
from collections import defaultdict, deque
from timeframe_aggregator import TimeframeAggregator
from tick_aggregator import TickAggregator

logger = logging.getLogger("multi-aggregator")


class DerivedTimeframeAggregator:
    """
    1초봉 기반 합성 봉 (메모리 전용)
    """
    
    def __init__(self, timeframe_ms: int, max_store_per_pair: int = 1000):
        self.timeframe_ms = timeframe_ms
        self.max_store_per_pair = max_store_per_pair
        self.data = defaultdict(dict)
        self.recent = defaultdict(deque)
        self.lock = threading.Lock()
        
        self.stats = {
            'total_updates': 0,
            'total_candles': 0,
            'dropped_candles': 0,
        }
    
    def _bucket_ts(self, ts_ms: int) -> int:
        return (ts_ms // self.timeframe_ms) * self.timeframe_ms
    
    def update_from_candle(self, pair: str, ts_ms: int, candle: dict):
        """
        1초봉 캔들로 합성 봉 업데이트
        """
        try:
            bucket_ts = self._bucket_ts(ts_ms)
            
            with self.lock:
                current = self.data[pair].get(bucket_ts)
                if current is None:
                    self.data[pair][bucket_ts] = {
                        "open": candle["open"],
                        "high": candle["high"],
                        "low": candle["low"],
                        "close": candle["close"],
                        "volume": candle["volume"],
                    }
                else:
                    current["high"] = max(current["high"], candle["high"])
                    current["low"] = min(current["low"], candle["low"])
                    current["close"] = candle["close"]
                    current["volume"] += candle["volume"]
                
                self.stats['total_updates'] += 1
                
        except Exception as e:
            logger.error(f"[{pair}] 합성 봉 업데이트 에러 ({self.timeframe_ms}ms): {e}")
    
    def flush_old(self, now_ms: int, max_late_ms: int):
        """
        완성된 합성 봉을 메모리에 보관
        """
        flushed = 0
        try:
            with self.lock:
                for pair in list(self.data.keys()):
                    for bucket_ts in list(self.data[pair].keys()):
                        if bucket_ts + self.timeframe_ms <= now_ms - max_late_ms:
                            candle = self.data[pair].pop(bucket_ts)
                            self.recent[pair].append((bucket_ts, candle))
                            flushed += 1
                            self.stats['total_candles'] += 1
                            
                            while len(self.recent[pair]) > self.max_store_per_pair:
                                self.recent[pair].popleft()
                                self.stats['dropped_candles'] += 1
                    
                    if not self.data[pair]:
                        del self.data[pair]
                        
        except Exception as e:
            logger.error(f"합성 봉 flush 에러 ({self.timeframe_ms}ms): {e}")
        
        return flushed
    
    def get_stats(self) -> dict:
        """
        통계 조회
        """
        stats = self.stats.copy()
        with self.lock:
            stats['pending_pairs'] = len(self.data)
            stats['pending_candles'] = {
                pair: len(candles)
                for pair, candles in self.data.items()
            }
            stats['stored_candles'] = {
                pair: len(candles)
                for pair, candles in self.recent.items()
            }
        return stats


class MultiAggregator:
    """
    모든 Aggregator를 한 곳에서 관리
    
    [개선1] 로깅 추가
    이유: 디버깅 및 모니터링 용이
    """
    
    def __init__(
        self,
        writer,
        timeframes_ms: list = None,
        tick_sizes: list = None,
        derived_timeframes_ms: list = None,
        derived_source_timeframe_ms: int = 1000,
        derived_max_store: int = 1000,
    ):
        # [개선2] Aggregator 리스트 관리 개선
        # 이유: 유연한 타임프레임 추가/제거
        if timeframes_ms is None:
            timeframes_ms = [500, 1000]
        if tick_sizes is None:
            tick_sizes = [3]
        
        timeframes_ms = sorted(set(timeframes_ms))
        tick_sizes = sorted(set(tick_sizes)) if tick_sizes else []
        
        self.time_aggrs = [
            TimeframeAggregator(tf, writer)
            for tf in timeframes_ms
        ]
        self.time_aggrs_by_tf = {aggr.timeframe_ms: aggr for aggr in self.time_aggrs}
        self.tick_aggrs = [
            TickAggregator(tick, writer)
            for tick in tick_sizes
        ]
        
        # 1초봉 기반 합성 봉 (메모리 전용)
        self.derived_source_timeframe_ms = derived_source_timeframe_ms
        derived_timeframes_ms = sorted(set(derived_timeframes_ms or []))
        derived_timeframes_ms = [
            tf for tf in derived_timeframes_ms
            if tf != derived_source_timeframe_ms
        ]
        self.derived_aggrs = []
        if derived_timeframes_ms and derived_source_timeframe_ms in self.time_aggrs_by_tf:
            self.derived_aggrs = [
                DerivedTimeframeAggregator(tf, derived_max_store)
                for tf in derived_timeframes_ms
            ]
        self.derived_last_ts = {}
        
        # [개선3] 통계 정보 추가
        self.stats = {
            'total_updates': 0,
            'total_flushes': 0,
            'last_update_time': None,
            'total_derived_updates': 0,
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
            for tick_aggr in self.tick_aggrs:
                try:
                    tick_aggr.update(pair, price, volume, ts_ms)
                except Exception as e:
                    logger.error(f"TickAggregator 업데이트 에러 ({tick_aggr.tick_size}틱): {e}")
            
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
                flushed_count = 0
                try:
                    if self.derived_aggrs and aggr.timeframe_ms == self.derived_source_timeframe_ms:
                        flushed_candles = aggr.flush_old(now_ms, max_late_ms, return_candles=True)
                        flushed_count = len(flushed_candles)
                        total_flushed += flushed_count
                        if flushed_candles:
                            for pair, bucket_ts, candle in flushed_candles:
                                self._update_derived_from_1s(pair, bucket_ts, candle)
                    else:
                        flushed_count = aggr.flush_old(now_ms, max_late_ms)
                        total_flushed += flushed_count
                    
                    # [개선7] flush 결과 로깅 (DEBUG 레벨)
                    if flushed_count > 0:
                        logger.debug(f"Flushed {flushed_count} candles from {aggr.timeframe_ms}ms aggregator")
                        
                except Exception as e:
                    logger.error(f"Flush 에러 ({aggr.timeframe_ms}ms): {e}")
            
            # 합성 봉 flush (메모리 전용)
            if self.derived_aggrs:
                for derived in self.derived_aggrs:
                    try:
                        derived_flushed = derived.flush_old(now_ms, max_late_ms)
                        if derived_flushed > 0:
                            logger.debug(f"Flushed {derived_flushed} derived candles ({derived.timeframe_ms}ms)")
                    except Exception as e:
                        logger.error(f"합성 봉 flush 에러 ({derived.timeframe_ms}ms): {e}")
            
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
            for tick_aggr in self.tick_aggrs:
                tick_aggr.flush_all()
            
            # 합성 봉 flush (메모리 전용)
            if self.derived_aggrs:
                now_ms = int(time.time() * 1000)
                for derived in self.derived_aggrs:
                    derived.flush_old(now_ms, max_late_ms=0)
            
            logger.info("MultiAggregator 종료 완료")
            
        except Exception as e:
            logger.error(f"MultiAggregator shutdown 에러: {e}")
    
    def get_stats(self) -> dict:
        """
        [개선12] 통계 조회 메서드 추가
        이유: 모니터링에 유용
        """
        stats = self.stats.copy()
        stats['timeframes'] = {
            str(aggr.timeframe_ms): aggr.get_stats()
            for aggr in self.time_aggrs
        }
        stats['ticks'] = {
            str(aggr.tick_size): aggr.get_stats()
            for aggr in self.tick_aggrs
        }
        stats['derived_timeframes'] = {
            str(aggr.timeframe_ms): aggr.get_stats()
            for aggr in self.derived_aggrs
        }
        return stats

    def _update_derived_from_1s(self, pair: str, ts_ms: int, candle: dict):
        """
        1초봉 기반 합성 봉 업데이트
        """
        last_ts = self.derived_last_ts.get(pair)
        if last_ts is not None and ts_ms <= last_ts:
            logger.warning(f"[{pair}] 1초봉 타임스탬프 역전: last={last_ts}, now={ts_ms}")
        self.derived_last_ts[pair] = ts_ms
        for derived in self.derived_aggrs:
            try:
                derived.update_from_candle(pair, ts_ms, candle)
                self.stats['total_derived_updates'] += 1
            except Exception as e:
                logger.error(f"[{pair}] 합성 봉 업데이트 에러 ({derived.timeframe_ms}ms): {e}")