# xdebug 架构说明书维护日志

## 2026-07-16

- 建立分析缓存 Phase 0 test-only probe、APB/AXI/stream size estimator 与 nightly
  `xdebug.analysis_cache_benchmark`，固化独立 engine 的 cold/hot、scanner、RSS、
  estimated bytes 和 stream compact JSON/XOUT golden。
- 基于 AXI stress 与 20,000-transfer stream 实测冻结 estimator safety factor 2.0、
  soft 1 GiB、hard 2 GiB，以及后续 repository/columnar/cache 阶段的性能和内存门槛。
- Phase 0 不改变 public action、schema、扫描范围、排序或输出；AnalysisRepository
  仍按独立计划后续实施。
- 完成 Phase 1 engine-owned `AnalysisRepository`：strict soft/hard 环境合同、2.0
  safety-factor accounting、typed canonical store、独立 lazy index、index-first 纯 LRU、
  building/ready 回滚、oversize、hard-limit/bad_alloc 和 generation cursor。
- stream config replace 改为同目录 temp + fsync + atomic rename，并仅在成功后以忽略
  name/description 的语义 fingerprint 通知 repository；同语义复用，差异语义失效。
- 完成 Phase 2 AXI repository 迁移：保留既有 `AxiTransactionTracker`/`AxiResult` 和
  输出顺序，所有 AXI action 复用单次 canonical scan；address、ID、handshake index
  独立 lazy build，cursor 按 generation 在 soft LRU 重建后续用。
- AXI 扫描与 index 构建纳入 working-set/hard-limit accounting，best-effort bad_alloc
  转换为结构化内存错误；由 AXI response schema 生成器统一发布预算错误字段。

## 2026-07-14

- 新增 `apb.statistics` / `axi.statistics`，基于 canonical 协议缓存按方向、AXI ID 与
  exact/range/mask 地址过滤统计 completed transaction；补齐 APB scan diagnostics，
  XOUT 固定解释 `unresolved_transaction_count`，避免 AI 猜测字段语义。
- 删除 Stream `data_fields` 配置和 runtime 兼容路径，命名逐拍字段统一使用
  `beat_fields`；inline schema 与 config file parser 均明确拒绝旧字段。
- 为 `stream.query` 增加扫描期多字段 exact/range/mask 过滤，data、beat 和
  packet-stable 字段在过滤视图内统一；packet 按 SOP/EOP 边界匹配并返回整包。
- 抽取通用任意位宽 value filter helper，Stream、APB statistics 和 AXI
  statistics 共用 literal 解析、三态 AND 与 mask/XZ 判断。

## 2026-07-07

- 初始化 `doc/agents/xdebug/` 说明书目录。
- 建立入口页、架构分层、action 开发、统一组件、通信协议、log、session、schema 校验、编码要求和测试矩阵。
- 根目录 `AGENTS.md` 引用本说明书，要求 xdebug 架构和 action 相关变更同步维护。

## 2026-07-09

- xverif skill 拆分为 `xverif-cli` 和 `xverif-mcp` 后，更新 `action-development.md` 的 skill 同步清单。
- 新增/修改 xdebug action 时，需要同时检查 CLI JSON envelope 文档和 MCP tool 参数壳文档是否需要同步。

## 2026-07-09

- 执行 xdebug 错误反馈、输出合同与表达式统一计划后，同步更新说明书中的 public 参数词典和错误提示要求。
- `schema-validation.md`、`coding-standards.md`、`action-development.md` 改为使用 `line_limit`、`args.output.verbose` 和 export action 描述大结果控制，移除旧 public `include_*` / 裸 `limit` 说法。
- skill 文档同步强调 `INVALID_TIME`、`correct_example`、`next_actions` 等结构化错误字段优先用于修复下一次请求。

## 2026-07-10

- xdebug/xcov MCP SDK 与 SDK-free wrapper 统一为 managed open/list/doctor/close/kill/gc 生命周期，backend 差异由 capability 表描述。
- 增加 tombstone、compact/verbose public record、固定 xdebug native admin path、xcov loop-owned cleanup 和 coverage native lifecycle guard。
- `actions` 默认返回 compact names，verbose 返回 descriptors；batch 汇总 failed indexes/codes/layers，unknown action 返回相近候选。
- 2026-07-14：收紧 P2 合同：`apb.query` 默认读写混合时间序列；Stream 使用
  `packet_stable_fields` 和 complete/partial packet 计数；`actions` catalog 增加
  category/requires/purposes/双语 keyword 过滤并移除 status 过滤；action 双语描述与
  purposes 统一由 `actions.yaml` 生成。
