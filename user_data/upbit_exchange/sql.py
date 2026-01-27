import sqlite3
conn = sqlite3.connect("ohlcv.sqlite")
print(" ")
print("1st recording time(UTC, KST)",conn.execute("SELECT datetime(ts/1000.0, 'unixepoch'), datetime(ts/1000.0, 'unixepoch', '+9 hours') FROM ohlcv_KRW_BTC ORDER BY ts ASC LIMIT 1;").fetchall())
print("LAST recording time(UTC, KST)",conn.execute("SELECT datetime(ts/1000.0, 'unixepoch'), datetime(ts/1000.0, 'unixepoch', '+9 hours') FROM ohlcv_KRW_BTC ORDER BY ts DESC LIMIT 1;").fetchall(),"BTC")
print("LAST recording time(UTC, KST)",conn.execute("SELECT datetime(ts/1000.0, 'unixepoch'), datetime(ts/1000.0, 'unixepoch', '+9 hours') FROM ohlcv_KRW_ETH ORDER BY ts DESC LIMIT 1;").fetchall(),"ETH")
print("LAST recording time(UTC, KST)",conn.execute("SELECT datetime(ts/1000.0, 'unixepoch'), datetime(ts/1000.0, 'unixepoch', '+9 hours') FROM ohlcv_KRW_XRP ORDER BY ts DESC LIMIT 1;").fetchall(),"XRP")
print("BTC",conn.execute("SELECT ts, open, high, low, close, volume, timeframe_ms FROM ohlcv_KRW_BTC ORDER BY ts DESC LIMIT 2;").fetchall())
print("ETH",conn.execute("SELECT ts, open, high, low, close, volume, timeframe_ms FROM ohlcv_KRW_ETH ORDER BY ts DESC LIMIT 2;").fetchall())
print("XRP",conn.execute("SELECT ts, open, high, low, close, volume, timeframe_ms FROM ohlcv_KRW_XRP ORDER BY ts DESC LIMIT 2;").fetchall())
conn.close()

