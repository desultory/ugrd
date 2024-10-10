# Configuration

At runtime, ugrd will try to read `/etc/ugrd/config.toml` for configuration options unless another file is specified.

There is very little to configure in the base image, unless you are just interested in specifying a few required kmods/files to be pulled into the initramfs.

Modules may be imported to extend the functionality of the build system and resulting image. Many modules are automatically included whn their features are used.

## Modules

The modules config directive should contain a list with names specifying the path of which will be loaded, such as `ugrd.base.base`, `ugrd.base.console` or `ugrd.crypto.crypsetup`.

> By default `ugrd.base.base` and `ugrd.base.core` are loaded. These modules include the cmdline, kmod, and mounts modules.

When a module is loaded, `initramfs_dict.py` will try to load the toml file for that module, parsing it in the same manner `config.yaml` is parsed.

Modules can load other modules, and can therefore be used as aliases for a set of modules.

## Base modules

Several basic modules are provided for actions such as mounts, cmdline processing, and kernel module loading.

Modules write to a shared config dict that is accessible by other modules.

### base.base

> The main module, mostly pulls basic binaries and pulls the `core`, `mounts`, and `cpio` module.

* `init_target` Set the init target for `switch_root`.
* `autodetect_init` (true) Automatically set the init target based `which init`.
* `shebang` (#!/bin/bash) sets the shebang on the init script.

### base.core

* `build_dir` (/tmp/initramfs) Defines where the build will take place.
* `out_dir` (/tmp/initramfs_out) Defines where packed files will be placed.
* `out_file` Sets the name of the output file, under `out_dir` unless a path is defined.
* `clean` (true) forces the build dir to be cleaned on each run.
* `hostonly` (true) Builds the initramfs for the current host, if disabled, validation is automatically disabled.
* `validate` (true) adds additional checks to verify the initramfs will work on the build host.
* `old_count` (1) Sets the number of old file to keep when running the `_rotate_old` function.
* `file_owner` (portage) sets the owner for items pulled into the initramfs on the build system
* `binaries` - A list used to define programs to be pulled into the initrams. `which` is used to find the path of added entries, and `lddtree` is used to resolve dependendies.
* `paths` - A list of directores to create in the `build_dir`. They do not need a leading `/`.

### base.cmdline

If used, this module will override the `mount_root` function and attempt to mount the root based on the passed cmdline parameters.

#### base.console

This module creates an agetty session. This is used by the `ugrd.crypto.gpg` module so the tty can be used for input and output.

Consoles are defined by name in the `console` dict using the following keys:

* `type` (tty) Specifies the console type, such as `tty` or `vt100`.
* `baud` - Set the serial device baud rate.

ex:

```
[console.tty0]
type = "tty"
```

Defines the default `/dev/tty0` console.

```
[console.ttyS1]
baud = 115_200
type = "vt100"
```

Defines /dev/ttyS1 as a `vt100` terminal with a `115200` baud rate.

##### General console options

`primary_console` (tty0) Used to set which console will be initialized with agetty on boot.

#### base.debug

This module contains debug programs such as `cp`, `mv`, `rm`, `grep`, `dmesg`, `find`, and `nano`,

Setting `start_shell` to `true` will start a bash shell in `init_debug`.

### Kernel modules

`ugrd.kmod.kmod` is the core of the kernel module loading..

#### ugrd.kmod.kmod confugration parameters

The following parameters can be used to change the kernel module pulling and initializing behavior:

* `kernel_version` (uname -r) Used to specify the kernel version to pull modules for, should be a directory under `/lib/modules/<kernel_version>`.
* `kmod_pull_firmware` (true) Adds kernel module firmware to dependencies
* `kmod_init` - Kernel modules to `modprobe` at boot.
* `kmod_autodetect_lspci` (false) Populates `kmod_init` with modules listed in `lspci -k`.
* `kmod_autodetect_lsmod` (false) Populates `kmod_init` with modules listed in `lsmod`.
* `kernel_modules` - Kernel modules to pull into the initramfs. These modules will not be `modprobe`'d automatically.
* `kmod_ignore` - Kernel modules to ignore. Modules which depend on ignored modules will also be ignored.
* `kmod_ignore_softdeps` (false) Ignore softdeps when checking kernel module dependencies.
* `no_kmod` (false) Disable kernel modules entirely.

#### Kernel module helpers

Some helper modules have been created to make importing required kernel modules easier.

`ugrd.kmod.nvme`, `usb`, and `fat` can be used to load modules for NVME's, USB storage, and the FAT file system respectively.

Similarly `ugrd.kmod.novideo` `nonetwork`, and `nosound` exist to ignore video, network, and sound devices that may appear when autodetecting modules.

### Filesystem modules

`autodetect_root` (true) Set the root mount parameter based on the current root label or uuid.
`autodetect_root_dm` (true) Attempt to automatically configure virtual block devices such as LUKS/LVM/MDRAID.
`autodetect_root_luks` (true) Attempt to automatically configure LUKS mounts for the root device.
`autodetect_root_lvm` (true) Attempt to automatically configure LVM mounts for the root device.
`autodetect_root_mdraid` (true) Attempt to automatically configure MDRAID mounts for the root device.
`autodetect_init_mount'` (true) Automatically detect the mountpoint for the init binary, and add it to `late_mounts`.

#### ugrd.fs.mounts

`mounts`: A dictionary containing entries for mounts, with their associated config.

`mounts.root` is predefined to have a destination of `/target_rootfs` and defines the root filesystem mount, used by `switch_root`.

Each mount has the following available parameters:

* `type` (auto) Mount filesystem type.
  - Setting the `type` to `vfat` includes the `vfat` kernel module automatically.
  - Setting the `type` to `btrfs` imports the `ugrd.fs.btrfs` module automatically.
* `destination` (/mount name) Mountpoint for the mount, if left unset will use /mount_name.
* Source type: Evaluated in the following order:
  - `uuid` Mount by the filesystem UUID.
  - `partuuid` Mount by the partition UUID.
  - `label` Mount by the device label.
  - `path` Mount by the device path.
* `options` A list of options to add to the mount.
* `base_mount` (false) Mounts with a mount command during `init_pre` instead of using `mount -a` in `init_main`.
* `no_validate` (false) Disables validation for the mount.

The most minimal mount entry that can be created must have a name, which will be used as the `destination`, and a source type.

The following configuration mounts the device with `uuid` `ABCD-1234` at `/boot`:

```
[mounts.boot]
uuid = "ABCD-1234"
```

The following configuration mounts the `btrfs` subvolume `stuff`  with `label` `extra` to `/mnt/extra`:

```
[mounts.extra]
options = [ "subvol=stuff" ]
type = "btrfs"
destination = "/mnt/extra"
label = "extra"
```

##### auto_mounts

Paths added to `auto_mounts` will be auto-configured to mount before `init_main` is run.

#### ugrd.fs.fakeudev

This module is used to create fake udev entries for DM devices.
This is only needed when using systemd, and if there are mounts that depend on a root DM device.

This module can be enabled by adding `ugrd.fs.fakeudev` to the `modules` list.

#### ugrd.fs.cpio

This module handles CPIO creation.

* `mknod_cpio` (true) Only create device nodes within the CPIO.
* `cpio_compression` (xz) Sets the compression method for the CPIO file.
* `cpio_rotate` (true) Rotates old CPIO files, keeping `old_count` number of old files.

##### General mount options

These are set at the global level and are not associated with an individual mount:

* `mount_wait` (false) Waits for user input before attenmpting to mount the generated fstab at `init_main`.
* `mount_timeout` - Timeout for `mount_wait` to automatically continue, passed to `read -t`.

#### ugrd.fs.btrfs

Importing this module will run `btrfs device scan` and pull btrfs modules.

* `subvol_selector` (false) The root subvolume will be selected at runtime based on existing subvolumes. Overridden by `root_subvol`.
* `autodetect_root_subvol` (true) Autodetect the root subvolume, unless `root_subvol` or `subvol_selector` is set. Depends on `hostonly`.
* `root_subvol` - Set the desired root subvolume.
* `_base_mount_path` (/root_base) Sets where the subvolume selector mounts the base filesytem to scan for subvolumes.

#### symlink creation

Symlinks are defined in the `symlinks` dict. Each entry must have a name, `source` and `target`:

```
[symlinks.pinentry]
source = "/usr/bin/pinentry-tty"
target = "/usr/bin/pinentry"
```

#### Copying files

Using the `dependencies` list will pull files into the initramfs using the same path on the host system.

```
dependencies = [ "/etc/ugrd/testfile" ]
```

#### Copying files to a different destination

To copy files to a different path:

```
[copies.my_key]
source = "/home/larry/.gnupg/pubkey.gpg"
destination = "/etc/ugrd/pub.gpg"
```

##### Device node creation

Device nodes can be created by defining them in the `nodes` dict using the following keys:

* `mode` (0o600) the device node, in octal.
* `path` (/dev/node name) the path to create the node at.
* `major` - Major value.
* `minor` - Minor value.

Example:

```
[nodes.console]
mode = 0o644
major = 5
minor = 1
```

Creates `/dev/console` with permissions `0o644`

> Using `mknod_cpio` from `ugrd.fs.cpio` will not create the device nodes in the build dir, but within the CPIO archive

### Cryptographic modules

Several cryptographic modules are provided, mostly to assist in mounting encrypted volumes and handling keyfiles.

#### ugrd.crypto.gpg

This module is required to perform GPG decryption within the initramfs. It depends on the `ugrd.base.console` module for agetty, which is required for input. Additionally, it depends on the `ugrd.crypt.cryptsetup` module, so both do not need to be defind.

`gpg_agent_args` is an append-only list which defines arguments passed to `gpg-agent`.

This module sets the `primary_console` to `tty0` and creates the console entry for it.
This configuration can be overriden in the specified user config if an actual serial interface is used, this is demonstrated in `config_raid_crypt_serial.toml`

#### ugrd.crypto.smartcard

Depends on the `ugrd.crypto.gpg` submodule, meant to be used with a YubiKey.

> Sets `cryptsetup_autoretry` to false

`sc_public_key` should point to the public key associated with the smarcard used to decrypt the GPG protected LUKS keyfile.
This file is added as a dependency and pulled into the initramfs.

#### ugrd.crypto.cryptsetup

This module is used to decrypt LUKS volumes in the initramfs.

> Modules such as the GPG and smartcard modules pull this automatically

Cryptsetup mounts can be configured with the following options:
* `key_type` - The type of key being used, if one is being used.
* `key_file` - The path of a key file.
* `key_command` - The command used to unlock or use the key.
* `reset_command` - The command to be used between unlock attempts.
* `header_file` - The path of the luks header file.
* `partuuid` - The partition UUID of the LUKS volume.
* `uuid` - The UUID fo the LUKS filesystem.
* `path` - The device path of the LUKS volume (validation must be disabled).
* `retries` (5) The number of times to attempt to unlock a key or cryptsetup volume.
* `try_nokey` (false) Whether or not to attempt unlocking with a passphrase if key usage fails
* `include_key` (false) Whether or not to include the key file in the initramfs.

`cryptsetup` is a dictionary that contains LUKS volumes to be decrypted.

> If `validate` is set to true, additional checks will be used to verify specified LUKS volumes
> Validation cannot be used with `path`, since storage paths may change at boot time.

A minimal defintion to decrypt a volume protected by a passphrase:

```
[cryptsetup.root]
uuid = "9e04e825-7f60-4171-815a-86e01ec4c4d3"
```

A cryptsetup mount which retries only 3 times, uses the key file `/boot/luks.gpg` with header file `/boot/luks_headers.img`:

```
[crytpsetup.root]
retries = 3
partuuid = "9e04e825-7f60-4171-815a-86e01ec4c4d3"
header = "/boot/luks_headers.img"
key_file = "/boot/luks.gpg"
key_type = "gpg"
```

Cryptsetup global config:

* `cryptsetup_key_type` - Sets the default `key_type` for all cryptsetup entries. 
* `cryptsetup_retries` (5) The default number of times to try to unlock a device.
* `cryptsetup_prompt` (false) Whether or not to prompt the user to press enter before attempting to unlock a device.
* `cryptsetup_autoretry` (false) Whether or not to automatically retry mount attempts.
* `cryptsetup_trim` (false) Whether or not to pass `--allow-discards` to cryptsetup (reduces security).
* `cryptsetup_keyfile_validation` (true) Whether or not to validate that keyfiles should exist at runtime.

##### Key type definitions

New key types can defined using the `cryptsetup_key_types` dict. At least `key_command` must be specified. The name of the key file is added to the end of this command:

```
[cryptsetup_key_types.gpg]
key_command = "gpg --decrypt {key_file} >"
```

Gets turned into:

```
gpg --decrypt /boot/luks.gpg > /run/key_root
```

When used with:

```
[cryptsetup.root]
key_type = "gpg"
key_file = "/boot/luks.gpg"
```

#### masks

To mask an import used by another module, the mask parameter can be used:

```
[mask]
init_final = ['mount_root']

```

This will mask the `mount_root` function pulled by the base module, if another mount function is being used.

