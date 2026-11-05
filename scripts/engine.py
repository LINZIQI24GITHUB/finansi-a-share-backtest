#!/usr/bin/env python3
"""A股日频回测引擎：T+1、涨跌停不可成交、整手、真实费率。

信号在第 i 根 K 线**收盘后**产生，默认在第 i+1 根 K 线**开盘**成交——
这是回测里最容易做假的地方，本引擎不给"当天收盘价成交"这种不可实现的选项。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ── A股规则 ────────────────────────────────────────────────────────────
COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_DUTY = 0.0005      # 卖出单边
TRANSFER_FEE = 0.00001   # 双向


def board(code: str) -> str:
    c = str(code).zfill(6)
    if c.startswith("688"):
        return "star"
    if c.startswith(("300", "301")):
        return "chinext"
    if c.startswith(("4", "8", "92")):
        return "bse"
    return "main"


def limit_pct(code: str, is_st: bool = False) -> float:
    b = board(code)
    if b == "main":
        return 0.05 if is_st else 0.10
    return {"star": 0.20, "chinext": 0.20, "bse": 0.30}[b]


def lot_size(code: str) -> int:
    return 200 if board(code) == "star" else 100


def fees_for(amount: float, side: str) -> float:
    commission = max(amount * COMMISSION_RATE, COMMISSION_MIN)
    stamp = amount * STAMP_DUTY if side == "sell" else 0.0
    transfer = amount * TRANSFER_FEE
    return commission + stamp + transfer


@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    qty: int
    pnl: float
    fees: float
    bars: int
    return_pct: float
    forced: bool = False


@dataclass
class Result:
    equity: pd.Series
    position: pd.Series
    trades: list[Trade] = field(default_factory=list)
    fees_total: float = 0.0
    blocked_buy: int = 0
    blocked_sell: int = 0
    halted_days: int = 0
    blocked_cash: int = 0


def prepare(df: pd.DataFrame, code: str, is_st: bool = False) -> pd.DataFrame:
    df = df.copy()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    df["prev_close"] = df["close"].shift(1)
    pct = limit_pct(code, is_st)
    # 交易所按昨收四舍五入到分
    df["limit_up"] = (df["prev_close"] * (1 + pct)).round(2)
    df["limit_down"] = (df["prev_close"] * (1 - pct)).round(2)
    return df


def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    code: str,
    cash: float = 100_000.0,
    slippage: float = 0.0,
    liquidate_at_end: bool = True,
    is_st: bool = False,
) -> Result:
    """signal: 每日收盘后的目标仓位（1=持有，0=空仓），与 df 同索引。"""
    df = prepare(df, code, is_st)
    sig = pd.Series(signal).reset_index(drop=True).fillna(0).astype(int).clip(0, 1)
    lot = lot_size(code)

    n = len(df)
    equity = np.zeros(n)
    position = np.zeros(n, dtype=int)
    trades: list[Trade] = []

    cash_left = float(cash)
    qty = 0
    entry = None
    fees_total = 0.0
    blocked_buy = blocked_sell = halted = blocked_cash = 0

    for i in range(n):
        o = float(df.at[i, "open"])
        c = float(df.at[i, "close"])
        vol = float(df.at[i, "volume"]) if not pd.isna(df.at[i, "volume"]) else 0.0
        up = df.at[i, "limit_up"]
        down = df.at[i, "limit_down"]
        halted_today = vol <= 0

        # ── 执行昨日收盘产生的信号 ──────────────────────────────
        if i > 0:
            target = int(sig.iloc[i - 1])
            if target == 1 and qty == 0:
                px = o * (1 + slippage)
                if halted_today:
                    halted += 1
                elif pd.notna(up) and px >= float(up) - 1e-9:
                    blocked_buy += 1
                else:
                    budget = cash_left / (1 + COMMISSION_RATE + TRANSFER_FEE)
                    shares = int(budget // (px * lot)) * lot
                    if shares > 0:
                        amount = shares * px
                        fee = fees_for(amount, "buy")
                        if amount + fee <= cash_left:
                            cash_left -= amount + fee
                            fees_total += fee
                            qty = shares
                            entry = {
                                "date": str(df.at[i, "date"]), "price": px,
                                "i": i, "cost": amount + fee,
                            }
                    else:
                        # 一手都买不起（高价股 + 小资金），计入诊断
                        blocked_cash += 1
            elif target == 0 and qty > 0:
                px = o * (1 - slippage)
                if halted_today:
                    halted += 1
                elif pd.notna(down) and px <= float(down) + 1e-9:
                    blocked_sell += 1
                else:
                    amount = qty * px
                    fee = fees_for(amount, "sell")
                    cash_left += amount - fee
                    fees_total += fee
                    pnl = (amount - fee) - entry["cost"]
                    trades.append(Trade(
                        entry_date=entry["date"], entry_price=entry["price"],
                        exit_date=str(df.at[i, "date"]), exit_price=px, qty=qty,
                        pnl=pnl, fees=fee, bars=i - entry["i"],
                        return_pct=pnl / entry["cost"],
                    ))
                    qty = 0
                    entry = None

        equity[i] = cash_left + qty * c
        position[i] = 1 if qty > 0 else 0

    # 最后一根强制平仓，保证统计完整
    if qty > 0 and liquidate_at_end:
        last = n - 1
        px = float(df.at[last, "close"])
        amount = qty * px
        fee = fees_for(amount, "sell")
        cash_left += amount - fee
        fees_total += fee
        pnl = (amount - fee) - entry["cost"]
        trades.append(Trade(
            entry_date=entry["date"], entry_price=entry["price"],
            exit_date=str(df.at[last, "date"]), exit_price=px, qty=qty,
            pnl=pnl, fees=fee, bars=last - entry["i"],
            return_pct=pnl / entry["cost"], forced=True,
        ))
        equity[last] = cash_left
        position[last] = 0
        qty = 0

    dates = df["date"].astype(str).tolist()
    return Result(
        equity=pd.Series(equity, index=dates, name="equity"),
        position=pd.Series(position, index=dates, name="position"),
        trades=trades, fees_total=fees_total,
        blocked_buy=blocked_buy, blocked_sell=blocked_sell, halted_days=halted,
        blocked_cash=blocked_cash,
    )
