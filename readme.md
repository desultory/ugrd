![ubuntu](https://github.com/desultory/ugrd/actions/workflows/ubuntu.yml/badge.svg)
![PyCPIO](https://github.com/desultory/pycpio/actions/workflows/unit_tests.yml/badge.svg)

# µgRD

> Microgram Ramdisk is a framework used to generate ramdisks using TOML definitions and python functions

## Design

µgRD is designed to generate a custom initramfs environment to boot the system that built it.

Generated images are as static and secure as possible, only including components and features required to mount the root and switch to it.

µgRD itself is pure python, and uses the `pycpio` library to generate the CPIO archive.

The final build environment is left in the specified `build_dir`, where it can be examined or repacked.

Unless validation is disabled, µgRD attemts to validate most configuration against the host system, raising exceptions or logging warnings warnings if the configuration is invalid.

## Project goal and features

The original goal of this project was to create an initramfs suitable for decrypting a LUKS root filesystem with a smartcard, with enough config validation to prevent the user from being left in a broken pre-boot environment.

### Auto-detection

* Root mount, using `/proc/mounts`. `root=` and `rootflags=` can be used but are not required.
* LUKS auto-configuration and validation for the root mount
* Rootfs LVM, including under LUKS, is auto-mounted
* MDRAID auto-configuration for the root mount.
* BTRFS root subvolumes are automatically detected, but can be overridden or `subvol_selector` can be used to select a subvolume at boot time.
* `/usr` auto-mounting if the init system requires it
* Auto-detection of kernel modules required by the storage device used by the root filesystem

### Validation

* Configuration validation against the host config in `validate` mode
* Static output image checks
* QEMU based test framework with `--test` or using the `ugrd.base.test` module

### Example config and features

* OpenPGP Smartcards (YubiKey) with the `ugrd.crypto.smartcard` module [yubikey example](examples/yubikey.toml)
* GPG encrypted LUKS keyfiles with the `ugrd.crypto.gpg` module [gpg example](examples/gpg_keyfile.toml)
* LUKS with detatched headers [detached headers example](examples/detached_headers.toml)
* Cryptsetup re-attempts and alternative unlock methods
  - Allows for late insertion of a smartcard `cryptsetup_retries` and `cryptsetup_autoretry`
  - Can fail back to plain password entry `try_nokey`
* Key entry over serial [raid crypt serial](examples/raid_crypt_serial.toml)

### Other info  

* Automatic CPIO generation (PyCPIO)
  - Device nodes are created within the CPIO only, so true root privileges are not required
  - Hardlinks are automatically created for files with matching SHA256 hashes
  - Automatic xz compression
* ZSH and BASH autocompletion for the `ugrd` command
* Similar usage/arguments as Dracut

## Support

µgRD is designed to be as portable as possible, but has only been tested on a limited number of systems.

### Operating systems

µgRD was designed to work with Gentoo, but has been tested on:

* Garuda linux
* Debian 12
* Ubuntu 22.04

### Filesystems

If userspace tools are not required to mount a the root filesystem, µgRD can be used with any filesystem supported by the kernel.

The following root filesystems have been tested:

* BTRFS
* EXT4
* XFS
* FAT32
* NILFS2

If the required kernel module is not built into the kernel, and the filesystem is not listed above, the kernel module may need to be included in `kmod_init`.

> The example config has `kmod_autodetect_lsmod` enabled which should automatically pull in the required modules, unless the active kernel differs from the build kernel.

### Architectures

µgRD is primarily designed and tested against `x86_64`, but has been tested on `arm64`.

## Docs

Additional documentation can be found in the [docs](docs) directory.

