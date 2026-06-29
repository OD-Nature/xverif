总结这个 SoC Test 环境的 Debug Entrypoints。

重点关注：

1. 如何复现失败，testcase/scenario/firmware test、seed、plusarg、boot mode。
2. log、waveform、coverage、firmware log、checker/assertion/scoreboard mismatch 入口。
3. 从 stimulus 到 DUT input，再到 DUT output 和 checker/scoreboard 的路径。
4. 首先查看的 3 到 5 个文件、log、信号或组件，以及按失败类型的排查路径。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

