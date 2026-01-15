from asyncio import run, gather, CancelledError, sleep
import ccxt.pro
import ccxt

from datetime import datetime
import itertools

async def loop(exchange, symbol, since, limit, ol):
    n=0
    spinner_symbols = itertools.cycle(['-', '/', '|', '\\'])

    while True:
        try:
            trades = await exchange.watch_trades(symbol, since, limit)
            len_trades = len(trades)
            if len_trades == 0 : continue # since 값 변경 등 말썽쟁이들이 있어도 list range index 문제가 '덜'생기게 해줌 ^^;
            now = exchange.milliseconds()

            #print('\r', end=' ')  # 여기 \r 을 안넣으면 아얘 화면이 안나오네?
            #print('\033c', end='') #\033c : os.system('clear') #화면 스크롤 안되도록
            print(next(spinner_symbols))

            tominute = datetime.fromtimestamp(trades[-1]['timestamp']/1000).replace(second=0).replace(microsecond=0)

            if n == 0: 
                n = len_trades

            if (n % ol) == 0:
                i = -(ol)
                trades.sort(key = lambda x:x['amount'])
                for trade in trades:
                    print(trades[i]['datetime'], exchange.id, '  \t', symbol, '\t', trades[i]['price'], trades[i]['amount'], trades[i]['id'])
                    i += 1
                print('Received', ol, '@', exchange.iso8601(now), 'after', exchange.iso8601(since))

            n += 1

        except Exception as e:
            print(str(e))
            #raise e  # uncomment to break all loops in case of an error in any one of them
            break  # you can also break just this one loop if it fails


async def main():
    exchange = ccxt.pro.binance()
    # exchange = ccxt.pro.upbit()

    markets = await exchange.load_markets()
    exchange.verbose = True  # uncomment for debugging purposes if necessary # 이거 켜면 message b 같은게 print 됨 ^^;
 
    ol = 33 # set the size of the cache to 66 (이 이하면 모자를 때 자주 있음)
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

    symbols = ['BTC/'+currency, 'ETH/'+currency, 'XRP/'+currency]


    limit=0
    await gather(*[loop(exchange, symbol, since, limit, ol) for symbol in symbols])
    await exchange.close()


run(main())

