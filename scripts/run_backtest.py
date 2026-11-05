#!/usr/bin/env python3
"""回测入口：取数 / 读本地 CSV → 跑策略 → 中文报告 + 权益曲线。

用法:
    python run_backtest.py --code 600519 --start 2024-01-01 --end 2025-12-31 \
        --strategy ma_cross --params fast=5,slow=20
    python run_backtest.py --data data/600519.csv --strategy bollinger
    python run_backtest.py --code 600519 --all --start 2024-01-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as eng  # noqa: E402
import metrics as mt  # noqa: E402
import strategies as st  # noqa: E402
from fetch_data import fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data"


def pad(text: str, width: int) -> str:
    """按显示宽度对齐（中文算 2 格）。"""
    import unicodedata
    text = str(text)
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    return text + " " * max(width - w, 0)


def load_data(args) -> tuple[pd.DataFrame, str]:
    if args.data:
        path = Path(args.data)
        df = pd.read_csv(path)
        if "date" not in df.columns:
            raise SystemExit(f"✗ {path} 缺少 date 列")
        code = args.code or path.stem
        return df, code
    if not args.code:
        raise SystemExit("需要 --code 或 --data")
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{args.code}.csv"
    if path.exists() and not args.refresh:
        df = pd.read_csv(path)
        if len(df) and (args.start is None or df["date"].min() <= args.start) and (args.end is None or df["date"].max() >= args.end):
            df = df[(df["date"] >= args.start) & (df["date"] <= args.end)] if args.start else df
            return df, args.code
    rows = fetch(args.code, args.start, args.end)
    if not rows:
        raise SystemExit(f"✗ {args.code} 取数失败")
    path.write_text(
        "date,open,high,low,close,volume\n" + "\n".join(",".join(r) for r in rows),
        encoding="utf-8",
    )
    df = pd.read_csv(path)
    return df[(df["date"] >= args.start) & (df["date"] <= args.end)], args.code


def parse_params(raw: str | None) -> dict:
    if not raw:
        return {}
    out = {}
    for chunk in raw.split(","):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        v = v.strip()
        try:
            out[k.strip()] = int(v) if v.lstrip("-").isdigit() else float(v)
        except ValueError:
            out[k.strip()] = v
    return out


def run_one(df: pd.DataFrame, code: str, name: str, params: dict, cash: float) -> dict:
    sig = st.build(name, df, params)
    res = eng.run_backtest(df, sig, code, cash=cash)
    m = mt.compute(res.equity, res.position, res.trades, res.fees_total)
    m["strategy"] = name
    m["params"] = params
    m["res"] = res
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description="A股日频回测")
    ap.add_argument("--code", default=None, help="6 位代码，自动取数")
    ap.add_argument("--data", default=None, help="本地 CSV（date,open,high,low,close,volume）")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--strategy", default="ma_cross")
    ap.add_argument("--params", default=None, help="如 fast=5,slow=20")
    ap.add_argument("--cash", type=float, default=100_000.0)
    ap.add_argument("--all", action="store_true", help="跑全部内置策略并排序")
    ap.add_argument("--refresh", action="store_true", help="强制重新取数")
    ap.add_argument("--out", default=None, help="权益曲线 CSV 输出路径；同目录自动生成同名 PNG")
    ap.add_argument("--no-chart", action="store_true", help="只输出文字/CSV，不生成 PNG")
    args = ap.parse_args()

    df, code = load_data(args)
    if len(df) < 60:
        raise SystemExit(f"✗ 数据只有 {len(df)} 根，太少了")

    if args.all:
        rows = []
        for name in st.STRATEGIES:
            m = run_one(df, code, name, {}, args.cash)
            rows.append(m)
            print("\n".join(mt.report_lines(m, f"{code} · {name}")))
        rows.sort(key=lambda m: -m["sharpe"])
        print("\n  策略排序（按夏普）")
        for m in rows:
            print("    " + pad(m["strategy"], 16) + pad(f"夏普 {m['sharpe']:.2f}", 14)
                  + pad(f"年化 {m['cagr']*100:.2f}%", 16)
                  + pad(f"回撤 {m['max_dd']*100:.2f}%", 18)
                  + f"交易 {m['trades']} 笔")
        best = rows[0]
        _dump(best, code, args)
        return

    params = parse_params(args.params)
    m = run_one(df, code, args.strategy, params, args.cash)
    print("\n".join(mt.report_lines(m, f"{code} · {args.strategy} {params or ''}".strip())))
    res = m["res"]
    print(f"  被执行规则挡掉：涨停买不到 {res.blocked_buy} 次，跌停卖不掉 {res.blocked_sell} 次，"
          f"停牌 {res.halted_days} 天，资金不足一手 {res.blocked_cash} 次")
    if res.trades:
        print("\n  最近 8 笔交易")
        print("    " + pad("买入日", 12) + pad("买入价", 10) + pad("卖出日", 12)
              + pad("卖出价", 10) + pad("天数", 6) + "盈亏")
        for t in res.trades[-8:]:
            print("    " + pad(t.entry_date, 12) + pad(f"{t.entry_price:.2f}", 10)
                  + pad(t.exit_date, 12) + pad(f"{t.exit_price:.2f}", 10)
                  + pad(t.bars, 6) + f"{t.pnl:>10,.0f}")
    _dump(m, code, args)


def _dump(m: dict, code: str, args) -> None:
    res = m["res"]
    out = Path(args.out) if args.out else ROOT / "out" / f"{code}_{m['strategy']}_equity.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "equity", "position"])
        for d, v, p in zip(res.equity.index, res.equity.values, res.position.values):
            w.writerow([d, f"{v:.2f}", int(p)])
    print(f"\n  权益曲线 → {out}")

    if not getattr(args, "no_chart", False):
        try:
            import chart
            png = chart.plot_equity(m, code, out.with_suffix(".png"))
            print(f"  回测图表 → {png}")
        except Exception as exc:  # keep the text report usable if plotting is unavailable
            print(f"  图表生成失败（文字/CSV 不受影响）：{exc}")


if __name__ == "__main__":
    main()
