#!/usr/bin/env python3
"""绩效指标：全部按 A 股口径 —— 一年 252 个交易日。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def drawdown(equity: pd.Series) -> tuple[pd.Series, float, int]:
    peak = equity.cummax()
    dd = equity / peak - 1
    return dd, float(dd.min()), int((dd < 0).sum())


def compute(
    equity: pd.Series,
    position: pd.Series,
    trades: list,
    fees_total: float,
    rf: float = 0.0,
) -> dict:
    eq = equity.astype(float)
    ret = eq.pct_change().dropna()
    n = len(eq)
    years = n / TRADING_DAYS if n else 0

    total_return = float(eq.iloc[-1] / eq.iloc[0] - 1) if n else 0.0
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1) if years > 0.2 and eq.iloc[0] > 0 else total_return
    vol = float(ret.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(ret) > 1 else 0.0
    daily_rf = rf / TRADING_DAYS
    excess = ret - daily_rf
    sharpe = float(excess.mean() / ret.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(ret) > 1 and ret.std(ddof=1) > 0 else 0.0
    downside = ret[ret < 0]
    sortino = float(excess.mean() / downside.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(downside) > 1 and downside.std(ddof=1) > 0 else 0.0

    dd, max_dd, dd_days = drawdown(eq)
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    return {
        "bars": n,
        "years": years,
        "total_return": total_return,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": max_dd,
        "dd_days": dd_days,
        "calmar": calmar,
        "trades": len(pnls),
        "win_rate": len(wins) / len(pnls) if pnls else 0.0,
        "avg_win": float(np.mean(wins)) if wins else 0.0,
        "avg_loss": float(np.mean(losses)) if losses else 0.0,
        "payoff": (np.mean(wins) / abs(np.mean(losses))) if wins and losses else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss else (float("inf") if gross_win else 0.0),
        "avg_bars": float(np.mean([t.bars for t in trades])) if trades else 0.0,
        "exposure": float(position.mean()) if len(position) else 0.0,
        "fees": fees_total,
        "fee_ratio": fees_total / float(eq.iloc[0]) if n else 0.0,
        "final_equity": float(eq.iloc[-1]),
    }


def report_lines(m: dict, title: str) -> list[str]:
    bar = "─" * 60
    pf = "∞" if m["profit_factor"] == float("inf") else f"{m['profit_factor']:.2f}"
    return [
        "",
        bar,
        f"  {title}",
        bar,
        f"  期末权益 {m['final_equity']:>12,.0f} 元   总收益 {m['total_return']*100:>7.2f}%",
        f"  年化收益 {m['cagr']*100:>10.2f}%       年化波动 {m['volatility']*100:>6.2f}%",
        f"  夏普     {m['sharpe']:>10.2f}        索提诺   {m['sortino']:>6.2f}",
        f"  最大回撤 {m['max_dd']*100:>10.2f}%       卡玛     {m['calmar']:>6.2f}",
        f"  交易 {m['trades']:>4} 笔  胜率 {m['win_rate']*100:>5.1f}%  盈亏比 {m['payoff']:>4.2f}  盈利因子 {pf}",
        f"  平均持有 {m['avg_bars']:>5.1f} 交易日   持仓占比 {m['exposure']*100:>5.1f}%",
        f"  总费用   {m['fees']:>10,.0f} 元（占初始资金 {m['fee_ratio']*100:.2f}%）",
        bar,
    ]
