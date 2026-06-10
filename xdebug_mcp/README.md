# xdebug MCP / LSF backend

> **MCP 入口已迁移至 [`xverif_mcp`](../xverif_mcp/README.md)**。`xdebug_mcp` Python 包已删除，仅保留 `xdebug_lsf` 子包（LSF 协议和 bsub 工具库，被 `xverif_mcp` 依赖）。

`xdebug_lsf/` 提供：
- `protocol.py` — `JsonlProcess`：JSONL 子进程协议（stdin/stdout JSON lines + request/response 匹配）
- `bsub.py` — `BsubRunner` / `BsubOptions`：bsub -I 命令构建和 LSF job 启动
- `fake_bsub.py` — 本地测试用 fake bsub
- `doctor.py` — LSF 链路诊断工具

## MCP 使用

MCP 入口统一为 `tools/xverif-mcp`（`python -m xverif_mcp.server`）。配置见 [`xverif_mcp/README.md`](../xverif_mcp/README.md)。

## 环境要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Verdi / VCS | V-2023.12-SP2 及以上 | 需 NPI 库，设置 `VERDI_HOME` |
| GCC | 5.0+ | 编译 xdebug C++ 代码 |
| Python | 3.11+ | 推荐 conda 环境 |
| pip | `mcp[cli]` | FastMCP + MCP Inspector |

## 测试

```bash
make -C xdebug PYTHON=python3 mcp-test
PYTHON=python3 XVERIF_MCP_FAKE_LSF=1 tools/xverif-lsf-doctor --fake
```

测试里的 fake LSF 不需要真实 `bsub`，覆盖 ready 噪声、多 session 并行、同 session 串行、session crash 隔离和 xout/json/envelope 返回。
