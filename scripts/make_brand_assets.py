#!/usr/bin/env python3
"""生成 FinanSI 品牌资产：SVG 标志（浅底 / 深底 / mark）+ 品牌板 PNG。

    python scripts/make_brand_assets.py            # 写到 ../assets/
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "lib"))

from ashare_core import brand  # noqa: E402

OUT = SKILL_DIR / "assets"


def board() -> Path:
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    rc = {"font.family": "sans-serif",
          "font.sans-serif": ["Microsoft YaHei", "Segoe UI", "DejaVu Sans"],
          "axes.unicode_minus": False}
    with plt.rc_context(rc):
        fig = plt.figure(figsize=(10.67, 6.67), dpi=150)
        fig.patch.set_facecolor(brand.PAPER)
        brand.draw_top_rule(fig, height=0.009)

        # 主 lockup
        brand.draw_lockup(fig, 0.06, 0.845, size_in=0.62, fontsize=26)
        fig.text(0.06, 0.755, "金融 Agent 的 Skills 精选", fontsize=15,
                 color=brand.INK_SOFT, ha="left", va="center")
        fig.text(0.06, 0.715, "finansi.work  ·  Curated Agent Skills for finance",
                 fontsize=9, color=brand.MUTED, ha="left", va="center",
                 fontfamily=list(brand.MONO_FONT))

        # 深色卡片
        card = FancyBboxPatch((0.60, 0.655), 0.34, 0.245,
                              boxstyle="round,pad=0,rounding_size=0.012",
                              transform=fig.transFigure, facecolor=brand.INK,
                              edgecolor="none", zorder=2)
        fig.add_artist(card)
        brand.draw_lockup(fig, 0.77, 0.778, size_in=0.44, fontsize=18,
                          dark=True, anchor="left")
        fig.text(0.77, 0.690, "深色底：用反白版，SI 改 #c2d05a", fontsize=8.5,
                 color=brand.LIME, ha="center", va="center")

        # 分隔线
        fig.add_artist(plt.Line2D([0.06, 0.94], [0.60, 0.60], color=brand.LINE,
                                  lw=0.9, transform=fig.transFigure))

        # 色板
        chips = [("纸底", brand.PAPER, "#f4f1e9"),
                 ("墨色", brand.INK, "#121313"),
                 ("Lime", brand.LIME, "#f4ff71"),
                 ("卡片", brand.CARD, "#fbfaf6"),
                 ("次级字", brand.MUTED, "#666962"),
                 ("SI 橄榄", brand.SI_LIGHT, "#6f7d2b"),
                 ("分隔线", brand.LINE, "#d9d3c5")]
        n = len(chips)
        x0, gap = 0.06, 0.127
        for i, (name, color, hexv) in enumerate(chips):
            x = x0 + i * gap
            fig.add_artist(FancyBboxPatch(
                (x, 0.435), 0.115, 0.095, boxstyle="round,pad=0,rounding_size=0.008",
                transform=fig.transFigure, facecolor=color,
                edgecolor=brand.LINE, linewidth=0.8, zorder=3))
            fig.text(x, 0.405, name, fontsize=8.2, color=brand.INK_SOFT,
                     ha="left", va="center")
            fig.text(x, 0.378, hexv, fontsize=7.8, color=brand.MUTED,
                     ha="left", va="center", fontfamily=list(brand.MONO_FONT))

        # 用法三条
        fig.text(0.06, 0.295, "用法", fontsize=10, fontweight="bold",
                 color=brand.INK, ha="left", va="center")
        notes = [
            "标志最小 24px；四周留白 ≥ 标志高度的 1/2，不加描边、不加阴影。",
            "深色底用反白版（墨块换纸底、SI 换 #c2d05a）；浅色底只用墨色版（SI #6f7d2b）。",
            "图表里只在页眉右上角放一个 lockup；页脚不放品牌条，底部只留一行风险提示。",
        ]
        for i, line in enumerate(notes):
            fig.text(0.06, 0.245 - i * 0.038, f"0{i + 1}", fontsize=8.5,
                     color=brand.MUTED, ha="left", va="center",
                     fontfamily=list(brand.MONO_FONT))
            fig.text(0.085, 0.245 - i * 0.038, line, fontsize=9.5,
                     color=brand.INK_SOFT, ha="left", va="center")

        fig.text(0.06, 0.055, "历史回测数据仅供参考，非投资建议。", fontsize=8.5,
                 color=brand.MUTED, ha="left", va="center")

        path = OUT / "brand-board.png"
        fig.savefig(path, dpi=150, facecolor=brand.PAPER)
        plt.close(fig)
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in brand.write_assets(OUT):
        print(f"  svg  → {p.name}")
    print(f"  png  → {board().name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
