# ohlcv_writer.py
import sqlite3
import threading
import time
import queue
import random
from pathlib import Path
import logging

logger = logging.getLogger("ohlcv-writer")


class OHLCVWriter:
    """
    OHLCV 데이터를 SQLite DB에 저장하는 클래스
    - pair 별 테이블 사용
    - PRIMARY KEY (ts)
    - 0.5초봉, 1초봉 등은 timeframe_ms 컬럼으로 구분
    """
    
    def __init__(
        self,
        db_path: str = None,
        batch_size: int = 100,
        queue_high_watermark: int = 8000,
        queue_hard_limit: int = 10000,
        retry_base_delay: float = 0.05,
        retry_max_delay: float = 2.0,
        retry_jitter_max: float = 0.05,
        retry_total_timeout: float = 10.0,
    ):
        """
        [개선1] 배치 처리 추가
        이유: 성능 향상 (매번 commit하지 않음)
        """
        # DB 파일 위치
        if db_path is None:
            self.db_path = Path(__file__).resolve().parent / "ohlcv.sqlite"
        else:
            self.db_path = Path(db_path)
        
        # SQLite는 멀티스레드에 약하므로 Lock 사용
        self.lock = threading.Lock()
        
        # [개선2] 배치 처리 관련 변수
        self.batch_size = batch_size
        self.batch_count = 0
        
        # [개선3] 연결 객체를 인스턴스 변수로 유지
        # 이유: 매번 연결/해제하면 느림
        self.conn = None
        self.closed = False
        self.close_lock = threading.Lock()

        # Writer 큐 설정 (오버로드 보호)
        self.queue_high_watermark = max(1, int(queue_high_watermark))
        self.queue_hard_limit = max(self.queue_high_watermark, int(queue_hard_limit))
        self.write_queue = queue.Queue(maxsize=self.queue_hard_limit)
        self.queue_overload_event = threading.Event()
        self.queue_degraded_event = threading.Event()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.worker_done_event = threading.Event()

        # DB locked/busy 재시도 정책
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.retry_jitter_max = retry_jitter_max
        self.retry_total_timeout = retry_total_timeout
        
        # [개선3-2] 데이터 정합성 통계
        self.stats = {
            'invalid_writes': 0,
            'out_of_order_writes': 0,
            'locked_retries': 0,
            'locked_timeouts': 0,
        }
        self.last_ts = {}
        self.invalid_log_interval = 60.0
        self.last_invalid_log_ts = 0.0
        self.last_order_log_ts = 0.0
        self.last_write_ts = None
        
        # DB 초기화
        self._init_db()
        self._start_worker()
    
    # =========================================================
    # DB 초기화
    # =========================================================
    def _init_db(self):
        """
        DB 파일 및 기본 설정 초기화
        
        [개선4] 연결 재사용
        이유: 성능 향상
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # [개선5] 연결 생성 및 유지
        self.conn = self._create_connection()
        
        with self.lock:
            # SQLite 성능 튜닝 옵션
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA temp_store=MEMORY;")
            # [개선6] 캐시 크기 증가 (10MB)
            self.conn.execute("PRAGMA cache_size=-10000;")
            self.conn.commit()
        
        logger.info(f"DB 초기화 완료: {self.db_path}")
    
    def _create_connection(self):
        """
        [개선7] 연결 생성 로직 분리
        이유: 재사용 가능
        """
        return sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=1.0  # 타임아웃 설정 (Writer 재시도 정책과 조합)
        )
    
    # =========================================================
    # 테이블 관련
    # =========================================================
    def _table_name(self, pair: str) -> str:
        """
        pair 이름을 테이블 이름으로 변환
        예) KRW-BTC → ohlcv_KRW_BTC
        """
        return f"ohlcv_{pair.replace('-', '_')}"
    
    def _create_table_if_not_exists(self, table: str):
        """
        [개선8] 테이블 생성 시 conn 파라미터 제거
        이유: 인스턴스 변수 사용
        """
        # [개선9] 테이블 존재 여부 캐싱
        # 이유: 매번 체크하면 느림
        if not hasattr(self, '_table_cache'):
            self._table_cache = set()
        
        if table in self._table_cache:
            return
        
        sql = f"""
        CREATE TABLE IF NOT EXISTS {table} (
            ts INTEGER PRIMARY KEY,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            timeframe_ms INTEGER NOT NULL
        );
        """
        self.conn.execute(sql)
        
        # ts + timeframe 조회 성능용 인덱스
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_tf "
            f"ON {table}(timeframe_ms, ts DESC);"
        )
        
        # [개선10] 캐시에 추가
        self._table_cache.add(table)
        self.conn.commit()
    
    # =========================================================
    # 데이터 저장
    # =========================================================
    def write(self, pair: str, ts: int, timeframe_ms: int, candle: dict):
        """
        OHLCV 1건 저장
        
        [개선11] 배치 처리 및 에러 처리 강화
        """
        try:
            if self.closed or self.stop_event.is_set():
                return
            if not self._validate_candle(pair, ts, timeframe_ms, candle):
                return
            item = (pair, ts, timeframe_ms, candle.copy())
            self._enqueue_write(item)
        except sqlite3.Error as e:
            logger.error(f"데이터 저장 에러 [{pair}@{ts}]: {e}")
        except Exception as e:
            logger.error(f"예상치 못한 에러 [{pair}@{ts}]: {e}")

    def _validate_candle(self, pair: str, ts: int, timeframe_ms: int, candle: dict) -> bool:
        """
        데이터 정합성 검증
        """
        try:
            if ts is None or ts <= 0:
                self._log_invalid(f"[{pair}] 잘못된 ts: {ts}")
                return False
            if timeframe_ms is None or not isinstance(timeframe_ms, int):
                self._log_invalid(f"[{pair}] 잘못된 timeframe_ms: {timeframe_ms}")
                return False
            required_keys = ("open", "high", "low", "close", "volume")
            for key in required_keys:
                if key not in candle:
                    self._log_invalid(f"[{pair}] candle 누락 키: {key}")
                    return False
            if candle["open"] <= 0 or candle["high"] <= 0 or candle["low"] <= 0 or candle["close"] <= 0:
                self._log_invalid(f"[{pair}] 잘못된 가격: {candle}")
                return False
            if candle["volume"] < 0:
                self._log_invalid(f"[{pair}] 잘못된 볼륨: {candle}")
                return False
            return True
        except Exception as e:
            self._log_invalid(f"[{pair}] 검증 실패: {e}")
            return False

    def _check_ts_order(self, table: str, timeframe_ms: int, ts: int):
        """
        타임스탬프 순서 검증 (경고만)
        """
        key = f"{table}:{timeframe_ms}"
        last_ts = self.last_ts.get(key)
        if last_ts is not None and ts < last_ts:
            self.stats['out_of_order_writes'] += 1
            self._log_order(f"[{table}] ts 역전 감지: last={last_ts}, now={ts}")
        self.last_ts[key] = max(ts, last_ts or ts)

    def _log_invalid(self, message: str):
        self.stats['invalid_writes'] += 1
        now = time.time()
        if now - self.last_invalid_log_ts >= self.invalid_log_interval:
            logger.warning(message)
            self.last_invalid_log_ts = now

    def _log_order(self, message: str):
        now = time.time()
        if now - self.last_order_log_ts >= self.invalid_log_interval:
            logger.warning(message)
            self.last_order_log_ts = now

    def _start_worker(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        self.worker_done_event.clear()
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name="ohlcv-writer-worker",
            daemon=True,
        )
        self.worker_thread.start()

    def _enqueue_write(self, item):
        last_log_ts = 0.0
        while not self.stop_event.is_set() and not self.closed:
            try:
                self.write_queue.put(item, timeout=0.5)
                return
            except queue.Full:
                self.queue_overload_event.set()
                now = time.time()
                if now - last_log_ts >= 5.0:
                    logger.warning(
                        f"Writer 큐 포화 (depth={self.write_queue.qsize()}, "
                        f"hard_limit={self.queue_hard_limit})"
                    )
                    last_log_ts = now

    def _worker_loop(self):
        try:
            while True:
                if self.stop_event.is_set() and self.write_queue.empty():
                    break
                try:
                    item = self.write_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    pair, ts, timeframe_ms, candle = item
                    self._write_one(pair, ts, timeframe_ms, candle)
                finally:
                    self.write_queue.task_done()
        finally:
            try:
                self.commit()
            except Exception as e:
                logger.error(f"Writer 종료 commit 에러: {e}")
            self.worker_done_event.set()

    def _write_one(self, pair: str, ts: int, timeframe_ms: int, candle: dict):
        table = self._table_name(pair)
        self._check_ts_order(table, timeframe_ms, ts)

        sql = f"""
        INSERT INTO {table}
        (ts, open, high, low, close, volume, timeframe_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ts) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            timeframe_ms = excluded.timeframe_ms
        """
        params = (
            ts,
            candle["open"],
            candle["high"],
            candle["low"],
            candle["close"],
            candle["volume"],
            timeframe_ms,
        )

        start = time.time()
        delay = self.retry_base_delay
        while not self.stop_event.is_set() and not self.closed:
            try:
                with self.lock:
                    if not self.conn:
                        return
                    self._create_table_if_not_exists(table)
                    self.conn.execute(sql, params)
                    self.batch_count += 1
                    if self.batch_count >= self.batch_size:
                        self.conn.commit()
                        self.batch_count = 0
                self.last_write_ts = time.time()
                if self.queue_degraded_event.is_set():
                    if self.get_queue_depth() < self.queue_high_watermark:
                        self.queue_degraded_event.clear()
                return
            except sqlite3.OperationalError as e:
                if not self._is_locked_error(e):
                    logger.error(f"데이터 저장 에러 [{pair}@{ts}]: {e}")
                    return
                elapsed = time.time() - start
                if elapsed >= self.retry_total_timeout:
                    self.stats['locked_timeouts'] += 1
                    self.queue_degraded_event.set()
                    logger.error(
                        f"DB locked/busy 지속 (elapsed={elapsed:.1f}s, "
                        f"limit={self.retry_total_timeout}s)"
                    )
                    return
                self.stats['locked_retries'] += 1
                sleep_for = min(delay, self.retry_max_delay)
                sleep_for += random.uniform(0, self.retry_jitter_max)
                time.sleep(sleep_for)
                delay *= 2
            except sqlite3.Error as e:
                logger.error(f"데이터 저장 에러 [{pair}@{ts}]: {e}")
                return

    def _is_locked_error(self, error: Exception) -> bool:
        msg = str(error).lower()
        return "locked" in msg or "busy" in msg
    
    def commit(self):
        """
        [개선15] 명시적 commit 메서드
        이유: 종료 시 강제 commit 필요
        """
        with self.lock:
            try:
                if not self.conn:
                    return
                if self.batch_count > 0:
                    self.conn.commit()
                    logger.debug(f"강제 커밋: {self.batch_count}건")
                    self.batch_count = 0
            except sqlite3.Error as e:
                logger.error(f"커밋 에러: {e}")
    
    # =========================================================
    # 오래된 데이터 정리
    # =========================================================
    def cleanup_old_data(self, days: int = 365):
        """
        오래된 데이터 삭제
        
        [개선16] 에러 처리 강화
        """
        try:
            cutoff_ts = int((time.time() - days * 86400) * 1000)
            
            with self.lock:
                cursor = self.conn.cursor()
                
                # 모든 테이블 조회
                cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name LIKE 'ohlcv_%'
                """)
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    logger.info(f"데이터 정리: {table}, cutoff={cutoff_ts}")
                    
                    cursor.execute(
                        f"DELETE FROM {table} WHERE ts < ?",
                        (cutoff_ts,)
                    )
                    deleted = cursor.rowcount
                    logger.info(f"{table}: {deleted}건 삭제")
                
                self.conn.commit()
                logger.info("데이터 정리 완료")
                
        except sqlite3.Error as e:
            logger.error(f"데이터 정리 에러: {e}")
    
    def close(self):
        """
        [개선17] 연결 종료 메서드
        이유: 리소스 정리 및 마지막 commit
        """
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
        
        logger.info("OHLCVWriter 종료 중...")
        
        try:
            # 큐 처리 중단 및 drain 대기
            self.stop_event.set()
            deadline = time.time() + 10.0
            while time.time() < deadline:
                if self.write_queue.unfinished_tasks == 0:
                    break
                time.sleep(0.1)
            if self.write_queue.unfinished_tasks > 0:
                logger.warning(
                    f"Writer 큐 drain 타임아웃 (pending={self.write_queue.unfinished_tasks})"
                )

            if self.worker_thread and self.worker_thread.is_alive():
                wait_timeout = max(5.0, self.retry_total_timeout + 2.0)
                if not self.worker_done_event.wait(timeout=wait_timeout):
                    logger.error(f"Writer worker 종료 지연 (waited={wait_timeout:.1f}s)")
                self.worker_thread.join(timeout=1.0)

            if self.worker_thread and self.worker_thread.is_alive():
                logger.error("Writer worker 종료 실패 → 안전상 DB 종료 생략")
                return

            # 남은 배치 commit (worker 종료 이후)
            self.commit()
            
            # 연결 종료
            if self.conn:
                with self.lock:
                    self.conn.close()
                    self.conn = None
                logger.info("DB 연결 종료 완료")
                
        except Exception as e:
            logger.error(f"종료 에러: {e}")

    def get_stats(self) -> dict:
        """
        통계 조회
        """
        stats = self.stats.copy()
        stats['queue_depth'] = self.get_queue_depth()
        stats['queue_high_watermark'] = self.queue_high_watermark
        stats['queue_hard_limit'] = self.queue_hard_limit
        stats['last_write_ts'] = self.last_write_ts
        stats['queue_overloaded'] = self.queue_overload_event.is_set()
        stats['queue_degraded'] = self.queue_degraded_event.is_set()
        return stats

    def get_queue_depth(self) -> int:
        try:
            return self.write_queue.qsize()
        except Exception:
            return 0

    def is_overloaded(self) -> bool:
        return self.queue_overload_event.is_set()

    def is_degraded(self) -> bool:
        return self.queue_degraded_event.is_set()

    def clear_queue(self) -> int:
        cleared = 0
        while True:
            try:
                self.write_queue.get_nowait()
                self.write_queue.task_done()
                cleared += 1
            except queue.Empty:
                break
        if cleared:
            logger.warning(f"Writer 큐 강제 드레인: {cleared}건 폐기")
        return cleared
    
    def __enter__(self):
        """
        [개선18] 컨텍스트 매니저 지원
        """
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()
    
    def __del__(self):
        """
        [개선19] 소멸자
        이유: 안전한 종료
        """
        try:
            if getattr(self, "closed", False):
                return
            if hasattr(self, 'conn') and self.conn:
                self.close()
        except:
            pass