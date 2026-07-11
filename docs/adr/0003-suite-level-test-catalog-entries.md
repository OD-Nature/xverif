---
status: accepted
---

# 测试清单以稳定 suite 为基本记录粒度

xverif 测试清单的一条常规记录对应一个可独立运行、可独立判断环境要求并可独立报告结果的稳定 suite；suite 内的普通用例继续由 pytest、unittest 或所属 runner 发现。只有环境、成本、资源或门禁归属显著不同的高成本场景才拆成独立记录，避免为每个 pytest node、参数组合和 active-trace case 维护庞大的重复清单。

## Considered Options

- 选择：稳定 suite 粒度，允许有依据的高成本子集拆分。
- 拒绝：逐测试用例建清单；选择最精细，但 node ID 与参数变化会制造大量维护噪声。
- 拒绝：沿用现有 Makefile target 粒度；实施容易，但会固化当前重叠入口和边界混乱。

## Consequences

- suite 必须拥有稳定 ID、单一执行入口和明确的结果边界。
- suite 内部用例数量可以变化，不要求同步改清单；清单报告仍可附带 runner 返回的 collected/passed/failed 数量。
- active-trace 等大规模参数集合默认由 suite 自己发现；只有运行合同不同的集合才成为另一条清单记录。
