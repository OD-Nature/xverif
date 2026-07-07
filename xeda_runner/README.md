# xeda-runner

带环境快照缓存的阻塞式 allowlist command runner。

纯 Python 标准库实现，零 pip 依赖。支持 bash / zsh / tcsh。

## 快速开始

```bash
# 初始化环境快照
xeda-runner init

# 查看可用 action
xeda-runner list-actions

# 了解 action 详情（含 command/fixed_args，仅供审计）
xeda-runner describe-action --action sim

# 预览命令（不需要 init）
xeda-runner run --action sim --target compile --option TEST=smoke_test --dry-run

# 执行
xeda-runner run --action sim --target compile --option TEST=smoke_test --option SEED=123
```

## 输出

正常执行时终端和 `~/.xeda_runner/<pid>.log` 同步输出：

```
[xeda-runner] log: ~/.xeda_runner/543212.log
[xeda-runner] runner_pid=543212 runner_pgid=543212
[xeda-runner] child_pid=543213 child_pgid=543212
[xeda-runner] action=sim target=compile
[xeda-runner] command: make -j8 compile TEST=smoke_test SEED=123
[xeda-runner] cwd=/proj/nic/work
... (命令 stdout/stderr) ...
[xeda-runner] exit_code=0
```

- `runner_pid`：xeda-runner 自身进程
- `child_pid`：实际启动的命令（make/vcs 等），可用于 `kill` 或监控
- `exit_code`：命令真实退出码

`--quiet` 可抑制以上 header 输出。

## 配置文件

`.xeda-runner.yaml`，详细格式见目录下示例文件。主要字段：

- `shell`：`tcsh` / `bash` / `zsh`
- `workdir`：工作目录（runner 自动 `cd`，**不要在 init_steps 里手动写**）
- `init_steps`：初始化命令序列，每步失败即退出（tcsh 用 status check，bash/zsh 用 `set -e`）
- `actions`：白名单，支持 target allowed + option values/pattern/required 校验
- `checks`：init 后验证这些命令在 PATH 中

## 命令

| 命令 | 功能 |
|---|---|
| `init [--refresh]` | 生成 init 脚本并执行，保存 env0 快照 |
| `env-info` | 查看快照状态（含 checks resolved paths） |
| `list-actions` | 列出白名单 action |
| `describe-action --action <name>` | 查看 action 完整配置 |
| `run --action <name> [--target <t>] [--option K=V ...]` | 阻塞执行 |
| `run --dry-run` | 仅校验并打印 argv，不执行，**不需要 init** |
| `run --quiet` | 抑制 header 输出 |

## 长任务说明

xeda-runner 是阻塞式 runner，不会后台化执行。如果预估命令执行时间超过 **5 分钟**，建议使用 `tmux` 或 `nohup` 保证任务不会被 terminal / shell 生命周期影响：

```bash
# tmux（推荐）
tmux new -d -s sim "xeda-runner run --action sim --target compile --option TEST=smoke"

# 查看输出
tmux capture-pane -t sim -p

# nohup
nohup xeda-runner run --action sim --target compile --option TEST=smoke > sim.log 2>&1 &

# 查看输出
tail -f sim.log
```

xeda-runner 只负责启动进程，不负责后台存活和结果监控。

## License

MIT
