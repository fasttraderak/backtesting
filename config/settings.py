import os
from pathlib import Path
from datetime import time
from typing import List, Tuple
from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class CostSettings(BaseModel):
    brokerage_per_order: float = Field(
        default_factory=lambda: float(os.getenv("BROKERAGE_PER_ORDER", "20.0")),
        description="Brokerage charged per executed order (INR)"
    )
    stt_rate: float = Field(
        default=0.000625,
        description="Securities Transaction Tax on Sell premium (0.0625%)"
    )
    exchange_rate: float = Field(
        default=0.000505,
        description="NSE Exchange Turnover charge on premium turnover (0.0505%)"
    )
    gst_rate: float = Field(
        default=0.18,
        description="GST 18% on (Brokerage + Exchange turnover charge)"
    )
    sebi_rate: float = Field(
        default=0.000001,
        description="SEBI charges INR 10 per crore (0.0001%)"
    )
    stamp_duty_rate: float = Field(
        default=0.00003,
        description="Stamp duty on Buy turnover (0.003%)"
    )
    slippage_per_leg: float = Field(
        default_factory=lambda: float(os.getenv("SLIPPAGE_PER_LEG", "0.15")),
        description="Estimated bid-ask slippage per contract leg in points"
    )


class LLMSettings(BaseModel):
    base_url: str = Field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://ai.quantflash.cloud/v1"),
        description="OpenAI-compatible proxy endpoint"
    )
    api_key: str = Field(
        default_factory=lambda: os.getenv("LLM_API_KEY", "sk-antigravity"),
        description="API Key for the proxy"
    )
    model: str = Field(
        default_factory=lambda: os.getenv("LLM_MODEL", "gemini-3.8-flash-high"),
        description="Primary Gemini model"
    )
    fallback_model: str = Field(
        default_factory=lambda: os.getenv("LLM_FALLBACK_MODEL", "gemini-pro-agent"),
        description="Deep reasoning fallback model"
    )


class INDmoneySettings(BaseModel):
    api_key: str = Field(
        default_factory=lambda: os.getenv("INDMONEY_API_KEY", ""),
        description="INDmoney API Key"
    )
    api_secret: str = Field(
        default_factory=lambda: os.getenv("INDMONEY_API_SECRET", ""),
        description="INDmoney API Secret"
    )
    access_token: str = Field(
        default_factory=lambda: os.getenv("INDMONEY_ACCESS_TOKEN", ""),
        description="Session Access Token"
    )
    base_url: str = "https://api.indmoney.com/v1"


class Settings(BaseModel):
    initial_capital: float = Field(
        default_factory=lambda: float(os.getenv("INITIAL_CAPITAL", "100000.0")),
        description="Initial starting trading capital in INR"
    )
    lot_size: int = Field(
        default_factory=lambda: int(os.getenv("DEFAULT_LOT_SIZE", "65")),
        description="Nifty 50 contract lot size (default 65)"
    )
    max_daily_loss: float = Field(
        default_factory=lambda: float(os.getenv("MAX_DAILY_LOSS", "2500.0")),
        description="Daily loss circuit breaker / cutoff in INR (2.5%)"
    )
    market_open: time = time(9, 15, 0)
    market_close: time = time(15, 30, 0)
    
    # 1-hour interval segments between 09:15 and 15:30
    hourly_windows: List[Tuple[str, str, str]] = [
        ("09:15", "10:15", "Morning Open Volatility"),
        ("10:15", "11:15", "Morning Settling"),
        ("11:15", "12:15", "Midday Consolidation - Sweet Spot 1"),
        ("12:15", "13:15", "Lunch Lull - Sweet Spot 2"),
        ("13:15", "14:15", "Early Afternoon Setup"),
        ("14:15", "15:30", "Afternoon Close & Gamma Volatility")
    ]
    
    costs: CostSettings = Field(default_factory=CostSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    indmoney: INDmoneySettings = Field(default_factory=INDmoneySettings)
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data" / "cache"


settings = Settings()
