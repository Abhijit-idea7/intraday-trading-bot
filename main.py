"""
main.py
-------
Entry point for the intraday trading bot.

Lifecycle (runs as a single long-lived process via GitHub Actions):
  1. Start at 08:45 IST (cron), wait until 09:20 IST to begin trading
  2. Loop every 2 minutes between 09:20 and 15:15 IST:
       a. Check exits for all open positions
       b. Scan candidates for new entry signals
  3. At 15:15 IST: force-close all open positions
  4. Print daily P&L summary and save to performance_log.csv
  5. CSV is committed back to the repo by the GitHub Actions workflow
"""

import logging
import time
from datetime import datetime

import pytz

from config import (
    LOOP_SLEEP_SECONDS,
    MAX_POSITIONS,
    SQUARE_OFF_TIME,
    TRADE_START_TIME,
)
from data_feed import get_top_candidates
from order_manager import calculate_quantity, place_order, square_off
from performance_tracker import PerformanceTracker
from strategy import check_exit_signal, fetch_and_prepare, generate_signal
from trade_tracker import TradeTracker

# ---------------------------------------------------------------------------
# Logging — structured output goes straight to GitHub Actions console
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

IST = pytz.timezone("Asia/Kolkata")


def ist_now() -> datetime:
    return datetime.now(IST)


def current_time_str() -> str:
    return ist_now().strftime("%H:%M")


def is_past(hhmm: str) -> bool:
    now = ist_now()
    h, m = map(int, hhmm.split(":"))
    limit = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return now >= limit


# ---------------------------------------------------------------------------
# Exit management
# ---------------------------------------------------------------------------

def check_exits(tracker: TradeTracker, perf: PerformanceTracker) -> None:
    """Evaluate all open positions and close any that hit SL, target, or trend flip."""
    for position in tracker.all_positions():
        symbol = position.symbol
        try:
            df = fetch_and_prepare(symbol)
            if df is None:
                continue

            reason = check_exit_signal(df, position.__dict__)
            if reason:
                exit_price = float(df["Close"].iloc[-2])
                ok = square_off(symbol, position.direction, position.quantity)
                if ok:
                    tracker.remove_position(symbol)
                    perf.record_trade(
                        symbol      = symbol,
                        direction   = position.direction,
                        entry_price = position.entry_price,
                        exit_price  = exit_price,
                        quantity    = position.quantity,
                        entry_time  = position.entry_time,
                        exit_reason = reason,
                    )
        except Exception as e:
            logger.error(f"Error checking exit for {symbol}: {e}")


def square_off_all(tracker: TradeTracker, perf: PerformanceTracker) -> None:
    """Force-close every open position at 15:15 IST."""
    logger.info("=== SQUARE-OFF TIME: closing all open positions ===")
    for position in tracker.all_positions():
        try:
            # Use last known close as exit price for P&L approximation
            df = fetch_and_prepare(position.symbol)
            exit_price = float(df["Close"].iloc[-2]) if df is not None else position.entry_price

            ok = square_off(position.symbol, position.direction, position.quantity)
            if ok:
                tracker.remove_position(position.symbol)
                perf.record_trade(
                    symbol      = position.symbol,
                    direction   = position.direction,
                    entry_price = position.entry_price,
                    exit_price  = exit_price,
                    quantity    = position.quantity,
                    entry_time  = position.entry_time,
                    exit_reason = "SQUARE_OFF",
                )
        except Exception as e:
            logger.error(f"Error squaring off {position.symbol}: {e}")
    logger.info("All positions closed.")


# ---------------------------------------------------------------------------
# Entry management
# ---------------------------------------------------------------------------

def scan_for_entries(candidates: list[str], tracker: TradeTracker) -> None:
    """Check each candidate for a fresh entry signal."""
    for symbol in candidates:
        if not tracker.can_open_new_trade():
            logger.info(f"All {MAX_POSITIONS} slots occupied — waiting for a position to close.")
            break

        if tracker.has_position(symbol):
            continue

        try:
            df = fetch_and_prepare(symbol)
            if df is None:
                continue

            signal = generate_signal(df, symbol=symbol)

            if signal["action"] in ("BUY", "SELL"):
                entry_price = float(df["Close"].iloc[-2])
                quantity    = calculate_quantity(entry_price)

                if quantity < 1:
                    logger.warning(f"{symbol}: quantity rounds to 0 at ₹{entry_price:.2f}, skipping.")
                    continue

                ok = place_order(symbol, signal["action"], quantity)
                if ok:
                    tracker.add_position(
                        symbol      = symbol,
                        direction   = signal["action"],
                        entry_price = entry_price,
                        sl          = signal["sl"],
                        target      = signal["target"],
                        quantity    = quantity,
                    )

        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=" * 60)
    logger.info("Intraday Trading Bot starting up")
    logger.info(f"Trade window : {TRADE_START_TIME} → {SQUARE_OFF_TIME} IST")
    logger.info(f"Max positions: {MAX_POSITIONS}")
    logger.info("=" * 60)

    # Wait for trade start time (runner may start at 08:45 IST)
    while not is_past(TRADE_START_TIME):
        logger.info(f"Waiting for {TRADE_START_TIME} IST... (now {current_time_str()})")
        time.sleep(30)

    # Select today's watchlist once at start
    logger.info("Selecting today's top candidates by ATR%...")
    candidates = get_top_candidates()
    logger.info(f"Watchlist: {candidates}")

    tracker = TradeTracker()
    perf    = PerformanceTracker()

    # Main strategy loop
    while True:
        now_str = current_time_str()
        logger.info(f"--- Loop tick at {now_str} IST ---")

        # Hard square-off gate
        if is_past(SQUARE_OFF_TIME):
            square_off_all(tracker, perf)
            break

        # 1. Check exits first
        if tracker.open_count() > 0:
            check_exits(tracker, perf)

        # 2. Scan for new entries
        if tracker.can_open_new_trade():
            scan_for_entries(candidates, tracker)

        # 3. Status log
        logger.info(tracker.summary())

        # 4. Sleep until next candle
        logger.info(f"Sleeping {LOOP_SLEEP_SECONDS}s until next candle...")
        time.sleep(LOOP_SLEEP_SECONDS)

    # ---------------------------------------------------------------------------
    # End of day — print summary and save to CSV
    # ---------------------------------------------------------------------------
    perf.daily_summary()
    perf.save_to_csv()

    logger.info("Bot exited cleanly.")


if __name__ == "__main__":
    run()
