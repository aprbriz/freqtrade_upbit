import asyncio
import ccxt.pro
import itertools
from tabulate import tabulate

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

            if len(trades) > 1:
                if trades[-2]['price'] < trades[-1]['price']:
                    print('\033[31m \033[1m'+'거래금액 증가중'+'\033[0m', trades[-1]['datetime'], trades[-1]['price'])
                elif trades[-2]['price'] > trades[-1]['price']:
                    print('\033[33m \033[1m'+'거래금액 감소중'+'\033[0m', trades[-1]['datetime'], trades[-1]['price'])

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
                    dt = datetime.fromtimestamp(trade['timestamp'] / 1000)
                    dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format(dt_str, exchange.id, trade['symbol'], trade['price'], trade['amount'], trade['id']))
        elif trades[-1]['price'] < min_price:
            min_price = trades[-1]['price']

        if trades[-1]['timestamp'] >= tominute.timestamp()*1000+60000:
            tominute = datetime.fromtimestamp(trades[-1]['timestamp']/1000).replace(second=0).replace(microsecond=0)
            lastminute_cost = tominute_cost
            tominute_cost = 0

        tominute_cost += trades[-1]['cost']

        if last_min_price >= trades[-1]['price']:
            last_min_price = trades[-1]['price']
            print('MIN value is replaced')
            print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format('Datetime', 'Exchange', 'Symbol', 'Price', 'Amount', 'ID'))
            for trade in trades:
                if trade['price'] == last_min_price:
                    dt = datetime.fromtimestamp(trade['timestamp'] / 1000)
                    dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format(dt_str, exchange.id, trade['symbol'], trade['price'], trade['amount'], trade['id']))


        elif last_max_price <= trades[-1]['price']:
            last_max_price = trades[-1]['price']
            print('MAX value is replaced')
            print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format('Datetime', 'Exchange', 'Symbol', 'Price', 'Amount', 'ID'))
            for trade in trades:
                if trade['price'] == last_max_price:
                    dt = datetime.fromtimestamp(trade['timestamp'] / 1000)
                    dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    print('{:<23}{:<8}{:<8}{:<8}{:<15}{:<15}'.format(dt_str, exchange.id, trade['symbol'], trade['price'], trade['amount'], trade['id']))



        since = int(trades[last_id_idx]['timestamp']) + 1
        last_id = trades[-1]['id']

        # print table
        if trades[-1]['price'] > max_price:
            max_price = trades[-1]['price']
            print('MAX value is replaced')
            print(tabulate([[datetime.fromtimestamp(trade['timestamp'] / 1000), exchange.id, trade['symbol'], trade['price'], trade['amount'], trade['id']] for trade in trades if trade['price'] == max_price], headers=['Datetime', 'Exchange', 'Symbol', 'Price', 'Amount', 'ID']))
        elif trades[-1]['price'] < min_price:
            min_price = trades[-1]['price']


        # await asyncio.sleep(1)

if __name__ == '__main__':

    exchange = ccxt.pro.binance()
    symbol = 'BTC/USDT'

    ol = 100 # set the size of the cache to 66 (이 이하면 모자를 때 자주 있음)
    exchange.options['tradesLimit'] = ol  
 
    if exchange.id == "upbit":
        since = exchange.milliseconds()-32400
        # ccxt 는 모두 exchange's or my server 가 아니라 UTC 기준임
        # websocket 으로 받는 json도 timestamp 부터 다 UTC로 바꿔버림 
        # 그런데, exchange 객체를 (이 위에서 선언할 때가 아니라 아래 loop 함수에서 처럼) 불러올 때 UTC가 적용됨
        # (아닌가? 암튼 loop 문 안에 .milli 는 UTC가 적용되던데??)
        # 따라서, 그 전에 사용할 때는 (KST는 SUMMER TIME을 안쓰므로) 일괄적으로 -32400 을 하면 됨
    else:
        since = exchange.milliseconds() 

    limit=0
    asyncio.get_event_loop().run_until_complete(loop(exchange, symbol, since, limit, ol))
    # await exchange.close() 윗줄과 같이하면 이게 필요 없나봐