总结这个 Subsystem Test 环境的 Integration Flow。

重点关注：

1. transaction flow 入口、经过的 IP/block/interconnect、出口。
2. 每段协议、backpressure 跨模块传播、ordering 约束。
3. interrupt/event 触发链路、memory access path。
4. scoreboard 观察点、scenario 覆盖和关键风险。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

