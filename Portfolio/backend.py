# backend.py
import os, json, time, hashlib
from typing import Optional, Dict, Any
from collections import deque
from fastapi import FastAPI, Header, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

API_KEY = os.getenv("API_KEY", "dev-key")
ALLOW_ORIGINS = ["*"]
LOG_JSONL = os.getenv("LOG_JSONL", "").strip()

ACCOUNT_TTL_SECS = int(os.getenv("ACCOUNT_TTL_SECS", "600"))   # account snapshot staleness window
HISTORY_TTL_SECS = int(os.getenv("HISTORY_TTL_SECS", "0"))     # 0 = never stale; >0 = stale after N secs

app = FastAPI(title="Code-to-Cash Live API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- Stores --------
latest_equity: Dict[str, Any] = {"is_trade_active": False}

latest_account: Dict[str, Any] = {}
latest_account_seen_ts: Optional[float] = None

# Trade history (ENTRY orders only), deduped by position_id
history_by_posid: Dict[str, Dict[str, Any]] = {}
last_history_seen_ts: Optional[float] = None

ingest_log: deque[Dict[str, Any]] = deque(maxlen=100)

# -------- Helpers --------
def _require_key(x_api_key: Optional[str]) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _log_row(row: Dict[str, Any]) -> None:
    ingest_log.append(row)
    print("[INGEST]", json.dumps(row, ensure_ascii=False))
    if LOG_JSONL:
        try:
            with open(LOG_JSONL, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as e:
            print("[LOG_FILE_ERROR]", str(e))

def _round2(v):
    if v is None: return None
    try: return round(float(v), 2)
    except Exception: return None

def _hash_rev(obj: Dict[str, Any]) -> str:
    """Stable revision hash so the UI can skip no-op updates."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()

def _compute_basic_stats() -> Dict[str, Any]:
    # account
    equity  = None
    balance = None
    if latest_account:
        try:
            equity  = float(latest_account.get("equity"))   if latest_account.get("equity")   is not None else None
        except Exception:
            equity = None
        try:
            balance = float(latest_account.get("balance"))  if latest_account.get("balance")  is not None else None
        except Exception:
            balance = None

    # trades
    trades  = list(history_by_posid.values())
    profits = []
    lots_sum = 0.0

    for t in trades:
        # profit may be None if still open; skip Nones
        p = t.get("profit")
        if p is not None:
            try:
                profits.append(float(p))
            except Exception:
                pass
        v = t.get("volume_initial")
        if v is not None:
            try:
                lots_sum += float(v)
            except Exception:
                pass

    wins   = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    decisive = len(wins) + len(losses)

    win_rate       = (100.0 * len(wins) / decisive) if decisive else None
    average_profit = (sum(wins) / len(wins)) if wins else 0.0
    # return average_loss as a NEGATIVE number (mean of losses)
    average_loss   = (sum(losses) / len(losses)) if losses else 0.0

    # average_rrr needs a per-trade risk amount; keep None for now
    average_rrr = None

    return {
        "equity": round(equity, 2) if equity is not None else None,
        "balance": round(balance, 2) if balance is not None else None,
        "win_rate": round(win_rate, 2) if win_rate is not None else None,
        "average_profit": round(average_profit, 2),
        "average_loss": round(average_loss, 2),
        "number_of_trades": len(trades),
        "lots": round(lots_sum, 2),
        "average_rrr": average_rrr,
        # intentionally excluding: sharpe_ratio, expectancy, profit_factor
    }


# -------- Ingest --------
@app.post("/ingest/snapshot")
async def ingest_snapshot(request: Request, x_api_key: Optional[str] = Header(None)):
    global latest_account, latest_account_seen_ts, last_history_seen_ts  # declare once, before any assignment

    _require_key(x_api_key)

    raw = await request.body()
    text = raw.decode("utf-8", errors="ignore").replace("\x00", "").strip()  # strip MT5 nulls
    client = request.client.host if request.client else "?"

    if not text:
        _log_row({"ts": _now_iso(), "client": client, "ok": False, "why": "empty"})
        return {"ok": False, "error": "empty_body"}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        _log_row({"ts": _now_iso(), "client": client, "ok": False, "why": "invalid_json", "preview": text[:300]})
        return {"ok": False, "error": "invalid_json", "detail": str(e)}

    # --- equity (minimal live)
    eq = payload.get("equity_curve")
    if isinstance(eq, dict):
        is_active = bool(eq.get("is_trade_active"))
        if is_active:
            try:
                profit = float(eq.get("profit")) if eq.get("profit") is not None else None
                current_equity = float(eq.get("current_equity")) if eq.get("current_equity") is not None else None
            except Exception:
                latest_equity.clear(); latest_equity.update({"is_trade_active": False})
                _log_row({"ts": _now_iso(), "client": client, "ok": False, "why": "malformed_numbers"})
                return {"ok": False, "error": "malformed_numbers"}
            latest_equity.clear()
            latest_equity.update({
                "profit": profit,
                "current_equity": current_equity,
                "is_trade_active": True,
                "ts": eq.get("t"),
            })
            _log_row({"ts": _now_iso(), "client": client, "ok": True, "active": True,
                      "profit": profit, "equity": current_equity})
        else:
            latest_equity.clear(); latest_equity.update({"is_trade_active": False, "ts": eq.get("t")})
            _log_row({"ts": _now_iso(), "client": client, "ok": True, "active": False})

    # --- account_info (store globally, no login keys)
    acc = payload.get("account_info")
    if isinstance(acc, dict):
        latest_account = dict(acc)  # store as-is for UI fidelity
        latest_account_seen_ts = time.time()
        _log_row({"ts": _now_iso(), "client": client, "ok": True, "account_info": True})

    # --- trade history ingestion (ENTRY orders only)
    hdr = payload.get("history_orders_header")
    if isinstance(hdr, dict):
        last_history_seen_ts = time.time()
        _log_row({"ts": _now_iso(), "client": client, "ok": True, "history_header": True,
                  "from": hdr.get("from"), "to": hdr.get("to"), "count": hdr.get("count")})

    ho = payload.get("history_order")
    if isinstance(ho, dict):
        last_history_seen_ts = time.time()

        # We dedupe by position_id (fallback to ticket if missing)
        pos_id = ho.get("position_id")
        ticket = ho.get("ticket")
        if pos_id is None and ticket is None:
            _log_row({"ts": _now_iso(), "client": client, "ok": False, "why": "history_missing_ids"})
        else:
            key = str(pos_id if pos_id is not None else ticket)

            # Normalize fields (kept close to EA output)
            row_core = {
                "position_id": pos_id,
                "ticket": ticket,
                "symbol": ho.get("symbol"),
                "type": ho.get("type"),
                "state": ho.get("state"),
                "volume_initial": ho.get("volume_initial"),
                "volume_current": ho.get("volume_current"),
                "price_open": ho.get("price_open"),
                "sl": ho.get("sl"),
                "tp": ho.get("tp"),
                "time_setup": ho.get("time_setup"),
                "time_done": ho.get("time_done"),
                "opening_balance": _round2(ho.get("opening_balance")),
                "closing_balance": _round2(ho.get("closing_balance")),
                "profit": _round2(ho.get("profit")),
            }
            rev = _hash_rev(row_core)

            existing = history_by_posid.get(key)
            if not existing or existing.get("rev") != rev:
                row = dict(row_core)
                row["rev"] = rev
                row["updated_at"] = _now_iso()
                history_by_posid[key] = row
                _log_row({"ts": _now_iso(), "client": client, "ok": True,
                          "history_order": True, "position_id": pos_id, "rev_changed": True})

    ft = payload.get("history_orders_footer")
    if ft is True or isinstance(ft, dict):
        _log_row({"ts": _now_iso(), "client": client, "ok": True, "history_footer": True})

    return {"ok": True}

# -------- Public endpoints --------
@app.get("/api/live/equity")
async def get_equity():
    data = {"is_trade_active": bool(latest_equity.get("is_trade_active"))}

    # Include timestamp and a derived date (YYYY-MM-DD) when available
    ts = latest_equity.get("ts")
    if ts:
        data["ts"] = ts
        # robustly derive the date part even if ts has microseconds
        data["trade_date"] = ts.split("T", 1)[0]

    if data["is_trade_active"]:
        data.update({
            "profit": latest_equity.get("profit"),
            "current_equity": latest_equity.get("current_equity"),
        })

    return {"ok": True, "data": data}


@app.get("/api/live/account")
async def get_account():
    if not latest_account:
        return {"ok": False, "message": "no account_info yet"}
    return {"ok": True, "data": latest_account}

@app.get("/api/live/account/needs")
async def needs_account():
    """Returns True if backend doesn't have account_info or it's stale."""
    if not latest_account or latest_account_seen_ts is None:
        return {"ok": True, "needs": True, "reason": "missing"}
    age = time.time() - latest_account_seen_ts
    return {"ok": True, "needs": (age > ACCOUNT_TTL_SECS),
            "age_secs": int(age), "ttl_secs": ACCOUNT_TTL_SECS}

# -------- Trades endpoints (for Lovable + EA handshake) --------
@app.get("/api/live/trades")
async def get_trades():
    """Normalized ENTRY orders, deduped by position_id, newest first."""
    rows = list(history_by_posid.values())
    rows.sort(key=lambda r: (r.get("time_done") or ""), reverse=True)
    return {"ok": True, "count": len(rows), "data": rows}

@app.get("/api/live/trades/needs")
async def needs_trades():
    """
    Ask EA to resend history when backend has none (and, optionally, when stale).
    Default: only ask when missing. Set HISTORY_TTL_SECS>0 to enable staleness.
    """
    if not history_by_posid or last_history_seen_ts is None:
        return {"ok": True, "needs": True, "reason": "missing"}
    if HISTORY_TTL_SECS and HISTORY_TTL_SECS > 0:
        age = time.time() - last_history_seen_ts
        return {"ok": True, "needs": (age > HISTORY_TTL_SECS),
                "age_secs": int(age), "ttl_secs": HISTORY_TTL_SECS}
    return {"ok": True, "needs": False, "reason": "ok"}

@app.get("/api/live/stats")
async def get_stats():
    return {"ok": True, "data": _compute_basic_stats()}

# -------- Debug (optional) --------
@app.get("/debug/ingests")
async def debug_ingests(n: int = Query(20, ge=1, le=100)):
    return {"ok": True, "data": list(ingest_log)[-n:]}

# -------- Main --------
if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=True)
