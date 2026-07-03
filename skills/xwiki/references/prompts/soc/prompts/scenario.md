总结这个 SoC Test 环境的 SoC Scenario Structure。

重点关注：

1. scenario/testcase/firmware test 列表和类型。
2. 对应 integration/system flow、参与 IP/agent/component。
3. sequence/firmware/test 入口、stimulus、expected behavior。
4. checks、knobs、regression entry、coverage、debug hint。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

