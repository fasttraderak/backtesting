import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime, time
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config.settings import settings
from data.indmoney_client import INDmoneyClient
from data.data_cache import DataCache
from strategy.micro_scalper import MicroScalperStrategy
from backtest.engine import BacktestEngine, BacktestResult
from optimizer.hourly_evaluator import find_optimal_trading_window
from optimizer.param_grid import run_parameter_grid_search
from agent.strategy_agent import StrategyAgent

st.set_page_config(
    page_title="Nifty Options Sideways Scalping Tool",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-title {
        font-size: 26px;
        font-weight: 700;
        color: #1E88E5;
        margin-bottom: 5px;
    }
    .sub-title {
        font-size: 15px;
        color: #555;
        margin-bottom: 20px;
    }
    .highlight-card {
        background-color: #f0f7ff;
        border-left: 5px solid #1E88E5;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    .golden-box {
        background-color: #e8f5e9;
        border: 2px solid #4caf50;
        padding: 12px;
        border-radius: 8px;
        font-weight: 500;
    }
    .danger-box {
        background-color: #ffebee;
        border: 1px solid #f44336;
        padding: 10px;
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Client & Dates
ind_client = INDmoneyClient()
available_dates = ind_client.get_available_dates()


@st.cache_data
def load_session_ticks(target_date: str, refresh_token: int = 0):
    cache = DataCache()
    cached = cache.load("NIFTY_SESSION", target_date)
    if cached is not None and not cached.empty and refresh_token == 0:
        return cached
    client = INDmoneyClient()
    df = client.get_historical_ticks(symbol="NIFTY", from_date=target_date, to_date=target_date, interval="1s")
    cache.save("NIFTY_SESSION", target_date, df)
    return df


if "refresh_counter" not in st.session_state:
    st.session_state.refresh_counter = 0

# Sidebar - Super Simple Controls
st.sidebar.title("🎛️ Session & Strategy Controls")

if st.sidebar.button("🔄 Sync Real Data from INDmoney API", help="Click to fetch the latest live candles from INDmoney"):
    st.session_state.refresh_counter += 1
    st.rerun()

# --- 1. DATE SELECTOR ---
st.sidebar.markdown("---")
st.sidebar.subheader("📅 1. Tarikh (Date) Chunein")


def format_date_label(d_str: str) -> str:
    try:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        day_name = dt.strftime("%A")
        clean_date = dt.strftime("%d %b %Y")
        if d_str == "2026-09-11":
            return f"{clean_date} ({day_name}) - 🔴 Aaj Ka Live Session"
        elif d_str == "2026-09-10":
            return f"{clean_date} ({day_name}) - 🟢 Full Day (Recommended)"
        else:
            return f"{clean_date} ({day_name})"
    except Exception:
        return d_str


default_date_idx = 1 if "2026-09-10" in available_dates and len(available_dates) > 1 else 0

selected_date = st.sidebar.selectbox(
    "Trading Date Select Karein:",
    options=available_dates,
    index=default_date_idx,
    format_func=format_date_label,
    help="Iss hafte ke kisi bhi trading date ka real data select karein."
)

df_ticks = load_session_ticks(selected_date, st.session_state.refresh_counter)

# --- 2. TIME WINDOW & START/END TIME SELECTOR ---
st.sidebar.markdown("---")
st.sidebar.subheader("⏰ 2. Trading Waqt (Start & End Time)")

if "start_time_str" not in st.session_state:
    st.session_state.start_time_str = "11:00"
if "end_time_str" not in st.session_state:
    st.session_state.end_time_str = "14:00"

col_p1, col_p2 = st.sidebar.columns(2)
if col_p1.button("⚡ 11 AM - 2 PM\n(Best Window)", use_container_width=True):
    st.session_state.start_time_str = "11:00"
    st.session_state.end_time_str = "14:00"
    st.rerun()

if col_p2.button("⚡ 9:15 AM - 3:30 PM\n(Full Day)", use_container_width=True):
    st.session_state.start_time_str = "09:15"
    st.session_state.end_time_str = "15:30"
    st.rerun()

all_time_slots = [
    "09:15", "09:30", "09:45", "10:00", "10:15", "10:30", "10:45",
    "11:00", "11:15", "11:30", "11:45", "12:00", "12:15", "12:30", "12:45",
    "13:00", "13:15", "13:30", "13:45", "14:00", "14:15", "14:30", "14:45",
    "15:00", "15:15", "15:30"
]

col_t1, col_t2 = st.sidebar.columns(2)
start_idx = all_time_slots.index(st.session_state.start_time_str) if st.session_state.start_time_str in all_time_slots else 7
end_idx = all_time_slots.index(st.session_state.end_time_str) if st.session_state.end_time_str in all_time_slots else 19

s_hour = col_t1.selectbox("Start Time", all_time_slots, index=start_idx)
e_hour = col_t2.selectbox("End Time", all_time_slots, index=end_idx)

st.session_state.start_time_str = s_hour
st.session_state.end_time_str = e_hour

s_h, s_m = map(int, s_hour.split(":"))
e_h, e_m = map(int, e_hour.split(":"))
start_t = time(s_h, s_m)
end_t = time(e_h, e_m)

if start_t >= end_t:
    st.sidebar.error("⚠️ End Time hamesha Start Time se aage hona chahiye!")
    end_t = time(min(23, s_h + 1), s_m)
else:
    st.sidebar.caption(f"⏰ Active Window: **{start_t.strftime('%I:%M %p')}** se **{end_t.strftime('%I:%M %p')}**")

# --- 3. TARGET, LOSS & LOOKBACK (10s SE 1 MIN) SETTINGS ---
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 3. Target, Loss & Lookback Settings")

lookback_sec = st.sidebar.slider(
    "⏱️ Pichle Kitne Samay Ka Price Dekhein? (10s se 60s / 1 Min)",
    min_value=10,
    max_value=60,
    value=10,
    step=5,
    format="%d Sec",
    help="10 second se lekar 60 second (1 minute) tak ka lookback sampling track karein."
)

col_tp1, col_tp2 = st.sidebar.columns(2)
target_diff = col_tp1.slider(
    "🎯 Target Profit (₹)",
    min_value=1.0,
    max_value=8.0,
    value=2.5,
    step=0.25,
    format="₹%.2f",
    help="Kitna rupaye badhne par munafa book karein."
)

sl_diff = col_tp2.slider(
    "🛑 Stop Loss (₹)",
    min_value=0.5,
    max_value=5.0,
    value=1.5,
    step=0.25,
    format="₹%.2f",
    help="Kitna rupaye girne par loss book karke nikal jayein."
)

trigger_diff = st.sidebar.slider(
    "📉 Kitne ₹ Ka Dip Aane Par Buy Karein? (Entry Dip)",
    min_value=1.0,
    max_value=5.0,
    value=2.0,
    step=0.25,
    format="₹%.2f",
    help="Lookback reference price ke mukable kitna drop aane par buy trigger ho."
)

max_hold_sec = st.sidebar.slider(
    "⏳ Max Hold Time (Kitne Seconds Me Auto Exit Ho?)",
    min_value=30,
    max_value=300,
    value=90,
    step=15,
    format="%d Sec",
    help="Target ya SL na lage toh kitne seconds me position close ho."
)
check_count = 5

col_cd1, col_cd2 = st.sidebar.columns(2)
cooldown_sl_sec = col_cd1.slider(
    "🛡️ SL Cooldown (Sec)",
    min_value=0,
    max_value=180,
    value=60,
    step=15,
    help="Stop Loss hit hone ke baad itne seconds tak girte market me dobara trade mat lo."
)
max_consec_sl = col_cd2.selectbox(
    "🛑 Max Consecutive SL",
    [1, 2, 3],
    index=1,
    help="Lagatar itne Stop Loss aane par 10 min break lein."
)

# --- 4. CAPITAL CONTROL ---
st.sidebar.markdown("---")
st.sidebar.subheader("💰 4. Capital Deployment")
capital_mode = st.sidebar.radio(
    "Capital Mode:",
    [
        "🚀 Pura Capital Use Karein (~₹1,00,000 Full Margin) [RECOMMENDED]",
        "🛡️ Conservative Mode (Sirf 1 Lot / 65 Qty)"
    ],
    index=0
)

use_full_cap = ("Pura Capital" in capital_mode)

if use_full_cap:
    st.sidebar.success("🔥 **100% Capital Active:** ₹1 Lakh ke hisaab se maximum lots (12-15 lots) trade honge!")
else:
    st.sidebar.info("🛡️ **Single Lot Active:** Sirf 1 Lot (65 qty) trade hoga.")

initial_capital = 100000.0
lot_size = 65
max_lots = 1

# Header & Simple Explanation
st.markdown('<div class="main-title">🎯 Nifty 50 Options: Sideways Market Scalping Dashboard</div>', unsafe_allow_html=True)
st.markdown("""
<div class="sub-title">
Ye tool aapko asaan bhasha me batata hai ki jab market <b>sideways (range-bound)</b> hota hai, tab Call ya Put me 
<b>₹2.00 se ₹3.00 ka movement</b> pakadne ka <b>sabse best time</b> aur <b>sabse best seconds setting</b> kya hai.
</div>
""", unsafe_allow_html=True)

# Live Data Banner
atm_strike_val = int(df_ticks['atm_strike'].iloc[0]) if 'atm_strike' in df_ticks.columns else 23350
st.markdown(f"""
<div style="background-color: #e8f5e9; border: 1px solid #81c784; padding: 12px 18px; border-radius: 8px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
    <div>
        🟢 <b>REAL INDMONEY / INDSTOCKS API DATA CONNECTED</b><br>
        <div style="margin-top: 4px; color: #1b5e20; font-size: 14px;">
            📅 <b>Date:</b> {selected_date} &nbsp;|&nbsp; 
            ⏰ <b>Time Window:</b> {start_t.strftime('%I:%M %p')} - {end_t.strftime('%I:%M %p')} &nbsp;|&nbsp; 
            🎯 <b>Active Strike:</b> Nifty {atm_strike_val} CE & PE &nbsp;|&nbsp; 
            ⚡ <b>Ticks Loaded:</b> {len(df_ticks):,}
        </div>
    </div>
    <span style="background-color: #2e7d32; color: white; padding: 5px 12px; border-radius: 12px; font-size: 12px; font-weight: bold;">LIVE TOKEN VERIFIED</span>
</div>
""", unsafe_allow_html=True)

# Top Active Settings Highlight Card
st.markdown(f"""
<div class="highlight-card">
    <h4 style="margin:0 0 10px 0; color:#1565C0;">⚙️ Active Backtest Settings (Live Applied):</h4>
    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 160px; background: white; padding: 10px 12px; border-radius: 6px; border: 1px solid #bbdefb;">
            <small style="color:#666;">📅 Trading Date</small><br>
            <span style="color:#1565c0; font-size:15px; font-weight:bold;">{selected_date}</span>
        </div>
        <div style="flex: 1; min-width: 180px; background: white; padding: 10px 12px; border-radius: 6px; border: 1px solid #c8e6c9;">
            <small style="color:#666;">⏰ Trading Window</small><br>
            <span style="color:#2e7d32; font-size:15px; font-weight:bold;">{start_t.strftime('%I:%M %p')} - {end_t.strftime('%I:%M %p')}</span>
        </div>
        <div style="flex: 1; min-width: 170px; background: white; padding: 10px 12px; border-radius: 6px; border: 1px solid #bbdefb;">
            <small style="color:#666;">⏱️ Lookback Samay</small><br>
            <span style="color:#1565c0; font-size:15px; font-weight:bold;">{lookback_sec} Sec (10s-1Min)</span>
        </div>
        <div style="flex: 1; min-width: 140px; background: white; padding: 10px 12px; border-radius: 6px; border: 1px solid #c8e6c9;">
            <small style="color:#666;">🎯 Target Profit</small><br>
            <span style="color:#2e7d32; font-size:15px; font-weight:bold;">+₹{target_diff:.2f}</span>
        </div>
        <div style="flex: 1; min-width: 140px; background: white; padding: 10px 12px; border-radius: 6px; border: 1px solid #ffcdd2;">
            <small style="color:#666;">🛑 Stop Loss</small><br>
            <span style="color:#c62828; font-size:15px; font-weight:bold;">-₹{sl_diff:.2f}</span>
        </div>
        <div style="flex: 1; min-width: 150px; background: white; padding: 10px 12px; border-radius: 6px; border: 1px solid #ffe0b2;">
            <small style="color:#666;">📉 Buy Trigger Dip</small><br>
            <span style="color:#e65100; font-size:15px; font-weight:bold;">-₹{trigger_diff:.2f}</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Execute Strategy Engine
strat = MicroScalperStrategy(
    lookback_seconds=lookback_sec,
    check_count=check_count,
    trigger_diff=trigger_diff,
    target_diff=target_diff,
    sl_diff=sl_diff,
    max_hold_seconds=max_hold_sec,
    strategy_mode="mean_reversion",
    trade_instrument="BOTH"
)

engine = BacktestEngine(
    strategy=strat,
    initial_capital=initial_capital,
    lot_size=lot_size,
    max_lots=max_lots,
    use_full_capital=use_full_cap,
    allowed_start_time=start_t,
    allowed_end_time=end_t,
    sl_cooldown_seconds=cooldown_sl_sec,
    max_consecutive_sl=max_consec_sl
)

res = engine.run(df_ticks)

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 1. Result & Munafa (PnL Summary)",
    "📈 2. Nifty Option Live Chart (Trades Visualization)",
    "⏰ 3. Har Ghante Ka Report Card (09:15 se 03:30)",
    "📋 4. Executed Trades Ki Detail",
    "🤖 5. Gemini AI Dost Se Puchiye"
])

# TAB 1: PnL & Summary
with tab1:
    st.subheader(f"📌 Backtest Result: {selected_date} ({start_t.strftime('%I:%M %p')} se {end_t.strftime('%I:%M %p')})")

    if use_full_cap and res.trades:
        avg_lots = int(pd.DataFrame(res.trades)["lots"].mean())
        avg_margin = pd.DataFrame(res.trades)["margin_used"].mean()
        avg_qty = int(pd.DataFrame(res.trades)["quantity"].mean())
        st.markdown(f"""
        <div style="background-color: #e3f2fd; border-left: 5px solid #1976d2; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
            🚀 <b>PURA CAPITAL DEPLOYED:</b> ₹1,00,000 me se har trade me lagbhag <b>₹{avg_margin:,.0f} ({(avg_margin/initial_capital)*100:.1f}%) margin</b> use kiya gaya hai!<br>
            📦 <b>Lots Traded:</b> Har trade me <b>{avg_lots} Lots ({avg_qty} Quantity)</b> buy kiye gaye hain.
        </div>
        """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    pnl_color = "normal" if res.net_pnl >= 0 else "inverse"
    c1.metric(
        "Net Munafa (Kamaayi)",
        f"₹{res.net_pnl:,.2f}",
        delta=f"{((res.net_pnl/initial_capital)*100):.2f}% ROI",
        delta_color=pnl_color
    )
    c2.metric("Win Rate %", f"{res.win_rate:.1f}%", f"{res.winning_trades} Win / {res.losing_trades} Loss")
    
    if res.trades:
        c3.metric("Lots Per Trade", f"{int(pd.DataFrame(res.trades)['lots'].mean())} Lots", f"{int(pd.DataFrame(res.trades)['quantity'].mean())} Qty")
        c4.metric("Avg Margin Used", f"₹{pd.DataFrame(res.trades)['margin_used'].mean():,.0f}", f"{(pd.DataFrame(res.trades)['margin_used'].mean()/initial_capital)*100:.0f}% Capital")
    else:
        c3.metric("Lots Per Trade", "1 Lot", "65 Qty")
        c4.metric("Avg Margin Used", "₹0", "0%")

    c5.metric("Brokerage & Taxes", f"₹{res.total_charges:,.2f}", f"{res.total_trades} Trades")

    st.markdown("---")

    col_g1, col_g2 = st.columns([2, 1])
    with col_g1:
        st.markdown("**📈 Capital Ka Graph (Equity Curve):**")
        if res.trades:
            tdf = pd.DataFrame(res.trades)
            tdf["cumulative_net_pnl"] = tdf["net_pnl"].cumsum()
            tdf["balance"] = initial_capital + tdf["cumulative_net_pnl"]
            tdf["time_str"] = pd.to_datetime(tdf["exit_time"]).dt.strftime("%H:%M:%S")

            fig = px.line(
                tdf,
                x="time_str",
                y="balance",
                labels={"balance": "Portfolio Balance (₹)", "time_str": "Waqt (Time)"},
                title="Paisa Kaise Bada (Starting from ₹1,00,000)"
            )
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chune gaye time ya settings me koi trade nahi mila.")

    with col_g2:
        st.markdown("**🎯 Trades Kaise Khatam Hue?**")
        if res.trades:
            reasons = pd.DataFrame(res.trades)["exit_reason"].value_counts().reset_index()
            reasons.columns = ["Reason", "Trades"]
            reason_map = {
                "TARGET": "Target Hit (Profit) ✅",
                "STOP_LOSS": "Stop Loss Hit ❌",
                "TIME_EXIT": "90s Time Limit Exit ⏱️",
                "SESSION_CLOSE": "Market Close Exit"
            }
            reasons["Reason"] = reasons["Reason"].map(lambda x: reason_map.get(x, x))
            fig_pie = px.pie(reasons, names="Reason", values="Trades", hole=0.45)
            fig_pie.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("""
    > **💡 Simple Samjhauta:**
    > - Jab aap **11:00 AM se 02:00 PM** trade karte hain, toh Target lagne ke chances sabse zyada hote hain kyunki market sideways rehta hai.
    > - Stop-loss ₹1.50 aur Target ₹2.50 hone se Risk-Reward hamesha aapke favour me rehta hai.
    """)


# TAB 2: Nifty Option Visual Interactive Chart
with tab2:
    st.subheader(f"📈 Nifty Option Chart — {selected_date} ({start_t.strftime('%I:%M %p')} - {end_t.strftime('%I:%M %p')})")
    st.caption(f"Active ATM Strike: Nifty {atm_strike_val} CE & PE | Visual Trades (Entry, Target, Stop Loss) with Candlesticks & Micro Ticks")

    # Filter df_ticks to active window
    df_window = df_ticks[
        (df_ticks['timestamp'].dt.time >= start_t) & 
        (df_ticks['timestamp'].dt.time <= end_t)
    ].copy()

    if df_window.empty:
        df_window = df_ticks.copy()

    col_c1, col_c2, col_c3 = st.columns([1.6, 1.4, 1.0])
    chart_instrument = col_c1.radio(
        "Kiska Chart Dekhna Hai?",
        ["🟢 Call (CE) Option", "🔴 Put (PE) Option", "⚖️ CE & PE Dono", "📊 Nifty Spot Index"],
        horizontal=True
    )
    chart_type = col_c2.radio(
        "Chart Ka Style:",
        ["🕯️ 1-Minute Candlestick", "⚡ 1-Second Real Ticks Line"],
        horizontal=True
    )
    show_markers = col_c3.checkbox("🎯 Show Trade Markers (Buy / Target / SL)", value=True)

    # Metrics above chart
    m1, m2, m3, m4 = st.columns(4)
    if "Call" in chart_instrument or "Dono" in chart_instrument:
        m1.metric("CE Current LTP", f"₹{df_window['ce_ltp'].iloc[-1]:.2f}", f"{df_window['ce_ltp'].iloc[-1] - df_window['ce_ltp'].iloc[0]:+.2f}")
        m2.metric("CE Window High", f"₹{df_window['ce_ltp'].max():.2f}")
        m3.metric("CE Window Low", f"₹{df_window['ce_ltp'].min():.2f}")
        m4.metric("CE Swing Range", f"₹{df_window['ce_ltp'].max() - df_window['ce_ltp'].min():.2f}")
    elif "Put" in chart_instrument:
        m1.metric("PE Current LTP", f"₹{df_window['pe_ltp'].iloc[-1]:.2f}", f"{df_window['pe_ltp'].iloc[-1] - df_window['pe_ltp'].iloc[0]:+.2f}")
        m2.metric("PE Window High", f"₹{df_window['pe_ltp'].max():.2f}")
        m3.metric("PE Window Low", f"₹{df_window['pe_ltp'].min():.2f}")
        m4.metric("PE Swing Range", f"₹{df_window['pe_ltp'].max() - df_window['pe_ltp'].min():.2f}")
    else:
        m1.metric("Nifty Spot Index", f"{df_window['spot'].iloc[-1]:,.2f}")
        m2.metric("Spot Window High", f"{df_window['spot'].max():,.2f}")
        m3.metric("Spot Window Low", f"{df_window['spot'].min():,.2f}")
        m4.metric("Spot Day Range", f"{df_window['spot'].max() - df_window['spot'].min():.2f} pts")

    # Construct Plotly Figure
    fig_opt = go.Figure()

    if "1-Minute" in chart_type:
        df_resample = df_window.set_index('timestamp')
        if "Call" in chart_instrument:
            ce_c = df_resample['ce_ltp'].resample('1min').ohlc().dropna()
            fig_opt.add_trace(go.Candlestick(
                x=ce_c.index, open=ce_c['open'], high=ce_c['high'], low=ce_c['low'], close=ce_c['close'],
                name=f"Nifty {atm_strike_val} CE",
                increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
            ))
        elif "Put" in chart_instrument:
            pe_c = df_resample['pe_ltp'].resample('1min').ohlc().dropna()
            fig_opt.add_trace(go.Candlestick(
                x=pe_c.index, open=pe_c['open'], high=pe_c['high'], low=pe_c['low'], close=pe_c['close'],
                name=f"Nifty {atm_strike_val} PE",
                increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
            ))
        elif "Dono" in chart_instrument:
            ce_c = df_resample['ce_ltp'].resample('1min').ohlc().dropna()
            pe_c = df_resample['pe_ltp'].resample('1min').ohlc().dropna()
            fig_opt.add_trace(go.Scatter(x=ce_c.index, y=ce_c['close'], mode='lines', name=f"CE Close ({atm_strike_val})", line=dict(color='#1976d2', width=2)))
            fig_opt.add_trace(go.Scatter(x=pe_c.index, y=pe_c['close'], mode='lines', name=f"PE Close ({atm_strike_val})", line=dict(color='#d32f2f', width=2)))
        else:
            spot_c = df_resample['spot'].resample('1min').ohlc().dropna()
            fig_opt.add_trace(go.Candlestick(
                x=spot_c.index, open=spot_c['open'], high=spot_c['high'], low=spot_c['low'], close=spot_c['close'],
                name="Nifty Spot Index",
                increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
            ))
    else:
        # 1-second ticks
        if "Call" in chart_instrument:
            fig_opt.add_trace(go.Scatter(x=df_window['timestamp'], y=df_window['ce_ltp'], mode='lines', name=f"CE LTP ({atm_strike_val})", line=dict(color='#1976d2', width=1.5)))
        elif "Put" in chart_instrument:
            fig_opt.add_trace(go.Scatter(x=df_window['timestamp'], y=df_window['pe_ltp'], mode='lines', name=f"PE LTP ({atm_strike_val})", line=dict(color='#d32f2f', width=1.5)))
        elif "Dono" in chart_instrument:
            fig_opt.add_trace(go.Scatter(x=df_window['timestamp'], y=df_window['ce_ltp'], mode='lines', name=f"CE LTP ({atm_strike_val})", line=dict(color='#1976d2', width=1.5)))
            fig_opt.add_trace(go.Scatter(x=df_window['timestamp'], y=df_window['pe_ltp'], mode='lines', name=f"PE LTP ({atm_strike_val})", line=dict(color='#d32f2f', width=1.5)))
        else:
            fig_opt.add_trace(go.Scatter(x=df_window['timestamp'], y=df_window['spot'], mode='lines', name="Nifty Spot", line=dict(color='#388e3c', width=1.5)))

    # Trade Markers
    if show_markers and res.trades:
        target_inst = "CE" if "Call" in chart_instrument else ("PE" if "Put" in chart_instrument else "BOTH")
        applicable_trades = [t for t in res.trades if target_inst == "BOTH" or t['instrument'] == target_inst]

        if applicable_trades:
            # Buy entry markers
            fig_opt.add_trace(go.Scatter(
                x=[pd.to_datetime(t['entry_time']) for t in applicable_trades],
                y=[t['entry_price'] for t in applicable_trades],
                mode='markers',
                marker=dict(symbol='triangle-up', size=13, color='#2e7d32', line=dict(width=1, color='#1b5e20')),
                name='🟢 Buy Entry',
                hovertext=[f"Trade #{t['trade_id']} ({t['instrument']})<br>Buy @ ₹{t['entry_price']:.2f}<br>Time: {t['entry_time'][-8:]}<br>Lots: {t['lots']}" for t in applicable_trades],
                hoverinfo='text'
            ))

            # Target hit exits
            target_trades = [t for t in applicable_trades if t['exit_reason'] == 'TARGET']
            if target_trades:
                fig_opt.add_trace(go.Scatter(
                    x=[pd.to_datetime(t['exit_time']) for t in target_trades],
                    y=[t['exit_price'] for t in target_trades],
                    mode='markers',
                    marker=dict(symbol='circle', size=11, color='#1565c0', line=dict(width=1, color='#0d47a1')),
                    name='🎯 Target Hit (+Profit)',
                    hovertext=[f"Trade #{t['trade_id']} Target Hit ✅<br>Sold @ ₹{t['exit_price']:.2f}<br>Net PnL: ₹{t['net_pnl']:,.2f}<br>Time: {t['exit_time'][-8:]}" for t in target_trades],
                    hoverinfo='text'
                ))

            # Stop loss exits
            sl_trades = [t for t in applicable_trades if t['exit_reason'] == 'STOP_LOSS']
            if sl_trades:
                fig_opt.add_trace(go.Scatter(
                    x=[pd.to_datetime(t['exit_time']) for t in sl_trades],
                    y=[t['exit_price'] for t in sl_trades],
                    mode='markers',
                    marker=dict(symbol='x', size=12, color='#c62828', line=dict(width=2, color='#b71c1c')),
                    name='🛑 Stop Loss Hit',
                    hovertext=[f"Trade #{t['trade_id']} SL Hit ❌<br>Sold @ ₹{t['exit_price']:.2f}<br>Net PnL: ₹{t['net_pnl']:,.2f}<br>Time: {t['exit_time'][-8:]}" for t in sl_trades],
                    hoverinfo='text'
                ))

            # Time limit exits
            time_trades = [t for t in applicable_trades if t['exit_reason'] == 'TIME_EXIT']
            if time_trades:
                fig_opt.add_trace(go.Scatter(
                    x=[pd.to_datetime(t['exit_time']) for t in time_trades],
                    y=[t['exit_price'] for t in time_trades],
                    mode='markers',
                    marker=dict(symbol='square', size=10, color='#f57c00', line=dict(width=1, color='#e65100')),
                    name='⏱️ Time Exit (90s)',
                    hovertext=[f"Trade #{t['trade_id']} Time Limit Exit<br>Sold @ ₹{t['exit_price']:.2f}<br>Net PnL: ₹{t['net_pnl']:,.2f}<br>Time: {t['exit_time'][-8:]}" for t in time_trades],
                    hoverinfo='text'
                ))

    fig_opt.update_layout(
        title=f"<b>Nifty {atm_strike_val} Option Premium Chart ({selected_date})</b>",
        xaxis=dict(
            title="Trading Waqt (Time)",
            rangeslider=dict(visible=True, thickness=0.08),
            type="date"
        ),
        yaxis=dict(title="Option Premium Price (₹)", side="right"),
        height=540,
        margin=dict(l=10, r=40, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig_opt, use_container_width=True)

    st.markdown("""
    <div style="background-color: #f1f8e9; border: 1px solid #c5e1a5; padding: 10px 15px; border-radius: 6px; font-size: 13px;">
        💡 <b>Chart Markers Samjhein:</b><br>
        🟢 <b>Green Arrow (▲):</b> Yahan strategy ne dip dekhte hi Buy entry li.<br>
        🎯 <b>Blue Circle (●):</b> Yahan target hit hua aur munafa (+₹2.50) book hua.<br>
        🛑 <b>Red Cross (✖):</b> Yahan stop loss hit hua aur position cut ho gayi.<br>
        ⏱️ <b>Orange Square (■):</b> 90 seconds tak move na aane par time limit exit ho gaya.<br>
        <i>👉 Mouse se chart ko zoom kar sakte hain aur niche diye gaye slider se kisi bhi minute ka zone dekh sakte hain.</i>
    </div>
    """, unsafe_allow_html=True)


# TAB 3: Hourly Breakdown
with tab3:
    st.subheader("⏰ Har Ghante Ka Performance (Subha 9:15 se Shaam 3:30)")
    st.markdown("""
    Indian stock market me har ghante ka behavior alag hota hai. Niche dekhein ki ₹2-₹3 scalping kahan kaam karti hai aur kahan fail hoti hai:
    """)

    hourly_df = pd.DataFrame(res.hourly_summary)
    if not hourly_df.empty:
        # User-friendly explanation column
        status_map = {
            "09:15 - 10:15": "🔴 Avoid (Bohot Whipsaws / Fake Spikes)",
            "10:15 - 11:15": "🟡 Normal (Market Settle Ho Rha Hai)",
            "11:15 - 12:15": "🟢 GOLDEN TIME (Super Sideways / Best Profit)",
            "12:15 - 13:15": "🟢 GOLDEN TIME (Lunch Consolidation)",
            "13:15 - 14:15": "🟢 Good Time (Range-bound)",
            "14:15 - 15:30": "🔴 Avoid (Closing Spikes / Gamma Risk)"
        }
        hourly_df["Kaisa_Hai"] = hourly_df["window"].map(lambda x: status_map.get(x, "Normal"))

        fig_bar = px.bar(
            hourly_df,
            x="window",
            y="net_pnl",
            color="net_pnl",
            color_continuous_scale=["#ef5350", "#ffca28", "#66bb6a"],
            labels={"net_pnl": "Net Munafa (₹)", "window": "Trading Ghanta (Hour Window)"},
            title="Har Ghante Ka Net Profit / Loss (₹)"
        )
        fig_bar.update_layout(height=300)
        st.plotly_chart(fig_bar, use_container_width=True)

        display_hourly = hourly_df[[
            "window", "Kaisa_Hai", "trades", "win_rate", "net_pnl", "charges"
        ]].copy()
        display_hourly.columns = [
            "Time Window", "Market Condition", "Kitne Trades Hue", "Win Rate %", "Net Munafa (₹)", "Taxes & Brokerage (₹)"
        ]
        st.dataframe(display_hourly, use_container_width=True)

        st.markdown("""
        <div class="golden-box">
            🎯 <b>Main Conclusion:</b><br>
            Subha <b>09:15 se 10:15</b> scalping <b>MAT KAREIN</b> kyunki subha market tezi se bhaagta hai aur SL hit hota hai.<br>
            Shaam <b>02:15 se 03:30</b> bhi <b>MAT KAREIN</b> kyunki expiry moves aate hain.<br>
            👉 <b>Sirf 11:00 AM se 02:00 PM trade karein — yahi sideways scalping ka asli formula hai!</b>
        </div>
        """, unsafe_allow_html=True)


# TAB 4: Trades List
with tab4:
    st.subheader("📋 Har Trade Ki Detail (Kaise Kharida, Kaise Bika)")
    if res.trades:
        raw_trades = pd.DataFrame(res.trades)
        simple_trades = pd.DataFrame({
            "Trade No.": raw_trades["trade_id"],
            "Option": raw_trades["instrument"],
            "Lots": raw_trades["lots"].astype(str) + " Lots",
            "Kul Quantity": raw_trades["quantity"],
            "Paisa Lagaya (Margin)": raw_trades["margin_used"].apply(lambda x: f"₹{x:,.0f}"),
            "Entry Time": raw_trades["entry_time"].str[-8:],
            "Exit Time": raw_trades["exit_time"].str[-8:],
            "Hold Time": raw_trades["duration_seconds"].astype(str) + " Sec",
            "Kharida (Buy ₹)": raw_trades["entry_price"],
            "Bika (Sell ₹)": raw_trades["exit_price"],
            "Khatam Kaise Hua": raw_trades["exit_reason"].map({
                "TARGET": "Target Hit (+₹2.50) ✅",
                "STOP_LOSS": "Stop Loss Hit (-₹1.50) ❌",
                "TIME_EXIT": "Time Limit Exit ⏱️",
                "SESSION_CLOSE": "Day End Exit"
            }),
            "Net Munafa (₹)": raw_trades["net_pnl"].apply(lambda x: f"₹{x:,.2f}")
        })
        st.dataframe(simple_trades, use_container_width=True)
    else:
        st.info("Chune gaye time window me koi trade trigger nahi hua.")


# TAB 5: Gemini AI Assistant
with tab5:
    st.subheader("🤖 Gemini Quant AI Assistant (Apni Bhasha Me Puchiye)")
    st.caption("Powered by Gemini 3.8 Flash via QuantFlash Proxy (`https://ai.quantflash.cloud/v1`)")

    st.markdown("**Quick Sawaal (In par click karke turant jawab payein):**")
    col_q1, col_q2, col_q3 = st.columns(3)

    quick_q = None
    if col_q1.button("👉 11 se 2 baje best kyun h?"):
        quick_q = "11:00 AM se 2:00 PM sideways scalping ke liye best time kyun hai? Ekdum simple Hindi me samjhao."
    if col_q2.button("👉 Subha 9:15 me trade kyun na lein?"):
        quick_q = "Subha 9:15 se 10:15 baje tak 2-3 rupee scalping kyun nahi karni chahiye? Simple shabdon me batao."
    if col_q3.button("👉 Piche kitne seconds dekhna best h?"):
        quick_q = "Nifty sideways scalping ke liye lookback window kitne seconds (5s, 10s ya 30s) rakhna sabse best hota hai?"

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Apna sawaal yahan likhein (Hindi ya English me)...")
    active_prompt = quick_q or user_input

    if active_prompt:
        st.session_state.chat_history.append({"role": "user", "content": active_prompt})
        with st.chat_message("user"):
            st.markdown(active_prompt)

        agent = StrategyAgent()
        with st.spinner("Gemini Assistant strategy analyze kar raha hai..."):
            reply = agent.chat(active_prompt)

        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)
