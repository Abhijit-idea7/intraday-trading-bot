"""
indicators.py
-------------
Adds Supertrend, VWAP, RSI, and Volume Average to a candle DataFrame.
Uses pandas-ta under the hood; all columns are appended in-place.
"""

import logging

import pandas as pd
import pandas_ta as ta

from config import (
    RSI_PERIOD,
    SUPERTREND_MULTIPLIER,
    SUPERTREND_PERIOD,
    VOLUME_LOOKBACK,
)

logger = logging.getLogger(__name__)

# Column name constants — derived from pandas-ta naming convention
ST_COL   = f"SUPERT_{SUPERTREND_PERIOD}_{SUPERTREND_MULTIPLIER}"   # Supertrend line value
STD_COL  = f"SUPERTd_{SUPERTREND_PERIOD}_{SUPERTREND_MULTIPLIER}"  # Direction: 1=bull, -1=bear
STL_COL  = f"SUPERTl_{SUPERTREND_PERIOD}_{SUPERTREND_MULTIPLIER}"  # Long stop (SL for longs)
STS_COL  = f"SUPERTs_{SUPERTREND_PERIOD}_{SUPERTREND_MULTIPLIER}"  # Short stop (SL for shorts)
RSI_COL  = f"RSI_{RSI_PERIOD}"
VWAP_COL = "VWAP_D"
VOLAVG_COL = "VOL_AVG"


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and append all required indicators to df.
    Returns the same DataFrame (with added columns) or raises on failure.

    Minimum rows needed: max(SUPERTREND_PERIOD * 2, RSI_PERIOD + 1, VOLUME_LOOKBACK) ≈ 20
    """
    df = df.copy()

    # --- Supertrend ---
    st = ta.supertrend(
        df["High"], df["Low"], df["Close"],
        length=SUPERTREND_PERIOD,
        multiplier=SUPERTREND_MULTIPLIER,
    )
    df = pd.concat([df, st], axis=1)

    # --- VWAP (anchored to day start — resets naturally since we fetch 1d of data) ---
    vwap = ta.vwap(df["High"], df["Low"], df["Close"], df["Volume"], anchor="D")
    df[VWAP_COL] = vwap

    # --- RSI ---
    df[RSI_COL] = ta.rsi(df["Close"], length=RSI_PERIOD)

    # --- Volume rolling average ---
    df[VOLAVG_COL] = df["Volume"].rolling(window=VOLUME_LOOKBACK).mean()

    return df


def get_supertrend_direction(df: pd.DataFrame, row: int = -1) -> int:
    """Return Supertrend direction for a given row: 1 = bullish, -1 = bearish."""
    return int(df[STD_COL].iloc[row])


def get_supertrend_sl(df: pd.DataFrame, direction: str, row: int = -1) -> float:
    """
    Return the Supertrend-based stop-loss price.
    For a LONG trade → use the lower band (STL_COL).
    For a SHORT trade → use the upper band (STS_COL).
    Falls back to the generic supertrend line if the directional column is NaN.
    """
    if direction == "BUY":
        sl = df[STL_COL].iloc[row]
        if pd.isna(sl):
            sl = df[ST_COL].iloc[row]
    else:
        sl = df[STS_COL].iloc[row]
        if pd.isna(sl):
            sl = df[ST_COL].iloc[row]
    return float(sl)
