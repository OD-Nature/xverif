---
name: xverif
description: >
  用于芯片验证中的确定性事实查询和计算：daidir/FSDB debug、coverage、
  SystemVerilog bit 计算、entry 解码、日志位置恢复、SVA 解释和波形渲染。
  先按任务选择能力，再按环境选择 MCP 或 CLI。批量 pynpi 分析用 x-npi，
  运维用 xverif-admin，执行 EDA 命令用 xeda-runner，持续知识用 xwiki。
---

# xverif

这是唯一通用隐式入口。先判断用户要解决的问题，不要先猜 CLI/MCP。

## 任务路由

| 用户意图 | 能力参考 |
| --- | --- |
| 信号、scope、driver/load、波形、协议、active driver、窗口证明 | [xdebug](references/capabilities/xdebug.md) |
| VDB coverage、hole、scope、源码 evidence | [xcov](references/xcov.md) |
| literal、slice、mask、表达式 | [xbit](references/xbit.md) |
| entry/descriptor/header fields | [xentry](references/xentry.md) |
| 恢复 `L_XXXXXXXX` 源码位置 | [xloc](references/xloc.md) |
| SVA temporal semantics | [xsva](references/xsva.md) |
| `list.export` 后渲染 JPG/stats | [xwaveform workflow](references/workflows/waveform-render.md) |
| 全量 xdebug action 的用途和合同入口 | [全量 action 索引](references/generated/xdebug-actions.md) |
| MCP/CLI 请求包装 | [surface 选择](references/core/execution-model.md) |
| 统一证据字段和 partial/truncated 处理 | [证据合同](references/core/evidence-contract.md) |
| 同一 canonical example 的三种请求包装 | [生成的 surface 示例](references/generated/surface-examples.md) |

批量 FSDB/VDB 扫描或自定义报告使用 `x-npi`；安装、LSF、transport、timeout、session 运维使用 `xverif-admin`；执行 make/VCS/simv/Verdi 使用 `xeda-runner`；项目长期知识使用 `xwiki`。

## 标准流程

真实 EDA 调用前确认 `XVERIF_EDA_PROFILE=verdi-2018|verdi-2023` 与
`VERDI_HOME` 一致；2018 xcov 走 native worker，2023 走 Python backend，不自动
fallback。

1. 明确问题和必须保留的证据。
2. 读取对应 capability/workflow；xdebug 从主流程开始，能力不足再读全量 action 索引。
3. 优先 MCP；原生 envelope、shell 或一次性脚本使用 CLI。具体包装见 surface reference。
4. 查询当前 tool/action catalog 和 action-specific schema，不猜字段。
5. 先执行最小受限查询，再根据证据扩展。
6. 输出结论、signal/path、time/range、value、file:line、action/tool、error/finding、truncated/partial 和 unknowns。

## 禁止事项

- 不把 MCP 参数壳写进原生 envelope，也不把 CLI target/envelope 写进 MCP query。
- 不因失败自动切换 surface、transport、backend、数据源或测试层级。
- 不把 truncated/partial 当全量。
- 不把波形图片当唯一证据；图片用于宏观观察，结论回到确定性 action 验证。
- 未授权时不修改 xwiki、不创建项目 config、不执行 EDA 命令。
