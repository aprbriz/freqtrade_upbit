import sqlite3
from contextlib import ExitStack

def ft(r): return f"['{r[0]}, {r[1]}]"
def one(conn, q): return conn.execute(q).fetchone()
def two(conn, q): return conn.execute(q).fetchall()

DBS = {"short":"ohlcv_short.sqlite","10s_1m":"ohlcv_10s_1m.sqlite","10m":"ohlcv_10m.sqlite"}
COINS = ["BTC","ETH","XRP"]

with ExitStack() as st:
    conns = {k: st.enter_context(sqlite3.connect(v)) for k,v in DBS.items()}
    print("\n" + "="*50)

    q = "SELECT datetime(ts/1000.0,'unixepoch'), datetime(ts/1000.0,'unixepoch','+9 hours') FROM ohlcv_KRW_BTC ORDER BY ts ASC LIMIT 1;"
    print("1st recording time(UTC, KST):", ft(one(conns["short"], q)))

    for c in COINS:
        q = f"SELECT datetime(ts/1000.0,'unixepoch'), datetime(ts/1000.0,'unixepoch','+9 hours') FROM ohlcv_KRW_{c} ORDER BY ts DESC LIMIT 1;"
        print("LAST recording time(UTC, KST):", ft(one(conns["short"], q)), c)

    plans = [
        ("short",  "{c}_short",   ""),
        ("10s_1m", "{c}_10s_1m",  "WHERE timeframe_ms=10000"),
        ("10s_1m", "{c}_10s_1m",  "WHERE timeframe_ms=60000"),
        ("10m",    "{c}_10m",     ""),
    ]

    for dbk, label_tpl, where in plans:
        for c in COINS:
            q = f"SELECT ts, open, high, low, close, volume, timeframe_ms FROM ohlcv_KRW_{c} {where} ORDER BY ts DESC LIMIT 2;"
            print(label_tpl.format(c=c) + ":", ", ".join(map(str, two(conns[dbk], q))))
