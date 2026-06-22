# xberif 项目 context

xberif 管理验证项目知识上下文：短 summary cards、detail markdown、brief/context。它不读 RTL/FSDB、不做 bit 计算、不还原日志位置。

## 何时使用

- 初始化 BT/IT/ST/SoC 项目 context。
- 生成或查询 `.xberif/cards.json`、`.xberif/details/*.md`。
- 构造 agent brief/context。
- 检查或修复 card/detail schema、metadata、section 合同。

## 入口

优先 MCP `xverif_context_*`。命令行：

```bash
xberif config init --kind bt
xberif init --model opus
xberif status
xberif validate
xberif list-topics
xberif brief --mode debug
xberif get backpressure
xberif detail backpressure
```

## 使用规则

- `config init` 只生成配置，不生成 `.xberif/` 状态。
- 真实生成必须显式传 `--model`。
- 默认先读 brief/card；只有需要 evidence 或展开时再读 detail。
- 不要直接编辑 `.xberif` 状态文件；用 xberif 命令维护。

## 排障

- `generated_raw`：raw cards/details 已生成但 catalog 缺失，先 `repair-catalog`。
- list/brief 查不到 topic：跑 `status`、`repair-catalog`、`validate`。
- Claude guard 阻止 `.xberif` 文件访问是预期；通过 xberif 命令读取。
