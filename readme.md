# µgRD

> Microgram Ramdisk is a framework used to generate ramdisks using TOML definitions and python functions

## Design

µgRD is designed to generate a custom initramfs environment to boot the system that built it.

Generated images are as static and secure as possible, only including components and features required to mount the root and switch to it.

µgRD itself is pure python, and uses the `pycpio` library to generate the CPIO archive.

The final environment will be left in `build_dir` where it can be examined or repacked.

Unless validation is diabled, µgRD attemts to validate most configuration against the host system, and will raise warnings or exceptions if the configuration is invalid.

## Project goal and features

The original goal of this project was to create an initramfs suitable for decrypting a LUKS root filesyem with a smartcard, with enough config validation to prevent the user from being left in a broken pre-boot environment.

Currently the following features are supported:

* Basic configuration validation in `validate` mode
* Static output image checks
* QEMU based test framework with `--test` or using the `ugrd.base.test` module
* OpenPGP Smartcards (YubiKey) with the `ugrd.crypto.smartcard` module
* GPG encrypted LUKS keyfiles with the `ugrd.crypto.gpg` module
* LUKS with detatched headers
* Cryptsetup re-attempts and alternative unlock methods
  - Allows for late insertion of a smartcard
  - Can fail back to plain password entry
* LVM support (under LUKS) with the `ugrd.fs.lvm` module
* Auto-detection and validation of the root mount using `/proc/mounts`
* Auto-detection and validation of LUKS root mounts
* Auto-detection and validation of the btrfs subvolume used for the root mount, if present
* Auto-detection of mountpoints for the system init.
* Dynamic BTRFS subvolume selection at boot time using `subvol_selector`
* Auto-detection of kernel modules using `lspci` and `lsmod`
* Reading the `root` and `rootflags` parameters from the kernel commandline
  - Falls back to host mount config if cmdline mount parameters fail
* Key entry over serial
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

