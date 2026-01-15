from asyncio import run, gather
import ccxt.pro
import ccxt


print('CCXT Pro version:', ccxtpro.__version__)
print('CCXT version:', ccxt.__version__)


async def loop(exchange, symbol):
    await exchange.throttle(200 / exchange.rateLimit)  # 1 subscription every 200 milliseconds
    while True:
        try:
            orderbook = await exchange.watch_order_book(symbol)
            now = exchange.milliseconds()
            print(exchange.iso8601(now), symbol, orderbook['asks'][0], orderbook['bids'][0])
        except Exception as e:
            print(str(e))
            #raise e  # uncomment to break all loops in case of an error in any one of them
            break  # you can also break just this one loop if it fails


async def main():
    exchange = ccxt.pro.binance()
    markets = await exchange.load_markets()
    # exchange.verbose = True  # uncomment for debugging purposes if necessary
    symbols = ['BTCUSDT', 'ETHUSDT', 'ETHBTC']
    await gather(*[loop(exchange, symbol) for symbol in symbols])
    await exchange.close()


run(main())