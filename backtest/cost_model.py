from typing import Dict, Any
from pydantic import BaseModel
from config.settings import settings


class TradeCostBreakdown(BaseModel):
    buy_price_raw: float
    sell_price_raw: float
    buy_price_slipped: float
    sell_price_slipped: float
    quantity: int
    slippage_cost: float
    gross_pnl: float
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    total_taxes_charges: float
    net_pnl: float
    pnl_per_qty: float


def calculate_trade_costs(
    buy_price: float,
    sell_price: float,
    quantity: int,
    slippage_per_leg: float = None,
    brokerage_per_order: float = None
) -> TradeCostBreakdown:
    """
    Computes precise round-trip Indian statutory taxes, brokerage, and slippage for Nifty options trades.
    """
    if slippage_per_leg is None:
        slippage_per_leg = settings.costs.slippage_per_leg
    if brokerage_per_order is None:
        brokerage_per_order = settings.costs.brokerage_per_order

    # 1. Slippage impact
    # Buyer pays higher, Seller receives lower
    buy_slipped = buy_price + slippage_per_leg
    sell_slipped = max(0.05, sell_price - slippage_per_leg)
    slippage_cost = 2 * slippage_per_leg * quantity

    # 2. Turnovers
    buy_turnover = buy_slipped * quantity
    sell_turnover = sell_slipped * quantity

    # 3. Gross PnL after slippage
    gross_pnl = (sell_slipped - buy_slipped) * quantity

    # 4. Brokerage (Buy + Sell legs)
    brokerage = brokerage_per_order * 2.0

    # 5. STT (0.0625% on sell turnover for options premium)
    stt = sell_turnover * settings.costs.stt_rate

    # 6. Exchange turnover charges (0.0505% on total turnover)
    exchange_charges = (buy_turnover + sell_turnover) * settings.costs.exchange_rate

    # 7. GST (18% on Brokerage + Exchange charges)
    gst = (brokerage + exchange_charges) * settings.costs.gst_rate

    # 8. SEBI Turnover Charges (INR 10 per crore = 0.0001%)
    sebi_charges = (buy_turnover + sell_turnover) * settings.costs.sebi_rate

    # 9. Stamp Duty (0.003% on buy turnover)
    stamp_duty = buy_turnover * settings.costs.stamp_duty_rate

    total_taxes_charges = round(brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty, 2)
    net_pnl = round(gross_pnl - total_taxes_charges, 2)
    pnl_per_qty = round(net_pnl / quantity, 2) if quantity > 0 else 0.0

    return TradeCostBreakdown(
        buy_price_raw=round(buy_price, 2),
        sell_price_raw=round(sell_price, 2),
        buy_price_slipped=round(buy_slipped, 2),
        sell_price_slipped=round(sell_slipped, 2),
        quantity=quantity,
        slippage_cost=round(slippage_cost, 2),
        gross_pnl=round(gross_pnl, 2),
        brokerage=round(brokerage, 2),
        stt=round(stt, 2),
        exchange_charges=round(exchange_charges, 2),
        gst=round(gst, 2),
        sebi_charges=round(sebi_charges, 2),
        stamp_duty=round(stamp_duty, 2),
        total_taxes_charges=total_taxes_charges,
        net_pnl=net_pnl,
        pnl_per_qty=pnl_per_qty
    )
