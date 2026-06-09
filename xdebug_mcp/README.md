# xdebug MCP / LSF backend

`xdebug_mcp` 是 `tools/xdebug-mcp` 的 Python 实现，基于 FastMCP SDK。提供两种 backend：

- `direct`：本机启动 `tools/xdebug --stdio-loop`（长连接进程，session 生命周期内复用）。
- `lsf`：通过 `bsub -I tools/xdebug --stdio-loop` 提交到 LSF 集群。

direct 和 LSF 共用 `XdebugLoopSession`，只在 `Launcher` 层分离。每 session 独立进程，同 session 串行（request_lock），多 session 可并行。

## 环境要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Verdi / VCS | V-2023.12-SP2 及以上 | 需 NPI 库，设置 `VERDI_HOME` |
| GCC | 5.0+ | 编译 xdebug C++ 代码 |
| Python | 3.11+ | 推荐 conda 环境 |
| pip | `mcp[cli]` | FastMCP + MCP Inspector |

## 入口

```bash
tools/xdebug-mcp
tools/xdebug-lsf-doctor
```

```bash
tools/xdebug-mcp
tools/xdebug-lsf-doctor
```

## MCP 配置

### Claude Code

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "xdebug": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xdebug_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xdebug_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "VERDI_HOME": "<verdi-install>",
        "LD_LIBRARY_PATH": "<verdi-install>/share/NPI/lib/LINUX64",
        "XDEBUG_MCP_BACKEND": "direct"
      }
    }
  }
}
```

LSF 模式将 `XDEBUG_MCP_BACKEND` 改为 `lsf`，并可设置队列：
```json
"XDEBUG_MCP_BACKEND": "lsf",
"XDEBUG_LSF_SESSION_QUEUE": "interactive"
```

### 通用 MCP client

```json
{
  "mcpServers": {
    "xdebug": {
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xdebug_mcp.server"],
      "env": { ... }
    }
  }
}
```

## 运行链路

```text
AI MCP client
  -> xdebug-mcp FastMCP server
  -> McpSessionManager
  -> DirectLauncher:           tools/xdebug --stdio-loop    (direct mode)
  -> LsfLauncher:     bsub -I tools/xdebug --stdio-loop    (LSF mode)
```

direct 和 LSF 共用 `XdebugLoopSession`（session 生命周期、request/response、timeout、cleanup），只在 `Launcher` 层分离。

- 不同 session 并行（独立 process），同 session 串行（request_lock）。
- session_open 是 eager open（立即启动 `--stdio-loop` 进程）。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `XDEBUG_MCP_BACKEND` | `direct`（默认）或 `lsf` |
| `XDEBUG_LSF_BSUB` | 覆盖 `bsub` 命令（默认 `bsub`） |
| `XDEBUG_LSF_SESSION_QUEUE` | session job 的 LSF 队列（默认 `interactive`） |
| `XDEBUG_LSF_BKILL` | 覆盖 `bkill` 命令 |
| `XDEBUG_MCP_FAKE_LSF=1` | 本地测试用 fake LSF runner |
| `XDEBUG_MCP_TIMEOUT_SEC` | direct one-shot 请求超时 |
| `XVERIF_HOME` | 仓库根目录 |
| `VERDI_HOME` | Verdi 安装目录（direct 模式需要） |

## 测试

```bash
make -C xdebug PYTHON=python3 mcp-test
PYTHON=python3 XDEBUG_MCP_FAKE_LSF=1 tools/xdebug-lsf-doctor --fake
```

测试里的 fake LSF 不需要真实 `bsub`，但会覆盖 ready 噪声、多 session 并行、同 session 串行、session crash 隔离和 xout/json/envelope 返回。

## 配置 Claude Code MCP

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "xdebug": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xdebug_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xdebug_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "VERDI_HOME": "<verdi-install>",
        "LD_LIBRARY_PATH": "<verdi-install>/share/NPI/lib/LINUX64",
        "XDEBUG_MCP_BACKEND": "direct"
      }
    }
  }
}
```

替换说明：
- `<conda-env>`：安装了 `mcp[cli]` 的 Python 环境路径（如 `~/miniconda3/envs/xdebug-mcp`）
- `<xverif>`：xverif 仓库根目录
- `<verdi-install>`：Synopsys Verdi 安装根目录（`XDEBUG_MCP_BACKEND=lsf` 时不需要）

`XDEBUG_MCP_BACKEND` 可选值：
- `direct`：本机启动 `tools/xdebug --stdio-loop`
- `lsf`：通过 `bsub -I tools/xdebug --stdio-loop` 提交到 LSF

Claude Code 在启动时会自动加载项目根目录下的 `.mcp.json`，无需额外配置。
