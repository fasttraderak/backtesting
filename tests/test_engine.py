from data.mock_data_generator import generate_nifty_options_session_data
from strategy.micro_scalper import MicroScalperStrategy
from backtest.engine import BacktestEngine
from optimizer.hourly_evaluator import find_optimal_trading_window


def test_backtest_engine_run():
    # Generate 1 session of 1s ticks
    df = generate_nifty_options_session_data(seed=123)
    assert len(df) == 22500

    strat = MicroScalperStrategy(
        lookback_seconds=10,
        check_count=5,
        trigger_diff=2.5,
        target_diff=2.5,
        sl_diff=1.5
    )

    engine = BacktestEngine(
        strategy=strat,
        initial_capital=100000.0,
        lot_size=65
    )

    res = engine.run(df)
    assert res.total_trades >= 0
    assert len(res.hourly_summary) == 6
    assert res.final_capital > 0

    opt = find_optimal_trading_window(res.hourly_summary)
    assert "recommendation" in opt
