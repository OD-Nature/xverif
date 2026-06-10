---
name: xeda-runner
description: 芯片项目 EDA 命令安全执行器。当 AI 需要执行 make/vcs/simv 等依赖项目 setup.csh/module 环境的命令时使用。
---

本项目的 EDA 命令必须通过 xeda-runner 执行。

## 禁止直接执行的命令

- make
- vcs
- simv
- urg
- verdi
- xrun
- xdebug
- 以及其他依赖项目 setup.csh / module 环境的命令

## 标准工作流

```bash
# 1. 首次使用：初始化环境快照
xeda-runner init

# 2. 查看可用 action
xeda-runner list-actions

# 3. 了解 action 支持的 target 和 option（含 command/fixed_args，仅供审计）
xeda-runner describe-action --action <name>

# 4. 预览命令（不需要 init）
xeda-runner run --action <name> --target <t> --option KEY=VALUE --dry-run

# 5. 执行命令
xeda-runner run --action <name> --target <t> --option KEY=VALUE
```

## 配置

配置文件为当前工作目录下的 `.xeda-runner.json`。如不在当前目录，可通过 `--config` 显式指定。

## 规则

- xeda-runner 是阻塞式命令，执行完成后根据 exit code 判断结果
- 禁止自行 source setup.csh / setup.sh
- 禁止自行设置环境变量
- 禁止自行拼接底层 EDA command
- 禁止绕过 xeda-runner 调用 make/vcs/simv/urg 等命令
- `describe-action` 输出的 `command`/`fixed_args` 仅供审计，不可绕过 runner 直接使用
