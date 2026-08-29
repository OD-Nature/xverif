# rc.generate 已确认语法与渲染问题

日期：2026-07-16
状态：已实现，待完整回归

本文记录 `xdebug` action `rc.generate` 生成 nWave `signal.rc` 时必须满足的语法和顺序合同。它是待实现要求，不表示当前 generator 已符合。

## 1. windowTimeUnit 必须固定且位于文件最前

生成文件的第一条有效 RC 语句必须是：

```rc
windowTimeUnit 1ns
```

要求：

- 单位固定为 `1ns`；输入配置不得包含 `window_time_unit`，出现即报错。
- 它必须在 `fileTimeScale`、`signalSpacing`、`zoom`、`cursor`、`marker`、`userMarker`、`addGroup` 与所有 signal/expr 语句之前。
- 文件头注释是否保留由实现决定；若保留，`windowTimeUnit 1ns` 必须是第一条非注释、可执行 RC 语句。

这保证 marker、cursor、zoom 等时间位置统一按 1ns 解释。

## 2. userMarker 的时间数值与语法

marker 必须按下列完整形式输出：

```rc
userMarker 10347.651 test ID_CYAN5 long_dashed
```

字段含义与顺序固定为：

```text
userMarker <time_in_1ns_unit> <marker_name> <color> <linestyle>
```

要求：

- `<time_in_1ns_unit>` 是相对于 `windowTimeUnit 1ns` 的数值，不在 `userMarker` 参数中重复加 `ns` 后缀。
- 例中 `10347.651` 表示 10347.651 ns。
- marker 名称有空白或特殊字符时仍需按 RC 语法正确引用；无空白名称保持未加引号的简洁形式。
- color 和 linestyle 必须保留调用方给出的完整 token，例如 `ID_CYAN5` 与 `long_dashed`。

## 3. 表达式先创建，随后在 group 内加入 signal list

仅创建 expression 不足以使其显示在 nWave signal list；但 `addExprSig` 本身不属于 group 内容。expression 必须先在目标 group 的 `addGroup` 之前创建，随后由该 group 内的 `addSignal` 加入列表：

```rc
addExprSig -b 1 -n UU req_fire "xxx"

addGroup "G2"
addSignal -h 18 /req_fire
```

要求：

- `addExprSig` 使用既有 bit size、notation、expr name 和 expression 渲染逻辑。
- 所有表达式创建语句在对应 group 的 `addGroup` 之前输出；它们不需要被 `addGroup` 包围。
- group 开始后，再输出 `addSignal -h 18 /<expr_name>`；`/<expr_name>` 是表达式名称在 RC signal list 中的路径。
- `-h 18` 为固定显示高度。
- 一条 expression 对应且只对应一条 group 内的 addSignal。addExprSig 与 addSignal 之间允许出现该 group 的 `addGroup`，但不允许跨到另一个 group。
- 普通信号和 expression signal 的 `addSignal` 都必须位于其所属 group 的有效范围内。

## 4. group 的隐式作用域

group 使用以下语法开始：

```rc
addGroup "G2"
```

其后的 `addSignal`（包含普通 signal 和 expression 的 `/name` addSignal）均属于当前 group，直到下一个 `addGroup` 出现：

```rc
addExprSig -b 1 -n UU req_fire "xxx"

addGroup "G1"
addSignal -h 18 /clk
addSignal -h 18 /rst_n

addGroup "G2"
addSignal -h 18 /req_fire
addSignal -h 18 /req_valid
```

要求：

- 不通过额外 group-id 参数指定成员关系；成员关系由语句顺序表达。
- renderer 必须先输出各 expression 的 `addExprSig` 创建语句；随后对每个 group 连续输出：`addGroup`、该 group 的普通 signal 与 expression 对应 `addSignal`，再进入下一个 group。
- 进入下一个 group 前不得插入属于前一 group 的 signal。
- subgroup 若继续支持，也必须遵循对应 RC 的顺序作用域；本问题首先锁定顶层 `addGroup` 行为。

## 5. 当前实现差异与后续实现面

已核对 `xdebug/src/waveform/service/rc_generator.cpp`：

1. 已移除配置化 `window_time_unit`；renderer 固定在首条非注释语句输出 `windowTimeUnit 1ns`。
2. 已将 expression 创建与 group signal-list 渲染分开：全部 `addExprSig` 在第一个 group 前，所属 group 再输出 `addSignal -h 18 /<expr_name>`。
3. group 内 signal list 按 group header、普通 signal、expression signal、子 group 的顺序连续输出；expression create 语句不会插入 group 内。

建议新增 unit/contract 覆盖：

1. `windowTimeUnit 1ns` 是第一条非注释语句，且配置中给出其它 time unit 时仍固定为 1ns。
2. 输入 marker `{time: "10347.651ns", name: test, color: ID_CYAN5, linestyle: long_dashed}` 时精确产生示例行。
3. 每个 `addExprSig` 位于目标 `addGroup` 之前，且目标 group 内恰有一条 `addSignal -h 18 /<expr_name>`；两者之间允许且必须出现该 group 的 `addGroup`。
4. 两个 group 含普通和 expression signal 时，验证所有 expression create 语句都在第一个 group header 前；从 `addGroup "G2"` 到下一 `addGroup` 前的全部 addSignal 都属于 G2，且没有跨组语句。
5. 现有 rc.generate response/schema、skill 示例和 `doc/signal_rc_syntax.md` 必须在实现后同步为真实行为。
