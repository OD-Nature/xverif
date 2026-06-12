# xverif MCP

`xverif_mcp` 是 `tools/xverif-mcp` 的 Python 实现，基于 FastMCP SDK。它是 xverif 工具体系统一 MCP 入口：

- **xdebug**：stateful backend，通过 `tools/xdebug --stdio-loop` 提供设计/波形查询能力，支持 direct/LSF 模式。
- **xcov**：stateful backend，通过 `tools/xcov --stdio-loop` 提供 VCS/Verdi coverage database 查询能力，支持 direct/LSF 模式。
- **xbit / xentry / xloc / xberif / xsva**：stateless CLI adapter，每次调用短生命周期 subprocess。

xdebug/xcov direct 和 LSF 共用 stdio-loop session manager，只在 `Launcher` 层分离。每 session 独立进程，同 session 串行（request_lock），多 session 可并行。

MCP 层保持轻量：它只负责启动/终止 `tools/xdebug --stdio-loop` 或
`tools/xcov --stdio-loop` 进程、维护 alias/default 映射、转发 JSON request、
处理 direct/LSF transport cleanup。设计/波形 session 状态由 xdebug 管理；
coverage database session、VDB/NPI handle、scope/cache/query 状态由 xcov 管理。

## 环境要求

| 组件 | 要求 |
|---|---|
| GCC | **5.0+** |
| Python | **3.11+**（`pip install "mcp[cli]"`） |
| Verdi | 当前基于 **V-2023.12-SP2** 开发与测试 |
| NPI | 随 Verdi 版本不同可能存在 API 参数差异 |

> 如果使用其他 Verdi 版本遇到编译或运行时 NPI 兼容性问题，可让 AI agent 根据编译错误和 NPI 头文件（`$VERDI_HOME/share/NPI/inc`）进行兼容性修复。

## 入口

```bash
tools/xverif-mcp
tools/xverif-lsf-doctor
```

## MCP 配置

### Claude Code

在项目根目录创建 `.mcp.json`（与 `.git/` 同级，**不是** `.claude/` 目录下）。

**direct 模式：**

```json
{
  "mcpServers": {
    "xverif": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xverif_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "XVERIF_MCP_BACKEND": "direct",
        "VERDI_HOME": "<verdi-install>",
        "LD_LIBRARY_PATH": "<verdi-install>/share/NPI/lib/LINUX64"
      }
    }
  }
}
```

**LSF 模式：**

```json
{
  "mcpServers": {
    "xverif": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xverif_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "XVERIF_MCP_BACKEND": "lsf",
        "XVERIF_LSF_SESSION_QUEUE": "interactive",
        "VERDI_HOME": "<verdi-install>",
        "LD_LIBRARY_PATH": "<verdi-install>/share/NPI/lib/LINUX64",
        "LSF_ENVDIR": "<lsf-install>/conf",
        "LSF_BINDIR": "<lsf-install>/bin",
        "LSF_LIBDIR": "<lsf-install>/lib",
        "LSF_SERVERDIR": "<lsf-install>/etc",
        "PATH": "<你的完整 PATH>",
        "SNPSLMD_LICENSE_FILE": "<synopsys-license>",
        "LM_LICENSE_FILE": "<cadence-license>",
        "MGLS_LICENSE_FILE": "<mentor-license>",
        "CDS_LIC_FILE": "<cadence-license>",
        "CDS_LIC_ONLY": "1",
        "DW_WAIT_LICENSE": "1"
      }
    }
  }
}
```

> **关键**：MCP server 子进程**不会自动继承**父进程（shell / IDE）的环境变量。`bsub` 提交的 LSF job 从 MCP server 子进程继承环境，因此**所有**必须在计算节点上生效的变量都要显式列在 `.mcp.json` 的 `env` 中——包括 `VERDI_HOME`、`LD_LIBRARY_PATH`、LSF 路径、EDA license 等。`PATH` 尤其重要，必须确保 `bsub`、`bkill` 等命令在其中。

替换说明：
- `<conda-env>`：安装了 `mcp[cli]` 的 Python 3.11 环境路径
- `<xverif>`：xverif 仓库根目录
- `<verdi-install>`：Synopsys Verdi 安装根目录
- `<lsf-install>`：LSF 安装根目录

`XVERIF_MCP_BACKEND` 可选值：
- `direct`：本机启动 `tools/xdebug --stdio-loop` 或 `tools/xcov --stdio-loop`
- `lsf`：通过 `bsub -I tools/<backend> --stdio-loop` 提交到 LSF

### 通用 MCP client

```json
{
  "mcpServers": {
    "xverif": {
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xverif_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>"
      }
    }
  }
}
```

Claude Code 启动时自动加载项目根目录下的 `.mcp.json`，无需额外配置。

## 运行链路

```text
AI MCP client
  -> xverif-mcp FastMCP server
  -> XverifDebugAdapter (xdebug)
       -> McpSessionManager
       -> DirectLauncher:  tools/xdebug --stdio-loop  (direct)
       -> LsfLauncher:     bsub -I tools/xdebug --stdio-loop  (LSF)
  -> XverifCoverageAdapter (xcov)
       -> McpSessionManager
       -> DirectLauncher:  tools/xcov --stdio-loop  (direct)
       -> LsfLauncher:     bsub -I tools/xcov --stdio-loop  (LSF)
  -> StatelessCliRunner (xbit/xentry/xloc/xberif/xsva)
       -> tools/<tool> --json ...
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `XVERIF_HOME` | 仓库根目录 |
| `XVERIF_MCP_BACKEND` | `direct`（默认）或 `lsf` |
| `XVERIF_MCP_TIMEOUT_SEC` | one-shot 请求超时（默认 360s） |
| `XVERIF_MCP_STARTUP_TIMEOUT_SEC` | session open 超时（默认 180s） |
| `XVERIF_MCP_REQUEST_TIMEOUT_SEC` | query 请求超时（默认 360s） |
| `XVERIF_MCP_CLOSE_TIMEOUT_SEC` | session close 超时（默认 30s） |
| `XVERIF_MCP_BKILL_TIMEOUT_SEC` | bkill 超时（默认 30s） |
| `XVERIF_MCP_ENABLE_WRITE=1` | 启用 xberif 写入操作 |
| `XVERIF_MCP_ENABLE_COMMON` | 暴露 common 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_DEBUG` | 暴露 xdebug/session 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_COV` | 暴露 xcov coverage 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_BIT` | 暴露 xbit 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_ENTRY` | 暴露 xentry 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_LOC` | 暴露 xloc 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_CONTEXT` | 暴露 xberif 只读 context 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_SVA` | 暴露 xsva 工具，默认 `1` |
| `XVERIF_MCP_ENABLE_CONTEXT_WRITE` | 暴露 xberif 写入/修复工具，默认 `0` |
| `XVERIF_LSF_BSUB` | 覆盖 `bsub` 命令（默认 `bsub`） |
| `XVERIF_LSF_SESSION_QUEUE` | session job 的 LSF 队列（默认 `interactive`） |
| `XVERIF_LSF_BKILL` | 覆盖 `bkill` 命令 |
| `XVERIF_XCOV_BIN` | 覆盖 xcov 可执行文件路径，默认 `tools/xcov` |
| `XVERIF_XCOV_PYTHON` | 覆盖 xcov 使用的 Python runtime |
| `XVERIF_XCOV_VERDI_HOME` | 覆盖 xcov 使用的 Verdi 安装路径 |
| `XVERIF_XCOV_LOG_DIR` | 覆盖 xcov 日志目录，默认 `~/.xverif/xcov` |
| `XVERIF_XCOV_LOG=0` | 关闭 xcov 日志 |
| `XVERIF_MCP_FAKE_LSF=1` | 本地测试用 fake LSF runner |
| `VERDI_HOME` | Verdi 安装目录 |
| `LD_LIBRARY_PATH` | 需包含 `<verdi-install>/share/NPI/lib/LINUX64` |

xdebug session 工具使用明确前缀：

```text
xverif_debug_session_open
xverif_debug_session_list
xverif_debug_session_use
xverif_debug_session_close
```

xcov session 工具使用 coverage 前缀：

```text
xverif_cov_session_open
xverif_cov_session_list
xverif_cov_session_use
xverif_cov_session_close
xverif_cov_query
```

## 工具暴露开关

每个工具组都有独立开关，取值支持 `1/0`、`true/false`、`yes/no`、`on/off`。未设置时，read-only 工具组默认开启；写入类工具默认不暴露。

```bash
# 只暴露 xdebug + common
XVERIF_MCP_ENABLE_BIT=0 \
XVERIF_MCP_ENABLE_ENTRY=0 \
XVERIF_MCP_ENABLE_LOC=0 \
XVERIF_MCP_ENABLE_CONTEXT=0 \
XVERIF_MCP_ENABLE_SVA=0 \
tools/xverif-mcp

# 关闭 xsva
XVERIF_MCP_ENABLE_SVA=0 tools/xverif-mcp

# 暴露 xberif 写工具
XVERIF_MCP_ENABLE_CONTEXT=1 \
XVERIF_MCP_ENABLE_CONTEXT_WRITE=1 \
XVERIF_MCP_ENABLE_WRITE=1 \
tools/xverif-mcp
```

`context_write` 工具需要同时满足：

```text
XVERIF_MCP_ENABLE_CONTEXT=1
XVERIF_MCP_ENABLE_CONTEXT_WRITE=1
XVERIF_MCP_ENABLE_WRITE=1
```

关闭某组后，该组工具不会注册到 FastMCP，因此不会出现在 MCP `tools/list` 中，也不能被 MCP client 直接调用。`xverif_tools` 和 `xverif_tool_help` 使用同一套策略；AI agent 不确定当前暴露范围时应先调用 `xverif_tools`。

## 测试

```bash
make -C xdebug PYTHON=python3 mcp-test
PYTHON=python3 XVERIF_MCP_FAKE_LSF=1 tools/xverif-lsf-doctor --fake
```
