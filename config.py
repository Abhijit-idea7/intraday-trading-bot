import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Stock Universe — High Beta NSE Stocks
# ---------------------------------------------------------------------------
STOCK_UNIVERSE = [
    "TMPV",   "TATASTEEL", "SAIL",      "BANKBARODA", "PNB",
    "CANBK",  "ADANIENT",  "ADANIPORTS", "ETERNAL",   "SUZLON",
    "IDEA",   "NHPC",      "IRFC",       "HINDCOPPER", "YESBANK",
]

# ---------------------------------------------------------------------------
# Strategy Parameters
# ---------------------------------------------------------------------------
SUPERTREND_PERIOD       = 10
SUPERTREND_MULTIPLIER   = 2.0

RSI_PERIOD              = 14
RSI_OVERBOUGHT          = 72      # No new longs above this
RSI_OVERSOLD            = 28      # No new shorts below this

VOLUME_SPIKE_MULTIPLIER = 1.2     # Current volume must be > 1.2x avg (1.5 was too tight on 2m candles)
VOLUME_LOOKBACK         = 10      # Candles used to compute avg volume

# ---------------------------------------------------------------------------
# Position Sizing
# ---------------------------------------------------------------------------
POSITION_SIZE_INR = 100_000       # Capital per trade in INR
MAX_POSITIONS     = 10            # Max simultaneous open positions (matches TOP_N_STOCKS)
TOP_N_STOCKS      = 10            # Candidates selected daily by ATR%

# ---------------------------------------------------------------------------
# Risk / Reward
# ---------------------------------------------------------------------------
RISK_REWARD_RATIO = 2.0           # Target = 2× the risk distance

# ---------------------------------------------------------------------------
# Timing  (all IST)
# ---------------------------------------------------------------------------
TRADE_START_TIME   = "09:20"      # No entries before this
SQUARE_OFF_TIME    = "15:15"      # Force-close all positions at this time
CANDLE_INTERVAL    = "2m"         # yfinance interval string
LOOP_SLEEP_SECONDS = 120          # Sleep between strategy iterations (matches 2m candle)

# ---------------------------------------------------------------------------
# Stocksdeveloper Webhook
# ---------------------------------------------------------------------------
STOCKSDEVELOPER_URL     = "https://tv.stocksdeveloper.in/"
STOCKSDEVELOPER_API_KEY = os.getenv("STOCKSDEVELOPER_API_KEY")
STOCKSDEVELOPER_ACCOUNT = os.getenv("STOCKSDEVELOPER_ACCOUNT", "AbhiZerodha")

if not STOCKSDEVELOPER_API_KEY:
    raise EnvironmentError(
        "STOCKSDEVELOPER_API_KEY is not set. "
        "Add it to your .env file or GitHub Actions secrets."
    )

# ---------------------------------------------------------------------------
# Order Defaults
# ---------------------------------------------------------------------------
EXCHANGE     = "NSE"
PRODUCT_TYPE = "INTRADAY"
ORDER_TYPE   = "MARKET"
VARIETY      = "REGULAR"
