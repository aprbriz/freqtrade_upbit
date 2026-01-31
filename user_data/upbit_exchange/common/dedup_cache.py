# dedup_cache.py
# 중복 제거 캐시 (POL-006 구현)

import threading
from collections import defaultdict, deque


class DedupCache:
    """
    trade 이벤트 중복 제거 캐시
    - trade_uuid → sequential_id → fallback 우선순위
    - market별 최근 N=20,000 이벤트 보관
    """
    
    def __init__(self, max_size: int = 20000):
        self.max_size = max_size
        self.recent = defaultdict(deque)
        self.recent_set = defaultdict(set)
        self.lock = threading.Lock()

    def add_and_check(self, pair: str, key) -> bool:
        """
        키 추가 및 중복 체크
        Returns: True if duplicate, False if new
        """
        with self.lock:
            bucket = self.recent_set[pair]
            if key in bucket:
                return True
            bucket.add(key)
            self.recent[pair].append(key)
            if len(self.recent[pair]) > self.max_size:
                old = self.recent[pair].popleft()
                bucket.discard(old)
            return False

    def reset(self):
        """전체 캐시 초기화 (generation 전환 시)"""
        with self.lock:
            self.recent.clear()
            self.recent_set.clear()
