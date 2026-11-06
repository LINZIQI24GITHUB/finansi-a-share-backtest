# 一句话回测A股

**Skill ID：** `finansi-a-share-backtest`

**一句话回测A股**：你只需要说“用 300750 跑 2024–2025 双均线回测”，Agent 就会取数、执行、输出中文报告和权益图。

把「成交假设」和「复权口径」当真的 A 股日频回测。

一条命令，两个产出：终端中文报告 + 一张带绩效表的图。

![宁德时代 300750 · 5/20 双均线](docs/example-300750.png)

> 这张样例里，策略跑输了买入持有 61 个百分点——这正是它的用处。图上直接把基准画在一起，
> 不会用一条好看的曲线把结论藏起来。

## 和常见回测脚本的区别

| | 常见做法 | 这个 Skill |
|---|---|---|
| 成交时点 | 信号当天收盘价成交 | **次日开盘价**成交（收盘后才看得到信号） |
| 涨停 / 跌停 | 忽略 | 一字板不成交，单独计数 |
| 停牌 | 按收盘价成交 | 零成交日不成交 |
| 整手 | 想买多少买多少 | 100 股一手（科创板 200 股起） |
| 收益口径 | 前复权（高分红股会虚高） | **后复权** + 按窗口首日真实价缩放 |
| 产出 | 一条曲线 | 中文报告 + 图 + 机器可读 JSON |

## 60 秒跑起来

```bash
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-backtest.git
cd finansi-a-share-backtest
pip install -r requirements.txt

python scripts/run.py run --code 300750 --start 2024-01-01 --end 2025-12-31 \
    --signal ma_cross --params fast=5,slow=20 --cash 100000
```

真实输出（和仓库自检用的是同一组数字，可复现）：

```text
──────────────────────────────────────────────────────────
  300750 · 双均线 5/20
──────────────────────────────────────────────────────────
  期末权益      178,198   总收益    78.20%
  年化收益      35.01%   年化波动  33.34%
  夏普           1.07   索提诺     1.49
  最大回撤     -20.82%   卡玛       1.68
  交易   13 笔  胜率  46.2%  盈亏比  4.21  盈利因子  3.61
  持仓占比  59.2%   总费用     1,648
──────────────────────────────────────────────────────────
  区间 2024-01-02 ~ 2025-12-31（485 根）　口径 后复权 × 0.5482（锚定首日真实价）
  被规则挡掉：涨停 0 次，跌停 0 次，资金不足 0 次，T+1 0 次
  权益曲线图 → backtest_300750_ma_cross.png
```

`--code` 支持 6 位代码、中文名（`宁德时代`）和 ETF（`510300`）。

## ETF 也能直接跑

![沪深300ETF 510300](docs/example-510300.png)

```bash
python scripts/run.py run --code 510300 --start 2024-01-01 --end 2026-12-31 --signal ma_cross --cash 1000000
```

写 6 位代码就行：ETF 会自动贴简称，按基金规则收费（**卖出不收印花税**），
沪市 `5xxxxx`、深市 `15xxxx` 都能识别。想要更短的标题可以 `--name "沪深300ETF"` 覆盖。

## 策略：内置信号 + 规则 JSON

内置两个信号：`ma_cross(fast,slow)`、`rsi_reversion(n,low,high)`。

更复杂的策略写成**受控的规则 JSON**——同一份 JSON 永远同一个结果，不用现写代码：

```bash
python scripts/run.py run --code 300308 --start 2024-01-01 --end 2026-12-31 \
    --rule '{"entry":[{"ind":"vol_ma","fast":5,"slow":10}],
             "exit":[{"ind":"vol_ma","fast":5,"slow":10,"below":true}],
             "stop_loss":8}'
```

| 原语 | 参数 | 含义 |
|---|---|---|
| `ma_cross` | `fast`, `slow` | 快线在慢线上方 |
| `price_above_ma` | `n` | 收盘站在 n 日均线上 |
| `rsi` | `n` + `lt` / `gt` | RSI 条件 |
| `bollinger` | `n`, `k`, `side` | 跌破下轨 / 突破上轨 |
| `breakout` | `n` | 收盘突破前 n 日最高 |
| `vol_ma` | `fast`, `slow`, `below` | 成交量均线（放量 / 缩量） |

`entry` 内多条是 AND，`exit` 内是 OR；可选 `stop_loss` / `take_profit`（百分比，按日内高低点触发）。

## 产出

- **中文报告**：期末权益、年化、夏普、索提诺、最大回撤、卡玛、胜率、盈亏比、费用、被规则挡掉的次数
- **PNG 图表（默认必出）**：权益曲线 + 买入持有基准 + 回撤 + 7 项绩效表 + 风险提示
  - 出图失败会以退出码 `2` 结束并提示装 matplotlib，不会悄悄降级成纯文字；只要文字请显式 `--no-plot`
- `--out x.csv`：另存权益曲线
- `--json`：机器可读结果，含 `chart` 路径

## 自检

```bash
python scripts/run.py demo       # 引擎 5 项断言（用本地缓存，跑对了才有意义）
python scripts/check_chart.py    # 制图 17 项断言（含像素级校验：lime 顶边、标志、绩效表、免责声明）
```

## 安装到 Agent

```text
Claude Code   ~/.claude/skills/finansi-a-share-backtest/
Codex         ~/.codex/skills/finansi-a-share-backtest/
Cursor        ~/.cursor/skills/finansi-a-share-backtest/
通用           ~/.agents/skills/finansi-a-share-backtest/
```

Windows：

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-backtest.git "$HOME\.agents\skills\finansi-a-share-backtest"
cd "$HOME\.agents\skills\finansi-a-share-backtest"
pip install -r requirements.txt
```

依赖 Python 3.11+ / `pandas` `numpy` `matplotlib` `eltdx`，不需要 API key。

## 数据

首次运行时通过 `eltdx` 拉取日线，缓存在 `~/.ashare/data`（可用 `ASHARE_DATA` 改路径），
之后增量更新。原始行情不随仓库分发。

## 为什么必须用后复权

同一只票、同一区间（300750，2024-01-02 → 2025-12-31）的买入持有收益：

| 口径 | 区间累计收益 | 说明 |
|---|---|---|
| 不复权 | 134.18% | 只有价格，不含分红 |
| **后复权** | **139.84%** | 价格 + 分红，正确 |
| 前复权 | 162.65% | 虚高 23 个百分点 |

前复权会把历史价压得过低，高分红股票尤其失真——所以这里收益用后复权，
价格再按窗口首日真实价等比缩放（收益率不变，但整手和费用才算得准）。

## 限制

- 只做日频，不处理日内撮合、滑点与冲击成本；
- 涨停排队、大单冲击未建模，开盘价即成交价；
- 分红现金不单独入账（收益已体现在后复权里）；
- 不做参数寻优——同一段数据调出的最优参数几乎必然过拟合；
- **不构成投资建议，历史统计不代表未来。**

## License

MIT · 由 [FinanSI](https://finansi.work) 维护。
