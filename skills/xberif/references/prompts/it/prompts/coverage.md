总结这个 IP Test 环境的 Coverage Structure。

重点关注：

1. covergroup、coverpoint、cross、coverage class/module。
2. 采样来源、sampling condition、functional/protocol/error/corner coverage。
3. coverage 与 sequence/scenario 的关系、开关、report 生成方式。
4. regression 是否收集 coverage 和明显缺失点。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

