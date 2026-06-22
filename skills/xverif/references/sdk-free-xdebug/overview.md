# SDK-free xdebug wrapper 总览

SDK-free xdebug wrapper 是非 MCP 的 Python UDS JSONL server/client，用于维护长期 `tools/xdebug --stdio-loop` session。它不需要 MCP SDK，适合脚本、批处理、或必须 LSF 但无法使用 MCP 的场景。

入口：

```bash
tools/xverif-loop-server
tools/xverif-loop-client
```

## 何时优先使用

- 必须使用 LSF，但不能安装或不能使用 MCP SDK。
- 需要 shell/python 脚本直接驱动 xdebug session。
- 需要非交互批处理保持一个长期 `--stdio-loop` backend。
- 不希望把 MCP 当脚本 API。

如果已有 MCP client 且 SDK 可用，交互式 AI 调用仍优先 MCP。只做一次性完整 JSON request 时，用 raw xdebug CLI 即可。

## 能力边界

第一版 SDK-free wrapper 只覆盖 stateful xdebug/xcov session：

- `debug.session.open`
- `debug.session.list`
- `debug.session.close`
- `debug.query`
- `cov.session.open/list/close/query`

它不覆盖 xbit/xentry/xloc/xberif/xsva，也不等价于完整 MCP 工具集。

## 与 raw CLI 的区别

raw CLI：

```text
tools/xdebug --json -   # 每次一个短进程
```

SDK-free wrapper：

```text
client -> UDS socket -> xverif-loop-server -> tools/xdebug --stdio-loop
```

wrapper 负责 alias、session manager、stdio-loop 进程和 LSF job cleanup。
