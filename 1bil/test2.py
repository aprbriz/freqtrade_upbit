# -*- coding: utf-8 -*-
import asyncio
import ccxt.pro

from datetime import datetime
import itertools

async def loop(exchange, symbol, since, limit, ol):

    n=0
    spinner_sgksmsymbols = itertools.cycle(['-', '/', '|', '\\'])
    while True:
        trades = await exchange.watch_trades(symbol, since, limit)
        len_trades = len(trades)
        if len_trades == 0 : continue # since 값 변경 등 말썽쟁이들이 있어도 list range index 문제가 '덜'생기게 해줌 ^^;
        now = exchange.milliseconds()

        # print('\r', end=' ')  # 여기 \r 을 안넣으면 아얘 화면이 안나오네?
        # print('\033c', end='') #\033c : os.system('clear') #화면 스크롤 안되도록

        print(next(spinner_symbols))
        cur_id = int(trades[-1]['id']) # 가끔 써먹으려면 int()를 써야

        if n == 0: 
            n = len_trades
            last_id = trades[-len_trades]['id'] # n==0 일 때는 len_trades 를 써도 됨
            last_id_idx = -len_trades # 아래 for 문에서 define 해줘도 여기서 미리 해줘야
                        
            min_price = trades[-1]['price']
            max_price = trades[-1]['price']
            
            tominute = datetime.fromtimestamp(trades[-1]['timestamp']/1000).replace(second=0).replace(microsecond=0)
            tominute_cost = 0
            lastminute_cost =0

            last_min_price = 2 ** 29 ## last_min_price 관련된 놈들 싹 필요 없는데... sorted 까지
            last_max_price = 0
        
        
        print(cur_id, last_id, last_id_idx, len_trades, '--------------------------------------------------------------')
        for trade in trades:

            # 항상 출력되는 key

            print(tabulate(trade['datetime'], exchange.id, '  \t', symbol, '\t', trade['id'], trade['price'], trade['cost'], trade['amount']), 
                  headers=['Datetime', 'Exchange', 'Symbol', 'Price', 'Amount', 'ID'])

            # print(trades[v]['datetime'], exchange.id, symbol, 'id', trades[v]['id'], trades[v]['price'], 
            #      'min/MAX', min_price, max_price, max_price-min_price, 'cost', trades[v]['cost'], '\t')
            # print(' ' * 80, end='\r')


        if (n % ol) == 0:
            
            match ((n/ol) % 4, n/ol):
                case (0,1):
                    print (trades)         
                    for trade in trades:
                        print(trade['datetime'], exchange.id, '  \t', symbol, '\t', trade['price'], trade['amount'], trade['id'])
                    since = now
                    limit = 25                    
                case (1,1):
                    for trade in trades:
                        print(trade['datetime'], exchange.id, '  \t', symbol, '\t', trade['price'], trade['amount'], trade['id'])
                    since = now
                    limit = 50                    
                case (2,1):
                    print (trades)         
                    since = now
                    limit = 75                    
                case (4,1):
                    print (trades)         
                    since = now
                    limit = 75                 
                case (_,2):
                    break

            
            i = -(ol)
            trades.sort(key = lambda x:x['amount'])
            # trades.sort(key = lambda x:x['price'])
            for trade in trades:
                # print(trades[i]['datetime'], exchange.id, '  \t', symbol, '\t', trades[i]['price'], trades[i]['amount'], trades[i]['id'])
                i += 1
            # if len(trades) > 2 : print(trades)

            print('Received', ol, '@', exchange.iso8601(now), 'after', exchange.iso8601(since))
            # since = now # 이게 range index 를 교란시키는 주범인 듯. 일단 while loop 중 값이 바뀌면 안될 듯.
            # 그리고 since 가 바뀔 때마다 len(trades) 가 0이 되니 이건 여기 들어가면 안됨


            i = -(ol)
            test_trades = sorted(trades, key=lambda x:x['price'], reverse=True)
            for test_trade in test_trades :
            #    print(test_trades[i]['datetime'], exchange.id, '  \t', symbol, '\t', test_trades[i]['price'], test_trades[i]['amount'], test_trades[i]['id'])
                i += 1
            print('\n')

            print('waiting for next update...','\n')
            await exchange.sleep (500)

        n += 1
        last_id = cur_id
        last_min_price = min_price
        last_max_price = max_price

    #    return self.safe_trade({
    #        'info': trade,
    #        'timestamp': timestamp,
    #        'datetime': self.iso8601(timestamp),
    #        'symbol': symbol,
    #        'id': id,
    #        'order': orderId,
    #        'type': type,
    #        'takerOrMaker': takerOrMaker,
    #        'side': side,
    #        'price': price,
    #        'amount': amount,
    #       'cost': cost,
    #       'fee': fee,



async def main():
    exchange = ccxt.pro.binance()
    # exchange = ccxt.pro.upbit()

    # exchange.verbose = True  # uncomment for debugging purposes if necessary # 이거 켜면 message b 같은게 print 됨 ^^;

    ol = 100 # set the size of the cache to 66 (이 이하면 모자를 때 자주 있음)
    exchange.options['tradesLimit'] = ol  


    if exchange.id == "upbit":
        since = exchange.milliseconds()-32400
        currency = 'KRW'
        # ccxt 는 모두 exchange's or my server 가 아니라 UTC 기준임
        # websocket 으로 받는 json도 timestamp 부터 다 UTC로 바꿔버림 
        # 그런데, exchange 객체를 (이 위에서 선언할 때가 아니라 아래 loop 함수에서 처럼) 불러올 때 UTC가 적용됨
        # (아닌가? 암튼 loop 문 안에 .milli 는 UTC가 적용되던데??)
        # 따라서, 그 전에 사용할 때는 (KST는 SUMMER TIME을 안쓰므로) 일괄적으로 -32400 을 하면 됨
    else:
        since = exchange.milliseconds() 
        currency = 'USDT'

    symbol = 'BTC/'+currency


    limit=0
    # await loop(exchange, 'BTC/USDT', since, limit, ol)
    await loop(exchange, symbol, since, limit, ol)
    await exchange.close()

if __name__ == '__main__':
    asyncio.run(main())
