#!/usr/bin/env python3
"""Check EFI files, kernel selection, USB mapping and official OpenCore schema."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]


def version(value, upper=False):
    return tuple(map(int, value.split("."))) if value else ((999, 999, 999) if upper else (0, 0, 0))


def selected(item, major):
    return item["Enabled"] and version(item.get("MinKernel", "")) <= (major, 0, 0) <= version(item.get("MaxKernel", ""), True)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_profile(efi, path, official, public, tahoe, baseline):
    cfg = plistlib.loads(path.read_bytes())
    if public:
        for key in ["MLB", "ROM", "SystemSerialNumber", "SystemUUID"]:
            require(cfg["PlatformInfo"]["Generic"][key] == baseline["PlatformInfo"]["Generic"][key], "Unredacted identity field: " + key)
    for section, group, folder in [("ACPI", "Add", "ACPI"), ("UEFI", "Drivers", "Drivers"), ("Misc", "Tools", "Tools")]:
        for item in cfg[section].get(group, []):
            if item["Enabled"]:
                require((efi / "OC" / folder / item["Path"]).is_file(), "Missing enabled path: " + item["Path"])
    infos = {}
    for item in cfg["Kernel"]["Add"]:
        if not item["Enabled"]:
            continue
        bundle = efi / "OC/Kexts" / item["BundlePath"]
        info_path = bundle / item["PlistPath"]
        require(info_path.is_file(), "Missing kext plist: " + item["BundlePath"])
        infos[item["BundlePath"]] = plistlib.loads(info_path.read_bytes())
        if item["ExecutablePath"]:
            executable = bundle / item["ExecutablePath"]
            require(executable.is_file(), "Missing kext executable: " + item["BundlePath"])
            r = subprocess.run(["/usr/bin/lipo", str(executable), "-verify_arch", "x86_64"], capture_output=True, text=True)
            require(r.returncode == 0, "Kext architecture check failed: " + item["BundlePath"] + ": " + r.stderr)
    selections = {}
    for major in ([23, 24, 25] if tahoe else [24]):
        active = [x for x in cfg["Kernel"]["Add"] if selected(x, major)]
        providers = {info["CFBundleIdentifier"] for info in infos.values()}
        loaded = set()
        for item in active:
            info = infos[item["BundlePath"]]
            identity = info["CFBundleIdentifier"]
            require(identity not in loaded, "Duplicate bundle ID on Darwin " + str(major) + ": " + identity)
            for dependency in info.get("OSBundleLibraries", {}):
                if dependency in providers:
                    require(dependency in loaded, "Dependency loads after consumer: " + item["BundlePath"])
            loaded.add(identity)
        selections[str(major)] = [x["BundlePath"] for x in active]
        if tahoe:
            require(sum(infos[x["BundlePath"]]["CFBundleIdentifier"] == "com.apple.driver.AirPort.BrcmNIC" for x in active) == 1,
                    "Expected exactly one Broadcom driver per Darwin version")
            for item in active:
                if item["BundlePath"].startswith("Tahoe/"):
                    require(major == 25, "Tahoe payload selected on an earlier OS")
            blocks = [x for x in cfg["Kernel"]["Block"] if selected(x, major) and x["Identifier"] == "com.apple.iokit.IOSkywalkFamily"]
            require(len(blocks) == 1 and blocks[0]["Strategy"] == "Exclude", "IOSkywalk replacement is not paired with exclusion")
    if tahoe:
        is_runtime = path.name == "config-runtime.plist"
        weg = [x for x in cfg["Kernel"]["Add"] if selected(x, 25) and x["BundlePath"] == "WhateverGreen.kext"]
        agdp = [x for x in cfg["Kernel"]["Patch"] if selected(x, 25) and x["Identifier"] == "com.apple.driver.AppleGraphicsDevicePolicy"]
        require(bool(weg) == is_runtime, "Unexpected WEG selection for profile")
        require(len(agdp) == (0 if is_runtime else 1), "Unexpected manual AGDP selection")
        if agdp:
            require(agdp[0]["Find"] == b"board-id\0" and agdp[0]["Replace"] == b"board-ix\0" and agdp[0]["Count"] == 1,
                    "AGDP patch differs from WEG pikera replacement")
        for patch in cfg["Kernel"]["Patch"]:
            require(not selected(patch, 24) or patch["Identifier"] != "com.apple.driver.AppleGraphicsDevicePolicy", "Tahoe AGDP patch affects Sequoia")
        require(cfg["Kernel"]["Quirks"]["DisableIoMapper"] is True, "Unexpected mapper configuration change")
        require(cfg["Misc"]["Security"]["SecureBootModel"] == "Disabled", "SecureBootModel does not match wireless setup")
        require(cfg["Kernel"]["Quirks"]["XhciPortLimit"] is False, "USB port limit quirk must remain disabled")
        # All Sequoia kernel selections retain the original order and identities.
        require(selections["24"] == [x["BundlePath"] for x in baseline["Kernel"]["Add"] if selected(x, 24)], "Sequoia kext selection changed")
    r = subprocess.run([str(official / "Utilities/ocvalidate/ocvalidate"), str(path)], capture_output=True, text=True)
    require(r.returncode == 0, path.name + ": " + r.stdout + r.stderr)
    return {"profile": path.name, "ocvalidate": "passed", "active_kexts": selections}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--opencore-release", type=Path, required=True)
    p.add_argument("--public", action="store_true")
    p.add_argument("--tahoe", action="store_true")
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    baseline = plistlib.loads((REPO / "1.0.7-sequoia-15.8.1/config.plist").read_bytes())
    expected = json.loads((args.archive.parent / "files-sha256.json").read_text())
    with tempfile.TemporaryDirectory() as temp, zipfile.ZipFile(args.archive) as z:
        require(z.testzip() is None, "ZIP CRC failure")
        require(len(z.namelist()) == len(set(z.namelist())), "Duplicate ZIP member")
        require(set(z.namelist()) == set(expected), "File manifest does not match ZIP")
        for name in z.namelist():
            require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe ZIP path")
            require(not any(x == ".DS_Store" or x.startswith("._") for x in Path(name).parts), "Unwanted metadata")
            require(hashlib.sha256(z.read(name)).hexdigest() == expected[name], "SHA-256 mismatch: " + name)
        z.extractall(temp)
        efi = Path(temp) / "EFI"
        for name in ["OC/OpenCore.efi", "BOOT/BOOTx64.efi"]:
            require((efi / name).read_bytes() == (args.opencore_release / "X64/EFI" / name).read_bytes(), "Core binary differs from official OpenCore 1.0.7")
        profiles = [efi / "OC/config.plist"]
        if args.tahoe:
            profiles += [efi / "OC/config-installer.plist", efi / "OC/config-runtime.plist"]
            require(profiles[0].read_bytes() == profiles[1].read_bytes(), "Default profile must be installer")
            usb = plistlib.loads((efi / "OC/Kexts/USBPorts.kext/Contents/Info.plist").read_bytes())
            with zipfile.ZipFile(REPO / "1.0.7-sequoia-15.8.1/EFI-OpenCore-1.0.7-Sequoia-15.8.1.zip") as original:
                old_usb = plistlib.loads(original.read("EFI/OC/Kexts/USBPorts.kext/Contents/Info.plist"))
            for name, personality in usb["IOKitPersonalities"].items():
                ports = personality["IOProviderMergeProperties"]["ports"]
                old_ports = old_usb["IOKitPersonalities"][name]["IOProviderMergeProperties"]["ports"]
                require(set(ports) == set(old_ports) and len(ports) <= 15, "USB selection changed or exceeds 15 ports")
                for port_name, port in ports.items():
                    require(port["port"] == old_ports[port_name]["port"] == port["usb-port-number"], "USB port address changed")
                    require(port["UsbConnector"] == old_ports[port_name]["UsbConnector"] == port["usb-port-type"], "USB connector type changed")
                    require(len(port["port"]) == 4, "USB port number must be four-byte data")
        checks = [check_profile(efi, c, args.opencore_release, args.public, args.tahoe, baseline) for c in profiles]
    report = {"archive": args.archive.name, "files_verified": len(expected), "archive_sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
              "OpenCore_1_0_7_binary_identity": "passed", "USB_map_check": "passed" if args.tahoe else "not modified",
              "profiles": checks, "static_validation": "passed", "runtime_validation": "not performed"}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k != "profiles"}, indent=2))
    print("Validated profiles: " + ", ".join(x["profile"] for x in checks))


if __name__ == "__main__":
    main()
