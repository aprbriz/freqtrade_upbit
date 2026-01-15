import asyncio
import ccxt.pro
import itertools

from datetime import datetime

async def loop(exchange, symbol, since, limit, ol):

    n = 0
    spinner_symbols = itertools.cycle(['-', '/', '|', '\\'])

    while True:
        trades = await exchange.watch_trades(symbol, since, limit)
        len_trades = len(trades)
        now = exchange.milliseconds()

        # print('\r', end=' ')
        # print('\033c', end='')

        # print(next(spinner_symbols))
        cur_id = int(trades[-1]['id'])

        if n == 0:
            n = len_trades
            last_id = trades[-len_trades]['id']
            last_id_idx = -len_trades

            min_price = trades[-1]['price']
            max_price = trades[-1]['price']
            last_min_price = 2 ** 29
            last_max_price = 0
            
            tominute = datetime.fromtimestamp(trades[-1]['timestamp']/1000).replace(second=0).replace(microsecond=0)
            tominute_cost = 0
            lastminute_cost = 0

        for i in range(-1,-len_trades,-1):
            if int(trades[i]['id']) == last_id:
                last_id_idx = i
                break

        if cur_id == last_id:
            continue

        if len(trades) > 1:
            if trades[-2]['price'] < trades[-1]['price']:
                print('\033[31m \033[1m'+'거래금액 증가중'+'\033[0m', trades[-1]['datetime'], trades[-1]['price'])
            elif trades[-2]['price'] > trades[-1]['price']:
                print('\033[33m \033[1m'+'거래금액 감소중'+'\033[0m', trades[-1]['datetime'], trades[-1]['price'])
        
        if trades[-1]['price'] > max_price:
            max_price = trades[-1]['price']
            print('MAX value is replaced')
            print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format('Datetime', 'Exchange', 'Symbol', 'Price', 'Amount', 'ID'))
            for trade in trades:
                if trade['price'] == max_price:
                    print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format('Datetime', 'Exchange', 'Symbol', 'Price', 'Amount', 'ID'))
                    for trade in trades:
                        if trade['price'] == max_price:
                            print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format(datetime.fromtimestamp(trade['timestamp'] / 1000), exchange.id, trade['symbol'], trade['price'], trade['amount'], trade['id']))
        elif trades[-1]['price'] < min_price:
            min_price = trades[-1]['price']
            print('MIN value is replaced')
            print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format('Datetime', 'Exchange', 'Symbol', 'Price', 'Amount', 'ID'))
            for trade in trades:
                if trade['price'] == min_price:
                    print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format(datetime.fromtimestamp(trade['timestamp'] / 1000), exchange.id, trade['symbol'], trade['price'], trade['amount'], trade['id']))

        n_new = len_trades - abs(last_id_idx)
        n += n_new
        last_id = trades[-n]['id']
        last_id_idx -= n_new

        if datetime.fromtimestamp(trades[-1]['timestamp']/1000).replace(second=0).replace(microsecond=0) > tominute:
            lastminute_cost = tominute_cost
            tominute = datetime.fromtimestamp(trades[-1]['timestamp']/1000).replace(second=0).replace(microsecond=0)
            tominute_cost = 0
            
        tominute_cost += sum([trade['amount']*trade['price'] for trade in trades])

        ol['minuteCost'] = tominute_cost
        ol['lastMinuteCost'] = lastminute_cost
        ol['minPrice'] = min_price
        ol['maxPrice'] = max_price


    await exchange.close()

if __name__ == '__main__':

    exchange = ccxt.pro.binance()
    symbol = 'BTC/USDT'
    since = None
    limit = 100

    ol = {}
    asyncio.get_event_loop().run_until_complete(loop(exchange, symbol, since, limit, ol))
