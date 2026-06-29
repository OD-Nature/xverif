总结这个 Block Test 环境的 Ordering Points。

重点关注：

1. FIFO、per-source、per-ID、request/response、input/output 顺序关系。
2. scheduler、pipeline、multi-port、multi-bank 是否改变顺序。
3. 打破顺序和恢复顺序的机制，tag、ID、sequence number、reorder buffer。
4. scoreboard/checker 的 ordering 假设和 assertion/coverage。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

