# server.py
import zmq
import signal
import sys
import pickle
import numpy as np
import pandas as pd
import pandas_ta as ta
import MetaTrader5 as mt5
from tensorflow.keras.models import load_model
from datetime import datetime

# ===========================
# Config
# ===========================
SYMBOL_MAIN   = "USDJPY"
TIMEFRAME     = mt5.TIMEFRAME_H4
N_BARS        = 600

AUX_SYMBOLS = {
    "gbpusd_close": "GBPUSD",
    "nzdusd_close": "NZDUSD",
    "eurusd_close": "EURUSD",
    "gbpjpy_close": "GBPJPY",
}

CONSENSUS_FEATS = [
    'williams_%r','log_return','stoch_%k','gbpusd_close','slope_42','close',
    'nzdusd_close','macd_signal','macd_hist','stoch_%d','ema_6','adx_10',
    'rsi','low','eurusd_close','tickvol','std_dev','macd','gbpjpy_close','atr'
]

# ===========================
# Load model & scaler (once)
# ===========================
model_cons = load_model('code_to_cash_usdjpy_h4_02-08-25_model.keras')
with open('code_to_cash_usdjpy_h4_02-08-25_scaler.pkl','rb') as f:
    scaler_cons = pickle.load(f)

# ===========================
# Helpers
# ===========================
def ensure_symbol(symbol: str):
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Failed to select symbol {symbol}")

def fetch_rates(symbol, timeframe, count) -> pd.DataFrame:
    ensure_symbol(symbol)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"Failed to get OHLC for {symbol}")
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def compute_features_pandasta(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.rename(columns={'tick_volume': 'tickvol'})
    out = out[['time', 'open', 'high', 'low', 'close', 'tickvol']]
    out.set_index('time', inplace=True)
    out.sort_index(inplace=True)

    out['log_return'] = np.log(out['close'] / out['close'].shift(1))
    out['williams_%r'] = ta.willr(high=out['high'], low=out['low'], close=out['close'], length=14)

    stoch = ta.stoch(high=out['high'], low=out['low'], close=out['close'], k=14, d=3)
    out['stoch_%k'] = stoch['STOCHk_14_3_3']
    out['stoch_%d'] = stoch['STOCHd_14_3_3']

    out['rsi'] = ta.rsi(close=out['close'], length=14)

    macd = ta.macd(close=out['close'], fast=12, slow=26, signal=9)
    out['macd']        = macd['MACD_12_26_9']
    out['macd_signal'] = macd['MACDs_12_26_9']
    out['macd_hist']   = macd['MACDh_12_26_9']

    adx = ta.adx(high=out['high'], low=out['low'], close=out['close'], length=10)
    out['adx_10'] = adx['ADX_10']

    out['ema_6'] = ta.ema(close=out['close'], length=6)
    ema42 = ta.ema(close=out['close'], length=42)
    out['slope_42'] = ema42.pct_change(1)

    out['atr'] = ta.atr(high=out['high'], low=out['low'], close=out['close'], length=14)
    out['std_dev'] = out['close'].rolling(20).std()

    return out

def attach_aux_closes(main_df: pd.DataFrame, aux_map, timeframe, n_bars) -> pd.DataFrame:
    result = main_df.copy()
    for col_name, sym in aux_map.items():
        aux_df = fetch_rates(sym, timeframe, n_bars)
        aux_df = aux_df[['time', 'close']].rename(columns={'close': col_name})
        aux_df.set_index('time', inplace=True)
        result = result.join(aux_df[col_name], how='left')
    return result

def build_X(df_full: pd.DataFrame):
    X = df_full[CONSENSUS_FEATS].copy()
    mask = ~X.isna().any(axis=1)
    X = X[mask]
    return X, mask

def make_prediction() -> str:
    """
    Computes features on the latest completed bar(s), scales, predicts,
    and returns 'buy' or 'sell' as a short string.
    """
    # Use all but the *current forming* bar on main symbol
    main_rates = fetch_rates(SYMBOL_MAIN, TIMEFRAME, N_BARS).iloc[:-1].copy()
    main_feats = compute_features_pandasta(main_rates)
    feats_full = attach_aux_closes(main_feats, AUX_SYMBOLS, TIMEFRAME, N_BARS)

    X_new, _ = build_X(feats_full)
    if X_new.empty:
        return "hold"  # nothing to predict on

    X_scaled = scaler_cons.transform(X_new.values)
    y_prob = model_cons.predict(X_scaled, verbose=0).ravel()
    y_lbl  = (y_prob > 0.5).astype(int)
    pred   = "buy" if y_lbl[-1] == 1 else "sell"

    ts = X_new.index[-1]
    print(f"[{ts}] Prediction: {pred}  (p={y_prob[-1]:.3f})")
    return pred

# ===========================
# ZMQ REP loop
# ===========================
def main():
    if not mt5.initialize():
        raise RuntimeError("MetaTrader5 initialize() failed")

    ctx = zmq.Context(io_threads=1)
    sock = ctx.socket(zmq.REP)
    sock.bind("tcp://127.0.0.1:5555")
    print("[ZMQ] Prediction server listening on tcp://127.0.0.1:5555")

    # graceful shutdown
    def shutdown(*_):
        print("\n[ZMQ] Shutting down...")
        try:
            sock.close(0)
        except Exception:
            pass
        try:
            ctx.term()
        except Exception:
            pass
        try:
            mt5.shutdown()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            # 1) Receive a request (blocks until EA sends)
            msg = sock.recv_string()
            # You can later support JSON like {"cmd":"request_prediction","symbol":"USDJPY"}
            if msg != "request_prediction":
                sock.send_string("unknown_request")
                continue

            # 2) Compute prediction
            try:
                pred = make_prediction()
            except Exception as e:
                # send an error string so the REQ client doesn't get stuck
                err = f"ERROR:{type(e).__name__}:{e}"
                print("[Predict] ", err)
                sock.send_string(err)
                continue

            # 3) Reply exactly once
            sock.send_string(pred)

        except zmq.ContextTerminated:
            break
        except Exception as e:
            # In REP sockets, we must reply for every recv.
            # If error happened before sending the reply, try to send an error.
            try:
                sock.send_string(f"ERROR:{type(e).__name__}:{e}")
            except Exception:
                pass
            print(f"[ZMQ] Loop error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
