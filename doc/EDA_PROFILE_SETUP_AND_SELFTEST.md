# EDA 双版本 Profile：配置、安装与自检指南

本指南描述 Verdi 2018 / 2023 双 profile 的环境配置、新用户安装流程、
自检层级和故障排查。两份 README 只保留概览；本文是唯一详细来源。

所有真实 VCS、Verdi、NPI、FSDB、VDB 和 license 动作都应在已配置 EDA
环境的宿主机或计算节点执行。

## 新用户安装与自检

下面的流程以 Bash 为例。所有真实 VCS、Verdi、NPI、FSDB、VDB 和 license
动作都应在已配置 EDA 环境的宿主机或计算节点执行。

### 1. 前置依赖

| 组件 | 基础要求 | 用途 |
|---|---|---|
| Linux x86-64 | 可运行目标 Synopsys安装 | EDA/NPI runtime |
| GNU Make | 推荐 4.x | 构建和自检入口 |
| GCC/G++ | 支持 C++11；xcov native worker还需 C++17 | xdebug、2018 xcov worker |
| Python | 推荐 3.11；xcov/xsva最低 3.10 | CLI、测试、MCP |
| VCS/Verdi | O-2018.09-SP2 或 V-2023.12-SP2 profile | fixture、daidir/FSDB/VDB、NPI |

安装常规 Python依赖：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r xdebug/tests/requirements.txt
python -m pip install "mcp[cli]" numpy Pillow
```

说明：

- `xbit`、`xentry`、`xloc` 和 `xeda-runner` 的核心逻辑主要使用标准库。
- `xwaveform` 需要 `numpy` 和 `Pillow`，可选绘图功能还需要 `matplotlib`。
- 只使用 CLI、不启动 MCP 时，可以不安装 `mcp[cli]`。

### 2. Clone 后设置统一入口

```bash
git clone <your-fork-or-upstream-url> xverif
cd xverif
export XVERIF_HOME="$PWD"
export PATH="$XVERIF_HOME/tools:$PATH"
```

多工作树并存时必须确认：

```bash
test "$XVERIF_HOME" = "$PWD"
```

否则新二进制可能误读另一个工作树的 schema、examples 或 engine。

### 3. 配置 Verdi 2018

```bash
export XVERIF_EDA_PROFILE=verdi-2018
export VERDI_HOME=<Verdi_O-2018.09-SP2安装目录>
export PATH=<VCS_O-2018.09-SP2安装目录>/bin:"$VERDI_HOME/bin:$PATH"

# 使用本地 license配置；不要把真实值提交到仓库
export SNPSLMD_LICENSE_FILE=<synopsys-license配置>
```

2018 profile行为：

- xdebug 使用旧 C++ ABI和 Verdi 2018 NPI兼容 shim。
- xcov 使用常驻 C++ native coverage worker，不依赖该版本缺失的
  `pynpi.cov`。
- `tools/xdebug` / `tools/xcov` 会在各自子进程内注入对应 NPI library路径，
  不需要全局修改 `LD_LIBRARY_PATH`。

构建并运行 profile 自检：

```bash
make
python3 -m pip install -e .
pytest --xverif-gate fast
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-prepare all-generated
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-gate regression -n auto
```

### 4. 配置 Verdi 2023

```bash
export XVERIF_EDA_PROFILE=verdi-2023
export VERDI_HOME=<Verdi_V-2023.12-SP2安装目录>
export PATH=<VCS_2023安装目录>/bin:"$VERDI_HOME/bin:$PATH"
export SNPSLMD_LICENSE_FILE=<synopsys-license配置>

make
python3 -m pip install -e .
pytest --xverif-gate fast
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-prepare all-generated
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-gate regression -n auto
```

2023 profile保留原作者的 Python `pynpi.cov` backend，不会自动切换到
2018 native worker。当前仓库已完成 2023自检入口和构建路径；正式交付前仍需在
安装了 2023 EDA的机器执行一次真实 fixture prepare 与 regression gate。

### 5. 自检层级

| 命令 | 是否需要 EDA/license | 覆盖范围 |
|---|---|---|
| `pytest --xverif-gate fast` | 否 | hermetic 单元、合同与静态检查 |
| `pytest --xverif-prepare all-generated` | 是 | 为当前 EDA profile 显式生成仓内 fixture |
| `pytest --xverif-gate regression -n auto` | 是 | 确定性回归及缓存 fixture 消费 |
| `pytest --xverif-gate nightly -n auto` | 是 | VIP、可选 realdata 与真实 LSF |

上述 fast → prepare → regression 流程是别人 clone 后首先应运行的基础健康检查。它会从仓内 SV源码生成
fixture，不依赖 GPIO、xip 或其它外部工程。扩展回归可能额外要求 numpy、VIP、
真实 LSF或外部 realdata；缺少这些依赖不能冒充通过。

已在 Verdi/VCS O-2018.09-SP2 实测通过的基础自检包括：xdebug schema、unit、
contract、session、MCP direct/fake-LSF，以及 xcov 2-test真实 VDB的
line/toggle/branch、Verdi Score、raw weighted coverage和正常 close/checkin。

### 6. License feature要求

2018实机调试已有证据确认：

| Feature | 场景 |
|---|---|
| `Verdi` | Verdi/NPI初始化、设计/波形查询 |
| `VCSTools_Net` | coverage NPI/VDB访问 |

VCS compile/runtime feature以及不同合同包中的别名可能不同，本仓库不猜测或硬编码。
应由 EDA管理员或实际 checkout日志确认。不要在 issue、日志或提交中记录 license
server地址、端口、完整 ID或凭据。

### 7. MCP配置

CLI自检通过后再启动 MCP：

```bash
tools/xverif-mcp
```

IDE/agent启动的 MCP进程不一定继承交互 shell环境。至少要显式传入：

```text
XVERIF_HOME
XVERIF_EDA_PROFILE
VERDI_HOME
PATH
PYTHONPATH
SNPSLMD_LICENSE_FILE（环境需要时）
```

完整 `.mcp.json`、direct/LSF和 timeout配置见
[`xverif_mcp/README.md`](../xverif_mcp/README.md)。也可以在确认环境中不含不应落盘的
凭据后使用 `sync_agent_env.py`。

## 故障排查

### `VERDI_HOME environment variable is not set`

确认 profile和安装目录来自同一 EDA版本：

```bash
echo "$XVERIF_EDA_PROFILE"
test -d "$VERDI_HOME/share/NPI/inc"
find "$VERDI_HOME/share/NPI/lib" -maxdepth 1 -type d
```

### `failed to import pynpi: cannot import name cov`

如果使用 Verdi 2018，这是选错 backend/profile：

```bash
export XVERIF_EDA_PROFILE=verdi-2018
make -C xcov native
```

2018必须走 native worker；不要 fallback到 URG HTML或伪造 coverage数据。

### `Failed to find Verdi resource directory (etc/) in LD_LIBRARY_PATH`

常规调用请使用 `tools/xcov`。直接运行 Python Dispatcher/native backend时，调用方
必须显式把当前 Verdi NPI lib目录加入该进程的 `LD_LIBRARY_PATH`。

### `NATIVE_WORKER_NOT_FOUND`

```bash
XVERIF_EDA_PROFILE=verdi-2018 make -C xcov native
test -x xcov/native/xcov-npi-worker
```

### `INVALID_VDB` 或 `npi_cov_open` 长时间无响应

先检查输入是否为完整 VDB，而不是空壳目录：

```bash
test -d <vdb>/snps/coverage/db
find <vdb>/snps/coverage/db -type f -print -quit
```

空目录是数据错误，不应继续等待 license。

### NPI/license初始化失败

按以下顺序排查：

1. `VERDI_HOME` 与目标 profile是否一致。
2. VDB/FSDB/daidir是否完整且可读。
3. 当前节点能否访问 license服务。
4. `Verdi` / `VCSTools_Net` 或本地对应 feature能否 checkout。
5. session close后 license占用是否回落。

### MCP session open timeout或 UDS `EPERM`

- UDS/TCP/file transport和真实进程通信测试必须在允许 bind/IPC的宿主环境运行。
- 大 VDB可提高 MCP startup/request timeout，但不能静默改 backend或 transport。
- 先用 CLI、fixture validation 和 focused suite 区分 EDA/NPI问题和 MCP外层 timeout。

### 测试报告 fixture缺失

显式准备并校验当前 profile 的 fixture：

```bash
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-prepare all-generated
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-fixture-validation --xverif-all-fixtures
```

`regression`、`nightly`、VIP、真实 LSF和 realdata仍可能要求额外环境；查看
具体失败命令和 SKIP原因，不要把沙箱失败直接当作产品回归。
构建仍由 Makefile 负责；测试只有根级 catalog-driven pytest plugin 一个公开入口。首次使用先安装测试包，普通 gate 只消费 `.xverif-test-cache/` 中已经发布的数据库，不会隐式运行 VCS/simv。

```bash
python3 -m pip install -e .
make -C xdebug
pytest --xverif-gate fast
export XVERIF_TEST_EXECUTION_ENV=host  # 仅在已经进入沙箱外 host 后设置
pytest --xverif-gate regression -n auto
pytest --xverif-gate nightly -n auto
```

显式准备或校验数据库 Fixture：

```bash
pytest --xverif-prepare all-generated
pytest --xverif-fixture-validation --xverif-all-fixtures
pytest --xverif-fixture-clean
pytest --xverif-results-clean
```

`fast` 是无外部 EDA 进程的 hermetic 门禁；`regression`、`nightly`、fixture prepare/validation 涉及 NPI、MCP 进程或 VCS 时必须在沙箱外执行。`XVERIF_TEST_EXECUTION_ENV=host` 只记录执行证据，不会提升权限或切换环境。cache miss 对 required suite 是 ERROR，并给出精确 prepare 命令；不会自动 prepare、SKIP 或切换 backend。裸 `pytest` 是 usage error。完整合同见 [`doc/agents/xdebug/tests.md`](agents/xdebug/tests.md)。

