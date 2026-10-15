# EFI maintenance

- Public archives and config copies must use the existing official Sample.plist SMBIOS placeholders. Keep complete private backups outside this repository.
- Preserve the live EFI. Build test packages from the published Sequoia snapshot; do not deploy or reboot as part of packaging.
- macOS 26 uses Darwin 25. Gate Tahoe-only kexts and patches accordingly, retaining the Sequoia path.
- Run `python3 scripts/verify_efi.py <archive> --opencore-release <OpenCore-1.0.7-RELEASE> --public` before publishing. For Tahoe packages also add `--tahoe` and verify all included profiles.
- `ocvalidate` proves schema validity, not successful boot, Wi-Fi, AirDrop, display or sleep behavior. Keep these states distinct in documentation.
- Use Chinese and English in commit messages. Use a separate branch for test EFI work; do not rewrite shared history.
