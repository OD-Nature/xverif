---
status: accepted
---

# 严格区分测试失败、环境错误、可选跳过和未选择

xverif pytest plugin 将产品断言不成立报告为 FAIL，将 required 工具、数据库 Fixture、license、进程或 transport 能力不可用报告为 ERROR；只有当前 gate 明确把 suite 声明为 optional 时才允许 SKIP，未被 gate 查询选中的 suite 报告为 DESELECT。测试代码和外部 runner 不得自行把 required 覆盖降级成 SKIP 或成功退出。

## Considered Options

- 选择：FAIL、ERROR、SKIP、DESELECT 按原因严格区分。
- 拒绝：所有环境缺失统一 SKIP；会让 required 覆盖未执行时仍出现绿色门禁。
- 拒绝：所有未完成统一 FAIL；无法区分产品回归与基础设施/资产问题，降低调试价值。

## Consequences

- gate 查询结果必须同时携带 required/optional 身份；optional 不是 suite 的永久属性。
- fixture cache miss 在普通 required gate 中是准备阶段缺失导致的 ERROR，并附显式 prepare 命令。
- pytest 自定义 item 必须在报告中保存稳定 error layer，例如 `assertion`、`fixture`、`environment`、`runner`、`timeout`。
- 旧 shell/Make runner 中的条件性 `exit 0` 和隐式 SKIP 需要逐项迁移到统一判定。
