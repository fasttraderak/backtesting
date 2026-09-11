from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from backtest.cost_model import calculate_trade_costs, TradeCostBreakdown
from config.settings import settings


class Position(BaseModel):
    trade_id: int
    instrument: str          # "CE" or "PE"
    entry_time: datetime
    entry_price: float
    target_price: float
    stop_loss_price: float
    lots: int
    quantity: int
    margin_used: float
    max_hold_seconds: int


class CompletedTrade(BaseModel):
    trade_id: int
    instrument: str
    entry_time: datetime
    exit_time: datetime
    hold_duration_seconds: int
    entry_price: float
    exit_price: float
    lots: int
    quantity: int
    margin_used: float
    exit_reason: str         # "TARGET", "STOP_LOSS", "TIME_EXIT", "SESSION_CLOSE", "DAILY_LOSS_CUTOFF"
    cost_breakdown: TradeCostBreakdown


class PortfolioManager:
    """
    Manages capital (starting with ₹1,00,000), position sizing, margin, and circuit breakers.
    Supports 100% full capital utilization (dynamic lot sizing).
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        lot_size: int = 65,
        max_lots: int = 1,
        max_daily_loss: float = 20000.0,
        use_full_capital: bool = True
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.lot_size = lot_size
        self.max_lots = max_lots
        self.max_daily_loss = max_daily_loss
        self.use_full_capital = use_full_capital
        
        self.open_positions: Dict[str, Position] = {}  # key: "CE" or "PE"
        self.completed_trades: List[CompletedTrade] = []
        self.daily_realized_pnl: float = 0.0
        self.trading_halted: bool = False
        self.trade_counter: int = 0

    def calculate_lots_to_trade(self, price: float) -> int:
        lot_cost = price * self.lot_size
        if lot_cost <= 0:
            return 1
        if self.use_full_capital:
            # Deploy up to 95% of available cash to leave buffer for slippage & broker fees
            usable_cash = self.cash * 0.95
            calculated_lots = int(usable_cash // lot_cost)
            return max(1, calculated_lots)
        return max(1, self.max_lots)

    def can_open_position(self, instrument: str, price: float) -> bool:
        if self.trading_halted:
            return False
        if instrument in self.open_positions:
            return False
        if self.daily_realized_pnl <= -self.max_daily_loss:
            self.trading_halted = True
            return False

        lots = self.calculate_lots_to_trade(price)
        margin_required = price * (self.lot_size * lots)
        if margin_required > self.cash:
            return False

        return True

    def open_position(
        self,
        instrument: str,
        entry_time: datetime,
        entry_price: float,
        target_price: float,
        stop_loss_price: float,
        max_hold_seconds: int = 90
    ) -> Optional[Position]:
        if not self.can_open_position(instrument, entry_price):
            return None

        lots = self.calculate_lots_to_trade(entry_price)
        qty = self.lot_size * lots
        margin_used = entry_price * qty
        self.cash -= margin_used

        self.trade_counter += 1
        pos = Position(
            trade_id=self.trade_counter,
            instrument=instrument,
            entry_time=entry_time,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            lots=lots,
            quantity=qty,
            margin_used=round(margin_used, 2),
            max_hold_seconds=max_hold_seconds
        )
        self.open_positions[instrument] = pos
        return pos

    def close_position(
        self,
        instrument: str,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str
    ) -> Optional[CompletedTrade]:
        if instrument not in self.open_positions:
            return None

        pos = self.open_positions.pop(instrument)
        costs = calculate_trade_costs(
            buy_price=pos.entry_price,
            sell_price=exit_price,
            quantity=pos.quantity
        )

        duration = int((exit_time - pos.entry_time).total_seconds())

        # Return capital + net PnL
        self.cash += (pos.entry_price * pos.quantity) + costs.net_pnl
        self.daily_realized_pnl += costs.net_pnl

        trade = CompletedTrade(
            trade_id=pos.trade_id,
            instrument=pos.instrument,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            hold_duration_seconds=max(1, duration),
            entry_price=pos.entry_price,
            exit_price=exit_price,
            lots=pos.lots,
            quantity=pos.quantity,
            margin_used=pos.margin_used,
            exit_reason=exit_reason,
            cost_breakdown=costs
        )
        self.completed_trades.append(trade)

        if self.daily_realized_pnl <= -self.max_daily_loss:
            self.trading_halted = True

        return trade
