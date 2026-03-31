"""
indicators.py
-------------
Manual implementations of Supertrend, VWAP, RSI, and Volume Average.
No external TA library required — only pandas and numpy.
"""

import numpy as np
import pandas as pd

from config import (
    RSI_PERIOD,
    SUPERTREND_MULTIPLIER,
    SUPERTREND_PERIOD,
    VOLUME_LOOKBACK,
)

# Column name constants used across strategy.py
ST_COL     = "supertrend"     # Supertrend line value
STD_COL    = "st_direction"   # 1 = bullish, -1 = bearish
STL_COL    = "st_lower"       # Lower band  (stop for long trades)
STS_COL    = "st_upper"       # Upper band  (stop for short trades)
RSI_COL    = "rsi"
VWAP_COL   = "vwap"
VOLAVG_COL = "vol_avg"


# ---------------------------------------------------------------------------
# RSI  (Wilder's smoothing = EMA with alpha=1/period)
# ---------------------------------------------------------------------------
def _rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# VWAP  (anchored to the first row — correct when data starts at market open)
# ---------------------------------------------------------------------------
def _vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical   = (high + low + close) / 3
    cum_vol   = volume.cumsum()
    cum_tpvol = (typical * volume).cumsum()
    return cum_tpvol / cum_vol.replace(0, np.nan)


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------
def _supertrend(
    high:       pd.Series,
    low:        pd.Series,
    close:      pd.Series,
    period:     int   = SUPERTREND_PERIOD,
    multiplier: float = SUPERTREND_MULTIPLIER,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    Returns (supertrend_line, direction, lower_band, upper_band).
    direction: numpy int array — 1 = bullish, -1 = bearish.
    """
    # ATR (Wilder)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    hl2         = (high + low) / 2
    basic_upper = (hl2 + multiplier * atr).values
    basic_lower = (hl2 - multiplier * atr).values
    close_arr   = close.values
    n           = len(close_arr)

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    direction   = np.ones(n, dtype=int)

    for i in range(1, n):
        # Upper band only drops — never rises — unless price breaks above it
        final_upper[i] = (
            basic_upper[i]
            if basic_upper[i] < final_upper[i - 1] or close_arr[i - 1] > final_upper[i - 1]
            else final_upper[i - 1]
        )
        # Lower band only rises — never drops — unless price breaks below it
        final_lower[i] = (
            basic_lower[i]
            if basic_lower[i] > final_lower[i - 1] or close_arr[i - 1] < final_lower[i - 1]
            else final_lower[i - 1]
        )
        # Direction flip logic
        if close_arr[i] > final_upper[i - 1]:
            direction[i] = 1
        elif close_arr[i] < final_lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

    supertrend_line = np.where(direction == 1, final_lower, final_upper)

    idx = close.index
    return (
        pd.Series(supertrend_line, index=idx, name=ST_COL),
        pd.Series(direction,       index=idx, name=STD_COL),
        pd.Series(final_lower,     index=idx, name=STL_COL),
        pd.Series(final_upper,     index=idx, name=STS_COL),
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all indicators and append them to df.
    Requires columns: Open, High, Low, Close, Volume.
    Minimum rows: ~20 (to allow ATR and RSI warmup).
    """
    df = df.copy()

    st, std, stl, sts = _supertrend(df["High"], df["Low"], df["Close"])
    df[ST_COL]     = st
    df[STD_COL]    = std
    df[STL_COL]    = stl
    df[STS_COL]    = sts

    df[VWAP_COL]   = _vwap(df["High"], df["Low"], df["Close"], df["Volume"])
    df[RSI_COL]    = _rsi(df["Close"])
    df[VOLAVG_COL] = df["Volume"].rolling(window=VOLUME_LOOKBACK).mean()

    return df


def get_supertrend_direction(df: pd.DataFrame, row: int = -1) -> int:
    return int(df[STD_COL].iloc[row])


def get_supertrend_sl(df: pd.DataFrame, direction: str, row: int = -1) -> float:
    """
    Stop-loss price from the Supertrend bands.
    Long  → lower band (STL_COL)
    Short → upper band (STS_COL)
    """
    sl = df[STL_COL].iloc[row] if direction == "BUY" else df[STS_COL].iloc[row]
    if pd.isna(sl):
        sl = df[ST_COL].iloc[row]
    return float(sl)
