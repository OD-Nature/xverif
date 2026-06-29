总结这个 SoC Test 环境的 Interrupt Routing。

重点关注：

1. interrupt source、aggregation point、controller/router、target。
2. enable/mask/status/pending/clear、priority/vector。
3. register/memory map/firmware/scenario 的关系。
4. test 如何触发和检查 interrupt，checker/coverage/debug 入口。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

