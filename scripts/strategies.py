#!/usr/bin/env python3
"""内置策略：全部只依赖 OHLCV，返回「每日收盘后应持有的目标仓位」(0/1)。

信号必须只用当日及之前的数据，否则就是未来函数——引擎会在下一根开盘成交，
所以这里用 rolling/ewm 时务必不要用 shift(-n)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _state(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    """进场信号触发后持仓，直到离场信号触发（简单状态机）。"""
    out = np.zeros(len(entry), dtype=int)
    holding = False
    for i in range(len(entry)):
        if not holding and bool(entry.iloc[i]):
            holding = True
        elif holding and bool(exit_.iloc[i]):
            holding = False
        out[i] = 1 if holding else 0
    return pd.Series(out, index=entry.index)


def ma_cross(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.Series:
    """双均线：快线上穿慢线持有，下穿离场。"""
    ma_f = df["close"].rolling(int(fast)).mean()
    ma_s = df["close"].rolling(int(slow)).mean()
    sig = (ma_f > ma_s).astype(int)
    sig[ma_s.isna()] = 0
    return sig


def rsi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def rsi_reversion(df: pd.DataFrame, n: int = 14, low: float = 30, high: float = 70) -> pd.Series:
    """RSI 超卖买入、超买离场。"""
    r = rsi(df, n)
    return _state(r < low, r > high)


def bollinger(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.Series:
    """跌破下轨买入，回到中轨离场。"""
    mid = df["close"].rolling(int(n)).mean()
    sd = df["close"].rolling(int(n)).std(ddof=0)
    lower = mid - k * sd
    entry = (df["close"] < lower) & lower.notna()
    exit_ = (df["close"] > mid) & mid.notna()
    return _state(entry, exit_)


def breakout(df: pd.DataFrame, n: int = 20, exit_n: int = 10) -> pd.Series:
    """唐奇安通道突破：突破近 n 日高点买入，跌破近 exit_n 日低点离场。"""
    hi = df["high"].rolling(int(n)).max().shift(1)
    lo = df["low"].rolling(int(exit_n)).min().shift(1)
    entry = (df["close"] > hi) & hi.notna()
    exit_ = (df["close"] < lo) & lo.notna()
    return _state(entry, exit_)


STRATEGIES = {
    "ma_cross": (ma_cross, {"fast": 5, "slow": 20}),
    "rsi_reversion": (rsi_reversion, {"n": 14, "low": 30, "high": 70}),
    "bollinger": (bollinger, {"n": 20, "k": 2.0}),
    "breakout": (breakout, {"n": 20, "exit_n": 10}),
}


def build(name: str, df: pd.DataFrame, params: dict | None = None) -> pd.Series:
    if name not in STRATEGIES:
        raise SystemExit(f"未知策略 {name}，可选：{', '.join(STRATEGIES)}")
    fn, defaults = STRATEGIES[name]
    cfg = {**defaults, **(params or {})}
    return fn(df, **cfg)
