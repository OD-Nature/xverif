# xverif

`xverif` 是面向芯片验证 debug agent 的本地工具仓库，当前包含七个核心工具、一个统一 MCP 入口和一个 EDA 命令执行器：

- [`xdebug`](xdebug/README.md)：查询设计数据库和波形数据库里的事实。
- [`xbit`](xbit/README.md)：确定性计算 bit、literal、slice、表达式和 expected value。
- [`xentry`](xentry/README.md)：按配置解析多拍 byte fragments，输出 raw entry 域段。
- [`xloc`](xloc/README.md)：UVM 日志位置压缩与恢复，降低 LLM token 噪声。
- [`xberif`](xberif/README.md)：生成和查询项目 summary cards/detail context，给 agent 提供可控上下文。
- [`xsva`](xsva/README.md)：把 SystemVerilog Assertion 编译为结构化 IR，并生成确定性解释和可视化。
- [`xcov`](xcov/README.md)：查询 VCS/Verdi coverage database，输出 compact coverage evidence。
- [`xverif-mcp`](xverif_mcp/README.md)：统一 MCP server，xdebug/xcov 作为 stateful backend，其他工具以 stateless CLI adapter 接入。
- [`xeda-runner`](xeda_runner/README.md)：带环境快照缓存的阻塞式 EDA 命令执行器（非 MCP，独立 CLI）。

简单说：`xdebug` 负责“事实从哪里来、某时刻发生了什么”，`xbit` 负责“这些值按 SystemVerilog 规则算出来到底是多少”，`xentry` 负责“这个 entry 的 bit 域段按配置切出来是什么”，`xloc` 负责“这条 log 在哪个文件的哪一行，但只在需要时才查”，`xberif` 负责”项目知识先用短卡片喂给 agent，细节按 topic 再展开”，`xsva` 负责”assertion 的 temporal 语义先降成 IR，再解释给人和 agent”，`xcov` 负责“coverage database 里哪些 scope/object/bin 已覆盖或未覆盖，并给出源码 evidence”，`xverif-mcp` 负责”把这些工具统一暴露给 AI agent 的 MCP 协议入口”，`xeda-runner` 负责”在预配置的安全白名单内执行 EDA 命令，先 init 缓存环境再 run 阻塞执行”。

## 工具概览

### 默认输出格式：XOUT

除显式机器协议外，xverif 用户命令默认输出 `xout` 结构化文本，第一行形如：

```text
@xdebug.trace.driver.v1
```

`xout` 使用少量固定区块，例如 `target:`、`summary:`、`data:`、`evidence:`、`next:`，目的是让 AI 少读无用 JSON envelope。需要脚本解析、schema 校验或完整字段时，显式加 `--json`；内部 agent stdio/hook 协议仍保持 JSON。

### xdebug

`xdebug` 是 xtrace 与 xwave 合并后的统一调试工具。它通过 JSON API 查询 Verdi/VCS `daidir` 设计事实、FSDB 波形事实，或在两者同时存在时做 combined/debug join。

适合的问题：

- 查信号 driver、load、依赖图、路径和源码 evidence。
- 查波形值、事件、窗口验证、signal changes、handshake 异常。
- 查 APB/AXI 协议异常、latency、outstanding、error response。
- 在具体波形时间点定位当前生效 RTL driver：`trace.active_driver`。

入口示例：

```bash
tools/xdebug -h
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | tools/xdebug -
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | tools/xdebug --json -
tools/xverif-mcp
```

`tools/xverif-mcp` 是统一 stdio MCP server（`python -m xverif_mcp.server`），xdebug 作为设计/波形 stateful backend，xcov 作为 coverage stateful backend，xbit/xentry/xloc/xberif/xsva 以 stateless CLI adapter 接入。
如果 AI 客户端在登录机、NPI/FSDB 查询需要跑到 LSF 计算节点，可以设置 `XVERIF_MCP_BACKEND=lsf`，让 MCP wrapper 通过 `bsub -I` 启动集群内 per-session stdio-loop 进程。不同 session 并行，同一 session 串行。
可用 `XVERIF_MCP_ENABLE_DEBUG/BIT/ENTRY/LOC/CONTEXT/SVA` 等环境变量按工具组关闭 MCP 暴露面。
如果不走 MCP 且本机无法直连计算节点 TCP 端口，xdebug 原生支持 `transport:"file"`，通过共享文件系统在 session 目录下交换 request/response。

所有 MCP tool 通用支持 `xverif_output_path` / `xverif_output_append` 参数，可将响应同时写入文件。

完整说明见 [`xdebug/README.md`](xdebug/README.md)。

### xbit

`xbit` 是确定性 bit/value/expression 计算器。它不读取 RTL、不分析层次结构，只负责把输入值按明确规则算对，避免 agent 靠心算处理位宽、符号位和表达式。

适合的问题：

- SV literal、hex/bin/decimal 转换。
- signed/unsigned 解释。
- bit slice/index、concat、repeat、mask、popcount、onehot。
- 常量表达式、valid-ready 条件、expected value 比较。
- 对 `xdebug` 返回的 compact values 做二次计算。

入口示例：

```bash
tools/xbit conv "8'shff"
tools/xbit eval "data[15:8] == 8'hbe" --var data=32'hdead_beef
```

完整说明见 [`xbit/README.md`](xbit/README.md)。

### xentry

`xentry` 是 JSON-first 的多拍 entry 域段解析器。它接收 canonical byte fragments，由外部 config 定义字段布局，只输出 raw field slices 和 provenance，不做协议理解或字段类型语义解码。

适合的问题：

- 解析 descriptor、metadata、table entry、WQE、CQE 或 header field。
- 把多拍 byte fragments 按有效 bit 拼成 entry。
- 按配置切出 field raw hex/bin。
- 查看跨拍 field 来自哪一拍、哪些 bit。

入口示例：

```bash
printf '%s\n' '{"api_version":"xentry.v1","action":"decode","config_path":"xentry/examples/entry.yaml","input_path":"xentry/examples/fragments.jsonl"}' | tools/xentry -
tools/xentry '{"api_version":"xentry.v1","action":"explain","config_path":"xentry/examples/entry.yaml"}'
tools/xentry --json '{"api_version":"xentry.v1","action":"explain","config_path":"xentry/examples/entry.yaml"}'
```

完整说明见 [`xentry/README.md`](xentry/README.md)。

### xloc

`xloc` 是 LLM-friendly 的 UVM 日志位置压缩与恢复工具。它将 UVM 仿真日志中冗长的文件路径替换为简短 `L_XXXXXXXX` ID，通过 sidecar JSONL 映射文件支持按需恢复源码上下文，降低 LLM 处理 log 的 token 噪声。

适合的问题：

- 解析仿真日志中 `L_XXXXXXXX` 对应的源码位置。
- 统计日志中高频报错的热点位置。
- 查看 loc_id 对应的源码上下文。
- 给带 loc_id 的日志添加可读注释。

入口示例：

```bash
tools/xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
tools/xloc stats out/sim.log
```

完整说明见 [`xloc/README.md`](xloc/README.md)。

### xberif

`xberif` 是项目级 agent context summary card 工具。它按 BT/IT/ST/SoC 等验证环境模板生成 topic prompts，把项目知识保存成短 summary cards 和可展开 detail markdown，供后续 agent 按需查询。

适合的问题：

- 给新 agent 快速注入当前项目的关键 topic 和验证上下文。
- 按 mode 输出紧凑 brief，避免每次塞入大量重复背景。
- 查询某个 topic 的 summary、key items、evidence 和 detail。
- 通过 `init --model <model>` 调用真实 agent 生成 cards/details，并用 hook/validate 守住输出合同。

入口示例：

```bash
tools/xberif config init --kind bt
tools/xberif init --model opus
tools/xberif brief --mode debug
```

完整说明见 [`xberif/README.md`](xberif/README.md)。

### xsva

`xsva` 是 SystemVerilog Assertion 语义编译工具。它不替代 VCS/Formal，也不让 LLM 直接自由解释 SVA 原文；它把 property/assertion 从文本 lowering 成 Surface IR、Sequence IR、Timeline IR，再从 IR 生成文本、Markdown 或 JSON 输出。

适合的问题：

- 列出 `.sva/.sv` 文件中的 property/assert/assume/cover。
- 检查 `|->`、`|=>`、`##N`、`##[m:n]`、range suffix path expansion 等 temporal 语义。
- 查看 local variable capture、per-attempt binding 和后续 `depends_on_captures`。
- 对 `first_match`、`intersect` 等高级 sequence 输出语义摘要，内部保留保守状态但不在用户解释中暴露。
- 为 SVA review、agent debug 和 golden regression 生成确定性 IR/解释。

入口示例：

```bash
tools/xsva list --file xsva/tests/golden_ir/simple_impl/input.sva
tools/xsva parse --file xsva/tests/golden_ir/ranged_delay/input.sva --property p_ranged --emit timeline-ir
tools/xsva explain --file xsva/tests/golden_ir/path_expand/input.sva --property p_path
```

完整说明见 [`xsva/README.md`](xsva/README.md)。

### xcov

`xcov` 是面向 AI/MCP 的 VCS/Verdi coverage database 查询引擎。它用 `xcov.v1` JSON request 查询 `simv.vdb` / `merged.vdb`，默认输出 `xout`，支持 code coverage、functional coverage、scope summary、coverage holes、source file/line 映射和大结果导出。

适合的问题：

- 打开大型 coverage database，并通过 session 复用打开成本。
- 查询 line/toggle/branch/condition/fsm/assert/functional coverage。
- 按 hierarchy scope 查看 summary、children 排名和 scope search。
- 查 coverage holes，并保留 `file/line` evidence。
- 根据源码 `file/line/window` 反查 coverage item。
- 导出 summary/holes/scope_tree/functional 为 `json/ndjson/csv/md`。

入口示例：

```bash
printf '%s\n' '{"api_version":"xcov.v1","action":"session.open","target":{"vdb":"fake"},"args":{"name":"cov0","fake":true}}' | tools/xcov --json -
tools/xcov --stdio-loop
```

MCP 工具入口使用 `xverif_cov_session_open`、`xverif_cov_query`、`xverif_cov_session_close`。真实 NPI coverage 查询需要可访问 Synopsys license server；优先使用 Python 3.11 环境，必要时再切换到 Verdi 自带 Python。

完整说明见 [`xcov/README.md`](xcov/README.md)，skill 见 [`xcov/skill/SKILL.md`](xcov/skill/SKILL.md)。

### xeda-runner

`xeda-runner` 是带环境快照缓存的阻塞式 allowlist EDA 命令执行器。它先通过 `init` 缓存 `tcsh/module/setup` 环境为 env0 快照，`run` 时读取快照并按配置白名单构造 argv、校验 target/option、阻塞执行并透传 exit code。纯 Python 标准库，零 pip 依赖，支持 bash/zsh/tcsh。

适合的问题：

- 在预配置的安全白名单内执行 `make`、`vcs`、`simv` 等 EDA 命令。
- 让 AI agent 只能通过限定 action/target/option 调用底层工具，避免绕过环境或拼 raw command。
- 需要执行超长任务（>5 分钟）时配合 `tmux`/`nohup` 保证不被 terminal 生命周期影响。

入口示例：

```bash
xeda-runner init
xeda-runner list-actions
xeda-runner describe-action --action sim
xeda-runner run --action sim --target compile --option TEST=smoke_test --dry-run
xeda-runner run --action sim --target compile --option TEST=smoke_test --option SEED=123
```

完整说明见 [`xeda_runner/README.md`](xeda_runner/README.md)，skill 见 [`xeda_runner/skill/SKILL.md`](xeda_runner/skill/SKILL.md)。

## 推荐 Shell 入口

为了在任意目录和非交互 shell 中稳定调用，建议把统一 wrapper 目录加入 `PATH`。示例中的 `<xverif-root>` 表示本仓库根目录，请按本机实际路径替换。

Bash / Zsh：

```bash
export XVERIF_HOME=<xverif-root>
export PATH="$XVERIF_HOME/tools:$PATH"
# 可选：指定 xberif Python；未设置时 tools/xberif 会优先找 ~/miniconda3/envs/xberif-py311/bin/python。
export XBERIF_PYTHON="$HOME/miniconda3/envs/xberif-py311/bin/python"
```

Tcsh：

```tcsh
setenv XVERIF_HOME <xverif-root>
setenv PATH "$XVERIF_HOME/tools:$PATH"
setenv XBERIF_PYTHON "$HOME/miniconda3/envs/xberif-py311/bin/python"
```

配置后：

```bash
xdebug -h
xbit conv "8'shff" --json
xentry '{"api_version":"xentry.v1","action":"explain","config_path":"xentry/examples/entry.yaml"}'
xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
xberif config init --kind bt
xsva list --file xsva/tests/golden_ir/simple_impl/input.sva
xcov --stdio-loop
xeda-runner init
xeda-runner run --action sim --target compile --option TEST=smoke_test
```

所有工具入口统一放在 `tools/` 目录下。

## 环境要求

| 组件 | 要求 |
|---|---|
| GCC | **5.0+** |
| Python | 3.11+（xberif / xverif-mcp）；xbit/xentry/xloc 支持 3.6+ |
| Verdi | 当前基于 **V-2023.12-SP2** 开发与测试，NPI API 随版本不同可能存在参数差异 |

> 如果使用其他 Verdi 版本遇到编译或运行时 NPI 兼容性问题，可让 AI agent 根据编译错误和 NPI 头文件进行兼容性修复。

## 构建与测试

`xdebug` 需要可用的 Verdi/NPI 环境；`xbit` 只依赖 Python 标准库；`xberif` 要求 Python 3.11+，真实 `init` 还需要可用的 agent 命令和显式 `--model` 参数。

```bash
make -C xdebug
make -C xdebug schema-test
make -C xdebug contract-test
make -C xdebug unit-test
make -C xdebug mcp-test            # xverif_mcp test_actions (需要 Verdi 环境)

make -C xbit test
make -C xentry test
make -C xloc test
make -C xberif test
make -C xsva test
make -C xcov test

# xverif_mcp 单元测试（无需 Verdi）
PYTHONPATH=xverif_mcp/src:. python -m pytest xverif_mcp/tests/ -q

# xeda_runner 单元测试（无需 Verdi）
python -m pytest xeda_runner/tests/ -q

make test
make full-test
```

`schema-test` 校验 xdebug JSON schema 和 examples，不依赖 Synopsys 环境；`contract-test` 在 xdebug 构建后校验 ActionSpec 与 runtime `actions` 输出一致。`make test` 覆盖仓库内常规单测、contract test 和自带夹具；`make full-test` 会加入更多设计、波形和真实数据回归，要求本机具备相应 Synopsys 运行环境和 license。

## 文档入口

- xdebug 用户文档：[`xdebug/README.md`](xdebug/README.md)
- xdebug agent skill：[`xdebug/skill/SKILL.md`](xdebug/skill/SKILL.md)
- xdebug JSON API 速查：[`xdebug/skill/references/json-api-reference.md`](xdebug/skill/references/json-api-reference.md)
- xbit 用户文档：[`xbit/README.md`](xbit/README.md)
- xbit agent skill：[`xbit/skill/SKILL.md`](xbit/skill/SKILL.md)
- xentry 用户文档：[`xentry/README.md`](xentry/README.md)
- xentry agent skill：[`xentry/skill/SKILL.md`](xentry/skill/SKILL.md)
- xloc 用户文档：[`xloc/README.md`](xloc/README.md)
- xloc agent skill：[`xloc/skill/SKILL.md`](xloc/skill/SKILL.md)
- xberif 用户文档：[`xberif/README.md`](xberif/README.md)
- xsva 用户文档：[`xsva/README.md`](xsva/README.md)
- xsva agent skill：[`xsva/skill/SKILL.md`](xsva/skill/SKILL.md)
- xcov 用户文档：[`xcov/README.md`](xcov/README.md)
- xcov agent skill：[`xcov/skill/SKILL.md`](xcov/skill/SKILL.md)
- xverif-mcp 用户文档：[`xverif_mcp/README.md`](xverif_mcp/README.md)
- xeda-runner 用户文档：[`xeda_runner/README.md`](xeda_runner/README.md)
- xeda-runner agent skill：[`xeda_runner/skill/SKILL.md`](xeda_runner/skill/SKILL.md)
