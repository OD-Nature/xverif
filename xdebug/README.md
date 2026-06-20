# xdebug

xdebug 是 xtrace 与 xwave 合并后的统一调试工具。公开入口使用 JSON request 描述动作，默认输出 `xout` 结构化文本；需要机器解析、schema 校验或回归兼容时显式加 `--json` 获取原 JSON response。旧的 xtrace/xwave 人类 CLI 不再作为主路径维护。

仓库内 skill source-of-truth 位于 [skill/SKILL.md](skill/SKILL.md)。更细的字段字典和 API 速查位于 [skill/references](skill/references)。

Action 协议由 `ActionSpec` / `ActionRegistry` 约束。`actions` 输出来自 runtime registry，并带有 `category`、`status`、`requires`、action-specific schema 和 example 信息；`xdebug/specs/actions/actions.yaml`、`xdebug/schemas/v1/actions` 与 `xdebug/examples` 由 contract test 校验一致。所有 non-removed action 都必须有自己的 request/response schema，不能退回通用 envelope schema。

## Quick Start

`-h` 和 `-help` 是 xdebug 唯一的非 JSON 命令，用于查看详尽的人类可读帮助：

```bash
tools/xdebug -h
tools/xdebug -help
```

默认输出是 `xout`，机器可读帮助仍通过 JSON action 获取；如果要让脚本读取完整字段，使用 `--json`：

```bash
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | tools/xdebug -
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | tools/xdebug --json -
printf '%s\n' '{"api_version":"xdebug.v1","action":"schema","args":{"action":"signal.statistics","kind":"request"}}' | tools/xdebug --json -
```

每个 action 的机器可读契约位于：

```text
xdebug/schemas/v1/actions/<action>.request.schema.json
xdebug/schemas/v1/actions/<action>.response.schema.json
xdebug/examples/requests/<action>.basic.json
xdebug/examples/responses/<action>.basic.json
```

`make -C xdebug contract-test` 会检查 runtime `actions` 输出、`specs/actions/actions.yaml`、schemas 和 examples 是否完全对齐。

推荐通过仓库根目录的 wrapper 调用，它会设置 Verdi/NPI 运行所需环境：

> **环境要求**：GCC 5.0+。当前基于 Verdi **V-2023.12-SP2** 开发与测试。NPI API 随 Verdi 版本不同可能存在参数差异——如果使用其他版本遇到编译或运行时 NPI 兼容性问题，可让 AI agent 根据编译错误和 NPI 头文件（`$VERDI_HOME/share/NPI/inc`）进行兼容性修复。

```bash
tools/xdebug -
```

从 stdin 传入 JSON request，默认返回 xout：

```bash
printf '%s\n' '{"api_version":"xdebug.v1","action":"value.at","target":{"session_id":"case_a"},"args":{"signal":"top.clk","time":"10ns"}}' \
  | tools/xdebug -
```

同一请求需要 JSON response 时：

```bash
printf '%s\n' '{"api_version":"xdebug.v1","action":"value.at","target":{"session_id":"case_a"},"args":{"signal":"top.clk","time":"10ns"}}' \
  | tools/xdebug --json -
```

典型 xout 输出：

```text
@xdebug.value.at.v1

target:
  signal: top.clk
  time: 10ns

summary:
  value: 1
  known: true
```

也可以使用请求文件：

```bash
tools/xdebug request.json
```

### Shell 命令入口

为了在任意目录和 Claude Code 这类非交互 shell 中稳定调用，建议把仓库 `tools/` 加入 `PATH`。下面示例里的 `<xverif-root>` 表示本仓库根目录，请按本机实际路径替换；文档和 skill 中不固定记录个人机器路径。

Bash：加入 `~/.bashrc`。

```bash
export XVERIF_HOME=<xverif-root>
export PATH="$XVERIF_HOME/tools:$PATH"
```

Zsh：加入 `~/.zshrc`。

```zsh
export XVERIF_HOME=<xverif-root>
export PATH="$XVERIF_HOME/tools:$PATH"
```

Tcsh：加入 `~/.tcshrc`。

```tcsh
setenv XVERIF_HOME <xverif-root>
setenv PATH "$XVERIF_HOME/tools:$PATH"
```

配置后可以直接使用：

```bash
xdebug -h
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | xdebug -
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | xdebug --json -
xdebug request.json
```

推荐使用 `tools/xdebug` 或 `PATH` 中的 `xdebug`。

### Cluster file transport

当本机或登录机无法直接连接计算节点 TCP 端口时，不要尝试把 xdebug daemon 暴露给本机直连；使用原生 `transport:"file"`，让 xdebug daemon 通过共享文件系统交换 request/response。默认交换目录在 backend session 目录下：

```text
~/.xdebug/design/sessions/<session_id>/transport/
~/.xdebug/waveform/sessions/<session_id>/transport/
```

启用方式：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "wave_file",
    "transport": "file"
  }
}
```

也可以设置新建 session 的默认 transport：

```bash
export XDEBUG_TRANSPORT=file
```

file transport v2 使用明确的状态目录，不再依赖 file lock：

```text
file transport directory:
  requests/    client-published pending requests
  claims/      worker-claimed running requests
  responses/   unread responses
  done/        archived request/claim/response history
  failed/      client_timeout / expired / stale_claim / invalid_request
  tmp/         atomic write temp files
  heartbeat/   worker liveness files
```

request 先写到 `tmp/`，再 atomic publish 到 `requests/`；daemon 用 `rename()` 抢到 `claims/`；response 写到 `responses/`，client 读完后默认归档到 `done/`。过期 request、坏 request、stale claim 和 client timeout 进入 `failed/`。如果旧 session 目录里还有 `locks/`，它只是历史残留，可以忽略。

普通 file transport 请求默认等待 300 秒，可用 `XDEBUG_FILE_TRANSPORT_TIMEOUT_MS` 调整；ping/quit 默认等待 2 秒，可用 `XDEBUG_FILE_TRANSPORT_PING_TIMEOUT_MS` 调整。大窗口 `axi.analysis`、`signal.changes` 或深层 `trace.graph` 如果确实需要更久，优先调普通请求 timeout，不要改 ping timeout。`XDEBUG_FILE_KEEP_HISTORY=1` 默认保留证据链；`XDEBUG_FILE_CLAIM_TIMEOUT_MS`、`XDEBUG_FILE_POLL_INTERVAL_MS`、`XDEBUG_FILE_MAX_JSON_BYTES`、`XDEBUG_FILE_DONE_TTL_SEC`、`XDEBUG_FILE_FAILED_TTL_SEC` 可用于高级排障和清理。

### MCP wrapper

`tools/xverif-mcp` 是基于 FastMCP SDK 的统一 MCP server。xdebug 作为设计/波形 stateful backend，通过 stdio-loop session 提供查询能力；xcov 作为 coverage stateful backend；其他 xverif 工具（xbit/xentry/xloc/xberif/xsva）以 stateless CLI adapter 方式接入。

MCP client 配置示例（direct 模式）：

```json
{
  "mcpServers": {
    "xverif": {
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

可用 xdebug MCP tools（以 `xverif_` 前缀统一命名）：

- `xverif_debug_session_open`：打开命名 session。
- `xverif_debug_session_list`：列出管理的 session。
- `xverif_debug_session_close`：关闭 session 并清理。
- `xverif_debug_query`：通过 loop session 调用 xdebug action。
- `xverif_debug_request`：一次性 raw JSON request（无 session）。
- `xverif_debug_actions` / `xverif_debug_schema`：查询 action catalog 和 schema。
- `xverif_wave_value_at`、`xverif_design_trace_driver` 等高频别名。

#### MCP LSF backend

LSF 模式将 `XVERIF_MCP_BACKEND` 设为 `lsf`：

```json
"XVERIF_MCP_BACKEND": "lsf",
"XVERIF_LSF_SESSION_QUEUE": "interactive"
```

LSF backend 的链路是：

```text
AI MCP client
  -> xverif-mcp FastMCP server
  -> McpSessionManager
  -> LsfLauncher: bsub -I tools/xdebug --stdio-loop
```

每个 session 一个独立 LSF job（不是 router + per-session TCP endpoint 的两层架构）。不同 session 并行，同一 session 串行（request_lock）。

常用环境变量：

| 变量 | 作用 |
| --- | --- |
| `XVERIF_MCP_BACKEND=lsf` | 启用 LSF backend |
| `XVERIF_LSF_BSUB` | 覆盖 `bsub` 命令，便于站点 wrapper 或测试 fake runner |
| `XVERIF_MCP_TIMEOUT_SEC` | 单次请求超时（默认 120s） |
| `PYTHON` | 指定运行 MCP/loop wrapper 的 Python，建议使用 Python 3.11+ |
| `XVERIF_HOME` | 指向仓库根目录，便于计算节点找到 `tools/xdebug` |

本地开发可用 fake LSF 跑 smoke，不需要真实 LSF：

```bash
PYTHON=python3 XVERIF_MCP_FAKE_LSF=1 tools/xverif-lsf-doctor --fake
```

真实环境建议先跑：

```bash
PYTHON=python3 tools/xverif-lsf-doctor
```

如果用户明确说”LSF 计算节点只能集群内部 TCP，登录机不能直连计算节点端口”，MCP 场景优先用 `XVERIF_MCP_BACKEND=lsf`。如果不能使用 MCP SDK，但仍希望由 Python wrapper 维护 LSF `--stdio-loop` session，使用 `tools/xverif-loop-server` / `tools/xverif-loop-client` 和 `XVERIF_LOOP_BACKEND=lsf`。如果不用 MCP/loop wrapper、只走 xdebug 原生命令，则优先使用上面的 `transport:”file”`。

非 MCP UDS wrapper 示例：

```bash
XVERIF_LOOP_BACKEND=lsf XVERIF_LOOP_SOCKET=/tmp/xverif-loop.sock tools/xverif-loop-server

tools/xverif-loop-client --socket /tmp/xverif-loop.sock --json \
  '{"id":"1","method":"debug.session.open","params":{"name":"s0","fsdb":"waves.fsdb"}}'
```

重复调试建议先打开 session，再用 `target.session_id` 访问：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "case_a"
  }
}
```

同名 `session.open` 永远不会复用或替换旧 session。已有 live session 时返回 `SESSION_ID_EXISTS`；已有 stale session 时返回 `SESSION_STALE`，需要显式 `session.close` 或 `session.gc` 后再重新 open。session name 必须以英文字母开头，只能包含英文、数字和下划线，最大 64 个字符。

## Test Entry Points

xdebug 测试入口以 Makefile 聚合 target 和 pytest marker 为主，Python 解释器可通过
`PYTHON=/path/to/python` 覆盖。

常用入口：

```bash
make -C xdebug test-fast
make -C xdebug test-synthetic
make -C xdebug test-vip
make -C xdebug test-session
make -C xdebug test-mcp-direct
make -C xdebug test-mcp-fake-lsf
make -C xdebug test-realdata-smoke
make -C xdebug test-regression
make -C xdebug test-nightly
```

在 Codex 受限沙箱中，只建议直接运行不启动 NPI/EDA/session 子进程的基础入口，例如
`test-fast`。所有涉及 NPI、Verdi/VCS、FSDB、daidir、`session.open`、Unix domain
socket、SVT VIP 编译/仿真的入口，应在沙箱外运行，否则可能得到 license 连接失败、
UDS bind 失败或 `SESSION_UNHEALTHY: child_exited` 等环境型失败。

`test-regression` 不包含真实 LSF。`test-nightly` 默认也不会强制真实 LSF；只有显式
设置 `XDEBUG_ENABLE_REAL_LSF=1` 时才追加 real LSF smoke：

```bash
XDEBUG_ENABLE_REAL_LSF=1 make -C xdebug test-mcp-real-lsf
XDEBUG_ENABLE_REAL_LSF=1 make -C xdebug test-nightly
```

真实项目 FSDB/daidir 通过 `xdebug/tests/realdata/manifests/*.yaml` 描述，Python
测试代码不硬编码项目路径。realdata 使用 invariant 检查，不做完整 JSON golden。

## Core Concepts

### 资源与 fallback

xdebug 当前只支持两类输入资源：

- `daidir`：Verdi/VCS 设计数据库，例如 `simv.daidir`。
- `fsdb`：FSDB 波形数据库，例如 `waves.fsdb`。

`target` 决定路由：

| target | 行为 |
| --- | --- |
| 仅 `daidir` | 使用设计侧能力，覆盖原 xtrace 的 driver/load/graph/path/source 等事实查询 |
| 仅 `fsdb` | 使用波形侧能力，覆盖原 xwave 的 value/event/APB/AXI/verify 等事实查询 |
| 同时有 `daidir` 与 `fsdb` | 启用 combined/debug join 能力，把波形现象连接到设计因果 |

### Session Transport：UDS、TCP 与 file

xdebug session 默认使用本机 Unix domain socket：

```json
{
  "transport": "uds"
}
```

同一台机器上的普通调试优先使用默认 UDS。只有 socket 路径不可共享、容器或 namespace 隔离导致 UDS 不可达、或确实需要跨进程边界连接 daemon 时，才显式使用 TCP。

如果问题是“本机无法连接集群计算节点 TCP 端口”，不要用 TCP 直连；改用 `transport:"file"`，让计算节点上的 daemon 通过共享 session 目录交换请求。

本机 TCP session 示例：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "wave_tcp",
    "transport": "tcp",
    "bind_host": "127.0.0.1",
    "port": 0
  }
}
```

`port:0` 或省略 `port` 表示由 daemon 自动分配端口；实际 endpoint 会写入 session endpoint/registry，后续查询继续通过 `target.session_id` 复用即可。远程或跨容器场景下，`bind_host` 是 daemon listen 地址，`host` 是 client 连接时使用的地址；只有用户明确需要远程访问时才设置公网或非 loopback 地址。

file session 示例：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "wave_file",
    "transport": "file"
  }
}
```

`XDEBUG_TRANSPORT=uds|tcp|file` 只影响新建 session；JSON 中显式的 `args.transport` 或 `target.transport` 优先级更高。

跨登录机和计算节点访问同一个共享路径时，`stat()` 返回的 `dev/inode` 可能不同。xdebug 只把 `dev/inode` 作为 endpoint/fingerprint 诊断信息记录，资源 freshness 判定只使用 `mtime + size`；因此这类共享挂载差异不会单独触发 session unhealthy 或自动 restart。

### JSON envelope

所有请求统一使用这个 envelope：

```json
{
  "api_version": "xdebug.v1",
  "request_id": "optional-id",
  "action": "trace.driver",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {},
  "limits": {},
  "output": {
    "verbosity": "compact",
    "pretty": false
  }
}
```

### 输出档位

`output.verbosity` 默认是 `compact`：

| verbosity | 用途 |
| --- | --- |
| `compact` | 默认，只返回 AI 下一步决策需要的摘要、证据、少量 examples、关键 graph/path |
| `full` | 兼容旧脚本或人工查看完整 payload |
| `debug` | 诊断 session、daemon、内部过程和截断原因 |

compact 默认不返回大字段，例如 `expanded_queries`、`raw_edges`、`all_samples`、`all_events`、`all_changes`、`normal_transactions`、`timeline`、`source_text`、`module_body`。需要时用精确 `include_*` 开关，不要一开始请求 `debug`。

### 常见意图到 action

| 意图 | 推荐 action | 说明 |
| --- | --- | --- |
| 统计 high/active cycles | `signal.statistics` | 有 `clock` 时做 clock-sampled 统计；无 `clock` 时做 raw value-change 统计，并返回 `sampling_mode`。 |
| 看跳变时间线 | `signal.changes` | compact 默认只返回 summary；需要行时设置 `include_rows:true`，用 `mode:"head"` 或 `"tail"` 控制方向。 |
| 判断窗口内保持 0/1 | `window.verify` 或 `signal.statistics` | 不要用 `signal.changes` 的 row count 当周期数。 |
| 找 first/last occurrence | `event.find`，或 `signal.changes` + `mode:"head"/"tail"` | `signal.changes aggregate_only:true` 适合先看首末值和跳变总数。 |

`signal.changes.summary.transition_count` 为兼容保留；新代码同时返回 `returned_change_rows`、`includes_initial_value`、`actual_transition_count` 和 `semantic_note`，优先读这些字段判断语义。

### include 开关与限制

设计侧常用开关：

```json
{
  "args": {
    "include_source": true,
    "include_ast": true,
    "include_candidates": true,
    "include_trace": true,
    "include_expanded_queries": true,
    "include_raw_edges": true,
    "include_graph": true,
    "include_debug": true
  }
}
```

波形侧常用开关：

```json
{
  "args": {
    "include_raw": true,
    "include_signal_meta": true,
    "include_rows": true,
    "include_samples": true,
    "include_all_changes": true,
    "include_transactions": true,
    "include_beats": true,
    "include_accesses": true,
    "include_debug": true
  }
}
```

通用限制：

```json
{
  "args": {
    "max_items": 20,
    "max_examples": 5
  },
  "limits": {
    "max_rows": 1000,
    "max_events": 1000,
    "max_samples": 1000000
  }
}
```

### TimeSpec

波形相关动作的时间字段接受 TimeSpec 字符串。常见形式：

```text
100ns
10us
@deadlock
@deadlock-20ns
@deadlock+5ns
@deadlock-10cycle(top.clk)
@deadlock+5posedge(top.clk)
```

绝对时间支持 `us`、`ns`、`ps`、`fs`。使用 cursor 时，优先让 xdebug 解析 `@name` 和 cycle offset，不要在 agent 里自己重算波形时间。

## Main Workflows

### 设计因果：driver / graph / path

先用外部 `rg` 或源码索引找候选信号名，再把精确 RTL path 交给 xdebug 查询。

查询 driver：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.driver",
  "target": {"daidir": "simv.daidir"},
  "args": {"signal": "top.u.ready"}
}
```

查询依赖图：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.graph",
  "target": {"daidir": "simv.daidir"},
  "args": {
    "signal": "top.u.ready",
    "direction": "driver"
  },
  "limits": {
    "max_depth": 3,
    "max_results": 80
  }
}
```

查询路径：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.path",
  "target": {"daidir": "simv.daidir"},
  "args": {
    "from_signal": "top.u.full",
    "to_signal": "top.u.ready"
  },
  "limits": {
    "max_depth": 5,
    "max_paths": 10
  }
}
```

### 波形取证：value / batch / verify

查询单点值：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {"session_id": "case_a"},
  "args": {
    "signal": "top.u.valid",
    "time": "100ns",
    "format": "hex"
  }
}
```

批量查询同一时间的多个信号：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {"session_id": "case_a"},
  "args": {
    "time": "100ns",
    "signals": ["top.u.valid", "top.u.ready", "top.u.data"],
    "format": "hex"
  }
}
```

`value.batch_at` 对部分信号缺失仍返回整体 ok，并在 `summary.missing_by_reason` 和每个 row 的 `status/reason/suggested_next_actions` 里说明原因。常见状态包括 `signal_not_found`、`not_dumped_or_unreadable`、`time_out_of_range`、`unsupported_format`。

unpacked/聚合数组可显式请求结构化显示：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {"session_id": "case_a"},
  "args": {
    "signal": "top.u.array_sig",
    "time": "100ns",
    "format": "array_indexed"
  }
}
```

返回会保留 raw value，并按 FSDB 打印顺序给出 `elements` 和 `by_index`。普通 scalar 请求该格式时返回 `unsupported_format` 诊断。

需要把波形值交给 xbit 切字段时，显式传 `slice_hint`：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {"session_id": "case_a"},
  "args": {
    "signal": "top.u.data",
    "time": "100ns",
    "format": "hex",
    "slice_hint": {"chunk_width": 32, "count": 4}
  }
}
```

响应里的 `data.xbit_hints.commands[]` 是可直接用 `tools/xbit` 执行的确定性 slice 命令。

验证条件：

```json
{
  "api_version": "xdebug.v1",
  "action": "verify.conditions",
  "target": {"session_id": "case_a"},
  "args": {
    "time": "100ns",
    "conditions": [
      {"signal": "top.u.valid", "op": "==", "value": "1"},
      {"signal": "top.u.ready", "op": "==", "value": "0"}
    ]
  }
}
```

### 生成 nWave signal.rc：rc.generate

`rc.generate` 从 JSON 配置生成 nWave `signal.rc`。配置中信号路径使用点分层次，xdebug 会校验信号存在于 FSDB，并在生成 rc 时转换成 `/top/u/sig` 风格路径。该 action 只生成 signal list/view rc，不写 `openDirFile` / `activeDirFile`，打开 FSDB 仍由 nWave 会话或外部脚本负责。语法背景见 [signal_rc_syntax.md](../doc/signal_rc_syntax.md)。
对于 `top.u.bus[15:0]` 这类 slice，校验会先查完整路径；若 FSDB 不接受 slice handle，则回退校验 base signal `top.u.bus` 是否存在。

请求：

```json
{
  "api_version": "xdebug.v1",
  "action": "rc.generate",
  "target": {"session_id": "case_a"},
  "args": {
    "config_path": "wave_view.json",
    "rc_path": "signal.rc",
    "include_preview": true
  }
}
```

配置示例：

```json
{
  "file_time_scale": "1ns",
  "window_time_unit": "1ns",
  "cursor": "120ns",
  "main_marker": "120ns",
  "zoom": {"begin": "0ns", "end": "500ns"},
  "groups": [
    {
      "name": "Analog",
      "signals": [
        {
          "path": "top.u_adc.sample[11:0]",
          "waveform": "analog",
          "height": 40,
          "analog": {"display_style": "pwl", "grid_x": true, "grid_y": true}
        }
      ]
    },
    {
      "name": "AXI",
      "subgroups": [
        {
          "name": "AW",
          "signals": ["top.u_axi.awvalid", "top.u_axi.awready"],
          "expr_signals": [
            {
              "name": "aw_fire",
              "bit_size": 1,
              "notation": "UUU",
              "expr": "$valid & $ready",
              "signals": {
                "valid": "top.u_axi.awvalid",
                "ready": "top.u_axi.awready"
              }
            }
          ]
        }
      ]
    }
  ],
  "user_markers": [
    {"name": "reset_done", "time": "120ns", "color": "ID_YELLOW5", "linestyle": "solid"}
  ]
}
```

校验失败时默认不写 rc；确实需要生成草稿时传 `allow_invalid:true`，并检查响应里的 `warnings` 和 `data.validation`。

### 协议与事件：event / APB / AXI

`event.find` 查 first/last/all occurrence。已有 event config 时传 `name`；临时查询可直接传 `expr` + `clk` + `signals`，不会留下持久 event config：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.find",
  "target": {"session_id": "case_a"},
  "args": {
    "expr": "valid && !ready",
    "clk": "top.clk",
    "signals": {
      "valid": "top.u.valid",
      "ready": "top.u.ready"
    },
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "mode": "last"
  }
}
```

`mode` 可为 `first`、`last` 或 `all`。`last` 会按 `scan_limit` 或 `limits.max_rows` 扫描后返回最后一个匹配点。

导出事件默认只返回聚合信息和少量 examples。完整 rows 必须显式请求：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {"session_id": "case_a"},
  "args": {
    "name": "if0",
    "expr": "valid && !ready",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    }
  },
  "limits": {
    "max_events": 1000
  }
}
```

需要 rows：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {"session_id": "case_a"},
  "args": {
    "name": "if0",
    "expr": "valid && ready",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "include_rows": true
  },
  "limits": {
    "max_rows": 1000
  }
}
```

APB/AXI 查询应先加载对应配置，再执行 `apb.query`、`axi.query` 或分析动作。compact 默认优先返回 error/slow/high-latency/outstanding finding，而不是所有正常 transaction/beat。

APB 配置的基础字段为 `paddr/pwdata/prdata/pwrite/penable/psel/clk/rst_n`。
真实 APB3/APB4 波形建议同时配置可选的 `pready` 和 `pslverr`：

- 配置 `pready` 后，xdebug 只在 access phase 完成时记录一笔 transfer，
  wait-state 周期不会被重复计数。
- 配置 `pslverr` 后，transaction 输出包含 `has_error`。
- 旧配置不带这两个字段仍可使用，但不能可靠区分 wait-state 或报告 slave
  error response。

### 联合定位：trace.active_driver

当同时有 `daidir` 和 `fsdb` 时，用 `trace.active_driver` 把“某时刻波形值”连接到“当前生效的设计驱动证据”：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {
    "signal": "top.u.ready",
    "requested_time": "120ns",
    "include_control": true
  }
}
```

推荐 debug flow：

1. 用 `value.at` 或 `event.export` 找到异常时间。
2. 用 `value.batch_at` 取相关握手、状态、数据寄存器。
3. 用 `trace.driver` 或 `trace.graph` 查设计依赖。
4. 如果两类资源都有，用 `trace.active_driver` 给出当前时间点的生效驱动。
5. 只有当 compact 证据不足时，再打开 `include_source`、`include_trace`、`include_rows` 等细节。

## 错误、截断与证据

常见错误码：

- `MISSING_FIELD`
- `UNKNOWN_ACTION`
- `INVALID_TARGET`
- `SESSION_NOT_FOUND`
- `SIGNAL_NOT_FOUND`
- `TIME_SPEC_INVALID`
- `WAVE_QUERY_FAILED`
- `INTERNAL_ENGINE_FAILED`
- `INTERNAL_ERROR`

所有脚本必须先检查 `ok`。失败时读取 `error.code` 和 `error.message`，不要解析 stderr 或人类文本。

`meta.truncated=true` 表示结果被主动截断。优先缩小查询范围或提高 `limits`；只有确实需要证明明细时才打开对应 `include_*`。

compact payload 优先返回 evidence，而不是大段源码：

```json
{
  "evidence": {
    "file": "rtl/foo.sv",
    "line": 123
  }
}
```

## 日志与排障

xdebug 默认静默记录结构化日志。日志只写文件，不打印到 stdout/stderr，不改变 JSON API 响应；日志写入失败也不会影响 action 执行。

主要位置：

- public action：`~/.xdebug/sessions/<session_id>/logs/actions.ndjson`
- stdio-loop 协议：`~/.xdebug/sessions/<session_id>/logs/stdio.ndjson`
- 无 session 或解析失败：`~/.xdebug/sessions/adhoc/logs/actions.ndjson`
- engine lifecycle：`~/.xdebug/engine/sessions/<hashed-session>/logs/lifecycle.ndjson`
- engine transport：`~/.xdebug/engine/sessions/<hashed-session>/logs/transport.ndjson`
- engine crash marker：`~/.xdebug/engine/sessions/<hashed-session>/logs/crash_marker.ndjson`
- log health：各 `logs/` 目录下的 `log_health.ndjson`
- MCP session：`~/.xverif/mcp/sessions/<alias>/session.ndjson`
- MCP stdio：`~/.xverif/mcp/sessions/<alias>/stdio.ndjson`
- MCP LSF：`~/.xverif/mcp/sessions/<alias>/lsf.ndjson`

每行都是一个 JSON event，常见字段包括 `ts`、`event_id`、`trace_id`、`request_id`、`layer`、`component`、`session_id`、`action`、`phase`、`elapsed_ms`、`ok`、`context`。成功 action 默认只记录摘要、路由、耗时和 `summary/meta`；失败 action 会额外记录裁剪后的 request/response。超大 compact payload 会写入 `logs/*_payload/` sidecar，主日志保留路径和 hash。

engine 启动时会在 `lifecycle.ndjson` 写入 `env.snapshot`，记录 hostname、cwd、argv0、构建时间、EDA/LSF 环境摘要，以及 `LD_LIBRARY_PATH` hash；路径字段受 `XDEBUG_LOG_PATH_MODE` / `XDEBUG_LOG_REDACT` 控制。

辅助命令：

```bash
xdebug log doctor --session <id> --json
xdebug log tail --session <id> --lines 40
xdebug log bundle --session <id> --out debug_bundle.tgz
xdebug log bundle --session <id> --out debug_bundle.redacted.tgz --redact
```

可选环境变量：

- `XDEBUG_LOG_PATH_MODE=full|basename|hash` / `XDEBUG_LOG_REDACT=1`：控制日志路径字段脱敏。
- `XDEBUG_LOG_MAX_BYTES` / `XDEBUG_LOG_MAX_FILES`：启用单文件大小滚动。
- `XVERIF_MCP_LOG_DIR`：覆盖 MCP structured log 根目录，默认 `~/.xverif/mcp`。
- `XVERIF_LOOP_LOG_DIR`：覆盖非 MCP UDS wrapper structured log 根目录，默认 `~/.xverif/loop-wrapper`。

定位工具问题时推荐顺序：

1. 先看 public `actions.ndjson`，确认 action、session、路由和最终 error。
2. 如果 stdout 协议、ready 前退出、invalid JSON 或 MCP envelope 异常，看 `stdio.ndjson`。
3. 如果是 `session.open`、`SESSION_UNHEALTHY` 或 `INTERNAL_ENGINE_FAILED`，再看 engine `lifecycle.ndjson`。
4. 如果怀疑 socket/TCP/ping/daemon 连接问题，看 `transport.ndjson`。
5. 如果是 MCP/LSF 启动、ready timeout、stdout pollution 或 cleanup 问题，看 `~/.xverif/mcp/sessions/<alias>/*.ndjson`。
6. 如果是非 MCP UDS wrapper 的请求解析、socket、LSF 或 cleanup 问题，看 `~/.xverif/loop-wrapper/logs/uds.ndjson` 和 `~/.xverif/loop-wrapper/sessions/<alias>/*.ndjson`。

日志相关快速回归入口：

```bash
make -C xdebug log-test
```

## 参考文档

- [docs/JSON_API.md](docs/JSON_API.md)：JSON envelope、target、输出策略。
- [docs/PAYLOAD_COMPACT.md](docs/PAYLOAD_COMPACT.md)：业务 payload 压缩契约。
- [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)：面向 agent 的最短调试指南。
- [skill/SKILL.md](skill/SKILL.md)：Codex skill source-of-truth。
- [skill/references/json-api-reference.md](skill/references/json-api-reference.md)：skill 内 API 速查。
- [skill/references/ai-response-dictionary.md](skill/references/ai-response-dictionary.md)：skill 内响应字段字典。
- [skill/references/recipes.md](skill/references/recipes.md)：常见 debug workflow。
- [skill/references/lsf-mcp.md](skill/references/lsf-mcp.md)：MCP LSF backend 说明。
- [skill/references/file-transport.md](skill/references/file-transport.md)：LSF/file transport v2 说明。
- [skill/references/rc-generate.md](skill/references/rc-generate.md)：nWave `signal.rc` 生成说明。
