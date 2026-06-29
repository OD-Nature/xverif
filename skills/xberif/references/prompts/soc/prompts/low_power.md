总结这个 SoC Test 环境的 Low Power Structure。

重点关注：

1. sleep/deep sleep/retention/shutdown 等 low power state。
2. power domain、isolation、retention、wakeup source。
3. clock gating、reset behavior、firmware entry/exit sequence。
4. wakeup interrupt、low power scenario、checker/assertion/debug 入口。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

