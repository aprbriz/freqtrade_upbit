from ccxt.base.errors import NotSupported
from ccxt.base.exchange import Exchange as exchange_base
from ccxt.async_support.base.exchange import Exchange as exchange_async
from ccxt.async_support.upbit import upbit as exchange_upbit
import requests


from freqtrade.exchange.binance import Binance
import freqtrade.exchange as exchanges
from freqtrade.exchange import MAP_EXCHANGE_CHILDCLASS
from freqtrade.enums import RunMode
from freqtrade.resolvers import ExchangeResolver
from freqtrade.exchange.exchange import Exchange as exchange1
from freqtrade.commands import Arguments
from freqtrade.commands.trade_commands import start_trading
import signal
from freqtrade.configuration import Configuration, setup_utils_configuration
from freqtrade.freqtradebot import FreqtradeBot


from asyncio import run, gather, CancelledError, sleep
import ccxt.pro
import ccxt

from datetime import datetime
import itertools


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




logger = logging.getLogger(__name__)


class Module():
    def _init(self, reconfig: bool) -> None:
        """
        Also called from the _reconfigure() method (with reconfig=True).
        """
        if reconfig or self._config is None:
            # Load configuration
            self._config = Configuration(self._args, None).get_config()

        # Init the instance of the bot
        self.freqtrade = FreqtradeBot(self._config)


class Exchange(exchange1):

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
        logger.info(f"_async_get_candle_history Exchange {self.name}, {pair}, {timeframe}, since_ms={since_ms}, candle_type={candle_type}\n")
        # logger.info("start fetching pair %s, interval %s ...", pair, timeframe)
        try:
            # Fetch OHLCV asynchronously
            s = '(' + arrow.get(since_ms // 1000).isoformat() + ') ' if since_ms is not None else ''
            # logger.debug("Fetching pair %s, %s, interval %s, since %s %s...",pair, candle_type, timeframe, since_ms, s)
            params = deepcopy(self._ft_has.get('ohlcv_params', {}))
            candle_limit = self.ohlcv_candle_limit(
                timeframe, candle_type=candle_type, since_ms=since_ms)
            # logger.debug("paramsb{params}, candle_limit {candle_limit}")
            
            if candle_type and candle_type != CandleType.SPOT:
                params.update({'price': candle_type.value})
    
    
            if candle_type != CandleType.FUNDING_RATE:
                logging.root.setLevel(logging.DEBUG)
                # exchange_async.has({'fetchTrades'})
                # logging.debug("exchange_async", exchange_async)
                # data = await exchange_async.fetch_ohlcv(self,

                # data = await self._api_async.fetch_ohlcv(
                # data = await self.fetch_ohlcv(self, pair, timeframe=timeframe, since=since_ms, limit=candle_limit, params=params)
                data = await self.fetch_ohlcv(self, pair, params=params)

            else:
                # Funding rate
                data = await self._fetch_funding_rate_history(
                    pair=pair,
                    timeframe=timeframe,
                    limit=candle_limit,
                    since_ms=since_ms,
                )

            logger.info(data[0])

            logger.info("Done fetching pair %s, interval %s ...", pair, timeframe)
    
    
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

    # 아래는 ccxt base upbit 인가에서 가져온 놈. 즉 upbit 전용
    async def fetch_ohlcv(self, symbol: str, timeframe='1m', since: Optional[int] = None, limit: Optional[int] = None, params={}):
        """
        fetches historical candlestick data containing the open, high, low, and close price, and the volume of a market
        :param str symbol: unified symbol of the market to fetch OHLCV data for
        :param str timeframe: the length of time each candle represents
        :param int|None since: timestamp in ms of the earliest candle to fetch
        :param int|None limit: the maximum amount of candles to fetch
        :param dict params: extra parameters specific to the upbit api endpoint
        :returns [[int]]: A list of candles ordered, open, high, low, close, volume
        """
        timeframe = '1m'
        # await exchange_async.load_markets()
        # market = exchange_async.market(symbol)
        market = 'KRW-BTC'
        timeframePeriod = exchange_async.parse_timeframe(timeframe)
        timeframeValue = exchange_async.safe_string(self.timeframes, timeframe, timeframe)
        if limit is None:
            limit = 200

        url = "https://api.upbit.com/v1/candles/minutes/1?market=KRW-BTC&count=200"
        headers = {"accept": "application/json"}
        response = requests.get(url, headers=headers)

        # response = await getattr(self, method)(self.extend(request, params))
        #
        #     [
        #         {
        #             market: "BTC-ETH",
        #             candle_date_time_utc: "2018-11-22T13:47:00",
        #             candle_date_time_kst: "2018-11-22T22:47:00",
        #             opening_price: 0.02915963,
        #             high_price: 0.02915963,
        #             low_price: 0.02915448,
        #             trade_price: 0.02915448,
        #             timestamp: 1542894473674,
        #             candle_acc_trade_price: 0.0981629437535248,
        #             candle_acc_trade_volume: 3.36693173,
        #             unit: 1
        #         },
        #         {
        #             market: "BTC-ETH",
        #             candle_date_time_utc: "2018-11-22T10:06:00",
        #             candle_date_time_kst: "2018-11-22T19:06:00",
        #             opening_price: 0.0294,
        #             high_price: 0.02940882,
        #             low_price: 0.02934283,
        #             trade_price: 0.02937354,
        #             timestamp: 1542881219276,
        #             candle_acc_trade_price: 0.0762597110943884,
        #             candle_acc_trade_volume: 2.5949617,
        #             unit: 1
        #         }
        #     ]
        #
        return exchange_async.parse_ohlcvs(response, market, timeframe, since, limit)


    # 아래는 ccxt async base 인가에서 가져온 놈들

    def parse_ohlcvs(self, ohlcvs: List[object], market: Optional[Any] = None, timeframe: str = '1m', since: Optional[int] = None, limit: Optional[int] = None):
        results = []
        for i in range(0, len(ohlcvs)):
            results.append(self.parse_ohlcv(ohlcvs[i], market))
        sorted = self.sort_by(results, 0)
        tail = (since is None)
        return self.filter_by_since_limit(sorted, since, limit, 0, tail)

    def parse_ohlcv(self, ohlcv, market=None):
        if isinstance(ohlcv, list):
            return [
                self.safe_integer(ohlcv, 0),  # timestamp
                self.safe_number(ohlcv, 1),  # open
                self.safe_number(ohlcv, 2),  # high
                self.safe_number(ohlcv, 3),  # low
                self.safe_number(ohlcv, 4),  # close
                self.safe_number(ohlcv, 5),  # volume
            ]
        return ohlcv




async def main():

    # logging.root.setLevel(logging.DEBUG)

    logging.basicConfig(level=logging.DEBUG)

    sysargv= ['trade']
    arguments = Arguments(sysargv)
    args = arguments.get_parsed_arg()
    config = setup_utils_configuration(args, RunMode.UTIL_EXCHANGE)
    # self = ExchangeResolver.load_exchange(config['exchange']['name'], config, validate=False)

    exchange = Exchange(config, validate=False)


    currency = 'KRW'
    pairs = ['BTC/'+currency, 'ETH/'+currency, 'XRP/'+currency]
    timeframe = '1m'
    since_ms = arrow.utcnow().int_timestamp * 1000
    candle_type= 'spot'

    # print(exchange._async_get_candle_history(pair='BTC/KRW', timeframe=timeframe, since_ms=since_ms, candle_type=candle_type))
    
    gather(*[
        exchange._async_get_candle_history(
        pair=pair, timeframe=timeframe, since_ms=since_ms, candle_type=candle_type)for pair in pairs])



    # print(f"Exchange {self.name} {self} config {self._ft_has.keys()}") 

run(main())