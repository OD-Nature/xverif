# xdebug 架构说明书维护日志

## 2026-07-11

- 增加 Verdi 2018/2023 构建 profile 骨架；2018 旧 ABI和 NPI 库目录探测集中在
  `mk/npi.mk`，现代 profile 保持上游默认 ABI。
- 增加 `core/npi/decompile_compat.h`，兼容 2018 两参数和新版五参数 decompile API。
- 修复 `unit-test`、`pytest-contract` 对实际链接/运行产物缺失的 Makefile 依赖。
- Verdi O-2018.09-SP2 环境下，当前 unified xdebug 已完成干净源码编译和 engine 链接。

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
