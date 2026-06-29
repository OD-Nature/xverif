总结这个 Subsystem Test 环境的 Project Summary。

重点关注：

1. 验证对象、当前验证层级、DUT/top/wrapper 名称。
2. RTL、DV、test、sequence、checker、script、doc 等重要目录。
3. README、Makefile、run 脚本、base test 等主要入口文件。
4. 验证目标、项目约定、DUT/testbench/公共库/外部依赖的边界。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

