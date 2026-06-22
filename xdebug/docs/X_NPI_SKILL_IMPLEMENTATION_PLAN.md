# x-npi Skill 建设计划

## Summary

- 新建独立 skill：`skills/x-npi`，所有 skill 名称统一使用 `x-npi`；Python import 包因语法限制使用 `x_npi`。
- 目标不是替代 xdebug 实时追踪，而是教 AI 用 Python `pynpi` 做大规模脚本化统计、波形扫描、协议分析和静态 driver/load 分析。
- 首版包含协议分析：APB、AXI、stream；不把 active-driver 近似方案作为首版能力，active causal tracing 仍指向 xdebug/C++ NPI。

## Key Changes

- 用 `skill-creator` 的 `init_skill.py` 初始化 `skills/x-npi`，包含 `SKILL.md`、`agents/openai.yaml`、`scripts/`、`references/`。
- `SKILL.md` 保持轻量，只写任务路由：
  - FSDB value/statistics/window scan。
  - APB/AXI/stream 离线分析。
  - design `trace_driver/load` 静态分析。
  - coverage 可引用现有 xcov/pynpi 模式。
  - active-driver 明确不走 x-npi，转 xdebug。
- `references/` 拆成 4 个文件：
  - `pynpi-runtime.md`：`VERDI_HOME`、`sys.path`、`LD_LIBRARY_PATH`、`npisys.init/end`、stdout/stderr 处理。
  - `waveform-patterns.md`：由 xdebug value/VCT/edge scan 思路转成 Python `waveform.open`、`sig_vec_value_at`、VCT cursor、批量采样模式。
  - `protocol-patterns.md`：由 xdebug APB/AXI/stream analyzer 抽取 Python 状态机模式，包含 clock edge、valid/ready、outstanding、latency、stall/window。
  - `design-trace-patterns.md`：`pynpi.lang.trace_driver_by_hdl2`、`trace_load_by_hdl2`、`DrvLoadStmt` 归一化和 source evidence 输出。
- `scripts/x_npi/` 提供可 import 的固定代码：
  - `runtime.py`：设置 pynpi 路径，并用 `pynpi_lifecycle()` 明确包装 `npisys.init/end` 生命周期；不引入 xdebug/xcov 式 session 概念。
  - `wave.py`：打开 FSDB、时间转换、批量采样、变化遍历、clock edge 扫描。
  - `protocol.py`：APB/AXI/stream transaction extractor 的首版实现。
  - `design.py`：静态 driver/load trace wrapper。
  - `jsonio.py`：稳定 JSON 输出、错误对象和 truncation metadata。
- `scripts/examples/` 提供可直接运行示例：
  - `wave_stats.py`：信号变化次数、first/last change、值分布。
  - `apb_summary.py`：APB read/write 统计和错误事务。
  - `axi_summary.py`：AXI read/write count、latency outlier、outstanding timeline。
  - `stream_summary.py`：valid/ready transfer、stall、packet summary。
  - `trace_driver_summary.py`：静态 driver/load 摘要。
- 更新顶层 README 的 skill 列表，说明 `x-npi` 与 `xdebug` 的分工；不把大量 pynpi 内容塞进现有 `xverif` skill。

## Implementation Flow

- 先从 C++ 代码抽取模式，不照搬接口：
  - `fsdb_scan_utils.cpp` 转成 Python VCT/clock-edge helper。
  - `apb_analyzer.cpp` 转成 APB completion 状态机。
  - `axi_analyzer.cpp` 转成 AXI channel handshake、pending queue、latency/outstanding 统计。
  - `stream_analyzer.cpp` 转成 generic valid/ready/packet/stall analyzer。
- 再写最小 Python helper 包，保持输入是普通 dict/list/path/time，输出是 JSON-friendly dict。
- 每个示例脚本只依赖 `scripts/x_npi` 和 Synopsys `pynpi`，不依赖 xdebug binary。
- 所有 live pynpi/FSDB/daidir 验证命令按用户要求放到沙箱外运行。

## Test Plan

- 静态验证：
  - `quick_validate.py skills/x-npi`。
  - Python import smoke：`PYTHONPATH=skills/x-npi/scripts python -c "import x_npi"`。
  - 对 helper 中纯 Python 状态机做 license-free unit tests。
- live 验证：
  - 用现有 synthetic/real waveform fixture 跑 `wave_stats.py`，对比 xdebug `value.batch_at`、`signal.statistics` 的关键计数。
  - 跑 `apb_summary.py`、`axi_summary.py`、`stream_summary.py`，对比现有 xdebug APB/AXI/stream 回归输出。
  - 跑 `trace_driver_summary.py`，对比 xdebug `trace.driver/load` JSON 的 signal/source/file/line 核心字段。
- 安装验证：
  - `make install-x-npi-skill`。
  - `diff -rq skills/x-npi ~/.codex/skills/x-npi` 和 `diff -rq skills/x-npi ~/.claude/skills/x-npi`。

## Assumptions

- skill 机器名、目录名、metadata name 都使用 `x-npi`。
- Python import 包名使用 `x_npi`，这是 Python 语法限制，不改变 skill 名。
- 首版纳入协议分析，但只承诺离线批量分析；实时因果追踪、active-driver、PVC active check 不纳入 x-npi 首版。
- 不新增 C++ worker，不改 xdebug 行为；xdebug 只作为模式来源和 A/B oracle。
