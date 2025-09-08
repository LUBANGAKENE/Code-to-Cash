#Prediction server
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
from typing import Optional, Dict, Tuple


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
def mt5_init_once():
    """Initialize MT5; optionally bind to a specific terminal/account."""
    # If you run more than one terminal, uncomment and fill these:
    # ok = mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, server=MT5_SERVER, password=MT5_PASS)
    ok = mt5.initialize()
    if not ok:
        raise RuntimeError(f"MetaTrader5 initialize() failed: {mt5.last_error()}")
    ti = mt5.terminal_info()
    ai = mt5.account_info()
    if ti is None or ai is None:
        raise RuntimeError("MT5 terminal/account not ready")

def resolve_symbol(base: str) -> str:
    """
    Try exact symbol, else scan broker's list for a likely variant (suffix/prefix).
    Returns the *actual* symbol name usable with this terminal.
    """
    if base is None or base == "":
        raise RuntimeError("Empty symbol")
    # Try exact
    if mt5.symbol_select(base, True):
        return base

    # Scan once
    all_syms = mt5.symbols_get()
    if not all_syms:
        raise RuntimeError("symbols_get() returned empty")

    candidates = []
    for s in all_syms:
        name = s.name
        # Heuristics: same core token somewhere in name
        if name == base or name.startswith(base) or name.endswith(base) or base in name:
            candidates.append(name)

    # Prefer the shortest match (often the “raw” symbol)
    candidates.sort(key=len)
    for name in candidates:
        if mt5.symbol_select(name, True):
            return name

    raise RuntimeError(f"Failed to select symbol variant for {base}")

def timeframe_from_period(period_str: str) -> int:
    """
    Map MQL5 _Period text to MetaTrader5.TIMEFRAME_* if you decide to send it.
    Accepts e.g.: M1,M5,M15,M30,H1,H4,D1,W1,MN1 (case-insensitive).
    """
    p = period_str.upper()
    lut = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
    }
    if p not in lut:
        raise RuntimeError(f"Unsupported timeframe: {period_str}")
    return lut[p]

def fetch_rates(base_symbol: str, timeframe: int, count: int) -> Tuple[pd.DataFrame, str]:
    """
    base_symbol can be 'USDJPY'; resolves to actual (e.g., 'USDJPY.a').
    Returns (df, resolved_symbol).
    """
    sym = resolve_symbol(base_symbol)
    rates = mt5.copy_rates_from_pos(sym, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"Failed to get OHLC for {sym}")
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df, sym

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

def attach_aux_closes(main_df: pd.DataFrame, aux_map: Dict[str, str], timeframe: int, n_bars: int) -> pd.DataFrame:
    result = main_df.copy()
    for col_name, base_sym in aux_map.items():
        aux_df, aux_resolved = fetch_rates(base_sym, timeframe, n_bars)
        aux_df = aux_df[['time', 'close']].rename(columns={'close': col_name})
        aux_df.set_index('time', inplace=True)
        result = result.join(aux_df[col_name], how='left')
    return result

def build_X(df_full: pd.DataFrame):
    X = df_full[CONSENSUS_FEATS].copy()
    mask = ~X.isna().any(axis=1)
    X = X[mask]
    return X, mask

def make_prediction(base_symbol: str, timeframe: int) -> str:
    """
    Computes features on the latest completed bar(s), scales, predicts, 'buy'/'sell'/'hold'.
    """
    # Use all but the *current forming* bar
    main_rates, resolved = fetch_rates(base_symbol, timeframe, N_BARS)
    main_rates = main_rates.iloc[:-1].copy()
    main_feats = compute_features_pandasta(main_rates)
    feats_full = attach_aux_closes(main_feats, AUX_SYMBOLS, timeframe, N_BARS)

    X_new, _ = build_X(feats_full)
    if X_new.empty:
        return "hold"

    X_scaled = scaler_cons.transform(X_new.values)
    y_prob = model_cons.predict(X_scaled, verbose=0).ravel()
    y_lbl  = (y_prob > 0.5).astype(int)
    pred   = "buy" if y_lbl[-1] == 1 else "sell"

    ts = X_new.index[-1]
    print(f"[{ts}] {resolved}: Prediction={pred}  p={y_prob[-1]:.3f}")
    return pred

# ===========================
# ZMQ REP loop
# ===========================
def main():
    mt5_init_once()

    ctx = zmq.Context(io_threads=1)
    sock = ctx.socket(zmq.REP)
    sock.bind("tcp://127.0.0.1:5555")
    print("[ZMQ] Prediction server listening on tcp://127.0.0.1:5555")

    def shutdown(*_):
        print("\n[ZMQ] Shutting down...")
        try: sock.close(0)
        except: pass
        try: ctx.term()
        except: pass
        try: mt5.shutdown()
        except: pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            msg = sock.recv_string()  # blocks

            # Supported:
            # 1) "request_prediction"
            # 2) "request_prediction|<SYMBOL>|<TF>" e.g., "request_prediction|USDJPY|H4"
            base_symbol = SYMBOL_MAIN
            timeframe   = TIMEFRAME

            if msg.startswith("request_prediction"):
                parts = msg.split("|")
                if len(parts) >= 2 and parts[1]:
                    base_symbol = parts[1]
                if len(parts) >= 3 and parts[2]:
                    timeframe = timeframe_from_period(parts[2])

                try:
                    pred = make_prediction(base_symbol, timeframe)
                    sock.send_string(pred)
                    continue
                except Exception as e:
                    err = f"ERROR:{type(e).__name__}:{e}"
                    print("[Predict] ", err)
                    sock.send_string(err)
                    continue

            sock.send_string("unknown_request")

        except zmq.ContextTerminated:
            break
        except Exception as e:
            try:
                sock.send_string(f"ERROR:{type(e).__name__}:{e}")
            except Exception:
                pass
            print(f"[ZMQ] Loop error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()