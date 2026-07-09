# xbit bit 计算

xbit 是确定性 bit/value/expression calculator。遇到 SV literal、slice、signed、mask、表达式或 expected value 比较时必须使用，不要心算。

## 何时使用

- 进制转换：hex/bin/decimal/SV literal。
- signed/unsigned：如 `8'shff`。
- bit slice/index、concat/repeat、trunc/zext/sext。
- popcount、onehot、mask、gray code。
- 常量表达式、valid-ready 条件、opcode/field 比较。
- xdebug 返回 `xbit_hints.commands[]` 或 `slice_hint`。

## MCP 入口

默认省略 `output_format`，使用适合 AI 阅读的 xout。脚本需要字段读取时才显式请求 JSON。

```json
{"tool":"xverif_bit_convert","args":{"value":"8'shff","signed":true}}
```

```json
{"tool":"xverif_bit_slice","args":{"value":"32'hdead_beef","msb":15,"lsb":8}}
```

```json
{"tool":"xverif_bit_eval","args":{"expr":"valid && ready","vars":{"valid":"1'b1","ready":"1'b0"}}}
```

## 读取规则

- 先看 `ok`。
- 结果读 `result.width/result.unsigned/result.signed_value/result.hex/result.bin/result.sv`。
- 条件读 `result.bool` 或 `matched`。
- `known:false` 不能当确定值。
- 错误时读 `error.code`，修输入宽度、literal 或表达式。

## 边界

xbit 不读 RTL、不做 elaboration、不查波形。需要事实先用 xdebug，拿到值后再用 xbit 算。
