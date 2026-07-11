# xentry entry decode

xentry 把多拍 byte fragments 按 config 切成 raw field slices。不要让 LLM 自己跨拍拼接或 hex slicing。

## 何时使用

- 用户提供 entry/descriptor/header/WQE/CQE fragments。
- 每拍有 `seq/data/valid_lsb/valid_width`。
- 有字段布局 config，或需要构造 config。
- 需要知道 field 来自哪一拍、哪些 bit。

## 入口

命令行：

```bash
tools/xentry --json '{"api_version":"xentry.v1","action":"decode","config":{},"fragments":[]}'
printf '%s\n' '<json-request>' | tools/xentry --json -
```

## 规则

- config 必须声明 `total_bits`、`fragment_byte_order`、`bit_numbering`、`fields`。
- fragment 必须是 byte fragments，不是任意整数列表。
- xentry 只输出 raw，不做 enum/IP/MAC/协议语义解释。
- 分析时引用 `field.raw_hex` 和 `field.source`。

## 排障

- `ok:false` 先读 config/fragments 错误。
- 跨拍字段异常时检查 byte order、bit numbering、valid range。
- 需要波形 valid/ready 事实时先用 xdebug。
