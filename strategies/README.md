# Strategies

每个子目录对应一个策略。目录名使用稳定策略名，不按临时文件名命名。

建议每个策略目录保持以下文件：

| 文件 | 用途 |
| --- | --- |
| `README.md` | 当前结论、是否继续研究、核心风险 |
| `backtests.md` | 关键回测结果，只保留有判断价值的样本 |
| `reproduction.md` | 复刻说明：源码、配置、回测包分别在哪里 |
| `live-trial.md` | 实盘/试盘记录；没有试盘则可以不建 |

建议每个策略目录保持以下子目录：

| 子目录 | 用途 |
| --- | --- |
| `strategy/` 或 `variants/` | 策略源码和参数 JSON |
| `backtest-results/` | 关键回测 zip 和 meta 文件 |
| `live-reproduction/` | 实盘相关配置；只放脱敏配置，不放私钥 |
