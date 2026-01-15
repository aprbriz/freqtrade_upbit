"""
Very Important PairList provider

Provides dynamic pair list based on trade volumes, etc.
bot'll watch websocket data of pairs from exchange.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal

from cachetools import TTLCache

from freqtrade.constants import Config, ListPairsWithTimeframes
from freqtrade.exceptions import OperationalException
from freqtrade.exchange import timeframe_to_minutes, timeframe_to_prev_date
from freqtrade.exchange.types import Tickers
from freqtrade.misc import format_ms_time
from freqtrade.plugins.pairlist.IPairList import IPairList
from freqtrade.plugins.pairlist.VolumePairList import VolumePairList


logger = logging.getLogger(__name__)

SORT_VALUES = ['quoteVolume']


class VIPairList(VolumePairList):


    def gen_pairlist(self, tickers: Tickers) -> List[str]:
        """
        Generate the pairlist
        :param tickers: Tickers (from exchange.get_tickers). May be cached.
        :return: List of pairs
        """
        # Generate dynamic whitelist
        # Must always run if this pairlist is not the first in the list.
        pairlist = self._pair_cache.get('pairlist')
        # pairlist = {}
        if pairlist:
            # Item found - no refresh necessary
            return pairlist.copy()
        else:
            # Use fresh pairlist
            # Check if pair quote currency equals to the stake currency.
            _pairlist = [k for k in self._exchange.get_markets(
                quote_currencies=[self._stake_currency],
                tradable_only=True, active_only=True).keys()]
            # No point in testing for blacklisted pairs...
            _pairlist = self.verify_blacklist(_pairlist, logger.info)
            if not self._use_range:
                filtered_tickers = [
                    v for k, v in tickers.items()
                    if (self._exchange.get_pair_quote_currency(k) == self._stake_currency
                        and (self._use_range or v.get(self._sort_key) is not None)
                        and v['symbol'] in _pairlist)]
                pairlist = [s['symbol'] for s in filtered_tickers]
            else:
                pairlist = _pairlist
            pairlist = self.filter_pairlist(pairlist, tickers)

            if 'pair_vilist' in self._config.get('exchange', {}):
                pair_vilist = self._config['exchange']['pair_vilist']
                pairlist += [pair for pair in pair_vilist if pair not in pairlist]

            self._pair_cache['pairlist'] = pairlist.copy()
            print("Use fresh pairlist",pairlist)


        return pairlist

    def filter_pairlist(self, pairlist: List[str], tickers: Dict) -> List[str]:
        """
        Filters and sorts pairlist and returns the whitelist again.
        Called on each bot iteration - please use internal caching if necessary
        :param pairlist: pairlist to filter or sort
        :param tickers: Tickers (from exchange.get_tickers). May be cached.
        :return: new whitelist
        """
        if self._use_range:
            # Create bare minimum from tickers structure.
            filtered_tickers: List[Dict[str, Any]] = [{'symbol': k} for k in pairlist]

            # get lookback period in ms, for exchange ohlcv fetch
            since_ms = int(timeframe_to_prev_date(
                self._lookback_timeframe,
                datetime.now(timezone.utc) + timedelta(
                    minutes=-(self._lookback_period * self._tf_in_min) - self._tf_in_min)
                    ).timestamp()) * 1000

            to_ms = int(timeframe_to_prev_date(
                            self._lookback_timeframe,
                            datetime.now(timezone.utc) - timedelta(minutes=self._tf_in_min)
                            ).timestamp()) * 1000

            # todo: utc date output for starting date
            self.log_once(f"Using volume range of {self._lookback_period} candles, timeframe: "
                          f"{self._lookback_timeframe}, starting from {format_ms_time(since_ms)} "
                          f"till {format_ms_time(to_ms)}", logger.info)
            needed_pairs: ListPairsWithTimeframes = [
                (p, self._lookback_timeframe, self._def_candletype) for p in
                [s['symbol'] for s in filtered_tickers]
                if p not in self._pair_cache
            ]

            # Get all candles
            candles = {}
            if needed_pairs:
                candles = self._exchange.refresh_latest_ohlcv(
                    needed_pairs, since_ms=since_ms, cache=False
                )
            for i, p in enumerate(filtered_tickers):
                contract_size = self._exchange.markets[p['symbol']].get('contractSize', 1.0) or 1.0
                pair_candles = candles[
                    (p['symbol'], self._lookback_timeframe, self._def_candletype)
                ] if (
                    p['symbol'], self._lookback_timeframe, self._def_candletype
                    ) in candles else None
                # in case of candle data calculate typical price and quoteVolume for candle
                if pair_candles is not None and not pair_candles.empty:
                    if self._exchange.get_option("ohlcv_volume_currency") == "base":
                        pair_candles['typical_price'] = (pair_candles['high'] + pair_candles['low']
                                                         + pair_candles['close']) / 3

                        pair_candles['quoteVolume'] = (
                            pair_candles['volume'] * pair_candles['typical_price']
                            * contract_size
                        )
                    else:
                        # Exchange ohlcv data is in quote volume already.
                        pair_candles['quoteVolume'] = pair_candles['volume']
                    # ensure that a rolling sum over the lookback_period is built
                    # if pair_candles contains more candles than lookback_period
                    quoteVolume = (pair_candles['quoteVolume']
                                   .rolling(self._lookback_period)
                                   .sum()
                                   .iloc[-1])

                    # replace quoteVolume with range quoteVolume sum calculated above
                    filtered_tickers[i]['quoteVolume'] = quoteVolume
                else:
                    filtered_tickers[i]['quoteVolume'] = 0
        else:
            # Tickers mode - filter based on incoming pairlist.
            filtered_tickers = [v for k, v in tickers.items() if k in pairlist]

        if self._min_value > 0:
            filtered_tickers = [
                v for v in filtered_tickers if v[self._sort_key] > self._min_value]

        sorted_tickers = sorted(filtered_tickers, reverse=True, key=lambda t: t[self._sort_key])

        # Validate whitelist to only have active market pairs
        pairs = self._whitelist_for_active_markets([s['symbol'] for s in sorted_tickers])
        pairs = self.verify_blacklist(pairs, logmethod=logger.info)
        # Limit pairlist to the requested number of pairs
        pairs = pairs[:self._number_pairs]

        return pairs
