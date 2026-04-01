"""
indicators.py
-------------
Manual implementations of Supertrend, VWAP, RSI, and Volume Average.
Matches TradingView's built-in Supertrend indicator exactly.

Key fix vs earlier version:
  Direction flip compares close against the CURRENT bar's finalized bands [i],
  not the previous bar's bands [i-1]. TradingView does the same — using [i-1]
  makes the flip condition harder to satisfy and causes missed signals.
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
ST_COL     = "supertrend"   # Supertrend line value (lower band when bullish, upper when bearish)
STD_COL    = "st_direction" # 1 = bullish, -1 = bearish
STL_COL    = "st_lower"     # Lower band (stop-loss for long trades)
STS_COL    = "st_upper"     # Upper band (stop-loss for short trades)
RSI_COL    = "rsi"
VWAP_COL   = "vwap"
VOLAVG_COL = "vol_avg"


# ---------------------------------------------------------------------------
# RSI  (Wilder's smoothing — matches TradingView's ta.rsi())
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
# VWAP  — resets every trading day (handles multi-day DataFrames correctly)
# ---------------------------------------------------------------------------
def _vwap_daily(df: pd.DataFrame) -> pd.Series:
    """
    Calculate VWAP anchored to each calendar day.
    Groups rows by date so VWAP resets at midnight — critical when the
    DataFrame spans multiple days (e.g. fetched with period='5d').
    """
    result = pd.Series(np.nan, index=df.index)
    for _, group_idx in df.groupby(df.index.date).groups.items():
        grp        = df.loc[group_idx]
        tp         = (grp["High"] + grp["Low"] + grp["Close"]) / 3
        cum_vol    = grp["Volume"].cumsum()
        cum_tpvol  = (tp * grp["Volume"]).cumsum()
        result.loc[group_idx] = (cum_tpvol / cum_vol.replace(0, np.nan)).values
    return result


# ---------------------------------------------------------------------------
# Supertrend  — matches TradingView's built-in Supertrend exactly
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

    Convention:
      direction = +1 → bullish (supertrend line = lower band, below price)
      direction = -1 → bearish (supertrend line = upper band, above price)

    TradingView match:
      Band persistence uses previous close vs previous bands.
      Direction flip compares current close vs CURRENT bar's finalized bands.
      This is the critical difference from a naive implementation that uses [i-1].
    """
    # ATR using Wilder's RMA — identical to TradingView's ta.atr()
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
        # ---- Band persistence ----
        # Upper band: only drops, never rises — unless previous close broke above it
        final_upper[i] = (
            basic_upper[i]
            if basic_upper[i] < final_upper[i - 1] or close_arr[i - 1] > final_upper[i - 1]
            else final_upper[i - 1]
        )
        # Lower band: only rises, never drops — unless previous close broke below it
        final_lower[i] = (
            basic_lower[i]
            if basic_lower[i] > final_lower[i - 1] or close_arr[i - 1] < final_lower[i - 1]
            else final_lower[i - 1]
        )

        # ---- Direction flip ----
        # FIX: compare against CURRENT bar's finalized bands [i], not previous [i-1].
        # TradingView: direction = close > upperBand ? bullish : close < lowerBand ? bearish : prev
        # Using [i-1] made the flip harder to trigger — this was causing missed signals.
        if close_arr[i] > final_upper[i]:
            direction[i] = 1
        elif close_arr[i] < final_lower[i]:
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
    Compute and append all indicators to df.
    Works correctly on multi-day DataFrames — VWAP resets each day,
    while Supertrend and RSI benefit from the longer history for warmup.
    """
    df = df.copy()

    st, std, stl, sts = _supertrend(df["High"], df["Low"], df["Close"])
    df[ST_COL]     = st
    df[STD_COL]    = std
    df[STL_COL]    = stl
    df[STS_COL]    = sts

    df[VWAP_COL]   = _vwap_daily(df)          # resets each trading day
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
