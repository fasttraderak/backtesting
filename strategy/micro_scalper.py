from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
import pandas as pd
import numpy as np


class ScalpSignal(BaseModel):
    timestamp: datetime
    instrument_type: str  # "CE" or "PE"
    signal_type: str       # "BUY"
    current_price: float
    trigger_delta: float
    target_price: float
    stop_loss_price: float
    lookback_seconds: int
    check_count: int
    reason: str


class MicroScalperStrategy:
    """
    Micro-scalping strategy designed for sideways option premiums.
    Monitors price displacement over N lookback seconds across K check samples.
    """

    def __init__(
        self,
        lookback_seconds: int = 10,
        check_count: int = 5,
        trigger_diff: float = 2.5,
        target_diff: float = 2.5,
        sl_diff: float = 1.5,
        max_hold_seconds: int = 90,
        strategy_mode: str = "mean_reversion",  # "mean_reversion" or "momentum"
        trade_instrument: str = "BOTH"          # "CE", "PE", or "BOTH"
    ):
        self.lookback_seconds = max(2, lookback_seconds)
        self.check_count = max(2, check_count)
        self.trigger_diff = trigger_diff
        self.target_diff = target_diff
        self.sl_diff = sl_diff
        self.max_hold_seconds = max_hold_seconds
        self.strategy_mode = strategy_mode
        self.trade_instrument = trade_instrument

    def evaluate_signal(
        self,
        current_idx: int,
        timestamps: np.ndarray,
        prices: np.ndarray,
        is_sideways_array: np.ndarray,
        instrument: str
    ) -> Optional[ScalpSignal]:
        """
        Evaluates whether a buy signal should be generated at current_idx for the given instrument.
        """
        # 1. Must be in a sideways market regime
        if not is_sideways_array[current_idx]:
            return None

        # 2. Check sufficient history for lookback
        if current_idx < self.lookback_seconds:
            return None

        current_price = prices[current_idx]
        current_ts = timestamps[current_idx]

        # 3. Sample check_count points over lookback_seconds
        step = max(1, self.lookback_seconds // self.check_count)
        sample_indices = [current_idx - (i * step) for i in range(self.check_count, 0, -1)]
        sample_prices = [prices[idx] for idx in sample_indices]
        ref_price = np.mean(sample_prices)

        price_delta = current_price - ref_price

        # 4. Signal logic
        if self.strategy_mode == "mean_reversion":
            # In a sideways market, when price drops by trigger_diff (e.g. -2.0 to -3.0),
            # buy the dip expecting mean-reversion rebound
            if price_delta <= -self.trigger_diff:
                target = round(current_price + self.target_diff, 2)
                sl = round(current_price - self.sl_diff, 2)
                return ScalpSignal(
                    timestamp=pd.to_datetime(current_ts),
                    instrument_type=instrument,
                    signal_type="BUY",
                    current_price=round(current_price, 2),
                    trigger_delta=round(price_delta, 2),
                    target_price=target,
                    stop_loss_price=sl,
                    lookback_seconds=self.lookback_seconds,
                    check_count=self.check_count,
                    reason=f"Dip of ₹{abs(price_delta):.2f} detected in {self.lookback_seconds}s. Mean reversion scalp."
                )
        elif self.strategy_mode == "momentum":
            # If price surges by trigger_diff (+2.0 to +3.0) with micro-momentum
            if price_delta >= self.trigger_diff:
                target = round(current_price + self.target_diff, 2)
                sl = round(current_price - self.sl_diff, 2)
                return ScalpSignal(
                    timestamp=pd.to_datetime(current_ts),
                    instrument_type=instrument,
                    signal_type="BUY",
                    current_price=round(current_price, 2),
                    trigger_delta=round(price_delta, 2),
                    target_price=target,
                    stop_loss_price=sl,
                    lookback_seconds=self.lookback_seconds,
                    check_count=self.check_count,
                    reason=f"Impulse surge of ₹{price_delta:.2f} detected in {self.lookback_seconds}s. Momentum scalp."
                )

        return None
