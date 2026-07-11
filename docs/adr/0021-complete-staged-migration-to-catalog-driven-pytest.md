---
status: accepted
---

# 在本次任务内分批完成全部测试编排迁移

本次测试优化必须把全仓现有 suite 全部迁移到 catalog 驱动的 pytest plugin，可以按层级、组件和环境依赖分批实现、验证和提交，但最终不得留下旧 Makefile、regression shell 或独立 pytest target 维护另一套 suite 选择、fixture prepare、SKIP 判定或结果汇总逻辑。迁移期用 collect/execution plan 与实际结果对照证明每批覆盖等价，切换完成后删除重复编排，不提供旧实现 fallback。

## Considered Options

- 选择：本次任务全量迁移，内部采用可验证的分批切换。
- 拒绝：新旧编排长期并存；会重新产生测试清单、门禁和环境合同漂移。
- 拒绝：一次性删除再重写；缺少逐批覆盖对照，难以发现 suite 丢失和结果语义变化。

## Consequences

- 计划必须列出全仓 suite inventory、迁移批次、每批 parity 证据和旧入口删除清单。
- 每批可以暂时保留尚未迁移区域的旧入口，但已迁移区域不得继续由两套编排共同拥有。
- 最终验收必须证明 catalog 覆盖所有 Python、C++、shell、Make/VCS、VIP、MCP、realdata 和 active-trace suite。
- 最终代码中允许保留 leaf runner，但它们只执行一个 suite 的业务步骤，不选择 gate、不隐式 prepare、不自行降级结果。
