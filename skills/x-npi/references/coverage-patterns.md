# Coverage Analysis Patterns

使用 Verdi Python coverage wrapper 查询 VCS/Verdi coverage database，例如 `simv.vdb` 或 `merged.vdb`。这类脚本适合离线批量导出 coverage summary、holes、scope metrics 和 functional coverage bins。

本页只适用于提供 Python `pynpi.cov` 的 Verdi版本。O-2018.09-SP2没有该接口，
应使用 `XVERIF_EDA_PROFILE=verdi-2018` 的 xcov native worker。不要在2018环境
尝试 import失败后改解析 URG HTML。

## When To Switch From xcov

优先用 xcov 做交互式查询：

- `scope.summary`、`scope.children`、`code_coverage.summary`、`code_coverage.holes` 看层次覆盖率。
- `export.code_coverage`、`export.function_coverage`、`export.assert` 导出 Markdown 给 AI/人审阅。

切到 x-npi/pynpi 的场景：

- 需要 JSON/CSV/数据库等非 Markdown 自定义输出。
- 需要跨多个 VDB 或多个 report 做二次统计。
- 需要自定义 hierarchy pruning、bin 聚合、排序或阈值策略。
- 需要把 coverage 与 FSDB、RTL 静态结构或项目自定义映射表关联。
- xcov 明确说明某个 URG 字段没有稳定 NPI API，不提供接口；不要从 URG HTML 反解析。

如果目标是复现 Verdi hierarchy `Score`，先分别计算各有效 metric的百分比，再做
等权平均；所有 bin合并后的 `covered/coverable` 只是 raw weighted coverage，二者
应分别输出。

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

直接使用 pynpi API 时，基本遍历形态如下。真实脚本应把 `VERDI_HOME`、`npisys.init/end`
放进 `pynpi_lifecycle`，并在 finally 中释放 handle/关闭 db。

```python
from pynpi import cov

db = cov.open("merged.vdb")
test = None
for th in db.test_handles():
    test = th if test is None else cov.merge_test(test, th)

for inst in db.instance_handles():
    metric = inst.toggle_metric_handle()
    if not metric:
        continue
    stack = list(metric.child_handles() or [])
    while stack:
        hdl = stack.pop()
        row = {
            "type": hdl.type(),
            "name": hdl.name(),
            "full_name": hdl.full_name(),
            "covered": hdl.covered(test),
            "coverable": hdl.coverable(test),
            "count": hdl.count(test),
            "file_name": hdl.file_name(),
            "line_no": hdl.line_no(test),
        }
        children = hdl.child_handles() or []
        stack.extend(children)
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

自定义导出时，按 covergroup 分块，再按 coverpoint/cross 下的 bin 输出。bin 自身没有
file/line 时，使用最近父 covergroup/coverpoint/cross 的 evidence；不要编造 bin 的
源码位置。

Functional hierarchy 通常是：

- covergroup
- coverpoint 或 cross
- bin

cross bin 表示一个组合，不要拆成多个独立 bin。

## URG-Aligned Summary Semantics

- code coverage summary 要按 URG dashboard 的计分对象聚合，不能把中间层 object 和 leaf bin 同时相加。
- Line 使用 `npiCovStmtBin`，Cond 使用 `npiCovConditionBin`，Toggle 使用 `npiCovToggleBin`，Branch 使用 `npiCovBranchBin`，FSM 使用 `npiCovTransBin`，Assert 使用 `npiCovAssert`、`npiCovCoverProperty`、`npiCovCoverSequence`。
- 排除 `coverable < 0` 或 `covered < 0` 的统计辅助 bin，例如 assertion 的 Attempt/Success/Failure/Incomplete bins。
- code coverage pct 必须用 `covered / coverable`；`count` 是 hit/sample count，不是覆盖率百分比。
- functional Group 分数不是简单的 covergroup raw `covered / coverable`。URG group score 按 direct coverpoint/cross 的 coverage percentage 做平均；`x_npi.coverage.coverage_summary()` 的 `functional_groups[*].coverage_pct` 使用这个规则，raw ratio 保留在 `raw_covered/raw_coverable/raw_coverage_pct`。
- hole 一般是 `covered < coverable` 或 `missing > 0`。
- 保留 `excluded`、`unreachable`、`illegal`、`attempted` 等 status flags；这些状态会改变 hole 的解释。
- bin 没有 file/line 时，继承最近父 coverage object 的 source evidence，并在输出中记录 `evidence_source.inherited=true`。
- 真实 coverage 查询需要 Synopsys license；涉及真实 VDB 的验证按用户要求在沙箱外运行。
