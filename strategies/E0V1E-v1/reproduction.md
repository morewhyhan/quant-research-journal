# E0V1E V1 Reproduction

## 目录内容

| 路径 | 内容 |
| --- | --- |
| `strategy/E0V1E.py` | V1 策略源码 |
| `strategy/E0V1E.json` | V1 策略参数 JSON |
| `live-reproduction/config.live.redacted.json` | 服务器 live 配置快照，已脱敏 |
| `live-reproduction/docker-compose.yml` | 服务器运行时 compose 快照 |
| `live-reproduction/entrypoint.sh` | 服务器运行入口脚本 |
| `live-reproduction/pairlists/` | live 使用过的自定义 pairlist/filter |
| `backtest-results/` | 保留下来的关键回测 zip 和 meta |

## 复刻方式

把 `strategy/E0V1E.py` 和 `strategy/E0V1E.json` 放入 Freqtrade 的 `user_data/strategies/`。

如果要复刻服务器 live 环境，还需要：

- 使用 `live-reproduction/config.live.redacted.json` 作为基础配置。
- 自行补入 `config.private.json` 或交易所密钥。
- 保留 `live-reproduction/pairlists/` 中的自定义 pairlist/filter。
- 使用 `live-reproduction/entrypoint.sh` 注册自定义 pairlist/filter。

## 注意

`config.live.redacted.json` 已经打码，不包含交易所密钥，也不保留 API server 密码。

