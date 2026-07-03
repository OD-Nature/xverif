总结这个 IP Test 环境的 Agent Structure。

重点关注：

1. agent class、active/passive、driver、monitor、sequencer。
2. agent config、interface/virtual interface、analysis port。
3. env 中实例化位置，与 scoreboard/coverage/RM 的连接。
4. 多 instance、master/slave/requester/responder 模式和扩展点。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

