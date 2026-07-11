# xcov / Verdi 2018 NPI 调试笔记

这份笔记记录的是这次把 `xcov` 从“能跑”推进到“能稳定给 AI/MCP 用”的关键经验。
目标不是复述接口，而是把踩坑顺序和排查方法固定下来，避免后续再把同类问题误判成
license 问题。

## 1. 先区分 license 和数据源问题

Verdi 能启动，不代表 NPI coverage 查询一定能打开正确的 VDB；反过来，NPI 打不开
也不一定是 license 断了。真正要先确认的是：

- Verdi 2018 的 `Verdi` / `VCSTools_Net` feature 是否能 checkout。
- 目标是不是完整 VDB，而不是空壳目录。
- 运行环境是不是加载了 Verdi 2018 的 NPI 库，而不是系统里别的版本。

调试时不要一上来就怀疑 `lmgrd`。先把“VDB 是否有效”和“worker 是否拿到正确库”
分开看。

## 2. 空壳 VDB 会伪装成 hang

这次最关键的坑是：`cov.vdb` / `simv_cov.vdb` 只是目录壳，里面没有真正的 coverage
数据库文件。Verdi 2018 在 `npi_cov_open()` 上不是干脆报错，而是长时间卡住，看起来像
license、环境变量或进程泄漏，实际根因是输入数据无效。

排查动作很简单：

- 先看 `vdb/snps/coverage/db` 是否存在。
- 再确认目录里至少有一个普通文件。
- 如果目录是空的，直接返回 `INVALID_VDB`，不要继续起 worker。

这一条能把大量“看起来像 license”的假问题提前挡掉。

## 3. 2018 版优先走 native worker

Verdi 2018 没有可用的 Python NPI 接口，所以 2018 的兼容方案要换成常驻 C++
worker。这个 worker 的价值有三点：

- 只 checkout 一次 license，避免每个请求都重新初始化。
- NPI 诊断走 stderr，stdout 只保留机器协议，方便 MCP 和脚本消费。
- session 生命周期明确，open / query / close 可以稳定复现。

结论是：2018 版本不要再把 Python wrapper 当主路径，native worker 才是能长期用的
兼容层。

## 4. 先做 preflight，再做长超时

NPI 初始化本来就比普通 CLI 慢，所以 worker 的启动超时要比默认值宽。更重要的是，
在真正 checkout license 之前先做 preflight：

- 检查 VDB 路径。
- 检查 `snps/coverage/db`。
- 检查 worker 二进制和 Verdi 库是否匹配。

这样能把“配置错”和“初始化慢”分开。前者要快速失败，后者才值得等待。

## 5. 关闭时要显式 checkin

worker 的退出路径必须走完整：

- `npi_cov_close(db)`
- `npi_end()`

不要依赖进程退出来“顺手释放”。
这次反复验证的结果是，正常 close/checkin 后 license server 上的占用会回到空闲状态。
如果关闭后占用不回落，优先查 worker 有没有异常退出，或者是否有外层进程把它杀掉了。

## 6. 只在本地 session 内改环境

最容易污染现场的不是 NPI 本身，而是环境变量处理：

- 不要全局改 `LD_LIBRARY_PATH`。
- 不要把 Verdi 路径写成长期污染系统 shell 的方式。
- 在 fish 里要保证 `config.fish` / `conf.d` 的加载顺序可控。

推荐做法是让调用方明确加载同一套环境，再启动 `xcov` 或 MCP server。这样别的 AI
也能复现同样的行为，不会因为宿主 shell 不同而出现“这次能跑、下次不行”。

## 7. 对外暴露的是结果，不是内部兼容细节

对上层工具和 AI 来说，应该暴露的是：

- `xcov.v1` 请求。
- `xout` / JSON 响应。
- `native` / `python` 后端选择。
- 明确的错误码和可读的 preflight 报错。

不应该把“我们内部是不是在绕 URG”作为对外语义。真实 coverage evidence 就是
coverage evidence；拿不到就报错，不要补假分母或者静默降级成另一个数据源。

## 8. 给后续调试的最短路径

当以后再遇到类似问题，优先按这个顺序查：

1. 用一个已知有效的 `simv.vdb` 验证输入。
2. 确认 Verdi 2018 相关 feature 能正常 checkout。
3. 确认 worker 走的是 native backend。
4. 看 stderr 的 NPI 诊断，不要只盯 stdout。
5. 检查 close/checkin 后 license 是否回落。

这套顺序基本能把“输入错误、环境错误、license 错误、worker 错误”分开。
