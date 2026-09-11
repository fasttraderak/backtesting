import numpy as np
import pandas as pd
from strategy.sideways_detector import SidewaysDetector
from strategy.micro_scalper import MicroScalperStrategy


def test_sideways_detector():
    detector = SidewaysDetector(window_seconds=10, max_range_points=5.0, max_std_dev=1.0)
    # Range bound prices
    flat_prices = pd.Series([100.0 + (i % 2) * 0.5 for i in range(50)])
    mask = detector.compute_regime(flat_prices)
    assert mask.iloc[-1] == True

    # Wildly trending prices
    trend_prices = pd.Series([100.0 + i * 2.0 for i in range(50)])
    mask_trend = detector.compute_regime(trend_prices)
    assert mask_trend.iloc[-1] == False


def test_micro_scalper_trigger():
    strat = MicroScalperStrategy(
        lookback_seconds=5,
        check_count=3,
        trigger_diff=2.5,
        target_diff=2.5,
        sl_diff=1.5,
        strategy_mode="mean_reversion"
    )

    timestamps = pd.date_range("2026-09-10 11:30:00", periods=10, freq="1s").values
    # Prices drop sharply from 125.0 to 121.0 (-4.0 drop)
    prices = np.array([125.0, 125.0, 125.0, 125.0, 125.0, 125.0, 125.0, 121.0, 121.0, 121.0])
    is_sideways = np.array([True] * 10)

    sig = strat.evaluate_signal(
        current_idx=7,
        timestamps=timestamps,
        prices=prices,
        is_sideways_array=is_sideways,
        instrument="CE"
    )

    assert sig is not None
    assert sig.signal_type == "BUY"
    assert sig.target_price == round(121.0 + 2.5, 2)
    assert sig.stop_loss_price == round(121.0 - 1.5, 2)
