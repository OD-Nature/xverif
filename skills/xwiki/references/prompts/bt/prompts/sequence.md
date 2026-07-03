总结这个 Block Test 环境的 Block Sequence / Stimulus Structure。

重点关注：

1. base/derived/directed/random/error/corner/stress sequence。
2. sequence item、字段、rand constraint、knob/config。
3. sequence 启动点、target sequencer、driver 连接、transaction 发送到 DUT 的路径。
4. virtual sequence、多 agent 协同、scoreboard/checker/RM 关系和扩展点。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

