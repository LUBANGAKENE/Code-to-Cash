# mt5_streamer.py
import time, os, json, requests, datetime as dt
import MetaTrader5 as mt5

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_KEY     = os.getenv("API_KEY", "dev-key")
POLL_SECS   = int(os.getenv("POLL_SECS", "5"))

def to_iso(ts):
    # Convert MT5 datetime (seconds) to ISO string
    if isinstance(ts, (int, float)):
        return dt.datetime.utcfromtimestamp(ts).isoformat() + "Z"
    return str(ts)

def position_to_dict(p):
    return {
        "ticket": p.ticket,
        "symbol": p.symbol,
        "type": p.type,            # 0=buy, 1=sell
        "volume": p.volume,
        "price_open": p.price_open,
        "sl": p.sl,
        "tp": p.tp,
        "profit": p.profit,
        "time": to_iso(p.time),
        "comment": p.comment
    }

def order_to_dict(o):
    return {
        "ticket": o.ticket,
        "symbol": o.symbol,
        "type": o.type,
        "volume_current": o.volume_current,
        "price_open": o.price_open,
        "sl": o.sl,
        "tp": o.tp,
        "time_setup": to_iso(o.time_setup),
        "state": o.state,
        "comment": o.comment
    }

def deal_to_dict(d):
    return {
        "ticket": d.ticket,
        "order": d.order,
        "symbol": d.symbol,
        "type": d.type,
        "volume": d.volume,
        "price": d.price,
        "profit": d.profit,
        "swap": d.swap,
        "commission": d.commission,
        "comment": d.comment,
        "time": to_iso(d.time)
    }

def fetch_snapshot():
    ai = mt5.account_info()
    if ai is None:
        raise RuntimeError("account_info() failed")

    # Open positions / working orders
    positions = mt5.positions_get() or []
    orders    = mt5.orders_get()    or []

    # Recent history (last 30 days)
    now  = dt.datetime.utcnow()
    frm  = now - dt.timedelta(days=30)
    deals = mt5.history_deals_get(frm, now) or []

    # Minimal equity curve point
    eq_point = {"t": now.isoformat() + "Z", "equity": float(ai.equity)}

    snapshot = {
        "ts": now.isoformat() + "Z",
        "account": {
            "login": ai.login,
            "name": ai.name,
            "server": ai.server,
            "currency": ai.currency,
            "balance": float(ai.balance),
            "equity": float(ai.equity),
            "profit": float(ai.profit),
            "margin": float(ai.margin),
            "margin_level": float(ai.margin_level) if ai.margin_level is not None else None
        },
        "positions": [position_to_dict(p) for p in positions],
        "orders":    [order_to_dict(o)    for o in orders],
        "deals":     [deal_to_dict(d)     for d in deals],
        "equity_point": eq_point
    }
    return snapshot

def main():
    if not mt5.initialize():
        raise RuntimeError("Failed to initialize MT5. Is MetaTrader 5 running and logged in?")

    try:
        while True:
            try:
                snap = fetch_snapshot()
                resp = requests.post(
                    f"{BACKEND_URL}/ingest/snapshot",
                    data=json.dumps(snap),
                    headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
                    timeout=5,
                )
                resp.raise_for_status()
            except Exception as e:
                print("POST error:", e)
            time.sleep(POLL_SECS)
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
