总结这个 SoC Test 环境的 Boot Flow。

重点关注：

1. reset vector、boot ROM、bootloader、firmware/baremetal entry。
2. ELF/hex/bin/image 加载、memory preload、CPU release sequence。
3. boot mode strap/plusarg/config、pass/fail 上报。
4. UART/mailbox/memory flag/host interface、boot log 和 failure debug。

建议每个 item 包含：

- name
- description
- related_file_or_component
- signals_or_fields
- condition_or_behavior
- verification_points
- confidence
- evidence

