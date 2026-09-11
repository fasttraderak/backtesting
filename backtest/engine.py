from typing import Dict, Any, List, Optional
from datetime import datetime, time, timedelta
import pandas as pd
import numpy as np
from pydantic import BaseModel

from strategy.sideways_detector import SidewaysDetector
from strategy.micro_scalper import MicroScalperStrategy, ScalpSignal
from backtest.portfolio import PortfolioManager, CompletedTrade
from config.settings import settings


class BacktestResult(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_pnl: float
    total_charges: float
    net_pnl: float
    final_capital: float
    max_drawdown: float
    profit_factor: float
    avg_trade_duration_sec: float
    trades: List[Dict[str, Any]]
    hourly_summary: List[Dict[str, Any]]


class BacktestEngine:
    """
    Second-by-second event-driven backtesting engine for Nifty options scalping.
    Simulates trading from 09:15:00 to 15:30:00.
    Includes Stop-Loss cooldown and consecutive loss circuit breakers to avoid
    'catching falling knives' during violent directional crashes.
    """

    def __init__(
        self,
        strategy: MicroScalperStrategy,
        sideways_detector: Optional[SidewaysDetector] = None,
        initial_capital: float = 100000.0,
        lot_size: int = 65,
        max_lots: int = 1,
        max_daily_loss: float = 20000.0,
        use_full_capital: bool = True,
        allowed_start_time: time = time(9, 15),
        allowed_end_time: time = time(15, 30),
        sl_cooldown_seconds: int = 60,
        max_consecutive_sl: int = 2
    ):
        self.strategy = strategy
        self.sideways_detector = sideways_detector or SidewaysDetector()
        self.initial_capital = initial_capital
        self.lot_size = lot_size
        self.max_lots = max_lots
        self.max_daily_loss = max_daily_loss
        self.use_full_capital = use_full_capital
        self.allowed_start_time = allowed_start_time
        self.allowed_end_time = allowed_end_time
        self.sl_cooldown_seconds = sl_cooldown_seconds
        self.max_consecutive_sl = max_consecutive_sl

    def run(self, df: pd.DataFrame) -> BacktestResult:
        """
        Executes the backtest on the session tick DataFrame.
        """
        if df.empty:
            raise ValueError("Input tick DataFrame is empty.")

        portfolio = PortfolioManager(
            initial_capital=self.initial_capital,
            lot_size=self.lot_size,
            max_lots=self.max_lots,
            max_daily_loss=self.max_daily_loss,
            use_full_capital=self.use_full_capital
        )

        timestamps = df["timestamp"].values
        ce_prices = df["ce_ltp"].values
        pe_prices = df["pe_ltp"].values

        # Detect sideways regime on CE and PE
        ce_sideways = self.sideways_detector.compute_regime(df["ce_ltp"]).values
        pe_sideways = self.sideways_detector.compute_regime(df["pe_ltp"]).values

        n_ticks = len(df)
        instruments_to_trade = []
        if self.strategy.trade_instrument in ("CE", "BOTH"):
            instruments_to_trade.append("CE")
        if self.strategy.trade_instrument in ("PE", "BOTH"):
            instruments_to_trade.append("PE")

        last_sl_time: Dict[str, datetime] = {}
        consecutive_sl: Dict[str, int] = {"CE": 0, "PE": 0}
        pause_until: Dict[str, datetime] = {}

        for idx in range(n_ticks):
            ts = pd.to_datetime(timestamps[idx])
            curr_time = ts.time()

            # 1. Update & check existing positions
            for inst in list(portfolio.open_positions.keys()):
                pos = portfolio.open_positions[inst]
                current_price = ce_prices[idx] if inst == "CE" else pe_prices[idx]
                elapsed_sec = int((ts - pos.entry_time).total_seconds())

                # Target hit
                if current_price >= pos.target_price:
                    portfolio.close_position(
                        instrument=inst,
                        exit_time=ts,
                        exit_price=pos.target_price,
                        exit_reason="TARGET"
                    )
                    consecutive_sl[inst] = 0
                # Stop Loss hit
                elif current_price <= pos.stop_loss_price:
                    portfolio.close_position(
                        instrument=inst,
                        exit_time=ts,
                        exit_price=pos.stop_loss_price,
                        exit_reason="STOP_LOSS"
                    )
                    last_sl_time[inst] = ts
                    consecutive_sl[inst] = consecutive_sl.get(inst, 0) + 1
                    if consecutive_sl[inst] >= self.max_consecutive_sl:
                        pause_until[inst] = ts + timedelta(minutes=10)
                # Time limit hit
                elif elapsed_sec >= pos.max_hold_seconds:
                    portfolio.close_position(
                        instrument=inst,
                        exit_time=ts,
                        exit_price=current_price,
                        exit_reason="TIME_EXIT"
                    )
                # Force close at end of trading day
                elif curr_time >= time(15, 25):
                    portfolio.close_position(
                        instrument=inst,
                        exit_time=ts,
                        exit_price=current_price,
                        exit_reason="SESSION_CLOSE"
                    )

            # Check if time is within allowed trading filter
            if not (self.allowed_start_time <= curr_time <= self.allowed_end_time):
                continue

            # Skip new entries if near close
            if curr_time >= time(15, 20):
                continue

            # 2. Check for entry signals
            for inst in instruments_to_trade:
                if inst in portfolio.open_positions:
                    continue

                # Circuit breaker check: consecutive loss pause
                if inst in pause_until and ts < pause_until[inst]:
                    continue

                # Circuit breaker check: Stop Loss cooldown
                if inst in last_sl_time:
                    if (ts - last_sl_time[inst]).total_seconds() < self.sl_cooldown_seconds:
                        continue

                prices = ce_prices if inst == "CE" else pe_prices
                sideways_arr = ce_sideways if inst == "CE" else pe_sideways

                sig: Optional[ScalpSignal] = self.strategy.evaluate_signal(
                    current_idx=idx,
                    timestamps=timestamps,
                    prices=prices,
                    is_sideways_array=sideways_arr,
                    instrument=inst
                )

                if sig:
                    portfolio.open_position(
                        instrument=inst,
                        entry_time=ts,
                        entry_price=sig.current_price,
                        target_price=sig.target_price,
                        stop_loss_price=sig.stop_loss_price,
                        max_hold_seconds=self.strategy.max_hold_seconds
                    )

        # Force close any residual positions at end of dataset
        if portfolio.open_positions:
            last_ts = pd.to_datetime(timestamps[-1])
            for inst in list(portfolio.open_positions.keys()):
                last_price = ce_prices[-1] if inst == "CE" else pe_prices[-1]
                portfolio.close_position(
                    instrument=inst,
                    exit_time=last_ts,
                    exit_price=last_price,
                    exit_reason="SESSION_CLOSE"
                )

        return self._generate_report(portfolio)

    def _generate_report(self, portfolio: PortfolioManager) -> BacktestResult:
        trades = portfolio.completed_trades
        total_trades = len(trades)
        from optimizer.hourly_evaluator import compute_hourly_breakdown
        
        if total_trades == 0:
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                gross_pnl=0.0,
                total_charges=0.0,
                net_pnl=0.0,
                final_capital=self.initial_capital,
                max_drawdown=0.0,
                profit_factor=0.0,
                avg_trade_duration_sec=0.0,
                trades=[],
                hourly_summary=compute_hourly_breakdown([])
            )

        winning = [t for t in trades if t.cost_breakdown.net_pnl > 0]
        losing = [t for t in trades if t.cost_breakdown.net_pnl < 0]

        gross_pnl = sum(t.cost_breakdown.gross_pnl for t in trades)
        total_charges = sum(t.cost_breakdown.total_taxes_charges for t in trades)
        net_pnl = sum(t.cost_breakdown.net_pnl for t in trades)

        gross_win = sum(t.cost_breakdown.net_pnl for t in winning)
        gross_loss = abs(sum(t.cost_breakdown.net_pnl for t in losing))
        profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else 99.0

        # Calculate equity curve & max drawdown
        equity = self.initial_capital
        peak = equity
        max_dd = 0.0
        for t in trades:
            equity += t.cost_breakdown.net_pnl
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        avg_duration = sum(t.hold_duration_seconds for t in trades) / total_trades

        # Trade dictionaries
        trade_dicts = []
        for t in trades:
            trade_dicts.append({
                "trade_id": t.trade_id,
                "instrument": t.instrument,
                "entry_time": t.entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                "exit_time": t.exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "lots": t.lots,
                "quantity": t.quantity,
                "margin_used": t.margin_used,
                "exit_reason": t.exit_reason,
                "gross_pnl": t.cost_breakdown.gross_pnl,
                "taxes_brokerage": t.cost_breakdown.total_taxes_charges,
                "net_pnl": t.cost_breakdown.net_pnl,
                "duration_seconds": t.hold_duration_seconds
            })

        # Calculate 1-hour breakdown
        from optimizer.hourly_evaluator import compute_hourly_breakdown
        hourly_summary = compute_hourly_breakdown(trades)

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round((len(winning) / total_trades) * 100, 2),
            gross_pnl=round(gross_pnl, 2),
            total_charges=round(total_charges, 2),
            net_pnl=round(net_pnl, 2),
            final_capital=round(self.initial_capital + net_pnl, 2),
            max_drawdown=round(max_dd, 2),
            profit_factor=profit_factor,
            avg_trade_duration_sec=round(avg_duration, 1),
            trades=trade_dicts,
            hourly_summary=hourly_summary
        )
