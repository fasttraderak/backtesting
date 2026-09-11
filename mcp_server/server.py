import json
from datetime import time
from typing import Optional, Dict, Any
from fastmcp import FastMCP

from data.indmoney_client import INDmoneyClient
from data.data_cache import DataCache
from strategy.micro_scalper import MicroScalperStrategy
from strategy.sideways_detector import SidewaysDetector
from backtest.engine import BacktestEngine, BacktestResult
from optimizer.hourly_evaluator import find_optimal_trading_window, compute_hourly_breakdown
from optimizer.param_grid import run_parameter_grid_search
from config.settings import settings

# Initialize FastMCP Server
mcp = FastMCP("NiftyOptionsScalpingBacktester")

# Shared data cache & client
client = INDmoneyClient()
cache = DataCache()


def _get_or_load_data(date_str: str = "2026-09-10"):
    cached_df = cache.load("NIFTY_SESSION", date_str)
    if cached_df is None:
        df = client.get_historical_ticks(symbol="NIFTY", from_date=date_str, to_date=date_str, interval="1s")
        cache.save("NIFTY_SESSION", date_str, df)
        return df
    return cached_df


@mcp.tool()
def run_scalp_backtest(
    lookback_seconds: int = 10,
    check_count: int = 5,
    trigger_diff: float = 2.5,
    target_diff: float = 2.5,
    sl_diff: float = 1.5,
    start_hour: str = "09:15",
    end_hour: str = "15:30",
    trade_instrument: str = "BOTH",
    initial_capital: float = 100000.0,
    lot_size: int = 65
) -> str:
    """
    Executes a high-frequency Nifty Options micro-scalping backtest on sideways market oscillations.
    Models 09:15 to 15:30 session with ₹1,00,000 capital, ₹2-₹3 scalps, Indian taxes, and slippage.
    """
    df = _get_or_load_data()

    s_h, s_m = map(int, start_hour.split(":"))
    e_h, e_m = map(int, end_hour.split(":"))

    strat = MicroScalperStrategy(
        lookback_seconds=lookback_seconds,
        check_count=check_count,
        trigger_diff=trigger_diff,
        target_diff=target_diff,
        sl_diff=sl_diff,
        max_hold_seconds=90,
        strategy_mode="mean_reversion",
        trade_instrument=trade_instrument
    )

    engine = BacktestEngine(
        strategy=strat,
        initial_capital=initial_capital,
        lot_size=lot_size,
        allowed_start_time=time(s_h, s_m),
        allowed_end_time=time(e_h, e_m)
    )

    result: BacktestResult = engine.run(df)
    optimal_window = find_optimal_trading_window(result.hourly_summary)

    output = {
        "parameters": {
            "initial_capital": initial_capital,
            "lot_size": lot_size,
            "lookback_seconds": lookback_seconds,
            "check_count": check_count,
            "trigger_diff": trigger_diff,
            "target_diff": target_diff,
            "sl_diff": sl_diff,
            "trading_hours": f"{start_hour} - {end_hour}",
            "instrument": trade_instrument
        },
        "performance_summary": {
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate_percent": result.win_rate,
            "gross_pnl_inr": result.gross_pnl,
            "taxes_and_brokerage_inr": result.total_charges,
            "net_pnl_inr": result.net_pnl,
            "final_capital_inr": result.final_capital,
            "profit_factor": result.profit_factor,
            "max_drawdown_inr": result.max_drawdown,
            "avg_duration_seconds": result.avg_trade_duration_sec
        },
        "hourly_breakdown": result.hourly_summary,
        "optimal_window_analysis": optimal_window
    }
    return json.dumps(output, indent=2)


@mcp.tool()
def get_hourly_breakdown(
    lookback_seconds: int = 10,
    check_count: int = 5,
    trigger_diff: float = 2.5
) -> str:
    """
    Returns the hourly performance breakdown (09:15 to 15:30) of the sideways micro-scalper
    to show where the strategy performs best (e.g. 11:00 AM to 02:00 PM sweet spot).
    """
    raw_res = run_scalp_backtest(
        lookback_seconds=lookback_seconds,
        check_count=check_count,
        trigger_diff=trigger_diff
    )
    data = json.loads(raw_res)
    hourly = {
        "hourly_breakdown": data["hourly_breakdown"],
        "optimal_window_analysis": data["optimal_window_analysis"]
    }
    return json.dumps(hourly, indent=2)


@mcp.tool()
def optimize_scalp_parameters(top_n: int = 5) -> str:
    """
    Runs a parameter grid search across lookback seconds, sampling checks, and trigger sizes,
    returning the top performing configurations sorted by Net PnL.
    """
    df = _get_or_load_data()
    top_results = run_parameter_grid_search(df, top_n=top_n)
    return json.dumps({"top_parameter_configurations": top_results}, indent=2)


if __name__ == "__main__":
    mcp.run()
