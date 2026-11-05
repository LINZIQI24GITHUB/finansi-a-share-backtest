# A-Share Backtest

A 股日频回测，内置真实交易约束，避免“信号当天收盘价买入”的虚假收益。

- 信号在下一根日线**开盘**成交
- T+1：当日买入不可卖
- 一字涨停买不进、一字跌停卖不掉
- 整手（100 股；科创板 200 股起）
- 佣金、印花税（股票卖出单边，**ETF 免征**）、过户费
- **后复权**收益序列 + 按窗口首日真实价缩放的价格
- 输出 252 口径的夏普、卡玛、最大回撤、胜率、盈亏比、费用
- **每次回测默认产出一张品牌图表**：权益曲线 + 回撤 + 7 项绩效表 + 风险提示

> 回测是研究工具，不是投资建议，也不承诺收益。

## 安装

```bash
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-backtest.git
```

把目录放到 Agent 的 skills 目录：

```text
Claude Code   ~/.claude/skills/a-share-backtest/
Codex         ~/.codex/skills/a-share-backtest/
Cursor        ~/.cursor/skills/a-share-backtest/
通用           ~/.agents/skills/a-share-backtest/
```

Windows 示例：

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-backtest.git "$HOME\.agents\skills\a-share-backtest"
```

依赖（Python 3.11+）：

```bash
cd a-share-backtest
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

`pandas / numpy / matplotlib / eltdx`。不需要 API key，第一次跑会自动拉日线。

## 快速开始

```bash
python scripts/run.py run --code 300750 --start 2024-01-01 --end 2025-12-31 \
    --signal ma_cross --params fast=5,slow=20 --cash 100000
```

产出两个东西：终端中文报告 + `backtest_300750_ma_cross.png`（图表默认必出，
`--no-plot` 才跳过；出图失败会以退出码 2 结束，不会悄悄降级成纯文字）。

`--code` 支持 6 位代码、中文名（`宁德时代`）和 ETF（`510300`，名称用 `--name` 补）。

## 策略：内置信号 + 规则 JSON

内置信号：`ma_cross(fast,slow)`、`rsi_reversion(n,low,high)`。

更复杂的策略写成**受控的规则 JSON**，同一份 JSON 永远同一个结果：

```bash
python scripts/run.py run --code 300308 --start 2024-01-01 --end 2026-12-31 \
    --rule '{"entry":[{"ind":"vol_ma","fast":5,"slow":10}],
             "exit":[{"ind":"vol_ma","fast":5,"slow":10,"below":true}],
             "stop_loss":8}'
```

可用原语：`ma_cross`、`price_above_ma`、`rsi`、`bollinger`、`breakout`、`vol_ma`（成交量均线）。
`entry` 内是 AND，`exit` 内是 OR，可选 `stop_loss` / `take_profit`（百分比，按日内高低点触发）。

## 自检

```bash
python scripts/run.py demo        # 引擎自检（用本地缓存，5 项断言）
python scripts/check_chart.py     # 制图自检（合成数据，17 项断言）
```

## 输出

- 终端中文报告：期末权益、年化、夏普、索提诺、最大回撤、卡玛、胜率、盈亏比、费用
- `backtest_<代码>_<策略>.png`：权益曲线（带买入持有基准）+ 回撤 + 绩效信息表 + 风险提示
- `--out` 可另存权益曲线 CSV；`--json` 输出机器可读结果（含 `chart` 路径）

## 在 Agent 里调用

```text
用 a-share-backtest 跑 300308 从 2024-01-01 到 2026-12-31 的成交量均线策略，
确认信号次日开盘成交，并列出涨跌停导致的失败成交。
```

## 约束与限制

- 只做日频；不处理日内撮合、滑点、冲击成本。
- 停牌、涨跌停、整手、费用按规则模拟，不等于真实券商成交。
- 收益用后复权（含分红），价格按窗口首日真实价缩放；分红现金不单独入账。
- 不做参数寻优；同一段数据调出的最优参数可能过拟合。
- 不构成投资建议。

## License

MIT. See [LICENSE](LICENSE).
