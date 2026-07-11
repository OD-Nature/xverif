# xcov coverage 查询

xcov 查询 VCS/Verdi coverage database（`simv.vdb`、`merged.vdb`）。它负责 coverage evidence，不负责自动解释 hole 根因或生成补测策略。

## 何时使用

- 查询 line/toggle/branch/condition/fsm/assert/function coverage。
- 用 `scope.*` 和 `code_coverage.*` 按 hierarchy scope 查看覆盖率概览。
- 按源码 file/line/window 反查 coverage item。
- 输出源码窗口和 coverage annotation。
- 输出 assert/cover property/cover sequence 的结构化 report。
- 通过 `export.code_coverage`、`export.function_coverage`、`export.assert` 导出
  Markdown 查看详细未覆盖项。

## MCP 入口

本文所有常规示例都使用 MCP tool 调用壳：`tool` 是 MCP 工具名，外层 `args` 是该 MCP tool 的参数；`xverif_cov_query.args.args` 才是 xcov action 参数。直接调用工具时传外层 `args` 对象，写 `xverif_batch` 时整段 JSON 可作为一行请求。

- `xverif_cov_session_open`
- `xverif_cov_session_list`
- `xverif_cov_session_doctor`
- `xverif_cov_query`
- `xverif_cov_session_close`
- `xverif_cov_session_kill`
- `xverif_cov_session_gc`
- `xverif_cov_list_actions`
- `xverif_cov_get_schema`
- `xverif_cov_raw_request`

默认优先使用 xout 输出；示例不写 `output_format`。只有脚本需要稳定读取 JSON 字段，或专门验证 JSON response/schema 时，才显式请求 JSON。需要完整 `xcov.v1` 原生 envelope 时，只通过 `xverif_cov_raw_request(request=...)`；CLI 入口请使用 `xverif-cli`。

真实 NPI coverage 查询需要 Synopsys license；受限沙箱内 license 可能不可达。

Backend由 EDA profile选择：`verdi-2018` 使用 C++ native NPI worker，
`verdi-2023` 使用 Python `pynpi.cov`。失败时不得静默切换 backend或解析 URG HTML。

coverage query 不允许直接调用 native `session.open/status/close` 或其它 lifecycle action。doctor 只读且映射 native `session.status`；kill 终止 managed loop/process/LSF job，不虚构 native kill。list 的 tombstone/verbose、精确 kill、partial cleanup 和 gc 规则与 xdebug 对称，失败时不切换 backend 或 transport。

## 常用请求

open：

```json
{
  "tool": "xverif_cov_session_open",
  "args": {
    "name": "cov0",
    "vdb": "merged.vdb"
  }
}
```

holes：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "code_coverage.holes",
    "args": {
      "scope": "uart_tb",
      "metrics": [
        "line",
        "toggle",
        "branch",
        "condition",
        "fsm",
        "assert"
      ],
      "limits": {
        "max_items": 100
      }
    }
  }
}
```

code holes glob filter：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "code_coverage.holes",
    "args": {
      "scope": "uart_tb",
      "query": {
        "include_patterns": [
          "*u_uart*"
        ],
        "exclude_patterns": [
          "*uvm*"
        ],
        "match_field": "full_name"
      }
    }
  }
}
```

function holes：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "function_coverage.holes",
    "args": {
      "levels": [
        "bin"
      ],
      "query": {
        "include_patterns": [
          "*APB_accesses_cg*"
        ],
        "match_field": "full_name"
      }
    }
  }
}
```

source map：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "source.map",
    "args": {
      "file": "rtl/ctrl.sv",
      "line": 123,
      "window": 3
    }
  }
}
```

source annotate：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "source.annotate",
    "args": {
      "file": "rtl/ctrl.sv",
      "line": 123,
      "window": 3
    }
  }
}
```

assert summary：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "assert.summary"
  }
}
```

code coverage export：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "export.code_coverage",
    "args": {
      "scope": "uart_tb",
      "threshold_pct": 100.0,
      "output": {
        "path": "code_coverage.md"
      }
    }
  }
}
```

function coverage export：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "export.function_coverage",
    "args": {
      "covergroup": "*uart*",
      "threshold_pct": 100.0,
      "output": {
        "path": "function_coverage.md"
      }
    }
  }
}
```

assert export：

```json
{
  "tool": "xverif_cov_query",
  "args": {
    "session": "cov0",
    "action": "export.assert",
    "args": {
      "scope": "uart_tb",
      "threshold_pct": 100.0,
      "output": {
        "path": "assert.md"
      }
    }
  }
}
```

## 读取规则

- 先看 `ok`。
- 看 `summary.matched_count/returned/truncated/output_path/note`。
- coverage item 关注 action 当前返回的字段；不要假设所有 action 都输出
  `metric/type/name/full_name/covered/coverable/missing/status/evidence.file/evidence.line`。
- 普通 metric/item的 coverage pct用 `covered/coverable`，不要用 hit count代替。
- `scope.summary.coverage_pct` 是与 Verdi GUI一致的有效 metric百分比等权平均；
  `raw_coverage_pct` 才是总 `covered/coverable` 加权值。结合
  `score_basis:"average_metric_pct"` 和 `score_item_count` 解释结果。
- 保留 `excluded/unreachable/illegal` 状态，不要误判为普通 hole。
- 交互查询优先用 `scope.summary`、`scope.children`、`scope.search`、
  `code_coverage.summary`、`code_coverage.holes` 看层次覆盖率。
- `scope.summary` 返回扁平覆盖率字段；不要期待 `metrics={...}`，也不要期待
  parent/depth/type/def_name；它会返回 `coverage_pct/score_basis/score_item_count/`
  `raw_coverage_pct` 以及各 `*_pct`。
- `scope.children` 和 `scope.search` 每项只返回 `name/full_name/coverage_pct`。
- `code_coverage.summary` 不输出 `name/full_name/functional_pct`。
- `code_coverage.holes` 只输出当前 hierarchy 与子模块覆盖率概览，只保留
  `name/full_name/coverage_pct/*_pct`，不展开具体未覆盖 signal、branch、condition 或
  bin，也不输出 parent/depth/type/def_name/covered/coverable/missing/file/line。
- `code_coverage.holes` 和 `function_coverage.holes` 支持 `query.include_patterns` /
  `query.exclude_patterns` 通配过滤；只支持 glob `*`、`?`，不要使用 regex。
- `function_coverage.holes` 默认按 `full_name` 过滤，可用 `match_field` 切到
  `covergroup`、`coverpoint`、`cross`、`bin` 或 `name`。
- `function_coverage.summary` 和 `function_coverage.holes` 不输出
  `metric/name/full_name/score_basis/score_item_count/raw_covered/raw_coverable/raw_missing`；
  `function_coverage.summary` 也不输出 `raw_coverage_pct`。
- xout 的 `items:` 是对齐纯文本表格，不是 Markdown 表格；JSON 响应结构不变。
- 详细未覆盖项必须用 `export.code_coverage`、`export.function_coverage`、
  `export.assert` 导出 Markdown 查看。
- 三个 export action只支持 Markdown。提供 `pynpi.cov` 的版本可转用 x-npi做复杂
  二次统计；Verdi 2018没有该 Python coverage API，应继续使用 xcov native导出，
  不得 fallback到 URG解析。
- `source.annotate` 的源码文本来自项目源文件，coverage annotation 来自 VDB/NPI，不解析 URG HTML。
- `assert.summary` 输出基础覆盖率和 attempts/real successes/without attempts；不输出
  kind/category/severity/failures/incomplete/first_match/file/line。需要完整 assertion
  Markdown 时使用 `export.assert`。
- 找不到 NPI API 支撑的 URG 字段时，不要做 fallback，不要要求 xcov 返回占位字段；应说明该字段做不到。

## 排障

- license/NPI 错误：在沙箱外确认 Verdi/NPI 和 license server。
- action 参数不确定：先用 `xverif_cov_list_actions` 和 `xverif_cov_get_schema`。
- 大结果：设置 limit，必要时 `overflow:"to_file"` 或 output path。
- MCP/LSF/session 问题：读 MCP 或 SDK-free loop 对应 troubleshooting。
