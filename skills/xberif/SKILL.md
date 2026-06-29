---
name: xberif
description: >
  当 AI agent 需要在芯片验证任务中复用持续记忆时使用：查询或维护由
  XBERIF_WIKI_DIR 指向的验证项目 LLM wiki，了解验证环境、DUT 功能、
  接口、testbench、sequence、checker、coverage、workflow、debug 入口、
  BT/IT/ST/SoC 项目上下文，并把新发现编译回 wiki，避免每次 session 从 0 启动。
  debug 完 case fail 后必须更新 xberif wiki。
---

# xberif 持续记忆 Skill

xberif 用来维护芯片验证项目的 LLM wiki。它不是 CLI/MCP 工具，也不读取旧版运行时状态目录；它规定 AI 如何查询、增删改查和校验一个持久 Markdown wiki。

## 必须先做

1. 读取环境变量 `XBERIF_WIKI_DIR`，它是当前 session 的 xberif wiki 根目录。
2. 如果 `XBERIF_WIKI_DIR` 未定义或为空，必须询问用户提供路径；不要 fallback 到 `doc/`、当前目录或其他猜测路径。
3. 初始化 wiki 或第一次为项目建立持续记忆时，如果用户没有告知 spec 路径或 RTL 路径，必须询问用户；不要自己猜测 spec/RTL 根目录。
4. 需要校验格式时运行：

```bash
python <xverif-root>/skills/xberif/scripts/validate_xberif_wiki.py
```

## 何时使用

- 需要了解验证环境、DUT 功能、接口、reset/clock、memory map、interrupt、testbench、agent、sequence、checker、scoreboard、coverage、workflow、debug 入口。
- 需要把源码、README、spec、test、wave/debug 报告或用户说明编译进持久项目记忆。
- 需要查询、创建、修改或废弃验证项目 wiki 页面。
- 需要检查 wiki 格式是否能被后续 agent 可靠读取。
- debug 完一个 case fail 后，必须更新 xberif wiki，把根因归入 `env_bug`、`rtl_bug` 或 `spec_bug` 主题之一。

## 查询顺序

1. 从 `$XBERIF_WIKI_DIR/index.md` 开始，找候选主题和入口页面。
2. 读取相关 concept 页面，看 frontmatter、正文、出链、evidence 和 citations。
3. 如果存在 `_index/backlinks.md` 或 `_index/tags.md`，用它们做反向或 tag 索引。
4. 如果仍找不到，只在 `$XBERIF_WIKI_DIR` 内用 `rg` 搜索 Markdown。
5. 搜索命中后必须回到页面级证据；不要只引用 grep 片段作答。
6. wiki 信息不足时再读 raw source，并把稳定发现编译回 wiki。

详细查询和 CRUD 规则见 [references/wiki-crud.md](references/wiki-crud.md)。

## 编译要求

严格执行 LLM Wiki 编译过程：raw sources 是事实来源，wiki 是编译产物，schema 由本 skill 规定。每次 ingest/update 必须读旧页面、抽取新事实、合并或新增 concept、更新 index/反向索引、追加 log、运行校验并汇报 unknowns。

总结或新增验证 topic 页面时，必须先按验证层级和主题读取 [references/prompts](references/prompts) 下对应 Markdown prompt，例如 `bt/prompts/project.md`、`it/prompts/agent.md`、`st/prompts/interconnect.md` 或 `soc/prompts/boot_flow.md`。没有完全匹配的 topic 时，选择最接近的 prompt 作为写作约束，并在 summary 中说明使用了哪个 prompt。输出还必须遵守 [references/prompt-output-requirements.md](references/prompt-output-requirements.md)。

禁止把具体仿真产物作为 wiki evidence 或 citation，例如单次 run 的 FSDB/VCD、simv 产物、临时日志、coverage 临时目录、scratch 报告、`/tmp` 文件。这些不会进入 git，只能作为当次 debug 的 raw observation；写入 wiki 时必须编译成稳定结论，并引用可追踪的 spec、RTL、test、脚本、README 或已提交文档。

case fail debug 结束后必须写回 wiki：

- `env_bug`：testbench、UVM env、sequence、checker、scoreboard、配置、脚本、仿真参数或环境依赖导致的问题。
- `rtl_bug`：DUT/RTL 实现、时序、状态机、接口行为、reset/clock、backpressure、ordering 等设计实现问题。
- `spec_bug`：spec 不清、spec 与 RTL/DV 期望冲突、需求缺失或文档定义错误。

如果根因未完全确认，仍要更新对应候选主题，把结论标为未确认，并记录下一步需要的证据。

详细流程见 [references/compile-process.md](references/compile-process.md)。

## Wiki 格式

wiki 根目录必须包含 `index.md` 和 `log.md`。普通 concept Markdown 必须有 YAML frontmatter，至少包含 `type`、`title`、`description`。链接必须相对可解析，禁止本机绝对路径和 `file://`。

完整格式见 [references/wiki-spec.md](references/wiki-spec.md)。

## 旧验证 topic prompts

旧 xberif 的 BT/IT/ST/SoC prompt 已保留在 [references/prompts](references/prompts)。需要按验证环境类型补 wiki 页面时，先进入对应层级目录，再按 topic 打开对应 prompt；输出约束集中在 [references/prompt-output-requirements.md](references/prompt-output-requirements.md)。
