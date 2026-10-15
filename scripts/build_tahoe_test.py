#!/usr/bin/env python3
"""Package two Tahoe test profiles without modifying the live EFI."""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
TAG = "3.0.0-rc.3"
PAYLOADS = {
    "IOSkywalkFamily-v1.2.0.zip": (
        "IOSkywalkFamily.kext", "17eab5f1b3b12bff097fb2c50610ee1dbd6f7fe8",
        "1e12b7ef42f55b39ea54ada97b46331220668b2c48a28656e9875c5145fe2479"),
    "IO80211FamilyLegacy-v1.0.0.zip": (
        "IO80211FamilyLegacy.kext", "1e3452819cac6cebbd19932895ee56888af6e449",
        "e681dcc76a2cd2cea4b0ad5f27a3c816055fde3cdccd890dd10a3e2c84e96d93"),
    "AirPortBrcmNIC-Tahoe-v1.0.0.zip": (
        "AirPortBrcmNIC-Tahoe.kext", "5c9f07250a9f6cc6d78c45921c43205910b66c39",
        "04edd7127ce096f5de9f8112af6d06744f27e5bc659e3d6516408755cb9af032"),
}


def extract(archive, target):
    with zipfile.ZipFile(archive) as z:
        if z.testzip():
            raise ValueError("Invalid ZIP: " + str(archive))
        for item in z.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or item.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError("Unsafe archive member")
        members = [item for item in z.infolist() if not any(
            part in {".DS_Store", "__MACOSX"} or part.startswith("._")
            for part in PurePosixPath(item.filename).parts)]
        z.extractall(target, members)


def save_plist(path, obj):
    path.write_bytes(plistlib.dumps(obj, sort_keys=False))


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--payload-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, default=REPO / "testing/26.7.1")
    args = p.parse_args()
    baseline = REPO / "1.0.7-sequoia-15.8.1/EFI-OpenCore-1.0.7-Sequoia-15.8.1.zip"
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != "1939d7fda0c41ca474bcdf51d26284ea262843a7ff54466d890b7a51b906b277":
        raise ValueError("Unexpected Sequoia baseline")
    args.output.mkdir(parents=True, exist_ok=True)
    provenance = []
    for name, (bundle, blob, sha) in PAYLOADS.items():
        data = (args.payload_dir / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha or hashlib.sha1(
                ("blob " + str(len(data)) + "\0").encode() + data).hexdigest() != blob:
            raise ValueError("Payload integrity mismatch: " + name)
        provenance.append({"name": name, "sha256": sha, "git_blob_sha1": blob,
                           "source": "https://github.com/dortania/OpenCore-Legacy-Patcher/blob/" + TAG + "/payloads/Kexts/Wifi/" + name})
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        extract(baseline, stage)
        before = hashes(stage)
        efi = stage / "EFI"
        cfg = plistlib.loads((efi / "OC/config.plist").read_bytes())
        for name, (bundle, _, _) in PAYLOADS.items():
            extract(args.payload_dir / name, efi / "OC/Kexts/Tahoe")

        # The existing stack remains byte-identical and selected only through Darwin 24.
        legacy_paths = {
            "IOSkywalkFamily.kext", "IO80211FamilyLegacy.kext",
            "IO80211FamilyLegacy.kext/Contents/PlugIns/AirPortBrcmNIC.kext"}
        entries = cfg["Kernel"]["Add"]
        for entry in entries:
            if entry["BundlePath"] in legacy_paths:
                entry["MaxKernel"] = "24.99.99"
            elif entry["BundlePath"] in {
                    "AppleALC.kext", "RadeonSensor.kext", "SMCRadeonGPU.kext", "HibernationFixup.kext"}:
                # USB audio and normal sleep are the initial Tahoe test scope.
                entry["MaxKernel"] = "24.99.99"
        insert_at = next(i for i, x in enumerate(entries) if x["BundlePath"].endswith("PlugIns/AirPortBrcmNIC.kext")) + 1
        tahoe_entries = []
        for _, (bundle, _, _) in PAYLOADS.items():
            info = plistlib.loads((efi / "OC/Kexts/Tahoe" / bundle / "Contents/Info.plist").read_bytes())
            tahoe_entries.append({"Arch": "x86_64", "BundlePath": "Tahoe/" + bundle,
                                  "Comment": "OCLP " + TAG + " / Tahoe only",
                                  "Enabled": True, "ExecutablePath": "Contents/MacOS/" + info["CFBundleExecutable"],
                                  "MaxKernel": "25.99.99", "MinKernel": "25.0.0", "PlistPath": "Contents/Info.plist"})
        entries[insert_at:insert_at] = tahoe_entries
        for block in cfg["Kernel"]["Block"]:
            if block["Identifier"] == "com.apple.iokit.IOSkywalkFamily":
                block["MaxKernel"] = "25.99.99"

        # Add the new USB property names without changing any port or connector type.
        usb_path = efi / "OC/Kexts/USBPorts.kext/Contents/Info.plist"
        usb = plistlib.loads(usb_path.read_bytes())
        for personality in usb["IOKitPersonalities"].values():
            for port in personality["IOProviderMergeProperties"]["ports"].values():
                port["usb-port-number"] = port["port"]
                port["usb-port-type"] = port["UsbConnector"]
        save_plist(usb_path, usb)

        args_list = cfg["NVRAM"]["Add"][GUID]["boot-args"].split()
        for arg in ["-v", "keepsyms=1", "debug=0x100"]:
            if arg not in args_list:
                args_list.append(arg)
        cfg["NVRAM"]["Add"][GUID]["boot-args"] = " ".join(args_list)
        cfg["Misc"]["Debug"].update({"AppleDebug": True, "ApplePanic": True, "SysReport": False, "Target": 67})

        # Match WhateverGreen's pikera replacement, including the terminating NUL.
        agdp = {"Arch": "Any", "Base": "", "Comment": "Tahoe installer: AGDP board-id to board-ix without WEG",
                "Count": 1, "Enabled": True, "Find": b"board-id\0",
                "Identifier": "com.apple.driver.AppleGraphicsDevicePolicy", "Limit": 0,
                "Mask": b"", "MaxKernel": "25.99.99", "MinKernel": "25.0.0",
                "Replace": b"board-ix\0", "ReplaceMask": b"", "Skip": 0}
        installer = copy.deepcopy(cfg)
        for entry in installer["Kernel"]["Add"]:
            if entry["BundlePath"] == "WhateverGreen.kext":
                entry["MaxKernel"] = "24.99.99"
        installer["Kernel"]["Patch"].append(agdp)
        runtime = copy.deepcopy(cfg)  # The original WEG and CFG property merge are restored.
        save_plist(efi / "OC/config.plist", installer)
        save_plist(efi / "OC/config-installer.plist", installer)
        save_plist(efi / "OC/config-runtime.plist", runtime)
        for name, obj in [("config-installer.plist", installer), ("config-runtime.plist", runtime)]:
            save_plist(args.output / name, obj)
        after = hashes(stage)
        changes = {"added_files": sorted(set(after) - set(before)),
                   "changed_existing_files": sorted(k for k in before if after.get(k) != before[k]),
                   "removed_files": sorted(set(before) - set(after)),
                   "runtime_tested": False}
        (args.output / "changes.json").write_text(json.dumps(changes, indent=2) + "\n")
        (args.output / "files-sha256.json").write_text(json.dumps(after, indent=2) + "\n")
        zip_name = "EFI-OpenCore-1.0.7-Tahoe-26.7.1-test.zip"
        with zipfile.ZipFile(args.output / zip_name, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name in after:
                item = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100644 << 16
                z.writestr(item, (stage / name).read_bytes())
        (args.output / "SHA256SUMS").write_text("".join(
            hashlib.sha256((args.output / name).read_bytes()).hexdigest() + "  " + name + "\n"
            for name in [zip_name, "config-installer.plist", "config-runtime.plist"]))
    (args.output / "provenance.json").write_text(json.dumps({
        "baseline": str(baseline.relative_to(REPO)), "OpenCore": "1.0.7",
        "target_macOS": "26.7.1 (25G241)", "target_Darwin": "25.x",
        "new_payloads": provenance,
        "WhateverGreen": "Existing official 1.7.1 binary; no third-party modification",
        "AGDP_patch_reference": "https://github.com/acidanthera/WhateverGreen/blob/0762cecc2a70054cd4dc3cf4d08979aca6acd9bb/WhateverGreen/kern_weg.cpp",
        "USB_property_reference": "https://github.com/corpnewt/USBMap/blob/master/USBMapInjectorEdit.py",
        "root_patches_included": False, "runtime_tested": False}, indent=2) + "\n")
    print("Built public test package: " + str(args.output))


if __name__ == "__main__":
    main()
