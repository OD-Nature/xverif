# Coverage Analysis Patterns

使用 Verdi Python coverage wrapper 查询 VCS/Verdi coverage database，例如 `simv.vdb` 或 `merged.vdb`。这类脚本适合离线批量导出 coverage summary、holes、scope metrics 和 functional coverage bins。

## Runtime

coverage API 入口：

```python
from pynpi import cov

db = cov.open("simv.vdb")
```

仍然必须先通过 `npisys.init(...)` 初始化；使用 skill helper 时：

```python
from x_npi.runtime import pynpi_lifecycle
from x_npi.coverage import open_covdb, close_covdb, merged_test_handle, coverage_items

with pynpi_lifecycle([sys.argv[0]]):
    db = open_covdb("simv.vdb")
    try:
        test = merged_test_handle(db)
        rows = coverage_items(db, test=test, metrics=["line", "toggle"])
    finally:
        close_covdb(db)
```

## Common Handles

常用 handle 方法：

| API | 用途 |
| --- | --- |
| `db.test_handles()` | 列出 coverage tests |
| `db.instance_handles()` | 顶层 instance handles |
| `inst.instance_handles()` | 子层次 |
| `inst.line_metric_handle()` | line coverage metric |
| `inst.toggle_metric_handle()` | toggle coverage metric |
| `inst.branch_metric_handle()` | branch coverage metric |
| `inst.condition_metric_handle()` | condition coverage metric |
| `inst.fsm_metric_handle()` | FSM coverage metric |
| `inst.assert_metric_handle()` | assertion coverage metric |
| `test.testbench_metric_handle()` | functional coverage metric |
| `hdl.child_handles()` | coverage object 或 bin 子节点 |
| `hdl.covered(test)` / `hdl.coverable(test)` | 覆盖对象数和可覆盖对象数 |
| `hdl.count(test)` | hit/sample count |
| `hdl.file_name()` / `hdl.line_no(test)` | source evidence |

## Code Coverage

遍历 code coverage 时，从 instance 进入 metric handle，再递归 `child_handles()` 到 object/bin：

```python
with pynpi_lifecycle([sys.argv[0]]):
    db = open_covdb(args.vdb)
    try:
        test = merged_test_handle(db)
        rows = coverage_items(
            db,
            test=test,
            metrics=["line", "toggle", "branch", "condition", "fsm", "assert"],
            scope=args.scope,
        )
    finally:
        close_covdb(db)
```

每行推荐输出：

```json
{
  "metric": "line",
  "type": "npiCovStmtBin",
  "scope": "top.u_dut",
  "name": "stmt_12",
  "full_name": "top.u_dut.stmt_12",
  "covered": 0,
  "coverable": 1,
  "missing": 1,
  "coverage_pct": 0.0,
  "count": 0,
  "status": ["not_covered"],
  "evidence": {"file": "rtl/dut.sv", "line": 12}
}
```

## Functional Coverage

functional coverage 从 test 的 `testbench_metric_handle()` 进入：

```python
rows = coverage_items(db, test=test, metrics=["functional"])
```

Functional hierarchy 通常是：

- covergroup
- coverpoint 或 cross
- bin

cross bin 表示一个组合，不要拆成多个独立 bin。

## Semantics

- coverage pct 必须用 `covered / coverable`；`count` 是 hit/sample count，不是覆盖率百分比。
- hole 一般是 `covered < coverable` 或 `missing > 0`。
- 保留 `excluded`、`unreachable`、`illegal`、`attempted` 等 status flags；这些状态会改变 hole 的解释。
- bin 没有 file/line 时，继承最近父 coverage object 的 source evidence，并在输出中记录 `evidence_source.inherited=true`。
- 真实 coverage 查询需要 Synopsys license；涉及真实 VDB 的验证按用户要求在沙箱外运行。
