总结这个 Subsystem Test 环境的 Memory Map。

重点关注：

1. address region、base、size、target slave/IP。
2. access type、register block、memory/SRAM/peripheral region。
3. decode logic、alias/remap、illegal access/error response。
4. test/firmware 访问方式、scoreboard/checker 验证、文档和 RTL 一致性。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

