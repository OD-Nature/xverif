总结这个 Block Test 环境的 Block Test Environment。

重点关注：

1. testbench top、DUT 实例化、interface/virtual interface。
2. driver、monitor、agent、sequencer、checker、scoreboard、reference model、config object。
3. stimulus 如何进入 DUT，DUT 输出在哪里采集，compare/check 在哪里发生。
4. clock/reset、waveform/log/report 控制和多 scenario 支持。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

