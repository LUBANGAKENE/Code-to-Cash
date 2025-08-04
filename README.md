# Code-to-Cash
Code to Cash is an end-to-end algorithmic Forex trading system that harnesses deep learning to forecast currency movements and executes trades automatically via MQL5.
## 📖 About
**Code to Cash** provides a modular foundation for:
- **Data pipelines**: Ingest and preprocess tick-level and OHLC market data.
- **Model training**: Jupyter notebook workflows to train neural networks to predict the direction of the market.
- **Backtesting**: Evaluate strategies on historical data.
- **Live execution**: MQL5 Expert Advisor for seamless deployment on MetaTrader 5, including risk management and position sizing.
## 📂 Repository Structure
- **training** - CSVs or raw files for model training
- **testing** - CSVs or raw files for out-of-sample testing
- **code_to_cash_usdjpy_h4_02-08-25.ipynb** - Jupyter notebook: train & evaluate model
- **code_to_cash_usdjpy_h4_2022-2025_predictions.txt** Text file: generated predictions on unseen data
- **usdjpy_breakout_backtest.mq5** - MQL5 Expert Advisor: backtesting algos in MT5
