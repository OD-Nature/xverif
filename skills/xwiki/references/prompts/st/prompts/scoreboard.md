总结这个 Subsystem Test 环境的 Integration Scoreboard / Checker。

重点关注：

1. scoreboard/checker 名称、expected path、actual path、compare point。
2. compare key、ordering assumption、out-of-order compare。
3. pending/expected/actual queue 或 table，reset 行为。
4. mismatch 报错格式、RM/monitor 连接和 debug 入口。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

