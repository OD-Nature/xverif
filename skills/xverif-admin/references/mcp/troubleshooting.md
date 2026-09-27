# MCP 排障

## 日志位置

默认根目录：`~/.xverif/mcp`，可用 `XVERIF_MCP_LOG_DIR` 覆盖。

- server：`logs/server.ndjson`
- session：`sessions/<session_id>/session.ndjson`
- stdio-loop：`sessions/<session_id>/stdio.ndjson`
- LSF：`sessions/<session_id>/lsf.ndjson`

## 定位顺序

1. 工具不可见：确认连接的是当前版本 MCP server 并刷新客户端工具列表；全部工具组始终注册。工具详情用 `xverif_tool_help`，xdebug action 发现用 `xverif_tools`。
2. FastMCP/SDK 启动失败：确认 Python 3.11+ 和 `mcp[cli]`。
3. session open 失败：看 `session.ndjson` 和 `stdio.ndjson`。
4. ready timeout/stdout pollution/backend exit：看 `stdio.ndjson`。
5. LSF job id、bsub、bkill、cleanup：看 `lsf.ndjson`。
6. xdebug backend native 问题：继续读 xdebug troubleshooting。

## 常见错误

- `SESSION_LOST`：MCP 已清理失效 session；重新 open。
- `SESSION_STALE`：同名 session 记录存在但进程不健康；显式 close/gc 后重开。
- `OUTPUT_WRITE_FAILED`：检查 MCP 进程工作目录、输出父目录是否存在以及写权限。
- `OUTPUT_SERIALIZATION_FAILED`：响应不能编码为严格 JSON；写入失败不能当作调用成功。
- `BAD_JSON` 或 envelope 异常：检查 MCP tool 参数壳和 `output_format`；xdebug 原生 envelope 请改用 `xverif`。


### 原生 coverage 初始化等待

`XVERIF_XCOV_NATIVE_INIT_TIMEOUT_SECONDS` 可在本机 MCP/EDA 环境设置 NPI 初始化
等待上限，默认 120 秒，必须为 `(0, 3600]` 的有限秒数；只影响 `init`，不会缩短
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
永久句柄和退出回收仍是当前原生实现的适用边界，长任务应划分明确的会话关闭点，
不能把短会话成功视为无界内存保证或所有 Verdi 安装的通用验证。
