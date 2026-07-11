# xeda-runner EDA 命令执行

xeda-runner 是项目 EDA 命令安全执行器。需要执行 make/vcs/simv/urg/verdi 等依赖 setup/module 环境的命令时使用。

## 禁止直接执行

如果项目配置了 xeda-runner，不要直接执行：

- `make`
- `vcs`
- `simv`
- `urg`
- `verdi`
- `xrun`
- 手动 source setup.csh/setup.sh

## 工作流

```bash
xeda-runner init
xeda-runner list-actions
xeda-runner describe-action --action <name>
xeda-runner run --action <name> --target <target> --option KEY=VALUE --dry-run
xeda-runner run --action <name> --target <target> --option KEY=VALUE
```

## 读取输出

- `runner_pid`：runner 进程。
- `child_pid`：实际 EDA 命令进程，监控/kill 用。
- `exit_code`：底层命令真实退出码。
- 日志同步写到 `~/.xeda_runner/<pid>.log`。

## 排障

- init 失败不会生成有效 env 快照；先修 setup/module。
- option 校验失败：看 action 的 allowed values/pattern。
- 预估超过 5 分钟时建议用户用 `tmux` 或 `nohup`，runner 本身不负责后台监控。
