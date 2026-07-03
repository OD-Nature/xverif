总结这个 Block Test 环境的 Ordering Points。

必须使用 Mermaid 绘图说明保序路径。优先使用 `flowchart` 表示从输入接受到输出提交的路径；如果 request/response 时序关系更关键，可以补充 `sequenceDiagram`。

重点关注：

1. FIFO、per-source、per-ID、request/response、input/output 顺序关系。
2. scheduler、arbiter、pipeline、multi-port、multi-bank、merge、response return 是否改变顺序。
3. 打破顺序和恢复顺序的机制，tag、ID、sequence number、reorder buffer、join FIFO。
4. scoreboard/checker 的 ordering 假设和 assertion/coverage。

Mermaid 图要求：

- 图中必须标出 ordered path：从哪个 input/accept point 到哪个 queue/pipeline/output point 保序。
- 图中必须标出 reorder point：在哪个 scheduler/arbiter/bank/merge/return path 可能调度乱序。
- 图中必须标出 restore point：在哪里用 ID/tag/sequence/reorder buffer/FIFO join 恢复顺序。
- 图后必须用文字逐条说明“从哪里到哪里保序”“在哪个点的调度可能乱序”“乱序后是否以及在哪里恢复”。

建议每个 item 包含：

- name
- description
- related_file_or_component
- mermaid_diagram
- ordered_from
- ordered_to
- ordering_granularity
- reorder_at
- restore_at
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence
