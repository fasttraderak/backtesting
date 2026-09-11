from typing import List, Dict, Any
from datetime import time
from backtest.portfolio import CompletedTrade
from config.settings import settings


def compute_hourly_breakdown(trades: List[CompletedTrade]) -> List[Dict[str, Any]]:
    """
    Groups completed trades into 1-hour windows between 09:15 and 15:30
    and calculates metrics for each window.
    """
    hourly_buckets = settings.hourly_windows
    breakdown = []

    for start_str, end_str, label in hourly_buckets:
        s_h, s_m = map(int, start_str.split(":"))
        e_h, e_m = map(int, end_str.split(":"))
        start_t = time(s_h, s_m)
        end_t = time(e_h, e_m)

        # Match trades based on entry time
        bucket_trades = [
            t for t in trades
            if start_t <= t.entry_time.time() < end_t
        ]

        total = len(bucket_trades)
        if total == 0:
            breakdown.append({
                "window": f"{start_str} - {end_str}",
                "label": label,
                "trades": 0,
                "win_rate": 0.0,
                "net_pnl": 0.0,
                "gross_pnl": 0.0,
                "charges": 0.0,
                "profit_factor": 0.0,
                "recommendation": "NO_ACTIVITY"
            })
            continue

        winning = [t for t in bucket_trades if t.cost_breakdown.net_pnl > 0]
        losing = [t for t in bucket_trades if t.cost_breakdown.net_pnl < 0]
        gross_pnl = sum(t.cost_breakdown.gross_pnl for t in bucket_trades)
        charges = sum(t.cost_breakdown.total_taxes_charges for t in bucket_trades)
        net_pnl = sum(t.cost_breakdown.net_pnl for t in bucket_trades)

        win_sum = sum(t.cost_breakdown.net_pnl for t in winning)
        loss_sum = abs(sum(t.cost_breakdown.net_pnl for t in losing))
        pf = round(win_sum / loss_sum, 2) if loss_sum > 0 else (99.0 if win_sum > 0 else 0.0)
        win_rate = round((len(winning) / total) * 100, 1)

        # Verdict
        if net_pnl > 500 and win_rate >= 60.0:
            rec = "GOLDEN_SWEET_SPOT"
        elif net_pnl > 0 and win_rate >= 50.0:
            rec = "PROFITABLE"
        elif net_pnl < -300:
            rec = "AVOID_HIGH_RISK"
        else:
            rec = "NEUTRAL"

        breakdown.append({
            "window": f"{start_str} - {end_str}",
            "label": label,
            "trades": total,
            "winning": len(winning),
            "losing": len(losing),
            "win_rate": win_rate,
            "gross_pnl": round(gross_pnl, 2),
            "charges": round(charges, 2),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": pf,
            "recommendation": rec
        })

    return breakdown


def find_optimal_trading_window(hourly_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Identifies the best continuous trading window based on net PnL and win rate.
    """
    profitable_windows = [w for w in hourly_summary if w["net_pnl"] > 0]
    if not profitable_windows:
        return {
            "best_window": "None",
            "best_single_window": "None",
            "best_window_label": "None",
            "best_window_pnl": 0.0,
            "best_window_win_rate": 0.0,
            "reason": "No single hour was net profitable with current parameter set.",
            "recommendation": "No single hour was net profitable with current parameters. Consider adjusting lookback seconds or trigger thresholds.",
            "total_net_pnl": 0.0,
            "recommended_hours": []
        }

    # Sort by Net PnL descending
    sorted_windows = sorted(profitable_windows, key=lambda x: x["net_pnl"], reverse=True)
    best_single = sorted_windows[0]

    recommended = [w["window"] for w in sorted_windows if w["recommendation"] in ("GOLDEN_SWEET_SPOT", "PROFITABLE")]

    return {
        "best_single_window": best_single["window"],
        "best_window_label": best_single["label"],
        "best_window_pnl": best_single["net_pnl"],
        "best_window_win_rate": best_single["win_rate"],
        "recommended_hours": recommended,
        "recommendation": f"Trade primarily during {', '.join(recommended)} to exploit sideways ₹2-₹3 oscillations while filtering out opening & closing whipsaws."
    }
