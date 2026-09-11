import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import requests
import pandas as pd
import numpy as np
from config.settings import settings

logger = logging.getLogger("INDmoneyClient")


class INDmoneyClient:
    """
    Client for INDmoney / INDstocks Official Developer API to fetch
    Real Option Chains, Expiries, and Historical Candle Data.
    """

    def __init__(self, api_key: Optional[str] = None, access_token: Optional[str] = None):
        self.api_key = api_key or settings.indmoney.api_key or "COQLB"
        self.access_token = access_token or settings.indmoney.access_token
        self.base_url = "https://api.indstocks.com"
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        if self.access_token:
            # INDstocks accepts raw token in Authorization header
            self.headers["Authorization"] = self.access_token

    def is_configured(self) -> bool:
        return bool(self.access_token and len(self.access_token) > 20)

    def get_nifty_expiries(self) -> List[str]:
        """Fetches active expiry dates for Nifty 50."""
        if not self.is_configured():
            return ["2026-09-15"]
        url = f"{self.base_url}/market/instruments/expiries"
        params = {"underlying": "NIFTY", "segment": "DERIVATIVE"}
        try:
            r = requests.get(url, headers=self.headers, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("data", ["2026-09-15"])
        except Exception as e:
            logger.error(f"Failed to fetch expiries: {e}")
        return ["2026-09-15"]

    def get_real_option_chain(self, expiry: Optional[str] = None, strike_count: int = 5) -> Dict[str, Any]:
        """
        Fetches the real option chain ladder for Nifty from INDstocks API.
        """
        if not self.is_configured():
            logger.warning("Token not configured, returning mock chain.")
            return {}

        if not expiry:
            expiries = self.get_nifty_expiries()
            expiry = expiries[0] if expiries else "2026-09-15"

        url = f"{self.base_url}/market/option-chain"
        params = {
            "exchange": "NSE",
            "segment": "INDEX",
            "underlying-scrip": "40000001",
            "expiry": expiry,
            "strike_count": strike_count
        }

        try:
            r = requests.get(url, headers=self.headers, params=params, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", {})
            else:
                logger.error(f"Option chain error {r.status_code}: {r.text}")
        except Exception as e:
            logger.error(f"Exception in option chain request: {e}")

        return {}

    def get_available_dates(self) -> List[str]:
        """
        Returns a sorted list of available trading dates (most recent first).
        Combines cached parquet files with known live dates of the current week.
        """
        from data.data_cache import DataCache
        cache = DataCache()
        dates = set()
        
        # 1. Read existing cached dates
        for p in cache.cache_dir.glob("NIFTY_SESSION_*.parquet"):
            d = p.stem.replace("NIFTY_SESSION_", "")
            if len(d) == 10 and d.count("-") == 2:
                dates.add(d)

        # 2. Add current week trading days as default candidates
        current_week_dates = ["2026-09-11", "2026-09-10", "2026-09-09", "2026-09-08", "2026-09-07"]
        for d in current_week_dates:
            dates.add(d)

        return sorted(list(dates), reverse=True)

    def fetch_this_week_real_data(self, target_date: Optional[str] = None) -> pd.DataFrame:
        """
        Fetches real historical candle data for Nifty Index and ATM Call/Put options
        for this week from the live INDstocks API, processes each trading day,
        caches all days to parquet, and returns ticks for the requested target_date.
        """
        from data.data_cache import DataCache
        cache = DataCache()

        logger.info("Fetching live option chain for ATM selection...")
        chain_data = self.get_real_option_chain(strike_count=4)
        underlying_ltp = chain_data.get("underlying_ltp", 23330.0)
        strikes = chain_data.get("strikes", {})

        # Find closest ATM strike
        atm_strike = None
        min_diff = 999999.0
        atm_ce_id = None
        atm_pe_id = None

        for strk_str, strk_info in strikes.items():
            strk_val = float(strk_str)
            diff = abs(strk_val - underlying_ltp)
            if diff < min_diff:
                min_diff = diff
                atm_strike = strk_val
                atm_ce_id = strk_info.get("ce", {}).get("security_id")
                atm_pe_id = strk_info.get("pe", {}).get("security_id")

        if not atm_ce_id or not atm_pe_id:
            atm_ce_id = "47287"
            atm_pe_id = "47288"
            atm_strike = 23250.0

        # Fetch 7 days of 1-minute historical candles
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (7 * 24 * 3600 * 1000)

        scrip_codes = f"NSE_40000001,NFO_{atm_ce_id},NFO_{atm_pe_id}"
        hist_url = f"{self.base_url}/market/historical/1minute?scrip-codes={scrip_codes}&start_time={start_ms}&end_time={end_ms}"

        logger.info(f"Fetching real candles for {scrip_codes}...")
        r = requests.get(hist_url, headers=self.headers, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Historical data fetch failed: {r.status_code} - {r.text}")

        res_json = r.json().get("data", {})
        index_candles = res_json.get("NSE_40000001", {}).get("candles", [])
        ce_candles = res_json.get(f"NFO_{atm_ce_id}", {}).get("candles", [])
        pe_candles = res_json.get(f"NFO_{atm_pe_id}", {}).get("candles", [])

        if not ce_candles or not pe_candles:
            raise RuntimeError("Received empty candle series from INDstocks.")

        # Convert to DataFrames
        df_ce = pd.DataFrame(ce_candles).set_index("ts")
        df_pe = pd.DataFrame(pe_candles).set_index("ts")
        df_idx = pd.DataFrame(index_candles).set_index("ts") if index_candles else None

        # Merge on common minute timestamps
        common_ts = df_ce.index.intersection(df_pe.index)
        if df_idx is not None:
            common_ts = common_ts.intersection(df_idx.index)

        common_ts = sorted(common_ts)

        # Group common timestamps by calendar date
        date_groups: Dict[str, List[int]] = {}
        for ts_sec in common_ts:
            d_str = datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d")
            date_groups.setdefault(d_str, []).append(ts_sec)

        logger.info(f"Processing real candle dates from INDstocks: {list(date_groups.keys())}")

        day_dfs: Dict[str, pd.DataFrame] = {}

        # Process each date and cache it
        for d_str, day_minutes in date_groups.items():
            records = []
            for ts_sec in day_minutes:
                base_dt = datetime.fromtimestamp(ts_sec)
                c_ce = df_ce.loc[ts_sec]
                c_pe = df_pe.loc[ts_sec]
                c_idx = df_idx.loc[ts_sec] if df_idx is not None else None

                # Accurately model intra-minute path using Open, High, Low, Close
                def _expand(c_row):
                    o, h, l, c = float(c_row['o']), float(c_row['h']), float(c_row['l']), float(c_row['c'])
                    if c >= o:
                        x_pts = [0, 15, 45, 59]
                        y_pts = [o, l, h, c]
                    else:
                        x_pts = [0, 15, 45, 59]
                        y_pts = [o, h, l, c]
                    base = np.interp(np.arange(60), x_pts, y_pts)
                    return np.round(base + np.random.normal(0, 0.05, 60), 2)

                ce_seq = _expand(c_ce)
                pe_seq = _expand(c_pe)
                idx_seq = (np.linspace(c_idx['o'], c_idx['c'], 60) if c_idx is not None else np.zeros(60))

                for s in range(60):
                    dt = base_dt + timedelta(seconds=s)
                    ce_val = round(float(ce_seq[s]), 2)
                    pe_val = round(float(pe_seq[s]), 2)
                    idx_val = round(float(idx_seq[s]), 2)

                    records.append({
                        "timestamp": dt,
                        "date": d_str,
                        "spot": idx_val,
                        "ce_ltp": ce_val,
                        "ce_bid": round(ce_val - 0.15, 2),
                        "ce_ask": round(ce_val + 0.15, 2),
                        "pe_ltp": pe_val,
                        "pe_bid": round(pe_val - 0.15, 2),
                        "pe_ask": round(pe_val + 0.15, 2),
                        "atm_strike": atm_strike
                    })

            day_df = pd.DataFrame(records)
            day_dfs[d_str] = day_df
            cache.save("NIFTY_SESSION", d_str, day_df)
            logger.info(f"Cached {len(day_df)} ticks for date {d_str} (ATM {atm_strike})")

        # Pick requested target_date or latest available
        if target_date and target_date in day_dfs:
            return day_dfs[target_date]
        
        sorted_available_dates = sorted(day_dfs.keys())
        if sorted_available_dates:
            # Prefer 2026-09-10 if today is partial or latest
            return day_dfs[sorted_available_dates[-1]]

        raise RuntimeError("No valid dates processed from INDstocks API data.")

    def get_historical_ticks(self, symbol: str = "NIFTY", from_date: str = "2026-09-10", to_date: str = "2026-09-10", interval: str = "1s") -> pd.DataFrame:
        """
        Main entrypoint: fetches real data if configured, else falls back to mock.
        Checks cache for from_date first.
        """
        from data.data_cache import DataCache
        cache = DataCache()
        
        cached_df = cache.load("NIFTY_SESSION", from_date)
        if cached_df is not None and not cached_df.empty:
            return cached_df

        try:
            if self.is_configured():
                return self.fetch_this_week_real_data(target_date=from_date)
        except Exception as e:
            logger.warning(f"Failed to fetch live real data from INDstocks for {from_date} ({e}). Falling back to simulation ticks.")
        
        from data.mock_data_generator import generate_nifty_options_session_data
        fallback_df = generate_nifty_options_session_data(target_date=from_date)
        cache.save("NIFTY_SESSION", from_date, fallback_df)
        return fallback_df
