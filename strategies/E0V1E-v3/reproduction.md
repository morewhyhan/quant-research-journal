# E0V1E V3 Reproduction

## 目录内容

| 路径 | 内容 |
| --- | --- |
| `variants/original/` | 原始 V3 策略源码和参数 JSON |
| `variants/longstake25/` | V3 longstake25 关键变体源码和参数 JSON |
| `variants/marketregime/` | V3 marketregime 关键变体源码和参数 JSON |
| `backtest-results/original/` | 原始 V3 关键回测 zip 和 meta |
| `backtest-results/longstake25/` | longstake25 关键回测 zip 和 meta |
| `backtest-results/marketregime/` | marketregime 关键回测 zip 和 meta |

## 复刻方式

选择一个 `variants/` 下的版本，把里面的 `.py` 和 `.json` 放入 Freqtrade 的 `user_data/strategies/`。

回测结果包已经放在对应的 `backtest-results/` 子目录中。Freqtrade 导出的 zip 内通常包含：

- 回测 JSON 明细。
- 回测时的 config 快照。
- 回测时的 strategy 源码快照。
- wallet / market change 等辅助结果。

因此后续复盘时，应优先使用这里保存的 zip，而不是只看 markdown 表格。

