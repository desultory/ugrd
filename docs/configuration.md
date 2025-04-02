# Configuration

At runtime, µgRD will try to read `/etc/ugrd/config.toml` for configuration options unless another file is specified.

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

* `switch_root_target` Set the target filesystem for `switch_root`, defaults to the root mountpoint if not set.
* `init_target` Sets the init target for `switch_root`.
* `autodetect_init` (true) Automatically set the init target based `which init`.
* `loglevel` (5) Sets the kernel log level in the init script.
* `shebang_args` (-l) sets the args for the shebang on the init script.
* `shebang` (#!/bin/sh) sets the shebang on the init script. (DEPRECATED, use shell and shebang_args)

### base.core

* `hostonly` (true) Builds the initramfs for the current host, if disabled, validation is automatically disabled.
* `validate` (true) adds additional checks to verify the initramfs will work on the build host.
* `tmpdir` (/tmp) Sets the temporary directory as the base for the build and out dir.
* `build_dir` (initramfs_build) If relative, it will be placed under `tmpdir`, defines the build directory.
* `random_build_dir` (false) Adds a uuid to the end of the build dir name when true.
* `build_logging` (false) Enables additional logging during the build process.
* `make_nodes` (false) Create real device nodes in the build dir. 
* `find_libgcc` (true) Automatically locates libgcc using ldconfig -p and adds it to the initramfs.
* `out_dir` (initramfs_out) If relative, it will be placed under `tmpdir`, defines the output directory.
* `out_file` Sets the name of the output file, under `out_dir`.
* `clean` (true) forces the build dir to be cleaned on each run.
* `old_count` (1) Sets the number of old file to keep when running the `_rotate_old` function.
* `binaries` - A list used to define programs to be pulled into the initrams. `which` is used to find the path of added entries, and `lddtree` is used to resolve dependendies.
* `binary_search_paths` ("/bin", "/sbin", "/usr/bin", "/usr/sbin") - Paths to search for binaries, automatically updated when binaries are added.
* `libraries` - A list of libaries searched for and added to the initramfs, by name.
* `library_paths` ("/lib", /lib64") - Paths to search for libraries, automatically updated when libraries are added.
* `paths` - A list of directores to create in the `build_dir`. They do not need a leading `/`.
* `shell` (/bin/sh) Sets the shell to be used in the init script.

#### Copying files

Using the `dependencies` list will pull files into the initramfs using the same path on the host system.

```
dependencies = [ "/etc/ugrd/testfile" ]
```

##### Optional dependencies

`opt_dependencies` attempts to add a file to `dependencies` but will not raise an error if the file is not found.

##### Compressed dependencies

`xz_dependencies` and `gz_dependnencies` can be used to decompress dependencies before adding them to the initramfs.

#### Copying files to a different destination

To copy files to a different path:

```
[copies.my_key]
source = "/home/larry/.gnupg/pubkey.gpg"
destination = "/etc/ugrd/pub.gpg"
```

#### symlink creation

Symlinks are defined in the `symlinks` dict. Each entry must have a name, `source` and `target`:

```
[symlinks.pinentry]
source = "/usr/bin/pinentry-tty"
target = "/usr/bin/pinentry"
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

By default, they will be processed by `ugrd.fs.cpio` and added to the CPIO archive.

To create device nodes in the build dir, set `make_nodes` to `true`.

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

This module contains debug programs such as `cp`, `mv`, `rm`, `grep`, `dmesg`, `find`, and an editor,

Setting `start_shell` to `true` will start a bash shell in `init_debug`.

Use `editor` to manually specify the editor binary, otherwise it is autodetected from the `EDITOR` environment variable
> If `validation` is enabled the editor binary is checked against a list of common editors, use `no_validate_editor` to skip this check if needed

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

#### Kernel module masks

By default, most unnecesaary modules are masked, by the following categories:

* `kmod_ignore_video` (true) - Ignores video modules.
* `kmod_ignore_network` (true) - Ignores network modules.
* `kmod_ignore_sound` (true) - Ignores sound modules.

These bools simply import `ugrd.kmod.no<category>` modules during `build_pre`. 

### Filesystem modules

`ugrd.fs.mounts` is the core of the filesystem module category and is included by default.

Additional modules include:

* `ugrd.fs.bcachefs` - Adds the bcachefs module and binary for mounting.
* `ugrd.fs.btrfs` - Helps with multi-device BTRFS mounts, subvolume selection.
* `ugrd.fs.fakeudev` - Makes 'fake' udev entries for DM devices.
* `ugrd.fs.cpio` - Packs the build dir into a CPIO archive with PyCPIO.
* `ugrd.fs.livecd` - Assists in livecd image creation.
* `ugrd.fs.lvm` - Activates LVM mounts.
* `ugrd.fs.mdraid` - For MDRAID mounts.
* `ugrd.fs.resume` - Handles resume from hibernation.
* `ugrd.fs.test_image` - Creates a test rootfs for automated testing.
* `ugrd.fs.zfs` - Adds basic ZFS support.

#### ugrd.fs.mounts

* `autodetect_root` (true) Set the root mount parameter based on the current root label or uuid.
* `autodetect_root_dm` (true) Attempt to automatically configure virtual block devices such as LUKS/LVM/MDRAID.
* `autodetect_root_luks` (true) Attempt to automatically configure LUKS mounts for the root device.
* `autodetect_root_lvm` (true) Attempt to automatically configure LVM mounts for the root device.
* `autodetect_root_mdraid` (true) Attempt to automatically configure MDRAID mounts for the root device.
* `autodetect_init_mount'` (true) Automatically detect the mountpoint for the init binary, and add it to `late_mounts`.
* `run_dirs` A list of directories to create under `/run/` at runtime

> `autodetect_root` is required for `autodetect_root_<type>` to work.

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
* `cpio_compression` (xz) Sets the compression method for the CPIO file, passed to PyCPIO.
* `cpio_rotate` (true) Rotates old CPIO files, keeping `old_count` number of old files.

##### General mount options

These are set at the global level and are not associated with an individual mount:

* `mount_timeout` (1.0) - Timeout in seconds for mount retries, can be set with `rootdelay` in the kernel command line.
* `mount_retries` - Number of times to retry running `mount -a`, no limit if unset.

#### ugrd.fs.btrfs

Importing this module will run `btrfs device scan` and pull btrfs modules.

* `subvol_selector` (false) The root subvolume will be selected at runtime based on existing subvolumes. Overridden by `root_subvol`.
* `autodetect_root_subvol` (true) Autodetect the root subvolume, unless `root_subvol` or `subvol_selector` is set. Depends on `hostonly`.
* `root_subvol` - Set the desired root subvolume.
* `_base_mount_path` (/root_base) Sets where the subvolume selector mounts the base filesytem to scan for subvolumes.

#### ugrd.fs.resume

When enabled, attempts to resume after hibernation if resume= is passed on the kernel command line.

> Please use the following option with **CAUTION** as it can be unstable in certain configurations! Any writes to disks that occur pre-resume run the risk of causing system instability! For more information have a read of the warnings in the [kernel docs](https://www.kernel.org/doc/html/latest/power/swsusp.html).

* `late_resume` (true) When enabled will attempt to resume from hibernation after decryption and device mapping, allowing resume from encrypted or otherwise hidden swap devices.

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
* `include_header` (false) Whether or not to include the header file in the initramfs.
* `validate_key` (true) Whether or not to validate that the key file exists.
* `validate_header` (true) Whether or not to validate the LUKS header.

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
* `cryptsetup_header_validation` (true) Whether or not to validate LUKS headers at runtime.

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

