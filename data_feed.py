"""
data_feed.py
------------
Fetches OHLCV candle data from Yahoo Finance for NSE-listed stocks.
All symbols are automatically suffixed with ".NS" for NSE.
"""

import logging
import time

import pandas as pd
import yfinance as yf

from config import CANDLE_INTERVAL, STOCK_UNIVERSE, TOP_N_STOCKS

logger = logging.getLogger(__name__)

def _ns(symbol: str) -> str:
    """Return Yahoo Finance ticker string for NSE."""
    return f"{symbol}.NS"


def fetch_candles(symbol: str, interval: str = CANDLE_INTERVAL, period: str = "1d") -> pd.DataFrame | None:
    """
    Fetch intraday OHLCV candles for a symbol.
    Returns a clean DataFrame or None on failure.
    """
    for attempt in range(3):
        try:
            df = yf.Ticker(_ns(symbol)).history(interval=interval, period=period)
            if df.empty:
                logger.warning(f"{symbol}: empty data returned (attempt {attempt + 1})")
                time.sleep(2)
                continue
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df.index = pd.to_datetime(df.index)
            # Keep only today's session — yfinance sometimes bleeds in previous day's candles
            # which would anchor VWAP to the wrong start point
            if not df.empty:
                last_date = df.index[-1].normalize()
                df = df[df.index >= last_date]
            return df
        except Exception as e:
            logger.warning(f"{symbol}: fetch error on attempt {attempt + 1} — {e}")
            time.sleep(2)
    logger.error(f"{symbol}: all fetch attempts failed, skipping.")
    return None


def fetch_daily_candles(symbol: str, period: str = "10d") -> pd.DataFrame | None:
    """
    Fetch daily OHLCV candles. Used for ATR-based stock ranking.
    """
    try:
        df = yf.Ticker(_ns(symbol)).history(interval="1d", period=period)
        if df.empty:
            return None
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception as e:
        logger.warning(f"{symbol}: daily fetch error — {e}")
        return None


def get_top_candidates() -> list[str]:
    """
    Rank STOCK_UNIVERSE by ATR% (ATR / Close price) using recent daily candles.
    Returns the top TOP_N_STOCKS symbols — the most volatile ones to trade today.
    ATR% normalises across price levels so a ₹100 stock and ₹2000 stock are comparable.
    """
    scores: dict[str, float] = {}

    for symbol in STOCK_UNIVERSE:
        df = fetch_daily_candles(symbol, period="10d")
        if df is None or len(df) < 3:
            continue
        try:
            prev_close = df["Close"].shift(1)
            tr = pd.concat([
                df["High"] - df["Low"],
                (df["High"] - prev_close).abs(),
                (df["Low"]  - prev_close).abs(),
            ], axis=1).max(axis=1)

            atr     = tr.mean()
            atr_pct = atr / df["Close"].iloc[-1]
            scores[symbol] = atr_pct
        except Exception as e:
            logger.warning(f"{symbol}: ATR calculation error — {e}")

    if not scores:
        logger.warning("Could not score any stocks; falling back to full universe.")
        return STOCK_UNIVERSE[:TOP_N_STOCKS]

    ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
    top    = ranked[:TOP_N_STOCKS]
    logger.info(f"Today's top {TOP_N_STOCKS} candidates by ATR%: {top}")
    logger.info({s: f"{scores[s]*100:.2f}%" for s in top})
    return top
