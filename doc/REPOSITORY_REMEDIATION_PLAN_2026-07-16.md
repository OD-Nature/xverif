# xverif 全仓问题修复计划（2026-07-16）

本计划以 `REPOSITORY_MAINTAINABILITY_REVIEW_2026-07-16.md` 为审计依据；它是本轮整改的唯一执行基线。

## 前置规则

1. 不复用旧 goal；以本文件创建新的执行 goal。
2. 不增加 fallback、自动重试、自动改名或默认共享访问。
3. 每阶段完成定向验证、`pytest --xverif-gate fast`、`git diff --check` 后，以中文 Git commit 提交；真实 NPI/FSDB/VIP/VCS/UDS 测试只在沙箱外 host 运行。

## 阶段 1：MCP 结果可信性与退出诊断

- `xverif_output_path` 写入失败返回 `OUTPUT_WRITE_FAILED`，保留原 action 结果于 `data.result`，附带路径和安全化 I/O 错误。
- batch 的非 object `args` 写入带行号的 `INVALID_BATCH_ARGUMENTS`，不执行该 tool，继续后续行。
- `close_all` 部分失败记录 server-level 结构化 shutdown event，并继续其余 cleanup。
- 同步 MCP schema、示例、skill 与单测，覆盖落盘失败、append、batch 类型/行号、未知 tool、输出文件失败和 cleanup 异常。
- Commit：`修复 MCP 输出与批处理静默失败并补充退出诊断`。

## 阶段 2：SDK-free loop 会话、UDS 安全与分层

- 用锁和 opening reservation 保证同名并发 open 只启动一次，其余返回 `SESSION_ID_EXISTS`。
- socket bind 后强制 `0600`；仅清理当前用户拥有且确认不活动的 Unix socket；普通文件、symlink、异主路径或活动 socket 返回 `SOCKET_PATH_UNSAFE`。
- 共享错误与生命周期逻辑下沉到无 MCP 依赖层，使 `xverif_loop` 可独立安装/import。
- 删除 5 个确认无 consumer 的旧 header。
- 新增并发 open、open/close/gc race、socket mode/路径负例与隔离 import 测试。
- Commit：`加固 SDK-free 会话并发、UDS 路径安全与独立分层`。

## 阶段 3：测试可信度、fixture 可移植性与覆盖治理

- 完整删除 action return replay 的 runner、registry/testdata、专用 pytest、矩阵和引用。
- fixture 指纹纳入 effective environment、外部根解析路径与显式 manifest/version；缺失依赖在 preflight 失败。
- 扩展 ResultManager 对失败、timeout、日志、junit/report、xdist 汇总的测试。
- 新增 catalog 管理的 host-only 最小真实 MCP/UDS 契约：open、query、invalid、close、crash 或 timeout。
- 建立 action/主要模块到正向、参数拒绝、环境失败测试的映射清单与未映射审计。
- Commit：`重构测试门禁并校验 fixture 外部依赖身份`。

## 阶段 4：Skill 一致性、x-npi 示例与运行时打包

- `examples.yaml` 成为真实唯一事实源；生成器解析它并验证 source 改动会改变产物。
- xwiki 未授权查询仅报告建议写回，不修改 wiki。
- skill 安装改为受控 rsync 镜像、manifest 与逐 skill `diff -qr` 验收。
- 为 wave_stats、coverage_summary、trace_driver_summary 增加 fixture-backed host-only 回归；trace 输出结构化 stage、dbdir、signal、mode。
- 根包仅保留 testinfra；MCP/loop 拆为独立 runtime package，声明依赖和 entry point，并增加 clean-venv smoke。
- Commit：`统一 skill 事实源并拆分 xverif MCP 运行时打包`。

## 最终验收

- 每阶段：定向测试、fast gate、diff 检查。
- 最终：host regression、新增 host-only suite、fixture identity 和 clean-venv smoke。
- 每次提交前运行 `git status --short`，只显式暂存本阶段文件；提交信息写明动机、范围和实际验证结果。
