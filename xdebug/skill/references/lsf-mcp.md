# xverif MCP LSF backend

本文说明 AI MCP 场景下如何使用 LSF backend 把 xdebug 查询提交到 LSF 计算节点。

## 架构

```text
MCP Client / Agent
    |
    v
xverif_mcp FastMCP server
    |
    v
McpSessionManager
    |
    v
LsfLauncher -> bsub -I tools/xdebug --stdio-loop
```

LSF 和 direct 共用 `XdebugLoopSession`，区别仅在于进程启动方式：
- `DirectLauncher`: 本地 `tools/xdebug --stdio-loop`
- `LsfLauncher`: `bsub -I tools/xdebug --stdio-loop`

## 配置

```json
{
  "mcpServers": {
    "xverif": {
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xverif_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "XVERIF_MCP_BACKEND": "lsf",
        "XVERIF_LSF_SESSION_QUEUE": "interactive"
      }
    }
  }
}
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `XVERIF_MCP_BACKEND` | 必须是 `lsf` | `direct` |
| `XVERIF_LSF_BSUB` | bsub 命令 | `bsub` |
| `XVERIF_LSF_SESSION_QUEUE` | session job 队列 | `interactive` |
| `XVERIF_LSF_BKILL` | bkill 命令 | `bkill` |
| `XVERIF_MCP_FAKE_LSF` | 设为 `1` 使用 fake bsub（本地测试） | — |

## 生命周期

```
session_open("case_a") → LsfLauncher 启动 bsub -I tools/xdebug --stdio-loop
                       → wait_ready("xdebug-stdio-loop")
                       → 发送 session.open → 记录 session_id → state=alive

query("case_a")        → stdin JSONL 发送请求，stdout JSONL 读取响应

session_close("case_a")→ 发送 session.close + stdio.quit
                       → launcher.terminate() → bkill <job_id>
```

每个 session 一个独立 LSF job。同 session 内串行（request_lock），多 session 可并行。

## 诊断

```bash
# fake LSF 本地自检
PYTHONPATH=xverif_mcp/src XVERIF_MCP_FAKE_LSF=1 python -m xverif_mcp.lsf.doctor --fake

# 真实 LSF 自检
PYTHONPATH=xverif_mcp/src python -m xverif_mcp.lsf.doctor

# 全量 action 测试
PYTHONPATH=xverif_mcp/src XVERIF_MCP_BACKEND=lsf XVERIF_MCP_FAKE_LSF=1 \
  python xverif_mcp/tools/test_actions.py
```
