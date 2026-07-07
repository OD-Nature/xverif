# xdebug 测试矩阵

xdebug 测试按成本和覆盖面分层。修改源码后，提交 git 前必须跑通关联测试；不能用一个宽泛测试替代更直接的 focused test。

## Schema 与 Contract

命令：

```bash
make -C xdebug schema-test
make -C xdebug contract-test
```

覆盖：

- JSON schema 文件合法性。
- request/response examples 合法性。
- action inventory 与 runtime actions 一致。
- action schema coverage。
- schema hints 和 required/anyOf 同步。

适用：

- 修改 `actions.yaml`。
- 修改 `schemas/v1/actions/`。
- 修改 examples。
- 修改 action registry、help、catalog。

## C++ Unit

命令：

```bash
make -C xdebug unit-test
```

覆盖：

- core types
- env config
- action log
- file exchange
- process runner
- session catalog
- action registry
- request contract
- text response builder
- common blocks
- logic value
- event expression
- rc generator

适用：

- 修改 C++ helper、core、response、value、event、session、process、log。

## Test Infra

命令：

```bash
make -C xdebug test-infra
```

覆盖：

- pytest runner、artifact、normalization、command helper。

适用：

- 修改 `xdebug/tests/runner/` 或测试基础设施。

## Pytest Contract

命令：

```bash
make -C xdebug pytest-contract
```

覆盖：

- CLI contract
- batch contract
- output contract
- JSON response contract
- time output contract
- unified runtime contract

适用：

- 修改 CLI/API 输出、batch、runtime contract、response shape。

## Waveform/Synthetic

命令：

```bash
make -C xdebug test-synthetic
```

或 focused：

```bash
make -C xdebug pytest-synthetic-existing
make -C xdebug pytest-counter-statistics
```

覆盖：

- 现有 synthetic waveform regression。
- counter statistics。
- active semantics。

适用：

- 修改 waveform value/event/signal/statistics/window/counter/clock sampling。

## VIP

命令：

```bash
make -C xdebug test-vip
```

覆盖：

- AXI VIP real waveform。
- APB VIP real waveform。

要求：

- 这类测试依赖真实 VIP/VCS/EDA 环境，按根目录 `AGENTS.md` 在沙箱外执行。

## Combined / Active Trace

命令：

```bash
make -C xdebug combined-test
make -C xdebug test-active-trace
```

覆盖：

- active driver fixture。
- combined design+waveform active semantics。

适用：

- 修改 `src/combined/`、active trace、design+waveform join。

## Session / Log / Transport

命令：

```bash
make -C xdebug test-session
make -C xdebug log-test
```

覆盖：

- session lifecycle。
- stdio-loop lifecycle。
- crash marker。
- UDS connect failure。
- transport log。

适用：

- 修改 session manager、transport、stdio-loop、engine lifecycle、logging。

## MCP

命令：

```bash
make -C xdebug mcp-test-schema
make -C xdebug mcp-test
make -C xdebug test-mcp-direct
make -C xdebug test-mcp-fake-lsf
make -C xdebug mcp-session-test
```

真实 LSF：

```bash
make -C xdebug test-mcp-real-lsf
```

要求：

- MCP stdio、real LSF、license/port/file-system 相关测试默认沙箱外执行。
- 如果沙箱内失败，先判断是否为 sandbox，而不是直接改代码。

## Realdata / Regression / Nightly

命令：

```bash
make -C xdebug test-realdata-smoke
make -C xdebug test-regression
make -C xdebug test-nightly
```

适用：

- 跨层行为改动。
- release 前或高风险 refactor。
- action routing、runtime、session、waveform/design combined 行为大改。

## 选择测试的规则

- 文档-only：检查链接、路径、引用和内容，不跑源码测试。
- schema-only：`schema-test`。
- public contract：`schema-test` + `contract-test`。
- C++ helper：`unit-test` + focused pytest。
- waveform action：schema/contract + focused waveform test。
- session/transport/log：session/log/MCP focused tests。
- MCP wrapper：MCP tests。
- NPI/VCS/VIP/LSF：沙箱外运行对应测试。

若测试无法运行，必须说明具体命令、失败原因、环境缺口和未覆盖风险。
