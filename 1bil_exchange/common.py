import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast, overload

from freqtrade.exceptions import DDosProtection, RetryableOrderError, TemporaryError
from freqtrade.mixins import LoggingMixin

# 로그를 기록하기 위한 설정입니다.
logger = logging.getLogger(__name__)
__logging_mixin = None


def _reset_logging_mixin():
    """
    글로벌 로깅 믹스인을 초기화합니다. 주로 테스트 용도로 사용됩니다.
    """
    global __logging_mixin
    __logging_mixin = LoggingMixin(logger)


def _get_logging_mixin():
    # Kucoin 거래소의 응답을 캐시하기 위한 로깅 믹스인을 가져옵니다.
    # 주로 재시도(retrier) 로직 내에서 사용됩니다.
    global __logging_mixin
    if not __logging_mixin:
        __logging_mixin = LoggingMixin(logger)
    return __logging_mixin


# 기본 재시도 횟수 설정 (총 실행 횟수는 이 값 + 1번이 됩니다)
API_RETRY_COUNT = 4
API_FETCH_ORDER_RETRY_COUNT = 5

# Freqtrade에서 사용하기에 부적합하거나 문제가 있는 거래소 목록입니다.
BAD_EXCHANGES = {
    "bitmex": "Various reasons.",
    "probit": "Requires additional, regular calls to `signIn()`.",
    "poloniex": "Does not provide fetch_order endpoint to fetch both open and closed orders.",
    "kucoinfutures": "Unsupported futures exchange.",
    "poloniexfutures": "Unsupported futures exchange.",
    "binancecoinm": "Unsupported futures exchange.",
}

# CCXT 라이브러리 내에서 이름이 바뀐 거래소들을 매핑합니다.
MAP_EXCHANGE_CHILDCLASS = {
    "okex": "okx",
    "gateio": "gate",
    "huboi": "htx",
}

# 공식적으로 지원하고 테스트된 거래소 목록입니다.
SUPPORTED_EXCHANGES = [
    "binance",
    "binanceus",
    "binanceusdm",
    "bingx",
    "bitmart",
    "bitget",
    "bybit",
    "gate",
    "htx",
    "hyperliquid",
    "kraken",
    "okx",
    "myokx",
]

# 거래소가 정상 작동하기 위해 반드시 가지고 있어야 하는 기능(메서드)들입니다.
EXCHANGE_HAS_REQUIRED: dict[str, list[str]] = {
    # 필수 기능 / 개인적인 기능 (계정 정보 등)
    "fetchOrder": ["fetchOpenOrder", "fetchClosedOrder"],
    "fetchL2OrderBook": ["fetchTicker"],
    "cancelOrder": [],
    "createOrder": [],
    "fetchBalance": [],
    # 공용 데이터 기능
    "fetchOHLCV": [],
}

# 있으면 좋지만 없어도 기본 동작은 가능한 선택적 기능들입니다.
EXCHANGE_HAS_OPTIONAL = [
    # 개인 기능
    "fetchMyTrades",  # 주문에 대한 체결 내역 및 수수료 확인
    "createLimitOrder",
    "createMarketOrder",  # 지정가 혹은 시장가 주문
    # 공용 기능
    "fetchOrderBook",
    "fetchL2OrderBook",
    "fetchTicker",  # 가격 확인용
    "fetchTickers",  # 여러 코인의 가격 확인용
    "fetchTrades",  # 과거 체결 내역 다운로드용
    # ccxt.pro (실시간 데이터 관련)
    "watchOHLCV",
]


def calculate_backoff(retrycount, max_retries):
    """
    재시도할 때마다 대기 시간을 점진적으로 늘리기 위한 계산 함수입니다. (지수 백오프)
    재시도 횟수가 남을수록 대기 시간이 길어집니다.
    """
    return (max_retries - retrycount) ** 2 + 1


def retrier_async(f):
    """
    비동기(async) 함수를 위한 재시도 데코레이터입니다.
    네트워크 오류 등이 발생했을 때 자동으로 다시 시도합니다.
    """
    async def wrapper(*args, **kwargs):
        # 실행 횟수를 설정에서 가져옵니다.
        count = kwargs.pop("count", API_RETRY_COUNT)
        kucoin = args[0].name == "KuCoin"  # 현재 거래소가 KuCoin인지 확인합니다.
        try:
            # 원래 함수를 실행합니다.
            return await f(*args, **kwargs)
        except TemporaryError as ex:
            # 일시적인 오류가 발생한 경우
            msg = f'{f.__name__}() returned exception: "{ex}". '
            if count > 0:
                msg += f"Retrying still for {count} times."
                count -= 1
                kwargs["count"] = count
                # 디도스 방지(DDosProtection)에 걸린 경우 대기 시간을 가집니다.
                if isinstance(ex, DDosProtection):
                    if kucoin and "429000" in str(ex):
                        # Kucoin 거래소의 특정 에러(429000)에 대한 예외 처리
                        _get_logging_mixin().log_once(
                            f"Kucoin 429 error, avoid triggering DDosProtection backoff delay. "
                            f"{count} tries left before giving up",
                            logmethod=logger.warning,
                        )
                        msg = ""
                    else:
                        # 일반적인 경우에는 대기 시간을 계산하여 잠시 쉽니다.
                        backoff_delay = calculate_backoff(count + 1, API_RETRY_COUNT)
                        logger.info(f"Applying DDosProtection backoff delay: {backoff_delay}")
                        await asyncio.sleep(backoff_delay)
                if msg:
                    logger.warning(msg)
                # 함수를 다시 실행(재귀 호출)합니다.
                return await wrapper(*args, **kwargs)
            else:
                # 재시도 횟수를 모두 소진하면 포기하고 에러를 발생시킵니다.
                logger.warning(msg + "Giving up.")
                raise ex

    return wrapper


F = TypeVar("F", bound=Callable[..., Any])


# 파이썬의 타입 힌트를 위한 설정들입니다 (함수 오버로딩).
@overload
def retrier(_func: F) -> F: ...


@overload
def retrier(_func: F, *, retries=API_RETRY_COUNT) -> F: ...


@overload
def retrier(*, retries=API_RETRY_COUNT) -> Callable[[F], F]: ...


def retrier(_func: F | None = None, *, retries=API_RETRY_COUNT):
    """
    일반(동기식) 함수를 위한 재시도 데코레이터입니다.
    사용법: @retrier 또는 @retrier(retries=5)
    """
    def decorator(f: F) -> F:
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 남은 재시도 횟수를 관리합니다.
            count = kwargs.pop("count", retries)
            try:
                # 실제 함수 실행
                return f(*args, **kwargs)
            except (TemporaryError, RetryableOrderError) as ex:
                # 일시적 오류나 재시도 가능한 주문 오류 발생 시
                msg = f'{f.__name__}() returned exception: "{ex}". '
                if count > 0:
                    logger.warning(msg + f"Retrying still for {count} times.")
                    count -= 1
                    kwargs.update({"count": count})
                    # 디도스 방지나 주문 에러인 경우 대기 시간을 가집니다.
                    if isinstance(ex, DDosProtection | RetryableOrderError):
                        backoff_delay = calculate_backoff(count + 1, retries)
                        logger.info(f"Applying DDosProtection backoff delay: {backoff_delay}")
                        time.sleep(backoff_delay)
                    # 다시 시도합니다.
                    return wrapper(*args, **kwargs)
                else:
                    # 끝내 에러가 해결되지 않으면 중단합니다.
                    logger.warning(msg + "Giving up.")
                    raise ex

        return cast(F, wrapper)

    # @retrier 형태로 썼을 때와 @retrier(retries=3) 형태로 썼을 때를 모두 지원합니다.
    if _func is None:
        return decorator
    else:
        return decorator(_func)
