# xberif LLM Wiki Compile Process

xberif 要求 AI 严格执行 LLM Wiki 的编译过程。

## Layers

- Raw sources：源码、README、spec、test、用户说明，以及当次 debug 中观察到的 wave/debug 现象。它们是事实来源，不被 xberif 改写。
- Wiki：Markdown 编译产物。它保存稳定概念、验证结论、接口关系、debug 入口、未确认项和 evidence。
- Schema：由 xberif skill 规定，包括 frontmatter、index/log、链接、废弃流程和证据规则。

具体仿真产物不能作为 wiki 的长期 evidence 或 citation，包括单次 run 的 FSDB/VCD、simv 产物、临时日志、coverage 临时目录、scratch 报告和 `/tmp` 文件。它们只允许作为当次 debug 的 observation；写入 wiki 时必须转化为稳定结论，并引用可追踪的 spec、RTL、test、脚本、README 或已提交文档。

## Ingest Or Update

每次 ingest/update 必须完成：

1. 读取 `index.md` 和相关旧页面。
2. 初始化 wiki 或第一次建立项目记忆时，确认用户已提供 spec 路径和 RTL 路径；缺失时必须询问。
3. 阅读 raw source。
4. 根据验证环境类型和主题，读取 `references/prompts/{bt,it,st,soc}/prompts/*.md` 中最匹配的 topic prompt，并结合 `references/prompt-output-requirements.md` 组织总结。
5. 抽取稳定事实、验证结论、接口关系、debug 入口、unknowns。
6. 优先更新已有 concept；只有没有合适页面时才新增。
7. 处理 contradiction：新材料推翻旧结论时，更新旧页面并记录 resolution。
8. 更新 `index.md`、出链、入链、可选 backlinks/tags。
9. 追加 `log.md`。
10. 运行 `validate_xberif_wiki.py`。
11. 向用户汇报来源、更新页面、使用的 prompt、剩余 unknowns 和校验结果。

## Case Fail Debug

debug 完 case fail 后必须更新 xberif wiki。根因主题只能归入以下三类之一：

- `env_bug`：testbench、UVM env、sequence、checker、scoreboard、配置、脚本、仿真参数或环境依赖导致的问题。
- `rtl_bug`：DUT/RTL 实现、时序、状态机、接口行为、reset/clock、backpressure、ordering 等设计实现问题。
- `spec_bug`：spec 不清、spec 与 RTL/DV 期望冲突、需求缺失或文档定义错误。

如果根因未完全确认，选择最可能的候选主题并标记为未确认，列出下一步证据需求。不要把临时仿真产物路径写成长期 citation。

## Query

回答问题时先查询 wiki；wiki 不足时查询 raw source，并将有价值的新知识编译回 wiki。不要让重要结论只留在 chat history。
