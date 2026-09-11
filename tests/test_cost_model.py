import pytest
from backtest.cost_model import calculate_trade_costs


def test_cost_calculation():
    # Buy 1 lot (65 qty) of Nifty at 120, sell at 122.5 (₹2.5 gain)
    res = calculate_trade_costs(
        buy_price=120.0,
        sell_price=122.5,
        quantity=65,
        slippage_per_leg=0.10,
        brokerage_per_order=20.0
    )
    assert res.quantity == 65
    assert res.gross_pnl > 0
    assert res.brokerage == 40.0  # 20 buy + 20 sell
    assert res.stt > 0
    assert res.total_taxes_charges > 40.0
    assert res.net_pnl < res.gross_pnl
