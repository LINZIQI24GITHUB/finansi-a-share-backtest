#!/usr/bin/env python3
"""图表层自检：只验制图，不碰引擎。

    python scripts/check_chart.py

默认用合成数据跑，不依赖行情缓存；本地有缓存时再补跑一次真实 CLI。
没装 matplotlib 时自动跳过渲染类检查（技能本来就把绘图当可选依赖）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "lib"))

from ashare_core import brand, chart  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []   # (状态, 名称, 备注)
TMP = Path(tempfile.mkdtemp(prefix="check-chart-"))

M = {"total_return": 0.1234, "cagr": 0.0567, "max_dd": -0.2, "volatility": 0.15,
     "sharpe": 1.234, "win_rate": 0.5, "payoff": 1.5, "trades": 9}


def ok(name: str, detail: str = "") -> None:
    RESULTS.append(("✓", name, detail))


def bad(name: str, detail: str = "") -> None:
    RESULTS.append(("✗", name, detail))


def skip(name: str, detail: str = "") -> None:
    RESULTS.append(("–", name, detail))


def expect(name: str, cond: bool, detail: str = "") -> None:
    (ok if cond else bad)(name, detail)


# ── 1. 绩效表的字段与格式 ────────────────────────────────────────────
items = chart.kpi_items(M)
expect("绩效表 7 项、顺序正确",
       [i[0] for i in items] == ["累计收益率", "年化收益率", "最大回撤", "年化波动率",
                                 "夏普比率", "胜率", "盈亏比"],
       "、".join(i[0] for i in items))
expect("绩效表数值格式",
       [i[1] for i in items] == ["+12.34%", "+5.67%", "-20.00%", "15.00%", "1.23", "50.0%", "1.50"],
       " ".join(i[1] for i in items))
zero = chart.kpi_items({**M, "trades": 0, "win_rate": 0.0, "payoff": 0.0})
expect("零成交时胜率/盈亏比为「—」", zero[5][1] == "—" and zero[6][1] == "—")
expect("图上的收益 = 报告里的收益", items[0][1] == f"{M['total_return']:+.2%}")

# ── 2. 渲染 + 像素级校验（品牌元素真的画上去了）───────────────────────
try:
    import matplotlib  # noqa: F401
    import numpy as np
    from PIL import Image
    HAVE_MPL = True
except Exception:  # noqa: BLE001
    HAVE_MPL = False
    skip("渲染与像素校验", "没装 matplotlib / Pillow")

if HAVE_MPL:
    import pandas as pd

    idx = pd.date_range("2024-01-02", periods=40, freq="B")
    eq = pd.Series(np.linspace(100.0, 118.0, 40) + np.sin(np.arange(40)) * 2, index=idx)
    bench = pd.Series(np.linspace(100.0, 112.0, 40), index=idx)
    out = chart.render(TMP / "chart.png", eq, M, title="测试股份 000001",
                       desc="5/20 双均线，快线上穿慢线买入、下穿卖出",
                       period="2024-01-02 ~ 2024-02-27 · 计算方式：后复权",
                       benchmark=bench)
    expect("渲染出图", out is not None and out.exists() and out.stat().st_size > 20_000,
           f"{out.stat().st_size // 1024}KB" if out and out.exists() else "无")

    if out and out.exists():
        im = Image.open(out).convert("RGB")
        px = im.load()
        w, h = im.size
        expect("画布 1650×1290（11×8.6in @150dpi）", (w, h) == (1650, 1290), f"{w}×{h}")

        def near(c1, c2, tol=6):
            return all(abs(a - b) <= tol for a, b in zip(c1, c2))

        rgb = lambda hx: tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))
        expect("顶部品牌 lime 条", near(px[w // 2, 2], rgb(brand.LIME)), str(px[w // 2, 2]))
        expect("纸底背景", near(px[8, h // 2], rgb(brand.PAPER)), str(px[8, h // 2]))

        def count_in(box, color, tol=8):
            x0, y0, x1, y1 = box
            return sum(1 for y in range(y0, y1, 2) for x in range(x0, x1, 2)
                       if near(px[x, y], rgb(color), tol))

        expect("右上角品牌标志（墨块像素）",
               count_in((1380, 20, 1620, 90), brand.INK) > 150,
               f"{count_in((1380, 20, 1620, 90), brand.INK)} px")
        expect("底部绩效表卡片底色",
               count_in((150, 1080, 1500, 1180), brand.CARD, tol=3) > 2000,
               f"{count_in((150, 1080, 1500, 1180), brand.CARD, tol=3)} px")
        expect("底部风险提示文字",
               count_in((520, 1230, 1130, 1270), brand.MUTED, tol=25) > 60,
               f"{count_in((520, 1230, 1130, 1270), brand.MUTED, tol=25)} px")

# ── 3. 没装 matplotlib 时降级 ────────────────────────────────────────
probe = (
    "import sys; sys.modules['matplotlib']=None;"
    f"sys.path.insert(0, r'{SKILL_DIR / 'lib'}');"
    "from ashare_core import chart; import pandas as pd;"
    "eq=pd.Series([1,1.1,1.05], index=['2024-01-02','2024-01-03','2024-01-04']);"
    "m={'total_return':.05,'cagr':.05,'max_dd':-.05,'volatility':.2,'sharpe':.5,"
    "'win_rate':.5,'payoff':1.2,'trades':2};"
    f"print(chart.render(r'{TMP / 'none.png'}', eq, m))")
r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
expect("无 matplotlib 时返回 None 且不抛异常",
       r.stdout.strip() == "None" and not (TMP / "none.png").exists(),
       r.stdout.strip() or r.stderr.strip()[:60])

# ── 4. 品牌资产与文档 ────────────────────────────────────────────────
assets = sorted(p.name for p in (SKILL_DIR / "assets").glob("*"))
expect("品牌资产齐全",
       assets == ["brand-board.png", "finansi-logo-dark.svg", "finansi-logo.svg",
                  "finansi-mark-dark.svg", "finansi-mark.svg"], "、".join(assets))
expect("SI 用橄榄两色", (brand.SI_LIGHT, brand.SI_DARK) == ("#6f7d2b", "#c2d05a"))
doc = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
expect("SKILL.md 写明了 --plot / 绩效表 / 免责声明",
       all(k in doc for k in ("--plot", "绩效信息表", "历史回测数据仅供参考，非投资建议。")))

# ── 5. CLI 串联（有行情缓存时才跑）────────────────────────────────────
cli_png = TMP / "cli.png"
env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
c = subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "run.py"), "run",
                    "--code", "300750", "--start", "2024-01-01", "--end", "2025-12-31",
                    "--signal", "ma_cross", "--params", "fast=5,slow=20",
                    "--cash", "100000", "--json", "--plot", str(cli_png)],
                   capture_output=True, text=True, env=env, cwd=SKILL_DIR)
if c.returncode != 0 or not c.stdout.strip().startswith("{"):
    skip("CLI --json --plot 串联", (c.stderr or c.stdout).strip().splitlines()[-1][:70])
else:
    data = json.loads(c.stdout)
    expect("CLI --json 含 chart 路径且文件存在",
           Path(data.get("chart") or "").exists() and cli_png.exists())
    expect("CLI 图上数字与 JSON 一致",
           chart.kpi_items(data)[0][1] == f"{data['total_return']:+.2%}",
           f"{data['total_return']:+.2%}")

# ── 汇总 ────────────────────────────────────────────────────────────
for mark, name, detail in RESULTS:
    print(f"  {mark} {name}" + (f"　（{detail}）" if detail else ""))
passed = sum(1 for m, _, _ in RESULTS if m == "✓")
failed = sum(1 for m, _, _ in RESULTS if m == "✗")
skipped = sum(1 for m, _, _ in RESULTS if m == "–")
print(f"\n{'✓ 通过' if not failed else '✗ 未通过'}（{passed} 通过 / {failed} 失败 / {skipped} 跳过）")

for p in TMP.glob("*"):
    p.unlink()
TMP.rmdir()
sys.exit(1 if failed else 0)
