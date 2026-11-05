# Data

回测数据不用手工准备：第一次跑会自动通过 `eltdx` 拉取日线，缓存在
`~/.ashare/data`（可用环境变量 `ASHARE_DATA` 指定别处）。

原始行情不随仓库分发——它的再分发条款取决于数据源。这个目录只放说明，
不要提交 CSV / parquet（见 `.gitignore`）。
