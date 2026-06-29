总结这个 IP Test 环境的 How to Create IP Testcases。

重点关注：

1. base test、test class 继承、命名和目录约定。
2. 如何选择或创建 sequence/virtual sequence，如何配置 knobs/plusargs/config object。
3. 如何注册 testcase、运行单测、指定 seed、打开 waveform、判断 pass/fail。
4. 常见错误和推荐最小 smoke 流程。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

