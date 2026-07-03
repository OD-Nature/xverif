---
name: xwiki
description: >
  当 AI agent 需要在芯片验证任务中复用持续记忆时使用：查询或维护由
  XWIKI_DIR 指向的验证项目 LLM wiki，了解验证环境、DUT 功能、
  接口、testbench、sequence、checker、coverage、workflow、debug 入口、
  BT/IT/ST/SoC 项目上下文，并把新发现编译回 wiki，避免每次 session 从 0 启动。
  debug 完 case fail 后必须更新 xwiki wiki。
---

# xwiki 持续记忆 Skill

xwiki 用来维护芯片验证项目的 LLM wiki。它不是 CLI/MCP 工具，也不读取旧版运行时状态目录；它规定 AI 如何查询、增删改查和校验一个持久 Markdown wiki。

## 必须先做

1. 读取环境变量 `XWIKI_DIR`，它是当前 session 的 xwiki wiki 根目录。
2. 如果 `XWIKI_DIR` 未定义或为空，必须询问用户提供路径；不要 fallback 到 `doc/`、当前目录或其他猜测路径。
3. 初始化 wiki 或第一次为项目建立持续记忆时，如果用户没有告知 spec 路径或 RTL 路径，必须询问用户；不要自己猜测 spec/RTL 根目录。
4. 需要校验格式时运行：

```bash
python <xverif-root>/skills/xwiki/scripts/validate_xwiki.py
```

## 何时使用

- 需要了解验证环境、DUT 功能、接口、reset/clock、memory map、interrupt、testbench、agent、sequence、checker、scoreboard、coverage、workflow、debug 入口。
- 需要把源码、README、spec、test、wave/debug 报告或用户说明编译进持久项目记忆。
- 需要查询、创建、修改或废弃验证项目 wiki 页面。
- 需要检查 wiki 格式是否能被后续 agent 可靠读取。
- debug 完一个 case fail 后，必须更新 xwiki wiki，把问题记录到 `de_issue` 或 `dv_issue` 描述对象中。

## 查询顺序

1. 从 `$XWIKI_DIR/index.md` 开始，找候选主题和入口页面。
2. 读取相关 concept 页面，看 frontmatter、正文、出链、evidence 和 citations。
3. 如果存在 `_index/backlinks.md` 或 `_index/tags.md`，用它们做反向或 tag 索引。
4. 如果仍找不到，只在 `$XWIKI_DIR` 内用 `rg` 搜索 Markdown。
5. 搜索命中后必须回到页面级证据；不要只引用 grep 片段作答。
6. wiki 信息不足时再读 raw source，并把稳定发现编译回 wiki。

详细查询和 CRUD 规则见 [references/wiki-crud.md](references/wiki-crud.md)。

## 编译要求

严格执行 LLM Wiki 编译过程：raw sources 是事实来源，wiki 是编译产物，schema 由本 skill 规定。每次 ingest/update 必须读旧页面、抽取新事实、合并或新增 concept、更新 index/反向索引、追加 log、运行校验并汇报 unknowns。

### 验证层次 prompt 读取硬规则

总结、新增或更新任何验证 topic 页面前，必须先确定当前验证层次是 `bt`、`it`、`st` 还是 `soc`。验证层次可来自用户说明、wiki index、已有 concept、仓库目录或验证环境命名；如果无法确定，必须询问用户，不得猜测。

一旦验证层次确定，必须读取该层次目录下的全部 prompt 文件：`references/prompts/<level>/prompts/*.md`。不能只读取最匹配的单个 topic prompt，也不能因为当前任务看似只涉及某个 topic 就跳过同层其它 prompt。读取全部 prompt 后，再结合当前 topic 选择主要约束，并在汇报中说明验证层次、已读取的 prompt 集合和主要使用的 prompt。

输出还必须遵守 [references/prompt-output-requirements.md](references/prompt-output-requirements.md)。

### Wiki 描述对象分类硬规则

所有 wiki Markdown 文件的 frontmatter 必须包含 `object_type`，且只能使用 `de`、`dv`、`de_issue`、`dv_issue` 四个值之一。该字段用于区分页面描述对象，不等同于页面标题、tag 或验证层次。

- `de`：描述设计实现、RTL、接口、微架构、协议行为、设计参数和数据路径。
- `dv`：描述验证环境、sequence、checker、scoreboard、coverage、test、debug workflow 和仿真入口。
- `de_issue`：持续记录设计、RTL、spec、协议定义、性能需求或微架构侧问题和风险。
- `dv_issue`：持续记录验证环境、RM、checker、scoreboard、sequence、testbench、脚本、配置或 DV 假设侧问题和风险。

`index.md` 默认使用 `object_type: dv`；`log.md` 默认使用 `object_type: dv_issue`。debug 完 case fail 后必须更新 `de_issue` 或 `dv_issue` 页面；根因未完全确认时，也要作为候选 issue 记录 unknown 和下一步证据。

禁止把具体仿真产物作为 wiki evidence 或 citation，例如单次 run 的 FSDB/VCD、simv 产物、临时日志、coverage 临时目录、scratch 报告、`/tmp` 文件。这些不会进入 git，只能作为当次 debug 的 raw observation；写入 wiki 时必须编译成稳定结论，并引用可追踪的 spec、RTL、test、脚本、README 或已提交文档。

case fail debug 结束后必须写回 wiki：

- 设计、RTL、spec、协议定义、性能需求或微架构侧问题写入 `de_issue`。
- testbench、UVM env、RM、checker、scoreboard、sequence、配置、脚本、仿真参数或 DV 假设问题写入 `dv_issue`。
- 如果根因未完全确认，仍要更新对应候选 issue 页面，把结论标为未确认，并记录下一步需要的证据。

详细流程见 [references/compile-process.md](references/compile-process.md)。

## Wiki 格式

wiki 根目录必须包含 `index.md` 和 `log.md`。所有 Markdown 文件都必须有 YAML frontmatter，至少包含 `type`、`title`、`description`、`object_type`。`object_type` 只能是 `de`、`dv`、`de_issue`、`dv_issue`。链接必须相对可解析，禁止本机绝对路径和 `file://`。

完整格式见 [references/wiki-spec.md](references/wiki-spec.md)。

## 验证 topic prompts

BT/IT/ST/SoC prompt 保存在 [references/prompts](references/prompts)。确定验证层次后，必须读取对应层次 `prompts/` 目录下的全部 Markdown 文件，并结合 [references/prompt-output-requirements.md](references/prompt-output-requirements.md) 生成或更新 wiki 页面。
