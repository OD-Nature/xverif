---
status: accepted
---

# 使用正交维度描述测试而非把门禁当作测试身份

xverif 的测试清单分别记录测试层级、能力域、环境依赖和成本；`fast`、`regression`、`nightly` 等门禁是对这些属性的具名查询，不是测试自身的分类。这样同一个测试可以准确表达为例如 `integration + waveform + requires_npi + slow`，避免当前 pytest markers 将合同、功能域、运行环境、成本和门禁混成一套扁平标签。

## Considered Options

- 选择：正交维度，门禁由查询定义。
- 拒绝：每个测试只归入 fast/regression/nightly 单一桶；简单但无法表达多维属性，移动门禁还会改变测试身份。
- 拒绝：各组件自行定义分类；保留局部灵活性，但顶层无法形成一致查询和报告。

## Consequences

- pytest marker、目录名和 Makefile target 不再单独充当测试分类事实源。
- 门禁可以调整选择条件而不改测试身份；同一测试可以进入多个门禁，但由统一查询解释原因。
- 清单 schema 必须区分至少四个维度：测试层级、能力域、环境依赖和成本。
