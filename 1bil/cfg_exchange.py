from freqtrade.enums import RunMode
from freqtrade.resolvers import ExchangeResolver
from freqtrade.exchange.exchange import Exchange as exchange1
from freqtrade.commands import Arguments
from freqtrade.configuration import setup_utils_configuration
from asyncio import run, gather, sleep
import ccxt.pro
import ccxt

import itertools

import logging
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Coroutine, Dict, List, Literal, Optional, Tuple, Union

import arrow
from pandas import DataFrame, concat

from freqtrade.data.converter import clean_ohlcv_dataframe, ohlcv_to_dataframe, trades_dict_to_list
from freqtrade.exchange.types import OHLCVResponse, OrderBook, Ticker, Tickers

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Exchange(exchange1):
    """
    def __init__(self, config: Config, validate: bool = True,
                 load_leverage_tiers: bool = False) -> None:
        # freqtrade.exchange.exchange 에서 init 했지만 다른 class 로 바꿔도 돌아가게..
        self._config: Config = {}
        self._config.update(config)
    """
    async def _async_get_candle_history_log(
        self,
        pair: str,
        since_ms: Optional[int] = None,
    ):

        if not self._config['dry_run']:
            logger.info(f"balances = {self.get_balances()}")            
        logger.info(f"l_Exchange name {self.name} candle_history {pair}, since_ms={since_ms}\n")

async def main():

    arguments = Arguments(['trade'])
    args = arguments.get_parsed_arg()
    config = setup_utils_configuration(args, RunMode.UTIL_EXCHANGE)
    # self = ExchangeResolver.load_exchange(config['exchange']['name'], config, validate=False)
    exchange = Exchange(config, validate=False)

    pairs = config['exchange']['pair_whitelist']
    since_ms = arrow.utcnow().int_timestamp * 1000
    
    gather(*[
        exchange._async_get_candle_history_log(
        pair=pair, since_ms=since_ms)for pair in pairs])

run(main())