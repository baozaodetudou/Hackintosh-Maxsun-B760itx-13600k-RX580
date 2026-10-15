# macOS Tahoe 26.7.1 测试 EFI / Test EFI

目标：MS-B760ITX / i5-13600K / RX 6600 XT / BCM94360CD / MacPro7,1。针对 macOS 26.7.1（25G241，Darwin 25）准备，基于 2026-10-15 实机 Sequoia 15.8.1 EFI，OpenCore 保持 1.0.7。

**状态：仅完成静态校验，尚未在本机启动 Tahoe。** 没有部署到硬盘 EFI、安装系统、应用 root patch 或修改磁盘。静态校验结果见 `validation.json`。

Prepared for this specific PC. This is an unbooted test configuration, not a verified Tahoe release. Existing OpenCore binaries are retained; system root patches are separate.

## 下载与配置 / Package and profiles

- [EFI 测试包](EFI-OpenCore-1.0.7-Tahoe-26.7.1-test.zip)
- [安装器配置](config-installer.plist)
- [运行配置](config-runtime.plist)
- [SHA-256](SHA256SUMS)、[文件清单](files-sha256.json)、[上游来源](provenance.json)、[修改清单](changes.json)

压缩包的 `EFI/OC` 内含三份配置：默认 `config.plist` 与 `config-installer.plist` 相同；另有 `config-runtime.plist`。OpenCore 只加载命名为 `config.plist` 的文件。

公开配置使用占位三码。使用前在三份配置中恢复本机私有 `MLB`、`ROM`、`SystemSerialNumber`、`SystemUUID`；其他机器自行生成标识。完整私有配置只保存在本机，不提交。

## 为什么分成两份 / Why two profiles

| 配置 | Darwin 25 上的显卡行为 | 使用阶段 |
| --- | --- | --- |
| installer（默认） | 不加载 WhateverGreen；用 OpenCore 的 AGDP `board-id\0 → board-ix\0` 补丁替代 pikera | Tahoe 安装器、Recovery、系统更新的安装阶段，以及排查 WEG 卡死 |
| runtime | 加载现有官方 WhateverGreen 1.7.1，保留 `agdpmod=pikera`、`gfxrst=1` 和本机 `CFG,CFG_USE_AGDC=false` | 已安装 Tahoe 的图形、多屏与显示器唤醒测试 |

安装器配置避开已报告的 WEG/AMD 安装器卡死路径。**运行配置仍有待实测**，不能把安装后重新启用 WEG 当成必然成功。若切换运行配置后卡死，回到安装器配置排查。

`CFG,CFG_USE_AGDC` 的属性转换依赖 WEG；它在无 WEG 的安装器配置下不等同于已生效的多屏唤醒修复。安装阶段先用单个显示器；进入运行配置后再测试双 DP 与其他显示器。

在不加载 WEG 的 Tahoe 阶段，`-wegnoigpu` 和 `gfxrst=1` 不发挥 WEG 的作用。因此使用前须确认 BIOS 的 Intel 核显已禁用，并将显示器接到 RX 6600 XT；13600K 的 UHD770 不作为显示设备。

Both profiles keep the existing WEG path through Darwin 24. The installer uses a Darwin-25-only AGDP patch; the runtime profile restores WEG and its property handling. The latter still requires hardware testing. No third-party WEG binary is included.

## Broadcom 无线 / Wireless

保留旧驱动供 Darwin 23–24 使用；Darwin 25 改为 OCLP **3.0.0-rc.3** 所使用的三份载荷，并按上游顺序加载：

1. `Tahoe/IOSkywalkFamily.kext`，来源包 v1.2.0。
2. `Tahoe/IO80211FamilyLegacy.kext`，来源包 v1.0.0。
3. `Tahoe/AirPortBrcmNIC-Tahoe.kext`，来源包 v1.0.0。

旧的内嵌 AirPortBrcmNIC 限制到 `24.99.99`；新驱动从 `25.0.0` 开始，防止同一个 bundle ID 同时注入。现有 IOSkywalk exclusion、AMFIPass 1.4.1、`-amfipassbeta`、`csr-active-config=03080000`、`SecureBootModel=Disabled` 与 `DisableIoMapper=true` 保留；没有添加 AppleVTD/BroadcomVTD 方案。

三份上游 ZIP 均用 GitHub blob SHA-1 和独立 SHA-256 核对，详见 provenance。EFI **不包含** OCLP 对系统的 `wifip2pd`、IO80211.framework 和 WiFiPeerToPeer.framework 等 root patches。在 Tahoe 中仍需安装 RC3 应用并检查 Modern Wireless 补丁；不要让 OCLP 的 **Build and Install OpenCore** 替换本机定制 EFI。

首次进入 Tahoe 时应准备有线网络；RTL812xLucy 保持现有版本，但其 Tahoe 实机网络状态也尚未验证。Wi-Fi 能连接不代表 AirDrop 或睡眠后自动重连已经通过。

## USB、音频和其他设置 / Other changes

- USBPorts 的 13 个端口、地址、接口类型、SMBIOS 与控制器匹配条件保持原样，只补齐 Tahoe 所用的 `usb-port-number`、`usb-port-type`，同时保留旧字段。
- AppleALC 限制到 Darwin 24：Tahoe 删除了 AppleHDA，当前测试以 USB-C 耳机为音频设备。板载 3.5mm 音频另行适配，不在本包中宣称已修复。
- RadeonSensor、SMCRadeonGPU、HibernationFixup 暂限到 Darwin 24；先验证基本显示和普通睡眠，GPU 遥测与深度休眠不属于本次初始测试范围。
- 现有 CPU、ACPI、电源和网卡设置保留，CPUFriend 原有禁用状态保留。
- 增加 `-v keepsyms=1 debug=0x100` 与 OpenCore 文件日志，用于启动问题诊断。日志只在本机查看，分享前先去除机器标识。
- Sequoia 的 kext 选择和顺序已静态核对一致；新增 USB 属性和诊断设置仍会作用于测试 EFI，因此原有 15.8.1 应保留独立可用的 EFI。

## 测试顺序 / Test sequence

1. 准备能够实际启动现有 15.8.1 的独立救援 EFI/介质，核实数据备份。
2. 将已恢复本机标识的测试 EFI 放在 FAT32 U 盘；先从该 U 盘进入现有 15，验证引导路径，再启动 Tahoe 安装器。
3. 使用默认安装器配置，将 Tahoe 安装到单独 SSD 或新 APFS 测试卷。保留原有 15.8.1 和 Windows。
4. 安装完成后，仅在**测试介质**的 `EFI/OC` 下执行 `cp config-runtime.plist config.plist`，然后启动已安装的 Tahoe。不要在 macOS 安装器重启阶段提前切换。
5. 按目标系统检测结果应用 Modern Wireless root patch，重启后分别测试下面项目。
6. 需要进入 Tahoe 安装器/Recovery 或再次更新系统时，将测试介质配置切回 `cp config-installer.plist config.plist`。若仍无法启动，使用独立的 Sequoia EFI 回退。

## 仍待实测 / Pending hardware validation

- 冷启动、重启、关机，且能重新进入保留的 15.8.1。
- GPU 硬件加速，所有显示器、DP/HDMI 接口、刷新率，以及多次熄屏后解锁。
- USB 2/3、Type-C、USB 耳机与 Broadcom 蓝牙。
- Wi-Fi 冷启动自动连接、开关重连、多次睡眠后自动重连。
- 与自己的设备双向 AirDrop 实际传文件，并在唤醒后重测。
- 多次系统睡眠、仅显示器休眠与较长时间睡眠后的恢复。

## 重新生成与验证 / Rebuild and verify

只依赖 Python 标准库；`--payload-dir` 指向已下载的三份上游 ZIP。脚本固定校验上游哈希，不访问本机 EFI，也不自动下载或安装。

```zsh
python3 scripts/build_tahoe_test.py --payload-dir /path/to/verified-payloads
python3 scripts/verify_efi.py testing/26.7.1/EFI-OpenCore-1.0.7-Tahoe-26.7.1-test.zip --opencore-release /path/to/OpenCore-1.0.7-RELEASE --public --tahoe --report testing/26.7.1/validation.json
```

## 来源 / References

- [Dortania Tahoe 指南](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html)
- [WEG 安装器故障原始报告](https://github.com/acidanthera/bugtracker/issues/2509)
- [WEG 官方 pikera 实现](https://github.com/acidanthera/WhateverGreen/blob/0762cecc2a70054cd4dc3cf4d08979aca6acd9bb/WhateverGreen/kern_weg.cpp)
- [RC3 无线驱动配置](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/3.0.0-rc.3/opencore_legacy_patcher/efi_builder/networking/wireless.py)
- [RC3 配置模板中的内核范围](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/3.0.0-rc.3/payloads/Config/config.plist)
- [USBMap 新旧字段兼容处理](https://github.com/corpnewt/USBMap/blob/master/USBMapInjectorEdit.py)
