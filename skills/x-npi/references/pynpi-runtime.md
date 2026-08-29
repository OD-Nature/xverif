# pynpi 运行时模式

## 启动

优先使用随 skill 提供的 runtime helper：

```python
from x_npi.runtime import pynpi_lifecycle

with pynpi_lifecycle([sys.argv[0]]):
    ...
```

访问 design DB 时：

```python
with pynpi_lifecycle([sys.argv[0], "-dbdir", daidir], load_design=True):
    ...
```

对于同时使用 design 和 FSDB 的脚本，只有当所用 Python API 需要 design binding 时才同时传入 `-dbdir` 和 `-ssf`。普通波形扫描只需要 `npisys.init([argv0])` 加 `waveform.open(fsdb)`。

## 环境

`VERDI_HOME` 必须指向 Synopsys Verdi 安装目录。helper 会把下面路径加入 `sys.path`：

```text
$VERDI_HOME/share/NPI/python
```

helper 只接受显式参数或标准环境变量 `VERDI_HOME`，不会静默读取项目私有替代变量。

## 查询当前安装版本的 API

当文档记忆与本机版本可能不一致，直接查看：

```text
$VERDI_HOME/share/NPI/python/pynpi/
```

可以搜索模块、类和方法定义，例如 waveform 时间归并遍历对应
`pynpi/waveform.py` 的 `TimeBasedHandle`。检查构造、`add`、`iter_start`、
`iter_next`、`get_value` 和结束方法的真实返回约定后再调用。不要因为没记住 API
就改用另一种数据源或 transport；查看安装包是当前 Verdi API 的正式查证方式，不是 fallback。

如果进程无法加载共享库，需要在启动 Python 之前设置 `LD_LIBRARY_PATH`。不要等 Python 已经启动后再尝试修复 `LD_LIBRARY_PATH`。

## 输出规范

NPI 可能在初始化后延迟向文件描述符 1 写 banner。JSON 工具必须在整个进程级 NPI 生命周期外层使用 `json_stdout_quarantine()`：native FD1 永久导向 stderr，最终 JSON 通过保存的原始 stdout 写出。只在 `init/end` 调用附近临时重定向不足以阻止延迟污染。

使用：

```python
from x_npi.jsonio import ok, error, print_json
from x_npi.runtime import json_stdout_quarantine

with json_stdout_quarantine() as json_stream:
    ...
    print_json(ok("wave_stats", summary={"count": 1}), json_stream)
```

来保持脚本输出稳定。

## 失败处理

在 JSON 中使用明确错误码：

```json
{"ok": false, "action": "wave_stats", "error": {"code": "FAILED", "message": "..."}}
```

常见失败：

- 缺少 `VERDI_HOME`。
- license 不可用。
- FSDB 不存在或不可读。
- 信号路径不匹配。
- `-dbdir` 不是有效的 Verdi/VCS 数据库，导致 `npisys.load_design` 失败。
