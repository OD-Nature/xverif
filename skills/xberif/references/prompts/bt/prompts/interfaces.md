总结这个 Block Test 环境的 Block Interfaces。

重点关注：

1. clock/reset、transaction、configuration、status、interrupt/event 接口。
2. valid/ready、request/ack、credit、FIFO push/pop 等握手。
3. payload、sideband、ID、tag、len、addr、opcode、mask、error。
4. 方向、协议、backpressure、ordering、outstanding 以及 driver/monitor 对应关系。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

