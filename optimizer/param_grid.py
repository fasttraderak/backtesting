from typing import List, Dict, Any, Optional
import itertools
from datetime import time
import pandas as pd
from strategy.micro_scalper import MicroScalperStrategy
from backtest.engine import BacktestEngine, BacktestResult


def run_parameter_grid_search(
    df: pd.DataFrame,
    lookback_options: Optional[List[int]] = None,
    check_counts: Optional[List[int]] = None,
    trigger_diffs: Optional[List[float]] = None,
    target_diffs: Optional[List[float]] = None,
    sl_diffs: Optional[List[float]] = None,
    initial_capital: float = 100000.0,
    lot_size: int = 65,
    top_n: int = 5
) -> List[Dict[str, Any]]:
    """
    Executes a parameter sweep over combinations of lookback seconds, sampling checks,
    and trigger displacements.
    """
    lookback_options = lookback_options or [5, 10, 15]
    check_counts = check_counts or [3, 5]
    trigger_diffs = trigger_diffs or [2.0, 2.5]
    target_diffs = target_diffs or [2.5]
    sl_diffs = sl_diffs or [1.5]

    combinations = list(itertools.product(
        lookback_options,
        check_counts,
        trigger_diffs,
        target_diffs,
        sl_diffs
    ))

    results = []

    for lb, chk, trig, tgt, sl in combinations:
        strat = MicroScalperStrategy(
            lookback_seconds=lb,
            check_count=chk,
            trigger_diff=trig,
            target_diff=tgt,
            sl_diff=sl,
            max_hold_seconds=90,
            strategy_mode="mean_reversion",
            trade_instrument="BOTH"
        )
        engine = BacktestEngine(
            strategy=strat,
            initial_capital=initial_capital,
            lot_size=lot_size
        )
        res: BacktestResult = engine.run(df)

        results.append({
            "lookback_seconds": lb,
            "check_count": chk,
            "trigger_diff": trig,
            "target_diff": tgt,
            "sl_diff": sl,
            "total_trades": res.total_trades,
            "win_rate": res.win_rate,
            "net_pnl": res.net_pnl,
            "total_charges": res.total_charges,
            "profit_factor": res.profit_factor,
            "max_drawdown": res.max_drawdown
        })

    # Sort by Net PnL descending
    sorted_results = sorted(results, key=lambda x: x["net_pnl"], reverse=True)
    return sorted_results[:top_n]
