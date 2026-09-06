# 本轮回测环境

- WSL Ubuntu / Python 3.12.3
- freqtrade 2026.5.1
- pandas 3.0.3
- numpy 2.5.0
- ccxt 4.5.61
- TA-Lib 0.6.8
- ft-pandas-ta 0.3.16（导入名 pandas_ta）
- pyarrow 24.0.0

## 本地运行

在本项目根目录的WSL终端执行：

```bash
.venv/bin/python validation/e0v1e64/test_variants.py
.venv/bin/python validation/e0v1e64/run_suite.py --workers 1
```

继续已中断的批次：

```bash
.venv/bin/python validation/e0v1e64/run_suite.py --resume --workers 1
```

单独重建汇总报告（要求六个导出齐全）：

```bash
.venv/bin/python validation/e0v1e64/summarize.py
```

本轮使用已有run_backtest.py与fix_dns.py离线市场补丁，不连接实盘交易账户。
数据是okx_2025_full_server_archive本地目录中的588份feather文件。
数据逐文件SHA256、源码及配置SHA256在year-2025/manifest.json。
每个完成版本另有completed.json，记录结果zip的SHA256与实际输入。

## 执行记录

- B0已完整复现历史基准：864笔、收益795.5182276%、PF1.4137013，入场/退出逐笔一致。
- 规则/参数/时点及月度边界共10项测试通过。
- 最初两个优化版并行导致15GiB内存及15GiB交换空间接近耗尽，已中止该并行尝试。
- 未完成的并行输出不计作回测结果；后续采用串行完整重跑。
- 结果按固定规则汇总，未因试验输赢调整策略门槛。

本文件中的命令针对原ft_userdata工程目录结构。归档脚本在tools/中保留原路径逻辑；异地复现应恢复上述目录结构并提供原数据和离线市场补丁。
