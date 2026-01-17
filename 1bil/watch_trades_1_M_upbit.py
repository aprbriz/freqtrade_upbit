from asyncio import run, gather, CancelledError, sleep
import ccxt.pro
import ccxt

from datetime import datetime
import itertools

async def loop(exchange, symbol, since, limit, ol):

    n=0
    spinner_symbols = itertools.cycle(['-', '/', '|', '\\'])

    # await exchange.throttle(200 / exchange.rateLimit)  # 1 subscription every 200 milliseconds
    # 이거 끄고 켜고 차이를 몰겠음
    while True:
        try:
            trades = await exchange.watch_trades(symbol, since, limit)
            len_trades = len(trades)
            if len_trades == 0 : continue # since 값 변경 등 말썽쟁이들이 있어도 list range index 문제가 '덜'생기게 해줌 ^^;
            now = exchange.milliseconds()

            print('\r', end=' ')  # 여기 \r 을 안넣으면 아얘 화면이 안나오네?
            print('\033c', end='') #\033c : os.system('clear') #화면 스크롤 안되도록

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
            
            # 최종값의 id가 list 중 끝에서 몇번째인지 조회. 현재 list 전체에서 조회하되 끝에서부터
            for i in range(-1,-len_trades,-1):
                # if i == -len_trades+1 or 0<1: print (i, last_id, trades[i]['id'])
                if int(trades[i]['id']) == last_id: # cur_id = int(...) 이니 요기도 int() 가 들어가야
                    last_id_idx = i
                    # print ("last_id_idx", i)
                    break
            
            print(cur_id, last_id, last_id_idx, len_trades, '--------------------------------------------------------------')
            for v in range(last_id_idx+1,0,1): # 최종값의 인덱스+1 id부터 끝까지 불러옴. for는 -1까지만 부름
            # for v in range(-(cur_id - last_id),0,1): 
            # upbit 등의 exchange 는 id 값을 timestamp 를 조작해서 만들어 '연속되지 않아서' 요걸 못씀

                # exchange 기준 20~60초 사이동안 직전 1분봉(1분 거래량을 합산해서 저장해서 써도 무방) 보다 거래금액이 크면...
                if datetime.fromtimestamp(trades[v]['timestamp']/1000).replace(second=0).replace(microsecond=0) == tominute:
                    tominute_cost += trades[v]['cost']
                else:
                    tominute = datetime.fromtimestamp(trades[v]['timestamp']/1000).replace(second=0).replace(microsecond=0)
                    lastminute_cost = tominute_cost
                    tominute_cost = 0                
                tosecond_num = datetime.fromtimestamp(trades[v]['timestamp']/1000).second
                if (tominute_cost > 0 and tosecond_num > 20 
                    and (tominute_cost / tosecond_num * 60 > lastminute_cost)
                    and lastminute_cost > 0):
                    print ('\033[31m \033[1m'+'거래금액 증가중'+'\033[0m', lastminute_cost, '->', tominute_cost, '@', tominute, tosecond_num)

                # min/max : 쓸데가 없는ㅋ
                if trades[v]['price'] > max_price: max_price = trades[v]['price']
                if trades[v]['price'] < min_price: min_price = trades[v]['price']
                if ((min_price > last_min_price) or (max_price < last_max_price) 
                    and min_price > 0):            
                    print('min/MAX value is replaced -------------------------------------------------------------')
                    i = -(len_trades)
                    for trade in sorted(trades, key=lambda x:x['price'], reverse=True):
                        print(trades[i]['datetime'], exchange.id, '  \t', symbol, '\t', trades[i]['price'], trades[i]['amount'], trades[i]['id'])
                        i += 1

                # 항상 출력되는 key
                print(trades[v]['datetime'], exchange.id, symbol, 'id', trades[v]['id'], trades[v]['price'], 
                    'min/MAX', min_price, max_price, max_price-min_price, 'cost', trades[v]['cost'], '\t')
                # print(' ' * 80, end='\r')


            if (n % ol) == 0:
                i = -(ol)
                trades.sort(key = lambda x:x['amount'])
                # trades.sort(key = lambda x:x['price'])
                for trade in trades:
                    print(trades[i]['datetime'], exchange.id, '  \t', symbol, '\t', trades[i]['price'], trades[i]['amount'], trades[i]['id'])
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
                await sleep(0.5)

            n += 1
            last_id = cur_id
            last_min_price = min_price
            last_max_price = max_price

        except CancelledError:   # 이거 안먹는 듯. 삭제?
            break

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


        except Exception as e:
            print(str(e))
            #raise e  # uncomment to break all loops in case of an error in any one of them
            break  # you can also break just this one loop if it fails


async def main():
    # exchange = ccxt.pro.binance()
    exchange = ccxt.pro.upbit()

    markets = await exchange.load_markets()
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

    symbols = ['BTC/'+currency, 'ETH/'+currency, 'XRP/'+currency]


    limit=0
    await gather(*[loop(exchange, symbol, since, limit, ol) for symbol in symbols])
    await exchange.close()


run(main())


# 아래건 뭔지 몰겠다. ^^;
# if __name__ == '__main__':
#    asyncio.get_event_loop().run_until_complete(main())

#if __name__ == '__main__':
#    asyncio_loop = asyncio.get_event_loop()
#    asyncio_loop.run_until_complete(main(asyncio_loop))