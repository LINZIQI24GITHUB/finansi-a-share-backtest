#!/usr/bin/env python3
"""A 股回测：后复权口径 + 真实账本 + 252 指标。

    python scripts/run.py --code 300750 --start 2024-01-01 --end 2025-12-31 \
        --signal ma_cross --params fast=5,slow=20 --cash 100000
    python scripts/run.py demo            # 离线自检，用本地缓存

复权口径（见 DECISIONS.md D4）：
    收益用**后复权**（不受分红除权影响），但后复权价格远高于真实价（茅台 9390），
    直接算整手会失真。所以取窗口首日的真实收盘价做等比缩放——
    收益序列不变，价格尺度回到真实水平，整手与费用才可算。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
for candidate in (os.getenv("ASHARE_LIB"),
                  SKILL_DIR.parents[1] / "lib" if len(SKILL_DIR.parents) > 1 else None,
                  SKILL_DIR / "lib"):
    if candidate and Path(candidate).is_dir() and (Path(candidate) / "ashare_core").is_dir():
        sys.path.insert(0, str(candidate))
        break

from ashare_core import engine, metrics, rulespec, signals  # noqa: E402
from ashare_core.providers.eltdx_provider import EltdxProvider  # noqa: E402
from ashare_core.store import BarsCache  # noqa: E402


def _default_data_dir() -> Path:
    env = os.getenv("ASHARE_DATA")
    if env:
        return Path(env)
    pack_data = SKILL_DIR.parents[1] / "data" if len(SKILL_DIR.parents) > 1 else None
    if pack_data and (pack_data.exists() or (SKILL_DIR.parents[1] / "lib").exists()):
        return pack_data
    return Path.home() / ".ashare" / "data"


DATA = _default_data_dir()


def load_scaled(cache: BarsCache, code: str, start: str, end: str) -> tuple:
    """后复权取数 + 按窗口首日真实价缩放。返回 (df, scale, 原始后复权首日价)。"""
    import pandas as pd

    hfq = cache.get(code, start, end, "hfq")
    raw = cache.get(code, start, end, "none")
    if hfq.empty or raw.empty:
        raise SystemExit(f"✗ {code} 取数失败")
    first_date = str(hfq["date"].iloc[0])
    raw0 = raw[raw["date"] == first_date]["close"]
    if raw0.empty:
        raise SystemExit(f"✗ {code} 在 {first_date} 没有不复权价格，无法锚定")
    scale = float(raw0.iloc[0]) / float(hfq["close"].iloc[0])
    df = hfq.copy()
    for col in ("open", "high", "low", "close"):
        df[col] = (df[col] * scale).round(2)
    return df, scale, float(hfq["close"].iloc[0])


def parse_params(raw: str | None) -> dict:
    out: dict = {}
    for chunk in (raw or "").split(","):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        v = v.strip()
        try:
            out[k.strip()] = int(v) if v.lstrip("-").isdigit() else float(v)
        except ValueError:
            out[k.strip()] = v
    return out


def resolve_code(raw: str, provider) -> str:
    """支持 6 位代码、sh600519、以及中文名（宁德时代 / 贵州茅台）。"""
    s = str(raw).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 6:
        return digits
    try:
        lst = provider.stock_list()
    except Exception:  # noqa: BLE001
        raise SystemExit(f"✗ 无法解析「{raw}」：既不是 6 位代码，也拿不到股票清单")
    hit = lst[lst["name"] == s]
    if hit.empty:
        hit = lst[lst["name"].str.contains(s, na=False)]
    if hit.empty:
        raise SystemExit(f"✗ 找不到名称含「{s}」的股票，请改用 6 位代码")
    if len(hit) > 1:
        names = "、".join(f"{r.code} {r.name}" for r in hit.head(6).itertuples())
        raise SystemExit(f"✗ 「{s}」匹配到多只：{names}，请指定代码")
    return str(hit.iloc[0]["code"])


def display_label(signal: str, params: dict) -> str:
    """给人看的策略名，别把 {'fast': 5} 这种 dict 直接印在标题上。"""
    p = params or {}
    if signal == "ma_cross":
        return f"双均线 {p.get('fast', 5)}/{p.get('slow', 20)}"
    if signal == "rsi_reversion":
        return (f"RSI({p.get('n', 14)}) 反转 "
                f"{p.get('low', 30)}/{p.get('high', 70)}")
    bits = ", ".join(f"{k}={v}" for k, v in p.items())
    return f"{signal}({bits})" if bits else signal


def signal_desc(signal: str, params: dict) -> str:
    """一句话说清这条策略在干什么，印在图表标题下面。"""
    p = params or {}
    if signal == "ma_cross":
        return (f"{p.get('fast', 5)}/{p.get('slow', 20)} 双均线，"
                "快线上穿慢线买入、下穿卖出")
    if signal == "rsi_reversion":
        return (f"RSI({p.get('n', 14)}) 反转，低于 {p.get('low', 30)} 买入、"
                f"高于 {p.get('high', 70)} 卖出")
    bits = ", ".join(f"{k}={v}" for k, v in p.items())
    return f"{signal}({bits})" if bits else signal


def _names_path() -> Path:
    return DATA / "names.json"


def remember_name(code: str, name: str) -> None:
    if not name:
        return
    try:
        path = _names_path()
        names = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        names[str(code).zfill(6)] = name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - 名字缓存只是锦上添花
        pass


def lookup_name(code: str) -> str:
    """查证券简称：先看缓存，再查股票清单，最后用行情快照表兜底（ETF / LOF 不在股票清单里）。"""
    code = str(code).zfill(6)
    try:
        path = _names_path()
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8")).get(code, "")
            if cached:
                return str(cached)
    except Exception:  # noqa: BLE001
        pass
    try:
        with EltdxProvider() as p:
            try:
                lst = p.stock_list()
                hit = lst[lst["code"] == code]
                name = str(hit.iloc[0]["name"]) if len(hit) else ""
            except Exception:  # noqa: BLE001
                name = ""
            if not name:
                name = p.profile(code).get("name", "")
    except Exception:  # noqa: BLE001
        name = ""
    if name:
        remember_name(code, name)
    return name


def run_one(code: str, start: str, end: str, signal: str | None = None,
            params: dict | None = None, cash: float = 100_000.0,
            rule: dict | None = None,
            stop_loss: float | None = None,
            take_profit: float | None = None) -> tuple[dict, object, object]:
    with EltdxProvider() as p:
        cache = BarsCache(p, DATA)
        resolved = resolve_code(code, p)
        df, scale, hfq0 = load_scaled(cache, resolved, start, end)

    if rule:
        sig = rulespec.build_position(df, rule)
        label = rulespec.describe(rule)
        desc = label
        sl = rule.get("stop_loss", stop_loss)
        tp = rule.get("take_profit", take_profit)
    else:
        sig = signals.build(signal or "ma_cross", df, **(params or {}))
        label = display_label(signal or "ma_cross", params or {})
        desc = signal_desc(signal or "ma_cross", params or {})
        bits = []
        if stop_loss:
            bits.append(f"止损{stop_loss:g}%")
        if take_profit:
            bits.append(f"止盈{take_profit:g}%")
        if bits:
            label += " + " + "/".join(bits)
            desc += "；" + "，".join(bits)
        sl, tp = stop_loss, take_profit

    res = engine.run(df, sig, resolved, cash=cash, stop_loss=sl, take_profit=tp)
    m = metrics.compute(res.equity, res.position, res.account.trades_df(), res.account.fees_paid)
    m["_meta"] = {"bars": len(df), "scale": scale, "hfq_first": hfq0,
                  "code": resolved, "label": label, "desc": desc, "rule": rule,
                  "start": df["date"].iloc[0], "end": df["date"].iloc[-1]}
    return m, res, df


def print_result(m: dict, res) -> None:
    meta = m["_meta"]
    if meta.get("default_signal"):
        print("⚠ 未指定策略，已使用默认：双均线 ma_cross(fast=5, slow=20)")
        print("  这只是默认参数的结果，不等于这只股票本身的结论；"
              "换策略请说「用 RSI 反转」，或给一条规则 JSON\n")
    print(metrics.format_report(m, f"{meta['code']} · {meta['label']}"))
    print(f"  区间 {meta['start']} ~ {meta['end']}（{meta['bars']} 根）　"
          f"口径 后复权 × {meta['scale']:.4f}（锚定首日真实价）")
    print(f"  被规则挡掉：涨停 {res.blocked['limit_up']} 次，跌停 {res.blocked['limit_down']} 次，"
          f"资金不足 {res.blocked['cash']} 次，T+1 {res.blocked['t1']} 次")
    if res.blocked.get("stop") or res.blocked.get("take_profit"):
        print(f"  止损触发 {res.blocked.get('stop', 0)} 次，止盈触发 {res.blocked.get('take_profit', 0)} 次")


def render_chart(args, m: dict, res, df, cash: float):
    """画权益曲线图（含绩效信息表与风险提示）。失败不影响回测结果。"""
    from ashare_core import chart

    target = args.plot
    if target == "auto":
        tag = args.signal or ("rule" if args.rule else "ma_cross")
        target = f"backtest_{m['_meta']['code']}_{tag}.png"
    meta = m["_meta"]
    bench = (df["close"].astype(float) / float(df["close"].iloc[0])) * cash
    bench.index = df["date"].tolist()
    name = meta.get("name") or ""
    try:
        return chart.render(
            target, res.equity, m,
            title=f"{name} {meta['code']}".strip(),
            desc=meta.get("desc") or meta.get("label", ""),
            period=f"{meta['start']} ~ {meta['end']} · 计算方式：后复权",
            benchmark=bench)
    except Exception as exc:  # noqa: BLE001 - 图挂了也不能让回测挂
        print(f"  ⚠ 画图失败：{type(exc).__name__}: {exc}")
        return None


def cmd_run(args) -> int:
    params = parse_params(args.params)
    rule = None
    if args.rule:
        try:
            rule = rulespec.load(args.rule)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"✗ 规则无法解析：{exc}")
        if args.stop_loss is not None:
            rule["stop_loss"] = args.stop_loss
        if args.take_profit is not None:
            rule["take_profit"] = args.take_profit
    explicit = args.signal is not None or rule is not None
    signal = args.signal or "ma_cross"
    m, res, df = run_one(args.code, args.start, args.end, signal, params, args.cash, rule,
                        args.stop_loss, args.take_profit)
    m["_meta"]["default_signal"] = not explicit
    if args.no_plot:
        args.plot = None
    if args.plot:
        m["_meta"]["name"] = args.name or lookup_name(m["_meta"]["code"])
    chart_path = render_chart(args, m, res, df, args.cash) if args.plot else None
    if args.plot and chart_path is None:
        print("⚠ 未生成图表：图表是交付物的一部分，不是可选项。")
        print("  先 pip install matplotlib 再重跑；确实只要文字请显式加 --no-plot。")
    if args.json:
        out = {k: v for k, v in m.items() if not k.startswith("_")}
        out["meta"] = m["_meta"]
        out["blocked"] = res.blocked
        out["chart"] = str(chart_path) if chart_path else None
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0 if (chart_path or not args.plot) else 2
    print_result(m, res)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "equity", "position"])
            for d, v, pos in zip(res.equity.index, res.equity.values, res.position.values):
                w.writerow([d, f"{v:.2f}", int(pos)])
        print(f"  权益曲线 → {path}")
    if chart_path:
        print(f"  权益曲线图 → {chart_path}")
    trades = res.account.trades_df()
    if not trades.empty:
        print("\n最近 5 笔成交")
        print(trades.tail(5).to_string(index=False))
    return 0 if (chart_path or not args.plot) else 2


def cmd_demo(args) -> int:
    """离线自检：固定参数跑一遍，关键数字与基准比对。"""
    code, start, end = "300750", "2024-01-01", "2025-12-31"
    params = {"fast": 5, "slow": 20}
    m, res, _ = run_one(code, start, end, "ma_cross", params, 100_000.0)

    checks = [
        ("总收益", m["total_return"], 0.7820, 0.01),
        ("夏普", m["sharpe"], 1.07, 0.05),
        ("最大回撤", m["max_dd"], -0.2082, 0.01),
        ("交易笔数", m["trades"], 13, 0),
        ("涨停挡单", res.blocked["limit_up"], 0, 0),
    ]
    print(f"离线自检：{code} {start} ~ {end} · ma_cross(5,20)")
    passed = 0
    for name, got, want, tol in checks:
        ok = abs(got - want) <= tol if tol else got == want
        passed += ok
        shown = f"{got:.4f}" if isinstance(got, float) else str(got)
        print(f"  {'✓' if ok else '✗'} {name}：{shown}（基准 {want}{'±' + str(tol) if tol else ''}）")
    total = len(checks)
    print(f"\n{'✓ 通过' if passed == total else '✗ 未通过'}（{passed}/{total}）")
    return 0 if passed == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="A 股回测（后复权 + 真实账本）")
    ap.add_argument("--data-dir", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="跑一次回测")
    r.add_argument("--code", required=True)
    r.add_argument("--start", required=True)
    r.add_argument("--end", required=True)
    r.add_argument("--signal", default=None, choices=list(signals.SIGNALS),
                   help="不指定则用默认双均线，并在报告顶部标注")
    r.add_argument("--params", default=None, help="如 fast=5,slow=20")
    r.add_argument("--rule", default=None,
                   help='规则 JSON（文件路径或内联），如 \'{"entry":[{"ind":"ma_cross","fast":5,"slow":20}],"stop_loss":8}\'')
    r.add_argument("--stop-loss", type=float, default=None, help="止损百分比，配合 --rule 或 --signal")
    r.add_argument("--take-profit", type=float, default=None, help="止盈百分比")
    r.add_argument("--cash", type=float, default=100_000.0)
    r.add_argument("--out", default=None, help="权益曲线 CSV 输出路径")
    r.add_argument("--plot", nargs="?", const="auto", default="auto",
                   help="权益曲线图 PNG（含绩效信息表与风险提示）——默认就出；"
                        "不带路径时自动命名，也可指定路径")
    r.add_argument("--no-plot", action="store_true",
                   help="只在调试或无 matplotlib 时用：跳过出图。回测的交付物默认包含图")
    r.add_argument("--name", default=None,
                   help="图表标题里的名称，如「沪深300ETF」；股票会自动查清单，ETF 需手填")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("demo", help="离线自检（用本地缓存）")
    d.set_defaults(func=cmd_demo)

    args = ap.parse_args()
    if args.data_dir:
        global DATA
        DATA = Path(args.data_dir)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
