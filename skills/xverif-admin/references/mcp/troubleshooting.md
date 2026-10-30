# MCP 排障

## 日志位置

默认根目录：`~/.xverif/mcp`，可用 `XVERIF_MCP_LOG_DIR` 覆盖。

- server：`logs/server.ndjson`
- session：`sessions/<session_id>/session.ndjson`
- stdio-loop：`sessions/<session_id>/stdio.ndjson`
- LSF：`sessions/<session_id>/lsf.ndjson`

## 定位顺序

1. 工具不可见：确认连接的是当前版本 MCP server 并刷新客户端工具列表；全部工具组始终注册。工具详情用 `xverif_tool_help`，xdebug action 发现用 `xverif_tools`。
2. FastMCP/SDK 启动失败：确认 Python 3.11+ 和 `mcp[cli]<2`；当前 server 使用 1.x 的 FastMCP 接口。
3. session open 失败：看 `session.ndjson` 和 `stdio.ndjson`。
4. ready timeout/stdout pollution/backend exit：看 `stdio.ndjson`。
5. LSF job id、bsub、bkill、cleanup：看 `lsf.ndjson`。
6. xdebug backend native 问题：继续读 xdebug troubleshooting。

## 常见错误

- `SESSION_LOST`：MCP 已清理失效 session；按 `next_actions` 重新 open；若来自 graceful close，
  说明 loop 已退出，改用 `xverif_debug_session_kill`。
- `SESSION_STALE` / `SESSION_TOMBSTONE_EXISTS`：名字仍被未解决记录占用。按错误里的
  `next_actions` 调用 `xverif_debug_session_kill`（= `session_close(mode="force")`）：它终止 loop
  并在引擎不可达时退役记录（`cleanup.native_kill="retired_unreachable"`、
  `cleanup.engine_confirmation="unreachable"`，不声称引擎进程已停止），之后同名
  `xverif_debug_session_open` 可成功。也可先 `xverif_debug_session_gc`，它会对 loop 已退出的记录
  重试一次回收并发布 `retired_count`。已 `closed` 的 tombstone 不再挡名字，直接重开即可。
- session/query 在运行一段时间后自行消失，且 `scheduler.wall_time_minutes` 与存活时长接近：
  这是 LSF `-W` runtime limit（`XVERIF_LSF_SESSION_WALL_TIME_SEC`，默认 7200 秒）到期，
  LSF 终止了 job。按需调大该值；残留记录用上面的 kill/gc 流程回收。
- 同名 open 的冲突探测是有界的（内部 `limits.timeout_ms`，默认 2000ms）：`SESSION_STALE` 会在
  秒级返回，不再等 file transport 的 300s 请求超时。
- `OUTPUT_WRITE_FAILED`：检查 MCP 进程工作目录、输出父目录是否存在以及写权限。
- `OUTPUT_SERIALIZATION_FAILED`：响应不能编码为严格 JSON；写入失败不能当作调用成功。
- `BAD_JSON` 或 envelope 异常：检查 MCP tool 参数壳和 `output_format`；xdebug 原生 envelope 请改用 `xverif`。

## Coverage 工具来源校验

`EDA_PROVENANCE_INVALID` 需要按 message 区分目录/可执行文件检查与 URG 版本查询失败。
xcov 固定使用配置的 `$VCS_HOME/bin/urg -full64 -version`，不从 PATH 改选另一套工具。
版本查询失败会给出 `detail.operation=urg.version`、可用的 `detail.returncode`、缺失标识
和限长脱敏的 stdout/stderr 摘录；不要仅凭这个错误码认定缺少 license。

CLI 成功不能证明 MCP 使用相同环境。核对 MCP 实际启动脚本、工具根、解释器、VCS_HOME、
VERDI_HOME，以及站点的库/架构设置；只检查 license 变量是否设置，不打印其值。
在另一个 shell 执行 `source env.sh` 不会更新已经启动的 MCP。项目可在自己的 MCP wrapper
加载该 checkout 的环境脚本，或在启动客户端前显式加载并配置必要变量转发；改完后重新
连接客户端，让新进程继承配置。不要让通用 xverif 自动猜项目目录或 source 任意 shell 配置。

对照实验在相同主机、权限和环境下执行，保留失败输出；不因 MCP 失败自动切换 CLI、
LSF 或另一个安装。缺少历史版本查询原文时，应明确根因尚未确定，不能事后归咎于某个
未验证的环境变量。

## 客户端退出后的清理

- 正常 EOF / 正常退出：MCP lifespan 与 `atexit` 都会执行 `close_all`。
- 收到 SIGTERM：MCP server 会在有界预算内（`close_timeout + bkill_timeout`，默认 60 秒，上限
  300 秒）执行 `close_all` 再退出，日志为 `mcp.shutdown.cleanup_begin/end`；预算耗尽会记
  `mcp.shutdown.cleanup_timeout` 并强制退出。
- SIGKILL（无法捕获）：本地进程组清理不会执行，只有 LSF `-W` 能兜底回收 job；direct 模式
  依赖 loop 的 stdin EOF，detached engine 依赖 `XDEBUG_SESSION_IDLE_TIMEOUT_SEC`（默认 86400s）。

### 原生 coverage 初始化等待

`XVERIF_XCOV_NATIVE_INIT_TIMEOUT_SECONDS` 可在本机 MCP/EDA 环境设置 NPI 初始化
等待上限，默认 120 秒，必须为 `(0, 3600]` 的有限秒数；用于握手和 `init`，不会缩短
VDB 打开或其它原生 RPC 的既有 120 秒期限，也不改变 URG 的执行期限。
设置后需显式关闭已有会话并重新连接。先导出尚未保存的 exclusion reason 和 EL。

超时仍返回 `NPI_WORKER_LOST`，`detail.failure_kind=timeout`，附带 operation、
elapsed_seconds、timeout_seconds 和可用的 diagnostic_path。每个 worker 的
`native-status.json` 记录初始化/打开阶段；超时时在 Linux 上尽力记录该 worker
自身 TCP 连接的地址、端口、状态和重传数，不读取网络 payload 或许可证环境内容。
诊断写入失败不掩盖原始错误。`init` 超时可能涉及许可证和网络，不能一概判为缺 feature。

不可恢复的 RPC 失败会立即终止并回收 worker；Linux 上拥有它的 Python 进程
意外退出时，worker 也由内核终止，即使正卡在厂商初始化中。新 wrapper 与 native
worker 必须一起部署；没有自动重试、重放 mutation 或切换 backend。


### coverage worker 的站点分配器设置

共享默认不强制内存分配器，保留继承的 `VCS_USE_MALLOC`。仅当本机原生加载发生
分配器崩溃且对照确认有效时，在仓库外的 MCP/EDA 环境设置
`XVERIF_XCOV_NATIVE_USE_MALLOC=1`（仅接受 `0`/`1`）。此选项只作用于 coverage 子进程，
不改变其它 EDA 工具；非法值返回 `NPI_ALLOCATOR_INVALID`，不会自动重试或切换。
已有 worker 不受后续环境变化影响；先显式保存 CSV/EL 并关闭，再建立新会话。
普通句柄按引用计数释放，SDK 内部仍可能保留部分对象直到进程退出；长任务应有明确的会话关闭点，
不能把短会话成功视为无界内存保证或所有 Verdi 安装的通用验证。

worker 报 `NPI_SDK_MISMATCH` 时，检查 `VERDI_HOME` 与构建时的安装是否一致，
用目标安装执行 `make xcov` 后再显式重开会话；运行时不会自动编译或切换 binding。
