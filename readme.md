# µgRD

> Microgram Ramdisk is a framework used to generate ramdisks using TOML definitions and python functions

## Project goal

ugrd is designed to generate custom initramfs environments. The final environment will be left in `build_dir` where it can be explored or modified.

The original goal of this project was to create an initramfs suitable for decrypting LUKS volumes, currently it supports the following:

* Basic configuration validation in `validate` mode
* OpenPGP Smartcards (YubiKey)
* GPG encrypted LUKS keyfiles
* LUKS with detatched headers
* Cryptsetup re-attempts and alternative unlock methods
  - Allows for late insertion of a smartcard
  - Can fail back to plain password entry
* Auto-detection of kernel modules using `lspci` and `lsmod`
* Auto-detection of the root mount using `/proc/mounts`
* Similar usage/arguments as Dracut
* Reading the `root=` parameter from the kernel commandline
  - Falls back to host mount config if cmdline mount parameters fail
* BTRFS subvolumes selection
* Key entry over serial
* Automatic CPIO generation (PyCPIO)
  - Device nodes are created within the CPIO only, so true root privileges are not required.
  - Hardlinks are automatically created for files with matching SHA256 hashes.

## Installation

To install `ugrd`, clone the repo and run `pip install .`.

> Setting `--break-system-packages` may be necessary

### Gentoo

`ugrd` is in the GURU repos. It can be installed with:

```
eselect repository enable guru
emerge --sync
emerge sys-kernel/ugrd
```

## Usage

Once installed, `ugrd` can be executed as root to create an initramfs based on the definition in `/etc/ugrd/config.toml`.

### Supplying configuration

Alternate configuration can be supplied with:

`ugrd -c example_config.toml`

### Overriding the output location

The last argument is the output file, which can be a path:

`ugrd /boot/ugrd.cpio`

> If no path information is supplied, the filename provided will be created under `build_dir`

### Hostonly mode

The `hostonly` boolean is enabled by default and must be set to use the `lsmod` and `lspci` kmod options, as well as `validation` mode.

It can be forced at runtime with `--hostonly` and disabled with `--no-hostonly`.

### Validation mode

The `validate` option is set by default and attempts to verify that the generated initramfs will work on the system creating it.

It can be forced at runtime with `--validate` and disabled with `--no-validate`.

## Output

Unless the `ugrd.base.cpio` module is included, an initramfs environment will be generated at `build_dir` which defaults to `/tmp/initramfs/`.

### Embedding the initramfs image into the kernel

The `build_dir`can be embedded into the Linux kernel using `CONFIG_INITRAMFS_SOURCE="/tmp/initramfs"`.

A CPIO file can be embedded into the Linux kernel passing the path: `CONFIG_INITRAMFS_SOURCE="/usr/src/initramfs/ugrd.cpio"`

### Making the kernel automatically search for the initamfs image

To make the kernel try to load a specific initrd file at boot, without embedding it:

```
CONFIG_CMDLINE_BOOL=y
CONFIG_CMDLINE="initrd=ugrd.cpio"
```

> This will use `ugrd.cpio` under the ESP.

### efibootmgr configuration

If the kernel is built with the `CONFIG_EFI_STUB` option, the path of the initramfs can be passed to it with the `initrd=` command line option.

This can be set with:

`efibootmgr -c -d /dev/sda -L "Gentoo UGRD" -l 'vmlinuz-gentoo.efi' -u 'initrd=ugrd.cpio'`

> This example assumes that the ESP is the first partition on `/dev/sda`, the kernel is named `vmlinuz-gentoo.efi` under the root of the ESP, and `ugrd.cpio` is also on the ESP root.

> On some systems, the EFI may remove entries that don't follow a particular format.

## Runtime usage

`ugrd` runs the `init` script generated in the build dir. In cases where `agetty` is needed, all but basic initialization and the final switch_root are performed in `init_main.sh`.

UGRD should prompt for relevant input or warn if devices are missing at runtime.

> If UGRD does not print it's version after the kernel calls /init, the `ugrd.base.console` module may need to be enabled to start an agetty session.

### Failure recovery

In the event of a failure, modules will either fail through, or re-exec the init script.

If a CPIO file is generated, it can be passed to the bootloader. Embedding the initramfs into the kernel is preferred, as the entire kernel image can be signed.

## Configuration

At runtime, ugrd will try to read `config.toml` for configuration options unless another file is specified..

### Base modules

Several basic modules are provided for actions such as mounts, config processing, and other basic parameters.

Modules write to a shared config dict that is accessible by other modules.

#### base.base

> The main module, mostly pulls basic binaries and pulls the `core`, `mounts`, and `cpio` module.

* `shebang` (#!/bin/bash) sets the shebang on the init script.
* `switch_root_target` Sets the `switch_root` target, if different from the root mount destination.

#### base.core

* `build_dir` (/tmp/initramfs) Defines where the build will take place.
* `out_dir` (/tmp/initramfs_out) Defines where packed files will be placed.
* `clean` (true) forces the build dir to be cleaned on each run.
* `hostonly` (true) Builds the initramfs for the current host, if disabled, validation is automatically disabled.
* `validate` (true) adds additional checks to verify the initramfs will work on the build host.
* `old_count` (1) Sets the number of old file to keep when running the `_rotate_old` function.
* `file_owner` (portage) sets the owner for items pulled into the initramfs on the build system
* `binaries` is a list used to define programs to be pulled into the initrams. `which` is used to find the path of added entries, and `lddtree` is used to resolve dependendies.
* `paths` is a list of directores to create in the `build_dir`. They do not need a leading `/`.

##### Build logging

Verbose information about what what is being moved into the initramfs build directory can be enabled by setting `build_logging` to `true`.

`_build_log_level` can be manually set to any log level. It is incremented by 10 when `build_logging` is enabled, with a minimum of 20.

This can be enabled at runtime with `--build-logging` or disabled wit `--no-build-logging`

The output can be logged to a file instead of stdout by specifying a log file with `--log-file`

#### base.cmdline

If used, this module will override the `mount_root` function and attempt to mount the root based on the passed cmdline parameters.

##### symlink creation

Symlinks are defined in the `symlinks` dict. Each entry must have a name, `source` and `target`:

```
[symlinks.pinentry]
source = "/usr/bin/pinentry-tty"
target = "/usr/bin/pinentry"
```

##### Copying files to a different destination

Using the `dependencies` list will pull files into the initramfs using the same path on the host system.

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
* `major` Major value.
* `minor` Minor value.

Example:

```
[nodes.console]
mode = 0o644
major = 5
minor = 1
```

Creates `/dev/console` with permissions `0o644`

> Using `mknod_cpio` from `ugrd.fs.cpio` will not create the device nodes in the build dir, but within the CPIO archive

#### base.console

This module creates an agetty session. This is used by the `ugrd.crypto.gpg` module so the tty can be used for input and output.

Consoles are defined by name in the `console` dict using teh following keys:

* `type` (tty) specifies the console type, such as `tty` or `vt100`.
* `baud` Specified the baud rate for serial devices.

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

`primary_console` (tty0)  is used to set which console will be initialized with agetty on boot.

#### base.debug

This module contains debug programs such as `cp`, `mv`, `rm`, `grep`, `dmesg`, `find`, and `nano`,

Setting `start_shell` to `true` will start a bash shell in `init_debug`.

### Kernel modules

`ugrd.kmod.kmod` is the core of the kernel module loading..

#### ugrd.kmod.kmod confugration parameters

The following parameters can be used to change the kernel module pulling and initializing behavior:

* `kernel_version` (uname -r) is used to specify the kernel version to pull modules for, should be a directory under `/lib/modules/<kernel_version>`.
* `kmod_pull_firmware` (true) Adds kernel module firmware to dependencies
* `kmod_init`  is used to specify kernel modules to load at boot. If set, ONLY these modules will be loaded with modprobe.
* `kmod_autodetect_lspci` (false) if set to `true`, will populate `kernel_modules` with modules listed in `lspci -k`.
* `kmod_autodetect_lsmod` (false) if set to `true`, will populate `kernel_modules` with modules listed in `lsmod`.
* `kernel_modules` is used to define a list of kernel module names to pull into the initramfs. These modules will not be `modprobe`'d automatically if `kmod_init` is also set.
* `kmod_ignore` is used to specify kernel modules to ignore. If a module depends on one of these, it will throw an error and drop it from being included.
* `kmod_ignore_softdeps` (false) ignore softdeps when checking kernel module dependencies.

#### Kernel module helpers

Some helper modules have been created to make importing required kernel modules easier.

`ugrd.kmod.nvme`, `usb`, and `fat` can be used to load modules for NVME's, USB storage, and the FAT file system respectively.

Similarly `ugrd.kmod.novideo` `nonetwork`, and `nosound` exist to ignore video, network, and sound devices that may appear when autodetecting modules.

### Filesystem modules

`autodetect_root` (true) Set the root mount parameter based on the current root label or uuid.

#### ugrd.fs.mounts

`mounts`: A dictionary containing entries for mounts, with their associated config.

`mounts.root` is predefined to have a destination of `/mnt/root` and defines the root filesystem mount, used by `switch_root`.

Each mount has the following available parameters:

* `type` (auto) the mount or filesystem type.
  - Setting the `type` to `vfat` includes the `vfat` kernel module automatically.
  - Setting the `type` to `btrfs` imports the `ugrd.fs.btrfs` module automatically.
* `destination` (/mount name) the mountpoint for the mount, if left unset will use /mount_name.
* `source` The source string or a dict with a key containing the source type, where the value is the target.
  - `uuid` Mount by the filesystem UUID.
  - `partuuid` Mount by the partition UUID.
  - `label` Mount by the device label.
* `options` A list of options to add to the mount.
* `base_mount` (false) is used for builtin mounts such as `/dev`, `/sys`, and `/proc`. Setting this to mounts it with a mount command in `init_pre` instead of using `mount -a` in `init_main`.
* `skip_unmount` (false) is used for the builtin `/dev` mount, since it will fail to unmount when in use. Like the name suggests, this skips running `umount` during `init_final`.
* `remake_mountpoint` will recreate the mountpoint with mkdir before the `mount -a` is called. This is useful for `/dev/pty`.

The most minimal mount entry that can be created must have a name, which will be used as the `destination`, and a `source`.

The following configuration mounts the device with `uuid` `ABCD-1234` at `/boot`:

```
[mounts.boot.source]
uuid = "ABCD-1234"
```

The following configuration mounts the `btrfs` subvolume `stuff`  with `label` `extra` to `/mnt/extra`:

```
[mounts.extra]
options = [ "subvol=stuff" ]
type = "btrfs"
destination = "/mnt/extra"

[mounts.extra.source]
label = "extra"
```

#### ugrd.fs.cpio

This module handles CPIO creation.

* `out_file` (ugrd.cpio) Sets the name of the output file, under `out_dir` unless a path is defined.
* `mknod_cpio` (true) Only create devicne nodes within the CPIO.

##### General mount options

These are set at the global level and are not associated with an individual mount:

* `mount_wait` (false) waits for user input before attenmpting to mount the generated fstab at `init_main`.
* `mount_timeout` timeout for `mount_wait` to automatically continue.


#### ugrd.fs.btrfs

Importing this module will run `btrfs device scan` and pull btrfs modules.

* `subvol_selector` (false) If enabled, the root subvolume will be selected at runtime based on existing subvolumes.
* `root_subvol` Can be set to the desired root subvolume.
* `base_mount_path` (/mnt/root_base) Used to determine where the subvolume selector mounts the base filesytem to scan for subvolumes.

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
* `retries` (5) - The number of times to attempt to unlock a key or cryptsetup volume.
* `try_nokey` - (false) - Whether or not to attempt unlocking with a passphrase if key usage fails

`cryptsetup` is a dictionary that contains LUKS volumes to be decrypted.

> If `validate` is set to true, additional checks will be used to verify specified LUKS volumes

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

#####

Cryptsetup global config:

* `cryptsetup_key_type` - Sets the default `key_type` for all cryptsetup entries. 
* `cryptsetup_retries` (5) The default number of times to try to unlock a device.
* `cryptsetup_autoretry` (false) Whether or not to automatically retry mount attempts.

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

## Modules

The modules config directive should contain a list with names specifying the path of which will be loaded, such as `ugrd.base.base`, `ugrd.base.console` or `ugrd.crypto.crypsetup`.

Another directory for modules can be created, the naming scheme is similar to how python imports work.

When a module is loaded, `initramfs_dict.py` will try to load the toml file for that module, parsing it in the same manner `config.yaml` is parsed.

The order in which modules/directives are loaded is very important!

Modules can load other modules using the `modules` directive, be careful considering loading orders.

If a module depends on another module, it can be added to the `mod_depends` list in the module config. A `ValueError` will be thrown if the module is not present.

> Modules can import other modules, but this would throw lots of warnings for things like the "no<kmod category>" modules

`_module_name` can be set within a module for logging purposes, it is verified to be accurate when imported but optional.

#### imports

The most powerful part of a module is the `imports` directive.

Imports are used to hook into the general processing scheme, and become part of the main `InitramfsGenerator` object.

Portions are loaded into the InitramfsGenerator's `config_dict` which is an `InitramfsConfigDict`

`imports` are defined like:

```
[imports.<hook>]
"module_dir.module_name" = [ "function_to_inject" ]
```

For example:

```
[imports.build_tasks]
"ugrd.fs.mounts" = [ "generate_fstab" ]
```

Is used in the base module to make the initramfs generator generate a fstab durinf the `build_tasks` phase.

Imported functions have access to the entire `self` scope, giving them full control of whatever other modules are loaded when they are executed, and the capability to dynamically create new functions.

This script should be executed as root, to have access to all files and libraries required to boot, so special care should be taken when loading and creating modules. 

#### masks

To mask an import used by another module, the mask parameter can be used:

```
[mask]
init_final = ['mount_root']

```

This will mask the `mount_root` function pulled by the base module, if another mount function is being used.

#### config_processing

These imports are very special, they can be used to change how parameters are parsed by the internal `config_dict`.

A good example of this is in `base.py`:

```
def _process_mounts_multi(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'mounts'
    """
    if 'destination' not in mount_config:
        mount_config['destination'] = f"/{key}"  # prepend a slash

    try:
        self['mounts'][key] = FstabMount(**mount_config)
        self['paths'].append(mount_config['destination'])
    except ValueError as e:
        self.logger.error("Unable to process mount: %s" % key)
        self.logger.error(e)
```

This module manages mount management, and loads new mounts into fstab objects, also defined in the base module.

The name of `config_prcessing` functions is very important, it must be formatted like `_process_{name}` where the name is the root variable name in the yaml config.

If the function name has `_multi` at the end, it will be called using the `handle_plural` function, iterating over passed lists/dicts automatically.

A new root varaible named `oops` could be defined, and a function `_process_oops` could be created and imported, raising an error when this vlaue is found, for example.

This module is loaded in the imports section of the `base.yaml` file:

```
[imports.config_processing]
"ugrd.fs.mounts" = [ "_process_mounts_multi" ]
```

#### Imports

UGRD allows functions to be imported from modules using the `imports` dict.

This is primarily used to run additional functions at build time, add init functions, and add library functions.

##### build_pre

`build_pre` contains build tasks which are run at the very start of the build, such as build directory cleaning and additional config processing.

##### build_tasks

`build_tasks` are functions which will be executed after `build_pre`, such as dependency pulling.

##### build_late

`build_late` functions are executed after the init has been generated.

##### pack

Packing facts, such as CPIO generation can be defined in the `pack` import.

The `cpio` module imports the `make_cpio_list` packing function with:

```
[imports.pack]
"ugrd.fs.cpio" = [ "make_cpio" ]
```

##### funcs

Functions can be added to `imports.funcs` to force the output to be added to `init_funcs.sh`.

##### init hooks

By default, the specified init hooks are:
* `init_pre` - Where the base initramfs environment is set up, such as creating a devtmpfs.
* `init_debug` - Where a shell is started if `start_shell` is enabled in the debug module.
* `init_early` - Where early actions such as checking for device paths, mounting the fstab take place.
* `init_main` - Most important initramfs activities should take place here.
* `init_late` - Space for additional checks, stuff that should run later in the init process.
* `init_premount` - Where filesystem related commands such as `btrfs device scan` can run.
* `init_mount` - Where the root filesystem mount takes place
* `init_cleanup` - Where filesystems are unmounted and the system is prepared to `exec switch_root`
* `init_final` - Where `switch_root` is executed.

> These hooks are defined under the `init_types` list in the `InitramfsGenerator` object.

When the init scripts are generated, functions under dicts in the config defined by the names in this list will be called to generate the init scripts.

Init functions should return a string or list of strings that contain shell lines to be added to the `init` file.

The `InitramfsGenerator.generate_init_main()` function (often called from `self`) can be used to output all init hook levels but `init_pre` and `init_final`.

A general overview of the procedure used for generating the init is to write the chosen `shebang`, then every init hook. The `custom_init` import can be used for more advanced confugrations, such as running another script in `agetty`.

##### custom_init

To change how everything but `init_pre` and `init_file` are handled at runtime, `custom_init` can be used.

The `console` module uses the `custom_init` hook to change the init creation procedure.

Like with the typical flow, it starts by creating the base `init` file with the shebang and `init_pre` portions. Once this is done, execution is handed off to all fucntions present in the `custom_init` imports.

Finally, like the standard init build, the `init_final` is written to the main `init` file.

```
[imports.custom_init]
"ugrd.base.console" = [ "custom_init" ]
```

The `custom_init` function should return a tuple with the line used to call the custom init file, and the contents of it.


```
def custom_init(self) -> str:
    """
    init override for the console module.
    Write the main init runlevels to self._custom_init_file.
    Returns the output of console_init which is the command to start agetty.
    """
    custom_init_contents = [self['shebang'],
                            f"# Console module version v{__version__}",
                            *self.generate_init_main()]

    return console_init(self), custom_init_contents


def console_init(self) -> str:
    """
    Start agetty on the primary console.
    Tell it to execute teh _custom_init_file
    If the console is a serial port, set the baud rate.
    """
    name = self['primary_console']
    console = self['console'][name]

    out_str = f"agetty --autologin root --login-program {self['_custom_init_file']}"

    console_type = console.get('type', 'tty')

    if console_type != 'tty':
        # This differs from usage in the man page but seems to work?
        out_str += f" --local-line {console['baud']}"

    out_str += f" {name} {console_type}"

    return out_str
```
