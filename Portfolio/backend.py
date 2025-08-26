# backend.py
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from collections import deque
from typing import Optional, Deque, Dict, Any
import uvicorn, os, time

API_KEY = os.getenv("API_KEY", "dev-key")

app = FastAPI(title="Code to Cash Live API")

# CORS for your dashboard domain(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_snapshot: Dict[str, Any] = {}
equity_series: Deque[Dict[str, Any]] = deque(maxlen=5000)  # simple in-memory store

@app.post("/ingest/snapshot")
async def ingest_snapshot(payload: Dict[str, Any], x_api_key: Optional[str] = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    global latest_snapshot
    latest_snapshot = payload
    if "equity_point" in payload:
        equity_series.append(payload["equity_point"])
    return {"ok": True}

@app.get("/api/live/snapshot")
async def get_snapshot():
    if not latest_snapshot:
        return {"ok": False, "message": "no data yet"}
    return {"ok": True, "data": latest_snapshot}

@app.get("/api/live/equity")
async def get_equity():
    return {"ok": True, "data": list(equity_series)}

if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=True)
