# reconnect_limiter.py
# 전역 재연결 레이트 리미터 (POL-004, P2-REQ-010 구현)

import time
import threading
from collections import deque


class GlobalReconnectLimiter:
    """
    전역 재연결 레이트 리미터
    - 최대 1회/초, 30회/분
    - 모든 Collector가 공유
    """
    
    def __init__(self, per_second: int = 1, per_minute: int = 30):
        self.per_second = per_second
        self.per_minute = per_minute
        self.lock = threading.Lock()
        self.attempts = deque()

    def wait_for_slot(self, shutdown_event: threading.Event) -> bool:
        """
        재연결 슬롯 대기
        Returns: True if slot acquired, False if shutdown
        """
        while True:
            now = time.time()
            with self.lock:
                # 60초 이상 지난 기록 제거
                while self.attempts and now - self.attempts[0] > 60:
                    self.attempts.popleft()
                
                # 초당 제한 체크
                second_wait = 0.0
                if self.attempts:
                    second_wait = max(0.0, 1.0 - (now - self.attempts[-1]))
                
                # 분당 제한 체크
                minute_wait = 0.0
                if len(self.attempts) >= self.per_minute:
                    minute_wait = max(0.0, 60.0 - (now - self.attempts[0]))
                
                wait_for = max(second_wait, minute_wait)
                if wait_for <= 0:
                    self.attempts.append(now)
                    return True
            
            # 대기 중 shutdown 체크
            if shutdown_event.wait(timeout=wait_for):
                return False
