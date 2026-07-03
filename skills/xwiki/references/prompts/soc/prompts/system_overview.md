总结这个 SoC Test 环境的 SoC System Overview。

重点关注：

1. SoC top、simulation top、CPU/processor subsystem。
2. bus/NoC/interconnect、DDR/SRAM/ROM/TCM、DMA、peripheral。
3. interrupt controller、reset/clock/power domain、debug/trace/UART/mailbox/host interface。
4. system address map、boot source、主要 traffic flow、testbench 连接。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

