---
status: accepted
---

# 区分 nightly 的仓库可控 required 能力与外部 optional 能力

nightly 将仓库能够生成和维护合同的普通/AXI/APB VIP Fixture、NPI、direct MCP 与 fake LSF suite 设为 required；仓库外真实项目 FSDB/daidir 和 real LSF 设为 optional。required 能力或有效缓存缺失使 nightly 在 preflight 阶段 ERROR，optional 能力缺失产生带原因的 SKIP；fake LSF 只验证 fake-LSF suite，不能作为 real LSF 的 fallback 或通过证据。

## Considered Options

- 选择：仓库可控能力 required，外部项目数据与 real LSF optional。
- 拒绝：所有 nightly 扩展都 optional；会让仓库拥有生成合同的 VIP 覆盖长期缺失仍显示通过。
- 拒绝：全部 required；会把仓库无法控制的外部项目数据和本机 LSF 部署变成普遍阻断。

## Consequences

- VIP fixture cache miss 需要先显式 prepare；普通 nightly 不自动仿真，缺失时 ERROR 并给出准备命令。
- optional suite 的 SKIP 进入终端、JUnit 和 JSON 汇总，并标明 capability/fixture 原因，不能静默省略。
- 某个部署环境可以通过显式 gate policy 将 realdata/real LSF 提升为 required，但不能在 suite 内动态改变身份。
- nightly 的 PASS 必须同时报告 required 全通过和 optional PASS/SKIP 计数。
