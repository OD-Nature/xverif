总结这个 SoC Test 环境的 SoC Interconnect / NoC。

重点关注：

1. interconnect/bus/NoC/crossbar 类型。
2. master/slave 列表、address decode、arbitration、routing。
3. backpressure、outstanding、ID/tag/ordering、clock domain。
4. bridge/adapter/converter、error response、checker 和 traffic scenario。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

