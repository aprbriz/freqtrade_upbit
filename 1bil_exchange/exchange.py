# pragma pylint: disable=W0603
"""
Cryptocurrency Exchanges support
"""
import asyncio
import inspect
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import floor
from threading import Lock
from typing import Any, Coroutine, Dict, List, Literal, Optional, Tuple, Union

import arrow
import ccxt
import ccxt.async_support as ccxt_async
from cachetools import TTLCache
from ccxt import TICK_SIZE
from dateutil import parser
from pandas import DataFrame, concat

from freqtrade.constants import (DEFAULT_AMOUNT_RESERVE_PERCENT, NON_OPEN_EXCHANGE_STATES, BidAsk,
                                 BuySell, Config, EntryExit, ListPairsWithTimeframes, MakerTaker,
                                 OBLiteral, PairWithTimeframe)
from freqtrade.data.converter import clean_ohlcv_dataframe, ohlcv_to_dataframe, trades_dict_to_list
from freqtrade.enums import OPTIMIZE_MODES, CandleType, MarginMode, TradingMode
from freqtrade.enums.pricetype import PriceType
from freqtrade.exceptions import (DDosProtection, ExchangeError, InsufficientFundsError,
                                  InvalidOrderException, OperationalException, PricingError,
                                  RetryableOrderError, TemporaryError)
from freqtrade.exchange.common import (API_FETCH_ORDER_RETRY_COUNT, remove_credentials, retrier,
                                       retrier_async)
from freqtrade.exchange.exchange_utils import (ROUND, ROUND_DOWN, ROUND_UP, CcxtModuleType,
                                               amount_to_contract_precision, amount_to_contracts,
                                               amount_to_precision, contracts_to_amount,
                                               date_minus_candles, is_exchange_known_ccxt,
                                               market_is_active, price_to_precision,
                                               timeframe_to_minutes, timeframe_to_msecs,
                                               timeframe_to_next_date, timeframe_to_prev_date,
                                               timeframe_to_seconds)
from freqtrade.exchange.types import OHLCVResponse, OrderBook, Ticker, Tickers
from freqtrade.misc import (chunks, deep_merge_dicts, file_dump_json, file_load_json,
                            safe_value_fallback2)
from freqtrade.plugins.pairlist.pairlist_helpers import expand_pairlist


from ccxt.base.errors import NotSupported
from ccxt.async_support.base.exchange import Exchange as exchange_async
from freqtrade.exchange.exchange import Exchange as exchange1
logger = logging.getLogger(__name__)


class Exchange(exchange1):
    #일단 상속은 해놓지만 서비스 버전에서는 상속 끊고 순환상속 해결함

    def _async_get_candle_history_log(
        self,
        pair: str,
        timeframe: str,
        candle_type: CandleType,
        since_ms: Optional[int] = None,
    ):
        logger.info(f"l_Exchange {self.name} {self} {super.__class__} async_get_candle_history {pair}, {timeframe}, since_ms={since_ms}, candle_type={candle_type}\n")

    @retrier_async
    async def _async_get_candle_history(
        self,
        pair: str,
        timeframe: str,
        candle_type: CandleType,
        since_ms: Optional[int] = None
    ) -> OHLCVResponse:        
        """
        Asynchronously get candle history data using fetch_ohlcv
        :param candle_type: '', mark, index, premiumIndex, or funding_rate
        returns tuple: (pair, timeframe, ohlcv_list)
        """
        # self = super()
        # logger.info(f"Exchange {self.name} {self} config {self._ft_has.keys()}") 
        logger.info(f"_async_get_candle_history {pair}, {timeframe}, since_ms={since_ms}, candle_type={candle_type}\n")
        logger.info("start fetching pair %s, interval %s ...", pair, timeframe)
        try:
            # Fetch OHLCV asynchronously
            s = '(' + arrow.get(since_ms // 1000).isoformat() + ') ' if since_ms is not None else ''
            logger.debug(
                "Fetching pair %s, %s, interval %s, since %s %s...",
                pair, candle_type, timeframe, since_ms, s
            )
            params = deepcopy(self._ft_has.get('ohlcv_params', {}))
            candle_limit = self.ohlcv_candle_limit(
                timeframe, candle_type=candle_type, since_ms=since_ms)

            
            if candle_type and candle_type != CandleType.SPOT:
                params.update({'price': candle_type.value})
            if candle_type != CandleType.FUNDING_RATE:
                # self.exchange_has(self, 'fetchTrades')
                # self._api_async.has('fetchTrades')
                #logging.root.setLevel(logging.DEBUG)
                #exchange_async.has({'fetchTrades'})
                logging.debug("## exchange_async ##", exchange_async)
                task = asyncio.create_task(self._api_async.fetch_ohlcv(
                    pair, timeframe=timeframe, since=since_ms,
                    limit=candle_limit, params=params)
                )
            else:
                # Funding rate
                task = asyncio.create_task(
                    self._fetch_funding_rate_history(
                    pair=pair,
                    timeframe=timeframe,
                    limit=candle_limit,
                    since_ms=since_ms,
                )
                )
            
            # task2 = asyncio.create_task(self._api_async.fetch_ohlcv(pair, timeframe='30m', since=since_ms, limit=candle_limit, params=params))
            # https://api.upbit.com/v1/candles/minutes/10?market=KRW-BTC&count=200
            # 어차피 200개를 받는 것이므로 1m 이든 30m 이든 받는 시간은 동일함
            # 시간을 아끼려면 1분봉이든 60분봉이든 200개 다 받을 필요는 없다는 것. 특히 tradebot(whitelist 결정할 때는?)
            # 근데 down-load 로 할 때 왜 200을 안넣었을 때 짤렸을까?

            data = await task
            logger.info("Done fetching pair %s, interval %s ...", pair, timeframe)
            # data2 = await task2
            # logger.info("Done fetching pair %s, interval %s ...", pair, '30m')


            if self.id == 'upbit':
                aaa = 1
            # Some exchanges sort OHLCV in ASC order and others in DESC.
            # Ex: Bittrex returns the list of OHLCV in ASC order (oldest first, newest last)
            # while GDAX returns the list of OHLCV in DESC order (newest first, oldest last)
            # Only sort if necessary to save computing time
            try:
                if data and data[0][0] > data[-1][0]:
                    data = sorted(data, key=lambda x: x[0])
            except IndexError:
                logger.exception("Error loading %s. Result was %s.", pair, data)
                return pair, timeframe, candle_type, [], self._ohlcv_partial_candle
            # logger.debug("Done fetching pair %s, interval %s ...", pair, timeframe)
            # logger.info(pair, timeframe, candle_type, data[-1], self._ohlcv_partial_candle)
            return pair, timeframe, candle_type, data, self._ohlcv_partial_candle


        except ccxt.NotSupported as e:
            raise OperationalException(
                f'Exchange {self._api.name} does not support fetching historical '
                f'candle (OHLCV) data. Message: {e}') from e
        except ccxt.DDoSProtection as e:
            raise DDosProtection(e) from e
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            raise TemporaryError(f'Could not fetch historical candle (OHLCV) data '
                                 f'for pair {pair} due to {e.__class__.__name__}. '
                                 f'Message: {e}') from e
        except ccxt.BaseError as e:
            raise OperationalException(f'Could not fetch historical candle (OHLCV) data '
                                       f'for pair {pair}. Message: {e}') from e

