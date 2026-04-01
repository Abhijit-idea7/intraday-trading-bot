"""
strategy.py
-----------
Signal generation: Supertrend + VWAP + Volume Spike + RSI Guard.

Entry logic (applied to the last COMPLETED candle = iloc[-2]):
  LONG  — Supertrend flips to bullish AND close > VWAP AND RSI < RSI_OVERBOUGHT
  SHORT — Supertrend flips to bearish AND close < VWAP AND RSI > RSI_OVERSOLD

  Volume spike is logged for reference but NOT used as an entry filter.
  Reason: on 2-min charts the rolling avg includes high-volume morning candles,
  causing every afternoon candle to appear as "low volume" and blocking valid trades.

NOTE: We always use iloc[-2] as the signal candle (last fully closed bar).
      iloc[-1] is the currently-forming candle on yfinance and has
      incomplete volume — using it causes the volume filter to always fail.

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
    ST_COL,
    STD_COL,
    VOLAVG_COL,
    VWAP_COL,
    add_indicators,
    get_supertrend_sl,
)

logger = logging.getLogger(__name__)

_HOLD = {"action": "HOLD", "sl": 0.0, "target": 0.0}

# Minimum candles needed for indicator warmup
# Supertrend period=10, RSI period=14, Volume lookback=10 → need ~15
MIN_CANDLES = 15


def fetch_and_prepare(symbol: str) -> pd.DataFrame | None:
    """
    Fetch 5 days of candles for proper ATR/RSI warmup, compute all indicators,
    then return only TODAY's candles for signal generation.

    Why 5d? TradingView's Supertrend ATR is warmed up over months of data.
    With only 1d (today's ~60-90 candles), the ATR diverges from TradingView's
    especially in the first 1-2 hours. 5d gives ~300+ candles — much closer.
    VWAP is calculated per day so it still anchors correctly to today's open.
    """
    df_full = fetch_candles(symbol, period="5d")
    if df_full is None or len(df_full) < MIN_CANDLES:
        logger.info(f"{symbol}: only {len(df_full) if df_full is not None else 0} candles — need {MIN_CANDLES}, skipping.")
        return None
    try:
        df_ind = add_indicators(df_full)
        # Filter to today only for signal generation
        today  = df_ind.index[-1].date()
        df_today = df_ind[df_ind.index.date == today]
        if len(df_today) < 3:
            logger.info(f"{symbol}: only {len(df_today)} candles today — waiting for more data.")
            return None
        return df_today
    except Exception as e:
        logger.warning(f"{symbol}: indicator calculation failed — {e}")
        return None


def generate_signal(df: pd.DataFrame, symbol: str = "") -> dict:
    """
    Evaluate the last COMPLETED candle (iloc[-2]) for an entry signal.

    iloc[-1] = currently forming candle (incomplete volume — do NOT use for signals)
    iloc[-2] = last fully closed candle  ← signal candle
    iloc[-3] = candle before that        ← used to detect direction flip
    """
    # Need at least 3 rows: [-3], [-2], [-1]
    if len(df) < 3:
        return _HOLD

    try:
        prev_dir = int(df[STD_COL].iloc[-3])   # direction 2 candles ago
        curr_dir = int(df[STD_COL].iloc[-2])   # direction at last completed candle
    except (KeyError, IndexError, ValueError) as e:
        logger.warning(f"{symbol}: could not read Supertrend direction — {e}")
        return _HOLD

    # Read all values from the last COMPLETED candle (iloc[-2])
    close   = df["Close"].iloc[-2]
    vwap    = df[VWAP_COL].iloc[-2]
    rsi     = df[RSI_COL].iloc[-2]
    volume  = df["Volume"].iloc[-2]
    vol_avg = df[VOLAVG_COL].iloc[-2]

    # Guard: skip if any indicator is NaN (still in warmup period)
    if any(pd.isna(v) for v in [vwap, rsi, vol_avg]):
        logger.info(f"{symbol}: indicator warmup not complete (NaN values), skipping.")
        return _HOLD

    flip_long  = (prev_dir == -1) and (curr_dir == 1)
    flip_short = (prev_dir ==  1) and (curr_dir == -1)
    vol_ratio  = (volume / vol_avg) if vol_avg > 0 else 0

    st_band = df[ST_COL].iloc[-2]   # Supertrend line value — compare this with TradingView
    # Log current state — compare st_band with TradingView's Supertrend value to verify match
    logger.info(
        f"{symbol}: dir={curr_dir:+d} flip_long={flip_long} flip_short={flip_short} | "
        f"close={close:.2f} ST={st_band:.2f} vwap={vwap:.2f} {'↑above' if close > vwap else '↓below'} | "
        f"rsi={rsi:.1f} | vol_ratio={vol_ratio:.2f}x"
    )

    # ---- LONG signal ----
    if flip_long:
        if close <= vwap:
            logger.info(f"{symbol}: LONG flip REJECTED — close {close:.2f} below VWAP {vwap:.2f}")
        elif rsi >= RSI_OVERBOUGHT:
            logger.info(f"{symbol}: LONG flip REJECTED — RSI {rsi:.1f} overbought (>= {RSI_OVERBOUGHT})")
        else:
            sl   = get_supertrend_sl(df, "BUY", row=-2)
            risk = close - sl
            if risk <= 0:
                logger.info(f"{symbol}: LONG flip REJECTED — invalid risk {risk:.2f}")
                return _HOLD
            target = close + (RISK_REWARD_RATIO * risk)
            logger.info(f"{symbol}: *** BUY SIGNAL *** entry={close:.2f} sl={sl:.2f} target={target:.2f} risk=₹{risk:.2f} vol={vol_ratio:.2f}x")
            return {"action": "BUY", "sl": sl, "target": target}

    # ---- SHORT signal ----
    if flip_short:
        if close >= vwap:
            logger.info(f"{symbol}: SHORT flip REJECTED — close {close:.2f} above VWAP {vwap:.2f}")
        elif rsi <= RSI_OVERSOLD:
            logger.info(f"{symbol}: SHORT flip REJECTED — RSI {rsi:.1f} oversold (<= {RSI_OVERSOLD})")
        else:
            sl   = get_supertrend_sl(df, "SELL", row=-2)
            risk = sl - close
            if risk <= 0:
                logger.info(f"{symbol}: SHORT flip REJECTED — invalid risk {risk:.2f}")
                return _HOLD
            target = close - (RISK_REWARD_RATIO * risk)
            logger.info(f"{symbol}: *** SELL SIGNAL *** entry={close:.2f} sl={sl:.2f} target={target:.2f} risk=₹{risk:.2f} vol={vol_ratio:.2f}x")
            return {"action": "SELL", "sl": sl, "target": target}

    return _HOLD


def check_exit_signal(df: pd.DataFrame, position: dict) -> str | None:
    """
    Check whether an open position should be closed based on:
      1. Price hitting target
      2. Price hitting stop-loss
      3. Supertrend flipping against the trade direction

    Uses iloc[-2] (last completed candle) for consistency.
    """
    current_price = df["Close"].iloc[-2]
    direction     = position["direction"]
    sl            = position["sl"]
    target        = position["target"]

    try:
        curr_dir = int(df[STD_COL].iloc[-2])
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
