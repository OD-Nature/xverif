总结这个 IP Test 环境的 Reference Model Structure。

重点关注：

1. reference model 文件、class/module/function。
2. 输入 transaction、expected transaction、内部状态模型。
3. 是否建模 queue、credit、ordering、counter、register、memory。
4. expected/actual path、compare point、限制和与 sequence/monitor/scoreboard 的连接。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

