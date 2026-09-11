# Comprehensive Architecture & Execution Plan: Nifty Options Micro-Scalping Backtester

> **Target Instrument**: Nifty 50 Index Options (CE & PE)  
> **Core Concept**: Sideways Market Micro-Movement Scalping (₹2 to ₹3 Target/Trigger)  
> **Broker / Data Provider**: INDmoney API  
> **Initial Capital**: ₹1,00,000 (1 Lakh INR)  
> **Trading Hours**: 09:15 AM to 03:30 PM (Detailed Hourly Window Breakdown)  
> **Integration Layer**: Python FastMCP (Model Context Protocol for AI Agent & UI orchestration)  

---

## 1. Executive Summary & Strategy Philosophy

### 1.1 The Core Idea
In typical trading sessions, especially between **11:00 AM and 02:00 PM**, the broader index frequently enters range-bound consolidation (sideways market). During these periods:
- Premium values of At-The-Money (ATM) and Near-The-Money (NTM) options oscillate back and forth within tight bands.
- Quick micro-movements of **₹2.00 to ₹3.00** occur repeatedly due to minor order book imbalances and micro-bursts before reverting.
- Instead of holding for large directional moves (which risk rapid theta decay in sideways markets), this strategy captures rapid **₹2.00 – ₹3.00 scalps** with a tight stop-loss (₹1.50 – ₹2.00) and strict time-based exits (e.g., exit if target not achieved within $N$ seconds).

### 1.2 The Critical Challenge & Solution
Micro-scalping (₹2 to ₹3 profit) is extremely sensitive to:
1. **Slippage & Latency**: Executing at sub-optimal ticks damages expectancy.
2. **Statutory Taxes & Brokerage**: STT, exchange turnover fees, GST, and SEBI charges can erode small profits if trade count is too high without edge.
3. **Time-of-Day Volatility Variations**: Morning (09:15 - 10:15) and market close (14:00 - 15:30) have high gamma and sharp swings where sideways scalping fails.

**The Solution**:
A high-resolution tick/second-level backtester that tests multiple lookback windows, dynamic sideways filters, strict slippage/tax modeling, and breaks down performance across **every 1-hour window** from 9:15 to 15:30 to scientifically identify the **"Golden Hours"** and optimum parameters.

---

## 2. System Architecture

The project is structured into modular layers, exposed to AI agents and web interfaces through **FastMCP**:

```
d:\open project\backtesting\
├── config/
│   ├── __init__.py
│   ├── settings.py              # Capital, brokerage, default lookbacks, API keys
│   └── constants.py             # Lot sizes (Nifty=25/50), market hours, exchange charges
├── data/
│   ├── __init__.py
│   ├── indmoney_client.py       # INDmoney API authentication & historical data fetcher
│   ├── data_cache.py            # Local tick/second Parquet/SQLite storage
│   └── mock_data_generator.py   # High-fidelity synthetic tick generator for offline testing
├── strategy/
│   ├── __init__.py
│   ├── sideways_detector.py     # Chop Index, ATR, Bollinger Band squeeze, Range filters
│   ├── micro_scalper.py         # Lookback seconds, tick counter, ₹2-₹3 trigger logic
│   └── base_strategy.py        # Abstract strategy class
├── backtest/
│   ├── __init__.py
│   ├── engine.py                # Second-by-second event-driven simulation loop (09:15-15:30)
│   ├── order_matcher.py         # Realistic fill engine with slippage & bid-ask spread
│   ├── portfolio.py             # Cash tracking (₹1L), margin requirements, position tracking
│   └── cost_model.py            # Indian regulatory charges (STT, GST, Exchange, Brokerage)
├── optimizer/
│   ├── __init__.py
│   ├── param_grid.py            # Grid search over lookbacks (5s-60s), sample checks, triggers
│   └── hourly_evaluator.py      # Hourly segmentation & statistical significance tests
├── analytics/
│   ├── __init__.py
│   ├── metrics.py               # Sharpe, Sortino, Max DD, Win Rate, Profit Factor
│   ├── hourly_reports.py        # 1-hour window PnL & win rate breakdown
│   └── visualizer.py            # Equity curve, drawdown plot, hourly heatmaps
├── mcp/
│   ├── __init__.py
│   └── server.py                # FastMCP server exposing tools & resources for Agent/UI
├── ui/
│   └── app.py                   # Streamlit interactive UI dashboard
├── tests/
│   ├── test_indmoney.py
│   ├── test_engine.py
│   └── test_strategy.py
├── requirements.txt
├── .env.example
└── plan.md                      # This master plan
```

---

## 3. Detailed Strategy Mechanics

### 3.1 Market Regime Filter (Detecting Sideways Market)
Before triggering any scalps, the engine verifies if the market is range-bound:
1. **Index ADX / Chop Filter**:
   - `ADX(14) < 20` on 1-minute or 3-minute bars (indicates lack of directional trend).
   - OR `Choppiness Index > 61.8` (signaling consolidation).
2. **Micro-Range Boundaries**:
   - Nifty Index or Option Strike 15-minute high/low range is within $R_{max}$ points.
   - Premium volatility is compressed (Bollinger Band width percentile < 30%).

### 3.2 Micro-Movement & Lookback Sampling Logic
Once a sideways regime is confirmed, the strategy analyzes micro-structure price shifts on ATM/NTM CE & PE:

- **Lookback Window ($T_{lookback}$)**:
  - Backtest range: `[3s, 5s, 10s, 15s, 30s, 60s]`.
- **Sample Frequency / Check Count ($K_{checks}$)**:
  - How many snapshots/ticks evaluated inside the lookback window (e.g., every 1s, 2s, or last $N$ consecutive ticks).
- **Trigger Condition ($\Delta P$)**:
  - **Mean-Reversion Dip Buy (Primary)**:
    - If price dropped by ₹2.00 – ₹3.00 from the rolling mean/VWAP of the lookback window without breaking lower support $\rightarrow$ **BUY**.
  - **Micro-Momentum Impulse**:
    - If price suddenly increases by ₹2.00 – ₹3.00 within $T_{lookback}$ on volume spike $\rightarrow$ **BUY** to capture continuation up to target.
  - **Dual Mode (Both CE & PE)**:
    - Evaluate both legs simultaneously. If market is purely sideways, both CE and PE oscillate; take independent micro-scalps with individual limits.

### 3.3 Trade Execution & Exit Rules
- **Entry**: Market Buy on ATM Strike (determined dynamically at entry time).
- **Target**: Entry + ₹2.00 (Configurable: ₹2.00, ₹2.50, ₹3.00).
- **Stop Loss (SL)**: Entry - ₹1.50 (Configurable: ₹1.00, ₹1.50, ₹2.00).
- **Time Stop**: If neither Target nor SL is hit within $T_{max}$ (e.g., 90 seconds or 180 seconds), exit immediately at market to avoid adverse drift.
- **Trailing SL (Optional)**: Move SL to breakeven once price gains +₹1.50.

---

## 4. Capital, Risk & Cost Management

### 4.1 Capital Allocation (₹1,00,000)
- **Margin Required**:
  - Buying 1 lot of Nifty ATM Option (Lot size = 25 or 50):
  - Average premium = ₹100 to ₹150 $\rightarrow$ Capital required per lot = ₹2,500 to ₹7,500.
  - 1-2 lots per trade ensures max position size is strictly < 10% of total capital (₹10,000), leaving ample cushion.
- **Risk Budget**:
  - Max risk per trade: ₹1.50 SL $\times$ 50 qty = ₹75 to ₹150 (approx 0.1% to 0.15% of ₹1L capital).
  - Max Daily Loss Cap: ₹2,500 (2.5%). If breached, trading terminates for the day.
  - Max Trades Per Day: Configurable (e.g., max 15-20 trades) to avoid overtrading churn.

### 4.2 Realistic Transaction Cost Model (Crucial for Micro-Scalping)
Micro-scalping with ₹2-₹3 target can fail in real trading if taxes are ignored. The engine calculates exact Indian exchange costs per completed round-trip trade:
1. **Brokerage**: ₹20 per executed order (or zero brokerage model if configured).
2. **STT (Securities Transaction Tax)**: 0.0625% on sell turnover for options premium.
3. **Exchange Turnover Charges**: NSE charges approx 0.0505% on premium turnover.
4. **GST**: 18% on (Brokerage + Exchange Charges).
5. **SEBI Charges**: ₹10 per crore.
6. **Stamp Duty**: 0.003% on buy turnover.
7. **Slippage Simulation**: ₹0.10 to ₹0.25 per leg (bid-ask spread gap penalty).

---

## 5. Hourly Performance Breakdown (09:15 to 15:30)

The backtesting engine splits every day's execution into distinct 1-hour sessions to pinpoint time-of-day edge:

| Session Time | Market Characteristic | Strategy Hypothesis |
| :--- | :--- | :--- |
| **09:15 - 10:15** | Opening bell, high volatility, overnight gap reactions. | **High Risk**: Stop-losses hit frequently. Expect negative or erratic returns. |
| **10:15 - 11:15** | Post-opening consolidation, initial trend formation. | **Moderate**: Strategy begins stabilizing as ATR shrinks. |
| **11:15 - 12:15** | Low volume, typical range-bound drift. | **High Edge (Golden Zone 1)**: Sideways ₹2-₹3 oscillations flourish. |
| **12:15 - 13:15** | Midday lunch lull, European pre-market calmness. | **High Edge (Golden Zone 2)**: Ideal for mean-reversion micro-scalping. |
| **13:15 - 14:15** | European open effects, slow build-up to expiry moves. | **Moderate to High**: Good consistency if trend filters are active. |
| **14:15 - 15:30** | Afternoon gamma spikes, 3 PM institutional moves. | **High Risk**: Large directional swings destroy range scalps. |

### Output Deliverable:
An **Hourly Heatmap & Performance Matrix** displaying:
- Hourly Win Rate (%)
- Hourly Net PnL (after brokerage and taxes)
- Hourly Profit Factor
- Hourly Max Drawdown
- Automated recommendation: **"Optimal Trading Window"** (e.g., Disable strategy from 09:15-10:15 and 14:15-15:30; run only 11:00-14:00).

---

## 6. INDmoney API Integration

### 6.1 Data Ingestion Architecture
- Connect to INDmoney developer/broker API endpoints:
  - Authentication / Access token lifecycle.
  - Option Chain endpoint: Fetch ATM, OTM, ITM strike identifiers for Nifty weekly contracts.
  - Historical Candle / Tick Data endpoint: Ingest second-by-second (or sub-minute tick) historical data.
- **Local Caching Layer**:
  - Downloaded historical tick datasets are cached locally in Apache Parquet / DuckDB format under `data/cache/`.
  - Avoids re-requesting the API during repeated parameter sweeps and protects against rate limiting.
- **Offline / Mock Data Generator**:
  - Provides realistic simulated tick data with synthetic order-book bid-ask spreads for instant testing before live API credentials are supplied.

---

## 7. FastMCP Server Integration (Model Context Protocol)

FastMCP provides an agent-native interface to query, execute, and calibrate backtests. Any AI agent (e.g. Claude Desktop, Antigravity Agent) or custom UI interacts via standardized tools:

### FastMCP Tools Exposed:
1. `indmoney_sync_data(symbol, start_date, end_date, interval)`:
   - Fetches and stores option chain tick data via INDmoney API.
2. `run_single_backtest(lookback_seconds, check_count, trigger_diff, target_diff, sl_diff, start_time, end_time)`:
   - Executes a single backtest run with specified parameters and capital ₹1,00,000.
3. `run_parameter_optimization(lookback_range, trigger_range, time_windows)`:
   - Performs a grid sweep and returns the top 5 parameter sets sorted by Sharpe Ratio and Net PnL.
4. `get_hourly_breakdown(backtest_id)`:
   - Returns JSON stats of hourly performance (9:15-10:15, 10:15-11:15, etc.) and highlights the optimal window.
5. `export_backtest_report(backtest_id, format)`:
   - Generates an HTML/Markdown report with trade logs, slippage impact, and equity curve.

---

## 8. AI Agent Integration (Quant Analyst Agent with Gemini)

### 8.1 LLM Endpoint Configuration
The system integrates an autonomous Strategy Agent utilizing the custom OpenAI-compatible endpoint configured with Gemini models:
- **Base URL**: `https://ai.quantflash.cloud/v1`
- **API Key**: `sk-antigravity`
- **Default Models**:
  - `gemini-3.8-flash-high` (High speed, deep reasoning for parameter sweeps and log analysis)
  - `gemini-pro-agent` / `gemini-3.1-pro-high` (For comprehensive strategy review and risk management)
- **Interface**: OpenAI-compatible Chat Completions with function/tool calling.

### 8.2 Agent Capabilities
- **Autonomous Optimization Loop**: Agent calls FastMCP tools, analyzes hourly performance matrices, identifies unprofitable hours (e.g. 09:15-10:15 morning chop), and recommends optimal lookback windows (e.g. 10s lookback, ₹2.5 trigger, running exclusively between 11:00 AM - 02:00 PM).
- **Natural Language Interaction**: User can query in Hindi/Hinglish/English: *"11 bje se 2 bje ke beech best parameters kya hain?"* and the Agent executes backtests, parses JSON outputs, and replies with actionable insights.

---

## 9. Step-by-Step Implementation Roadmap

### Phase 1: Environment & Foundation
- Set up project structure, virtual environment, and dependencies (`fastmcp`, `openai`, `pandas`, `numpy`, `plotly`, `streamlit`, `pydantic`, `python-dotenv`).
- Build configuration module with capital rules (₹1,00,000), LLM proxy settings (`https://ai.quantflash.cloud/v1`), Nifty lot sizes, and Indian statutory tax calculations (`cost_model.py`).

### Phase 2: Data Layer & INDmoney Client
- Implement `indmoney_client.py` for authentication, option chain retrieval, and historical tick ingestion.
- Implement caching with Parquet/SQLite and high-fidelity mock generator for immediate testing.

### Phase 3: Core Strategy & Sideways Filter
- Develop `sideways_detector.py` (ADX, Chop Index, Range compression).
- Develop `micro_scalper.py` with parameterizable lookback seconds, sampling count, and ₹2-₹3 trigger conditions.

### Phase 4: Event-Driven Backtesting Engine
- Build `engine.py` simulating 09:15 to 15:30 timeline.
- Implement realistic order fills with bid-ask spread and slippage.
- Integrate portfolio state management (₹1L capital, margin checks, daily loss cutoff).

### Phase 5: Hourly Analytics & Optimization
- Create `hourly_evaluator.py` to segment trades into 60-minute blocks.
- Generate comparative metrics to identify the best time window (e.g., 11:00 AM - 2:00 PM).
- Run parameter sweeps across lookback durations (5s to 60s) and target/SL ratios.

### Phase 6: FastMCP Server & Gemini Agent
- Build `mcp/server.py` using `fastmcp` to expose tools to agents.
- Build `agent/strategy_agent.py` invoking Gemini via the custom endpoint to autonomously guide the backtesting process.

### Phase 7: UI & Verification
- Build interactive Streamlit dashboard (`ui/app.py`) with visual heatmaps, equity curves, and Gemini Agent chat.
- Execute automated tests across data, strategy, engine, and MCP server.
