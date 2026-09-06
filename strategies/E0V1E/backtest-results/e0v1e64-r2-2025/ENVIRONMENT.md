# 第二轮执行环境与复现

最终数据质量更正见DATA_QUALITY.md；2025实际池180、实际资金费未计，7月组不采用，另补6月1～29日。规则测试11项、报告测试3项均通过。

沿用上一轮WSL Ubuntu / Python 3.12.3 / freqtrade 2026.5.1 / pandas 3.0.3 / numpy 2.5.0 / ccxt 4.5.61 / TA-Lib 0.6.8 / ft-pandas-ta 0.3.16 / pyarrow 24.0.0。

本地源目录：my-strategies/E0V1E64_R2。完整冻结父类及JSON随源码归档；没有更改服务器策略或旧版研究文件。

数据目录：user_data/data/okx_2025_full_server_archive。588份feather文件的哈希必须与上一轮V5的manifest逐项一致，否则运行器拒绝继续。198项白名单中196项有5m数据；不同币种的上市时间不同。

执行前11项单元测试全部通过。测试涵盖参数加载、旧父类一致性、120分钟边界、70%利润线、跳空穿越软退出、空单高价的正确时点、入场前价格排除、多继承下V5功能保留、仓位上限、live禁止。

所有全年回测使用独立进程串行执行，禁止并行以避免15GiB WSL内存耗尽。run.log保留本地；公开结果包含原始ZIP、meta、completed、manifest、baseline_validation和comparison。completed包含实际输入哈希与结果ZIP哈希。

运行脚本依赖ft_userdata工作区布局与已有run_backtest.py / fix_dns.py。fix_dns提供离线市场/精度/杠杆档模拟，不是历史交易所全部限制的真实重建；其源码和哈希一起归档便于审计。研究仓库不携带大型行情数据或完整Python虚拟环境，复制到其他机器仍须恢复这些依赖。

原始回测假设和局限参见[Freqtrade官方回测说明](https://docs.freqtrade.io/en/stable/backtesting/)。新规则的定点因果测试不等同于全策略lookahead-analysis或实盘一致性证明，后者需另行验证；参见[官方未来数据检查说明](https://www.freqtrade.io/en/stable/lookahead-analysis/)。

本轮报告里的EV是历史单笔profit_ratio均值，不是已知的未来数学期望；金额PF是正盈亏金额之和除以负盈亏绝对值之和，受复利与仓位路径影响。
