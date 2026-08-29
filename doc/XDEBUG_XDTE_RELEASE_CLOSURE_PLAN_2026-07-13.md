# XDTE xdebug 发布闭环与可信证据优化计划

状态：已完成（2026-07-13）

## 背景与目标

XDTE 反馈中仍出现 `handshake.inspect` 将合法 `ready_without_valid`
逐拍放入 finding 的现象，但 xdebug 源码已经在 2026-07-13 实现默认
`summary` 输出。核对发现 `xdebug/xdebug` 二进制仍为 2026-07-11 构建，
不能将该反馈直接判为当前源码回归。

本计划先完成发布可追溯、session 资源身份和 XDTE 主回归的 manifest 发布，
再以新构建和新鲜 FSDB 复验已实现的公共合同。不会引入自动 retry、自动
reopen、transport/backend/data-source fallback，也不会把 class/virtual-interface
或动态 aggregate 的现有证据边界误称为已支持能力。

## 阶段与提交

### 提交一：构建身份、active-trace schema 与 catalog

- xdebug 所有响应的 `tool` 元数据保留兼容 `version`，新增 `build_id`、
  `git_revision`、`schema_revision`，由构建生成并在 CLI/MCP/session
  路径保持一致。
- 补齐 `trace.active_driver` 与 `trace.active_driver_chain` response schema、
  examples、XOUT 和 contract tests，对齐现有 `requested_time`、
  `driver_last_change_time`、`time_semantics`、`evidence_scope` 与
  `evidence_status`。
- 生成 action 索引排除已移除 `signal.search`，并校验生成索引与 runtime catalog
  的 action 集合和数量一致。

### 提交二：session 资源身份与失败诊断

- 保留 `resource_hash` 的兼容性，并明确它仅标识 canonical path。
- 新增结构化资源身份：提供 manifest 时返回 manifest digest；未提供时返回
  FSDB stat snapshot（mtime、size、dev、inode），不将路径 hash 伪装为内容 hash。
- `session.open` 失败返回脱敏、长度受限的 native/engine 摘要，并明确资源缺失、
  FSDB open 失败和 engine 启动失败；不硬编码 sidecar 名称或猜测缺失 sidecar。

### 提交三：xverif 通用 manifest helper

- 新增 CLI helper，显式接受 FSDB、可选 daidir 和输出路径；校验资源后按
  `xdebug.run-manifest.v1` 计算 digest。
- 先写临时文件再原子替换发布 `state:"published"` manifest；不等待文件稳定、
  不枚举/猜测 sidecar。
- 补 JSON shape、路径/哈希、原子发布和错误形状的纯 Python 测试。

### 提交四：XDTE `dv/cfg` 接入与实机闭环

- `ncrun` 保留 run 前 `waves.fsdb*` 清理；仅在 simv 成功退出后调用 helper，
  在 run 目录发布 `run-manifest.json`。
- 全量重建 xdebug，并重启 MCP/engine；确认返回的构建、git、schema 身份与当前
  提交一致。
- 用 `tc_rm_monitor_copy_500req_concurrent` 的新鲜产物和 manifest 复验默认
  idle summary、`intervals/all` 兼容模式、`value_format=dec`、active-trace
  时间/证据字段、manifest 成功与篡改失败、资源失败诊断。

## 验收与环境

- 静态 schema、example、catalog 与 skill 检查在沙箱内执行。
- NPI、FSDB、VCS、MCP transport 和 XDTE 仿真在 host 执行。
- 交付前 `tool.build_id/git_revision/schema_revision` 必须能区分旧二进制；
  MCP 与 CLI 身份必须一致；成功 run 后才有 manifest；同路径新资源不再只显示
  路径 hash。
- XDTE 未能由当前 FSDB 证明的 class/virtual-interface、动态数组和优化 port
  继续标为限制，优先使用 monitor/log/RM 交叉证据。

## 实施与验收记录

- 构建身份、active-trace schema/catalog 与 response examples 已落地；重建后的
  CLI 对真实请求返回当前 `git_revision` 和 actions schema 的 `schema_revision`。
- xdebug manifest helper 已由 XDTE `dv/cfg` 的 `ncrun` 成功路径调用；500-request
  回归生成 2,969,568-byte FSDB 与 `state:"published"` manifest。有效 manifest
  可打开 waveform session，篡改的 SHA-256 被 `RESOURCE_PROVENANCE_MISMATCH` 拒绝。
- 同一真实 FSDB 验证了 `handshake.inspect` 默认 `summary`、显式 `intervals` 和
  小窗口 `all` 策略；`value_format:"dec"` 可被请求并完成分析。无效 FSDB 返回
  `ENGINE_START_FAILED`，含受限长度的 native 启动摘要。
- 静态/skill 门禁通过，MCP stdio-loop host regression 通过；实机 session 已显式关闭。
