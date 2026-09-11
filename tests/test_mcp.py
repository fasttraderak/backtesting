import json
from mcp_server.server import run_scalp_backtest, get_hourly_breakdown, optimize_scalp_parameters


def test_mcp_tools():
    # Test run_scalp_backtest tool
    res_str = run_scalp_backtest(
        lookback_seconds=10,
        check_count=5,
        trigger_diff=2.5,
        start_hour="11:00",
        end_hour="14:00"
    )
    data = json.loads(res_str)
    assert "performance_summary" in data
    assert "hourly_breakdown" in data
    assert "optimal_window_analysis" in data

    # Test get_hourly_breakdown tool
    hourly_str = get_hourly_breakdown(lookback_seconds=10, trigger_diff=2.5)
    hourly_data = json.loads(hourly_str)
    assert len(hourly_data["hourly_breakdown"]) == 6

    # Test optimize_scalp_parameters tool
    opt_str = optimize_scalp_parameters(top_n=2)
    opt_data = json.loads(opt_str)
    assert len(opt_data["top_parameter_configurations"]) <= 2
