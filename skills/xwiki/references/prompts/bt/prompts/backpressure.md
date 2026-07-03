总结 block 中所有反压点。

重点关注：

1. valid/ready、FIFO full/almost_full、credit empty、downstream ready 拉低。
2. busy、stall、retry、nack、scheduler grant 不发放等阻塞条件。
3. upstream、downstream、阻塞条件、解除条件和相关信号。
4. 死锁、饥饿、吞吐下降、ordering 风险以及 checker/assertion/coverage 覆盖情况。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

