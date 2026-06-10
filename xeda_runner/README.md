# xeda-runner

带环境快照缓存的阻塞式 allowlist command runner。

纯 Python 标准库实现，零 pip 依赖。支持 bash / zsh / tcsh。

## 快速开始

```bash
# 初始化环境快照
xeda-runner init

# 查看可用 action
xeda-runner list-actions

# 了解 action 详情
xeda-runner describe-action --action sim

# 执行
xeda-runner run --action sim --target compile --option TEST=smoke_test --option SEED=123

# 仅预览，不执行
xeda-runner run --action sim --target compile --dry-run
```

## 配置文件

`.xeda-runner.json`，详细格式见目录下示例文件。

## License

MIT
