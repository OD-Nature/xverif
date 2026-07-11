# xsva

SystemVerilog Assertion 语义编译工具。

把 SVA 从文本语法编译为结构化 IR（Surface → Sequence → Timeline），所有解释从 IR 生成。
`explain` 默认展示面向用户的英文语义摘要。内部仍保留精确
`match_paths` / `obligations`，但范围 delay、range suffix、repeat 和高级 sequence
不会在用户解释里展开成多条候选 path。

## 命令

```bash
xsva list    --file <file>                       # 列出所有 property/assertion
xsva scan    --file <file>                       # 语法构造分布统计
xsva explain --file <file> --property <name>      # 文本解释
xsva parse   --file <file> --property <name> --emit surface-ir|sequence-ir|timeline-ir
```

## 示例

```bash
python -m xsva list --file tests/golden_ir/simple_impl/input.sva
python -m xsva explain --file tests/golden_ir/simple_impl/input.sva --property p_test
python -m xsva parse --file tests/golden_ir/simple_impl/input.sva --property p_test --emit timeline-ir
```

范围和高级语法示例：

```systemverilog
property p_first;
  req |-> first_match(##[1:4] ack) ##1 done;
endproperty
```

解释输出会说明：`ack must be the first match at cycle +1 to +4; done must be true 1 clk after that first ack.`

```systemverilog
property p_intersect;
  req |-> (a ##1 b) intersect (c ##1 d);
endproperty
```

解释输出会按 `Sequence 1`、`Sequence 2` 和 `Relation` 分别说明两个 sequence 的内部时序以及二者必须同时开始、同时结束。

## 测试

```bash
pytest --xverif-gate fast --xverif-suite xsva.core
pytest --xverif-gate regression --xverif-suite xsva.cli
pytest --xverif-gate nightly --xverif-suite xsva.vcs
```
