# xwiki LLM Wiki Compile Process

xwiki 要求 AI 严格执行 LLM Wiki 的编译过程。

## Layers

- Raw sources：源码、README、spec、test、用户说明，以及当次 debug 中观察到的 wave/debug 现象。它们是事实来源，不被 xwiki 改写。
- Wiki：Markdown 编译产物。它保存稳定概念、验证结论、接口关系、debug 入口、未确认项和 evidence。
- Schema：由 xwiki skill 规定，包括 frontmatter、index/log、链接、废弃流程和证据规则。

具体仿真产物不能作为 wiki 的长期 evidence 或 citation，包括单次 run 的 FSDB/VCD、simv 产物、临时日志、coverage 临时目录、scratch 报告和 `/tmp` 文件。它们只允许作为当次 debug 的 observation；写入 wiki 时必须转化为稳定结论，并引用可追踪的 spec、RTL、test、脚本、README 或已提交文档。

## Ingest Or Update

每次 ingest/update 必须完成：

1. 读取 `index.md` 和相关旧页面。
2. 初始化 wiki 或第一次建立项目记忆时，确认用户已提供 spec 路径和 RTL 路径；缺失时必须询问。
3. 阅读 raw source。
4. 确定验证层次 `bt/it/st/soc`；如果无法确定，必须询问用户。确定后读取 `references/prompts/<level>/prompts/*.md` 下全部 prompt 文件，并结合 `references/prompt-output-requirements.md` 组织总结。
5. 抽取稳定事实、验证结论、接口关系、debug 入口、unknowns。
6. 按 object_type 选择目录：设计事实进入 `de/`，验证事实进入 `dv/`，设计/spec/RTL 问题进入 `de_issue/`，DV 问题进入 `dv_issue/`。`de_issue` 下必须继续区分 `spec/` 或 `rtl/`。
7. 优先更新已有 concept；只有没有合适页面时才新增。
8. 处理 contradiction：新材料推翻旧结论时，更新旧页面并记录 resolution。
9. 更新根 `index.md`、相关目录及沿途子目录的 `index.md`、出链、入链、可选 backlinks/tags。
10. 追加最接近更新页面的目录级 `log.md`；跨多个描述对象目录时分别追加各目录日志。
11. 如果创建新子目录，必须同时创建该目录的 `index.md` 和 `log.md`。
12. 运行 `validate_xwiki.py`。
13. 向用户汇报来源、更新页面、验证层次、已读取的 prompt 集合、主要使用的 prompt、剩余 unknowns 和校验结果。

## Case Fail Debug

获得写回授权后，debug 完 case fail 时更新 xwiki wiki。根因主题只能归入以下三类之一：

- `env_bug`：写入 `dv_issue/`，描述 testbench、UVM env、sequence、checker、scoreboard、配置、脚本、仿真参数或环境依赖导致的问题。
- `rtl_bug`：写入 `de_issue/rtl/`，描述 DUT/RTL 实现、时序、状态机、接口行为、reset/clock、backpressure、ordering 等设计实现问题。
- `spec_bug`：写入 `de_issue/spec/`，描述 spec 不清、spec 与 RTL/DV 期望冲突、需求缺失或文档定义错误。

如果根因未完全确认，选择最可能的候选主题并标记为未确认，列出下一步证据需求。不要把临时仿真产物路径写成长期 citation。

## Query

回答问题时先查询 wiki；wiki 不足时查询 raw source，并将有价值的新知识编译回 wiki。不要让重要结论只留在 chat history。
