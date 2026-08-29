# xdebug 测试计划落地状态

更新时间：2026-06-19

本文记录 `TEST_PLAN.md` 的当前实现状态。测试计划仍是目标和设计依据；本文只记录
已经落地的入口、提交和验证结果，便于后续继续维护。

## 已落地范围

| 范围 | 状态 | 主要提交 |
| --- | --- | --- |
| 完整测试规划文档 | 已落地 | `fff8116` |
| pytest runner、normalize、artifact 基础设施 | 已落地 | `d328a1b`, `919bedf` |
| CLI / action / schema / examples / xout / JSON 合同 | 已落地 | `b7d3786` |
| 现有 synthetic 设计、波形、combined 回归接入 | 已落地 | `99936a2` |
| session / stdio-loop 生命周期 | 已落地 | `18192ea` |
| MCP direct 与 fake LSF 全链路 | 已落地 | `30505cc` |
| AXI SVT VIP 真实波形环境 | 已落地 | `635907a` |
| APB SVT VIP 真实波形环境 | 已落地 | `fa61679` |
| active trace 高风险语义回归 | 已落地 | `259c999`, `aeb1428` |
| realdata manifest 回归入口 | 已落地 | `766fd02` |
| nightly 与可选 real LSF 入口 | 已落地 | `d1406bf` |
| file transport session 链路 | 已落地 | `6cf246b` |
| batch 行为合同 | 已落地 | `50d89a2` |
| MCP 与 CLI normalized JSON 一致性 | 已落地 | `e69245d` |
| direct UDS timeout 合同 | 已落地 | `6ee7150` |
| session registry 容错合同 | 已落地 | `da981f3` |
| C++ header 依赖追踪 | 已落地 | `4c00d24` |

## 当前测试入口

- `make test-infra`
- `make schema-test`
- `make unit-test`
- `make contract-test`
- `make pytest-contract`
- `make test-synthetic`
- `make test-session`
- `make test-mcp-direct`
- `make test-mcp-fake-lsf`
- `make test-realdata-smoke`
- `make test-regression`
- `make test-vip`
- `make test-nightly`
- `make test-mcp-real-lsf`：可选 real LSF，需设置 `XDEBUG_ENABLE_REAL_LSF=1`

## 最近完整验证

已执行并通过：

```bash
PYTHON=python3 make clean all
PYTHON=python3 make test-regression
PYTHON=python3 make test-nightly
```

`test-nightly` 覆盖：

- test-infra
- schema/example validation
- C++ unit tests
- runtime action/schema contract
- pytest contract
- existing synthetic regression
- combined active semantics
- session / stdio-loop
- MCP direct
- MCP fake LSF
- realdata smoke
- AXI SVT VIP real waveform
- APB SVT VIP real waveform

real LSF 仍按计划作为可选项；未设置 `XDEBUG_ENABLE_REAL_LSF=1` 时，
`test-nightly` 会明确输出跳过提示。

### 2026-06-19 本轮复核

本轮继续验证了当前 HEAD 的分层入口：

```bash
PYTHON=python3 make test-fast
PYTHON=python3 make test-synthetic
PYTHON=python3 make test-session
PYTHON=python3 make test-mcp-direct
PYTHON=python3 make test-mcp-fake-lsf
PYTHON=python3 make test-realdata-smoke
PYTHON=python3 make test-vip
```

其中 `test-fast` 可在普通沙箱内运行；所有需要 NPI、Verdi/VCS、FSDB、daidir、
`session.open` 子进程、Unix domain socket 或真实 VIP 编译/仿真的入口，必须在
Codex 沙箱外运行。沙箱内运行这些入口时会出现 license 连接、UDS bind 或
`SESSION_UNHEALTHY: child_exited` 之类的环境型失败，不应据此判断 xdebug 功能回归。

## 维护要求

后续新增 xdebug action、schema、example、MCP wrapper 或 session transport 时，应同步：

1. 更新 action/schema/example 合同测试。
2. 给新增功能至少补 contract 或 synthetic 测试。
3. 若涉及真实 FSDB、daidir、APB、AXI 或 active trace，补 synthetic/realdata invariant。
4. 若涉及 MCP，补 direct 和 fake LSF 链路测试。
5. 按阶段提交并推送远端；每个阶段提交信息写清楚覆盖范围和验证命令。
