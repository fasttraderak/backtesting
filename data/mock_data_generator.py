import numpy as np
import pandas as pd
from datetime import datetime, time, timedelta
from typing import Optional


def generate_nifty_options_session_data(
    target_date: str = "2026-09-10",
    initial_spot: float = 24500.0,
    atm_strike: float = 24500.0,
    base_ce_prem: float = 125.0,
    base_pe_prem: float = 120.0,
    seed: int = 42
) -> pd.DataFrame:
    """
    Generates realistic second-by-second (1s) tick data for a full trading day (09:15:00 to 15:30:00).
    Total seconds: 6 hours 15 mins = 22,500 seconds.

    Market Regimes modeled:
    - 09:15 - 10:15: Opening volatility, high standard deviation, sudden spikes.
    - 10:15 - 11:15: Morning settling, moderate volatility.
    - 11:15 - 14:00: Sideways consolidation, range-bound mean-reversion, frequent ₹2.0-₹3.0 micro-oscillations!
    - 14:00 - 15:30: Afternoon volume surge, trending gamma spikes, closing momentum.
    """
    np.random.seed(seed)
    
    start_dt = datetime.strptime(f"{target_date} 09:15:00", "%Y-%m-%d %H:%M:%S")
    num_seconds = 6 * 3600 + 15 * 60  # 22,500 seconds
    timestamps = [start_dt + timedelta(seconds=i) for i in range(num_seconds)]

    # Arrays for prices
    ce_prices = np.zeros(num_seconds)
    pe_prices = np.zeros(num_seconds)
    spot_prices = np.zeros(num_seconds)
    bid_spreads = np.zeros(num_seconds)
    ask_spreads = np.zeros(num_seconds)

    curr_ce = base_ce_prem
    curr_pe = base_pe_prem
    curr_spot = initial_spot

    for i, ts in enumerate(timestamps):
        current_time = ts.time()
        
        # 1. Opening Volatility (09:15 - 10:15)
        if time(9, 15) <= current_time < time(10, 15):
            ce_vol = 0.35
            pe_vol = 0.35
            drift_ce = np.random.choice([-0.02, 0.02, 0.05, -0.05])
            drift_pe = -drift_ce
            spread = 0.20
            
        # 2. Morning Settling (10:15 - 11:15)
        elif time(10, 15) <= current_time < time(11, 15):
            ce_vol = 0.20
            pe_vol = 0.20
            drift_ce = 0.0
            drift_pe = 0.0
            spread = 0.15
            
        # 3. Sideways Range-Bound Golden Window (11:15 - 14:00)
        elif time(11, 15) <= current_time < time(14, 0):
            # Strong mean reversion back towards baseline with micro-oscillations of 2-3 rupees
            ce_vol = 0.14
            pe_vol = 0.14
            # Ornstein-Uhlenbeck style mean reversion
            theta = 0.008
            drift_ce = -theta * (curr_ce - base_ce_prem)
            drift_pe = -theta * (curr_pe - base_pe_prem)
            spread = 0.10
            
        # 4. Afternoon & Closing Fluctuation (14:00 - 15:30)
        else:
            ce_vol = 0.40
            pe_vol = 0.40
            drift_ce = np.random.choice([-0.06, 0.06, 0.03, -0.03])
            drift_pe = -drift_ce * 0.9
            spread = 0.25

        # Update CE with small random step + micro jumps
        jump_ce = 0.0
        if np.random.rand() < 0.015:  # 1.5% chance of micro-displacement (2 to 3 rupee shift)
            jump_ce = np.random.choice([-2.5, -2.0, 2.0, 2.5, 3.0])
            
        step_ce = np.random.normal(drift_ce, ce_vol) + jump_ce
        curr_ce = max(5.0, curr_ce + step_ce)

        # Update PE
        jump_pe = 0.0
        if np.random.rand() < 0.015:
            jump_pe = np.random.choice([-2.5, -2.0, 2.0, 2.5, 3.0])
            
        step_pe = np.random.normal(drift_pe, pe_vol) + jump_pe
        curr_pe = max(5.0, curr_pe + step_pe)

        # Update Spot
        curr_spot += (step_ce - step_pe) * 1.2

        ce_prices[i] = round(curr_ce, 2)
        pe_prices[i] = round(curr_pe, 2)
        spot_prices[i] = round(curr_spot, 2)
        bid_spreads[i] = round(spread, 2)
        ask_spreads[i] = round(spread, 2)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "spot": spot_prices,
        "ce_ltp": ce_prices,
        "ce_bid": np.round(ce_prices - bid_spreads, 2),
        "ce_ask": np.round(ce_prices + ask_spreads, 2),
        "pe_ltp": pe_prices,
        "pe_bid": np.round(pe_prices - bid_spreads, 2),
        "pe_ask": np.round(pe_prices + ask_spreads, 2),
        "atm_strike": atm_strike
    })
    return df
