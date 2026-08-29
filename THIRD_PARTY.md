# Third-Party and Proprietary Dependencies

## 开源授权范围

xverif 仓库中的独立 source code 和 documentation 按仓库根目录的 [`LICENSE`](LICENSE) 以 MIT License 发布。MIT License 只适用于本项目有权授权的内容，不扩展到用户机器上安装的 EDA software、vendor SDK、database format implementation 或其它 third-party materials。

## Synopsys Verdi NPI 与 FSDB Reader

`xdebug` 和 `xcov` 的部分 backend 使用 Synopsys Verdi NPI、NPI L1、FSDB interfaces 或 coverage interfaces。这些组件是 Synopsys proprietary software，不属于 xverif，也不按 MIT License 授权。

本仓库有意不包含：

- `libNPI.so`、`libnpiL1.so`、`libnffr.so`、`libnffw.so` 等 Synopsys libraries；
- `npi*.h`、`ffrAPI.h`、`ffrKit.h`、`fsdbShr.h` 等 Synopsys headers；
- Synopsys manuals、PDF、official examples、license files 或安装包；
- 包含上述内容的 prebuilt binary、archive、Python wheel、rpm/deb package 或 container image。

用户必须从自己的合法 Synopsys installation 提供这些 dependencies，并自行确认其 agreement 授予所需权利。`VERDI_HOME`、`LD_LIBRARY_PATH` 等环境变量只用于定位本地文件；文件存在、能够编译或能够运行均不构成 license grant。

Synopsys NPI/FSDB headers 中的 proprietary notice 指明，相应 interfaces 的授权受适用的书面协议约束，并提及 VC Apps Access Program Agreement。普通 Verdi installation、end-user license、maintenance agreement 或 evaluation access 是否覆盖具体用途，必须以用户与 Synopsys 实际签署的 agreement 为准。

有关 VC Apps/NPI 的公开产品信息可参考：

- [Synopsys VC Apps Video Series](https://www.synopsys.com/verification/resources/videos/vcapps-video-series.html)
- [Synopsys Legal](https://www.synopsys.com/company/legal.html)

## Source-only wrapper 分发规则

公开 fork、GitHub repository 或 source archive 可以包含本项目独立编写的 wrapper source，但不得包含或复制 Synopsys proprietary materials。贡献者和发布者应遵守以下规则：

1. 构建时只通过用户提供的 `VERDI_HOME` 引用 vendor headers/libraries。
2. 不把本地 `build/`、`libexec/`、动态库、vendor headers 或带有 proprietary payload 的 cache 上传为 release artifact。
3. 公共 CI 只运行不需要 Synopsys software/license 的 static、schema、mock 或 contract tests；需要真实 NPI/FSDB/coverage runtime 的测试应在具备合法环境的 private/self-hosted runner 上运行，且不得导出 vendor artifacts。
4. 不提供从 Verdi、VCS、JasperGold 或其它产品安装目录抽取、复制、下载或重新打包 proprietary components 的脚本。
5. 不声称 xverif 的 MIT License 授予任何 Synopsys API、runtime、FSDB format 或 trademark rights。

## Binary、container 与 hosted service

即使 executable 只以 dynamic linking 方式引用用户本地的 Synopsys libraries，公开分发该 executable 是否被允许，仍取决于适用的 Synopsys agreement。未经明确书面授权，本项目的公共发布物应保持 source-only，不发布 NPI/FSDB/coverage engine binary，也不发布预装 proprietary runtime 的 container image。

使用这些 interfaces 向第三方提供 hosted service、SaaS、OEM integration 或商业再分发，可能需要额外权利，应在发布前向 Synopsys 和法律顾问确认。

## No Legal Advice

本文用于说明本仓库的技术和分发边界，不构成法律意见。若本文与用户实际签署的 vendor agreement 冲突，以该 agreement 为准。
