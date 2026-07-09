# xsva SVA IR 解释

xsva 把 SystemVerilog Assertion 编译为 Surface IR、Sequence IR、Timeline IR，再基于 IR 生成确定性解释。不要直接让 LLM 自由解释 SVA temporal semantics。

## MCP 入口

默认省略 `output_format`，使用 xout。`emit` 取 `surface-ir`、`sequence-ir` 或 `timeline-ir`。

```json
{"tool":"xverif_sva_list_properties","args":{"file":"input.sva"}}
```

```json
{"tool":"xverif_sva_parse_property","args":{"file":"input.sva","property":"p_name","emit":"timeline-ir"}}
```

```json
{"tool":"xverif_sva_explain_property","args":{"file":"input.sva","property":"p_name"}}
```

## 工作流

1. 先 `list` 确认 property/assertion 名称。
2. 对目标 property 取 timeline IR。
3. 优先基于 `semantic_notes` 解释用户语义。
4. local variable 看 captures 和 depends_on_captures。
5. `first_match`、`throughout`、`intersect`、`within`、`[*]`、`[->]`、`[=]` 等高级 sequence 必须依赖 IR/semantic_notes。

## 排障和维护

- 不支持的 SVA 构造应给 conservative diagnostic，不要补语义。
- 修改 parser/lowering 时先加失败语义测试，再修实现，最后更新 golden IR。
- 回归入口在 `xsva` 目录运行 `make test`。
