# A-Share Backtest

A股日频回测，内置真实交易约束，避免“信号当天收盘价买入”的虚假收益。

- 信号在下一根日线开盘成交
- T+1：当日买入不可卖
- 一字涨停买不进、一字跌停卖不掉
- 整手（100 股；科创板 200 股）
- 佣金、印花税、过户费
- 输出 252 口径的夏普、卡玛、最大回撤、胜率、盈亏比、费用占比

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

依赖：

```bash
cd a-share-backtest
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.11+；依赖 pandas、numpy、requests。不需要 API key。

## 快速开始

```bash
# 拉 600519 日线（前复权）
python scripts/fetch_data.py --code 600519 --start 2024-01-01 --end 2025-12-31 --out data/

# 双均线回测
python scripts/run_backtest.py --code 600519 --start 2024-01-01 --end 2025-12-31 --strategy ma_cross

# 四种内置策略一起跑
python scripts/run_backtest.py --code 600519 --start 2024-01-01 --end 2025-12-31 --all

# 使用本地 CSV
python scripts/run_backtest.py --data data/600519.csv --strategy bollinger --params n=20,k=2
```

输出：终端中文报告 + `out/<code>_<strategy>_equity.csv`。

## 在 Agent 里调用

```text
用 a-share-backtest 跑 600519 从 2024-01-01 到 2025-12-31 的双均线回测，
确认信号次日开盘成交，并列出涨跌停导致的失败成交。
```

## 内置策略

```text
ma_cross      双均线
rsi_reversion RSI 反转
bollinger     布林带
donchian      唐奇安突破
```

## 约束与限制

- 只做日频；不处理日内撮合、滑点、冲击成本。
- 停牌、涨跌停、整手、费用按规则模拟，不等于真实券商成交。
- 数据来自公开行情接口；复权口径和数据质量需使用者自行确认。
- 不做参数寻优；同一段数据调出的最优参数可能过拟合。
- 不构成投资建议。

## License

MIT. See [LICENSE](LICENSE).
