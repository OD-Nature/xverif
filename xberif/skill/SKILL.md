---
name: xberif
description: >
  当 AI agent 需要为芯片验证项目初始化 xberif 配置、生成或查询项目 summary cards、
  读取/维护 topic detail markdown、构造 agent brief/context，或检查 xberif card/detail 合同时使用。
  xberif 管项目知识上下文，不读 RTL/FSDB、不做 bit 计算、不还原日志位置。
---

# xberif

`xberif` 是 xverif 的项目级 agent context 工具。它把验证项目知识按 topic 保存成短 summary card 和可展开 detail markdown，让 agent 先读紧凑 brief，必要时再按 topic 拉取细节。

## 何时使用

使用 xberif：

- 用户要为 BT/IT/ST/SoC 验证项目初始化 context/card 配置。
- 用户要运行 `xberif init` 生成 `.xberif/cards.json` 和 `.xberif/details/*.md`。
- 用户要查询当前项目已有 topic、brief、card、detail。
- 用户要检查或修复 xberif card/detail schema、metadata、section 合同。
- 用户问模型如何传入、为什么 headless 运行看起来安静、或 Claude Code hook 校验为什么失败。

不要使用 xberif：

- 查 RTL driver/load/path、波形值、事件或协议异常：用 `xdebug`。
- 算 SV literal、slice、mask、expected value：用 `xbit`。
- 解析 descriptor/entry/header fragments：用 `xentry`。
- 还原 `L_XXXXXXXX` 日志位置：用 `xloc`。

## 调用入口

优先使用 shell 中已安装的 `xberif` 命令：

```bash
xberif config init --kind bt
xberif init --model opus
xberif brief --mode debug
xberif get backpressure
xberif detail backpressure
```

如果 shell 没有安装 `xberif`，在 xverif 仓库根目录可临时使用：

```bash
PYTHONPATH=xberif "$HOME/miniconda3/bin/python" -m xberif <command> ...
```

回答和文档里不要暴露本机绝对路径；需要描述路径时使用 `<xverif-root>`、`<project-root>`、`$XVERIF_HOME`。

## 初始化与生成流程

1. 在目标项目根目录运行配置初始化：

```bash
xberif config init --kind bt
```

`--kind` 支持 `bt`、`it`、`st`、`soc`。该命令只生成项目内 `xberif/` 配置、prompts 和 views，不应生成 `.xberif/` 状态目录。

2. 真实生成 cards/details 时必须显式传模型：

```bash
xberif init --model opus
```

模型来源保持单一：CLI `--model <model>` 是必填；`kind.toml` 不保存默认 model；`agent.command` 里也不应写 `--model`。如果发现模型同时出现在配置和 CLI，要改成只从 CLI 传入。

3. 生成后检查输出：

```bash
xberif validate
xberif list-topics
xberif brief --mode debug
```

`.xberif/cards.json` 是 card catalog；`.xberif/details/*.md` 是展开说明；`.xberif/manifest.json` 是项目扫描和 topic manifest。

## 查询流程

短上下文：

```bash
xberif brief --mode debug
```

单 topic card：

```bash
xberif get backpressure
```

单 topic detail：

```bash
xberif detail backpressure
xberif get backpressure --detail
```

Agent 回答时默认先引用 brief/card 中的短结论；只有用户要展开、需要 evidence、或 card 信息不足时再读取 detail。

## Card / Detail 合同

card 是短摘要，detail 是展开说明。维护合同时遵守：

- `summary` 必须短而明确，只概括该 topic 的结论。
- `key_items` 必须有 `name`、`one_line`、`confidence`、`evidence`。
- `detail.available=true` 时，应存在 `.xberif/details/<card_id>.md`。
- detail markdown 必须包含 YAML frontmatter，且 `schema_version/env_kind/topic/card_id/title/confidence` 与 card 对齐。
- detail 标题和 metadata 必须和 card 精确匹配；不要随意改成“差不多”的标题。
- detail section 用来展开说明，不要把展开解释塞回 card summary。

写入入口：

```bash
cat card.json | xberif card upsert --stdin
cat detail.md | xberif detail upsert backpressure --stdin
xberif validate
```

## Claude Code / Hook 排错

- headless agent 运行时 stdout 可能很安静；不要仅凭终端无输出判断卡住。
- 需要确认 Claude Code 是否在跑时，查看对应 project transcript JSONL。
- Stop hook 失败常见原因是 card/detail schema、detail title、metadata 或 required section 不匹配。
- 如果 `init` 报 agent command 里已有 `--model`，应从 `kind.toml` 的 `agent.command` 移除模型参数，继续通过 `xberif init --model <model>` 传入。

## 依赖和测试

`xberif` 需要 Python 3.11+，运行依赖 `typer`、`rich`、`pydantic`、`jsonschema`、`tomli-w`、`pathspec`，测试依赖 `pytest`。

在 xverif 仓库根目录：

```bash
make -C xberif
make -C xberif test
```

如果 `make -C xberif test` 因缺少 `pytest` 或运行依赖失败，报告缺失依赖，不要改业务逻辑绕过测试。
