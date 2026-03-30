"""
strategy.py
-----------
Signal generation: Supertrend + VWAP + Volume Spike + RSI Guard.

Entry logic (applied to the most recently CLOSED candle):
  LONG  — Supertrend flips to bullish AND close > VWAP
           AND volume > 1.5× avg AND RSI < RSI_OVERBOUGHT
  SHORT — Supertrend flips to bearish AND close < VWAP
           AND volume > 1.5× avg AND RSI > RSI_OVERSOLD

Returns a dict:
  { "action": "BUY" | "SELL" | "HOLD",
    "sl":     float,   # stop-loss price
    "target": float }  # target price (Risk × RISK_REWARD_RATIO)
"""

import logging

import pandas as pd

from config import (
    RISK_REWARD_RATIO,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    VOLUME_SPIKE_MULTIPLIER,
)
from data_feed import fetch_candles
from indicators import (
    RSI_COL,
    STD_COL,
    VOLAVG_COL,
    VWAP_COL,
    add_indicators,
    get_supertrend_sl,
)

logger = logging.getLogger(__name__)

_HOLD = {"action": "HOLD", "sl": 0.0, "target": 0.0}


def fetch_and_prepare(symbol: str) -> pd.DataFrame | None:
    """
    Download today's 3-min candles and attach all indicators.
    Returns None if data is insufficient.
    """
    df = fetch_candles(symbol)
    if df is None or len(df) < 20:
        logger.debug(f"{symbol}: not enough candles ({len(df) if df is not None else 0}), skipping.")
        return None
    try:
        return add_indicators(df)
    except Exception as e:
        logger.warning(f"{symbol}: indicator calculation failed — {e}")
        return None


def generate_signal(df: pd.DataFrame) -> dict:
    """
    Evaluate the most recently completed candle for an entry signal.

    We read index -1 as the signal candle (last fully closed bar).
    We compare direction at -1 vs -2 to detect a fresh Supertrend flip.
    """
    try:
        prev_dir = int(df[STD_COL].iloc[-2])
        curr_dir = int(df[STD_COL].iloc[-1])
    except (KeyError, IndexError, ValueError):
        return _HOLD

    close      = df["Close"].iloc[-1]
    vwap       = df[VWAP_COL].iloc[-1]
    rsi        = df[RSI_COL].iloc[-1]
    volume     = df["Volume"].iloc[-1]
    vol_avg    = df[VOLAVG_COL].iloc[-1]

    # Guard: skip if any indicator is NaN
    if any(pd.isna(v) for v in [vwap, rsi, vol_avg]):
        return _HOLD

    volume_ok = volume >= VOLUME_SPIKE_MULTIPLIER * vol_avg
    flip_long  = (prev_dir == -1) and (curr_dir == 1)
    flip_short = (prev_dir ==  1) and (curr_dir == -1)

    # ---- LONG signal ----
    if flip_long and close > vwap and volume_ok and rsi < RSI_OVERBOUGHT:
        sl     = get_supertrend_sl(df, "BUY")
        risk   = close - sl
        if risk <= 0:
            return _HOLD
        target = close + (RISK_REWARD_RATIO * risk)
        logger.debug(f"LONG signal | close={close:.2f} vwap={vwap:.2f} rsi={rsi:.1f} sl={sl:.2f} tgt={target:.2f}")
        return {"action": "BUY", "sl": sl, "target": target}

    # ---- SHORT signal ----
    if flip_short and close < vwap and volume_ok and rsi > RSI_OVERSOLD:
        sl     = get_supertrend_sl(df, "SELL")
        risk   = sl - close
        if risk <= 0:
            return _HOLD
        target = close - (RISK_REWARD_RATIO * risk)
        logger.debug(f"SHORT signal | close={close:.2f} vwap={vwap:.2f} rsi={rsi:.1f} sl={sl:.2f} tgt={target:.2f}")
        return {"action": "SELL", "sl": sl, "target": target}

    return _HOLD


def check_exit_signal(df: pd.DataFrame, position: dict) -> str | None:
    """
    Check whether an open position should be closed based on:
      1. Price hitting target
      2. Price hitting stop-loss
      3. Supertrend flipping against the trade direction

    Returns "TARGET", "STOP_LOSS", "TREND_FLIP", or None (hold).
    """
    current_price = df["Close"].iloc[-1]
    direction     = position["direction"]
    sl            = position["sl"]
    target        = position["target"]

    try:
        curr_dir = int(df[STD_COL].iloc[-1])
    except (KeyError, ValueError):
        curr_dir = None

    if direction == "BUY":
        if current_price >= target:
            return "TARGET"
        if current_price <= sl:
            return "STOP_LOSS"
        if curr_dir == -1:
            return "TREND_FLIP"
    else:  # SHORT
        if current_price <= target:
            return "TARGET"
        if current_price >= sl:
            return "STOP_LOSS"
        if curr_dir == 1:
            return "TREND_FLIP"

    return None
