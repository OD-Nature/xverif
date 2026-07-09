# SDK-free xdebug/xcov LSF

必须 LSF 且无法使用 MCP 或需要脚本化运行时，优先使用 SDK-free wrapper：

```bash
XVERIF_LOOP_BACKEND=lsf \
XVERIF_LOOP_SOCKET=/tmp/xverif-loop.sock \
tools/xverif-loop-server
```

server 会通过 LSF 启动：

```text
bsub -I tools/xdebug --stdio-loop
bsub -I tools/xcov --stdio-loop
```

## 常用环境变量

- `XVERIF_LOOP_BACKEND=lsf`
- `XVERIF_LSF_BSUB`：覆盖 bsub 命令。
- `XVERIF_LSF_BKILL`：覆盖 bkill 命令。
- `XVERIF_LSF_SESSION_QUEUE`：session job queue，默认 `interactive`。
- `XVERIF_LSF_SESSION_RESOURCE`：LSF resource string。
- `XVERIF_LOOP_FAKE_LSF=1`：本地 fake LSF 测试。

LSF job 从 wrapper server 继承环境。脚本启动 server 时必须显式设置计算节点需要的 `VERDI_HOME`、`LD_LIBRARY_PATH`、license 和 PATH。

## 使用建议

- 每个 wrapper session 对应一个 backend process；LSF 模式下是一个 LSF interactive job。
- 同一 session 请求串行；不同 session 可并行。
- 关闭 session 或 server shutdown 时 wrapper 会尝试清理 subprocess 和 LSF job。
