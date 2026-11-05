#!/usr/bin/env python3
"""Render the equity/drawdown chart for a backtest result.

The chart is intentionally optional: a missing matplotlib install must not stop
the text report or the CSV from being produced.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

INK = "#121313"
MUTED = "#666962"
CREAM = "#f4f1e9"
PAPER = "#fbfaf6"
LINE = "#d2cfc6"
GREEN = "#1f4d3a"
LIME = "#e8f36a"
RUST = "#a65c26"


def _pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def plot_equity(m: dict, code: str, out_png: Path) -> Path:
    """Write a two-panel equity + drawdown chart with a metrics table."""
    res = m["res"]
    eq = pd.Series(res.equity).astype(float)
    dates = pd.to_datetime(pd.Series(eq.index), errors="coerce")
    x = dates if not dates.isna().any() else pd.Series(range(len(eq)))
    peak = eq.cummax()
    dd = eq / peak - 1.0
    final = float(eq.iloc[-1])
    start = float(eq.iloc[0])

    fig = plt.figure(figsize=(15, 9), facecolor=CREAM)
    gs = fig.add_gridspec(3, 1, height_ratios=[3.1, 1.05, 1.0], hspace=0.28)

    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(PAPER)
    ax.plot(x, eq, color=INK, linewidth=1.8, label="Equity")
    ax.fill_between(x, start, eq, color=LIME, alpha=0.35, linewidth=0)
    ax.axhline(start, color=MUTED, linewidth=0.8, linestyle=(0, (4, 4)), alpha=0.7)
    ax.set_title(f"{code}  ·  {m['strategy']}", loc="left", fontsize=22, color=INK, pad=18, fontweight="bold")
    ax.text(0.0, 1.01, "A-share daily backtest  ·  next-open execution  ·  T+1 / price limits / board lots / fees",
            transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")
    ax.set_ylabel("Equity (CNY)", color=MUTED, fontsize=10)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(axis="y", color="#e5e1d8", linewidth=0.8)
    ax.tick_params(colors=MUTED, labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=MUTED)

    ax2 = fig.add_subplot(gs[1], sharex=ax)
    ax2.set_facecolor(PAPER)
    ax2.fill_between(x, dd * 100, 0, color=RUST, alpha=0.22, linewidth=0)
    ax2.plot(x, dd * 100, color=RUST, linewidth=1.0)
    ax2.set_ylabel("Drawdown %", color=MUTED, fontsize=9)
    ax2.grid(axis="y", color="#e5e1d8", linewidth=0.7)
    ax2.tick_params(colors=MUTED, labelsize=8)
    for side in ("top", "right"):
        ax2.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax2.spines[side].set_color(LINE)

    ax3 = fig.add_subplot(gs[2])
    ax3.axis("off")
    ax3.set_facecolor(CREAM)
    pf = "∞" if m["profit_factor"] == float("inf") else f"{m['profit_factor']:.2f}"
    metrics = [
        ("Total return", _pct(m["total_return"]), "CAGR", _pct(m["cagr"])),
        ("Sharpe", f"{m['sharpe']:.2f}", "Max drawdown", _pct(m["max_dd"])),
        ("Win rate", _pct(m["win_rate"], 1), "Payoff", f"{m['payoff']:.2f}"),
        ("Trades", f"{m['trades']}", "Fee ratio", _pct(m["fee_ratio"])),
    ]
    for i, (k1, v1, k2, v2) in enumerate(metrics):
        y = 0.82 - i * 0.21
        ax3.text(0.00, y, k1, fontsize=8, color=MUTED, transform=ax3.transAxes)
        ax3.text(0.115, y, v1, fontsize=11, color=INK, fontweight="bold", transform=ax3.transAxes)
        ax3.text(0.24, y, k2, fontsize=8, color=MUTED, transform=ax3.transAxes)
        ax3.text(0.37, y, v2, fontsize=11, color=INK, fontweight="bold", transform=ax3.transAxes)
    ax3.text(
        0.50, 0.82,
        f"Final equity  {final:,.0f} CNY\n"
        f"Period  {m['bars']} trading days  ({m['years']:.2f} years)\n"
        f"Exposure  {_pct(m['exposure'], 1)}   ·   Fees  {m['fees']:,.0f} CNY\n"
        f"Blocked  buy {res.blocked_buy} / sell {res.blocked_sell} / halted {res.halted_days}d\n"
        f"Trades  {m['trades']}   ·   Profit factor  {pf}",
        fontsize=8.5, color=MUTED, va="top", linespacing=1.65, transform=ax3.transAxes,
    )
    fig.text(
        0.012, 0.018,
        "Backtested results are hypothetical, do not include taxes/slippage beyond the model, "
        "and are not investment advice. Past performance does not guarantee future results.",
        fontsize=7.5, color=MUTED,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=170, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_png
