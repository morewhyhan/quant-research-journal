# E0V1E 2025 Full-Year Comparison

This directory records four backtests using the same server-sourced OKX dataset and the same backtesting configuration.

## Dataset

- Source: server archive okx_2025_full_current_universe.tar.gz
- Coverage: 2024-12-31 startup data through 2026-01-01
- Backtest window: 2025-01-01 through 2026-01-01
- Data files: 196 five-minute futures files, 196 mark files, and 196 funding-rate files
- Initial wallet: 8,000 USDT
- Maximum open trades: 1
- Fee: 0.05%
- Protection: 18-candle cooldown
- Current configuration whitelist: 198 pairs; 196 pairs had five-minute data in this archive

The 223 MB source archive is intentionally not committed to this repository. Its local SHA-256 is:

957e36b54c896465303ba293026603c6ea77dab13bfc7e9d38ed824b13503635

## Results

| Version | Trades | Return | PF | Max drawdown | Sharpe | Sortino | EV/trade | Win rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V3 Original | 863 | +379.50% | 1.332 | 32.34% | 3.37 | 2.08 | +0.332% | 86.79% |
| V3 Original + 60/40 | 863 | +320.95% | 1.324 | 27.27% | 3.49 | 2.26 | +0.332% | 86.79% |
| Server current V3 | 864 | +790.04% | 1.305 | 42.98% | 2.91 | 1.55 | +0.361% | 86.81% |
| Server current V3 + 60/40 | 864 | +795.52% | 1.414 | 33.02% | 3.87 | 2.12 | +0.361% | 86.81% |

## Interpretation

The server-current 60/40 research replay is the best of these four on this sample: it slightly increases terminal return while reducing maximum drawdown by about 9.97 percentage points and improving PF and Sharpe.

This is not evidence that the result will persist indefinitely. The sample uses the current pair whitelist replayed backward, includes contracts with different listing dates, and the server-current result is driven mainly by the short side. The position-sizing variant also needs high-water-mark persistence across restarts.

## Historical repository comparison

The repository's older V3 Original records used a fixed 143-pair data set:

| Period | Return | Max drawdown | PF | Trades |
| --- | ---: | ---: | ---: | ---: |
| 2024 | +128.85% | 57.95% | 1.15 | 689 |
| 2025H1 | -35.12% | 48.98% | 0.87 | 335 |
| 2025H2 | -67.89% | 67.95% | 0.68 | 282 |
| 2026H1 | +155.04% | 14.84% | 1.69 | 255 |

Those historical records are not directly comparable with this 196-pair server archive.
