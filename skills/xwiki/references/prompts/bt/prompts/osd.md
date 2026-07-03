总结这个 Block Test 环境的 OSD（outstanding data/descriptor/transaction）容量。

目标是搞清楚每个接口、队列、bank、pipeline、request/response path 最多能接收、容纳或允许多少个 outstanding item。

重点关注：

1. 每个入口接口在反压前最多接受多少个 request/data/descriptor。
2. 每个内部 FIFO、credit pool、ROB、tag table、MSHR、bank queue、pipeline stage 的容量限制。
3. 每个出口或 response path 允许多少未完成事务，以及 response 是否受 ID/tag/source 限制。
4. 设计可接受上限、协议限制、配置参数限制、DV sequence/test 限制之间的差异。
5. OSD 达到上限后的 backpressure 条件和可观测信号。

证据要求：

- OSD 数量必须引用 RTL/spec/DV 证据，优先引用 parameter、localparam、FIFO depth、counter width、credit 初值、ID/tag table size 和 valid/ready gating。
- 如果只能推导范围，必须说明推导公式和 unknown。
- 如果 RTL 理论上支持的 OSD 与 DV 默认配置不同，必须分别列出。

建议每个 item 包含：

- name
- interface_or_path
- osd_definition
- max_osd
- limiting_resource
- limiting_formula
- backpressure_condition
- related_file_or_component
- signals_or_fields
- rtl_or_spec_refs
- dv_limit_or_assumption
- verification_points
- confidence
- evidence
