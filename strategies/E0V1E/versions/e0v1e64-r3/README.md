# 第三轮完整源码：V5基准，V10～V13独立候选

V5依赖链完整冻结：E0V1E_v3 → E0V1E_v3_equity60_reserve40 → ResearchBase → E0V1E64_V5。V10～V13各自从V5派生，V6不在继承链中。

V10相对ATR仓位；V11近期已平仓表现预算；V12多单入场价15%灾难止损；V13三槽且同方向最多两笔。每个可运行类都有同名参数JSON；V13必须使用最大持仓3，其余1。研究类拒绝live运行。

不要只复制一个子类文件，需要本目录所有父类和对应JSON。完整规则和证据见validation/e0v1e64-r3；GitHub归档报告为同策略下的backtest-results/e0v1e64-r3。
