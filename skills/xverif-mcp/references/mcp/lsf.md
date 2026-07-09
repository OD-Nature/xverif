# MCP LSF backend

MCP 使用 LSF 时设置：

```bash
XVERIF_MCP_BACKEND=lsf
```

链路：

```text
MCP client -> xverif-mcp -> LsfLauncher -> bsub -I tools/xdebug --stdio-loop
```

xcov 同理启动 `tools/xcov --stdio-loop`。

## 环境变量

- `XVERIF_MCP_BACKEND=lsf`
- `XVERIF_LSF_BSUB`
- `XVERIF_LSF_BKILL`
- `XVERIF_LSF_SESSION_QUEUE`
- `XVERIF_LSF_SESSION_RESOURCE`
- `XVERIF_MCP_STARTUP_TIMEOUT_SEC`
- `XVERIF_MCP_REQUEST_TIMEOUT_SEC`
- `XVERIF_MCP_FAKE_LSF=1` 本地 fake LSF

MCP server 子进程不会自动继承 IDE/shell 外的环境。必须在 MCP 配置里显式列出计算节点需要的 Verdi、NPI、license、PATH、LSF 变量。

如果必须 LSF 但不能使用 MCP SDK，或要脚本化驱动 session，改用 [../sdk-free-loop/overview.md](../sdk-free-loop/overview.md)。
