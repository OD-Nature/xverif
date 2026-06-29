总结这个 SoC Test 环境的 Firmware / Baremetal Test Interface。

重点关注：

1. firmware 源码、baremetal test、entry function、startup/linker script。
2. build system、ELF/bin/hex 生成、加载地址。
3. MMIO、DMA、peripheral、interrupt 访问方式。
4. pass/fail、firmware log、host 交互、regression entry 和 debug。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

