# ohlcv_writer.py
import sqlite3
import threading
import time
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
    
    def __init__(self, db_path: str = None, batch_size: int = 100):
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
        
        # DB 초기화
        self._init_db()
    
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
            timeout=10.0  # 타임아웃 설정
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
            table = self._table_name(pair)
            
            with self.lock:
                # 테이블 생성 (캐싱으로 빠름)
                self._create_table_if_not_exists(table)
                
                # [개선12] UPSERT 문법 개선
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
                
                self.conn.execute(
                    sql,
                    (
                        ts,
                        candle["open"],
                        candle["high"],
                        candle["low"],
                        candle["close"],
                        candle["volume"],
                        timeframe_ms,
                    )
                )
                
                # [개선13] 배치 카운터 증가
                self.batch_count += 1
                
                # [개선14] 배치 단위로만 commit
                if self.batch_count >= self.batch_size:
                    self.conn.commit()
                    logger.debug(f"배치 커밋: {self.batch_count}건")
                    self.batch_count = 0
                    
        except sqlite3.Error as e:
            logger.error(f"데이터 저장 에러 [{pair}@{ts}]: {e}")
        except Exception as e:
            logger.error(f"예상치 못한 에러 [{pair}@{ts}]: {e}")
    
    def commit(self):
        """
        [개선15] 명시적 commit 메서드
        이유: 종료 시 강제 commit 필요
        """
        with self.lock:
            try:
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
        logger.info("OHLCVWriter 종료 중...")
        
        try:
            # 남은 배치 commit
            self.commit()
            
            # 연결 종료
            if self.conn:
                with self.lock:
                    self.conn.close()
                logger.info("DB 연결 종료 완료")
                
        except Exception as e:
            logger.error(f"종료 에러: {e}")
    
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
            if hasattr(self, 'conn') and self.conn:
                self.close()
        except:
            pass