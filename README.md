# Code-to-Cash
Code to Cash is an end-to-end algorithmic Forex trading system that harnesses deep learning to forecast currency movements and executes trades automatically via MQL5.
## 📖 About
**Code to Cash** provides a modular foundation for:
- **Data pipelines**: Ingest and preprocess tick-level and OHLC market data.
- **Model training**: Jupyter notebook workflows to train neural networks to predict the direction of the market.
- **Backtesting**: Evaluate strategies on historical data.
- **Live execution**: MQL5 Expert Advisor for seamless deployment on MetaTrader 5, including risk management and position sizing.
## 🔍 How the Algorithm Works
### 1. Fetching Predictions
- **Backtest Mode**  
  - The algorithm uses two parallel arrays, `times[]` and `predictions[]`, which contain predictions the model would have made for the time are hard-coded at compile time.  
- **Live Mode**  
  - Instead of hard-coded arrays, the algorithm fetches the latest prediction for each 4 H bar directly from the trained model via a ZeroMQ socket.
### 2. Trading Window  
   - Only runs between `StartHour:StartMinute` and `EndHour:EndMinute` (local or broker time).  
   - Outside that window it closes any open positions, deletes pending orders, and resets flags.
### 3. On Each New Bar
   - Aligns the current 4H candle time to pick up the latest prediction.  
   - Computes the highest high and lowest low over the past `HighLowBars` bars (breakout levels).
### 4. Entry Logic
   - **Buy prediction** → place a **BuyStop** at the recent high;  
     stop-loss at the recent low;  
     take-profit at `stop-loss distance × RiskToRewardRatio`.  
   - **Sell prediction** → place a **SellStop** at the recent low;  
     stop-loss at the recent high;  
     take-profit at `stop-loss distance × RiskToRewardRatio`.  
   - Ensures only one pending “buy” and one “sell” order per bar via `glBuyPlaced`/`glSellPlaced` flags.
### 5. Money Management
   - If `UseMoneyManagement` is true, `MoneyManagement()` computes position size from `RiskPercent`;  
   - Otherwise it uses a fixed lot (`FixedVolume`).
### 6. Optional Risk Controls
   - **Break-even**: once a trade reaches `BreakEvenRatio` in profit, moves SL to break-even with an optional `LockProfit`.  
   - (Trailing-stop code is included but disabled by default.)


## 📂 Repository Structure
- **training** - CSVs or raw files for model training
- **testing** - CSVs or raw files for out-of-sample testing
- **`code_to_cash_usdjpy_h4_02-08-25.ipynb`** - Jupyter notebook: train & evaluate model
- **`code_to_cash_usdjpy_h4_2022-2025_predictions.txt`** Text file: generated predictions on unseen data
- **`usdjpy_breakout_backtest.mq5`** - MQL5 Expert Advisor: backtesting algos in MT5
- **`receive_predictions.mq5`** – MQL5 script to test receiving predictions from Python via ZeroMQ  
- **`send_ctc_v1_predictions.py`** – Python prediction server that loads the trained model, fetches market data, generates features, and serves predictions to MT5 over ZeroMQ
### MQL5 Includes
Custom and third-party helper classes used by the EA:

- **Include/Money/**  
  - `MoneyManagement.mqh` – dynamic lot sizing and risk-based position sizing  

- **Include/Trade/**  
  - `Trade.mqh` – standard CTrade wrapper for order execution  
  - `TradeBook.mqh` – helper class for tracking and managing multiple orders  
  - `TrailingStops.mqh` – utility functions for trailing stop management  

- **Include/Zmq/**  
  - `AtomicCounter.mqh`, `Context.mqh`, `Errno.mqh`, `Socket.mqh`,  
    `SocketOptions.mqh`, `Z85.mqh`, `Zmq.mqh`, `ZmqMsg.mqh` – ZeroMQ bindings for MQL5 to communicate with Python services
