---
name: xsva
description: >
  当 AI agent 需要把 SystemVerilog Assertion (SVA) property/assert/assume/cover
  解析成 xsva 的 Surface IR、Sequence IR、Timeline IR，生成确定性解释、Markdown
  或 JSON，或维护 xsva golden/语义/CLI 回归时使用。适用于 SVA temporal
  semantic review、range delay/path expansion、local variable capture、高级 sequence
  的 semantic_notes 摘要验证；不要让 LLM 直接自由解释 SVA 原文。
---

# xsva

`xsva` 是 SVA 语义编译和解释工具。它的事实源是 IR，而不是自然语言猜测：

```text
SVA source -> Surface IR -> Sequence IR -> Timeline IR -> text/markdown/json
```

使用本 skill 时，必须优先让 `xsva` 解析和 lowering，再基于 IR 解释 SVA。不要直接对 SVA 原文自由解释 temporal semantics。

## 入口

优先使用已安装的 `xsva` 命令。如果当前 shell 没有安装命令，但工作目录是 xverif 仓库，可使用：

```bash
cd <xverif-root>/xsva
/home/yian/miniconda3/bin/python -m xsva --help
```

当前环境没有稳定的 `python` 命令时，使用 `/home/yian/miniconda3/bin/python` 或 `make test` 内置的解释器。

常用命令：

```bash
xsva list    --file input.sva
xsva scan    --file input.sva
xsva parse   --file input.sva --property p_name --emit surface-ir
xsva parse   --file input.sva --property p_name --emit sequence-ir
xsva parse   --file input.sva --property p_name --emit timeline-ir
xsva explain --file input.sva --property p_name
xsva explain --file input.sva --property p_name --markdown
```

## Agent 工作流

1. 先运行 `xsva list --file <file>`，确认 property/assertion 名称。
2. 对目标 property 先取 `timeline-ir` JSON，再解释语义。
3. 如果 timeline 有 `semantic_notes`，优先用这些摘要解释用户语义，不要向用户报告内部 lowering/partial 状态。
4. 对 `##[m:n]` 后接 suffix sequence，用户解释应使用摘要，例如 `ack must be true at cycle +1 to +3; done must be true 1 clk after ack.`；内部可再检查 `match_paths` 是否保留候选路径。
5. 对 local variable，检查 `trigger.captures`、path-specific captures 和 `depends_on_captures`。
6. 对 `first_match`、`throughout`、`intersect`、`within`、`[*]`、`[->]`、`[=]` 等高级 sequence，确认解释来自 `semantic_notes`，不能把它们误说成固定 cycle 的普通 point obligation。
7. 对用户输出，默认引用 `trigger` 和 `semantic_notes`；`match_paths` / `obligations` 是内部/evidence 结构，不作为默认人类解释格式。

## 语义检查速查

必须守住这些 MVP 语义：

- `req |-> ack`：`ack` 在 cycle `+0`。
- `req |=> ack`：`ack` 在 cycle `+1`。
- `req |-> ##2 ack`：`ack` 在 cycle `+2`。
- `req |=> ##2 ack`：`ack` 在 cycle `+3`。
- `req |-> ##[1:4] ack`：内部是单个 `eventually` obligation，window `[1,4]`；用户摘要是 `ack must be true at cycle +1 to +4.`
- `req |-> ##[1:3] ack ##1 done`：内部保留三条候选路径；用户摘要是 `ack must be true at cycle +1 to +3; done must be true 1 clk after ack.`
- `(req, v = data) |-> ##[1:4] ack && rsp == v`：`v=data` 是 per-attempt capture，后续 obligation 依赖 `v`。
- `first_match(##[1:4] ack) ##1 done`：`semantic_notes` 应说明 `ack must be the first match at cycle +1 to +4; done must be true 1 clk after that first ack.`
- `valid throughout (req ##1 ack)`：`semantic_notes` 应说明右侧 sequence 摘要，以及 `valid` 在整个匹配区间保持成立。
- `(a ##1 b) intersect (c ##1 d)`：`semantic_notes` 应包含 `Sequence 1`、`Sequence 2`、`Relation`，并说明两者同时开始、同时结束。
- `(a ##1 b) within (c ##[1:3] d)`：`semantic_notes` 应包含 `Sequence 1`、`Sequence 2`、`Relation`，并说明 sequence 1 的匹配区间落在 sequence 2 内部。
- `ack[*3]` / `ack[->2]` / `ack[=2]`：`semantic_notes` 应分别说明连续重复、第 N 次出现、累计匹配 N 次。

## 回归和维护

在 `<xverif-root>/xsva` 下运行：

```bash
make test
```

测试体系应包含：

- exact golden IR：`tests/golden_ir/<case>/{surface_ir,sequence_ir,timeline_ir}.json`
- direct semantics tests：检查 cycle/window/path/capture/status 字段
- CLI smoke tests：覆盖 `list/scan/parse/explain`

更新 xsva parser/lowering 时，先加能失败的语义测试，再修实现，最后更新 golden JSON。不要只比较 name/count；golden 必须做完整 JSON 对比，并确认对外 JSON 不包含内部 lowering 状态字段。

## 边界

xsva 不替代 VCS、formal 或完整 SVA 仿真引擎。遇到工具未支持的 SVA 构造时，正确行为是 conservative diagnostic，而不是让 agent 补语义。

如果需要验证真实仿真 pass/fail，可在核心 case 修复后再使用 `tests/vcs` 作为第二层语义对照。
