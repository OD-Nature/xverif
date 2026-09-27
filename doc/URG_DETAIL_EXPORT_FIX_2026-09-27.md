# URG 明细导出修复（2026-09-27）

## 问题与修复

在 VCS/Verdi V-2023.12-SP2 的真实 UART1 数据库上，`export.code_coverage`
首先返回 `URG_DETAIL_PARSE_INCOMPLETE: FSM summary is missing`。
原始 URG 报告包含摘要；模块标题匹配的 `\s` 跨过换行，吞掉紧随其后的
`Summary for FSM`。修复为仅匹配当前行，并测试单 FSM、多 FSM、尾空格、CRLF
及相似模块名前缀，缺失摘要仍然报错。

完整检查还修复了以下问题：

- condition 的 Status 表头正则跨行捕获上方标记，重复 marker 后丢失真值行。
- 短表达式的标记可能是 `-2` 或 `2`，并非总有两侧连字符。
- 多行 `if` 需要按成对括号提取完整条件；同一行多个三目分支必须分别关联谓词。
- URG XML 中只有 assertion 的实例不会出现在 code-only 明细中。仅在 XML 证实
  该指标不存在时允许空结果，未知或损坏的非空指标继续拒绝。
- assertion 明细不能写死 `top` 根名；从右侧解析数字列，保留转义名称中的空格。
  在 Without Attempts 等下一表前停止，避免重复计算，并核对 Uncovered 摘要数量。
- functional 明细的默认压缩和 maxmissing=256 会漏掉 cross bin。使用本机 URG
  help 明确支持的 `-show brief group -group expand_bins`，将 maxmissing 设为资源
  上限加一；解析器检查每个对象的明细数量，压缩、截断和无法解释的行均报错。
- 保留 native 自动 bin 与 cross bin 身份，修正 class covergroup 的完整 scope。
  URG 默认变量视图保留 `[auto[1] - auto[3]]`，展开视图为三个单 bin，但 NPI 只提供
  一个范围对象。因此同时生成两种 URG 视图：变量采用默认范围、cross 采用展开结果，
  并核对两视图的变量 coverable 总数。范围 gap 明示 coverable>1，未知 count 为 null；
  不将单个展开 bin 映射到整个 NPI 范围，不推测范围边界。
- native covergroup 过滤器先取得 full_name 再比较，避免跳过其它组时引用未初始化变量。

公共 action/schema 与调用入口不变，不跳过 FSM，不更换 coverage backend，
不引入容器路径、许可证配置或新的启动层。本次不修改 native C++ 和 RTL/TB。

## 验证方法

正式入口：

```sh
pytest --xverif-gate regression --xverif-suite xcov.unit \
  --xverif-suite xcov.modinfo_complex --xverif-suite xcov.edge_cases \
  --xverif-suite skills.xverif
```

真实 UART1 smoke 重新编译运行：1954 次比较，UVM Error/Fatal 均为 0。
代码导出覆盖 117 个实例、5 类指标，共 585 组；RX FSM 为 5/20，TX 为 5/17。
断言原文的 129 个缺口中，127 个位于请求的 UART1 HDL 层次。
功能覆盖率输出保留 URG 的类型汇总视图和实例视图，不能将二者行数相加当成
唯一 bin 总数；已对两个 covergroup 类型视图的 618 个未覆盖身份与真实 NPI
逐一比对，全部一致。原始报告和设计数据库不进入本源码仓库。

诊断中出现过 native session 打开超时。另一次长时间 URG 等待的调用栈明确位于
`libucapi::scl_lc_checkout`；本机许可证入口 TCP 可达。TCP 可达不证明许可证
checkout 始终及时。此运行环境现象与确定性的文本解析错误分别记录，未通过
隐藏错误、提高原生 RPC 超时或自动重试修改来掩盖。

许可证诊断中，同一服务器的 IPv4 短对照连续 5 次成功，但完整回归仍复现
checkout 等待；因此已撤回本机 IPv4 强制设置。两次现场栈都位于
`libucapi::scl_lc_checkout`。查询时 Verdi 许可证为 99 份中 2 份占用，不能据此
解释为许可证数量耗尽；服务端或网络响应的进一步根因尚未确定。

最终冻结代码的关联回归：223 项中 221 项通过、2 项超时（378.17 秒）。
失败为 `test_csv_export_persists_session_reasons_and_rejects_conflicting_merge`
的 session.open 失败（约 128 秒）及 `test_strict_policy_rejects_covered_object`
的 120 秒子进程超时。同版本随后对这两项各复核一次，2 项均通过（11.44 秒）；
不将该复核替换原始失败，也不声称运行环境已稳定。原生会话超时与许可证等待
是否完全同源尚未取得直接栈证据。此前针对范围、断言解析、真实排除的 11 项
针对性检查全部通过（24.28 秒）。
