import os
from pathlib import Path
from typing import Optional
import pandas as pd
from config.settings import settings


class DataCache:
    """
    Manages local persistent caching of high-frequency options tick data.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or settings.data_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, symbol: str, date_str: str) -> Path:
        safe_sym = symbol.replace(":", "_").replace("/", "_")
        return self.cache_dir / f"{safe_sym}_{date_str}.parquet"

    def exists(self, symbol: str, date_str: str) -> bool:
        return self._get_path(symbol, date_str).exists()

    def save(self, symbol: str, date_str: str, df: pd.DataFrame) -> Path:
        path = self._get_path(symbol, date_str)
        df.to_parquet(path, index=False)
        return path

    def load(self, symbol: str, date_str: str) -> Optional[pd.DataFrame]:
        path = self._get_path(symbol, date_str)
        if path.exists():
            df = pd.read_parquet(path)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df
        return None

    def clear(self):
        for f in self.cache_dir.glob("*.parquet"):
            f.unlink()
