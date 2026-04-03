"""
performance_tracker.py
----------------------
Records every trade, computes daily P&L summary, and appends results
to performance_log.csv which is committed back to the repo at end of day.

CSV columns:
  date, symbol, direction, entry_time, exit_time,
  entry_price, exit_price, quantity, pnl_inr, exit_reason

Daily summary is printed to GitHub Actions logs at square-off time.
"""

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytz

logger = logging.getLogger(__name__)

IST      = pytz.timezone("Asia/Kolkata")
LOG_FILE = Path("performance_log.csv")

CSV_FIELDS = [
    "date", "symbol", "direction",
    "entry_time", "exit_time",
    "entry_price", "exit_price", "quantity",
    "pnl_inr", "exit_reason",
]


# ---------------------------------------------------------------------------
# Data structure for a single closed trade
# ---------------------------------------------------------------------------
@dataclass
class TradeRecord:
    date:        str
    symbol:      str
    direction:   str    # "BUY" or "SELL"
    entry_time:  str    # "HH:MM"
    exit_time:   str    # "HH:MM"
    entry_price: float
    exit_price:  float
    quantity:    int
    pnl_inr:     float  # positive = profit, negative = loss
    exit_reason: str    # TARGET | STOP_LOSS | TREND_FLIP | SQUARE_OFF


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------
class PerformanceTracker:
    def __init__(self) -> None:
        self.trades: list[TradeRecord] = []

    # ------------------------------------------------------------------
    # Record a closed trade
    # ------------------------------------------------------------------
    def record_trade(
        self,
        symbol:      str,
        direction:   str,
        entry_price: float,
        exit_price:  float,
        quantity:    int,
        entry_time:  str,
        exit_reason: str,
    ) -> TradeRecord:
        now      = datetime.now(IST)
        exit_time = now.strftime("%H:%M")

        pnl = (
            (exit_price - entry_price) * quantity
            if direction == "BUY"
            else (entry_price - exit_price) * quantity
        )
        pnl = round(pnl, 2)

        record = TradeRecord(
            date        = now.strftime("%Y-%m-%d"),
            symbol      = symbol,
            direction   = direction,
            entry_time  = entry_time,
            exit_time   = exit_time,
            entry_price = entry_price,
            exit_price  = exit_price,
            quantity    = quantity,
            pnl_inr     = pnl,
            exit_reason = exit_reason,
        )
        self.trades.append(record)

        emoji = "✅" if pnl >= 0 else "❌"
        logger.info(
            f"[PERF] {emoji} {direction} {symbol} | "
            f"entry={entry_price:.2f} exit={exit_price:.2f} qty={quantity} | "
            f"P&L=₹{pnl:+,.0f} | reason={exit_reason}"
        )
        return record

    # ------------------------------------------------------------------
    # End-of-day summary printed to GitHub Actions logs
    # ------------------------------------------------------------------
    def daily_summary(self) -> None:
        sep = "=" * 55
        logger.info(f"[PERF] {sep}")

        if not self.trades:
            logger.info("[PERF] No trades executed today.")
            logger.info(f"[PERF] {sep}")
            return

        total       = len(self.trades)
        profitable  = [t for t in self.trades if t.pnl_inr > 0]
        losses      = [t for t in self.trades if t.pnl_inr <= 0]
        gross_pnl   = sum(t.pnl_inr for t in self.trades)
        # Zerodha intraday brokerage: ₹20 per order × 2 legs = ₹40 per trade
        brokerage   = total * 40
        net_pnl     = gross_pnl - brokerage
        win_rate    = len(profitable) / total * 100
        best        = max(self.trades, key=lambda t: t.pnl_inr)
        worst       = min(self.trades, key=lambda t: t.pnl_inr)

        lines = [
            f"DAILY PERFORMANCE — {self.trades[0].date}",
            sep,
            f"  Total trades      : {total}",
            f"  Profitable        : {len(profitable)}  ({win_rate:.1f}% win rate)",
            f"  Loss-making       : {len(losses)}",
            sep,
            f"  Gross P&L         : ₹{gross_pnl:+,.0f}",
            f"  Brokerage (est.)  : -₹{brokerage:,.0f}",
            f"  Net P&L (est.)    : ₹{net_pnl:+,.0f}",
            sep,
            f"  Best trade  : {best.symbol} {best.direction} ₹{best.pnl_inr:+,.0f} ({best.exit_reason})",
            f"  Worst trade : {worst.symbol} {worst.direction} ₹{worst.pnl_inr:+,.0f} ({worst.exit_reason})",
            sep,
            "  TRADE BREAKDOWN:",
        ]
        for t in self.trades:
            emoji = "✅" if t.pnl_inr >= 0 else "❌"
            lines.append(
                f"    {emoji} {t.symbol:12s} {t.direction:4s} "
                f"{t.entry_time}→{t.exit_time}  "
                f"₹{t.entry_price:.2f}→₹{t.exit_price:.2f}  "
                f"qty={t.quantity}  P&L=₹{t.pnl_inr:+,.0f}  [{t.exit_reason}]"
            )
        lines.append(sep)

        for line in lines:
            logger.info(f"[PERF] {line}")

    # ------------------------------------------------------------------
    # Append today's trades to performance_log.csv in the repo root
    # ------------------------------------------------------------------
    def save_to_csv(self) -> None:
        if not self.trades:
            logger.info("[PERF] No trades to save.")
            return

        file_exists = LOG_FILE.exists()
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
            for t in self.trades:
                writer.writerow({
                    "date":        t.date,
                    "symbol":      t.symbol,
                    "direction":   t.direction,
                    "entry_time":  t.entry_time,
                    "exit_time":   t.exit_time,
                    "entry_price": t.entry_price,
                    "exit_price":  t.exit_price,
                    "quantity":    t.quantity,
                    "pnl_inr":     t.pnl_inr,
                    "exit_reason": t.exit_reason,
                })

        logger.info(f"[PERF] {len(self.trades)} trade(s) saved to {LOG_FILE}")
