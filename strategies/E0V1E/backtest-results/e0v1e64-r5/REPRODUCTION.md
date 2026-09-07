# 第五轮复现与归档说明

这是本地研究回测，不是服务器实盘记录；本轮没有改服务器，也没有让研究策略下实盘单。

## 文件布局

仓库中的 `strategies/E0V1E/versions/e0v1e64-r5` 是完整策略及父类、参数；
`strategies/E0V1E/backtest-results/e0v1e64-r5` 是冻结方案、回测输出和分析工具。

工具按原始工作目录布局运行：

```text
ft_userdata/
  run_backtest.py
  fix_dns.py
  my-strategies/E0V1E64_R4/
  my-strategies/E0V1E64_R5/
  validation/e0v1e64-r4/
  validation/e0v1e64-r5/
  user_data/data/okx_12m_archive/futures/
  user_data/data/okx_2025_full_server_archive/futures/
  .venv/
```

需把两轮的策略目录、结果目录映射回上述位置。R5内的 `workspace_helpers` 保存本次实际使用的根目录包装脚本。
冻结的 `fix_dns.py` 使用原WSL绝对数据路径，因此原环境完整路径为 `/mnt/c/Users/why/Desktop/ft_userdata`；这不是可在任意目录直接运行的安装包。
如需迁移路径，先明确记录包装器变更并另开一次实验，不能在现有冻结清单中替换哈希。

原始行情文件体积较大，未上传Git；两段 `manifest.json` 逐文件记录它们的SHA256。
只有结果ZIP、缺少这些原始行情时，可以查看成交统计，但不能完整复现信号和含浮盈亏净值。
2025归档缺失真实资金费，本轮没有虚构补齐。

## 执行与断点续跑

在原WSL环境的工作目录执行：

```bash
.venv/bin/python validation/e0v1e64-r5/test_combinations.py
.venv/bin/python validation/e0v1e64-r5/test_report.py
.venv/bin/python validation/e0v1e64-r5/run_suite.py
.venv/bin/python validation/e0v1e64-r5/window_report.py
.venv/bin/python validation/e0v1e64-r5/final_audit.py
```

`run_suite.py` 已完成的输出会验证后复用，不会再运行。它先核对与R4完全相同的行情、配置、父类及包装脚本，
复用V5/V14/V16/V17，再串行运行V18～V21。每份 `completed.json` 明确标记新跑或复用；
不能把8份旧对照说成8次新回测。精确参数与数据区间见 `SPEC.md`，运行版本见 `ENVIRONMENT.json`。

如果在空的新工作目录重新生成结果，仍需保留用于来源核验的R4控制输出；不要删除已有结果来强制重跑。
本轮策略输入在执行前冻结。统计报告脚本可以在不改动成交输出的前提下修正，但其最终哈希必须重新审计。

## 方差和规则效果

- 日收益是相邻UTC午夜的含浮盈亏账户净值之比减1；日样本方差采用 `ddof=1`。
- 表中日方差 = 小数收益方差 × 10000，单位为百分点²；日标准差 = 方差开平方，单位为%。
- `FACTOR_EFFECTS.json` 的主效果是其余两规则四种状态下“开启减关闭”的平均；
  两规则交互是第三条规则两种状态下的平均差中之差，三阶项是两种状态下两阶交互之差。
- 这些是固定历史路径中执行规则的整体效果，不是三个独立资产的收益；不能拿收益率直接相加。
- `MATCHED_CASES.json` 逐笔比较同币、同方向、同入场时间的交易；不同资金路径的金额差不应单独归因于退出规则。
- `MONTHLY.md`、`WINDOWS.json` 是逐月和滚动90天描述；滚动窗重叠，不是独立试验。
- V14排序中含三个指标，本轮只检验整个既定排序模块，不声称三个指标分别有独立预测力。

## 保留的风险与审计边界

普通回测使用OHLC时点假设；5m收盘估值回撤不是逐tick最低净值，也没有加入滑点。
冻结V5的空单 `min_rate` 方向问题和资金高水位重启恢复缺陷仍在，本轮不修改这些来混淆比较。
所有新组合继承禁止实盘运行的研究保护。

旧R4运行清单包含当时README哈希，后来README被补充结果；本轮没有篡改旧清单来掩盖这个差异。
复用校验针对行情、执行代码、参数、配置、包装器和原始ZIP；新R5冻结清单不依赖可追加的说明README。

仓库新增R5目录使用 `* -text` 的 `.gitattributes`，保留字节级换行，不让Git自动换行转换改变已审计源码SHA256。
