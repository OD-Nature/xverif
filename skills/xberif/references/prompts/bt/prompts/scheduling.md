总结这个 Block Test 环境的 Scheduling Points。

重点关注：

1. arbiter、grant、dispatch、issue、select、port/channel/bank/entry/pipeline 调度。
2. priority、round-robin、fixed-priority、age-based 等策略。
3. 输入候选、输出目标、blocking condition、grant signal。
4. 和 backpressure、credit、FIFO full 的关系，以及 starvation/fairness 风险。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

