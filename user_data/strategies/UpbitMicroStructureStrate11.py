# UpbitMicroStructureStrategy.py
# pragma pylint: disable=missing-docstring, invalid-name

import sqlite3
from pathlib import Path
import pandas as pd
import logging
from freqtrade.strategy import IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)


class UpbitMicroStructureStrategy(IStrategy):
    """
    업비트 초단기(0.5초 / 1초 / 3틱봉) 데이터를 직접 SQLite에서 읽어 사용하는 Strategy
    
    [] 로깅 추가
    이유: 디버깅 및 모니터링
    """
    
    # =====================================================
    # freqtrade 기본 설정
    # =====================================================
    timeframe = "1m"  # freqtrade에게는 "형식상" 타임프레임만 제공
    
    # 초단기 전략이므로 ROI, 손절은 Strategy에서 직접 제어
    minimal_roi = {"0": 0.01}
    stoploss = -0.02
    
    process_only_new_candles = True
    startup_candle_count = 1
    
    # =====================================================
    # DB 관련 설정
    # =====================================================
    DB_PATH = Path(__file__).resolve().parents[1] / "upbit_exchange" / "ohlcv.sqlite"
    
    # =====================================================
    # 공통 유틸 함수
    # =====================================================
    def _load_ohlcv(
        self,
        pair: str,
        timeframe_ms: int,
        limit: int = 200
    ) -> DataFrame:
        """
        SQLite에서 특정 pair + timeframe 데이터를 읽어오는 함수
        
        [] pandas 에러 모두 처리
        이유: 에러 발생 시 빈 DataFrame 반환하여 전략 중단 방지
        
        timeframe_ms:
        - 500 → 0.5초봉
        - 1000 → 1초봉
        - -3 → 3틱봉
        """
        try:
            # [] pair 형식 검증
            # 이유: 잘못된 형식으로 인한 에러 방지
            if '/' not in pair:
                logger.error(f"잘못된 pair 형식: {pair}")
                return pd.DataFrame()
            
            # freqtrade pair: ETH/KRW
            # DB table name : ohlcv_KRW_ETH
            parts = pair.replace('-', '/').split('/')
            if len(parts) != 2:
                logger.error(f"pair 파싱 실패: {pair}")
                return pd.DataFrame()
            
            base, quote = parts
            table = f"ohlcv_{quote}_{base}"
            
            # [] DB 연결 에러 처리
            try:
                with sqlite3.connect(self.DB_PATH) as conn:
                    # 1️⃣ 테이블 존재 여부 체크
                    check_sql = """
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name=?
                    """
                    result = conn.execute(check_sql, (table,)).fetchone()
                    
                    if not result:
                        logger.warning(f"테이블 없음: {table}")
                        return pd.DataFrame()
                    
                    # 2️⃣ 실제 데이터 로드
                    sql = f"""
                    SELECT ts, open, high, low, close, volume
                    FROM {table}
                    WHERE timeframe_ms = ?
                    ORDER BY ts DESC
                    LIMIT ?
                    """
                    
                    # [] pd.read_sql_query 에러 처리
                    # 이유: pandas SQL 관련 에러 방지
                    try:
                        df = pd.read_sql_query(
                            sql,
                            conn,
                            params=(timeframe_ms, limit),
                        )
                    except pd.errors.DatabaseError as e:
                        logger.error(f"SQL 실행 에러 [{table}]: {e}")
                        return pd.DataFrame()
                    
                    # [] 빈 DataFrame 체크
                    if df.empty:
                        logger.debug(f"데이터 없음 [{table}@{timeframe_ms}ms]")
                        return df
                    
                    # [] 필수 컬럼 검증
                    # 이유: 컬럼 누락으로 인한 에러 방지
                    required_cols = ['ts', 'open', 'high', 'low', 'close', 'volume']
                    if not all(col in df.columns for col in required_cols):
                        logger.error(f"필수 컬럼 누락 [{table}]: {df.columns.tolist()}")
                        return pd.DataFrame()
                    
                    # [] datetime 변환 에러 처리
                    # 이유: pandas to_datetime 에러 방지
                    try:
                        df["date"] = pd.to_datetime(df["ts"], unit="ms", errors='coerce')
                        
                        # NaT 값 제거 (잘못된 timestamp)
                        if df["date"].isna().any():
                            logger.warning(f"잘못된 timestamp 발견, 제거 중...")
                            df = df.dropna(subset=['date'])
                            
                    except Exception as e:
                        logger.error(f"datetime 변환 에러 [{table}]: {e}")
                        return pd.DataFrame()
                    
                    # [] 정렬 에러 처리
                    # 이유: pandas sort_values 에러 방지
                    try:
                        df = df.sort_values("ts").reset_index(drop=True)
                    except Exception as e:
                        logger.error(f"정렬 에러 [{table}]: {e}")
                        return pd.DataFrame()
                    
                    logger.debug(f"데이터 로드 완료 [{table}@{timeframe_ms}ms]: {len(df)}건")
                    return df
                    
            except sqlite3.Error as e:
                logger.error(f"DB 연결 에러: {e}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"_load_ohlcv 예상치 못한 에러: {e}", exc_info=True)
            return pd.DataFrame()
    
    # =====================================================
    # Indicator 생성
    # =====================================================
    def populate_indicators(
        self,
        dataframe: DataFrame,
        metadata: dict
    ) -> DataFrame:
        """
        freqtrade가 주기적으로 호출하는 함수
        여기서 우리가 만든 초단기 데이터를 직접 읽는다
        
        [] 전체 에러 처리 강화
        이유: 어떤 에러가 발생해도 전략이 중단되지 않도록
        """
        try:
            # 🔒 컬럼 기본값 초기화 (중요)
            dataframe["mom_500ms"] = 0.0
            dataframe["range_1s"] = 0.0
            dataframe["vol_3tick"] = 0.0
            
            pair = metadata.get("pair")
            if not pair:
                logger.error("pair 정보 없음")
                return dataframe
            
            # -------------------------------------------------
            # 0.5초봉 로드
            # -------------------------------------------------
            try:
                df_500ms = self._load_ohlcv(
                    pair=pair,
                    timeframe_ms=500,
                    limit=120
                )
                
                # [] 빈 DataFrame 처리
                if not df_500ms.empty and len(df_500ms) > 0:
                    # [] pandas 연산 에러 처리
                    # 이유: SettingWithCopyWarning 등 pandas 경고/에러 방지
                    try:
                        df_500ms = df_500ms.copy()  # 복사본 생성
                        df_500ms["momentum"] = df_500ms["close"] - df_500ms["open"]
                        
                        # 최신 값 전달
                        dataframe.loc[:, "mom_500ms"] = df_500ms.iloc[-1]["momentum"]
                    except Exception as e:
                        logger.error(f"0.5초봉 처리 에러: {e}")
                        
            except Exception as e:
                logger.error(f"0.5초봉 로드 에러: {e}")
            
            # -------------------------------------------------
            # 1초봉 로드
            # -------------------------------------------------
            try:
                df_1s = self._load_ohlcv(
                    pair=pair,
                    timeframe_ms=1000,
                    limit=120
                )
                
                if not df_1s.empty and len(df_1s) > 0:
                    try:
                        df_1s = df_1s.copy()
                        df_1s["range"] = df_1s["high"] - df_1s["low"]
                        
                        dataframe.loc[:, "range_1s"] = df_1s.iloc[-1]["range"]
                    except Exception as e:
                        logger.error(f"1초봉 처리 에러: {e}")
                        
            except Exception as e:
                logger.error(f"1초봉 로드 에러: {e}")
            
            # -------------------------------------------------
            # 3틱봉 로드
            # -------------------------------------------------
            try:
                df_3tick = self._load_ohlcv(
                    pair=pair,
                    timeframe_ms=-3,
                    limit=120
                )
                
                if not df_3tick.empty and len(df_3tick) > 0:
                    try:
                        df_3tick = df_3tick.copy()
                        
                        # [] rolling 계산 에러 처리
                        # 이유: 데이터 부족 시 에러 방지
                        if len(df_3tick) >= 5:
                            df_3tick["vol_ma"] = df_3tick["volume"].rolling(5).mean()
                            
                            # NaN 값 처리
                            if not pd.isna(df_3tick.iloc[-1]["vol_ma"]):
                                dataframe.loc[:, "vol_3tick"] = df_3tick.iloc[-1]["vol_ma"]
                        else:
                            logger.debug("3틱봉 데이터 부족 (< 5건)")
                            
                    except Exception as e:
                        logger.error(f"3틱봉 처리 에러: {e}")
                        
            except Exception as e:
                logger.error(f"3틱봉 로드 에러: {e}")
            
            return dataframe
            
        except Exception as e:
            logger.error(f"populate_indicators 치명적 에러: {e}", exc_info=True)
            
            # [] 에러 발생 시에도 기본 dataframe 반환
            # 이유: freqtrade가 중단되지 않도록
            if "mom_500ms" not in dataframe.columns:
                dataframe["mom_500ms"] = 0.0
            if "range_1s" not in dataframe.columns:
                dataframe["range_1s"] = 0.0
            if "vol_3tick" not in dataframe.columns:
                dataframe["vol_3tick"] = 0.0
            
            return dataframe
    
    # =====================================================
    # 진입 조건
    # =====================================================
    def populate_entry_trend(
        self,
        dataframe: DataFrame,
        metadata: dict
    ) -> DataFrame:
        """
        매수(진입) 조건
        
        [] 안전한 비교 연산
        이유: NaN, Inf 값으로 인한 에러 방지
        """
        try:
            # [] rolling 계산 에러 처리
            # 이유: 데이터 부족 시 에러 방지
            if len(dataframe) >= 10:
                range_ma = dataframe["range_1s"].rolling(10).mean()
                vol_ma = dataframe["vol_3tick"].rolling(10).mean()
                
                # [] 조건 검사 시 NaN 체크
                # 이유: pandas 비교 연산 에러 방지
                dataframe.loc[
                    (
                        (dataframe["mom_500ms"] > 0) &
                        (dataframe["range_1s"] > range_ma) &
                        (dataframe["vol_3tick"] > vol_ma) &
                        # NaN이 아닌 값만
                        (~dataframe["mom_500ms"].isna()) &
                        (~dataframe["range_1s"].isna()) &
                        (~dataframe["vol_3tick"].isna())
                    ),
                    "enter_long"
                ] = 1
            else:
                logger.debug("진입 조건: 데이터 부족 (< 10건)")
                
        except Exception as e:
            logger.error(f"populate_entry_trend 에러: {e}")
        
        return dataframe
    
    # =====================================================
    # 청산 조건
    # =====================================================
    def populate_exit_trend(
        self,
        dataframe: DataFrame,
        metadata: dict
    ) -> DataFrame:
        """
        매도(청산) 조건
        
        [] 안전한 청산 조건
        """
        try:
            # [] NaN 체크 추가
            dataframe.loc[
                (
                    (dataframe["mom_500ms"] < 0) &
                    (~dataframe["mom_500ms"].isna())
                ),
                "exit_long"
            ] = 1
            
        except Exception as e:
            logger.error(f"populate_exit_trend 에러: {e}")
        
        return dataframe
