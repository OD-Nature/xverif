# AGENTS.md

本文件是本仓库的 agent 工作规则入口。所有 agent 先读本文件，再按任务读取更细的外部材料。

## 基本沟通

- 必须使用中文和用户沟通。
- 回答要直接、具体、证据驱动；不把猜测当事实。
- 当结论依赖仓库状态、schema、测试输出或环境行为时，先检查真实文件和命令结果。
- 用户明确要求实现时，直接完成实现、验证和交付说明；用户要求计划、评审或只读探索时，不越界修改。

## 执行前确认

- 除非用户明确要求直接执行，否则每次执行前至少给出三个可选方案，并交由用户选择。
- 计划阶段和实现阶段必须分清：计划阶段不修改 repo；实现阶段按已确认计划落地。
- 如果用户已经明确给出 `PLEASE IMPLEMENT THIS PLAN`、`开始实现`、`提交`、`推送` 等指令，可按该指令执行，不再重复询问同一决策。

## 权限与环境

- 所有 NPI、VCS 仿真、VIP、真实 license、真实 LSF、真实 EDA 工具动作，默认在沙箱外运行。
- 遇到进程通信、网络端口、文件系统、license、UDS/TCP/file transport、MCP stdio-loop 等问题，先判断是否为沙箱差异，再判断产品、SDK 或代码问题。
- 沙箱内失败不能直接当作产品回归；需要时做 sandbox-vs-host 对照，并在结果里说明执行位置。
- 不打印 access token、refresh token、cookie、完整唯一 ID 或其它敏感凭据。

## Fallback 规则

- 除非用户明确要求，不允许私自 fallback。
- 如果确实需要 fallback，必须先向用户说明原因、风险和替代路径，并等待确认。
- 不能因为某个环境动作失败就静默切换 transport、后端、数据源、测试层级或工具入口。

## Git 规则

- git commit 信息必须使用中文，并写清楚动机、范围和验证情况。
- 提交前必须运行 `git status --short`，确认只包含本次相关文件。
- 不使用 `git add .` 盲目打包；优先显式列文件，或在只提交已跟踪改动时使用 `git add -u`。
- 不回滚用户或其它进程产生的无关改动。
- 用户要求推送远端时，提交后推送当前目标分支，并回报 commit id 和推送结果。

## 项目概述

`xverif` 是面向芯片验证工作的工具集合，提供 debug、coverage、bit 计算、日志定位、协议/断言辅助和 agent/MCP 集成能力。

- `xdebug/`：统一的设计数据库、波形数据库和 combined debug 查询工具，提供 JSON action、schema、session、engine、log、transport 和测试体系。
- `xcov/`：coverage database 查询与报告工具，面向 VCS/Verdi coverage 数据。
- `xbit/`：确定性 bit、SystemVerilog literal、slice、mask 和表达式计算工具。
- `xentry/`：entry、descriptor、header、fragment 等结构化字段解析工具。
- `xloc/`：压缩日志位置 ID 与源码位置之间的还原、统计和标注工具。
- `xsva/`：SVA 解析、IR 生成和语义解释工具。
- `xeda_runner/`：安全执行 make、VCS、simv、Verdi 等 EDA 命令的 runner。
- `xverif_mcp/`：把 xverif 工具暴露给 MCP client 的 server、adapter 和测试。
- `skills/`：面向 Codex/Claude 等 agent 的工具使用说明、reference、脚本和可安装 skill。
- `doc/`：项目级报告、计划、架构说明和临时交付文档。

## 测试要求

- 一旦修改源码，在提交 git 前必须把关联测试全部跑通。
- 文档-only 修改可只做内容、链接、格式和引用检查；不需要运行源码测试。
- 测试命令必须来自当前仓库的 Makefile、README、pytest 配置或脚本，不凭旧记忆猜命令。
- 如果测试因 license、EDA 环境、真实数据、LSF 或沙箱限制无法运行，必须在最终说明和提交说明中写清楚阻塞原因。

常用入口：

- 顶层常规测试：`make test`
- 顶层完整真实回归：`make full-test`
- xdebug schema/example：`make -C xdebug schema-test`
- xdebug contract：`make -C xdebug contract-test`
- xdebug C++ unit：`make -C xdebug unit-test`
- xdebug 快速组合：`make -C xdebug test-fast`
- xdebug 回归分层：`make -C xdebug test-regression`
- xdebug nightly/VIP/真实 LSF：`make -C xdebug test-nightly` 或对应 `test-vip`、`test-mcp-real-lsf`，这类动作按环境规则在沙箱外执行。
- MCP action smoke：`make -C xdebug mcp-test` 或 `make -C xdebug mcp-test-schema`
- xbit/xentry/xloc/xcov/xwaveform：优先使用各目录 Makefile 的 `test` 目标。

## xdebug 外部材料

xdebug 代码架构、添加 action 流程、统一组件、通信协议、log、session、schema 校验、编码要求和测试矩阵，维护在：

- [doc/agents/xdebug/README.md](doc/agents/xdebug/README.md)

修改 xdebug 架构、action、schema、session、transport、log、runtime 或测试体系时，必须检查该说明书是否需要同步更新。

## 环境错误复盘

每次 agent 犯环境相关错误后，必须向本文件追加一条简短复盘。格式如下：

```markdown
### YYYY-MM-DD 环境错误复盘

- 错误现象：
- 误判原因：
- 以后规则：
```

只记录对后续工作有复用价值的环境误判；不要写入 token、cookie、license 内容、完整 session id 或其它敏感信息。
