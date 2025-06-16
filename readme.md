![tests](https://github.com/desultory/ugrd/actions/workflows/tests.yml/badge.svg)
![PyCPIO](https://github.com/desultory/pycpio/actions/workflows/unit_tests.yml/badge.svg)
![Zenlib](https://github.com/desultory/zenlib/actions/workflows/unit_tests.yml/badge.svg)
![Black](https://img.shields.io/badge/code%20style-black-000000.svg)

# µgRD

> Microgram Ramdisk is a framework used to generate POSIX compatible ramdisks using TOML definitions and python functions

## Design

µgRD is designed to generate a custom initramfs environment to boot the system which built it.

Generated images are as static and secure as possible, only including components and features required to mount the root and switch to it.

µgRD itself is written in pure Python, and generates POSIX shell scripts to mount the rootfs and continue booting.

The final build environment is left in the specified `build_dir`, where it can be examined or repacked.

Unless validation is disabled, µgRD attemts to validate most configuration against the host system, raising exceptions or logging warnings warnings if the configuration is invalid.

## Project goal and features

The original goal of this project was to create an initramfs suitable for decrypting a LUKS root filesystem with a smartcard, with enough config validation to prevent the user from being left in a broken pre-boot environment.

### Auto-detection

* Root mount, using `/proc/mounts`. `root=` and `rootflags=` can be used but are not required
* MDRAID auto-configuration for the root mount
* LUKS auto-configuration and validation for the root mount
  - LUKS under LVM support
  - LUKS under MDRAID support
* LVM based root volumes are auto-mounted
* BTRFS root subvolumes are automatically detected to `root_subvol`
    - `subvol_selector` can be used to select a subvolume at boot time
* `/usr` auto-mounting if the init system requires it
* Auto-detection of kernel modules required by the storage device used by the root filesystem
* Init system/target auto-detection

### Validation

* Configuration validation against the host config in `validate` mode
* LUKS header and crypto backend validation
* Imported binary and shell function collision detection
* Static output image checks, ensuring necessary files are packed
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
* "merged usr" symlinks are creatd by default and can be disabled by setting `merge_usr = false`
* ZSH and BASH autocompletion for the `ugrd` command
* Basic hibernation/resume support with `ugrd.fs.resume`
* Similar usage/arguments as Dracut

## Support

µgRD is designed to be as portable as possible, but has only been tested on a limited number of systems.

### Operating systems

µgRD was designed to work with Gentoo, but has been tested on:

* Garuda linux
* CachyOS
* Debian 12
* Ubuntu 22.04

### Shells

µgRD was originally designed for bash, but should work for POSIX compatible shells including:

* dash
* ksh

> Some non-POSIX compatible shells may function, but bash, dash, and ksh are part of automated testing.

### Filesystems

If userspace tools are not required to mount a the root filesystem, µgRD can be used with any filesystem supported by the kernel.

The following root filesystems have been tested:

* BTRFS
* EXT4
* XFS
* F2FS
* NILFS2

> The root mount can automatically be mounted under an overlay filesystem by using the `ugrd.fs.overlayfs` module.

The following filesystems have limited support:

* BCACHEFS
* ZFS

Additionally, the following filesystems have been tested for non-root mounts:

* FAT32

If the required kernel module is not built into the kernel, and the filesystem is not listed above, the kernel module may need to be included in `kmod_init`.

> The example config has `kmod_autodetect_lsmod` enabled which should automatically pull in the required modules, unless the active kernel differs from the build kernel.

### Architectures

µgRD was originally designed for modern `amd64` systems but has been tested on:

* arm64
   * Raspberry Pi 4
   * Raspberry Pi 5
   * Quartz64 Model A
   * Radxa Zero3E
* riscv64
   * StarFive VisionFive 2

## Docs

Additional documentation can be found in the [docs](docs) directory.
