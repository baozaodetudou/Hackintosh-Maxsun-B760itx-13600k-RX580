# OpenCore 1.0.7 / macOS Sequoia 15.8.1

2026-10-15 从本机实际 EFI 分区以只读方式获取。系统为 15.8.1（24H32），SMBIOS MacPro7,1，硬件为 MS-B760ITX / i5-13600K / RX 6600 XT / BCM94360CD / 64GB RAM。

## 内容 / Contents

- `EFI-OpenCore-1.0.7-Sequoia-15.8.1.zip`：公开 EFI，解压后包含 `EFI/BOOT` 和 `EFI/OC`。
- `config.plist`：压缩包中的配置副本，便于审阅差异。
- `files-sha256.json`：压缩包中每个文件的 SHA-256。
- `SHA256SUMS`：压缩包的 SHA-256。
- `capture.json`：采集范围、系统版本、隐私处理和测试边界。

完整原始备份的 480 个文件均与实际 EFI 逐文件 SHA-256 核对一致，仅保存在本机。公开包保留 474 个文件：去掉 Apple 固件更新缓存和 macOS 文件系统元数据，并将机器标识替换为 OpenCore 1.0.7 官方 Sample.plist 的占位值。其他引导设置和二进制保持原样。

The private backup matches all 480 source files. The public archive contains 474 files, omits firmware-update cache/metadata, and replaces active machine identifiers with official OpenCore sample values. It is not directly usable until personal identifiers are restored or generated.

## 配置状态 / Configuration

- OpenCore 1.0.7，保持现用 ACPI、USB 端口映射与 kext 顺序。
- RX 6600 XT：`agdpmod=pikera`、`gfxrst=1`，保留 `CFG,CFG_USE_AGDC=false`。
- `revpatch=memtab,pci,cpuname,sbvmm`：保留 RestrictEvents 原有功能并恢复更新检测。
- BCM94360CD：保留 IOSkywalkFamily + IO80211FamilyLegacy + AirPortBrcmNIC，以及 AMFIPass。
- 当前系统 Modern Wireless root patch 元数据：OCLP 2.5.1 / PatcherSupportPkg 1.9.7 / 24H32。

**Root patch 不属于 EFI。** 恢复系统或更新系统后，需要另行确认目标系统所需补丁。此备份没有额外加入 Tahoe 支持，也没有替换正在使用的 EFI。

## 使用与回退 / Use and recovery

1. 校验 `SHA256SUMS`，解压到 FAT32 测试介质。
2. 将本机原始配置里的 `MLB`、`ROM`、`SystemSerialNumber`、`SystemUUID` 恢复到测试副本；其他机器应生成自己的标识。
3. 从该介质先验证能进入原有 15.8.1，再考虑部署到硬盘。

公开包通过静态检查不代表已经制作并实测了救援 U 盘。恢复 EFI 也不会把已升级的 macOS 降级。

Verify the archive, supply the correct private SMBIOS identifiers, and boot a USB copy before deployment. EFI restoration does not downgrade macOS or restore root patches.

## 验证 / Validation

见 `validation.json`。本次备份确认系统已启动至 15.8.1；没有执行睡眠、无线开关、AirDrop 传输或重启测试。
