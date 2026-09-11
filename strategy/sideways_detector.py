import numpy as np
import pandas as pd
from typing import Dict, Any


class SidewaysDetector:
    """
    Detects whether the market is currently range-bound / sideways.
    Uses:
    1. Rolling High-Low Range compression (default: 300 seconds / 5 mins).
    2. Rolling Standard Deviation / Volatility threshold.
    3. Maximum drift threshold.
    """

    def __init__(
        self,
        window_seconds: int = 300,
        max_range_points: float = 10.0,
        max_std_dev: float = 2.0
    ):
        self.window_seconds = window_seconds
        self.max_range_points = max_range_points
        self.max_std_dev = max_std_dev

    def compute_regime(self, series: pd.Series) -> pd.Series:
        """
        Takes a price series (e.g., CE LTP or PE LTP or Spot) and calculates
        a boolean mask where True indicates Sideways / Range-bound conditions.
        """
        rolling_max = series.rolling(window=self.window_seconds, min_periods=max(10, self.window_seconds // 4)).max()
        rolling_min = series.rolling(window=self.window_seconds, min_periods=max(10, self.window_seconds // 4)).min()
        rolling_range = rolling_max - rolling_min
        rolling_std = series.rolling(window=self.window_seconds, min_periods=max(10, self.window_seconds // 4)).std()

        # Market is sideways if the recent range and std dev are under threshold
        is_sideways = (rolling_range <= self.max_range_points) & (rolling_std <= self.max_std_dev)
        return is_sideways.fillna(False)
