# xloc

`xloc` 是给 LLM debug agent 使用的 UVM 日志位置压缩与恢复工具。

它回答的问题很窄：

- 这个 `L_XXXXXXXX` 对应哪个文件的哪一行？
- 这段仿真日志里哪些位置报错最多？
- 这个 loc_id 附近源码是什么样的？

它明确不做：

- 不分析 RTL 逻辑
- 不读 FSDB 波形
- 不查设计层次结构
- 不做仿真或 formal

## 核心思路

UVM 仿真日志中大量出现这种内容：

```text
UVM_ERROR <project-root>/tb/env/scoreboard.sv(238) @ 100ns: packet mismatch
```

对 LLM 来说，`<project-root>/tb/env/scoreboard.sv(238)` 消耗 token 但大部分时候决策价值很低。

`xloc` 把它变成：

```text
UVM_ERROR L_00000001 @ 100ns: packet mismatch
```

当 LLM 需要知道具体位置时，调用 `xloc resolve L_00000001` 还原。

## Quick Start

默认输出为 `xout` 结构化文本；需要脚本解析时，`resolve/context/stats` 可加 `--json`。

```bash
pytest --xverif-gate fast --xverif-suite xloc.unit

# 用一个手动构造的 JSONL 试一下
echo '{"loc_id":"L_00000001","file":"tb/test.sv","line":42,"msg_id":"ERROR_TEST"}' > /tmp/test.xloc.jsonl
tools/xloc resolve L_00000001 --map /tmp/test.xloc.jsonl
tools/xloc resolve L_00000001 --map /tmp/test.xloc.jsonl --json
```

### Shell 命令入口

为了在任意目录和非交互 shell 中稳定调用，建议把仓库 `tools/` 加入 `PATH`。下面示例里的 `<xverif-root>` 表示本仓库根目录，请按本机实际路径替换。

Bash / Zsh：

```bash
export XVERIF_HOME=<xverif-root>
export PATH="$XVERIF_HOME/tools:$PATH"
```

Tcsh：

```tcsh
setenv XVERIF_HOME <xverif-root>
setenv PATH "$XVERIF_HOME/tools:$PATH"
```

配置后可以直接使用：

```bash
xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
xloc stats out/sim.log
```

## Commands

### resolve — 还原源码位置

```bash
xloc resolve L_00000005 --map out/sim.log.xloc.jsonl
```

输出：

```text
loc_id:  L_00000005
file:    tb/simple_test.sv
line:    3
msg_id:  PKT_MISMATCH
```

### context — 查看源码上下文

```bash
xloc context L_00000005 --map out/sim.log.xloc.jsonl --before 5 --after 5
```

先 resolve，再打印目标行附近源码，目标行以 `>>>` 标记。

`--before` / `--after` 默认各 20 行。

### stats — 统计热点位置

```bash
xloc stats out/sim.log --top 20
```

自动查找同目录下的 `sim.log.xloc.jsonl`（或通过 `--map` 指定）。

输出：

```text
loc_id          count  file                            msg_id
L_00000001        127  tb/scoreboard.sv                PKT_MISMATCH
L_00000002         31  tb/monitor.sv                   BAD_PKT
...
27 unique locations, 320 total occurrences
```

### annotate — 给日志加注释

```bash
xloc annotate out/sim.log --map out/sim.log.xloc.jsonl
```

在 log 中每个首次出现的 loc_id 前插入一行：

```text
[loc] L_00000001 -> tb/test.sv:42
```

输出到 stdout，可重定向到文件。

## UVM 集成

### 在你的验证环境中使用

将仓库中 `sv/xloc_pkg.sv` 和 `sv/xloc_report_server.sv` 两个文件复制到你的验证环境，然后在 testbench 顶层注册：

```systemverilog
import xloc_pkg::*;

xloc_report_server loc_svr;

initial begin
  loc_svr = new();
  loc_svr.copy(uvm_coreservice_t::get().get_report_server());
  uvm_coreservice_t::get().set_report_server(loc_svr);
end
```

仿真后产物：

- `sim.log` — 路径已替换为 `L_XXXXXXXX`
- `sim.log.xloc.jsonl` — sidecar 映射文件

可以通过 `set_map_path("custom/path.jsonl")` 自定义 JSONL 输出路径。

### 机制

- loc_id 使用递增序列号：`L_%08X`（零碰撞）
- 通过 static 关联数组去重：同一 file:line:msg_id 只生成一次
- JSONL 逐行追加写入，仿真中断不丢数据

## Vim gf 跳转

`xloc` 提供一个 Vim 插件，让你在打开 `sim.log` 时把光标放在 `L_XXXXXXXX` 上直接按 `gf`，跳到 `sim.log.xloc.jsonl` 记录的源码 `file:line`。

安装方式任选一种：

```vim
" 在 ~/.vimrc 中 source 仓库内插件
source <xverif-root>/xloc/vim/plugin/xloc.vim
```

或复制到 Vim 插件目录：

```bash
mkdir -p ~/.vim/plugin
cp <xverif-root>/xloc/vim/plugin/xloc.vim ~/.vim/plugin/xloc.vim
```

固定 map 规则：

```text
<run-dir>/sim.log
<run-dir>/sim.log.xloc.jsonl
```

如果 JSONL 里的 `file` 是相对路径，建议在 `~/.vimrc` 设置工程根目录：

```vim
let g:xloc_repo_root = "<project-root>"
```

插件默认只在 `*.log` 且旁边存在 `<log>.xloc.jsonl` 时启用 buffer-local `gf`，不会全局覆盖普通源码文件里的 `gf`。如需关闭自动映射：

```vim
let g:xloc_auto_enable = 0
```

关闭自动映射后仍可手动执行：

```vim
:XlocGF
```

查找 map 时插件优先调用 `rg --color=never --max-count 1`，没有 `rg` 时 fallback 到 `grep`，最后才用 Vim `readfile()`。同一个 loc_id 会按 map mtime 缓存，适合几十 MB 以上的大 map 文件。

## 内建 UVM 测试环境

```bash
pytest --xverif-prepare xloc.uvm
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-gate nightly --xverif-suite xloc.uvm
```

测试环境位于 `xloc/tb/`，在不同文件中调用 `uvm_error`/`uvm_warning`/`uvm_info`，验证多文件 loc_id 生成和去重。显式 prepare 通过 `Makefile.fixture` 构建并发布内容寻址缓存；nightly 只消费缓存，不会隐式重复仿真。

## Agent 使用原则

当 LLM debug agent 处理带 loc_id 的日志时：

1. **不要猜 loc_id**。用 `xloc resolve` 查询。
2. **先 stats 后 resolve**。了解高频位置，优先查这些。
3. **需要源码证据时才 context**。只是想知道文件在哪用 resolve 就够了。
4. **回答时引用 loc_id + 文件位置**。例如：`L_00000005 (simple_test.sv:3)`。

## 构建与测试

```bash
make -C xloc          # 语法检查
pytest --xverif-gate fast --xverif-suite xloc.unit
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-gate regression --xverif-suite xloc.vim
pytest --xverif-prepare xloc.uvm
XVERIF_TEST_EXECUTION_ENV=host pytest --xverif-gate nightly --xverif-suite xloc.uvm
```

`xloc` 只依赖 Python 标准库，不依赖 NPI、Verdi 或任何 Synopsys 工具。UVM 测试环境需要 VCS。
