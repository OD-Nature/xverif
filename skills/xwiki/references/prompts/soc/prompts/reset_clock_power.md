总结这个 SoC Test 环境的 Reset, Clock, and Power Structure。

重点关注：

1. reset source/tree、CPU/peripheral reset、clock source/domain。
2. PLL/divider/gate、power domain、isolation、retention。
3. low power entry/exit、reset release、clock gating scenario。
4. power state test、checker、CDC/RDC/power domain 风险。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

