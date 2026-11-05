#!/usr/bin/env python3
"""A股日线数据获取：腾讯行情接口 → 本地 CSV 缓存（前复权）。

用法:
    python fetch_data.py --code 600519 --start 2024-01-01 --end 2025-12-31
    python fetch_data.py --codes 600519,300750,000001 --start 2023-01-01 --out data/

不依赖 akshare / tushare，也不需要 API key。接口对前复权数据一次性返回，
超过约 640 个交易日需要分段请求，本脚本自动分段并拼接。
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

BASE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def secid(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def _chunks(start: str, end: str, years: int = 2):
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    while d0 <= d1:
        chunk_end = min(d1, date(d0.year + years, d0.month, min(d0.day, 28)) - timedelta(days=1))
        yield d0.isoformat(), chunk_end.isoformat()
        d0 = chunk_end + timedelta(days=1)


def fetch(code: str, start: str, end: str, retries: int = 2) -> list[list[str]]:
    sid = secid(code)
    rows: dict[str, list[str]] = {}
    for a, b in _chunks(start, end):
        params = {"param": f"{sid},day,{a},{b},640,qfq"}
        for attempt in range(retries + 1):
            try:
                r = requests.get(BASE, params=params, headers=UA, timeout=20)
                payload = r.json()
                block = (payload.get("data") or {}).get(sid) or {}
                klines = block.get("qfqday") or block.get("day") or []
                for k in klines:
                    rows[k[0]] = [k[0], k[1], k[3], k[4], k[2], k[5]]
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == retries:
                    print(f"  ! {sid} {a}~{b} 拉取失败：{type(exc).__name__}", file=sys.stderr)
                time.sleep(1.2 * (attempt + 1))
        time.sleep(0.35)
    return [rows[d] for d in sorted(rows)]


def save(rows: list[list[str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="A股日线（前复权）→ CSV")
    ap.add_argument("--code", default=None, help="单个 6 位代码")
    ap.add_argument("--codes", default=None, help="逗号分隔的多个代码")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="data", help="输出目录（单只时也可给 .csv 路径）")
    args = ap.parse_args()

    codes = [c.strip() for c in (args.codes.split(",") if args.codes else [args.code]) if c and c.strip()]
    if not codes or codes == [None]:
        raise SystemExit("请给 --code 或 --codes")

    out = Path(args.out)
    for code in codes:
        rows = fetch(code, args.start, args.end)
        if not rows:
            print(f"✗ {code}: 没拿到数据（代码是否正确？）")
            continue
        path = out if (len(codes) == 1 and out.suffix.lower() == ".csv") else out / f"{code}.csv"
        save(rows, path)
        print(f"✓ {code}: {len(rows)} 根K线  {rows[0][0]} → {rows[-1][0]}  → {path}")


if __name__ == "__main__":
    main()
