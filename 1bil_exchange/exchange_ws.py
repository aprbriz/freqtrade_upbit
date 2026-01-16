import asyncio
import logging
import time
from copy import deepcopy
from functools import partial
from threading import Thread
import ccxt
from freqtrade.constants import Config, PairWithTimeframe
from freqtrade.enums.candletype import CandleType
from freqtrade.exceptions import TemporaryError
from freqtrade.exchange.common import retrier
from freqtrade.exchange.exchange import timeframe_to_seconds
from freqtrade.exchange.exchange_types import OHLCVResponse
from freqtrade.util import dt_ts, format_ms_time, format_ms_time_det

logger = logging.getLogger(__name__)

class ExchangeWS:
    def __init__(self, config: Config, ccxt_object: ccxt.Exchange) -> None:
        self.config = config
        self._ccxt_object = ccxt_object
        
        # 비동기 작업(Task)들과 수집 중인 코인(Klines) 목록 관리
        self._background_tasks: set[asyncio.Task] = set()
        self._klines_watching: set[PairWithTimeframe] = set()
        self._klines_scheduled: set[PairWithTimeframe] = set()
        
        # 마지막 갱신 시간 및 요청 시간 기록 (데이터 신선도 체크용)
        self.klines_last_refresh: dict[PairWithTimeframe, float] = {}
        self.klines_last_request: dict[PairWithTimeframe, float] = {}
        
        # 웹소켓은 별도의 전용 스레드("ccxt_ws")에서 백그라운드로 실행됨
        self._thread = Thread(name="ccxt_ws", target=self._start_forever)
        self._thread.start()
        self.__cleanup_called = False

    def _start_forever(self) -> None:
        """별도 스레드 내에서 비동기 이벤트 루프를 생성하고 무한 실행함"""
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_forever()
        finally:
            if self._loop.is_running():
                self._loop.stop()

    def cleanup(self) -> None:
        """프로그램 종료 시 모든 연결을 닫고 자원을 정리함"""
        logger.debug("정리 작업(Cleanup) 시작 - 중단 프로세스 중")
        self._klines_watching.clear()
        
        # 실행 중인 모든 백그라운드 태스크 취소
        for task in self._background_tasks:
            task.cancel()
            
        if hasattr(self, "_loop") and not self._loop.is_closed():
            self.reset_connections()
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        time.sleep(0.1)
        if not self._loop.is_closed():
            self._loop.close()
        
        self._thread.join() # 스레드가 종료될 때까지 대기
        logger.debug("정리 완료 - 중단됨")

    def reset_connections(self) -> None:
        """
        연결 초기화 - 약 9일 정도 운영 시 발생하는 'Connection-Reset' 에러 방지
        """
        if hasattr(self, "_loop") and not self._loop.is_closed():
            logger.info("웹소켓(WS) 연결을 초기화합니다.")
            asyncio.run_coroutine_threadsafe(self._cleanup_async(), loop=self._loop)
            
            while not self.__cleanup_called:
                time.sleep(0.1)
            self.__cleanup_called = False

    async def _cleanup_async(self) -> None:
        """비동기 방식으로 CCXT 세션을 닫고 캐시를 비움"""
        try:
            await self._ccxt_object.close()
            # 캐시를 비워줍니다. 비우지 않으면 다이내믹 페어리스트 시작 시 문제가 생길 수 있습니다.
            self._ccxt_object.ohlcvs.clear()
        except Exception:
            logger.exception("_cleanup_async 실행 중 예외 발생")
        finally:
            self.__cleanup_called = True

    def _pop_history(self, paircomb: PairWithTimeframe) -> None:
        """CCXT 캐시에서 특정 심볼/시간대 조합의 과거 데이터를 삭제함"""
        self._ccxt_object.ohlcvs.get(paircomb[0], {}).pop(paircomb[1], None)
        self.klines_last_refresh.pop(paircomb, None)


    @retrier(retries=3) # 에러 발생 시 최대 3번까지 자동으로 재시도합니다.
    def ohlcvs(self, pair: str, timeframe: str) -> list[list]:
        """
        특정 심볼/시간대의 캔들 데이터 복사본을 반환합니다.
        참고: 웹소켓 수신 데이터만 포함되므로 시간이 지날수록 축적됩니다.
        """
        try:
            # 웹소켓 스레드가 원본 리스트를 수정하는 도중 읽으면 에러가 날 수 있으므로
            # deepcopy로 그 순간의 '스냅샷'을 찍어 안전하게 가져옵니다.
            return deepcopy(self._ccxt_object.ohlcvs.get(pair, {}).get(timeframe, []))
        except RuntimeError as e:
            # 복사 도중 데이터가 변해 발생한 런타임 에러를 포착합니다.
            # TemporaryError를 던지면 @retrier가 대기 시간 없이 '즉시' 재시도를 수행합니다.
            raise TemporaryError(f"데이터 복사 중 충돌 발생(즉시 재시도): {e}") from e


    def cleanup_expired(self) -> None:
        """
        최근 일정 시간 동안 요청이 없었던 심볼은 감시 목록에서 제외하여 자원을 아낌
        """
        changed = False
        for p in list(self._klines_watching):
            _, timeframe, _ = p
            timeframe_s = timeframe_to_seconds(timeframe)
            last_refresh = self.klines_last_request.get(p, 0)
            
            # 마지막 요청으로부터 (봉 시간 + 20초) 이상 지났으면 삭제
            if last_refresh > 0 and (dt_ts() - last_refresh) > ((timeframe_s + 20) * 1000):
                logger.info(f"웹소켓 감시 목록에서 {p}를 제거합니다.")
                self._klines_watching.discard(p)
                self._pop_history(p) # 메모리 절약을 위해 과거 기록도 삭제
                changed = True
        
        if changed:
            logger.info(f"제거 작업 완료: 현재 감시 중인 코인 수 ({len(self._klines_watching)})")

    async def _schedule_while_true(self) -> None:
        """감시 목록에 있는 코인 중 아직 실행 중이 아닌 태스크를 비동기로 시작함"""
        for p in self._klines_watching:
            if p not in self._klines_scheduled:
                self._klines_scheduled.add(p)
                pair, timeframe, candle_type = p
                
                # 실시간 캔들 수집 워커 시작
                task = asyncio.create_task(
                    self._continuously_async_watch_ohlcv(pair, timeframe, candle_type)
                )
                self._background_tasks.add(task)
                
                # 작업 종료 시 실행될 콜백 등록
                task.add_done_callback(
                    partial(
                        self._continuous_stopped,
                        pair=pair, timeframe=timeframe, candle_type=candle_type,
                    )
                )

    async def _unwatch_ohlcv(self, pair: str, timeframe: str, candle_type: CandleType) -> None:
        """웹소켓 서버에 더 이상 해당 코인 데이터를 보내지 말라고 요청함"""
        try:
            await self._ccxt_object.un_watch_ohlcv_for_symbols([[pair, timeframe]])
        except ccxt.NotSupported as e:
            logger.debug("해당 거래소가 un_watch_ohlcv_for_symbols 기능을 지원하지 않음: %s", e)
        except Exception:
            logger.exception("_unwatch_ohlcv 실행 중 에러")

    def _continuous_stopped(self, task: asyncio.Task, pair: str, timeframe: str, candle_type: CandleType):
        """수집 작업이 중단되었을 때 상태를 정리함"""
        self._background_tasks.discard(task)
        
        result = "완료"
        if task.cancelled():
            result = "취소됨"
        else:
            if (res := task.result()) is not None:
                result = str(res)
        
        logger.info(f"{pair}, {timeframe} - 수집 작업 종료 - 상태: {result}")
        
        # 거래소 연결 해제 시도
        asyncio.run_coroutine_threadsafe(
            self._unwatch_ohlcv(pair, timeframe, candle_type),
            loop=self._loop
        )
        self._klines_scheduled.discard((pair, timeframe, candle_type))
        self._pop_history((pair, timeframe, candle_type))

    async def _continuously_async_watch_ohlcv(self, pair: str, timeframe: str, candle_type: CandleType) -> None:
        """실제로 CCXT 웹소켓을 호출하여 실시간 데이터를 무한히 받아오는 핵심 루프"""
        try:
            while (pair, timeframe, candle_type) in self._klines_watching:
                start = dt_ts()
                # 거래소로부터 실시간 데이터를 기다림 (blocking 아님)
                data = await self._ccxt_object.watch_ohlcv(pair, timeframe)
                self.klines_last_refresh[(pair, timeframe, candle_type)] = dt_ts()
                
                logger.debug(
                    f"수신 완료 {pair}, {timeframe}, 데이터 {len(data)}개 "
                    f"소요시간: {(dt_ts() - start) / 1000:.3f}초"
                )
        except ccxt.ExchangeClosedByUser:
            logger.debug("사용자에 의해 거래소 연결이 닫혔습니다.")
        except ccxt.BaseError:
            logger.exception(f"{pair}, {timeframe} 수집 루프 중 CCXT 기본 에러 발생")
        finally:
            # 에러가 나거나 루프를 빠져나오면 감시 목록에서 제거
            self._klines_watching.discard((pair, timeframe, candle_type))

    def schedule_ohlcv(self, pair: str, timeframe: str, candle_type: CandleType) -> None:
        """새로운 코인/시간대를 감시 목록에 등록하고 수집 스케줄을 실행함"""
        self._klines_watching.add((pair, timeframe, candle_type))
        self.klines_last_request[(pair, timeframe, candle_type)] = dt_ts()
        
        # 메인 스레드에서 비동기 루프의 스케줄러 실행
        asyncio.run_coroutine_threadsafe(self._schedule_while_true(), loop=self._loop)
        
        # 만료된 코인 정리
        self.cleanup_expired()

    async def get_ohlcv(self, pair: str, timeframe: str, candle_type: CandleType, candle_ts: int) -> OHLCVResponse:
        """
        CCXT의 웹소켓 캐시에 저장된 실시간 캔들 데이터를 가져옵니다.
        :param candle_ts: 우리가 기대하는 캔들의 종료 시점 타임스탬프
        """
        # 웹소켓으로 실시간 수집 중인 데이터의 복사본을 가져옴
        candles = self.ohlcvs(pair, timeframe)
        refresh_date = self.klines_last_refresh[(pair, timeframe, candle_type)]
        
        received_ts = candles[-1][0] if candles else 0
        drop_hint = received_ts >= candle_ts # 기대하는 시간만큼 데이터가 쌓였는지 확인
        
        # 데이터 시간과 수신 시간이 맞지 않으면 경고 (시스템 시계 불일치 문제 등)
        if received_ts > refresh_date:
            logger.warning(
                f"{pair}, {timeframe} - 캔들 시간이 마지막 갱신 시간보다 앞섬 "
                f"({format_ms_time(received_ts)} > {format_ms_time_det(refresh_date)}). "
                "일반적으로 시간 동기화(Sync) 문제일 가능성이 높습니다."
            )
            
        return pair, timeframe, candle_type, candles, drop_hint
