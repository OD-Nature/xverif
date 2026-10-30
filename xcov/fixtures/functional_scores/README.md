# 功能覆盖分数 fixture

最小真实 VCS 数据库，覆盖不同 coverpoint 权重、零权重、goal、cross goal、不同实例权重
和 `type_option.merge_instances`。用于逐项对照 URG verbose XML、summary text 与完整报告，
明确 score 与已覆盖 bin 比例的区别。编译与仿真只通过 `make fixture RUN_DIR=<隔离目录>` 执行。

`reference/session.xml` 来自 VCS/URG V-2023.12-SP2 的固定查询参数
`-full64 -xml_verbose -format text -show summary`；只移除了运行时间与本机命令路径。
`reference/groups.txt` 来自同一个 VDB 的普通 `-full64 -format text` 报告，仅清理行尾空白。
普通报告 TYPE 分数与按源码可核查的 TYPE bin 数如下：

| TYPE 后缀 | 分数 | 已覆盖 / 总 bin |
|---|---:|---:|
| weighted_cg | 66.6667 | 1 / 3 |
| goals_cg | 25 | 1 / 4 |
| cross_goals_cg | 37.5 | 3 / 8 |
| type_only_cg | 50 | 1 / 2 |
| instances::cg | 100 | 2 / 2 |
| merged_instances::cg | 100 | 2 / 2 |
| zero_weight_cg | 无分数 | 固定 XML 未给出 |
| empty_cg | 无分数 | 固定 XML 未给出 |

`weighted_cg` 的 TYPE 点权重为 2、1、0，而 INSTANCE 点权重为 3、1、0。
零权重点仍有一个真实 bin，因此不能把加权 bin 数当作 bin 个数。
`cross_goals_cg` 的 XML Group Score 为 33.3333%，普通 TYPE SCORE 为 37.50%；
这是 XML 用加权 bin 比例、普通报告用点/cross 百分比加权产生的差异。
goal 是达标阈值，报告不会将 goal=50 的 50% 点重新标成 100%。
两个多实例组的 TYPE 都为 100%，普通报告 INSTANCE 分别为 87.50% 和 50.00%。

全零权重组与空组在固定 XML 中都是没有任何属性或子项的 TYPE scope；
普通详细报告分别列出 0/1 与 0/0，但固定查询不能区分，因此公开计数必须保留 null。
普通报告总 TYPE 分数为 63.19%，INSTANCE 为 63.50%；固定查询发现未知组元数据时，
作用域功能汇总保留 null 并报告不完整，正常组仍可分别查询。

fixture 同时包含 generate ternary 链，供 branch 源码定位和 Verdi GUI 人工核查。
`-kdb`、`-debug_access+all` 保留了匹配的设计数据库。
